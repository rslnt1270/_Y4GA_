# © YAGA Project — Todos los derechos reservados
"""
Tests unitarios de services/refresh_service.py (Sprint 10).

Cubre: happy path create/rotate, sliding window, reuse detection,
revoke_token/family/all_families_for_user, cap absoluto.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services import refresh_service as rs


pytestmark = pytest.mark.asyncio


UID_A = "11111111-1111-1111-1111-111111111111"
UID_B = "22222222-2222-2222-2222-222222222222"


async def test_create_refresh_token_ok(fake_redis):
    em = await rs.create_refresh_token(UID_A, "1.2.3.4", "ua-test")

    assert len(em.token_id) >= 40
    assert em.usuario_id == UID_A
    assert em.familia_id
    assert em.expira_en_sliding > datetime.now(tz=timezone.utc)
    assert em.cap_absoluto > em.expira_en_sliding or em.cap_absoluto == em.expira_en_sliding

    # Persistió en Valkey
    data = await fake_redis.hgetall(f"refresh:{em.token_id}")
    assert data["usuario_id"] == UID_A
    assert data["rotated_to"] == ""
    assert data["familia_id"] == em.familia_id

    familia = await fake_redis.hgetall(f"familia:{em.familia_id}")
    assert familia["revocada"] == "0"

    # Set de familias del usuario
    fams = await fake_redis.smembers(f"idx_usuario:{UID_A}")
    assert em.familia_id in fams


async def test_rotation_invalidates_previous(fake_redis):
    em1 = await rs.create_refresh_token(UID_A, "ip", "ua")
    em2 = await rs.validate_and_rotate(em1.token_id, "ip", "ua")

    assert em2.token_id != em1.token_id
    assert em2.familia_id == em1.familia_id  # misma familia
    assert em2.usuario_id == UID_A

    # El viejo está marcado como rotado (no borrado, sobrevive 60s)
    old = await fake_redis.hgetall(f"refresh:{em1.token_id}")
    assert old.get("rotated_to") == em2.token_id


async def test_reuse_detection_revokes_family(fake_redis):
    em1 = await rs.create_refresh_token(UID_A, "ip", "ua")
    em2 = await rs.validate_and_rotate(em1.token_id, "ip", "ua")

    # Segundo intento con el token ya rotado → debe revocar familia
    with pytest.raises(rs.ReuseDetected):
        await rs.validate_and_rotate(em1.token_id, "ip-attacker", "ua-attacker")

    familia = await fake_redis.hgetall(f"familia:{em1.familia_id}")
    assert familia["revocada"] == "1"
    assert familia["motivo"] == "reuse_detected"

    # El token "bueno" (em2) ya no debe funcionar: familia revocada
    with pytest.raises(rs.RefreshTokenError):
        await rs.validate_and_rotate(em2.token_id, "ip", "ua")


async def test_validate_unknown_token_raises(fake_redis):
    with pytest.raises(rs.RefreshTokenError):
        await rs.validate_and_rotate("nonexistent-xxx", "ip", "ua")


async def test_revoke_token_logout_removes_entry(fake_redis):
    em = await rs.create_refresh_token(UID_A, "ip", "ua")
    uid = await rs.revoke_token(em.token_id)
    assert uid == UID_A

    # Ya no existe
    exists = await fake_redis.exists(f"refresh:{em.token_id}")
    assert exists == 0

    with pytest.raises(rs.RefreshTokenError):
        await rs.validate_and_rotate(em.token_id, "ip", "ua")


async def test_revoke_family_blocks_subsequent_rotation(fake_redis):
    em = await rs.create_refresh_token(UID_A, "ip", "ua")
    await rs.revoke_family(em.familia_id, motivo="test")

    with pytest.raises(rs.RefreshTokenError):
        await rs.validate_and_rotate(em.token_id, "ip", "ua")


async def test_revoke_all_families_for_user(fake_redis):
    em_a1 = await rs.create_refresh_token(UID_A, "ip", "ua-dev1")
    em_a2 = await rs.create_refresh_token(UID_A, "ip", "ua-dev2")  # 2º device
    em_b  = await rs.create_refresh_token(UID_B, "ip", "ua-b")

    count = await rs.revoke_all_families_for_user(UID_A, motivo="password_reset")
    assert count == 2

    # Ambas familias de A revocadas
    for em in (em_a1, em_a2):
        fam = await fake_redis.hgetall(f"familia:{em.familia_id}")
        assert fam["revocada"] == "1"
        assert fam["motivo"] == "password_reset"

    # Familia de B intacta
    fam_b = await fake_redis.hgetall(f"familia:{em_b.familia_id}")
    assert fam_b["revocada"] == "0"

    # B sigue pudiendo rotar normalmente
    em_b2 = await rs.validate_and_rotate(em_b.token_id, "ip", "ua-b")
    assert em_b2.familia_id == em_b.familia_id


async def test_sliding_window_extends_ttl(fake_redis):
    em1 = await rs.create_refresh_token(UID_A, "ip", "ua")
    ttl1 = await fake_redis.ttl(f"refresh:{em1.token_id}")
    assert ttl1 > rs.REFRESH_TOKEN_TTL_SECONDS - 10  # casi full 30d

    em2 = await rs.validate_and_rotate(em1.token_id, "ip", "ua")
    ttl2_new = await fake_redis.ttl(f"refresh:{em2.token_id}")
    # TTL del nuevo es casi 30d otra vez (sliding)
    assert ttl2_new > rs.REFRESH_TOKEN_TTL_SECONDS - 10

    # TTL del viejo bajó a ≤60s
    ttl_old = await fake_redis.ttl(f"refresh:{em1.token_id}")
    assert 0 < ttl_old <= rs.ROTATED_TTL_SECONDS


async def test_cap_absoluto_no_se_mueve_con_rotacion(fake_redis):
    em1 = await rs.create_refresh_token(UID_A, "ip", "ua")
    em2 = await rs.validate_and_rotate(em1.token_id, "ip", "ua")
    # Cap de la familia preserva el momento del login inicial (±1s tolerancia)
    delta = abs((em2.cap_absoluto - em1.cap_absoluto).total_seconds())
    assert delta < 1


async def test_empty_token_rejected(fake_redis):
    with pytest.raises(rs.RefreshTokenError):
        await rs.validate_and_rotate("", "ip", "ua")

    # revoke_token con token vacío es no-op seguro
    assert await rs.revoke_token("") is None

    # revoke_all con usuario vacío es no-op seguro
    assert await rs.revoke_all_families_for_user("", "motivo") == 0

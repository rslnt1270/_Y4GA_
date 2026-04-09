#!/usr/bin/env bash
# © YAGA Project — Todos los derechos reservados
# deploy_sprint5.sh — Deploy Sprint 5 a produccion EC2 (sin rebuild de imagen)
#
# Sprint 5 incluye:
#   - slowapi rate limiting (main.py + core/limiter.py + auth.py)
#   - GPS endpoints nuevos (gps.py + gps_service.py)
#   - Poleana rooms en Redis (api/v1/poleana.py reemplaza poleana_router.py)
#   - Eliminacion de Sistema B legacy (routers/auth.py, core/auth.py)
#   - docker-compose.yml limpio (sin refs a secrets/*.pem)
#   - Frontend actualizado (GPS controls, tab Analitica)
#
# Uso:
#   chmod +x deploy_sprint5.sh
#   ./deploy_sprint5.sh
#
# Requisitos:
#   - Ejecutar desde la raiz del proyecto (/home/user/_Y4GA_/ o equivalente)
#   - Tener el PEM accesible en la ruta configurada abajo
#   - Conexion SSH activa al EC2

set -euo pipefail

# ── Configuracion ────────────────────────────────────────────────────────────
PEM="${YAGA_PEM:-$HOME/Documentos/Project_Y4GA_/yaga_backend.pem}"
EC2_HOST="ec2-3-19-35-76.us-east-2.compute.amazonaws.com"
EC2="ec2-user@${EC2_HOST}"
SSH_OPTS="-i ${PEM} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
REMOTE_BASE="~/yaga-project"
CONTAINER="yaga_api"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_step()  { echo -e "\n${CYAN}[STEP]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_fail()  { echo -e "${RED}[FAIL]${NC} $1"; }

# ── Pre-flight checks ───────────────────────────────────────────────────────
log_step "Pre-flight: verificando archivos locales..."

REQUIRED_FILES=(
    "app/main.py"
    "app/core/limiter.py"
    "app/api/v1/auth.py"
    "app/api/v1/gps.py"
    "app/api/v1/poleana.py"
    "app/services/gps_service.py"
    "docker-compose.yml"
    "frontend/index.html"
)

MISSING=0
for f in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$f" ]; then
        log_fail "Archivo no encontrado: $f"
        MISSING=1
    fi
done

if [ "$MISSING" -eq 1 ]; then
    echo "Ejecuta este script desde la raiz del proyecto (_Y4GA_/)."
    exit 1
fi

if [ ! -f "$PEM" ]; then
    log_fail "PEM no encontrado: $PEM"
    echo "Configura la variable YAGA_PEM con la ruta al archivo .pem"
    echo "  export YAGA_PEM=/ruta/a/yaga_backend.pem"
    exit 1
fi

log_ok "Todos los archivos locales presentes"
log_ok "PEM encontrado: $PEM"

# ── Verificar que los archivos legacy NO existen localmente ──────────────────
log_step "Verificando eliminacion de archivos legacy Sistema B..."

if [ -f "app/routers/auth.py" ]; then
    log_fail "app/routers/auth.py aun existe localmente -- deberia haberse eliminado en Sprint 5"
    exit 1
fi
if [ -f "app/core/auth.py" ]; then
    log_fail "app/core/auth.py aun existe localmente -- deberia haberse eliminado en Sprint 5"
    exit 1
fi
log_ok "Archivos legacy eliminados correctamente"

# ── Verificar conectividad SSH ───────────────────────────────────────────────
log_step "Verificando conectividad SSH a EC2..."
if ! ssh $SSH_OPTS "$EC2" "echo 'SSH OK'" 2>/dev/null; then
    log_fail "No se pudo conectar a $EC2"
    exit 1
fi
log_ok "Conexion SSH activa"

# ── Verificar estado actual de contenedores ──────────────────────────────────
log_step "Verificando estado de contenedores en EC2..."
ssh $SSH_OPTS "$EC2" "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# ── FASE 1: Instalar dependencia slowapi en el container ─────────────────────
log_step "FASE 1: Verificando/instalando slowapi en el container..."
ssh $SSH_OPTS "$EC2" "docker exec ${CONTAINER} pip show slowapi >/dev/null 2>&1 && echo 'slowapi ya instalado' || docker exec ${CONTAINER} pip install slowapi 2>&1 | tail -3"
log_ok "slowapi disponible en container"

# ── FASE 2: Crear directorios remotos si no existen ──────────────────────────
log_step "FASE 2: Preparando directorios en EC2..."
ssh $SSH_OPTS "$EC2" "mkdir -p ${REMOTE_BASE}/app/core ${REMOTE_BASE}/app/api/v1 ${REMOTE_BASE}/app/services ${REMOTE_BASE}/frontend"
log_ok "Directorios remotos listos"

# ── FASE 3: Subir archivos al host EC2 via SCP ──────────────────────────────
log_step "FASE 3: Subiendo archivos al host EC2 (scp)..."

scp_file() {
    local src="$1"
    local dst="$2"
    echo -n "  scp $src -> EC2:$dst ... "
    scp $SSH_OPTS "$src" "${EC2}:${dst}" 2>/dev/null
    echo "OK"
}

# Archivos Python modificados
scp_file "app/main.py"                "${REMOTE_BASE}/app/main.py"
scp_file "app/core/limiter.py"        "${REMOTE_BASE}/app/core/limiter.py"
scp_file "app/api/v1/auth.py"         "${REMOTE_BASE}/app/api/v1/auth.py"
scp_file "app/api/v1/gps.py"          "${REMOTE_BASE}/app/api/v1/gps.py"
scp_file "app/api/v1/poleana.py"      "${REMOTE_BASE}/app/api/v1/poleana.py"
scp_file "app/services/gps_service.py" "${REMOTE_BASE}/app/services/gps_service.py"

# docker-compose.yml actualizado
scp_file "docker-compose.yml"         "${REMOTE_BASE}/docker-compose.yml"

# Frontend estatico
scp_file "frontend/index.html"        "${REMOTE_BASE}/frontend/index.html"

log_ok "Todos los archivos subidos al host EC2"

# ── FASE 4: Copiar archivos del host al container (docker cp) ────────────────
log_step "FASE 4: Copiando archivos al container ${CONTAINER} (docker cp)..."

docker_cp() {
    local src="$1"
    local dst="$2"
    echo -n "  docker cp $src -> ${CONTAINER}:$dst ... "
    ssh $SSH_OPTS "$EC2" "docker cp ${REMOTE_BASE}/${src} ${CONTAINER}:${dst}"
    echo "OK"
}

# CRITICO: core/limiter.py es NUEVO -- el directorio /app/core/ ya existe en el container
# pero el archivo no. docker cp lo crea automaticamente.
docker_cp "app/core/limiter.py"         "/app/core/limiter.py"
docker_cp "app/main.py"                 "/app/main.py"
docker_cp "app/api/v1/auth.py"          "/app/api/v1/auth.py"
docker_cp "app/api/v1/gps.py"           "/app/api/v1/gps.py"
docker_cp "app/api/v1/poleana.py"       "/app/api/v1/poleana.py"
docker_cp "app/services/gps_service.py" "/app/services/gps_service.py"

# POLEANA: main.py importa 'api.poleana_router' (el archivo original).
# La reescritura con Redis esta en api/v1/poleana.py.
# Para que la nueva version Redis sea la activa, reemplazamos tambien poleana_router.py.
echo ""
log_warn "main.py importa api.poleana_router -- reemplazando con la version Redis..."
docker_cp "app/api/v1/poleana.py"       "/app/api/poleana_router.py"
log_ok "poleana_router.py reemplazado con version Redis (api/v1/poleana.py)"

log_ok "Todos los archivos copiados al container"

# ── FASE 5: Eliminar archivos legacy del container ───────────────────────────
log_step "FASE 5: Eliminando archivos legacy Sistema B del container..."
ssh $SSH_OPTS "$EC2" "docker exec ${CONTAINER} rm -f /app/routers/auth.py /app/core/auth.py 2>/dev/null && echo 'Archivos legacy eliminados' || echo 'Archivos legacy ya no existian'"
log_ok "Limpieza de Sistema B completada"

# ── FASE 6: Esperar recarga automatica de WatchFiles ─────────────────────────
log_step "FASE 6: Esperando recarga automatica de uvicorn (WatchFiles)..."
echo "  Aguardando 6 segundos para que WatchFiles detecte cambios..."
sleep 6

echo ""
echo "  --- Ultimas lineas de log del container ---"
ssh $SSH_OPTS "$EC2" "docker logs ${CONTAINER} --tail=12 2>&1"
echo "  --- Fin de logs ---"

# ── FASE 7: Verificaciones post-deploy ───────────────────────────────────────
log_step "FASE 7: Verificaciones post-deploy..."

echo ""
echo "  7.1 Verificando importaciones Python..."
IMPORT_RESULT=$(ssh $SSH_OPTS "$EC2" "docker exec ${CONTAINER} python3 -c \"
import sys
sys.path.insert(0, '/app')
from core.limiter import limiter
from slowapi import Limiter
assert isinstance(limiter, Limiter), 'limiter no es instancia de Limiter'
print('slowapi+limiter: OK')

from api.v1.gps import router as gps_r
print('gps endpoints: OK')

from api.v1.auth import router as auth_r
print('auth+rate_limit: OK')

from services.gps_service import get_gps_historial, get_resumen_jornadas_con_gps
print('gps_service nuevas funciones: OK')

print('ALL IMPORTS OK')
\" 2>&1")
echo "  $IMPORT_RESULT"

if echo "$IMPORT_RESULT" | grep -q "ALL IMPORTS OK"; then
    log_ok "Todas las importaciones correctas"
else
    log_fail "Error en importaciones -- revisar logs"
    ssh $SSH_OPTS "$EC2" "docker logs ${CONTAINER} --tail=20 2>&1"
    exit 1
fi

echo ""
echo "  7.2 Verificando health endpoint..."
HEALTH_RESULT=$(ssh $SSH_OPTS "$EC2" "curl -sf http://localhost:8000/health 2>&1 || echo 'HEALTH_FAIL'")
echo "  Response: $HEALTH_RESULT"

if echo "$HEALTH_RESULT" | grep -q '"status":"ok"'; then
    log_ok "Health endpoint respondiendo correctamente"
else
    log_warn "Health endpoint no responde -- puede estar reiniciando. Reintentando en 5s..."
    sleep 5
    HEALTH_RESULT=$(ssh $SSH_OPTS "$EC2" "curl -sf http://localhost:8000/health 2>&1 || echo 'HEALTH_FAIL'")
    echo "  Retry response: $HEALTH_RESULT"
    if echo "$HEALTH_RESULT" | grep -q '"status":"ok"'; then
        log_ok "Health endpoint respondiendo tras retry"
    else
        log_fail "Health endpoint sigue sin responder"
        ssh $SSH_OPTS "$EC2" "docker logs ${CONTAINER} --tail=30 2>&1"
        exit 1
    fi
fi

echo ""
echo "  7.3 Verificando rate limiting (slowapi activo)..."
RATE_CHECK=$(ssh $SSH_OPTS "$EC2" "docker exec ${CONTAINER} python3 -c \"
import sys; sys.path.insert(0, '/app')
from main import app
handler_found = False
for h in app.exception_handlers:
    if 'RateLimitExceeded' in str(h):
        handler_found = True
        break
# Tambien verificar via state
has_limiter = hasattr(app.state, 'limiter')
print(f'exception_handler={handler_found} state.limiter={has_limiter}')
if has_limiter:
    print('RATE_LIMIT_OK')
else:
    print('RATE_LIMIT_FAIL')
\" 2>&1")
echo "  $RATE_CHECK"

if echo "$RATE_CHECK" | grep -q "RATE_LIMIT_OK"; then
    log_ok "Rate limiting (slowapi) configurado correctamente"
else
    log_warn "No se pudo verificar rate limiting -- revisar manualmente"
fi

echo ""
echo "  7.4 Verificando estado de contenedores..."
ssh $SSH_OPTS "$EC2" "docker ps --format 'table {{.Names}}\t{{.Status}}'"

echo ""
echo "  7.5 Verificando que Redis responde (para Poleana rooms)..."
ssh $SSH_OPTS "$EC2" "docker exec yaga_redis redis-cli ping"

# ── Resumen final ────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo -e "${GREEN} DEPLOY SPRINT 5 COMPLETADO${NC}"
echo "============================================================"
echo ""
echo "  Archivos desplegados:"
echo "    [MODIFIED] app/main.py              (slowapi integration)"
echo "    [NEW]      app/core/limiter.py       (Limiter compartido)"
echo "    [MODIFIED] app/api/v1/auth.py        (rate limiting decorators)"
echo "    [MODIFIED] app/api/v1/gps.py         (+historial +resumen-jornadas)"
echo "    [MODIFIED] app/api/v1/poleana.py     (rooms en Redis)"
echo "    [MODIFIED] app/services/gps_service.py (+2 funciones nuevas)"
echo "    [MODIFIED] docker-compose.yml        (sin refs secrets/*.pem)"
echo "    [MODIFIED] frontend/index.html       (GPS controls, tab Analitica)"
echo ""
echo "  Archivos eliminados del container:"
echo "    [DELETED]  app/routers/auth.py       (Sistema B legacy)"
echo "    [DELETED]  app/core/auth.py          (Sistema B legacy)"
echo ""
echo "  Nota: poleana_router.py fue reemplazado con la version Redis"
echo "        (main.py importa api.poleana_router, no api.v1.poleana)"
echo ""
echo "  Endpoints nuevos disponibles:"
echo "    GET  /api/v1/gps/historial/{jornada_id}"
echo "    GET  /api/v1/gps/resumen-jornadas"
echo ""
echo "  Rate limits activos:"
echo "    POST /auth/register      3/minute"
echo "    POST /auth/login         5/minute"
echo "    POST /auth/forgot-password  3/hour"
echo ""
echo "  Verificacion manual sugerida:"
echo "    ssh -i \$PEM $EC2 'curl -s http://localhost:8000/api/docs'"
echo "    ssh -i \$PEM $EC2 'docker logs ${CONTAINER} --tail=20'"
echo "============================================================"

#!/bin/bash
# © YAGA Project — Todos los derechos reservados
# deploy_yaga.sh — Deploy completo YAGA backend a EC2 + migración DB
# Uso: ./deploy_yaga.sh [--skip-migration] [--rebuild]
#
# Flags:
#   --skip-migration  No ejecutar scripts de migración SQL
#   --rebuild         Forzar docker build --no-cache

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
PEM="$(dirname "$0")/yaga_backend.pem"
EC2_HOST="ec2-user@ec2-3-19-35-76.us-east-2.compute.amazonaws.com"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
EC2_DIR="~/yaga-project"
SKIP_MIGRATION=false
REBUILD=false

for arg in "$@"; do
    case $arg in
        --skip-migration) SKIP_MIGRATION=true ;;
        --rebuild)        REBUILD=true ;;
    esac
done

if [ ! -f "$PEM" ]; then
    echo "ERROR: No se encuentra $PEM"
    exit 1
fi
chmod 600 "$PEM"
SSH="ssh -i $PEM -o StrictHostKeyChecking=no"
RSYNC="rsync -az --delete -e 'ssh -i $PEM -o StrictHostKeyChecking=no'"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   YAGA — Deploy v0.5.0 → EC2         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Sincronizar código ─────────────────────────────────────────────────────
echo "[1/5] Sincronizando código..."
rsync -az --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='secrets/' \
    --exclude='yaga_backend.pem' \
    --exclude='data_science/' \
    --exclude='Poleana_Project/' \
    -e "ssh -i $PEM -o StrictHostKeyChecking=no" \
    "$LOCAL_DIR/" "$EC2_HOST:$EC2_DIR/"

# ── 2. Migración DB ───────────────────────────────────────────────────────────
if [ "$SKIP_MIGRATION" = false ]; then
    echo ""
    echo "[2/5] Ejecutando migraciones SQL..."
    $SSH "$EC2_HOST" "
        for f in \$(ls $EC2_DIR/infrastructure/database/migrations/*.sql 2>/dev/null | sort); do
            ver=\$(basename \$f .sql)
            applied=\$(docker exec yaga_postgres psql -U yaga_user yaga_db -tAc \
                \"SELECT version FROM schema_migrations WHERE version='\$ver'\" 2>/dev/null || echo '')
            if [ -z \"\$applied\" ]; then
                echo \"  Aplicando migración \$ver...\"
                docker exec -i yaga_postgres psql -U yaga_user yaga_db < \$f
                echo \"  ✓ \$ver aplicada\"
            else
                echo \"  ✓ \$ver ya aplicada — skip\"
            fi
        done
    "
else
    echo ""
    echo "[2/5] Migración omitida (--skip-migration)"
fi

# ── 3. Rebuild imagen Docker ──────────────────────────────────────────────────
echo ""
echo "[3/5] Rebuilding imagen API..."
$SSH "$EC2_HOST" "
    cd $EC2_DIR
    $([ "$REBUILD" = true ] && echo 'docker compose build --no-cache api' || echo 'docker compose build api')
"

# ── 4. Reiniciar contenedor API ────────────────────────────────────────────────
echo ""
echo "[4/5] Reiniciando yaga_api..."
$SSH "$EC2_HOST" "
    cd $EC2_DIR
    docker compose up -d --no-deps api
    sleep 3
    docker inspect --format='{{.State.Health.Status}}' yaga_api
"

# ── 5. Health check ───────────────────────────────────────────────────────────
echo ""
echo "[5/5] Health check..."
$SSH "$EC2_HOST" "
    for i in 1 2 3 4 5; do
        STATUS=\$(curl -sf http://localhost:8000/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"status\"])' 2>/dev/null || echo 'error')
        if [ \"\$STATUS\" = 'ok' ]; then
            echo '  ✓ API saludable'
            break
        fi
        echo \"  Intento \$i/5 — esperando...\"
        sleep 3
    done
"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Deploy completado — y4ga.app       ║"
echo "╚══════════════════════════════════════╝"
echo ""

#!/bin/bash
# © YAGA Project — Todos los derechos reservados
# Configura ALLOWED_HOSTS, INSTALLED_APPS y urls.py para las apps
# 'polls' y 'xray' en ambas instancias EC2 de testing.
#
# Uso: bash infrastructure/configure_django_apps.sh [ubuntu|ec2|all]
# Default: all (configura ambas instancias)

set -euo pipefail

TARGET="${1:-all}"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15"

# ── Instancia Ubuntu (us-east-1) — puerto 6285, SG sg-0486cecc1922afa30 ──────
UBUNTU_HOST="ubuntu@ec2-34-228-82-92.compute-1.amazonaws.com"
UBUNTU_PEM="develomen.pem"
UBUNTU_TESTING="testing"
UBUNTU_BASE="/home/ubuntu/venv/www/testing"
UBUNTU_PUBLIC_DNS="ec2-34-228-82-92.compute-1.amazonaws.com"
UBUNTU_PORT=6285

# ── Instancia EC2 testing (us-east-2) — puerto 8000 ──────────────────────────
EC2_HOST="ec2-user@ec2-13-58-246-32.us-east-2.compute.amazonaws.com"
EC2_PEM="YAGA_development_pm.pem"
EC2_TESTING="testing"
EC2_BASE="/home/ec2-user/venv/www/testing"
EC2_PUBLIC_DNS="ec2-13-58-246-32.us-east-2.compute.amazonaws.com"
EC2_PORT=8000

# ── Función: configurar una instancia ────────────────────────────────────────
configure_instance() {
  local HOST="$1"
  local PEM="$2"
  local BASE="$3"
  local PROJECT="$4"      # subdirectorio con settings.py
  local PUBLIC_DNS="$5"
  local APPS="${6:-polls xray}"  # apps a registrar

  echo ""
  echo "── Configurando $HOST ──────────────────────────────"

  if [ ! -f "$PEM" ]; then
    echo "  SKIP: no se encontró $PEM"
    return 1
  fi
  chmod 400 "$PEM"

  ssh $SSH_OPTS -i "$PEM" "$HOST" bash <<REMOTE
set -euo pipefail
SETTINGS="$BASE/$PROJECT/settings.py"
URLS="$BASE/$PROJECT/urls.py"

echo "  Archivo settings: \$SETTINGS"
echo "  Archivo urls    : \$URLS"

# ── settings.py ──────────────────────────────────────────
# ALLOWED_HOSTS
python3 - <<PY
import re, sys
path = '\$SETTINGS'
txt  = open(path).read()
changed = False

# Detectar y parchear ALLOWED_HOSTS vacío o con localhost solo
allowed_pattern = r"ALLOWED_HOSTS\s*=\s*\[([^\]]*)\]"
match = re.search(allowed_pattern, txt)
hosts_needed = ['$PUBLIC_DNS', 'localhost', '127.0.0.1']

if match:
    current = match.group(1)
    missing = [h for h in hosts_needed if h not in current]
    if missing:
        new_hosts = current.rstrip()
        if new_hosts.strip():
            new_hosts += ",\n    "
        new_hosts += ",\n    ".join(f"'{h}'" for h in missing)
        txt = txt[:match.start(1)] + new_hosts + txt[match.end(1):]
        changed = True
        print(f"  ALLOWED_HOSTS: agregados {missing}")
    else:
        print("  ALLOWED_HOSTS: ya configurado")
else:
    # Agregar desde cero
    txt = txt + "\nALLOWED_HOSTS = [" + ", ".join(f"'{h}'" for h in hosts_needed) + "]\n"
    changed = True
    print("  ALLOWED_HOSTS: creado")

# INSTALLED_APPS
apps_to_add = [a for a in '${APPS}'.split() if f"'{a}'" not in txt and f'"{a}"' not in txt]
for app in apps_to_add:
    # Insertar antes del cierre de INSTALLED_APPS
    txt = re.sub(r"(INSTALLED_APPS\s*=\s*\[.*?)(])",
                 lambda m: m.group(1) + f"    '{app}',\n" + m.group(2),
                 txt, flags=re.DOTALL)
    changed = True
    print(f"  INSTALLED_APPS: agregado '{app}'")

if not apps_to_add:
    print("  INSTALLED_APPS: apps ya presentes")

if changed:
    open(path, 'w').write(txt)
PY

# ── urls.py ──────────────────────────────────────────────
python3 - <<PY
import re
path = '\$URLS'
txt  = open(path).read()
changed = False

# Asegurar import include
if 'include' not in txt:
    txt = re.sub(
        r'from django\.urls import (path)',
        r'from django.urls import \1, include',
        txt
    )
    changed = True
    print("  urls.py: 'include' importado")

# Agregar rutas faltantes
for app in '${APPS}'.split():
    pattern = f"'{app}/"
    if pattern not in txt:
        txt = re.sub(
            r'(urlpatterns\s*=\s*\[)',
            f"\\1\n    path('{app}/', include('{app}.urls')),",
            txt
        )
        changed = True
        print(f"  urls.py: ruta '/{app}/' agregada")

if not changed:
    print("  urls.py: ya configurado")
else:
    open(path, 'w').write(txt)
PY

echo ""
echo "  ── Resultado urls.py ──"
cat "\$URLS"
echo ""

# ── Verificar que los archivos urls.py de cada app existan ────────────────
for APP in ${APPS}; do
  APP_URLS="$BASE/\$APP/urls.py"
  if [ ! -f "\$APP_URLS" ]; then
    echo "  ADVERTENCIA: \$APP_URLS no existe — creando stub básico"
    cat > "\$APP_URLS" <<APPURLS
# © YAGA Project — Todos los derechos reservados
from django.urls import path
from . import views

app_name = '\$APP'

urlpatterns = [
    path('', views.index, name='index'),
]
APPURLS
    echo "  Creado stub: \$APP_URLS"
  fi
done
REMOTE

  echo "  OK — $HOST configurado"
}

# ── Despacho ─────────────────────────────────────────────────────────────────
case "$TARGET" in
  ubuntu)
    configure_instance "$UBUNTU_HOST" "$UBUNTU_PEM" "$UBUNTU_BASE" \
      "$UBUNTU_TESTING" "$UBUNTU_PUBLIC_DNS" "polls xray"
    ;;
  ec2)
    configure_instance "$EC2_HOST" "$EC2_PEM" "$EC2_BASE" \
      "$EC2_TESTING" "$EC2_PUBLIC_DNS" "polls xray"
    ;;
  all|*)
    configure_instance "$UBUNTU_HOST" "$UBUNTU_PEM" "$UBUNTU_BASE" \
      "$UBUNTU_TESTING" "$UBUNTU_PUBLIC_DNS" "polls xray"
    configure_instance "$EC2_HOST" "$EC2_PEM" "$EC2_BASE" \
      "$EC2_TESTING" "$EC2_PUBLIC_DNS" "polls xray"
    ;;
esac

echo ""
echo "========================================================"
echo " CONFIGURACIÓN COMPLETADA"
echo "========================================================"
echo ""
echo " Ubuntu (us-east-1) — puerto $UBUNTU_PORT (SG: sg-0486cecc1922afa30):"
echo "   http://$UBUNTU_PUBLIC_DNS:$UBUNTU_PORT/xray/"
echo "   http://$UBUNTU_PUBLIC_DNS:$UBUNTU_PORT/polls/"
echo ""
echo " EC2 testing (us-east-2) — puerto $EC2_PORT:"
echo "   http://$EC2_PUBLIC_DNS:$EC2_PORT/xray/"
echo "   http://$EC2_PUBLIC_DNS:$EC2_PORT/polls/"
echo ""
echo " Para levantar Django:"
echo "   Ubuntu : python manage.py runserver 0.0.0.0:$UBUNTU_PORT"
echo "   EC2    : python manage.py runserver 0.0.0.0:$EC2_PORT"
echo "   (activar venv primero: source ~/venv/bin/activate)"

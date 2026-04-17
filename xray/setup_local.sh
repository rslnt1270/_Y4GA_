#!/bin/bash
# © YAGA Project — Todos los derechos reservados
# Instala dependencias y prepara el entorno local para probar xray con Django.
# Uso: bash xray/setup_local.sh  (desde la raíz del proyecto Django)

set -euo pipefail

echo "=== Setup local: app xray (homicidios) ==="

# Instalar dependencias Python
pip install --quiet pandas requests geopy openpyxl

echo "  Dependencias instaladas: pandas, requests, geopy, openpyxl"

# Crear carpeta de datos dentro del app
mkdir -p xray/data
echo "  Carpeta xray/data/ lista para cache del CSV"

# Verificar settings.py
SETTINGS=$(find . -name "settings.py" -not -path "*/migrations/*" | head -1)
if [ -z "$SETTINGS" ]; then
  echo "  ADVERTENCIA: no se encontró settings.py — configura INSTALLED_APPS manualmente"
else
  echo "  settings.py encontrado: $SETTINGS"
  if ! grep -q "xray" "$SETTINGS"; then
    echo ""
    echo "  Agrega 'xray' a INSTALLED_APPS en $SETTINGS:"
    echo "      INSTALLED_APPS = ["
    echo "          ...,"
    echo "          'xray',"
    echo "      ]"
  else
    echo "  'xray' ya está en INSTALLED_APPS"
  fi
fi

# Verificar urls.py del proyecto
URLS=$(find . -name "urls.py" -not -path "*/xray/*" -not -path "*/migrations/*" | head -1)
if [ -n "$URLS" ]; then
  if ! grep -q "xray" "$URLS"; then
    echo ""
    echo "  Agrega la ruta en $URLS:"
    echo "      from django.urls import path, include"
    echo "      urlpatterns = ["
    echo "          ...,"
    echo "          path('xray/', include('xray.urls')),"
    echo "      ]"
  else
    echo "  Ruta 'xray/' ya registrada en $URLS"
  fi
fi

echo ""
echo "=== Para iniciar Django en local ==="
echo "  python manage.py migrate"
echo "  python manage.py runserver 0.0.0.0:8000"
echo ""
echo "  Abrir en navegador: http://localhost:8000/xray/"
echo ""
echo "  En EC2/Ubuntu (puerto 6285):"
echo "  python manage.py runserver 0.0.0.0:6285"
echo "  → http://ec2-34-228-82-92.compute-1.amazonaws.com:6285/xray/"

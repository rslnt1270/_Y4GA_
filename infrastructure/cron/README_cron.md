# Crontab — YAGA EC2

## Retención de datos (LFPDPPP)

Ejecuta el script de limpieza diariamente a las 3:00 AM UTC.
Solo elimina transacciones con más de 7 años de antigüedad
de usuarios que han ejercido su derecho de cancelación (soft delete).

### Configuración en EC2

```bash
# Conectarse al EC2
ssh -i ~/Documentos/Project_Y4GA_/yaga_backend.pem \
  ec2-user@ec2-3-19-35-76.us-east-2.compute.amazonaws.com

# Editar crontab del usuario ec2-user
crontab -e

# Agregar esta línea:
0 3 * * * docker exec yaga_api python /app/scripts/cleanup_old_transactions.py >> /home/ec2-user/logs/cleanup.log 2>&1
```

### Pre-requisitos

1. El script debe estar copiado dentro del container:
   ```bash
   docker cp cleanup_old_transactions.py yaga_api:/app/scripts/cleanup_old_transactions.py
   ```

2. Crear directorio de logs:
   ```bash
   mkdir -p /home/ec2-user/logs
   ```

3. Verificar que DATABASE_URL está configurada en el container:
   ```bash
   docker exec yaga_api printenv DATABASE_URL
   ```

### Verificación manual

```bash
# Ejecutar manualmente para probar
docker exec yaga_api python /app/scripts/cleanup_old_transactions.py

# Ver logs
tail -20 /home/ec2-user/logs/cleanup.log
```

### Notas

- Los archivos CSV de respaldo se generan en `/tmp/` dentro del container.
  Para preservarlos, montar un volumen o copiarlos periódicamente:
  ```bash
  docker cp yaga_api:/tmp/yaga_archive_*.csv /home/ec2-user/backups/
  ```
- El script NO toca `viajes_historicos` (datos de referencia sin PII directa).
- Requiere `asyncpg` (ya incluido en la imagen Docker de YAGA).

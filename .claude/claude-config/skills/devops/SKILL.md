---
name: devops
description: "Infraestructura Docker/EC2/EKS, CI/CD, monitoreo, y configuración de servicios para YAGA."
---

# DevOps YAGA — Referencia

## Infra actual
```
[Cloudflare WAF/CDN] → [EC2 t3.small Amazon Linux 2023]
                         ├── Nginx (reverse proxy :80/:443 → :8000)
                         ├── Docker Compose
                         │   ├── api (FastAPI :8000)
                         │   ├── postgres (16, :5432)
                         │   └── redis (7, :6379, maxmem 128MB)
                         └── deploy_yaga.sh (migration + health gate)

[Cloudflare Pages] → Poleana frontend (static)
[EC2 :8000/api/v1/poleana/*] → Poleana backend (WebSocket)
```

## docker-compose.yml (K8s-ready)
- Labels `app.kubernetes.io/*` para `kompose convert`
- Healthcheck en API container: `curl -f http://localhost:8000/health`
- Secrets montados `:ro`
- Redis maxmemory 128mb (match ElastiCache param group)
- Volume labels `backup:required` (hook Velero)

## Deploy script (deploy_yaga.sh)
```bash
# 1. Pull latest
git pull origin main --recurse-submodules
# 2. Build
docker compose build --no-cache api
# 3. Migrate (idempotente)
docker compose exec api python -m alembic upgrade head
# 4. Restart
docker compose up -d api
# 5. Health gate (retry 5x con backoff)
for i in {1..5}; do curl -sf http://localhost:8000/health && exit 0; sleep $((i*2)); done
echo "DEPLOY FAILED" && exit 1
```

## Ruta a EKS (3 pasos)
1. `kompose convert -f docker-compose.yml -o infrastructure/k8s/`
2. `eksctl create cluster --name yaga-prod --region us-east-2 --node-type t3.small --nodes 2`
3. RDS PostgreSQL multi-AZ + ElastiCache Redis + External Secrets Operator

## Monitoreo actual
- CloudWatch: CPU, memory, disk, API latency
- Nginx access.log: request rate, 4xx/5xx
- Roadmap: Prometheus + Grafana + Loki

## Nginx config
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 7200s;  # 2h para WebSocket Poleana
}
```

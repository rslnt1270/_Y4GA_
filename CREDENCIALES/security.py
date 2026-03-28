# ==============================================================================
# PROPIEDAD INTELECTUAL DE YAGA
# Licencia: Propietaria y Confidencial. 
# Queda estrictamente prohibida la copia, distribución o modificación no autorizada.
# Módulo: K8s Ingress Rate Limiting & Security Policies
# ==============================================================================

apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: yaga-core-ingress
  annotations:
    # Límite estricto: 5 peticiones por segundo por IP
    nginx.ingress.kubernetes.io/limit-rps: "5"
    # Margen de ráfaga antes de devolver HTTP 503 (Service Unavailable)
    nginx.ingress.kubernetes.io/limit-burst-multiplier: "2"
    # Enviar cabeceras de seguridad estrictas (HSTS, No-Sniff)
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains";
      more_set_headers "X-Frame-Options: DENY";
spec:
  tls:
  - hosts:
    - api.y4ga.app
    secretName: yaga-tls-secret
  rules:
  - host: api.y4ga.app
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: yaga-financial-service
            port:
              number: 443

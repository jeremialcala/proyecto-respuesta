# Fase 04 — Testing

Pirámide (unit → integration → contract → e2e → security), matriz OWASP Top 10, SAST/DAST/SCA/fuzzing/pentest.
Incluye red-teaming de los rieles del chatbot (ADR-0002) y pruebas de sesgo del matching.

**Gate 3 (cierre):** tests pasando + DAST limpio + performance dentro de SLOs.

## Estado

- ✅ **Nivel unit** cubierto en cada servicio de `apps/` (**99 tests en verde**): dominio puro
  (auditoría SHA-256, máquina de estados, drift/fusión, guardarraíles, escaneo CSAM, firma webhook,
  decisión de entrega) y casos de uso con fakes.
- 🚧 **Pendiente**: integración (con Postgres/SQS/SNS/S3 reales vía LocalStack/Testcontainers),
  contract tests de los eventos (ADR-0011), e2e del flujo central, y seguridad (SAST/DAST/SCA,
  red-teaming de rieles del chatbot — ADR-0002, pruebas de sesgo del matching — ADR-0004/0013).
- 🚧 **Calibración** de umbrales para ArcFace (`τ0`, `α/β/Δ_max`) con datos reales (ADR-0013).

# vault-worker

Tercer eslabón de la ingestión de Meta (ADR-0005): el **Worker de Control de Bóveda**. Consume
`inbound.media` (emitido por el [meta-handler](../meta-handler)), **descarga** el binario por
`media_id`, lo **escanea** (AV + CSAM), lo **cifra con sobre por usuario** (ADR-0008), lo **persiste**
cifrado en S3 y emite **`media.stored`** para el motor de matching.

## Invariantes de seguridad (cubiertos por tests)

- **CSAM** (child-safety): el binario **nunca** se persiste ni se publica; se registra un EventAction
  de alta severidad y se bloquea. CSAM tiene **precedencia** sobre el resultado del antivirus.
- **Malware**: cifrado → **cuarentena** (bucket separado); **no** llega al matching.
- **Limpio**: cifrado de sobre (DEK por **sujeto** = `contact_ref`, ADR-0008) → bóveda → `media.stored`
  (scan=clean) correlacionado por `event_id`.
- El **binario en claro nunca se persiste**: siempre se cifra antes de tocar el almacén.
- El binario **no viaja por eventos**: `media.stored` lleva solo el `media_ref`.

## Arquitectura (Clean Architecture / DDD)

```
src/vault_worker/
├── domain/        # puro: models, scan (veredicto CSAM>MALWARE>CLEAN + sha256)
├── application/   # ports (Downloader, Scanner, EnvelopeCipher, MediaStore, Publisher, EventLog) + vault_service + events
├── adapters/      # graph_downloader, scanner (placeholder), kms_envelope_cipher, s3_media_store, sns_publisher, sqs_consumer
└── config.py
```

## MVP / pendiente fase 03

- **Scanner** es un placeholder explícito (`PassthroughScanner`): integrar **ClamAV + lista de hashes
  CSAM** antes de producción (obligatorio por child-safety).
- **Cifrado**: KMS `GenerateDataKey` + AES-GCM con encryption context por sujeto; afinar **clave por
  usuario** con Vault Transit (ADR-0008).
- Cola de **incidentes CSAM** y traza Event/EventAction en Postgres (hoy no-op).

## Estado

- ✅ Dominio (scan) + `VaultService` con **8 tests en verde** (fakes; sin infra).
- 🚧 Adaptarores AWS/Graph con deps perezosas; escáner/cifrado reales en fase 03.

## Ejecutar

```bash
pip install -e ".[test]" && pytest
pip install -e . && python -m vault_worker
```

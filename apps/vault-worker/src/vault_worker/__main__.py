"""Arranque del Worker de Bóveda (wiring). inbound.media → bóveda cifrada → media.stored."""
from __future__ import annotations

import logging
import os

from .application.vault_service import VaultService
from .adapters.graph_downloader import GraphMediaDownloader
from .adapters.kms_envelope_cipher import KmsEnvelopeCipher
from .adapters.noop_event_log import NoopEventLog
from .adapters.passthrough_cipher import PassthroughCipher
from .adapters.s3_media_store import S3MediaStore
from .adapters.scanner import PassthroughScanner
from .adapters.sns_publisher import SnsEventPublisher
from .adapters.sqs_consumer import SqsConsumer
from .config import VaultConfig


def build_consumer(cfg: VaultConfig) -> SqsConsumer:
    # Cifrado: KMS envelope en prod (ADR-0008); passthrough (JPEG plano) en dev para que el matcher,
    # que aún no descifra, lea la imagen desde S3 persistente (MinIO).
    cipher = PassthroughCipher() if cfg.cipher_mode == "passthrough" else \
        KmsEnvelopeCipher(cfg.kms_key_id, cfg.aws_region)
    service = VaultService(
        cfg,
        downloader=GraphMediaDownloader(cfg.graph_api_base),
        scanner=PassthroughScanner(),          # TODO fase-03: ClamAV + hashing CSAM
        cipher=cipher,
        store=S3MediaStore(cfg.media_bucket, cfg.quarantine_bucket, cfg.aws_region, sse=cfg.s3_sse),
        publisher=SnsEventPublisher(cfg.stored_queue_url, cfg.aws_region),
        event_log=NoopEventLog(),
    )
    return SqsConsumer(cfg.input_queue_url, cfg.aws_region, service,
                       cfg.max_messages, cfg.wait_time_seconds)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    build_consumer(VaultConfig.from_env()).start()


if __name__ == "__main__":
    main()

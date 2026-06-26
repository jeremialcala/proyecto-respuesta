"""Config del motor tras ADR-0013 (ArcFace 512-d) y ADR-0012 (SQS/SNS)."""
from matching_worker.config import EMBEDDING_DIM, ArcFaceParams, WorkerConfig


def test_embedding_dim_is_512_for_arcface():
    assert EMBEDDING_DIM == 512
    assert ArcFaceParams().embedding_dim == 512
    assert ArcFaceParams().backbone == "iresnet100"


def test_worker_config_reads_env(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "sa-east-1")
    monkeypatch.setenv("SQS_INPUT_QUEUE_URL", "https://sqs/x")
    monkeypatch.setenv("SNS_OUTPUT_TOPIC_ARN", "arn:aws:sns:sa-east-1:1:cand")
    monkeypatch.setenv("PGVECTOR_DSN", "postgresql://localhost/respuesta")
    cfg = WorkerConfig.from_env()
    assert cfg.aws_region == "sa-east-1"
    assert cfg.input_queue_url.endswith("/x")
    assert cfg.output_topic_arn.startswith("arn:aws:sns")
    assert "respuesta" in cfg.pgvector_dsn

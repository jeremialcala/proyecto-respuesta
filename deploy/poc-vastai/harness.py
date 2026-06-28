#!/usr/bin/env python3
"""Harness de carga/medición del plano de inferencia (PoC ADR-0019).

Actúa como el worker in-region: publica `face.extract.requested` (imagen base64) al topic de extracción
y drena la cola de respuesta `face.embedded`, casando por `job_id`. Mide lo que el ADR-0019 deja como
decisiones abiertas: **cold-start, throughput, latencia p50/p95/p99, tasa de detección, timeouts/errores
y egress** (bytes enviados). Funciona contra LocalStack (dry-run) o AWS real (mismo código, cambia el
endpoint). NO envía datos reales: úsalo con `gen_synthetic_faces.py` o datos consentidos (ADR-0019 §6).

Ejemplos:
    # Dry-run local (docker compose --profile poc up -d inference-worker):
    python harness.py --endpoint http://localhost:4566 --region sa-east-1 \
        --extract-topic-arn arn:aws:sns:sa-east-1:000000000000:face-extract-requested \
        --reply-queue-url http://localhost:4566/000000000000/face-embedded-reply \
        --images ./synthetic --count 200 --concurrency 8 --timeout 120 --out results.json

    # vast.ai Secure Cloud / AWS real: omite --endpoint y usa los ARNs/URLs reales (creds por el chain).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import threading
import time
import uuid
from datetime import datetime, timezone


def _envelope(payload: dict, producer: str = "poc-harness") -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "face.extract.requested",
        "producer": producer,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": "1.0.0",
        "payload": payload,
    }


def _clients(endpoint: str | None, region: str):
    import boto3
    kw = {"region_name": region}
    if endpoint:
        kw["endpoint_url"] = endpoint
        # LocalStack ignora el valor pero boto3 exige credenciales presentes.
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    return boto3.client("sns", **kw), boto3.client("sqs", **kw)


def _load_images(path: str) -> list[bytes]:
    if os.path.isfile(path):
        return [open(path, "rb").read()]
    out = []
    for name in sorted(os.listdir(path)):
        if name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            out.append(open(os.path.join(path, name), "rb").read())
    if not out:
        raise SystemExit(f"sin imágenes en {path} (genera con gen_synthetic_faces.py)")
    return out


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class Harness:
    def __init__(self, sns, sqs, topic_arn: str, reply_queue: str, timeout: float):
        self._sns = sns
        self._sqs = sqs
        self._topic = topic_arn
        self._reply = reply_queue
        self._timeout = timeout
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}     # job_id -> {send, recv, faces, status, bytes, _freed}
        self._done = threading.Event()
        self._sem: threading.BoundedSemaphore | None = None

    def _free(self, job: dict) -> None:
        """Libera el permiso de concurrencia de un trabajo, una sola vez (bajo self._lock)."""
        if not job.get("_freed"):
            job["_freed"] = True
            if self._sem is not None:
                try:
                    self._sem.release()
                except ValueError:
                    pass

    def _drain_reply_queue(self) -> int:
        n = 0
        while True:
            r = self._sqs.receive_message(QueueUrl=self._reply, MaxNumberOfMessages=10, WaitTimeSeconds=0)
            msgs = r.get("Messages", [])
            if not msgs:
                return n
            for m in msgs:
                self._sqs.delete_message(QueueUrl=self._reply, ReceiptHandle=m["ReceiptHandle"])
                n += 1

    def _collector(self) -> None:
        while not self._done.is_set():
            r = self._sqs.receive_message(QueueUrl=self._reply, MaxNumberOfMessages=10,
                                          WaitTimeSeconds=2)
            for m in r.get("Messages", []):
                try:
                    body = json.loads(m["Body"])
                    inner = json.loads(body["Message"]) if "Message" in body else body
                    p = inner.get("payload", {}) or {}
                except Exception:
                    self._sqs.delete_message(QueueUrl=self._reply, ReceiptHandle=m["ReceiptHandle"])
                    continue
                jid = p.get("job_id")
                now = time.monotonic()
                with self._lock:
                    job = self._jobs.get(jid)
                    if job and job["recv"] is None:
                        job["recv"] = now
                        job["faces"] = len(p.get("faces", []))
                        job["status"] = "ok"
                        self._free(job)        # libera el permiso desde el colector (evita deadlock)
                self._sqs.delete_message(QueueUrl=self._reply, ReceiptHandle=m["ReceiptHandle"])

    def _watchdog(self) -> None:
        """Marca timeout y libera los trabajos que exceden self._timeout desde su envío."""
        while not self._done.is_set():
            now = time.monotonic()
            with self._lock:
                for j in self._jobs.values():
                    if j["recv"] is None and j["status"] != "timeout" and now - j["send"] > self._timeout:
                        j["status"] = "timeout"
                        self._free(j)
            time.sleep(0.25)

    def run(self, images: list[bytes], count: int, concurrency: int) -> dict:
        self._sem = threading.BoundedSemaphore(concurrency)
        encoded = [base64.b64encode(images[i % len(images)]).decode("ascii") for i in range(count)]
        sizes = [len(images[i % len(images)]) for i in range(count)]

        print(f"drenando cola de respuesta… ({self._drain_reply_queue()} mensajes viejos)")
        collector = threading.Thread(target=self._collector, daemon=True)
        watchdog = threading.Thread(target=self._watchdog, daemon=True)
        collector.start()
        watchdog.start()

        t0 = time.monotonic()
        for i in range(count):
            self._sem.acquire()    # liberado por el colector (ok) o el watchdog (timeout)
            job_id = uuid.uuid4().hex
            with self._lock:
                self._jobs[job_id] = {"send": time.monotonic(), "recv": None, "faces": 0,
                                      "status": "pending", "bytes": sizes[i]}
            self._sns.publish(
                TopicArn=self._topic,
                Message=json.dumps(_envelope({"job_id": job_id, "image_b64": encoded[i]})),
                MessageAttributes={"event_type": {"DataType": "String",
                                                  "StringValue": "face.extract.requested"}},
            )

        # Espera a que TODO trabajo termine (recv) o expire (timeout), con un tope global de cortesía.
        hard_stop = time.monotonic() + self._timeout + 10
        while time.monotonic() < hard_stop:
            with self._lock:
                pending = [j for j in self._jobs.values() if j["recv"] is None and j["status"] != "timeout"]
            if not pending:
                break
            time.sleep(0.25)
        with self._lock:                       # cualquier rezagado → timeout
            for j in self._jobs.values():
                if j["recv"] is None:
                    j["status"] = "timeout"
        self._done.set()
        collector.join(timeout=3)
        watchdog.join(timeout=1)
        return self._metrics(t0)

    def _metrics(self, t0: float) -> dict:
        with self._lock:
            jobs = list(self._jobs.values())
        ok = [j for j in jobs if j["status"] == "ok"]
        lat = sorted((j["recv"] - j["send"]) for j in ok)
        recvs = [j["recv"] for j in ok]
        total_bytes = sum(j["bytes"] for j in jobs)
        wall = (max(recvs) - t0) if recvs else 0.0
        return {
            "count": len(jobs),
            "ok": len(ok),
            "timeouts": sum(1 for j in jobs if j["status"] == "timeout"),
            "cold_start_s": round(min(lat), 3) if lat else None,   # 1ª respuesta ≈ carga de modelo
            "throughput_jobs_s": round(len(ok) / wall, 2) if wall > 0 else None,
            "latency_p50_s": round(_percentile(lat, 0.50), 3) if lat else None,
            "latency_p95_s": round(_percentile(lat, 0.95), 3) if lat else None,
            "latency_p99_s": round(_percentile(lat, 0.99), 3) if lat else None,
            "latency_max_s": round(max(lat), 3) if lat else None,
            "detection_rate": round(sum(1 for j in ok if j["faces"] > 0) / len(ok), 3) if ok else None,
            "avg_faces": round(statistics.mean(j["faces"] for j in ok), 2) if ok else None,
            "egress_bytes_sent": total_bytes,
            "egress_mb_sent": round(total_bytes / 1e6, 2),
            "wall_s": round(wall, 2),
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="Harness PoC del plano de inferencia (ADR-0019).")
    ap.add_argument("--endpoint", default=None, help="endpoint boto3 (LocalStack). Omitir para AWS real.")
    ap.add_argument("--region", default="sa-east-1")
    ap.add_argument("--extract-topic-arn", required=True)
    ap.add_argument("--reply-queue-url", required=True)
    ap.add_argument("--images", required=True, help="dir (o archivo) de imágenes sintéticas/consentidas")
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=120.0, help="espera global tras el último envío")
    ap.add_argument("--out", default="results.json")
    args = ap.parse_args()

    images = _load_images(args.images)
    sns, sqs = _clients(args.endpoint, args.region)
    print(f"imágenes={len(images)} count={args.count} concurrency={args.concurrency} "
          f"destino={'LocalStack' if args.endpoint else 'AWS'} ({args.region})")

    h = Harness(sns, sqs, args.extract_topic_arn, args.reply_queue_url, args.timeout)
    metrics = h.run(images, args.count, args.concurrency)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print("\n=== Resultados PoC (ADR-0019) ===")
    for k, v in metrics.items():
        print(f"  {k:22s} {v}")
    print(f"\nguardado en {args.out}")


if __name__ == "__main__":
    main()

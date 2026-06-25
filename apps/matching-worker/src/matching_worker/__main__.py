"""Punto de entrada del worker (wiring). Esqueleto — la composición real va en fase 03."""
from __future__ import annotations


def main() -> None:
    # TODO(fase-03): leer config, construir adaptadores (pgvector, FAISS, OpenCV, AMQP),
    # inyectarlos en MatchingService y arrancar el consumer.
    raise NotImplementedError("Wiring del worker pendiente (fase 03-implementation)")


if __name__ == "__main__":
    main()

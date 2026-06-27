"""Embedder on-premises vía Ollama (`/api/embeddings`). `urllib` (stdlib), mismo host que el LLM.

Modelo por defecto: `nomic-embed-text` (768 dims). Sirve para recuperar solo los turnos relevantes
de la conversación y así economizar tokens del LLM (ADR-0015).

`NullEmbedder` desactiva los embeddings (la memoria opera solo con la ventana reciente).
"""
from __future__ import annotations

import json
import urllib.request
from typing import Sequence


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str = "nomic-embed-text") -> None:
        self._url = base_url.rstrip("/") + "/api/embeddings"
        self._model = model

    def embed(self, text: str) -> Sequence[float]:
        if not text:
            return []
        body = json.dumps({"model": self._model, "prompt": text}).encode()
        req = urllib.request.Request(self._url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (host on-prem propio)
                data = json.loads(resp.read())
        except Exception:   # degradación elegante: sin embeddings, memoria solo con ventana reciente
            return []
        return data.get("embedding", []) or []


class NullEmbedder:
    """Embeddings deshabilitados: devuelve vacío siempre."""

    def embed(self, text: str) -> Sequence[float]:
        return []

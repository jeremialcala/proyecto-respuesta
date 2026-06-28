"""FetcherAllowlist estática (tests/dev). El real es `meta_fetcher_allowlist` (rangos IP/UA de Meta).

`allow_all=True` (por defecto) permite cualquier descarga — útil en dev/tests. Para `open_token`
siempre permite (solo el token opaco protege). Para audiencias restringidas, respeta `allow_all`.
"""
from __future__ import annotations


class StaticAllowlist:
    def __init__(self, allow_all: bool = True) -> None:
        self._allow_all = allow_all

    def is_allowed(self, audience: str, src_ip: str, user_agent: str) -> bool:
        if audience == "open_token":
            return True
        return self._allow_all

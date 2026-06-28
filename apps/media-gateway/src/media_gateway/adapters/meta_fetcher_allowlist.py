"""Allowlist de fetchers para `audience=meta_fetchers` (rangos IP + User-Agent de Meta). ADR-0017 §6.

Para `meta_fetchers` exige que `src_ip` caiga en algún CIDR permitido **y** que el `user_agent`
contenga alguno de los tokens esperados (`facebookexternalhit`, fetcher de WhatsApp). Para
`authenticated_session` la sesión la valida la capa de API (Auth0, ADR-0009), no este allowlist →
delega permitiendo (placeholder; se endurece en fase 03). Para `open_token` solo protege el token.

Los rangos/UA de Meta cambian; se mantienen por config (ADR-0017 §Pendiente). Esqueleto fase 03.
"""
from __future__ import annotations

import ipaddress


class MetaFetcherAllowlist:
    def __init__(self, cidrs: tuple[str, ...], user_agents: tuple[str, ...]) -> None:
        self._nets = [ipaddress.ip_network(c) for c in cidrs]
        self._uas = tuple(ua.lower() for ua in user_agents)

    def is_allowed(self, audience: str, src_ip: str, user_agent: str) -> bool:
        if audience == "open_token":
            return True
        if audience == "authenticated_session":
            return True  # la sesión Auth0 la valida la API; placeholder fase 03
        # audience == meta_fetchers
        if not self._ua_ok(user_agent):
            return False
        return self._ip_ok(src_ip)

    def _ua_ok(self, user_agent: str) -> bool:
        ua = (user_agent or "").lower()
        return any(token in ua for token in self._uas)

    def _ip_ok(self, src_ip: str) -> bool:
        try:
            ip = ipaddress.ip_address(src_ip)
        except ValueError:
            return False
        return any(ip in net for net in self._nets)

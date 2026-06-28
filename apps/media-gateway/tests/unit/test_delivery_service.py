"""Flujo del plano público con fakes en memoria (desambiguación end-to-end). ADR-0017 §3/§5.

Cubre: descifrado OK, HMAC inválido (404), expiración (410), agotamiento de usos (410), revocación
(403), solo `scan=clean` (403), allowlist (403) y rate-limit (429). Orquestación fail-closed.
"""
import time

from media_gateway.adapters.hmac_token_signer import HmacTokenSigner
from media_gateway.adapters.memory_grant_store import MemoryGrantStore
from media_gateway.adapters.memory_media_store import MemoryMediaStore
from media_gateway.adapters.memory_rate_limiter import MemoryRateLimiter
from media_gateway.adapters.noop_event_log import NoopAuditLog
from media_gateway.adapters.passthrough_cipher import PassthroughCipher
from media_gateway.adapters.static_allowlist import StaticAllowlist
from media_gateway.application import events
from media_gateway.application.delivery_service import DeliveryService
from media_gateway.application.grant_service import GrantService
from media_gateway.domain.models import Purpose, ServeResult

MEDIA_REF = "s3://vault/media/subject-1/crop-2"
PLAINTEXT = b"\xff\xd8\xff JPEG-rostro-2"


def _harness(*, allow_all=True, rate_max=100):
    store = MemoryGrantStore()
    signer = HmacTokenSigner(b"shared-key")
    media = MemoryMediaStore()
    media.put(MEDIA_REF, PLAINTEXT, {"scan": "clean", "subject": "subject-1",
                                     "content_type": "image/jpeg"})
    audit = NoopAuditLog()
    grants = GrantService(store, signer, audit, public_base_url="https://media.example")
    delivery = DeliveryService(store, signer, StaticAllowlist(allow_all),
                               MemoryRateLimiter(rate_max), media, PassthroughCipher(), audit)
    return grants, delivery, store, media, audit


def _token_of(url: str) -> str:
    return url.rsplit("/m/", 1)[1]


def _issue(grants, **kw):
    defaults = dict(media_ref=MEDIA_REF, content_type="image/jpeg",
                    purpose=Purpose.DISAMBIGUATION_CROP, created_by="output-service")
    defaults.update(kw)
    return grants.issue(**defaults)


def test_happy_path_serves_decrypted_bytes():
    grants, delivery, _, _, audit = _harness()
    token = _token_of(_issue(grants).url)
    out = delivery.serve(token, src_ip="1.2.3.4", user_agent="facebookexternalhit/1.1")
    assert out.result is ServeResult.OK
    assert out.body == PLAINTEXT
    assert out.content_type == "image/jpeg"
    assert events.MEDIA_SERVED in [e for e, _ in audit.records]


def test_invalid_hmac_is_not_found():
    grants, delivery, _, _, _ = _harness()
    token = _token_of(_issue(grants).url)
    token_id, exp, _sig = token.split(".")
    tampered = f"{token_id}.{exp}.AAAAtampered"
    assert delivery.serve(tampered, src_ip="1.2.3.4", user_agent="x").result is ServeResult.NOT_FOUND


def test_malformed_token_is_not_found():
    _, delivery, _, _, _ = _harness()
    assert delivery.serve("garbage", src_ip="1.2.3.4", user_agent="x").result is ServeResult.NOT_FOUND


def test_unknown_token_is_not_found():
    grants, delivery, _, _, _ = _harness()
    # token bien firmado pero nunca creado en el ledger
    exp = int(time.time()) + 600
    sig = HmacTokenSigner(b"shared-key").sign("ghost", exp)
    assert delivery.serve(f"ghost.{exp}.{sig}", src_ip="1.2.3.4",
                          user_agent="x").result is ServeResult.NOT_FOUND


def test_expired_grant_is_gone():
    grants, delivery, _, _, _ = _harness()
    token = _token_of(_issue(grants, ttl_s=1, now=int(time.time()) - 10).url)
    assert delivery.serve(token, src_ip="1.2.3.4", user_agent="x").result is ServeResult.GONE


def test_exhausted_uses_is_gone():
    grants, delivery, _, _, _ = _harness()
    token = _token_of(_issue(grants, max_uses=2).url)
    assert delivery.serve(token, src_ip="1.2.3.4", user_agent="x").result is ServeResult.OK
    assert delivery.serve(token, src_ip="1.2.3.4", user_agent="x").result is ServeResult.OK
    assert delivery.serve(token, src_ip="1.2.3.4", user_agent="x").result is ServeResult.GONE


def test_revoked_grant_is_forbidden():
    grants, delivery, _, _, _ = _harness()
    issued = _issue(grants)
    grants.revoke(issued.token_id)
    assert delivery.serve(_token_of(issued.url), src_ip="1.2.3.4",
                          user_agent="x").result is ServeResult.FORBIDDEN


def test_non_clean_media_is_forbidden():
    grants, delivery, _, media, _ = _harness()
    media.put(MEDIA_REF, PLAINTEXT, {"scan": "pending", "subject": "subject-1"})
    token = _token_of(_issue(grants).url)
    assert delivery.serve(token, src_ip="1.2.3.4", user_agent="x").result is ServeResult.FORBIDDEN


def test_allowlist_block_is_forbidden():
    grants, delivery, _, _, _ = _harness(allow_all=False)
    token = _token_of(_issue(grants).url)  # audience=meta_fetchers
    assert delivery.serve(token, src_ip="9.9.9.9", user_agent="curl").result is ServeResult.FORBIDDEN


def test_rate_limit_returns_429():
    grants, delivery, _, _, _ = _harness(rate_max=1)
    token = _token_of(_issue(grants, max_uses=5).url)
    assert delivery.serve(token, src_ip="1.2.3.4", user_agent="x").result is ServeResult.OK
    assert delivery.serve(token, src_ip="1.2.3.4", user_agent="x").result is ServeResult.RATE_LIMITED

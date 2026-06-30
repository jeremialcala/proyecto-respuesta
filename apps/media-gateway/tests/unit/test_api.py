"""Apps FastAPI de ambos planos (TestClient) con fakes. Mapeo a HTTP y boot. ADR-0017 §3."""
from fastapi.testclient import TestClient

from media_gateway.adapters.hmac_token_signer import HmacTokenSigner
from media_gateway.adapters.memory_grant_store import MemoryGrantStore
from media_gateway.adapters.memory_media_store import MemoryMediaStore
from media_gateway.adapters.memory_rate_limiter import MemoryRateLimiter
from media_gateway.adapters.noop_event_log import NoopAuditLog
from media_gateway.adapters.passthrough_cipher import PassthroughCipher
from media_gateway.adapters.static_allowlist import StaticAllowlist
from media_gateway.api.internal_app import create_internal_app
from media_gateway.api.public_app import create_public_app
from media_gateway.application.delivery_service import DeliveryService
from media_gateway.application.grant_service import GrantService

MEDIA_REF = "s3://vault/media/subject-1/crop-2"
PLAINTEXT = b"JPEG-bytes"


def _apps():
    store = MemoryGrantStore()
    signer = HmacTokenSigner(b"shared")
    audit = NoopAuditLog()
    media = MemoryMediaStore()
    media.put(MEDIA_REF, PLAINTEXT, {"scan": "clean", "subject": "subject-1",
                                     "content_type": "image/jpeg"})
    grants = GrantService(store, signer, audit, public_base_url="https://media.example")
    delivery = DeliveryService(store, signer, StaticAllowlist(True),
                               MemoryRateLimiter(100), media, PassthroughCipher(), audit)
    return TestClient(create_internal_app(grants)), TestClient(create_public_app(delivery))


def test_healthz_both_planes():
    internal, public = _apps()
    assert internal.get("/healthz").json() == {"status": "ok"}
    assert public.get("/healthz").json() == {"status": "ok"}


def test_issue_then_serve_end_to_end():
    internal, public = _apps()
    resp = internal.post("/grants", json={"media_ref": MEDIA_REF, "content_type": "image/jpeg",
                                          "purpose": "disambiguation_crop"})
    assert resp.status_code == 201
    body = resp.json()
    assert "token_id" in body and "expires_at" in body
    token = body["url"].rsplit("/m/", 1)[1]

    got = public.get(f"/m/{token}", headers={"user-agent": "facebookexternalhit/1.1"})
    assert got.status_code == 200
    assert got.content == PLAINTEXT
    assert got.headers["content-type"].startswith("image/jpeg")
    assert got.headers["cache-control"] == "private, no-store"


def test_issue_enrollment_closing_then_serve_end_to_end():
    # ADR-0020: el cierre tipo imagen emite concesión purpose=enrollment_closing y la sirve a Meta.
    internal, public = _apps()
    resp = internal.post("/grants", json={"media_ref": MEDIA_REF, "content_type": "image/jpeg",
                                          "purpose": "enrollment_closing"})
    assert resp.status_code == 201
    token = resp.json()["url"].rsplit("/m/", 1)[1]

    got = public.get(f"/m/{token}", headers={"user-agent": "facebookexternalhit/1.1"})
    assert got.status_code == 200
    assert got.content == PLAINTEXT


def test_serve_unknown_token_is_404():
    _internal, public = _apps()
    assert public.get("/m/does.123.notreal").status_code == 404


def test_revoke_then_serve_is_403():
    internal, public = _apps()
    body = internal.post("/grants", json={"media_ref": MEDIA_REF, "content_type": "image/jpeg",
                                          "purpose": "disambiguation_crop"}).json()
    assert internal.delete(f"/grants/{body['token_id']}").status_code == 204
    token = body["url"].rsplit("/m/", 1)[1]
    assert public.get(f"/m/{token}").status_code == 403


def test_revoke_by_ref_requires_a_key():
    internal, _public = _apps()
    assert internal.post("/grants:revoke-by-ref", json={}).status_code == 422

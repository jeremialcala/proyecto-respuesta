"""Emisión y revocación de concesiones (plano interno) con fakes en memoria. ADR-0017 §3."""
from media_gateway.adapters.hmac_token_signer import HmacTokenSigner
from media_gateway.adapters.memory_grant_store import MemoryGrantStore
from media_gateway.adapters.noop_event_log import NoopAuditLog
from media_gateway.application import events
from media_gateway.application.grant_service import GrantService
from media_gateway.domain.models import Audience, Purpose


def _service():
    store = MemoryGrantStore()
    audit = NoopAuditLog()
    svc = GrantService(store, HmacTokenSigner(b"k"), audit,
                       public_base_url="https://media.example/")
    return svc, store, audit


def test_issue_persists_grant_and_returns_signed_url():
    svc, store, audit = _service()
    issued = svc.issue(media_ref="s3://b/m/s/1", content_type="image/jpeg",
                       purpose=Purpose.DISAMBIGUATION_CROP, created_by="output-service", now=1000)
    grant = store.get(issued.token_id)
    assert grant is not None
    assert grant.media_ref == "s3://b/m/s/1"
    assert grant.audience is Audience.META_FETCHERS       # default del propósito
    assert grant.expires_at == 1000 + 600                 # TTL del propósito
    assert issued.token_id in issued.url
    assert issued.url.startswith("https://media.example/m/")
    assert events.GRANT_ISSUED in [e for e, _ in audit.records]


def test_issue_tags_grant_with_report_id():
    svc, store, _ = _service()
    issued = svc.issue(media_ref="s3://b/m/s/1", content_type="image/jpeg",
                       purpose=Purpose.DISAMBIGUATION_CROP, created_by="output-service",
                       report_id="rep-1", entity_id="ent-1")
    grant = store.get(issued.token_id)
    assert grant.report_id == "rep-1" and grant.entity_id == "ent-1"


def test_issue_overrides_ttl_and_max_uses():
    svc, store, _ = _service()
    issued = svc.issue(media_ref="s3://b/m/s/1", content_type="image/jpeg",
                       purpose=Purpose.DISAMBIGUATION_CROP, created_by="x",
                       ttl_s=30, max_uses=1, now=1000)
    grant = store.get(issued.token_id)
    assert grant.max_uses == 1
    assert grant.expires_at == 1030


def test_revoke_marks_grant_and_audits():
    svc, store, audit = _service()
    issued = svc.issue(media_ref="s3://b/m/s/1", content_type="image/jpeg",
                       purpose=Purpose.ATTACHMENT, created_by="x")
    svc.revoke(issued.token_id)
    assert store.get(issued.token_id).is_revoked()
    assert events.GRANT_REVOKED in [e for e, _ in audit.records]


def test_revoke_by_ref_revokes_all_matching():
    svc, store, _ = _service()
    a = svc.issue(media_ref="s3://b/m/s/1", content_type="image/jpeg",
                  purpose=Purpose.ATTACHMENT, created_by="x")
    b = svc.issue(media_ref="s3://b/m/s/1", content_type="image/jpeg",
                  purpose=Purpose.ATTACHMENT, created_by="x")
    c = svc.issue(media_ref="s3://b/m/s/2", content_type="image/jpeg",
                  purpose=Purpose.ATTACHMENT, created_by="x")
    count = svc.revoke_by_ref(media_ref="s3://b/m/s/1")
    assert count == 2
    assert store.get(a.token_id).is_revoked()
    assert store.get(b.token_id).is_revoked()
    assert not store.get(c.token_id).is_revoked()

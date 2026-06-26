"""Orquestación del Worker de Bóveda (ADR-0005/0008): download→scan→cifra→store→media.stored."""
from vault_worker.config import VaultConfig
from vault_worker.domain.models import EncryptedObject, ScanVerdict
from vault_worker.application.vault_service import VaultService


class FakeDownloader:
    def __init__(self, data=b"JPEGDATA"):
        self.data = data
        self.calls = []

    def download(self, media_id, bot_id):
        self.calls.append((media_id, bot_id))
        return self.data


class FakeScanner:
    def __init__(self, av_clean=True, csam_hit=False):
        self._r = (av_clean, csam_hit)

    def scan(self, data):
        return self._r


class SpyCipher:
    def __init__(self):
        self.calls = []

    def encrypt(self, data, subject):
        self.calls.append((data, subject))
        return EncryptedObject(ciphertext=b"ENC"+data, wrapped_dek=b"wdek", key_id="k1", subject=subject)


class SpyStore:
    def __init__(self):
        self.puts = []

    def put(self, obj, *, key, metadata, quarantine=False):
        self.puts.append({"obj": obj, "key": key, "metadata": metadata, "quarantine": quarantine})
        return ("s3://quar/" if quarantine else "s3://vault/") + key


class SpyPub:
    def __init__(self):
        self.events = []

    def publish(self, env):
        self.events.append(env)


class SpyLog:
    def __init__(self):
        self.actions = []

    def record_action(self, event_id, action, status, detail=""):
        self.actions.append((action, status, detail))


def _env(contact="584120000000", media_id="media-1", event_id="evt-1"):
    return {"event_id": event_id, "event_type": "inbound.media",
            "payload": {"bot_id": "bot-1", "contact_ref": contact, "message_id": "wamid.1",
                        "media_id": media_id, "media_type": "image", "mime_type": "image/jpeg"}}


def _svc(scanner):
    dl, cipher, store, pub, log = FakeDownloader(), SpyCipher(), SpyStore(), SpyPub(), SpyLog()
    svc = VaultService(VaultConfig(producer="vault-worker"), dl, scanner, cipher, store, pub, log)
    return svc, dl, cipher, store, pub, log


def test_clean_encrypts_stores_and_publishes():
    svc, dl, cipher, store, pub, log = _svc(FakeScanner(av_clean=True))
    out = svc.handle(_env())
    assert out.verdict is ScanVerdict.CLEAN and out.media_ref.startswith("s3://vault/media/")
    # cifrado por sujeto (clave por usuario, ADR-0008)
    assert cipher.calls[0][1] == "584120000000"
    # se persiste el CIFRADO, no el plano
    assert store.puts[0]["obj"].ciphertext == b"ENCJPEGDATA"
    assert store.puts[0]["quarantine"] is False
    # media.stored correlacionado y scan=clean
    assert len(pub.events) == 1
    ev = pub.events[0]
    assert ev["event_type"] == "media.stored" and ev["event_id"] == "evt-1"
    assert ev["payload"]["scan"] == "clean" and ev["payload"]["media_ref"].startswith("s3://vault/")


def test_malware_quarantined_not_published():
    svc, dl, cipher, store, pub, log = _svc(FakeScanner(av_clean=False))
    out = svc.handle(_env())
    assert out.verdict is ScanVerdict.MALWARE and out.media_ref is None
    assert store.puts[0]["quarantine"] is True   # cifrado y en cuarentena
    assert pub.events == []                        # NO va a matching
    assert any(s == "MALWARE_QUARANTINED" for _, s, _ in log.actions)


def test_csam_blocked_never_stored_or_published():
    svc, dl, cipher, store, pub, log = _svc(FakeScanner(av_clean=True, csam_hit=True))
    out = svc.handle(_env())
    assert out.verdict is ScanVerdict.CSAM and out.media_ref is None
    assert store.puts == []        # child-safety: NO se persiste
    assert cipher.calls == []      # ni siquiera se cifra/guarda
    assert pub.events == []
    assert any(s == "CSAM_BLOCKED" for _, s, _ in log.actions)


def test_downloads_by_media_id():
    svc, dl, *_ = _svc(FakeScanner())
    svc.handle(_env(media_id="media-xyz"))
    assert dl.calls == [("media-xyz", "bot-1")]

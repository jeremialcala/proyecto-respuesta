"""Desambiguación multi-rostro: imágenes por URL firmada + botón de opciones (ADR-0016/0017)."""
from output_service.application.output_service import OutputService
from output_service.config import OutputConfig
from output_service.domain.face_options import build_face_options, use_buttons
from output_service.domain.models import DeliveryMode


class FakeCipher:
    def decrypt(self, jwe_body):
        return jwe_body


class FakeWindow:
    def __init__(self, open_):
        self._open = open_

    def is_open(self, contact_ref):
        return self._open


class SpySender:
    def __init__(self):
        self.texts, self.templates, self.images = [], [], []
        self.buttons, self.lists = [], []

    def send_text(self, bot_id, channel, contact_ref, text):
        self.texts.append((contact_ref, text))

    def send_template(self, bot_id, channel, contact_ref, template, lang):
        self.templates.append((contact_ref, template, lang))

    def send_image(self, bot_id, channel, contact_ref, link, caption):
        self.images.append((contact_ref, link, caption))

    def send_buttons(self, bot_id, channel, contact_ref, body, buttons):
        self.buttons.append((contact_ref, body, buttons))

    def send_list(self, bot_id, channel, contact_ref, body, button_label, rows):
        self.lists.append((contact_ref, body, button_label, rows))


class FakeGrants:
    def __init__(self):
        self.calls = []

    def issue_grant(self, media_ref, *, content_type, purpose, channel, report_id):
        self.calls.append((media_ref, purpose, report_id))
        return f"https://media.example/m/token-for-{media_ref}"


class Log:
    def __init__(self):
        self.a = []

    def record_action(self, event_id, action, status, detail=""):
        self.a.append((action, status))


def _svc(open_window=True):
    sender, grants, log = SpySender(), FakeGrants(), Log()
    svc = OutputService(OutputConfig(hsm_template="jornada_update", hsm_lang="es"),
                        FakeCipher(), FakeWindow(open_window), sender, log, grants=grants)
    return svc, sender, grants, log


def _env(media_refs, text="¿Cuál es la persona? Responde el número o «ninguno».", report_id="rep-1"):
    return {"event_id": "evt-1", "event_type": "outbound.reply",
            "payload": {"bot_id": "bot-1", "channel": "whatsapp", "contact_ref": "584120000000",
                        "jwe_body": text, "media_refs": list(media_refs), "report_id": report_id}}


def test_two_faces_uses_buttons_and_issues_grants():
    svc, sender, grants, _ = _svc(open_window=True)
    res = svc.handle(_env(["vault://crop/a", "vault://crop/b"]))
    assert res.mode is DeliveryMode.INTERACTIVE
    # una concesión + una imagen por rostro, etiquetadas con report_id y purpose de desambiguación
    assert [c[0] for c in grants.calls] == ["vault://crop/a", "vault://crop/b"]
    assert all(p == "disambiguation_crop" and r == "rep-1" for _, p, r in grants.calls)
    assert [img[2] for img in sender.images] == ["Rostro 1", "Rostro 2"]
    assert all(img[1].startswith("https://media.example/m/") for img in sender.images)
    # 2 rostros → botones; las opciones incluyen "Ninguno" y son parseables por el chatbot
    assert len(sender.buttons) == 1 and sender.lists == []
    titles = [t for _id, t in sender.buttons[0][2]]
    assert titles == ["Rostro 1", "Rostro 2", "Ninguno"]


def test_three_faces_uses_list():
    svc, sender, grants, _ = _svc(open_window=True)
    res = svc.handle(_env(["vault://crop/a", "vault://crop/b", "vault://crop/c"]))
    assert res.mode is DeliveryMode.INTERACTIVE
    assert len(sender.images) == 3
    assert sender.buttons == [] and len(sender.lists) == 1
    rows = sender.lists[0][3]
    assert [t for _id, t in rows] == ["Rostro 1", "Rostro 2", "Rostro 3", "Ninguno"]


def test_no_media_refs_keeps_text_path():
    svc, sender, grants, _ = _svc(open_window=True)
    res = svc.handle({"event_id": "e", "payload": {"bot_id": "b", "channel": "whatsapp",
                     "contact_ref": "x", "jwe_body": "hola"}})
    assert res.mode is DeliveryMode.TEXT
    assert sender.texts == [("x", "hola")]
    assert grants.calls == [] and sender.images == []


def test_closed_window_falls_back_to_template_no_grants():
    svc, sender, grants, _ = _svc(open_window=False)
    res = svc.handle(_env(["vault://crop/a", "vault://crop/b"]))
    assert res.mode is DeliveryMode.TEMPLATE
    assert grants.calls == [] and sender.images == []
    assert sender.templates == [("584120000000", "jornada_update", "es")]


def test_build_face_options_and_use_buttons():
    opts = build_face_options(3)
    assert [o.label for o in opts] == ["Rostro 1", "Rostro 2", "Rostro 3", "Ninguno"]
    assert opts[-1].id == "face:none" and opts[0].id == "face:0"
    assert use_buttons(2) and not use_buttons(3)

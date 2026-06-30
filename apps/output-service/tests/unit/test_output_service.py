"""Orquestación del Servicio de Salida: texto en ventana, HSM fuera (ADR-0005)."""
from output_service.config import OutputConfig
from output_service.application.output_service import OutputService
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
        self.texts = []
        self.templates = []
        self.images = []

    def send_text(self, bot_id, channel, contact_ref, text):
        self.texts.append((contact_ref, text))

    def send_template(self, bot_id, channel, contact_ref, template, lang):
        self.templates.append((contact_ref, template, lang))

    def send_image(self, bot_id, channel, contact_ref, link, caption):
        self.images.append((contact_ref, link, caption))


class FakeGrants:
    def __init__(self):
        self.calls = []

    def issue_grant(self, media_ref, *, content_type, purpose, channel, report_id):
        self.calls.append((media_ref, purpose, report_id))
        return f"https://media/m/tok-{media_ref.rsplit('/', 1)[-1]}"


class Log:
    def __init__(self):
        self.a = []

    def record_action(self, event_id, action, status, detail=""):
        self.a.append((action, status))


def _svc(open_window):
    sender, log = SpySender(), Log()
    svc = OutputService(OutputConfig(hsm_template="jornada_update", hsm_lang="es"),
                        FakeCipher(), FakeWindow(open_window), sender, log)
    return svc, sender, log


def _env(text="Hola, ¿nombre completo?"):
    return {"event_id": "evt-1", "event_type": "outbound.reply",
            "payload": {"bot_id": "bot-1", "channel": "whatsapp",
                        "contact_ref": "584120000000", "jwe_body": text}}


def test_within_window_sends_text():
    svc, sender, _ = _svc(True)
    res = svc.handle(_env("hola"))
    assert res.mode is DeliveryMode.TEXT
    assert sender.texts == [("584120000000", "hola")] and sender.templates == []


def test_outside_window_sends_hsm_template():
    svc, sender, _ = _svc(False)
    res = svc.handle(_env("hola"))
    assert res.mode is DeliveryMode.TEMPLATE
    assert sender.texts == []
    assert sender.templates == [("584120000000", "jornada_update", "es")]


def test_decrypts_body():
    svc, sender, _ = _svc(True)
    svc.handle({"event_id": "e", "payload": {"bot_id": "b", "channel": "whatsapp",
               "contact_ref": "x", "jwe_body": "PLAINTEXT(JWE-PENDIENTE):descifrado"}})
    # FakeCipher es passthrough, así que el prefijo llega tal cual; valida que se usa el cipher inyectado
    assert sender.texts[0][1].endswith("descifrado")


# --- cierre tipo imagen (ADR-0020 RF-18) ---
def _svc_grants(open_window):
    sender, log, grants = SpySender(), Log(), FakeGrants()
    svc = OutputService(OutputConfig(hsm_template="jornada_update", hsm_lang="es"),
                        FakeCipher(), FakeWindow(open_window), sender, log, grants=grants)
    return svc, sender, grants


def _img_env(caption="Reporte completo. ...", media_ref="vault://m/foto1", report_id="rep_1"):
    return {"event_id": "evt-img", "event_type": "outbound.reply",
            "payload": {"bot_id": "bot-1", "channel": "whatsapp", "contact_ref": "584120000000",
                        "jwe_body": caption, "kind": "image",
                        "media": {"media_ref": media_ref}, "report_id": report_id}}


def test_closing_image_issues_grant_and_sends_image():
    svc, sender, grants = _svc_grants(True)
    res = svc.handle(_img_env())
    assert res.mode is DeliveryMode.IMAGE
    assert grants.calls == [("vault://m/foto1", "enrollment_closing", "rep_1")]
    assert sender.images == [("584120000000", "https://media/m/tok-foto1", "Reporte completo. ...")]
    assert sender.texts == []


def test_closing_image_outside_window_falls_back_to_template():
    svc, sender, grants = _svc_grants(False)
    res = svc.handle(_img_env())
    assert res.mode is DeliveryMode.TEMPLATE      # fuera de ventana → HSM, sin imagen
    assert sender.images == [] and grants.calls == []


def test_closing_image_without_grants_falls_back_to_text_summary():
    """Sin media-gateway (no grants): el resumen igual llega como TEXTO (la imagen es prod, ADR-0017)."""
    svc, sender, _ = _svc(True)                   # _svc no inyecta grants
    res = svc.handle(_img_env(caption="Reporte completo. Nombre: Juan ..."))
    assert res.mode is DeliveryMode.TEXT
    assert sender.texts == [("584120000000", "Reporte completo. Nombre: Juan ...")]
    assert sender.images == []


def test_closing_image_grant_failure_falls_back_to_text():
    class BoomGrants:
        def issue_grant(self, *a, **k):
            raise RuntimeError("media-gateway caído")
    sender, log = SpySender(), Log()
    svc = OutputService(OutputConfig(), FakeCipher(), FakeWindow(True), sender, log, grants=BoomGrants())
    res = svc.handle(_img_env())
    assert res.mode is DeliveryMode.TEXT and sender.images == [] and len(sender.texts) == 1

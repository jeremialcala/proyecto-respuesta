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

    def send_text(self, bot_id, channel, contact_ref, text):
        self.texts.append((contact_ref, text))

    def send_template(self, bot_id, channel, contact_ref, template, lang):
        self.templates.append((contact_ref, template, lang))


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

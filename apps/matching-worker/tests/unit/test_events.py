"""Sobre común de eventos (ADR-0011)."""
import re

import pytest

from matching_worker.application.events import build_envelope, ENVELOPE_VERSION


def test_envelope_has_standard_fields():
    env = build_envelope("candidate.generated", {"x": 1}, "matching-worker")
    assert set(env) == {"event_id", "event_type", "producer", "timestamp", "version", "payload"}
    assert env["event_type"] == "candidate.generated"
    assert env["producer"] == "matching-worker"
    assert env["version"] == ENVELOPE_VERSION
    assert env["payload"] == {"x": 1}


def test_envelope_event_id_is_uuid_and_unique():
    a = build_envelope("e.x", {}, "p")
    b = build_envelope("e.x", {}, "p")
    assert re.fullmatch(r"[0-9a-f-]{36}", a["event_id"])
    assert a["event_id"] != b["event_id"]


def test_envelope_timestamp_is_utc_iso():
    env = build_envelope("e.x", {}, "p")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", env["timestamp"])


def test_envelope_overrides_are_respected():
    env = build_envelope("e.x", {}, "p", event_id="fixed", timestamp="2026-06-26T00:00:00Z")
    assert env["event_id"] == "fixed"
    assert env["timestamp"] == "2026-06-26T00:00:00Z"


@pytest.mark.parametrize("et,prod", [("", "p"), ("e.x", "")])
def test_envelope_requires_event_type_and_producer(et, prod):
    with pytest.raises(ValueError):
        build_envelope(et, {}, prod)

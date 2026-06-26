"""Veredicto de escaneo: precedencia CSAM > MALWARE > CLEAN (ADR-0005 child-safety)."""
from vault_worker.domain.scan import decide_verdict, sha256_hex
from vault_worker.domain.models import ScanVerdict


def test_clean():
    assert decide_verdict(av_clean=True, csam_hit=False) is ScanVerdict.CLEAN


def test_malware():
    assert decide_verdict(av_clean=False, csam_hit=False) is ScanVerdict.MALWARE


def test_csam_takes_precedence_over_av():
    # Aunque el AV diga limpio, un hit CSAM manda.
    assert decide_verdict(av_clean=True, csam_hit=True) is ScanVerdict.CSAM
    assert decide_verdict(av_clean=False, csam_hit=True) is ScanVerdict.CSAM


def test_sha256_stable():
    assert sha256_hex(b"abc") == sha256_hex(b"abc")
    assert sha256_hex(b"abc") != sha256_hex(b"abd")

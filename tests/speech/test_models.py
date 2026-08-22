import hashlib

import pytest

from claudechat.speech.models import IntegrityError, ModelSpec, ensure_model


def _spec_for(payload: bytes, url: str) -> ModelSpec:
    return ModelSpec(
        name="probe.bin",
        url=url,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def test_returns_existing_file_when_digest_matches(tmp_path):
    payload = b"good payload"
    (tmp_path / "probe.bin").write_bytes(payload)
    spec = _spec_for(payload, "https://example.invalid/probe.bin")
    assert ensure_model(spec, tmp_path) == tmp_path / "probe.bin"


def test_rejects_existing_file_with_wrong_digest(tmp_path):
    (tmp_path / "probe.bin").write_bytes(b"tampered")
    spec = _spec_for(b"good payload", "https://example.invalid/probe.bin")
    with pytest.raises(IntegrityError):
        ensure_model(spec, tmp_path)


def test_downloads_and_verifies(tmp_path, monkeypatch):
    payload = b"downloaded payload"
    spec = _spec_for(payload, "https://example.invalid/probe.bin")

    def fake_fetch(url, dest, max_bytes):
        dest.write_bytes(payload)

    monkeypatch.setattr("claudechat.speech.models._fetch", fake_fetch)
    path = ensure_model(spec, tmp_path)
    assert path.read_bytes() == payload


def test_rejects_download_with_wrong_digest(tmp_path, monkeypatch):
    spec = _spec_for(b"expected", "https://example.invalid/probe.bin")
    monkeypatch.setattr(
        "claudechat.speech.models._fetch",
        lambda url, dest, max_bytes: dest.write_bytes(b"malicious"),
    )
    with pytest.raises(IntegrityError):
        ensure_model(spec, tmp_path)
    assert not (tmp_path / "probe.bin").exists()

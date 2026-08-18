from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "github_api_utils.py"
    scripts_dir = str(script_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_request_json_retries_transient_url_errors(monkeypatch) -> None:
    module = load_script_module()
    outcomes: list[object] = [
        urllib.error.URLError("connection reset by peer"),
        urllib.error.URLError("certificate verify failed"),
        FakeResponse(b'{"ok": true}'),
    ]
    sleeps: list[float] = []

    def fake_urlopen(_request: object, *, timeout: float) -> FakeResponse:
        assert timeout == 1
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, FakeResponse)
        return outcome

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)

    assert module.request_json(
        "https://api.github.test/data",
        user_agent="test-agent",
        timeout_seconds=1,
        retry_delay_seconds=2,
    ) == {"ok": True}
    assert sleeps == [2, 4]
    assert outcomes == []


def test_request_json_does_not_retry_nontransient_http_errors(monkeypatch) -> None:
    module = load_script_module()
    calls = 0

    def fake_urlopen(_request: object, *, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            "https://api.github.test/missing",
            404,
            "Not Found",
            {},
            io.BytesIO(b"missing"),
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match=r"HTTP 404: missing"):
        module.request_json(
            "https://api.github.test/missing",
            user_agent="test-agent",
            retry_delay_seconds=0,
        )

    assert calls == 1

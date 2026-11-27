from __future__ import annotations

import email.message
import http.client
import io
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import network_retry as nr  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_budget() -> None:
    nr.reset_retry_budget()


def http_error(code: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    message = email.message.Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError("https://example.test/x", code, "boom", message, io.BytesIO(b""))


class FakeResponse:
    def __init__(self, body: bytes, *, content_length: int | None = None, fail_after: int | None = None):
        self.body = body
        self.headers = {"Content-Length": str(len(body) if content_length is None else content_length)}
        self.fail_after = fail_after
        self._stream = io.BytesIO(body)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        if self.fail_after is not None:
            raise ConnectionResetError(104, "Connection reset by peer")
        return self._stream.read(amount)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (http_error(502), True),
        (http_error(504), True),
        (http_error(429), True),
        (http_error(404), False),
        (http_error(401), False),
        (ConnectionResetError(104, "reset"), True),
        (http.client.IncompleteRead(b"abc", 10), True),
        (http.client.RemoteDisconnected("closed"), True),
        (TimeoutError("slow"), True),
        (socket.gaierror(-3, "temporary failure"), True),
        (ssl.SSLError("handshake"), True),
        (urllib.error.URLError("connection refused"), True),
        (urllib.error.URLError(ssl.SSLCertVerificationError("bad cert")), False),
        (nr.IncompleteDownload("short"), True),
        (FileNotFoundError("missing"), False),
        (ValueError("SHA-256 mismatch"), False),
    ],
)
def test_is_transient(error: BaseException, expected: bool) -> None:
    assert nr.is_transient(error) is expected


def test_backoff_delay_grows_and_caps() -> None:
    midpoint = lambda: 0.5  # noqa: E731 - jitter term becomes zero
    delays = [nr.backoff_delay(n, base_delay=5, max_delay=40, random_fraction=midpoint) for n in range(1, 6)]
    assert delays == [5, 10, 20, 40, 40]
    assert nr.backoff_delay(1, base_delay=10, random_fraction=lambda: 0.0) == pytest.approx(7.5)
    assert nr.backoff_delay(1, base_delay=10, random_fraction=lambda: 1.0) == pytest.approx(12.5)


def test_retry_call_recovers_from_transient_failures() -> None:
    outcomes = [ConnectionResetError(104, "reset"), http_error(503), "ok"]
    sleeps: list[float] = []

    def action() -> str:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert nr.retry_call("op", action, sleep=sleeps.append) == "ok"
    assert len(sleeps) == 2


def test_retry_call_does_not_retry_permanent_errors() -> None:
    calls: list[int] = []

    def action() -> None:
        calls.append(1)
        raise http_error(404)

    with pytest.raises(urllib.error.HTTPError):
        nr.retry_call("op", action, sleep=lambda _s: None)
    assert calls == [1]


def test_retry_call_gives_up_after_attempts() -> None:
    calls: list[int] = []

    def action() -> None:
        calls.append(1)
        raise ConnectionResetError(104, "reset")

    with pytest.raises(ConnectionResetError):
        nr.retry_call("op", action, attempts=3, sleep=lambda _s: None)
    assert len(calls) == 3


def test_retry_call_honours_retry_after() -> None:
    outcomes: list[object] = [http_error(429, {"Retry-After": "90"}), "ok"]
    sleeps: list[float] = []

    def action() -> str:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    nr.retry_call("op", action, sleep=sleeps.append)
    assert sleeps == [90.0]


def test_retry_budget_stops_retrying_during_an_outage(monkeypatch) -> None:
    monkeypatch.setenv(nr.RETRY_BUDGET_ENV, "12")
    calls: list[int] = []

    def action() -> None:
        calls.append(1)
        raise http_error(504)

    with pytest.raises(urllib.error.HTTPError):
        nr.retry_call("op", action, attempts=10, base_delay=5, sleep=lambda _s: None)
    # first retry (~5s) fits the 12s budget; the next (~10s) does not.
    assert len(calls) == 2


def test_read_url_retries_reset_while_reading_body(monkeypatch) -> None:
    responses = [FakeResponse(b"", fail_after=0), FakeResponse(b"payload")]
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: responses.pop(0))
    monkeypatch.setattr(nr.time, "sleep", lambda _s: None)
    assert nr.read_url("https://example.test/x", timeout=1) == b"payload"


def test_read_url_treats_short_body_as_retryable(monkeypatch) -> None:
    responses = [FakeResponse(b"abc", content_length=10), FakeResponse(b"0123456789")]
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: responses.pop(0))
    monkeypatch.setattr(nr.time, "sleep", lambda _s: None)
    assert nr.read_url("https://example.test/x", timeout=1) == b"0123456789"


def test_download_url_retries_truncation_and_leaves_no_temp_file(monkeypatch, tmp_path: Path) -> None:
    responses = [FakeResponse(b"abc", content_length=10), FakeResponse(b"0123456789")]
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: responses.pop(0))
    monkeypatch.setattr(nr.time, "sleep", lambda _s: None)
    destination = tmp_path / "sub" / "archive.tar.gz"
    nr.download_url("https://example.test/x", destination, timeout=1)
    assert destination.read_bytes() == b"0123456789"
    assert [path.name for path in destination.parent.iterdir()] == ["archive.tar.gz"]


def test_download_url_retries_when_verify_reports_incomplete(monkeypatch, tmp_path: Path) -> None:
    responses = [FakeResponse(b"short"), FakeResponse(b"complete")]
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: responses.pop(0))
    monkeypatch.setattr(nr.time, "sleep", lambda _s: None)

    def verify(path: Path) -> None:
        if path.stat().st_size != len(b"complete"):
            raise nr.IncompleteDownload("size mismatch")

    destination = tmp_path / "archive"
    nr.download_url("https://example.test/x", destination, timeout=1, verify=verify)
    assert destination.read_bytes() == b"complete"


def test_download_url_does_not_retry_digest_failures(monkeypatch, tmp_path: Path) -> None:
    calls: list[int] = []

    def fake_urlopen(*_args: object, **_kwargs: object) -> FakeResponse:
        calls.append(1)
        return FakeResponse(b"data")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(nr.time, "sleep", lambda _s: None)

    def verify(_path: Path) -> None:
        raise ValueError("SHA-256 mismatch")

    destination = tmp_path / "archive"
    with pytest.raises(ValueError, match="SHA-256"):
        nr.download_url("https://example.test/x", destination, timeout=1, verify=verify)
    assert calls == [1]
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("pr", "list", "--repo", "o/r"), True),
        (("pr", "view", "1"), True),
        (("api", "repos/o/r/commits/abc/check-runs"), True),
        (("api", "-X", "GET", "repos/o/r/issues", "-f", "state=open"), True),
        (("api", "--method=GET", "repos/o/r/issues"), True),
        (("api", "-X", "POST", "repos/o/r/issues"), False),
        (("api", "repos/o/r/issues", "-f", "title=x"), False),
        (("pr", "create", "--title", "x"), False),
        (("pr", "merge", "1"), False),
        (("workflow", "run", "x.yml"), False),
        ((), False),
    ],
)
def test_is_read_only_gh(args: tuple[str, ...], expected: bool) -> None:
    assert nr.is_read_only_gh(args) is expected


def fake_subprocess(outcomes: list[tuple[int, str, str]], calls: list[list[str]]):
    def fake_run(command, **_kwargs):
        calls.append(list(command))
        code, out, err = outcomes.pop(0)
        return subprocess.CompletedProcess(command, code, stdout=out, stderr=err)

    return fake_run


def test_run_gh_retries_transient_read(monkeypatch) -> None:
    calls: list[list[str]] = []
    outcomes = [
        (1, "", "HTTP 502: 502 Bad Gateway (https://api.github.com/graphql)\n"),
        (1, "", "Post https://api.github.com/graphql: unexpected EOF\n"),
        (0, "42\n", ""),
    ]
    monkeypatch.setattr(subprocess, "run", fake_subprocess(outcomes, calls))
    monkeypatch.setattr(nr.time, "sleep", lambda _s: None)
    assert nr.run_gh(["pr", "list", "--repo", "o/r"], capture=True) == "42"
    assert len(calls) == 3


def test_run_gh_does_not_retry_permanent_read_errors(monkeypatch) -> None:
    calls: list[list[str]] = []
    outcomes = [(1, "", "gh: Not Found (HTTP 404)\n")]
    monkeypatch.setattr(subprocess, "run", fake_subprocess(outcomes, calls))
    monkeypatch.setattr(nr.time, "sleep", lambda _s: None)
    with pytest.raises(subprocess.CalledProcessError) as raised:
        nr.run_gh(["api", "repos/o/r/releases"], capture=True)
    assert "404" in raised.value.stderr
    assert len(calls) == 1


def test_run_gh_never_retries_mutations(monkeypatch) -> None:
    calls: list[list[str]] = []
    outcomes = [(1, "", "HTTP 502: 502 Bad Gateway\n")]
    monkeypatch.setattr(subprocess, "run", fake_subprocess(outcomes, calls))
    monkeypatch.setattr(nr.time, "sleep", lambda _s: None)
    with pytest.raises(subprocess.CalledProcessError):
        nr.run_gh(["pr", "create", "--title", "x"])
    assert len(calls) == 1

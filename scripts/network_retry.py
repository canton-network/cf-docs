"""Shared retry handling for the network and `gh` calls made by generated-docs scripts.

Upstream flakes seen in scheduled runs were connection resets mid-download, HTTP 502/503/504
from GitHub, truncated release archives, and failed `gh api` polls. Each script used to carry
its own narrow retry loop (or none), so one dropped connection failed a whole target. Route
every outbound call through this module instead.

Design points:

- One transient classification (`is_transient`) covers `HTTPError` 408/425/429/5xx,
  `URLError`, every `ConnectionError`, timeouts, TLS errors, `http.client` errors such as
  `IncompleteRead`, and truncated downloads.
- Download, verification and body read happen inside the retried block, so a failure while
  streaming the body is retried, not just a failure to open the connection.
- Backoff is exponential with jitter and honours `Retry-After`.
- A process-wide retry budget keeps a real outage from multiplying delays across dozens of
  calls: once the budget is spent, failures raise immediately.
- Only read-only `gh` commands are retried automatically; mutations stay with their callers.
"""

from __future__ import annotations

import http.client
import os
import random
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
DEFAULT_ATTEMPTS = 5
DEFAULT_BASE_DELAY_SECONDS = 5.0
DEFAULT_MAX_DELAY_SECONDS = 60.0
JITTER_FRACTION = 0.25
MAX_RETRY_AFTER_SECONDS = 120.0
DEFAULT_RETRY_BUDGET_SECONDS = 600.0
RETRY_BUDGET_ENV = "NETWORK_RETRY_BUDGET_SECONDS"
CHUNK_BYTES = 1024 * 1024

# stderr signatures of transient `gh`/`git` failures. Kept narrow so deterministic errors
# (404, 401, validation failures) fail immediately.
TRANSIENT_STDERR_PATTERN = re.compile(
    r"HTTP 50[0234]|HTTP 429|HTTP 408|"
    r"\b50[0234] (?:Bad Gateway|Service Unavailable|Gateway Time-?out|Internal Server Error)\b|"
    r"connection reset|connection refused|broken pipe|unexpected eof|unexpected end of json|"
    r"unexpected disconnect|early eof|tls handshake timeout|i/o timeout|timed? ?out|"
    r"temporary failure in name resolution|no such host|could not resolve host|"
    r"remote end hung up|rate limit",
    re.IGNORECASE,
)

READ_ONLY_GH_COMMANDS = frozenset(
    {
        ("pr", "list"),
        ("pr", "view"),
        ("pr", "checks"),
        ("pr", "diff"),
        ("run", "list"),
        ("run", "view"),
        ("release", "list"),
        ("release", "view"),
        ("repo", "view"),
        ("auth", "status"),
    }
)


class IncompleteDownload(ValueError):
    """A download finished with fewer bytes than the server announced or the manifest records."""


_spent_retry_seconds = 0.0


def reset_retry_budget() -> None:
    global _spent_retry_seconds
    _spent_retry_seconds = 0.0


def retry_budget_seconds() -> float:
    raw = os.environ.get(RETRY_BUDGET_ENV)
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_RETRY_BUDGET_SECONDS


def is_transient(error: BaseException) -> bool:
    """True when retrying the same request later could plausibly succeed."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code in RETRYABLE_HTTP_STATUS_CODES
    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            return False
        return True
    if isinstance(error, ssl.SSLCertVerificationError):
        return False
    if isinstance(
        error,
        (
            ConnectionError,
            TimeoutError,
            socket.timeout,
            socket.gaierror,
            ssl.SSLError,
            http.client.HTTPException,
            EOFError,
            IncompleteDownload,
        ),
    ):
        return True
    return False


def backoff_delay(
    attempt: int,
    *,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    jitter: float = JITTER_FRACTION,
    random_fraction: Callable[[], float] = random.random,
) -> float:
    """Exponential delay for the Nth failed attempt (1-based), with +/- jitter."""
    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
    spread = delay * jitter
    return max(0.0, delay + (random_fraction() * 2 - 1) * spread)


def retry_after_seconds(error: BaseException) -> float | None:
    if not isinstance(error, urllib.error.HTTPError):
        return None
    value = error.headers.get("Retry-After") if error.headers is not None else None
    if not value:
        return None
    try:
        return min(MAX_RETRY_AFTER_SECONDS, max(0.0, float(value)))
    except ValueError:
        return None


def retry_call(
    operation: str,
    action: Callable[[], T],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    is_retryable: Callable[[BaseException], bool] = is_transient,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Run `action`, retrying transient failures with backoff until attempts or budget run out."""
    global _spent_retry_seconds
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    sleeper = sleep if sleep is not None else time.sleep
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except Exception as error:
            if attempt == attempts or not is_retryable(error):
                raise
            delay = backoff_delay(attempt, base_delay=base_delay, max_delay=max_delay)
            announced = retry_after_seconds(error)
            if announced is not None:
                delay = max(delay, announced)
            if _spent_retry_seconds + delay > retry_budget_seconds():
                print(
                    f"{operation} failed: {error}; retry budget "
                    f"({retry_budget_seconds():g}s) exhausted, not retrying",
                    file=sys.stderr,
                )
                raise
            _spent_retry_seconds += delay
            print(
                f"{operation} attempt {attempt}/{attempts} failed: "
                f"{type(error).__name__}: {error}; retrying in {delay:.1f}s",
                file=sys.stderr,
            )
            sleeper(delay)
    raise AssertionError("unreachable")


def read_url(
    request: urllib.request.Request | str,
    *,
    timeout: float,
    operation: str | None = None,
    **retry_options: object,
) -> bytes:
    """Fetch a URL and return the whole body; opening and reading are retried together."""
    label = operation or f"GET {_request_url(request)}"

    def attempt() -> bytes:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            _check_announced_length(response, len(body))
            return body

    return retry_call(label, attempt, **retry_options)  # type: ignore[arg-type]


def download_url(
    request: urllib.request.Request | str,
    destination: Path,
    *,
    timeout: float,
    verify: Callable[[Path], None] | None = None,
    operation: str | None = None,
    **retry_options: object,
) -> None:
    """Stream a URL to `destination` atomically.

    The body is written to a temporary sibling, checked against `Content-Length` and the
    optional `verify` callback, then moved into place. All of that sits inside the retried
    block, so truncated or corrupt transfers are fetched again. `verify` may raise
    `IncompleteDownload` to mark a failure as retryable; any other exception it raises is final.
    """
    label = operation or f"download {_request_url(request)}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.{os.getpid()}.tmp")

    def attempt() -> None:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                with temporary.open("wb") as handle:
                    shutil.copyfileobj(response, handle, CHUNK_BYTES)
                _check_announced_length(response, temporary.stat().st_size)
            if verify is not None:
                verify(temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    retry_call(label, attempt, **retry_options)  # type: ignore[arg-type]


def is_read_only_gh(args: Sequence[str]) -> bool:
    """True for `gh` invocations that are safe to repeat."""
    if not args:
        return False
    if args[0] == "api":
        method: str | None = None
        for index, token in enumerate(args):
            if token in ("-X", "--method") and index + 1 < len(args):
                method = args[index + 1].upper()
            elif token.startswith("--method="):
                method = token.split("=", 1)[1].upper()
            elif token.startswith("-X") and len(token) > 2:
                method = token[2:].upper()
        has_body = any(
            token in ("-f", "-F", "--field", "--raw-field", "--input")
            or token.startswith(("--field=", "--raw-field=", "--input="))
            for token in args
        )
        # `gh api` switches to POST when fields are given without an explicit method.
        return method == "GET" or (method is None and not has_body)
    return len(args) >= 2 and (args[0], args[1]) in READ_ONLY_GH_COMMANDS


def run_command(
    command: Sequence[str],
    *,
    capture: bool = False,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    operation: str | None = None,
    retry: bool = False,
    **retry_options: object,
) -> str:
    """Run a command, optionally retrying when stderr shows a transient network failure.

    stderr is always captured and echoed so the signature can be classified; the raised
    `CalledProcessError` carries it. stdout is returned stripped when `capture` is set and
    passed through to the console otherwise.
    """
    merged_env = None
    if env is not None:
        merged_env = os.environ.copy()
        merged_env.update(env)
    label = operation or " ".join(command[:3])

    def attempt() -> str:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
        )
        if completed.stderr:
            sys.stderr.write(completed.stderr)
            sys.stderr.flush()
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode,
                list(command),
                output=completed.stdout,
                stderr=completed.stderr,
            )
        return completed.stdout.strip() if capture else ""

    if not retry:
        return attempt()
    return retry_call(
        label,
        attempt,
        is_retryable=is_transient_command_failure,
        **retry_options,  # type: ignore[arg-type]
    )


def is_transient_command_failure(error: BaseException) -> bool:
    if not isinstance(error, subprocess.CalledProcessError):
        return False
    stderr = error.stderr if isinstance(error.stderr, str) else ""
    return bool(TRANSIENT_STDERR_PATTERN.search(stderr))


def run_gh(
    args: Sequence[str],
    *,
    capture: bool = False,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    **retry_options: object,
) -> str:
    """Run `gh`, retrying only read-only commands that fail with a transient error."""
    return run_command(
        ("gh", *args),
        capture=capture,
        env=env,
        cwd=cwd,
        retry=is_read_only_gh(args),
        operation=f"gh {' '.join(args[:2])}",
        **retry_options,
    )


def _request_url(request: urllib.request.Request | str) -> str:
    return request if isinstance(request, str) else request.full_url


def _check_announced_length(response: object, received: int) -> None:
    headers = getattr(response, "headers", None)
    announced = headers.get("Content-Length") if headers is not None else None
    if not isinstance(announced, str):
        return
    try:
        expected = int(announced)
    except (TypeError, ValueError):
        return
    # Content-Encoding can make the announced length differ from the decoded body, but the
    # urllib opener used here never decodes, so a mismatch means the transfer was cut short.
    if received != expected:
        raise IncompleteDownload(
            f"received {received} of {expected} bytes announced by Content-Length"
        )

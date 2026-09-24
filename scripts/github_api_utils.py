from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 5.0
RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _retry_delay(retry_delay_seconds: float, attempt: int) -> float:
    return retry_delay_seconds * attempt


def _log_retry(
    *,
    url: str,
    attempt: int,
    attempts: int,
    detail: str,
    delay: float,
) -> None:
    print(
        f"GitHub API request attempt {attempt}/{attempts} failed for {url}: {detail}; "
        f"retrying in {delay:g}s",
        file=sys.stderr,
    )


def request_json(
    url: str,
    *,
    user_agent: str,
    timeout_seconds: float = 30,
    attempts: int = DEFAULT_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> Any:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must not be negative")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": user_agent,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            detail = f"HTTP {error.code}: {message}"
            if error.code not in RETRYABLE_HTTP_STATUS_CODES or attempt == attempts:
                raise RuntimeError(
                    f"GitHub API request failed for {url}: {detail}"
                ) from error
            delay = _retry_delay(retry_delay_seconds, attempt)
            _log_retry(
                url=url,
                attempt=attempt,
                attempts=attempts,
                detail=detail,
                delay=delay,
            )
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as error:
            detail = str(error)
            if attempt == attempts:
                raise RuntimeError(
                    f"GitHub API request failed for {url}: {detail}"
                ) from error
            delay = _retry_delay(retry_delay_seconds, attempt)
            _log_retry(
                url=url,
                attempt=attempt,
                attempts=attempts,
                detail=detail,
                delay=delay,
            )
            time.sleep(delay)

    raise AssertionError("unreachable")

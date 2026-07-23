from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TIMEOUT_SECONDS = 20.0
DPM_LATEST_URL = "https://get.digitalasset.com/install/latest"
USER_AGENT = "cf-docs-generated-reference-source-updater"


@dataclass(frozen=True)
class SourceUpdate:
    source: str
    path: Path
    field: str
    previous: str
    current: str


def load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def latest_dpm_version(*, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    request = urllib.request.Request(DPM_LATEST_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        version = response.read().decode("utf-8").strip()
    if not version:
        raise ValueError(f"{DPM_LATEST_URL} returned an empty latest version")
    return version

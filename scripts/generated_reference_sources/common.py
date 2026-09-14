from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TIMEOUT_SECONDS = 20.0
DPM_LATEST_URL = "https://get.digitalasset.com/install/latest"
USER_AGENT = "cf-docs-generated-reference-source-updater"
STABLE_DPM_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


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


def stable_dpm_versions(*, min_version: str) -> list[str]:
    minimum_match = STABLE_DPM_VERSION_RE.fullmatch(min_version)
    if minimum_match is None:
        raise ValueError(f"Invalid stable DPM min_version: {min_version}")
    minimum = tuple(int(part) for part in minimum_match.groups())
    completed = subprocess.run(
        ["dpm", "version", "--all", "--output", "json"],
        cwd=Path(tempfile.gettempdir()),
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list):
        raise ValueError("`dpm version --all --output json` returned a non-list payload")
    versions: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict) or entry.get("remote") is not True:
            continue
        version = entry.get("version")
        if not isinstance(version, str):
            continue
        match = STABLE_DPM_VERSION_RE.fullmatch(version)
        if match is None:
            continue
        parts = tuple(int(part) for part in match.groups())
        if parts >= minimum:
            versions.add(version)
    if not versions:
        raise ValueError(f"No stable remote DPM versions found at or after {min_version}")

    def sort_key(version: str) -> tuple[int, int, int]:
        match = STABLE_DPM_VERSION_RE.fullmatch(version)
        if match is None:
            raise ValueError(f"Invalid stable DPM version: {version}")
        major, minor, patch = match.groups()
        return int(major), int(minor), int(patch)

    return sorted(versions, key=sort_key)

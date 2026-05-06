from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness.characterization_common import CHARACTERIZATION_ROOT, load_json, relative_to_manifest, reset_dir, run_x2mdx, write_json


FIXTURE_DIR = CHARACTERIZATION_ROOT / "asyncapi"
SOURCE_CONFIG = FIXTURE_DIR / "source-artifacts.json"
INPUT_DIR = FIXTURE_DIR / "input"
CACHE_DIR = INPUT_DIR / "cache"
MANIFEST_PATH = INPUT_DIR / "manifest.json"
EXPECTED_DIR = FIXTURE_DIR / "expected"
EXPECTED_FILE = EXPECTED_DIR / "ledger-api-websocket-reference.mdx"
DOCS_JSON_BEFORE = FIXTURE_DIR / "docs_json.before.json"
DOCS_JSON_AFTER = FIXTURE_DIR / "docs_json.after.json"
DEFAULT_REPO_DIR = REPO_ROOT / ".cache" / "characterization" / "asyncapi" / "repos" / "splice-wallet-kernel"


def run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd else None,
        "check": True,
        "text": True,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    print("Running:", " ".join(command))
    completed = subprocess.run(command, **kwargs)
    return completed.stdout.strip() if capture else ""


def git(args: list[str], *, cwd: Path, capture: bool = False) -> str:
    return run(["git", *args], cwd=cwd, capture=capture)


def ensure_repo(repo_dir: Path, *, remote: str, fetch: bool) -> Path:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        run(["git", "clone", "--bare", remote, str(repo_dir)])
    if fetch:
        git(["fetch", "origin", "--tags", "--prune"], cwd=repo_dir)
    return repo_dir


def materialize_asyncapi_source(*, repo_dir: Path, ref: str, source_path: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        git(["show", f"{ref}:{source_path}"], cwd=repo_dir, capture=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_manifest(*, skip_fetch: bool) -> Path:
    source_config = load_json(SOURCE_CONFIG)
    repo_config = source_config.get("repo") if isinstance(source_config.get("repo"), dict) else {}
    remote = repo_config.get("remote")
    ref = repo_config.get("ref")
    source_path_template = source_config.get("source_path_template")
    if not isinstance(remote, str) or not remote:
        raise ValueError("Source config must define repo.remote")
    if not isinstance(ref, str) or not ref:
        raise ValueError("Source config must define repo.ref")
    if not isinstance(source_path_template, str) or not source_path_template:
        raise ValueError("Source config must define source_path_template")

    selected_versions = [version for version in source_config.get("versions", []) if isinstance(version, str) and version]
    if not selected_versions:
        raise ValueError("Source config must define a non-empty versions list")

    repo_dir = ensure_repo(DEFAULT_REPO_DIR, remote=remote, fetch=not skip_fetch)
    versions_payload: list[dict[str, str]] = []
    for version in selected_versions:
        source_path = source_path_template.format(version=version)
        fixture_path = materialize_asyncapi_source(
            repo_dir=repo_dir,
            ref=ref,
            source_path=source_path,
            output_path=CACHE_DIR / version / "asyncapi.yaml",
        )
        versions_payload.append(
            {
                "version": version,
                "source_path": source_path,
                "fixture_path": relative_to_manifest(fixture_path, MANIFEST_PATH),
            }
        )

    return write_json(
        MANIFEST_PATH,
        {
            "source": source_config.get("source") or "splice-wallet-kernel Ledger API AsyncAPI snapshots",
            "publish_version": source_config.get("publish_version") or selected_versions[-1],
            "versions": versions_payload,
        },
    )


def refresh(*, skip_fetch: bool) -> Path:
    source_config = load_json(SOURCE_CONFIG)
    publish_version = str(source_config.get("publish_version") or "")
    if not publish_version:
        raise ValueError("Source config must define publish_version")

    manifest_path = build_manifest(skip_fetch=skip_fetch)
    reset_dir(EXPECTED_DIR)
    run_x2mdx(
        [
            "asyncapi",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--output-file",
            str(EXPECTED_FILE),
            "--publish-version",
            publish_version,
            "--source-name",
            "splice-wallet-kernel Ledger API AsyncAPI snapshots",
            "--version-filter",
            "characterization fixture versions",
            "--page-title",
            "JSON API AsyncAPI Reference",
            "--page-description",
            "JSON Ledger API WebSocket AsyncAPI reference and version history.",
        ]
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        docs_root = Path(temp_dir) / "docs-main"
        output_file = docs_root / "reference" / "json-api-asyncapi-reference.mdx"
        docs_json_path = docs_root / "docs.json"
        docs_json_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DOCS_JSON_BEFORE, docs_json_path)
        run_x2mdx(
            [
                "asyncapi",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-file",
                str(output_file),
                "--publish-version",
                publish_version,
                "--source-name",
                "splice-wallet-kernel Ledger API AsyncAPI snapshots",
                "--version-filter",
                "characterization fixture versions",
                "--page-title",
                "JSON API AsyncAPI Reference",
                "--page-description",
                "JSON Ledger API WebSocket AsyncAPI reference and version history.",
                "--docs-json",
                str(docs_json_path),
                "--nav-dropdown",
                "Reference",
                "--nav-group",
                "Ledger API Endpoints",
            ]
        )
        write_json(DOCS_JSON_AFTER, load_json(docs_json_path))
    return EXPECTED_FILE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the AsyncAPI characterization fixtures from splice-wallet-kernel Ledger API snapshots."
    )
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()
    refresh(skip_fetch=args.skip_fetch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

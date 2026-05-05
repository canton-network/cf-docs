from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness.characterization_common import CHARACTERIZATION_ROOT, load_json, relative_to_manifest, reset_dir, run_x2mdx, write_json


FIXTURE_DIR = CHARACTERIZATION_ROOT / "openrpc"
SOURCE_CONFIG = FIXTURE_DIR / "source-artifacts.json"
INPUT_DIR = FIXTURE_DIR / "input"
CACHE_DIR = INPUT_DIR / "cache"
MANIFEST_PATH = INPUT_DIR / "manifest.json"
EXPECTED_DIR = FIXTURE_DIR / "expected"
EXPECTED_ALT_LAYOUT_DIR = FIXTURE_DIR / "expected_alt_layout"
DEFAULT_REPO_DIR = REPO_ROOT / ".cache" / "characterization" / "openrpc" / "repos" / "splice-wallet-kernel"


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


def materialize_openrpc_spec(*, repo_dir: Path, tag: str, source_path: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        git(["show", f"{tag}:{source_path}"], cwd=repo_dir, capture=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_manifest(*, skip_fetch: bool) -> Path:
    source_config = load_json(SOURCE_CONFIG)
    repo_config = source_config.get("repo") if isinstance(source_config.get("repo"), dict) else {}
    remote = repo_config.get("remote")
    tag_prefix = repo_config.get("tag_prefix")
    if not isinstance(remote, str) or not remote:
        raise ValueError("Source config must define repo.remote")
    if not isinstance(tag_prefix, str) or not tag_prefix:
        raise ValueError("Source config must define repo.tag_prefix")

    selected_versions = [version for version in source_config.get("versions", []) if isinstance(version, str) and version]
    if not selected_versions:
        raise ValueError("Source config must define a non-empty versions list")

    repo_dir = ensure_repo(DEFAULT_REPO_DIR, remote=remote, fetch=not skip_fetch)
    specs_payload: list[dict[str, Any]] = []
    for spec in source_config.get("specs", []):
        if not isinstance(spec, dict):
            continue
        spec_id = spec.get("spec_id")
        display_name = spec.get("display_name")
        source_path = spec.get("source_path")
        if not isinstance(spec_id, str) or not spec_id:
            continue
        if not isinstance(display_name, str) or not display_name:
            continue
        if not isinstance(source_path, str) or not source_path:
            continue

        version_entries: list[dict[str, str]] = []
        for version in selected_versions:
            tag = f"{tag_prefix}{version}"
            fixture_path = materialize_openrpc_spec(
                repo_dir=repo_dir,
                tag=tag,
                source_path=source_path,
                output_path=CACHE_DIR / "specs" / version / Path(source_path).name,
            )
            version_entries.append(
                {
                    "version": version,
                    "source_path": source_path,
                    "fixture_path": fixture_path.resolve().relative_to(REPO_ROOT.resolve()).as_posix(),
                }
            )

        specs_payload.append(
            {
                "spec_id": spec_id,
                "display_name": display_name,
                "source_path": source_path,
                "versions": version_entries,
            }
        )

    return write_json(
        MANIFEST_PATH,
        {
            "source": source_config.get("source") or "splice-wallet-kernel Wallet Gateway OpenRPC release-tag snapshots",
            "overview_title": source_config.get("overview_title") or "Wallet Gateway JSON-RPC",
            "publish_version": source_config.get("publish_version") or selected_versions[-1],
            "specs": specs_payload,
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
            "openrpc",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(EXPECTED_DIR),
            "--fixture-root",
            str(REPO_ROOT),
            "--publish-version",
            publish_version,
            "--source-name",
            "splice-wallet-kernel Wallet Gateway OpenRPC release-tag snapshots",
            "--version-filter",
            "characterization fixture versions",
            "--link-prefix",
            "/reference/wallet-gateway-json-rpc",
        ]
    )
    reset_dir(EXPECTED_ALT_LAYOUT_DIR)
    run_x2mdx(
        [
            "openrpc",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(EXPECTED_ALT_LAYOUT_DIR),
            "--fixture-root",
            str(REPO_ROOT),
            "--publish-version",
            publish_version,
            "--source-name",
            "splice-wallet-kernel Wallet Gateway OpenRPC release-tag snapshots",
            "--version-filter",
            "characterization fixture versions",
            "--overview-name",
            "wallet-gateway-overview.mdx",
            "--spec-dir-name",
            "rpc-specs",
            "--link-prefix",
            "/reference/wallet-gateway-json-rpc",
        ]
    )
    return EXPECTED_DIR


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the OpenRPC characterization fixtures from splice-wallet-kernel release tags."
    )
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()
    refresh(skip_fetch=args.skip_fetch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

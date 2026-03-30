#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "ledger-bindings" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "ledger-bindings"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "ledger-bindings" / "manifest.json"
DEFAULT_OVERVIEW_FILE = REPO_ROOT / "docs-main" / "appdev" / "reference" / "ledger-bindings-api-lifecycle.mdx"
DEFAULT_DETAILS_DIR = REPO_ROOT / "docs-main" / "appdev" / "reference" / "ledger-bindings-api-lifecycle"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download configured JavaDoc/ScalaDoc jars, write a local x2mdx manifest, and generate the Ledger bindings reference pages."
    )
    parser.add_argument(
        "--source-config",
        default=str(DEFAULT_SOURCE_CONFIG),
        help="Checked-in source config listing artifacts and versions to download.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help="Directory used to cache downloaded Javadoc/Scaladoc jars.",
    )
    parser.add_argument(
        "--manifest-out",
        default=str(DEFAULT_MANIFEST),
        help="Path to the generated local x2mdx manifest.",
    )
    parser.add_argument(
        "--overview-file",
        default=str(DEFAULT_OVERVIEW_FILE),
        help="Path to the generated overview MDX page.",
    )
    parser.add_argument(
        "--details-dir",
        default=str(DEFAULT_DETAILS_DIR),
        help="Directory for generated artifact and type pages.",
    )
    parser.add_argument(
        "--docs-json",
        default=str(DEFAULT_DOCS_JSON),
        help="Path to the Mintlify docs.json file to update.",
    )
    parser.add_argument(
        "--nav-dropdown",
        default="Reference",
        help="Top-level Mintlify dropdown to update with the overview page.",
    )
    parser.add_argument(
        "--nav-group",
        action="append",
        help="Mintlify group path to update. Repeat for nested groups.",
    )
    parser.add_argument(
        "--version",
        action="append",
        help="Artifact version to include. Repeat to limit generation to a subset of configured versions.",
    )
    parser.add_argument(
        "--repo-base",
        help="Override the Maven repository base URL from the checked-in source config.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download jars even if they already exist in the local cache.",
    )
    parser.add_argument(
        "--source-name",
        default="Published DAML Java/Scala bindings Javadoc/Scaladoc jars",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        default="configured bindings artifact versions",
        help="Version-filter label embedded in generated content.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def maven_javadoc_url(repo_base: str, group: str, artifact: str, version: str) -> str:
    group_path = group.replace(".", "/")
    file_name = f"{artifact}-{version}-javadoc.jar"
    return f"{repo_base.rstrip('/')}/{group_path}/{artifact}/{version}/{file_name}"


def download_file(url: str, target: Path, *, force: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        print(f"Using cached jar: {target}")
        return

    print(f"Downloading: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "digital-asset-docs-x2mdx/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while downloading {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while downloading {url}: {exc}") from exc


def build_manifest(
    *,
    source_config: dict[str, Any],
    cache_dir: Path,
    manifest_path: Path,
    include_versions: set[str] | None,
    repo_base_override: str | None,
    force_download: bool,
) -> Path:
    repo_base = repo_base_override or str(source_config.get("repo_base") or "https://repo1.maven.org/maven2")
    artifacts_payload: list[dict[str, Any]] = []

    artifacts = source_config.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Source config must contain an `artifacts` list")

    for artifact_entry in artifacts:
        if not isinstance(artifact_entry, dict):
            continue
        group = artifact_entry.get("group")
        artifact = artifact_entry.get("artifact")
        language = artifact_entry.get("language")
        versions = artifact_entry.get("versions")
        include_prefixes = artifact_entry.get("include_prefixes") or []
        if not isinstance(group, str) or not group:
            continue
        if not isinstance(artifact, str) or not artifact:
            continue
        if language not in {"java", "scala"}:
            continue
        if not isinstance(versions, list):
            continue

        version_entries: list[dict[str, str]] = []
        for version in versions:
            if not isinstance(version, str) or not version:
                continue
            if include_versions is not None and version not in include_versions:
                continue

            jar_target = cache_dir / "jars" / group / artifact / version / f"{artifact}-{version}-javadoc.jar"
            download_file(
                maven_javadoc_url(repo_base, group, artifact, version),
                jar_target,
                force=force_download,
            )
            version_entries.append(
                {
                    "version": version,
                    "jar_path": str(jar_target.resolve()),
                }
            )

        if not version_entries:
            continue

        artifacts_payload.append(
            {
                "group": group,
                "artifact": artifact,
                "language": language,
                "include_prefixes": [prefix for prefix in include_prefixes if isinstance(prefix, str)],
                "versions": version_entries,
            }
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": source_config.get("source") or "digital-asset/docs local JVM docs cache",
        "repo_base": repo_base,
        "artifacts": artifacts_payload,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def build_command(args: argparse.Namespace, manifest_path: Path) -> list[str]:
    command = [
        "x2mdx",
        "jvm-docs",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path.resolve()),
        "--overview-file",
        str(Path(args.overview_file).resolve()),
        "--details-dir",
        str(Path(args.details_dir).resolve()),
        "--docs-json",
        str(Path(args.docs_json).resolve()),
        "--nav-dropdown",
        args.nav_dropdown,
        "--source-name",
        args.source_name,
        "--version-filter",
        args.version_filter,
    ]

    for nav_group in args.nav_group or []:
        command.extend(["--nav-group", nav_group])
    for version in args.version or []:
        command.extend(["--version", version])
    return command


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    include_versions = set(args.version) if args.version else None
    manifest_path = build_manifest(
        source_config=source_config,
        cache_dir=Path(args.cache_dir).resolve(),
        manifest_path=Path(args.manifest_out).resolve(),
        include_versions=include_versions,
        repo_base_override=args.repo_base,
        force_download=args.force_download,
    )
    command = build_command(args, manifest_path)
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())

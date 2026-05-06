from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness.characterization_common import (
    CHARACTERIZATION_ROOT,
    load_json,
    relative_to_manifest,
    reset_dir,
    run_x2mdx,
    write_json,
)


FIXTURE_DIR = CHARACTERIZATION_ROOT / "jvm_docs"
SOURCE_CONFIG = FIXTURE_DIR / "source-artifacts.json"
INPUT_DIR = FIXTURE_DIR / "input"
CACHE_DIR = INPUT_DIR / "cache"
MANIFEST_PATH = INPUT_DIR / "manifest.json"
EXPECTED_DIR = FIXTURE_DIR / "expected"
OVERVIEW_FILE = EXPECTED_DIR / "index.mdx"
EXPECTED_DOCS_LAYOUT_DIR = FIXTURE_DIR / "expected_docs_layout"
DOCS_JSON_BEFORE = FIXTURE_DIR / "docs_json.before.json"
DOCS_JSON_AFTER = FIXTURE_DIR / "docs_json.after.json"


def slugify(value: str) -> str:
    out = value.lower()
    out = re.sub(r"[^a-z0-9]+", "-", out)
    return re.sub(r"-{2,}", "-", out).strip("-")


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
    request = urllib.request.Request(url, headers={"User-Agent": "x2mdx-characterization/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while downloading {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while downloading {url}: {exc}") from exc


def build_manifest(*, force_download: bool) -> Path:
    source_config = load_json(SOURCE_CONFIG)
    repo_base = str(source_config.get("repo_base") or "https://repo1.maven.org/maven2")

    artifacts: list[dict[str, Any]] = []
    for artifact_entry in source_config.get("artifacts", []):
        if not isinstance(artifact_entry, dict):
            continue
        versions = artifact_entry.get("versions")
        if not isinstance(versions, list):
            continue

        version_entries: list[dict[str, str]] = []
        for version in versions:
            if not isinstance(version, str) or not version:
                continue
            group = str(artifact_entry["group"])
            artifact = str(artifact_entry["artifact"])
            jar_path = CACHE_DIR / "jars" / artifact / version / f"{artifact}-{version}-javadoc.jar"
            download_file(
                maven_javadoc_url(repo_base, group, artifact, version),
                jar_path,
                force=force_download,
            )
            version_entries.append(
                {
                    "version": version,
                    "jar_path": relative_to_manifest(jar_path, MANIFEST_PATH),
                }
            )

        artifacts.append(
            {
                "group": artifact_entry["group"],
                "artifact": artifact_entry["artifact"],
                "language": artifact_entry["language"],
                "include_prefixes": artifact_entry.get("include_prefixes", []),
                **(
                    {"status_manifest": artifact_entry["status_manifest"]}
                    if isinstance(artifact_entry.get("status_manifest"), str)
                    else {}
                ),
                "versions": version_entries,
            }
        )

    return write_json(
        MANIFEST_PATH,
        {
            "source": "Published DAML Java/Scala bindings Javadoc/Scaladoc jars",
            "overview_title": source_config.get("overview_title") or "Ledger API Java Bindings",
            "artifacts": artifacts,
        },
    )


def refresh(*, force_download: bool) -> Path:
    manifest_path = build_manifest(force_download=force_download)
    reset_dir(EXPECTED_DIR)
    run_x2mdx(
        [
            "jvm-docs",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--overview-file",
            str(OVERVIEW_FILE),
            "--details-dir",
            str(EXPECTED_DIR),
            "--overview-title",
            "Ledger API JVM Bindings",
            "--source-name",
            "Published DAML Java/Scala bindings Javadoc/Scaladoc jars",
            "--version-filter",
            "characterization fixture versions",
        ]
    )
    reset_dir(EXPECTED_DOCS_LAYOUT_DIR)
    run_x2mdx(
        [
            "jvm-docs",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--overview-file",
            str(EXPECTED_DOCS_LAYOUT_DIR / "ledger-api-jvm-bindings.mdx"),
            "--details-dir",
            str(EXPECTED_DOCS_LAYOUT_DIR / "details"),
            "--source-name",
            "Published DAML Java/Scala bindings Javadoc/Scaladoc jars",
            "--version-filter",
            "characterization fixture versions",
        ]
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        docs_root = Path(temp_dir) / "docs-main"
        overview_file = docs_root / "reference" / "ledger-api-jvm-bindings.mdx"
        details_dir = docs_root / "reference" / "details"
        docs_json_path = docs_root / "docs.json"
        docs_json_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DOCS_JSON_BEFORE, docs_json_path)
        run_x2mdx(
            [
                "jvm-docs",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--overview-file",
                str(overview_file),
                "--details-dir",
                str(details_dir),
                "--docs-json",
                str(docs_json_path),
                "--nav-dropdown",
                "Reference",
                "--source-name",
                "Published DAML Java/Scala bindings Javadoc/Scaladoc jars",
                "--version-filter",
                "characterization fixture versions",
            ]
        )
        write_json(DOCS_JSON_AFTER, load_json(docs_json_path))
    return EXPECTED_DIR


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the JVM-docs characterization fixtures from published Javadoc/Scaladoc jars."
    )
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()
    refresh(force_download=args.force_download)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

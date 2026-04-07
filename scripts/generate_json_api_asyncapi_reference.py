#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "ledger-api-asyncapi" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "ledger-api-asyncapi"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "ledger-api-asyncapi" / "manifest.json"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "docs-main" / "appdev" / "reference" / "json-api-asyncapi-reference.mdx"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch published JSON Ledger API AsyncAPI pages, write an x2mdx manifest, and render the Mintlify page."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="Reference")
    parser.add_argument("--version", action="append", help="Explicit version to include. Repeat to limit generation.")
    parser.add_argument("--publish-version", help="Version whose websocket surface should be published.")
    parser.add_argument(
        "--source-name",
        default="docs.digitalasset.com JSON Ledger API AsyncAPI fixtures",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        default="published docs major versions",
        help="Version-filter label embedded in generated content.",
    )
    parser.add_argument(
        "--page-title",
        default="JSON API AsyncAPI Reference",
        help="Title to use for the generated page.",
    )
    parser.add_argument(
        "--page-description",
        default="JSON Ledger API WebSocket AsyncAPI reference and version history.",
        help="Description to use for the generated page.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def fetch_text(url: str) -> tuple[str | None, int | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "digital-asset-docs-x2mdx/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8"), response.status
    except urllib.error.HTTPError as exc:
        return exc.read().decode("utf-8", errors="replace"), exc.code


def extract_yaml(html_text: str) -> str:
    blocks = re.findall(r"<pre[^>]*>(.*?)</pre>", html_text, re.S)
    rendered_blocks: list[str] = []
    for block in blocks:
        text = re.sub(r"<[^>]+>", "", block)
        text = html.unescape(text).strip("\n")
        if not text or "asyncapi:" not in text:
            continue
        if text not in rendered_blocks:
            rendered_blocks.append(text)
    if not rendered_blocks:
        raise RuntimeError("No embedded AsyncAPI YAML block found in the source page")
    return rendered_blocks[0] + "\n"


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def write_manifest(
    *,
    source_config: dict[str, Any],
    manifest_path: Path,
    cache_dir: Path,
    repo_root: Path,
    versions: list[dict[str, str]],
    publish_version: str,
) -> Path:
    manifest_versions: list[dict[str, str]] = []
    for version_entry in versions:
        version = version_entry["version"]
        fixture_path = cache_dir / version / "asyncapi.yaml"
        if not fixture_path.exists():
            continue
        manifest_versions.append(
            {
                "version": version,
                "url": version_entry["url"],
                "source_path": version_entry["source_path"],
                "fixture_path": str(fixture_path.resolve().relative_to(repo_root.resolve())),
            }
        )

    manifest = {
        "source": source_config.get("source") or "docs.digitalasset.com published JSON Ledger API AsyncAPI pages",
        "publish_version": publish_version,
        "versions": manifest_versions,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def build_command(args: argparse.Namespace, manifest_path: Path, publish_version: str, versions: list[str]) -> list[str]:
    command = [
        "x2mdx",
        "asyncapi",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path),
        "--fixture-root",
        str(REPO_ROOT),
        "--output-file",
        str(Path(args.output_file).resolve()),
        "--docs-json",
        str(Path(args.docs_json).resolve()),
        "--nav-dropdown",
        args.nav_dropdown,
        "--publish-version",
        publish_version,
        "--source-name",
        args.source_name,
        "--version-filter",
        args.version_filter,
        "--page-title",
        args.page_title,
        "--page-description",
        args.page_description,
    ]
    for version in versions:
        command.extend(["--version", version])
    return command


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    configured_versions = source_config.get("versions")
    if not isinstance(configured_versions, list) or not all(isinstance(item, dict) for item in configured_versions):
        raise ValueError("Source config must define a `versions` list of objects")

    selected_versions = [
        {
            "version": str(entry["version"]),
            "url": str(entry["url"]),
            "source_path": str(entry["source_path"]),
        }
        for entry in configured_versions
        if (not args.version or str(entry.get("version")) in set(args.version))
    ]
    if not selected_versions:
        raise ValueError("No AsyncAPI versions selected")
    selected_versions.sort(key=lambda entry: version_key(entry["version"]))

    publish_version = args.publish_version or str(source_config.get("publish_version") or selected_versions[-1]["version"])
    if publish_version not in {entry["version"] for entry in selected_versions}:
        raise ValueError(f"Publish version '{publish_version}' is not selected")

    cache_dir = Path(args.cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    for entry in selected_versions:
        html_text, status = fetch_text(entry["url"])
        if status != 200 or html_text is None:
            raise RuntimeError(f"Failed to fetch AsyncAPI source page for {entry['version']}: {entry['url']} (status {status})")
        yaml_text = extract_yaml(html_text)
        output_path = cache_dir / entry["version"] / "asyncapi.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_text, encoding="utf-8")

    manifest_path = write_manifest(
        source_config=source_config,
        manifest_path=Path(args.manifest_out).resolve(),
        cache_dir=cache_dir,
        repo_root=REPO_ROOT,
        versions=selected_versions,
        publish_version=publish_version,
    )

    command = build_command(
        args,
        manifest_path=manifest_path,
        publish_version=publish_version,
        versions=[entry["version"] for entry in selected_versions],
    )
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())

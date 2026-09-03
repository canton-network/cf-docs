#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import textwrap
from typing import Any, TypedDict, cast
import urllib.parse
import urllib.request

from docs_env import ensure_repo_direnv


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "canton-release-reference"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "docs-main"
    / "global-synchronizer"
    / "reference"
    / "canton-console-commands.mdx"
)
DEFAULT_RELEASE_REPO = "digital-asset/canton"
REFERENCE_SCRIPT = REPO_ROOT / "scripts" / "canton_console_reference.canton"
SIMPLE_TOPOLOGY_CONFIG = Path("examples/01-simple-topology/simple-topology.conf")
USER_AGENT = "cf-docs-canton-console-reference/1.0"
STABLE_TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
PRIMARY_SECTIONS = (
    ("Participant", "Participant Commands"),
    ("Multiple Participants", "Multiple Participant Commands"),
    ("Sequencer", "Sequencer Administration Commands"),
    ("Mediator", "Mediator Administration Commands"),
)


class ConsoleItem(TypedDict):
    name: str
    arguments: list[list[str]]
    return_type: str
    summary: str
    description: str
    topic: list[str]
    scope: str


@dataclass(frozen=True)
class ReleaseAsset:
    tag: str
    version: str
    name: str
    url: str
    size: int
    digest: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Canton console command reference from a public Canton release binary."
    )
    parser.add_argument("--release-repo", default=DEFAULT_RELEASE_REPO)
    parser.add_argument(
        "--canton-tag",
        help="Public Canton release tag. Defaults to the latest GitHub release.",
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--reference-json",
        type=Path,
        help="Use previously generated reference JSON instead of downloading and running a Canton release.",
    )
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument(
        "--docs-json",
        help="Accepted for compatibility with the aggregate reference generator; this page does not alter navigation.",
    )
    return parser.parse_args()


def github_api_json(path: str) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com/{path.lstrip('/')}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_release_asset(*, release_repo: str, tag: str | None) -> ReleaseAsset:
    api_path = (
        f"repos/{release_repo}/releases/tags/{urllib.parse.quote(tag, safe='')}"
        if tag
        else f"repos/{release_repo}/releases/latest"
    )
    payload = github_api_json(api_path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected GitHub release object for {release_repo}")

    resolved_tag = payload.get("tag_name")
    if not isinstance(resolved_tag, str):
        raise ValueError(f"GitHub release is missing tag_name for {release_repo}")
    tag_match = STABLE_TAG_RE.fullmatch(resolved_tag)
    if tag_match is None:
        raise ValueError(f"Expected a stable Canton release tag, got {resolved_tag!r}")
    version = tag_match.group("version")
    asset_name = f"canton-open-source-{version}.tar.gz"

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError(f"GitHub release {resolved_tag} is missing assets")
    asset = next(
        (
            item
            for item in assets
            if isinstance(item, dict) and item.get("name") == asset_name
        ),
        None,
    )
    if asset is None:
        raise ValueError(f"GitHub release {resolved_tag} does not contain {asset_name}")

    url = asset.get("browser_download_url")
    size = asset.get("size")
    digest = asset.get("digest")
    if not isinstance(url, str) or not url:
        raise ValueError(
            f"GitHub release asset {asset_name} is missing its download URL"
        )
    if not isinstance(size, int) or size <= 0:
        raise ValueError(f"GitHub release asset {asset_name} is missing its size")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(
            f"GitHub release asset {asset_name} is missing its SHA-256 digest"
        )

    return ReleaseAsset(
        tag=resolved_tag,
        version=version,
        name=asset_name,
        url=url,
        size=size,
        digest=digest,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path, asset: ReleaseAsset) -> None:
    if path.stat().st_size != asset.size:
        raise ValueError(f"Release archive size mismatch for {path}")
    expected_digest = asset.digest.removeprefix("sha256:")
    actual_digest = sha256(path)
    if actual_digest != expected_digest:
        raise ValueError(
            f"Release archive SHA-256 mismatch for {path}: expected {expected_digest}, got {actual_digest}"
        )


def ensure_release_archive(
    *, asset: ReleaseAsset, cache_dir: Path, force_refresh: bool
) -> Path:
    archive_path = cache_dir / "release-assets" / asset.tag / asset.name
    if archive_path.exists() and not force_refresh:
        verify_archive(archive_path, asset)
        return archive_path

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = archive_path.with_name(f"{archive_path.name}.{os.getpid()}.tmp")
    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    try:
        with (
            urllib.request.urlopen(request, timeout=300) as response,
            temp_path.open("wb") as handle,
        ):
            shutil.copyfileobj(response, handle)
        verify_archive(temp_path, asset)
        temp_path.replace(archive_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return archive_path


def extract_release(
    *, archive_path: Path, asset: ReleaseAsset, cache_dir: Path, force_refresh: bool
) -> Path:
    extract_root = cache_dir / "release-distributions" / asset.tag
    distribution_root = extract_root / f"canton-open-source-{asset.version}"
    manifest_path = extract_root / ".asset.json"
    expected_manifest = {
        "asset": asset.name,
        "digest": asset.digest,
        "size": asset.size,
        "tag": asset.tag,
        "url": asset.url,
    }
    required_paths = (
        distribution_root / "bin" / "canton",
        distribution_root / "lib" / f"canton-open-source-{asset.version}.jar",
        distribution_root / SIMPLE_TOPOLOGY_CONFIG,
    )
    if (
        not force_refresh
        and manifest_path.is_file()
        and all(path.is_file() for path in required_paths)
    ):
        if json.loads(manifest_path.read_text(encoding="utf-8")) == expected_manifest:
            return distribution_root

    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    required_members = {
        path.relative_to(extract_root).as_posix() for path in required_paths
    }
    extracted_members: set[str] = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            if member.name not in required_members:
                continue
            archive.extract(member, extract_root, filter="data")
            extracted_members.add(member.name)
    missing_members = sorted(required_members - extracted_members)
    if missing_members:
        raise FileNotFoundError(
            f"Release archive is missing required files: {', '.join(missing_members)}"
        )

    canton_binary = distribution_root / "bin" / "canton"
    canton_binary.chmod(canton_binary.stat().st_mode | stat.S_IXUSR)
    manifest_path.write_text(
        json.dumps(expected_manifest, indent=2) + "\n", encoding="utf-8"
    )
    return distribution_root


def load_console_items(payload: object) -> list[ConsoleItem]:
    if not isinstance(payload, dict) or not isinstance(payload.get("console"), list):
        raise ValueError("Canton reference JSON must contain a console list")

    items: list[ConsoleItem] = []
    for index, item in enumerate(payload["console"]):
        if not isinstance(item, dict):
            raise ValueError(f"Console item {index} must be an object")
        required_strings = ("name", "return_type", "summary", "description", "scope")
        if not all(isinstance(item.get(key), str) for key in required_strings):
            raise ValueError(f"Console item {index} has invalid string fields")
        topics = item.get("topic")
        arguments = item.get("arguments")
        if (
            not isinstance(topics, list)
            or not topics
            or not all(isinstance(value, str) and value for value in topics)
        ):
            raise ValueError(f"Console item {index} has invalid topics")
        if not isinstance(arguments, list) or not all(
            isinstance(argument, list)
            and len(argument) == 2
            and all(isinstance(value, str) for value in argument)
            for argument in arguments
        ):
            raise ValueError(f"Console item {index} has invalid arguments")
        items.append(cast(ConsoleItem, item))
    return items


def generate_reference_json(
    *,
    distribution_root: Path,
    cache_dir: Path,
    asset: ReleaseAsset,
    force_refresh: bool,
) -> dict[str, Any]:
    script_digest = hashlib.sha256(REFERENCE_SCRIPT.read_bytes()).hexdigest()
    output_path = cache_dir / "reference-json" / asset.tag / f"{script_digest}.json"
    if output_path.is_file() and not force_refresh:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        load_console_items(payload)
        return payload

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(distribution_root / "bin" / "canton"),
        "run",
        str(REFERENCE_SCRIPT),
        "-c",
        str(distribution_root / SIMPLE_TOPOLOGY_CONFIG),
        "--log-level-stdout=error",
    ]
    environment = os.environ.copy()
    environment.pop("CI", None)
    completed = subprocess.run(
        command,
        cwd=distribution_root,
        env=environment,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    payload = json.loads(completed.stdout)
    load_console_items(payload)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def normalize_help_text(value: str) -> str:
    normalized = textwrap.dedent(value).strip()
    normalized = re.sub(r"``([^`]+)``", r"`\1`", normalized)
    return (
        normalized.replace("<", r"\<")
        .replace(">", r"\>")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def inline_code(value: str) -> str:
    if "`" in value:
        return f"`` {value} ``"
    return f"`{value}`"


def anchor_base(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-")


def sorted_items(items: list[ConsoleItem]) -> list[ConsoleItem]:
    return sorted(
        items,
        key=lambda item: (
            item["name"].casefold(),
            item["scope"].casefold(),
            tuple(
                (name.casefold(), value.casefold()) for name, value in item["arguments"]
            ),
        ),
    )


def render_command(
    item: ConsoleItem, *, heading_level: int, anchor_counts: dict[str, int]
) -> list[str]:
    base = anchor_base(item["name"])
    occurrence = anchor_counts[base]
    anchor_counts[base] += 1
    anchor = base if occurrence == 0 else f"{base}_{occurrence}"
    scope = "" if item["scope"] == "Stable" else f" ({item['scope']})"
    lines = [
        f'<div id="{anchor}" />',
        "",
        f"{'#' * heading_level} {inline_code(item['name'])}{scope}",
        "",
        normalize_help_text(item["summary"]),
        "",
    ]

    description = normalize_help_text(item["description"])
    if description:
        lines.extend([description, ""])
    if item["arguments"]:
        lines.extend(["**Arguments**", ""])
        for name, argument_type in item["arguments"]:
            lines.append(f"- {inline_code(name)}: {inline_code(argument_type)}")
        lines.append("")
    if item["return_type"]:
        lines.extend([f"**Returns:** {inline_code(item['return_type'])}", ""])
    return lines


def render_console_reference(items: list[ConsoleItem], *, asset: ReleaseAsset) -> str:
    section_roots = {root for root, _title in PRIMARY_SECTIONS}
    top_level = [item for item in items if item["topic"][0] not in section_roots]
    by_root: dict[str, list[ConsoleItem]] = {
        root: [item for item in items if item["topic"][0] == root]
        for root, _title in PRIMARY_SECTIONS
    }
    anchor_counts: dict[str, int] = defaultdict(int)
    lines = [
        "---",
        'title: "Canton Console Commands"',
        'description: "Generated Canton console command reference for participant, mediator, and sequencer administration."',
        "---",
        "",
        (
            "{/* GENERATED_FROM "
            f'source="{DEFAULT_RELEASE_REPO}" ref="{asset.tag}" asset="{asset.name}" '
            f'digest="{asset.digest}" command_count="{len(items)}" */}}'
        ),
        "",
        "# Console Commands",
        "",
        (
            f"This reference is generated from runtime help metadata in the public Canton {asset.version} release. "
            "Commands marked Preview, Testing, or Repair are outside the stable command surface."
        ),
        "",
        "## Top-level Commands",
        "",
        "The following commands are available at the top level of the Canton console.",
        "",
    ]
    for item in sorted_items(top_level):
        lines.extend(render_command(item, heading_level=3, anchor_counts=anchor_counts))

    for root, section_title in PRIMARY_SECTIONS:
        section_items = by_root[root]
        lines.extend([f"## {section_title}", ""])
        direct_items = [item for item in section_items if len(item["topic"]) == 1]
        for item in sorted_items(direct_items):
            lines.extend(
                render_command(item, heading_level=3, anchor_counts=anchor_counts)
            )

        grouped: dict[tuple[str, ...], list[ConsoleItem]] = defaultdict(list)
        for item in section_items:
            if len(item["topic"]) > 1:
                grouped[tuple(item["topic"][1:])].append(item)
        for topic in sorted(
            grouped, key=lambda value: tuple(part.casefold() for part in value)
        ):
            lines.extend([f"### {' › '.join(topic)}", ""])
            for item in sorted_items(grouped[topic]):
                lines.extend(
                    render_command(item, heading_level=4, anchor_counts=anchor_counts)
                )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ensure_repo_direnv(
        repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:]
    )
    args = parse_args()
    asset = resolve_release_asset(release_repo=args.release_repo, tag=args.canton_tag)
    if args.reference_json is not None:
        payload = json.loads(args.reference_json.read_text(encoding="utf-8"))
    else:
        archive_path = ensure_release_archive(
            asset=asset, cache_dir=args.cache_dir, force_refresh=args.force_refresh
        )
        distribution_root = extract_release(
            archive_path=archive_path,
            asset=asset,
            cache_dir=args.cache_dir,
            force_refresh=args.force_refresh,
        )
        payload = generate_reference_json(
            distribution_root=distribution_root,
            cache_dir=args.cache_dir,
            asset=asset,
            force_refresh=args.force_refresh,
        )

    items = load_console_items(payload)
    output = render_console_reference(items, asset=asset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Generated {args.output} from {asset.tag} ({len(items)} console commands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

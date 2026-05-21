#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from docs_env import ensure_repo_direnv


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPO_ROOT / "config" / "x2mdx" / "reference-update-policy.json"
DEFAULT_SUMMARY = REPO_ROOT / ".internal" / "reference-doc-update-summary.json"
USER_AGENT = "digital-asset-docs-reference-updater/1.0"


@dataclass(frozen=True)
class SurfaceResult:
    name: str
    config_paths: tuple[str, ...]
    changed: bool
    before: dict[str, Any]
    after: dict[str, Any]
    updates: tuple[str, ...]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update generated reference-doc source pins from upstream version sources."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Discover updates without modifying config files.")
    mode.add_argument("--apply", action="store_true", help="Rewrite source config files when newer versions exist.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    return parser.parse_args(argv)


def json_load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def numeric_version_prefix(version: str) -> str | None:
    match = re.match(r"^(?P<version>\d+\.\d+\.\d+)", version)
    return match.group("version") if match else None


def major_minor(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 2:
        raise ValueError(f"Expected semantic version with major.minor: {version}")
    return f"{parts[0]}.{parts[1]}"


def request_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_json_url(url: str) -> Any:
    request = urllib.request.Request(url, headers=request_headers())
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read().decode("utf-8")


def head_url(url: str) -> bool:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return 200 <= response.status < 400
    except urllib.error.HTTPError as exc:
        if exc.code == 405:
            get_request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(get_request, timeout=60) as response:
                return 200 <= response.status < 400
        return False


def github_paginated(path: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    page = 1
    while True:
        separator = "&" if "?" in path else "?"
        payload = fetch_json_url(f"https://api.github.com/{path}{separator}per_page=100&page={page}")
        if not isinstance(payload, list):
            raise ValueError(f"Expected GitHub list payload for {path}")
        output.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return output
        page += 1


def github_release_versions(repository: str, tag_regex: str, *, require_asset: str | None = None) -> list[str]:
    matcher = re.compile(tag_regex)
    versions: list[str] = []
    for release in github_paginated(f"repos/{repository}/releases"):
        if release.get("draft") or release.get("prerelease"):
            continue
        tag_name = release.get("tag_name")
        if not isinstance(tag_name, str):
            continue
        match = matcher.fullmatch(tag_name)
        if match is None:
            continue
        version = match.groupdict().get("version")
        if not version:
            continue
        if require_asset is not None:
            assets = release.get("assets")
            if not isinstance(assets, list):
                continue
            wanted = require_asset.format(version=version)
            if not any(isinstance(asset, dict) and asset.get("name") == wanted for asset in assets):
                continue
        versions.append(version)
    return sorted(set(versions), key=version_key)


def github_tag_versions(repository: str, tag_regex: str, group_name: str = "version") -> list[str]:
    matcher = re.compile(tag_regex)
    versions: list[str] = []
    for tag in github_paginated(f"repos/{repository}/tags"):
        name = tag.get("name")
        if not isinstance(name, str):
            continue
        match = matcher.fullmatch(name)
        if match is None:
            continue
        version = match.groupdict().get(group_name)
        if version:
            versions.append(version)
    return sorted(set(versions), key=version_key)


def git_remote_tag_versions(remote: str, tag_regex: str, group_name: str = "version") -> list[str]:
    completed = subprocess.run(
        ["git", "ls-remote", "--tags", remote],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    matcher = re.compile(tag_regex)
    versions: list[str] = []
    for line in completed.stdout.splitlines():
        ref = line.rsplit("\t", 1)[-1]
        if ref.endswith("^{}"):
            continue
        tag_name = ref.removeprefix("refs/tags/")
        match = matcher.fullmatch(tag_name)
        if match is None:
            continue
        version = match.groupdict().get(group_name)
        if version:
            versions.append(version)
    return sorted(set(versions), key=version_key)


def tag_versions(surface: dict[str, Any], group_name: str = "version") -> list[str]:
    remote = surface.get("remote")
    if isinstance(remote, str) and remote:
        return git_remote_tag_versions(remote, str(surface["tag_regex"]), group_name=group_name)
    return github_tag_versions(str(surface["repository"]), str(surface["tag_regex"]), group_name=group_name)


def latest_versions(versions: Iterable[str], keep: int) -> list[str]:
    selected = sorted(set(versions), key=version_key)
    if keep > 0:
        selected = selected[-keep:]
    return selected


def maven_metadata_versions(repo_base: str, group: str, artifact: str) -> list[str]:
    group_path = group.replace(".", "/")
    metadata_url = f"{repo_base.rstrip('/')}/{group_path}/{artifact}/maven-metadata.xml"
    root = ET.fromstring(fetch_text_url(metadata_url))
    versions = [
        node.text.strip()
        for node in root.findall("./versioning/versions/version")
        if node.text and re.fullmatch(r"\d+\.\d+\.\d+", node.text.strip())
    ]
    return sorted(set(versions), key=version_key)


def maven_javadoc_url(repo_base: str, group: str, artifact: str, version: str) -> str:
    group_path = group.replace(".", "/")
    return f"{repo_base.rstrip('/')}/{group_path}/{artifact}/{version}/{artifact}-{version}-javadoc.jar"


def npm_package_versions(package_name: str) -> list[str]:
    encoded = urllib.parse.quote(package_name, safe="")
    payload = fetch_json_url(f"https://registry.npmjs.org/{encoded}")
    versions = payload.get("versions") if isinstance(payload, dict) else None
    if not isinstance(versions, dict):
        raise ValueError(f"Expected npm versions object for {package_name}")
    return sorted(
        (version for version in versions if re.fullmatch(r"\d+\.\d+\.\d+", version)),
        key=version_key,
    )


def release_url(config: dict[str, Any], version: str, *, field: str = "version") -> str:
    template = config.get("release_url_template")
    if not isinstance(template, str) or not template:
        raise ValueError("Config must define release_url_template")
    return template.format(**{field: version, "version": version, "canton_version": version})


def validate_urls(urls: Iterable[str]) -> None:
    missing = [url for url in urls if not head_url(url)]
    if missing:
        formatted = "\n".join(f"- {url}" for url in missing)
        raise RuntimeError(f"Candidate artifacts are not reachable:\n{formatted}")


def surface_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)


def summarize_change(label: str, before: Any, after: Any) -> str | None:
    if before == after:
        return None
    return f"{label}: {before!r} -> {after!r}"


def update_github_release_versions(
    *,
    repo_root: Path,
    name: str,
    surface: dict[str, Any],
) -> SurfaceResult:
    path = str(surface["config_path"])
    config_path = repo_root / path
    before = json_load(config_path)
    after = surface_payload(before)
    versions = github_release_versions(
        str(surface["repository"]),
        str(surface["tag_regex"]),
    )
    min_version = after.get("min_version")
    if isinstance(min_version, str) and min_version:
        versions = [version for version in versions if version_key(version) >= version_key(min_version)]
    selected = latest_versions(versions, int(surface.get("keep") or 0))
    after["versions"] = selected
    if surface.get("publish_latest") and selected:
        after["publish_version"] = selected[-1]
    updates = tuple(
        item
        for item in (
            summarize_change("versions", before.get("versions"), after.get("versions")),
            summarize_change("publish_version", before.get("publish_version"), after.get("publish_version")),
        )
        if item
    )
    return SurfaceResult(name, (path,), before != after, before, after, updates)


def update_git_tag_versions(
    *,
    repo_root: Path,
    name: str,
    surface: dict[str, Any],
) -> SurfaceResult:
    path = str(surface["config_path"])
    config_path = repo_root / path
    before = json_load(config_path)
    after = surface_payload(before)
    versions = tag_versions(surface)
    min_version = after.get("min_version")
    if isinstance(min_version, str) and min_version:
        versions = [version for version in versions if version_key(version) >= version_key(min_version)]
    selected = latest_versions(versions, int(surface.get("keep") or 0))
    after["versions"] = selected
    if surface.get("publish_latest") and selected:
        after["publish_version"] = selected[-1]
    updates = tuple(
        item
        for item in (
            summarize_change("versions", before.get("versions"), after.get("versions")),
            summarize_change("publish_version", before.get("publish_version"), after.get("publish_version")),
        )
        if item
    )
    return SurfaceResult(name, (path,), before != after, before, after, updates)


def update_github_release_asset_versions(
    *,
    repo_root: Path,
    name: str,
    surface: dict[str, Any],
) -> SurfaceResult:
    path = str(surface["config_path"])
    config_path = repo_root / path
    before = json_load(config_path)
    after = surface_payload(before)
    versions = github_release_versions(
        str(surface["repository"]),
        str(surface["tag_regex"]),
        require_asset=str(surface["asset_template"]),
    )
    min_version = after.get("min_version")
    if isinstance(min_version, str) and min_version:
        versions = [version for version in versions if version_key(version) >= version_key(min_version)]
    selected = latest_versions(versions, int(surface.get("keep") or 0))
    after["versions"] = selected
    if surface.get("publish_latest") and selected:
        after["publish_version"] = selected[-1]
    updates = tuple(
        item
        for item in (
            summarize_change("versions", before.get("versions"), after.get("versions")),
            summarize_change("publish_version", before.get("publish_version"), after.get("publish_version")),
        )
        if item
    )
    return SurfaceResult(name, (path,), before != after, before, after, updates)


def update_canton_tag_versions(
    *,
    repo_root: Path,
    name: str,
    surface: dict[str, Any],
) -> SurfaceResult:
    path = str(surface["config_path"])
    config_path = repo_root / path
    before = json_load(config_path)
    after = surface_payload(before)
    versions = tag_versions(surface)
    min_version = after.get("min_version")
    if isinstance(min_version, str) and min_version:
        versions = [version for version in versions if version_key(version) >= version_key(min_version)]
    excluded = after.get("excluded_versions") or []
    if isinstance(excluded, list):
        excluded_set = {item for item in excluded if isinstance(item, str)}
        versions = [version for version in versions if version not in excluded_set]
    if surface.get("validate_release_url"):
        validate_urls(release_url(after, version) for version in versions)
    after["versions"] = versions
    updates = tuple(
        item
        for item in (summarize_change("versions", before.get("versions"), after.get("versions")),)
        if item
    )
    return SurfaceResult(name, (path,), before != after, before, after, updates)


def latest_canton_minor_entries(
    versions: list[str],
    keep_minor_count: int,
    current_entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    latest_by_minor: dict[str, str] = {}
    for version in versions:
        minor = major_minor(version)
        current = latest_by_minor.get(minor)
        if current is None or version_key(version) > version_key(current):
            latest_by_minor[minor] = version
    for entry in current_entries:
        minor = entry.get("version")
        current_canton_version = entry.get("canton_version")
        if not isinstance(minor, str) or not isinstance(current_canton_version, str):
            continue
        current_numeric = numeric_version_prefix(current_canton_version)
        candidate = latest_by_minor.get(minor)
        if current_numeric is None:
            latest_by_minor.setdefault(minor, current_canton_version)
        elif candidate is None or version_key(current_numeric) > version_key(candidate):
            latest_by_minor[minor] = current_canton_version
    selected_minors = sorted(latest_by_minor, key=version_key)[-keep_minor_count:]
    return [
        {
            "version": minor,
            "canton_version": latest_by_minor[minor],
        }
        for minor in selected_minors
    ]


def update_canton_release_bundle_minors(
    *,
    repo_root: Path,
    name: str,
    surface: dict[str, Any],
) -> SurfaceResult:
    config_paths = tuple(str(path) for path in surface["config_paths"])
    first_config = json_load(repo_root / config_paths[0])
    versions = tag_versions(surface, group_name="canton_version")
    current_entries = first_config.get("versions")
    if not isinstance(current_entries, list):
        current_entries = []
    entries = latest_canton_minor_entries(
        versions,
        int(surface["keep_minor_count"]),
        [entry for entry in current_entries if isinstance(entry, dict)],
    )
    if surface.get("validate_release_url"):
        validate_urls(release_url(first_config, entry["canton_version"], field="canton_version") for entry in entries)
    publish_version = entries[-1]["version"] if entries else None

    before_combined: dict[str, Any] = {}
    after_combined: dict[str, Any] = {}
    changed = False
    updates: list[str] = []
    for path in config_paths:
        before = json_load(repo_root / path)
        after = surface_payload(before)
        after["versions"] = copy.deepcopy(entries)
        if publish_version:
            after["publish_version"] = publish_version
        before_combined[path] = before
        after_combined[path] = after
        changed = changed or before != after
        for item in (
            summarize_change(f"{path} versions", before.get("versions"), after.get("versions")),
            summarize_change(f"{path} publish_version", before.get("publish_version"), after.get("publish_version")),
        ):
            if item:
                updates.append(item)
    return SurfaceResult(name, config_paths, changed, before_combined, after_combined, tuple(updates))


def update_maven_javadoc_artifact(
    *,
    repo_root: Path,
    name: str,
    surface: dict[str, Any],
) -> SurfaceResult:
    path = str(surface["config_path"])
    before = json_load(repo_root / path)
    after = surface_payload(before)
    repo_base = str(after.get("repo_base") or "https://repo1.maven.org/maven2")
    keep = int(surface.get("keep") or 0)
    artifacts = after.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError(f"{path} must define artifacts list")
    updates: list[str] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            continue
        group = artifact.get("group")
        artifact_name = artifact.get("artifact")
        if not isinstance(group, str) or not isinstance(artifact_name, str):
            continue
        versions = latest_versions(maven_metadata_versions(repo_base, group, artifact_name), keep)
        if surface.get("validate_javadoc"):
            validate_urls(maven_javadoc_url(repo_base, group, artifact_name, version) for version in versions)
        old_versions = artifact.get("versions")
        artifact["versions"] = versions
        item = summarize_change(f"artifacts[{index}].versions", old_versions, versions)
        if item:
            updates.append(item)
    return SurfaceResult(name, (path,), before != after, before, after, tuple(updates))


def update_npm_packages(
    *,
    repo_root: Path,
    name: str,
    surface: dict[str, Any],
) -> SurfaceResult:
    path = str(surface["config_path"])
    before = json_load(repo_root / path)
    after = surface_payload(before)
    keep = int(surface.get("keep") or 0)
    packages = after.get("packages")
    if not isinstance(packages, list):
        raise ValueError(f"{path} must define packages list")
    updates: list[str] = []
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            continue
        package_name = package.get("package_name")
        if not isinstance(package_name, str) or not package_name:
            continue
        versions = latest_versions(npm_package_versions(package_name), keep)
        old_versions = package.get("versions")
        old_publish_version = package.get("publish_version")
        package["versions"] = versions
        if surface.get("publish_latest") and versions:
            package["publish_version"] = versions[-1]
        for item in (
            summarize_change(f"packages[{index}].versions", old_versions, package.get("versions")),
            summarize_change(
                f"packages[{index}].publish_version",
                old_publish_version,
                package.get("publish_version"),
            ),
        ):
            if item:
                updates.append(item)
    return SurfaceResult(name, (path,), before != after, before, after, tuple(updates))


def surface_result(repo_root: Path, name: str, surface: dict[str, Any]) -> SurfaceResult:
    kind = surface.get("kind")
    if kind == "github-release-versions":
        return update_github_release_versions(repo_root=repo_root, name=name, surface=surface)
    if kind == "git-tag-versions":
        return update_git_tag_versions(repo_root=repo_root, name=name, surface=surface)
    if kind == "github-release-asset-versions":
        return update_github_release_asset_versions(repo_root=repo_root, name=name, surface=surface)
    if kind == "canton-tag-versions":
        return update_canton_tag_versions(repo_root=repo_root, name=name, surface=surface)
    if kind == "canton-release-bundle-minors":
        return update_canton_release_bundle_minors(repo_root=repo_root, name=name, surface=surface)
    if kind == "maven-javadoc-artifact":
        return update_maven_javadoc_artifact(repo_root=repo_root, name=name, surface=surface)
    if kind == "npm-packages":
        return update_npm_packages(repo_root=repo_root, name=name, surface=surface)
    raise ValueError(f"Unsupported surface kind for {name}: {kind}")


def write_results(repo_root: Path, results: list[SurfaceResult]) -> None:
    for result in results:
        if not result.changed:
            continue
        if len(result.config_paths) == 1:
            json_dump(repo_root / result.config_paths[0], result.after)
            continue
        for path in result.config_paths:
            json_dump(repo_root / path, result.after[path])


def summary_payload(results: list[SurfaceResult]) -> dict[str, Any]:
    updated = [result for result in results if result.changed]
    return {
        "has_updates": bool(updated),
        "updated_surfaces": [result.name for result in updated],
        "surfaces": [
            {
                "name": result.name,
                "config_paths": list(result.config_paths),
                "changed": result.changed,
                "updates": list(result.updates),
            }
            for result in results
        ],
    }


def pr_body(summary: dict[str, Any]) -> str:
    if not summary["has_updates"]:
        return "No generated reference-doc source updates were found."
    lines = [
        "Generated reference-doc source pins were updated from upstream releases.",
        "",
        "Updated surfaces:",
    ]
    for surface in summary["surfaces"]:
        if not surface["changed"]:
            continue
        lines.append(f"- {surface['name']}")
        for update in surface["updates"]:
            lines.append(f"  - {update}")
    lines.extend(
        [
            "",
            "Validation run by the workflow:",
            "- `npm run generate:all-reference-docs`",
            "- focused source-updater and generated-reference tests",
            "- `git diff --check`",
        ]
    )
    return "\n".join(lines)


def write_github_outputs(summary: dict[str, Any]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    body = pr_body(summary)
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"has_updates={str(summary['has_updates']).lower()}\n")
        handle.write(f"updated_surfaces={','.join(summary['updated_surfaces'])}\n")
        handle.write("pr_body<<EOF\n")
        handle.write(body)
        handle.write("\nEOF\n")


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    policy = json_load(Path(args.policy).resolve())
    surfaces = policy.get("surfaces")
    if not isinstance(surfaces, dict):
        raise ValueError("Policy must define a surfaces object")

    results: list[SurfaceResult] = []
    for name, surface in surfaces.items():
        if not isinstance(surface, dict):
            continue
        try:
            results.append(surface_result(repo_root, name, surface))
        except Exception as exc:
            raise RuntimeError(f"Failed to update source surface '{name}'") from exc
    if args.apply:
        write_results(repo_root, results)

    summary = summary_payload(results)
    json_dump(Path(args.summary).resolve(), summary)
    write_github_outputs(summary)
    print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_repo_direnv(repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:] if argv is None else argv)
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

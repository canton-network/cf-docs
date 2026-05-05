from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness.characterization_common import CHARACTERIZATION_ROOT, load_json, relative_to_manifest, reset_dir, run_x2mdx, write_json


FIXTURE_DIR = CHARACTERIZATION_ROOT / "protobuf"
SOURCE_CONFIG = FIXTURE_DIR / "source-artifacts.json"
INPUT_DIR = FIXTURE_DIR / "input"
CACHE_DIR = INPUT_DIR / "cache"
MANIFEST_PATH = INPUT_DIR / "manifest.json"
EXPECTED_DIR = FIXTURE_DIR / "expected"
DEFAULT_REPO_DIR = REPO_ROOT / ".cache" / "characterization" / "protobuf" / "repos" / "canton"
DESCRIPTOR_IMAGE_NAME = ".proto_snapshot_image.bin.gz"
STABLE_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
OWNED_PROTO_RE = re.compile(r"^community/.+/src/main/protobuf/.+\.proto$")


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


def git_bytes(args: list[str], *, cwd: Path, check: bool = True) -> bytes | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, completed.args, completed.stdout, completed.stderr)
    if not check and completed.returncode != 0:
        return None
    return completed.stdout


def ensure_repo(repo_dir: Path, *, remote: str, fetch: bool) -> Path:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        run(["git", "clone", "--bare", remote, str(repo_dir)])
    if fetch:
        git(["fetch", "origin", "--tags", "--prune"], cwd=repo_dir)
    return repo_dir


def semver_key(version: str) -> tuple[int, int, int]:
    match = STABLE_TAG_RE.fullmatch(f"v{version}" if not version.startswith("v") else version)
    if not match:
        raise ValueError(f"Expected stable semver version, got: {version}")
    return (int(match.group("major")), int(match.group("minor")), int(match.group("patch")))


def release_date(repo_dir: Path, tag: str) -> str | None:
    date = git(["for-each-ref", "--format=%(creatordate:short)", f"refs/tags/{tag}"], cwd=repo_dir, capture=True)
    return date or None


def list_owned_proto_paths(repo_dir: Path, tag: str) -> list[str]:
    tree = git(["ls-tree", "-r", "--name-only", tag, "community"], cwd=repo_dir, capture=True)
    return sorted(line.strip() for line in tree.splitlines() if OWNED_PROTO_RE.fullmatch(line.strip()) and "/target/" not in line)


def repo_path_to_import_path(repo_path: str) -> str:
    marker = "/src/main/protobuf/"
    if marker not in repo_path:
        raise ValueError(f"Unable to derive import path from '{repo_path}'")
    return repo_path.split(marker, 1)[1]


def descriptor_image_path(version: str) -> Path:
    return CACHE_DIR / "descriptor-images" / version / DESCRIPTOR_IMAGE_NAME


def materialize_descriptor_image(repo_dir: Path, *, tag: str, output_path: Path, force_refresh: bool) -> bool:
    if output_path.exists() and not force_refresh:
        return True
    image_bytes = git_bytes(["show", f"{tag}:{DESCRIPTOR_IMAGE_NAME}"], cwd=repo_dir, check=False)
    if image_bytes is None:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    return True


def build_manifest(*, skip_fetch: bool, force_refresh: bool) -> Path:
    source_config = load_json(SOURCE_CONFIG)
    repo_config = source_config.get("repo") if isinstance(source_config.get("repo"), dict) else {}
    remote = repo_config.get("remote")
    if not isinstance(remote, str) or not remote:
        raise ValueError("Source config must define repo.remote")
    selected_versions = {
        version for version in source_config.get("versions", []) if isinstance(version, str) and version
    }
    if not selected_versions:
        raise ValueError("Source config must define a non-empty versions list")

    repo_dir = ensure_repo(DEFAULT_REPO_DIR, remote=remote, fetch=not skip_fetch)
    releases: list[dict[str, Any]] = []
    for version in sorted(selected_versions, key=semver_key):
        tag = f"v{version}"
        proto_paths = list_owned_proto_paths(repo_dir, tag)
        if not proto_paths:
            raise ValueError(f"No owned protobuf files found for {tag}")
        image_path = descriptor_image_path(version)
        if not materialize_descriptor_image(repo_dir, tag=tag, output_path=image_path, force_refresh=force_refresh):
            raise ValueError(f"Missing {DESCRIPTOR_IMAGE_NAME} in {tag}")
        releases.append(
            {
                "version": version,
                "tag": tag,
                "date": release_date(repo_dir, tag),
                "descriptor_image_path": relative_to_manifest(image_path, MANIFEST_PATH),
                "import_to_repo_path": {
                    repo_path_to_import_path(repo_path): repo_path
                    for repo_path in proto_paths
                },
            }
        )

    metadata_path = FIXTURE_DIR / "metadata.json"
    return write_json(
        MANIFEST_PATH,
        {
            "source": source_config.get("source") or "Canton protobuf descriptor snapshots from release tags",
            "repo": {
                "remote": repo_config.get("remote"),
                "web_url": repo_config.get("web_url"),
            },
            "metadata_path": relative_to_manifest(metadata_path, MANIFEST_PATH),
            "versions": releases,
        },
    )


def refresh(*, skip_fetch: bool, force_refresh: bool) -> Path:
    manifest_path = build_manifest(skip_fetch=skip_fetch, force_refresh=force_refresh)
    reset_dir(EXPECTED_DIR)
    run_x2mdx(
        [
            "protobuf",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(EXPECTED_DIR),
            "--source-name",
            "Canton protobuf descriptor snapshots from release tags",
            "--version-filter",
            "characterization fixture versions",
        ]
    )
    return EXPECTED_DIR


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the protobuf characterization fixtures from Canton release tags."
    )
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()
    refresh(skip_fetch=args.skip_fetch, force_refresh=args.force_refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

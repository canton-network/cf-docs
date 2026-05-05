from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness.characterization_common import CHARACTERIZATION_ROOT, load_json, relative_to_manifest, reset_dir, run_x2mdx, write_json


FIXTURE_DIR = CHARACTERIZATION_ROOT / "typedoc"
SOURCE_CONFIG = FIXTURE_DIR / "source-artifacts.json"
INPUT_DIR = FIXTURE_DIR / "input"
CACHE_DIR = REPO_ROOT / ".cache" / "characterization" / "typedoc" / "npm"
TYPEDOC_DIR = INPUT_DIR / "typedoc"
MANIFEST_PATH = INPUT_DIR / "manifest.json"
EXPECTED_DIR = FIXTURE_DIR / "expected"
EXPECTED_FILE = EXPECTED_DIR / "typescript.mdx"


def run(command: list[str], *, cwd: Path, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print("Running:", " ".join(command))
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def patch_tsconfig(package_dir: Path) -> None:
    tsconfig_path = package_dir / "tsconfig.json"
    payload = json.loads(tsconfig_path.read_text(encoding="utf-8"))
    compiler_options = payload.setdefault("compilerOptions", {})
    if not isinstance(compiler_options, dict):
        raise ValueError(f"Expected compilerOptions object in {tsconfig_path}")
    compiler_options["ignoreDeprecations"] = "5.0"
    compiler_options["typeRoots"] = ["./node_modules/@types"]
    tsconfig_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def prepare_package(*, package_name: str, version: str, force_regenerate: bool) -> Path:
    version_dir = CACHE_DIR / version
    package_dir = version_dir / "package"
    tarball_path = version_dir / "package.tgz"

    if force_regenerate and version_dir.exists():
        shutil.rmtree(version_dir)

    if package_dir.exists():
        patch_tsconfig(package_dir)
        return package_dir

    version_dir.mkdir(parents=True, exist_ok=True)
    completed = run(["npm", "pack", "--silent", f"{package_name}@{version}"], cwd=version_dir, capture_output=True)
    tarball_name = completed.stdout.strip().splitlines()[-1].strip()
    packed_tarball = version_dir / tarball_name
    packed_tarball.rename(tarball_path)
    with tarfile.open(tarball_path, "r:gz") as archive:
        archive.extractall(version_dir)
    if not package_dir.exists():
        raise ValueError(f"Expected npm tarball to extract a package directory at {package_dir}")
    patch_tsconfig(package_dir)
    return package_dir


def ensure_package_dependencies(package_dir: Path, *, force_regenerate: bool) -> None:
    node_modules_dir = package_dir / "node_modules"
    if force_regenerate and node_modules_dir.exists():
        shutil.rmtree(node_modules_dir)
    if node_modules_dir.exists():
        print(f"Using cached npm install: {package_dir}")
        return
    run(["npm", "install", "--ignore-scripts", "--no-package-lock", "--silent"], cwd=package_dir)


def ensure_typedoc_json(
    *,
    package_name: str,
    typedoc_version: str,
    version: str,
    force_regenerate: bool,
) -> Path:
    output_json = TYPEDOC_DIR / version / "typedoc.json"
    if output_json.exists() and not force_regenerate:
        print(f"Using cached TypeDoc JSON: {output_json}")
        return output_json

    package_dir = prepare_package(
        package_name=package_name,
        version=version,
        force_regenerate=force_regenerate,
    )
    ensure_package_dependencies(package_dir, force_regenerate=force_regenerate)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "npx",
            "--yes",
            f"typedoc@{typedoc_version}",
            "--json",
            str(output_json),
            "index.d.ts",
        ],
        cwd=package_dir,
    )
    return output_json


def build_manifest(*, force_regenerate: bool) -> Path:
    source_config = load_json(SOURCE_CONFIG)
    selected_versions = [version for version in source_config.get("versions", []) if isinstance(version, str) and version]
    if not selected_versions:
        raise ValueError("No @daml/types versions configured for characterization")

    package_name = str(source_config.get("package_name") or "@daml/types")
    typedoc_version = str(source_config.get("typedoc_version") or "0.27.9")
    publish_version = str(source_config.get("publish_version") or selected_versions[-1])

    for version in selected_versions:
        ensure_typedoc_json(
            package_name=package_name,
            typedoc_version=typedoc_version,
            version=version,
            force_regenerate=force_regenerate,
        )

    return write_json(
        MANIFEST_PATH,
        {
            "source": source_config.get("source") or "Published @daml/types npm tarballs rendered to local TypeDoc JSON",
            "package_name": package_name,
            "publish_version": publish_version,
            "versions": [
                {
                    "version": version,
                    "json_path": relative_to_manifest(TYPEDOC_DIR / version / "typedoc.json", MANIFEST_PATH),
                }
                for version in selected_versions
            ],
        },
    )


def refresh(*, force_regenerate: bool) -> Path:
    manifest_path = build_manifest(force_regenerate=force_regenerate)
    reset_dir(EXPECTED_DIR)
    run_x2mdx(
        [
            "typedoc",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--output-file",
            str(EXPECTED_FILE),
            "--publish-version",
            "3.4.11",
            "--source-name",
            "Published @daml/types npm tarballs rendered to local TypeDoc JSON",
            "--version-filter",
            "characterization fixture versions",
            "--page-title",
            "TypeScript",
            "--page-description",
            "TypeScript and JavaScript language bindings for Canton.",
        ]
    )
    return EXPECTED_FILE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the TypeDoc characterization fixtures from published @daml/types npm tarballs."
    )
    parser.add_argument("--force-regenerate", action="store_true")
    args = parser.parse_args()
    refresh(force_regenerate=args.force_regenerate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

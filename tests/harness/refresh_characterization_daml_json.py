from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness.characterization_common import CHARACTERIZATION_ROOT, load_json, relative_to_manifest, reset_dir, run_x2mdx, write_json


FIXTURE_DIR = CHARACTERIZATION_ROOT / "daml_json"
SOURCE_CONFIG = FIXTURE_DIR / "source-artifacts.json"
INPUT_DIR = FIXTURE_DIR / "input"
CACHE_DIR = INPUT_DIR / "cache"
MANIFEST_PATH = INPUT_DIR / "manifest.json"
EXPECTED_DIR = FIXTURE_DIR / "expected"
HELPER_SCRIPT = Path(__file__).resolve().parent / "generate_daml_standard_library_json.sh"


def generate_json_snapshot(
    *,
    version: str,
    output_json: Path,
    package_set: str,
    sdk_source: str,
    lf_target: str | None,
    force_regenerate: bool,
) -> None:
    if output_json.exists() and not force_regenerate:
        print(f"Using cached Daml docs JSON: {output_json}")
        return

    output_json.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "bash",
        str(HELPER_SCRIPT),
        "--output-json",
        str(output_json),
        "--sdk-version",
        version,
        "--package-set",
        package_set,
        "--sdk-source",
        sdk_source,
    ]
    if lf_target:
        command.extend(["--lf-target", lf_target])
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=Path(__file__).resolve().parents[2], check=True)


def build_manifest(*, force_regenerate: bool) -> Path:
    source_config = load_json(SOURCE_CONFIG)
    selected_versions = [version for version in source_config.get("versions", []) if isinstance(version, str) and version]
    if not selected_versions:
        raise ValueError("No Daml SDK versions configured for characterization")

    package_set = str(source_config.get("package_set") or "base")
    sdk_source = str(source_config.get("sdk_source") or "dpm")
    lf_target = source_config.get("lf_target") if isinstance(source_config.get("lf_target"), str) else None
    publish_version = str(source_config.get("publish_version") or selected_versions[-1])

    for version in selected_versions:
        generate_json_snapshot(
            version=version,
            output_json=CACHE_DIR / "json" / version / "modules.json",
            package_set=package_set,
            sdk_source=sdk_source,
            lf_target=lf_target,
            force_regenerate=force_regenerate,
        )

    return write_json(
        MANIFEST_PATH,
        {
            "source": source_config.get("source") or "Published Daml Standard Library docs JSON from local SDK artifacts",
            "publish_version": publish_version,
            "versions": [
                {
                    "version": version,
                    "json_path": relative_to_manifest(CACHE_DIR / "json" / version / "modules.json", MANIFEST_PATH),
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
            "daml-json",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(EXPECTED_DIR),
            "--publish-version",
            "3.4.11",
            "--overview-title",
            "Daml Standard Library",
            "--source-name",
            "Published Daml Standard Library docs JSON from local SDK artifacts",
            "--version-filter",
            "characterization fixture versions",
            "--link-prefix",
            "/appdev/reference/daml-standard-library",
        ]
    )
    return EXPECTED_DIR


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the Daml JSON characterization fixtures from local SDK artifacts."
    )
    parser.add_argument("--force-regenerate", action="store_true")
    args = parser.parse_args()
    refresh(force_regenerate=args.force_regenerate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

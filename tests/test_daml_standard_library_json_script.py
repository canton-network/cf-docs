from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_dpm_sdk_manifest(
    dpm_home: Path,
    *,
    sdk_version: str,
    damlc_version: str,
    daml_script_version: str,
) -> None:
    manifest_path = dpm_home / "cache/sdk/open-source" / f"{sdk_version}.yaml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        f"""apiVersion: digitalasset.com/v1
kind: SdkManifest
spec:
  components:
    damlc:
      version: {damlc_version}
    daml-script:
      version: {daml_script_version}
  version: {sdk_version}
  edition: open-source
""",
        encoding="utf-8",
    )


def write_daml_script_test_dar(path: Path) -> None:
    import zipfile

    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, source in (
            ("pkg/Daml/Script.daml", "module Daml.Script where\n"),
            ("pkg/Daml/Script/Internal.daml", "module Daml.Script.Internal where\n"),
        ):
            archive.writestr(
                zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)),
                source,
            )


def test_dpm_source_requires_installed_sdk_manifest(tmp_path: Path) -> None:
    dpm_home = tmp_path / "dpm"
    env = os.environ.copy()
    env["DPM_HOME"] = str(dpm_home)

    completed = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/generate_daml_standard_library_json.sh"),
            "--output-json",
            str(tmp_path / "base.json"),
            "--sdk-version",
            "9.9.9",
            "--sdk-source",
            "dpm",
            "--skip-install",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert "No installed DPM SDK manifest found for 9.9.9" in completed.stderr


def test_dpm_source_uses_cached_damlc_binary(tmp_path: Path) -> None:
    sdk_version = "1.2.3"
    lf_target = "2.2"
    dpm_home = tmp_path / "dpm"
    write_dpm_sdk_manifest(
        dpm_home,
        sdk_version=sdk_version,
        damlc_version=sdk_version,
        daml_script_version=sdk_version,
    )
    pkg_db_root = (
        dpm_home
        / "cache/components/damlc"
        / sdk_version
        / "damlc-dist-dpm/resources/pkg-db_dir"
    )
    target_root = pkg_db_root / lf_target
    (target_root / "daml-prim/DA").mkdir(parents=True)
    (target_root / f"daml-stdlib-{sdk_version}/DA").mkdir(parents=True)
    (target_root / "daml-prim/DA/Prim.daml").write_text(
        "module DA.Prim where\n", encoding="utf-8"
    )
    (target_root / f"daml-stdlib-{sdk_version}/DA/List.daml").write_text(
        "module DA.List where\n", encoding="utf-8"
    )

    log_path = tmp_path / "damlc.log"
    damlc_bin = (
        dpm_home / "cache/components/damlc" / sdk_version / "damlc-dist-dpm/damlc"
    )
    damlc_bin.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$0 $*" >> "$FAKE_DAMLC_LOG"
output=""
package=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output="$2"
      shift 2
      ;;
    --package-name)
      package="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
python3 - "$output" "$package" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps([{"md_name": sys.argv[2]}]) + "\\n", encoding="utf-8")
PY
""",
        encoding="utf-8",
    )
    damlc_bin.chmod(0o755)

    path_bin = tmp_path / "bin"
    path_bin.mkdir()
    dpm_bin = path_bin / "dpm"
    dpm_bin.write_text("#!/usr/bin/env bash\nexit 42\n", encoding="utf-8")
    dpm_bin.chmod(0o755)

    output_json = tmp_path / "base.json"
    env = os.environ.copy()
    env.update(
        {
            "DPM_HOME": str(dpm_home),
            "FAKE_DAMLC_LOG": str(log_path),
            "PATH": f"{path_bin}{os.pathsep}{env['PATH']}",
        }
    )

    subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/generate_daml_standard_library_json.sh"),
            "--output-json",
            str(output_json),
            "--sdk-version",
            sdk_version,
            "--lf-target",
            lf_target,
            "--sdk-source",
            "dpm",
            "--skip-install",
        ],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )

    calls = log_path.read_text(encoding="utf-8")
    assert str(damlc_bin) in calls
    assert "dpm damlc" not in calls
    assert json.loads(output_json.read_text(encoding="utf-8")) == [
        {"md_name": "daml-stdlib"},
        {"md_name": "daml-prim"},
    ]


def test_dpm_source_uses_manifest_damlc_component_version(tmp_path: Path) -> None:
    sdk_version = "3.5.3"
    damlc_version = "3.5.2"
    lf_target = "2.3"
    dpm_home = tmp_path / "dpm"
    write_dpm_sdk_manifest(
        dpm_home,
        sdk_version=sdk_version,
        damlc_version=damlc_version,
        daml_script_version=damlc_version,
    )
    pkg_db_root = (
        dpm_home
        / "cache/components/damlc"
        / damlc_version
        / "damlc-dist-dpm/resources/pkg-db_dir"
    )
    target_root = pkg_db_root / lf_target
    (target_root / "daml-prim/DA").mkdir(parents=True)
    (target_root / f"daml-stdlib-{damlc_version}/DA").mkdir(parents=True)
    (target_root / "daml-prim/DA/Prim.daml").write_text(
        "module DA.Prim where\n", encoding="utf-8"
    )
    (target_root / f"daml-stdlib-{damlc_version}/DA/List.daml").write_text(
        "module DA.List where\n",
        encoding="utf-8",
    )

    log_path = tmp_path / "damlc.log"
    damlc_bin = (
        dpm_home / "cache/components/damlc" / damlc_version / "damlc-dist-dpm/damlc"
    )
    damlc_bin.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$0 $*" >> "$FAKE_DAMLC_LOG"
output=""
package=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output="$2"
      shift 2
      ;;
    --package-name)
      package="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
python3 - "$output" "$package" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps([{"md_name": sys.argv[2]}]) + "\\n", encoding="utf-8")
PY
""",
        encoding="utf-8",
    )
    damlc_bin.chmod(0o755)

    output_json = tmp_path / "base.json"
    env = os.environ.copy()
    env.update(
        {
            "DPM_HOME": str(dpm_home),
            "FAKE_DAMLC_LOG": str(log_path),
        }
    )

    subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/generate_daml_standard_library_json.sh"),
            "--output-json",
            str(output_json),
            "--sdk-version",
            sdk_version,
            "--lf-target",
            lf_target,
            "--sdk-source",
            "dpm",
            "--skip-install",
        ],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )

    assert str(damlc_bin) in log_path.read_text(encoding="utf-8")
    assert json.loads(output_json.read_text(encoding="utf-8")) == [
        {"md_name": "daml-stdlib"},
        {"md_name": "daml-prim"},
    ]


def test_daml_script_json_uses_daml_script_dars(tmp_path: Path) -> None:
    sdk_version = "1.2.3"
    lf_target = "2.2"
    dpm_home = tmp_path / "dpm"
    write_dpm_sdk_manifest(
        dpm_home,
        sdk_version=sdk_version,
        damlc_version=sdk_version,
        daml_script_version=sdk_version,
    )
    pkg_db_root = (
        dpm_home
        / "cache/components/damlc"
        / sdk_version
        / "damlc-dist-dpm/resources/pkg-db_dir"
    )
    (pkg_db_root / lf_target).mkdir(parents=True)
    dar_path = (
        dpm_home
        / "cache/components/daml-script"
        / sdk_version
        / f"daml-script-{lf_target}.dar"
    )
    write_daml_script_test_dar(dar_path)

    log_path = tmp_path / "damlc.log"
    damlc_bin = (
        dpm_home / "cache/components/damlc" / sdk_version / "damlc-dist-dpm/damlc"
    )
    damlc_bin.parent.mkdir(parents=True, exist_ok=True)
    damlc_bin.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$0 $*" >> "$FAKE_DAMLC_LOG"
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
python3 - "$output" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        [
            {"md_name": "Daml.Script"},
            {"md_name": "Daml.Script.Internal"},
            {"md_name": "Daml.Script.Internal.Questions"},
        ]
    )
    + "\\n",
    encoding="utf-8",
)
PY
""",
        encoding="utf-8",
    )
    damlc_bin.chmod(0o755)

    output_json = tmp_path / "script.json"
    env = os.environ.copy()
    env.update(
        {
            "DPM_HOME": str(dpm_home),
            "FAKE_DAMLC_LOG": str(log_path),
        }
    )

    subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/generate_daml_script_json.sh"),
            "--output-json",
            str(output_json),
            "--sdk-version",
            sdk_version,
            "--lf-target",
            lf_target,
            "--sdk-source",
            "dpm",
            "--skip-install",
        ],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )

    calls = log_path.read_text(encoding="utf-8")
    assert "--package-name daml-script" in calls
    assert "--package-db" in calls
    assert "Daml/Script.daml" in calls
    assert "Daml/Script/Internal.daml" in calls
    assert "--include-modules" not in calls
    assert json.loads(output_json.read_text(encoding="utf-8")) == [
        {"md_name": "Daml.Script"},
        {"md_name": "Daml.Script.Internal"},
    ]


def test_daml_script_json_uses_manifest_component_versions(tmp_path: Path) -> None:
    sdk_version = "3.5.3"
    damlc_version = "3.5.2"
    daml_script_version = "3.5.1"
    lf_target = "2.3"
    dpm_home = tmp_path / "dpm"
    write_dpm_sdk_manifest(
        dpm_home,
        sdk_version=sdk_version,
        damlc_version=damlc_version,
        daml_script_version=daml_script_version,
    )
    pkg_db_root = (
        dpm_home
        / "cache/components/damlc"
        / damlc_version
        / "damlc-dist-dpm/resources/pkg-db_dir"
    )
    (pkg_db_root / lf_target).mkdir(parents=True)
    dar_path = (
        dpm_home
        / "cache/components/daml-script"
        / daml_script_version
        / f"daml-script-{lf_target}.dar"
    )
    write_daml_script_test_dar(dar_path)

    log_path = tmp_path / "damlc.log"
    damlc_bin = (
        dpm_home / "cache/components/damlc" / damlc_version / "damlc-dist-dpm/damlc"
    )
    damlc_bin.parent.mkdir(parents=True, exist_ok=True)
    damlc_bin.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$0 $*" >> "$FAKE_DAMLC_LOG"
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
python3 - "$output" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps([{"md_name": "Daml.Script"}, {"md_name": "Daml.Script.Internal"}]) + "\\n",
    encoding="utf-8",
)
PY
""",
        encoding="utf-8",
    )
    damlc_bin.chmod(0o755)

    output_json = tmp_path / "script.json"
    env = os.environ.copy()
    env.update(
        {
            "DPM_HOME": str(dpm_home),
            "FAKE_DAMLC_LOG": str(log_path),
        }
    )

    subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/generate_daml_script_json.sh"),
            "--output-json",
            str(output_json),
            "--sdk-version",
            sdk_version,
            "--lf-target",
            lf_target,
            "--sdk-source",
            "dpm",
            "--skip-install",
        ],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )

    calls = log_path.read_text(encoding="utf-8")
    assert str(damlc_bin) in calls
    assert json.loads(output_json.read_text(encoding="utf-8")) == [
        {"md_name": "Daml.Script"},
        {"md_name": "Daml.Script.Internal"},
    ]


def test_base_package_set_merges_shared_prelude_modules(tmp_path: Path) -> None:
    sdk_version = "1.2.3"
    lf_target = "2.2"
    dpm_home = tmp_path / "dpm"
    write_dpm_sdk_manifest(
        dpm_home,
        sdk_version=sdk_version,
        damlc_version=sdk_version,
        daml_script_version=sdk_version,
    )
    pkg_db_root = (
        dpm_home
        / "cache/components/damlc"
        / sdk_version
        / "damlc-dist-dpm/resources/pkg-db_dir"
    )
    target_root = pkg_db_root / lf_target
    (target_root / "daml-prim/DA").mkdir(parents=True)
    (target_root / f"daml-stdlib-{sdk_version}/DA").mkdir(parents=True)
    (target_root / "daml-prim/DA/Prim.daml").write_text(
        "module DA.Prim where\n", encoding="utf-8"
    )
    (target_root / f"daml-stdlib-{sdk_version}/DA/List.daml").write_text(
        "module DA.List where\n", encoding="utf-8"
    )

    damlc_bin = (
        dpm_home / "cache/components/damlc" / sdk_version / "damlc-dist-dpm/damlc"
    )
    damlc_bin.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
output=""
package=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output="$2"
      shift 2
      ;;
    --package-name)
      package="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
python3 - "$output" "$package" <<'PY'
import json
import sys
from pathlib import Path

out, package = sys.argv[1], sys.argv[2]
if package == "daml-stdlib":
    payload = [
        {
            "md_name": "Prelude",
            "md_descr": ["stdlib"],
            "md_adts": [{"ADTDoc": {"ad_name": "Optional"}}],
            "md_classes": [{"cl_name": "Action"}],
        },
        {"md_name": "DA.List", "md_functions": [{"fct_name": "foldl"}]},
    ]
else:
    payload = [
        {
            "md_name": "Prelude",
            "md_adts": [{"ADTDoc": {"ad_name": "Bool"}}],
            "md_classes": [{"cl_name": "Eq"}],
        },
        {
            "md_name": "DA.Exception",
            "md_adts": [{"ADTDoc": {"ad_name": "ArithmeticError"}}],
        },
    ]
Path(out).write_text(json.dumps(payload) + "\\n", encoding="utf-8")
PY
""",
        encoding="utf-8",
    )
    damlc_bin.chmod(0o755)

    output_json = tmp_path / "base.json"
    env = os.environ.copy()
    env["DPM_HOME"] = str(dpm_home)

    subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/generate_daml_standard_library_json.sh"),
            "--output-json",
            str(output_json),
            "--sdk-version",
            sdk_version,
            "--lf-target",
            lf_target,
            "--sdk-source",
            "dpm",
            "--package-set",
            "base",
            "--skip-install",
        ],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )

    by_name = {
        m["md_name"]: m for m in json.loads(output_json.read_text(encoding="utf-8"))
    }
    assert set(by_name) == {"Prelude", "DA.List", "DA.Exception"}
    assert by_name["Prelude"]["md_descr"] == ["stdlib"]
    assert [a["ADTDoc"]["ad_name"] for a in by_name["Prelude"]["md_adts"]] == [
        "Optional",
        "Bool",
    ]
    assert [c["cl_name"] for c in by_name["Prelude"]["md_classes"]] == ["Action", "Eq"]
    assert [a["ADTDoc"]["ad_name"] for a in by_name["DA.Exception"]["md_adts"]] == [
        "ArithmeticError"
    ]

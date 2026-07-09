from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dpm_source_uses_cached_damlc_binary(tmp_path: Path) -> None:
    sdk_version = "1.2.3"
    lf_target = "2.2"
    dpm_home = tmp_path / "dpm"
    pkg_db_root = dpm_home / "cache/components/damlc" / sdk_version / "damlc-dist-dpm/resources/pkg-db_dir"
    target_root = pkg_db_root / lf_target
    (target_root / "daml-prim/DA").mkdir(parents=True)
    (target_root / f"daml-stdlib-{sdk_version}/DA").mkdir(parents=True)
    (target_root / "daml-prim/DA/Prim.daml").write_text("module DA.Prim where\n", encoding="utf-8")
    (target_root / f"daml-stdlib-{sdk_version}/DA/List.daml").write_text("module DA.List where\n", encoding="utf-8")

    log_path = tmp_path / "damlc.log"
    damlc_bin = dpm_home / "cache/components/damlc" / sdk_version / "damlc-dist-dpm/damlc"
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
    assert json.loads(output_json.read_text(encoding="utf-8")) == [{"md_name": "daml-stdlib"}, {"md_name": "daml-prim"}]

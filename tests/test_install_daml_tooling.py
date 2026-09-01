from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_daml_tooling.sh"


def write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_installer_retries_the_complete_install_command(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    attempt_file = tmp_path / "attempts"
    sleep_file = tmp_path / "sleeps"
    write_executable(
        fake_bin / "curl",
        "#!/usr/bin/env bash\nprintf '%s\\n' '# fake installer'\n",
    )
    write_executable(
        fake_bin / "sh",
        """#!/usr/bin/env bash
cat >/dev/null
attempt=0
if [[ -f "$ATTEMPT_FILE" ]]; then
  attempt="$(cat "$ATTEMPT_FILE")"
fi
attempt=$((attempt + 1))
printf '%s\n' "$attempt" > "$ATTEMPT_FILE"
if ((attempt < 3)); then
  exit 35
fi
""",
    )
    write_executable(
        fake_bin / "sleep",
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$1\" >> \"$SLEEP_FILE\"\n",
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "ATTEMPT_FILE": str(attempt_file),
        "SLEEP_FILE": str(sleep_file),
        "DAML_INSTALL_MAX_ATTEMPTS": "3",
        "DAML_INSTALL_RETRY_DELAY_SECONDS": "2",
    }

    result = subprocess.run(
        ["bash", str(INSTALL_SCRIPT)],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0
    assert attempt_file.read_text(encoding="utf-8") == "3\n"
    assert sleep_file.read_text(encoding="utf-8") == "2\n4\n"
    assert "attempt 3/3" in result.stdout

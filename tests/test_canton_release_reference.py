from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import canton_release_reference as release_reference  # noqa: E402


ASSET = release_reference.ReleaseAsset(
    tag="v1.2.3",
    version="1.2.3",
    name="canton-open-source-1.2.3.tar.gz",
    url="https://example.com/canton-open-source-1.2.3.tar.gz",
    size=1,
    digest="sha256:" + "a" * 64,
)


class RunReferenceScriptTests(unittest.TestCase):
    def run_script(self, root: Path, **kwargs: object) -> tuple[object, mock.MagicMock]:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"ok": true}\n'
        )
        with (
            mock.patch.object(
                release_reference.subprocess, "run", return_value=completed
            ) as run,
            mock.patch.dict(release_reference.os.environ, {"CI": "true"}),
        ):
            payload = release_reference.run_reference_script(
                distribution_root=root / "dist",
                script_path=root / "reference.canton",
                cache_dir=root / "cache",
                cache_namespace="example",
                asset=ASSET,
                force_refresh=False,
                **kwargs,  # type: ignore[arg-type]
            )
        return payload, run

    def test_environment_overrides_reach_canton_without_ci(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reference.canton").write_text("println(1)\n", encoding="utf-8")

            payload, run = self.run_script(
                root, environment_overrides={"GENERATE_METRICS_FOR_DOCS": ""}
            )

        self.assertEqual(payload, {"ok": True})
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["GENERATE_METRICS_FOR_DOCS"], "")
        self.assertNotIn("CI", environment)

    def test_environment_overrides_get_their_own_cache_entry(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reference.canton").write_text("println(1)\n", encoding="utf-8")

            self.run_script(root)
            _, cached_run = self.run_script(root)
            _, overridden_run = self.run_script(
                root, environment_overrides={"GENERATE_METRICS_FOR_DOCS": ""}
            )

        cached_run.assert_not_called()
        overridden_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()

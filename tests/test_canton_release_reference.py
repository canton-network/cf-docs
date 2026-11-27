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


class EnsureReleaseArchiveTests(unittest.TestCase):
    class Response:
        def __init__(self, body: bytes, *, content_length: int | None = None) -> None:
            self.body = body
            self.headers = {"Content-Length": str(len(body) if content_length is None else content_length)}
            self.offset = 0

        def __enter__(self) -> "EnsureReleaseArchiveTests.Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, amount: int = -1) -> bytes:
            end = len(self.body) if amount < 0 else self.offset + amount
            chunk = self.body[self.offset : end]
            self.offset += len(chunk)
            return chunk

    def asset_for(self, body: bytes) -> "release_reference.ReleaseAsset":
        import hashlib

        return release_reference.ReleaseAsset(
            tag="v1.2.3",
            version="1.2.3",
            name="canton-open-source-1.2.3.tar.gz",
            url="https://example.com/canton-open-source-1.2.3.tar.gz",
            size=len(body),
            digest="sha256:" + hashlib.sha256(body).hexdigest(),
        )

    def test_truncated_and_reset_downloads_are_retried(self) -> None:
        body = b"x" * 4096
        outcomes: list[object] = [
            ConnectionResetError(104, "Connection reset by peer"),
            self.Response(body[:100], content_length=len(body)),
            self.Response(body),
        ]

        def fake_urlopen(*_args: object, **_kwargs: object) -> object:
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with TemporaryDirectory() as tmp:
            with (
                mock.patch.object(release_reference.urllib.request, "urlopen", fake_urlopen),
                mock.patch.object(release_reference.network_retry.time, "sleep"),
            ):
                path = release_reference.ensure_release_archive(
                    asset=self.asset_for(body), cache_dir=Path(tmp), force_refresh=False
                )
            self.assertEqual(path.read_bytes(), body)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])
        self.assertEqual(outcomes, [])

    def test_corrupt_cached_archive_is_replaced(self) -> None:
        body = b"y" * 2048
        asset = self.asset_for(body)
        with TemporaryDirectory() as tmp:
            cached = Path(tmp) / "release-assets" / asset.tag / asset.name
            cached.parent.mkdir(parents=True)
            cached.write_bytes(body[:10])
            with mock.patch.object(
                release_reference.urllib.request, "urlopen", lambda *_a, **_k: self.Response(body)
            ):
                path = release_reference.ensure_release_archive(
                    asset=asset, cache_dir=Path(tmp), force_refresh=False
                )
            self.assertEqual(path.read_bytes(), body)


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

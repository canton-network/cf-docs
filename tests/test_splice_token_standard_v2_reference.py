from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Self

import pytest

import scripts.generate_splice_token_standard_v2_reference as token_v2_reference

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str) -> ModuleType:
    script_path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_mdx(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\ntitle: "{title}"\n---\n', encoding="utf-8")


def test_source_config_covers_every_token_standard_v2_dar() -> None:
    config = token_v2_reference.load_json(
        REPO_ROOT
        / "config"
        / "x2mdx"
        / "splice-token-standard-v2"
        / "source-artifacts.json"
    )

    assert config["published_dars"] == [
        "splice-api-token-allocation-instruction-v2-1.0.0.dar",
        "splice-api-token-allocation-request-v2-1.0.0.dar",
        "splice-api-token-allocation-v2-1.0.0.dar",
        "splice-api-token-holding-v2-1.0.0.dar",
        "splice-api-token-transfer-events-v2-1.0.0.dar",
        "splice-api-token-transfer-instruction-v2-1.0.0.dar",
    ]
    assert config["supporting_dars"] == ["splice-api-token-metadata-v1-1.0.0.dar"]
    assert config["min_version"] == "0.6.11"
    assert config["package_version"] == "1.0.0"
    assert "publish_version" not in config
    assert "revision" not in config


def test_release_selection_is_unbounded_and_uses_immutable_tag_revisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[object] = [
        [
            {"name": "0.7.0", "commit": {"sha": "sha-070"}},
            {"name": "0.6.11", "commit": {"sha": "sha-0611"}},
            {"name": "0.6.10", "commit": {"sha": "too-old"}},
            {"name": "0.7.1-rc1", "commit": {"sha": "prerelease"}},
        ]
    ]
    monkeypatch.setattr(
        token_v2_reference,
        "github_json",
        lambda _url: payloads.pop(0),
    )

    releases = token_v2_reference.selected_releases(
        source_config={
            "repository": "canton-network/splice",
            "tag_regex": r"^(?P<version>0\.[0-9]+\.[0-9]+)$",
            "min_version": "0.6.11",
        },
        include_versions=None,
    )

    assert releases == [
        token_v2_reference.ReleaseInfo("0.6.11", "0.6.11", "sha-0611"),
        token_v2_reference.ReleaseInfo("0.7.0", "0.7.0", "sha-070"),
    ]
    assert token_v2_reference.resolve_publish_release(
        releases=releases, requested_version=None
    ) == releases[-1]


def test_all_reference_pipeline_merges_v2_nav_after_splice_openapi() -> None:
    aggregate = load_script("generate_all_reference_docs")
    jobs = [job.script_path.name for job in aggregate.SCRIPT_JOBS]
    v2_index = jobs.index("generate_splice_token_standard_v2_reference.py")

    assert jobs.index("generate_splice_mintlify_openapi.py") < v2_index
    assert aggregate.SCRIPT_JOBS[v2_index].nav_slices == (
        aggregate.NavSlice("nested_group", ("Splice APIs", "Splice Daml Packages")),
    )


def test_dar_family_requires_the_configured_package_version() -> None:
    assert (
        token_v2_reference.dar_family(
            "splice-api-token-holding-v2-1.0.0.dar",
            package_version="1.0.0",
        )
        == "splice-api-token-holding-v2"
    )

    with pytest.raises(ValueError, match="must end"):
        token_v2_reference.dar_family(
            "splice-api-token-holding-v2-current.dar",
            package_version="1.0.0",
        )


class FakeDarResponse:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"PK-test-dar"


def test_ensure_dar_retries_transient_download_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcomes: list[object] = [
        urllib.error.URLError("connection reset by peer"),
        urllib.error.HTTPError(
            "https://raw.githubusercontent.test/dar",
            503,
            "Service Unavailable",
            {},
            io.BytesIO(),
        ),
        FakeDarResponse(),
    ]
    sleeps: list[float] = []

    def fake_urlopen(_request: object, *, timeout: float) -> FakeDarResponse:
        assert timeout == 60
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, FakeDarResponse)
        return outcome

    monkeypatch.setattr(token_v2_reference.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(token_v2_reference.time, "sleep", sleeps.append)
    monkeypatch.setattr(token_v2_reference, "DOWNLOAD_RETRY_DELAY_SECONDS", 2)

    output = token_v2_reference.ensure_dar(
        repository="canton-network/splice",
        revision="abc123",
        filename="splice-api-token-holding-v2-1.0.0.dar",
        cache_dir=tmp_path,
        force_refresh=False,
    )

    assert output.read_bytes() == b"PK-test-dar"
    assert sleeps == [2, 4]
    assert outcomes == []


def test_dependency_include_dirs_resolves_token_package_names(tmp_path: Path) -> None:
    metadata = token_v2_reference.PackageInfo(
        family="splice-api-token-metadata-v1",
        package_name="splice-api-token-metadata-v1",
        package_id="splice-api-token-metadata-v1-1.0.0",
        package_root=tmp_path / "metadata",
        exposed_modules=["Splice.Api.Token.MetadataV1"],
        depends=[],
    )
    holding = token_v2_reference.PackageInfo(
        family="splice-api-token-holding-v2",
        package_name="splice-api-token-holding-v2",
        package_id="splice-api-token-holding-v2-1.0.0",
        package_root=tmp_path / "holding",
        exposed_modules=["Splice.Api.Token.HoldingV2"],
        depends=[metadata.package_id],
    )
    transfer = token_v2_reference.PackageInfo(
        family="splice-api-token-transfer-instruction-v2",
        package_name="splice-api-token-transfer-instruction-v2",
        package_id="splice-api-token-transfer-instruction-v2-1.0.0",
        package_root=tmp_path / "transfer",
        exposed_modules=["Splice.Api.Token.TransferInstructionV2"],
        depends=[holding.package_id],
    )

    assert token_v2_reference.dependency_include_dirs(
        info=transfer,
        package_index={
            metadata.package_id: metadata,
            holding.package_id: holding,
            transfer.package_id: transfer,
        },
    ) == [holding.package_root, metadata.package_root]


def test_x2mdx_render_omits_snapshot_and_prioritizes_interfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_json = tmp_path / "docs-main" / "docs.json"
    output_dir = tmp_path / "docs-main" / "reference" / "token-v2"
    manifest = tmp_path / "manifest.json"
    docs_json.parent.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    docs_json.write_text("{}\n", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    (output_dir / "index.mdx").write_text("overview\n", encoding="utf-8")
    commands: list[list[str]] = []

    def capture_command(command: list[str], **_kwargs: object) -> None:
        commands.append(command)

    monkeypatch.setattr(token_v2_reference.subprocess, "run", capture_command)

    token_v2_reference.run_x2mdx(
        manifest_path=manifest,
        output_dir=output_dir,
        publish_version="1.0.0",
        overview_title="token-v2",
        source_name="unit test",
        version_filter="unit test",
        docs_json_path=docs_json,
        history_report_path=tmp_path / "history-report.json",
        lifecycle_metadata_path=tmp_path / "lifecycle.json",
    )

    assert len(commands) == 1
    assert "--omit-module-snapshot" in commands[0]
    assert "--interfaces-first" in commands[0]
    assert "--history-report" in commands[0]
    assert "--lifecycle-metadata" in commands[0]
    assert (output_dir / "index.mdx").exists()


def test_navigation_merge_groups_token_standard_packages_by_version(
    tmp_path: Path,
) -> None:
    docs_json = tmp_path / "docs-main" / "docs.json"
    output_root = (
        tmp_path / "docs-main" / "sdks-tools" / "api-reference" / "splice-daml"
    )
    docs_json.parent.mkdir(parents=True, exist_ok=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "products": [
                        {
                            "product": "API Reference",
                            "pages": [
                                {
                                    "group": "Splice APIs",
                                    "pages": [
                                        {
                                            "group": "Splice Daml Packages",
                                            "pages": [
                                                {
                                                    "group": "splice-api-reward-assignment-v1",
                                                    "pages": ["existing/reward"],
                                                },
                                                {
                                                    "group": "splice-api-token-holding-v1",
                                                    "pages": ["existing/v1"],
                                                },
                                                {
                                                    "group": "splice-dso-governance",
                                                    "pages": ["existing/governance"],
                                                },
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    write_mdx(
        output_root / "splice-api-token-holding-v2" / "splice-api-token-holdingv2.mdx",
        "Splice.Api.Token.HoldingV2",
    )
    write_mdx(
        output_root / "splice-api-token-holding-v2" / "index.mdx",
        "splice-api-token-holding-v2",
    )

    token_v2_reference.update_docs_navigation(
        docs_json_path=docs_json,
        product_label="API Reference",
        parent_groups=["Splice APIs"],
        nav_group_label="Splice Daml Packages",
        output_root=output_root,
        family_order=["splice-api-token-holding-v2"],
    )
    first_render = docs_json.read_text(encoding="utf-8")

    token_v2_reference.update_docs_navigation(
        docs_json_path=docs_json,
        product_label="API Reference",
        parent_groups=["Splice APIs"],
        nav_group_label="Splice Daml Packages",
        output_root=output_root,
        family_order=["splice-api-token-holding-v2"],
    )

    payload = token_v2_reference.load_json(docs_json)
    package_groups = payload["navigation"]["products"][0]["pages"][0]["pages"][0][
        "pages"
    ]
    assert package_groups == [
        {
            "group": "splice-api-reward-assignment-v1",
            "pages": ["existing/reward"],
        },
        {
            "group": "Token Standard v1",
            "pages": [
                {"group": "splice-api-token-holding-v1", "pages": ["existing/v1"]}
            ],
        },
        {
            "group": "Token Standard v2",
            "pages": [
                {
                    "group": "splice-api-token-holding-v2",
                    "pages": [
                        "sdks-tools/api-reference/splice-daml/splice-api-token-holding-v2/index",
                        "sdks-tools/api-reference/splice-daml/splice-api-token-holding-v2/splice-api-token-holdingv2",
                    ],
                }
            ],
        },
        {"group": "splice-dso-governance", "pages": ["existing/governance"]},
    ]
    assert docs_json.read_text(encoding="utf-8") == first_render


def test_generated_packages_publish_standard_overviews_and_module_history() -> None:
    output_root = (
        REPO_ROOT / "docs-main" / "sdks-tools" / "api-reference" / "splice-daml"
    )

    config = token_v2_reference.load_json(
        REPO_ROOT
        / "config"
        / "x2mdx"
        / "splice-token-standard-v2"
        / "source-artifacts.json"
    )
    for dar_filename in config["published_dars"]:
        family = token_v2_reference.dar_family(
            dar_filename, package_version=config["package_version"]
        )
        family_dir = output_root / family
        assert (family_dir / "index.mdx").exists()
        module_pages = [
            page for page in family_dir.glob("*.mdx") if page.name != "index.mdx"
        ]
        assert len(module_pages) == 1
        module_text = module_pages[0].read_text(encoding="utf-8")
        assert "## Module Snapshot" not in module_text
        assert '<Card title="Lifecycle">' not in module_text
        assert '<Card title="Notices">' not in module_text
        assert module_text.index("## Interfaces") < module_text.index("## Data Types")
        assert 'class="x2mdx-ref-page' in module_text
        assert "## History" in module_text

    report = token_v2_reference.load_history_report(
        output_root / "token-standard-v2-history-report.json"
    )
    assert report.surface_id == "splice-token-standard-v2-daml"
    assert report.version_policy.value == "latest_selected_release"
    assert report.publish_version == report.comparison_versions[-1]
    assert len(report.comparison_versions) > 1
    assert len(report.current_items()) == len(config["published_dars"])

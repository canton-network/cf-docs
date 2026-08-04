from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

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
        output_root / "splice-api-token-holding-v2" / "index.mdx",
        "splice-api-token-holding-v2",
    )
    write_mdx(
        output_root / "splice-api-token-holding-v2" / "splice-api-token-holdingv2.mdx",
        "Splice.Api.Token.HoldingV2",
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


def test_generated_overviews_do_not_describe_token_packages_as_the_standard_library() -> (
    None
):
    output_root = (
        REPO_ROOT / "docs-main" / "sdks-tools" / "api-reference" / "splice-daml"
    )

    for index_path in output_root.glob("splice-api-token-*v2/index.mdx"):
        assert "Daml Standard Library" not in index_path.read_text(encoding="utf-8")

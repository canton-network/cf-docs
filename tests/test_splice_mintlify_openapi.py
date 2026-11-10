from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from x2mdx.history import (
    VersionSelectionPolicy,
    load_history_report,
    validate_history_report,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module(script_name: str) -> ModuleType:
    script_path = REPO_ROOT / "scripts" / script_name
    scripts_dir = str(script_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_splice_openapi_release_requests_use_github_token(monkeypatch) -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    assert module.request_headers(
        "https://api.github.com/repos/example/project/releases"
    ) == {
        "Accept": "application/vnd.github+json",
        "User-Agent": module.USER_AGENT,
        "Authorization": "Bearer test-token",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def test_checked_in_splice_history_report_is_valid_and_retains_removed_operations() -> (
    None
):
    report = load_history_report(
        REPO_ROOT / "docs-main" / "openapi" / "splice" / "history-report.json"
    )

    validate_history_report(report)

    assert report.surface_id == "splice-openapi"
    assert report.version_policy == VersionSelectionPolicy.LATEST_SELECTED_RELEASE
    assert report.comparison_versions[0] == "0.5.10"
    assert report.comparison_versions[-1] == report.publish_version
    assert tuple(artifact.version for artifact in report.source_artifacts) == (
        report.comparison_versions
    )
    assert report.current_items()
    assert any(not item.current_present for item in report.items)
    assert all(item.route is not None for item in report.items if not item.current_present)
    assert all(
        (REPO_ROOT / "docs-main" / f"{item.route.removeprefix('/')}.mdx").is_file()
        for item in report.items
        if item.route is not None
    )


def test_splice_openapi_publish_defaults_to_latest_selected_release() -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    releases = [
        {"version": "0.5.10"},
        {"version": "0.6.14"},
        {"version": "0.7.4"},
    ]

    assert module.resolve_publish_release(
        source_config={},
        releases=releases,
        requested_version=None,
    ) == {"version": "0.7.4"}


def test_splice_openapi_publish_allows_explicit_historical_override() -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    releases = [
        {"version": "0.5.10"},
        {"version": "0.6.14"},
        {"version": "0.7.4"},
    ]

    assert module.resolve_publish_release(
        source_config={},
        releases=releases,
        requested_version="0.6.14",
    ) == {"version": "0.6.14"}


def test_splice_openapi_history_window_ends_at_historical_publish_override() -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    releases = [
        {"version": "0.5.10"},
        {"version": "0.6.14"},
        {"version": "0.7.4"},
    ]

    assert module.comparison_releases_through_publish(
        releases=releases,
        publish_version="0.6.14",
    ) == [
        {"version": "0.5.10"},
        {"version": "0.6.14"},
    ]


def test_splice_openapi_rewrites_scan_server_examples(tmp_path: Path) -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    spec_bytes = b"""openapi: 3.0.0
servers:
  - url: https://example.com/api/scan
paths: {}
"""

    rendered_scan = module.render_output_bytes(
        spec_filename="scan.yaml",
        spec_bytes=spec_bytes,
        output_path=tmp_path / "scan.yaml",
    ).decode("utf-8")
    rendered_stream = module.render_output_bytes(
        spec_filename="scan-stream-server.yaml",
        spec_bytes=spec_bytes,
        output_path=tmp_path / "scan-stream-server.yaml",
    ).decode("utf-8")
    rendered_wallet = module.render_output_bytes(
        spec_filename="wallet-external.yaml",
        spec_bytes=spec_bytes,
        output_path=tmp_path / "wallet-external.yaml",
    ).decode("utf-8")

    assert (
        "https://scan.sv-1.global.canton.network.sync.global/api/scan" in rendered_scan
    )
    assert (
        "https://scan.sv-1.global.canton.network.sync.global/api/scan"
        in rendered_stream
    )
    assert "https://example.com/api/scan" not in rendered_scan
    assert "https://example.com/api/scan" not in rendered_stream
    assert "https://example.com/api/scan" in rendered_wallet


def test_splice_openapi_nav_emits_explicit_manual_pages_for_every_spec(
    tmp_path: Path,
) -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    docs_json = tmp_path / "docs-main" / "docs.json"
    write_json(
        docs_json,
        {
            "navigation": {
                "dropdowns": [
                    {
                        "dropdown": "API Reference",
                        "pages": [
                            {"group": "Wallet Kernel", "pages": ["reference/wallet"]}
                        ],
                    }
                ]
            }
        },
    )
    openapi_path = (
        tmp_path / "docs-main" / "openapi" / "splice" / "token-standard" / "token.yaml"
    )
    openapi_path.parent.mkdir(parents=True, exist_ok=True)
    openapi_path.write_text(
        """openapi: 3.0.3
paths:
  /registry/metadata:
    get:
      summary: /registry/metadata
  /registry/metadata/{token-id}:
    parameters: []
    post:
      summary: /registry/metadata/{token-id}
components: {}
""",
        encoding="utf-8",
    )
    source_config = {
        "nav_dropdown": "API Reference",
        "top_level_group_label": "Splice APIs",
        "insert_after_group": "Wallet Kernel",
        "enabled_nav_specs": ["token.yaml"],
        "families": [
            {
                "group": "Scan APIs",
                "specs": [
                    {
                        "filename": "token.yaml",
                        "nav_label": "Scan API",
                        "source": "openapi/splice/token-standard/token.yaml",
                        "directory": "reference/splice-scan-api",
                    }
                ],
            }
        ],
    }

    module.update_docs_navigation(
        docs_json_path=docs_json,
        source_config=source_config,
        families=module.normalized_families(source_config),
    )

    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    api_pages = docs["navigation"]["dropdowns"][0]["pages"]
    splice_group = api_pages[1]
    scan_group = splice_group["pages"][0]
    scan_api = scan_group["pages"][0]
    assert scan_api == {
        "group": "Scan API",
        "pages": [
            "reference/splice-scan-api/get-registrymetadata",
            "reference/splice-scan-api/post-registrymetadata:token-id",
        ],
    }


def test_splice_manual_pages_rely_on_mintlify_navigation_breadcrumbs(
    tmp_path: Path,
) -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://scan.example.com/api/scan"}],
        "paths": {
            "/v0/scans": {
                "get": {
                    "summary": "List scans",
                    "operationId": "listScans",
                    "responses": {"200": {"description": "Success"}},
                }
            }
        },
    }
    docs_json = tmp_path / "docs-main" / "docs.json"

    families = [
        {
            "group": "Scan APIs",
            "specs": [
                {
                    "filename": "scan.yaml",
                    "nav_label": "Scan API",
                    "source": "openapi/splice/scan/scan.yaml",
                    "directory": "reference/splice-scan-api",
                }
            ],
        }
    ]
    snapshots = {"scan.yaml": {"0.7.4": spec}}
    releases = [
        {
            "version": "0.7.4",
            "tag": "v0.7.4",
            "asset_name": "0.7.4_openapi.tar.gz",
            "download_url": "https://example.com/0.7.4_openapi.tar.gz",
        }
    ]
    history_report = module.build_splice_history_report(
        source_config={},
        families=families,
        snapshots=snapshots,
        releases=releases,
        publish_version="0.7.4",
    )

    written = module.write_manual_operation_pages(
        docs_json_path=docs_json,
        families=families,
        snapshots=snapshots,
        publish_version="0.7.4",
        history_report=history_report,
    )

    assert len(written) == 1
    rendered = next(iter(written)).read_text(encoding="utf-8")
    assert "x2mdx-ref-breadcrumbs" not in rendered
    assert 'title: "GET /v0/scans"' in rendered
    assert 'api: "GET https://scan.example.com/api/scan/v0/scans"' in rendered
    assert '<span class="x2mdx-ref-meta-label">Operation ID</span>' not in rendered


def test_splice_openapi_normalizes_path_summaries_for_mintlify_operation_slugs(
    tmp_path: Path,
) -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    source = b"""openapi: 3.0.3
paths:
  /registry/metadata:
    get:
      summary: /registry/metadata
  /registry/metadata/{token-id}:
    post:
      summary: /registry/metadata/{token-id}
  /registry/descriptive:
    get:
      summary: Descriptive operation label
  /registry/missing/{token-id}:
    get:
      operationId: getMissing
components: {}
"""

    rendered = module.render_output_bytes(
        spec_filename="token.yaml",
        spec_bytes=source,
        output_path=tmp_path / "token.yaml",
    ).decode("utf-8")

    assert '      summary: "GET /registry/metadata"' in rendered
    assert '      summary: "POST /registry/metadata/:token-id"' in rendered
    assert "      summary: Descriptive operation label" in rendered
    assert '      summary: "GET /registry/missing/:token-id"' in rendered


def test_splice_openapi_validator_rejects_mintlify_operation_slug_collisions(
    tmp_path: Path,
) -> None:
    module = load_script_module("validate_splice_mintlify_openapi_nav.py")
    openapi_path = (
        tmp_path / "docs-main" / "openapi" / "splice" / "token-standard" / "token.yaml"
    )
    openapi_path.parent.mkdir(parents=True, exist_ok=True)
    openapi_path.write_text(
        """openapi: 3.0.3
paths:
  /registry/metadata:
    get:
      summary: /registry/metadata
  /registry/metadata/{token-id}:
    post:
      summary: /registry/metadata/{token-id}
components: {}
""",
        encoding="utf-8",
    )

    try:
        module.validate_openapi_operation_slug_uniqueness(
            docs_json_path=tmp_path / "docs-main" / "docs.json",
            entries=[
                ("openapi/splice/token-standard/token.yaml", "reference/splice-token")
            ],
        )
    except ValueError as error:
        assert "collide under Mintlify operation slugging" in str(error)
        assert "GET /registry/metadata" in str(error)
        assert "POST /registry/metadata/{token-id}" in str(error)
    else:
        raise AssertionError("Expected Mintlify slug collision validation to fail")


def test_splice_openapi_nav_updates_product_navigation_and_preserves_existing_pages(
    tmp_path: Path,
) -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    docs_json = tmp_path / "docs-main" / "docs.json"
    write_json(
        docs_json,
        {
            "navigation": {
                "products": [
                    {
                        "product": "API Reference",
                        "pages": [
                            "api-reference",
                            {"group": "Wallet Gateway", "pages": ["reference/wallet"]},
                            {
                                "group": "Splice APIs",
                                "pages": [
                                    "sdks-tools/api-reference/splice-daml-apis",
                                    {
                                        "group": "Scan APIs",
                                        "pages": ["stale-scan-entry"],
                                    },
                                ],
                            },
                        ],
                    }
                ]
            }
        },
    )
    openapi_path = tmp_path / "docs-main" / "openapi" / "splice" / "scan" / "scan.yaml"
    openapi_path.parent.mkdir(parents=True, exist_ok=True)
    openapi_path.write_text(
        """openapi: 3.0.3
paths:
  /v0/scans:
    get:
      summary: /v0/scans
components: {}
""",
        encoding="utf-8",
    )
    source_config = {
        "nav_dropdown": "API Reference",
        "top_level_group_label": "Splice APIs",
        "insert_after_group": "Wallet Gateway",
        "enabled_nav_specs": ["scan.yaml"],
        "families": [
            {
                "group": "Scan APIs",
                "specs": [
                    {
                        "filename": "scan.yaml",
                        "nav_label": "Scan API",
                        "source": "openapi/splice/scan/scan.yaml",
                        "directory": "reference/splice-scan-api",
                    }
                ],
            }
        ],
    }

    module.update_docs_navigation(
        docs_json_path=docs_json,
        source_config=source_config,
        families=module.normalized_families(source_config),
    )

    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    api_pages = docs["navigation"]["products"][0]["pages"]
    splice_group = api_pages[2]
    assert splice_group["group"] == "Splice APIs"
    assert splice_group["pages"][0] == "sdks-tools/api-reference/splice-daml-apis"
    assert splice_group["pages"][1]["group"] == "Scan APIs"
    assert splice_group["pages"][1]["pages"][0]["pages"] == [
        "reference/splice-scan-api/get-v0scans"
    ]


def test_splice_openapi_exclusions_must_cover_disabled_specs() -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    source_config = {
        "enabled_nav_specs": ["public.yaml"],
        "excluded_specs": [{"filename": "internal.yaml", "reason": "Internal API."}],
        "families": [
            {
                "group": "APIs",
                "specs": [
                    {
                        "filename": "public.yaml",
                        "nav_label": "Public",
                        "source": "openapi/public.yaml",
                        "directory": "reference/public",
                    },
                    {
                        "filename": "internal.yaml",
                        "nav_label": "Internal",
                        "source": "openapi/internal.yaml",
                        "directory": "reference/internal",
                    },
                ],
            }
        ],
    }

    module.validate_excluded_specs(
        source_config=source_config,
        families=module.normalized_families(source_config),
        enabled_specs=module.enabled_nav_specs(source_config),
    )


def test_removed_navigation_uses_custom_history_report(tmp_path: Path) -> None:
    module = load_script_module("validate_splice_mintlify_openapi_nav.py")
    report_path = REPO_ROOT / "docs-main/openapi/splice/history-report.json"
    custom_path = tmp_path / "custom-history.json"
    custom_path.write_bytes(report_path.read_bytes())
    report = load_history_report(custom_path)
    removed = next(item for item in report.items if not item.current_present)
    filename = removed.id.split("::", 1)[0]
    pages = module.removed_operation_page_refs(tmp_path, filename, history_report_path=custom_path)
    assert removed.route.lstrip("/") in pages


def _derived_source_config() -> dict[str, object]:
    return {
        "enabled_nav_specs": ["scan-proxy.yaml", "scan-proxy-token-metadata-v1.yaml"],
        "excluded_specs": [
            {"filename": "token-metadata-v1.yaml", "reason": "Only the proxied copy is enabled here."}
        ],
        "families": [
            {
                "group": "Validator APIs",
                "specs": [
                    {
                        "filename": "scan-proxy.yaml",
                        "nav_label": "Scan Proxy API",
                        "source": "openapi/splice/validator/scan-proxy.yaml",
                        "directory": "reference/splice-scan-proxy-api",
                    },
                    {
                        "filename": "scan-proxy-token-metadata-v1.yaml",
                        "nav_label": "Scan Proxy Token Metadata Service",
                        "source": "openapi/splice/validator/scan-proxy-token-metadata-v1.yaml",
                        "directory": "reference/splice-scan-proxy-token-metadata-service",
                        "derived_from": {
                            "filename": "token-metadata-v1.yaml",
                            "path_prefix": "/v0/scan-proxy",
                            "server_url": "https://example.com/api/validator",
                        },
                    },
                ],
            },
            {
                "group": "Token Standard APIs",
                "specs": [
                    {
                        "filename": "token-metadata-v1.yaml",
                        "nav_label": "Token Metadata Service",
                        "source": "openapi/splice/token-standard/token-metadata-v1.yaml",
                        "directory": "reference/splice-token-metadata-service",
                    }
                ],
            },
        ],
    }


_TOKEN_METADATA_SPEC = """openapi: 3.0.0
info:
  title: token metadata service
  description: |
    Implemented by token registries.
  version: 1.2.0
paths:
  /registry/metadata/v1/info:
    get:
      operationId: getRegistryInfo
      summary: Registry info
      responses:
        "200":
          description: ok
  /registry/metadata/v1/instruments/{instrumentId}:
    get:
      operationId: getInstrument
      summary: Instrument
      responses:
        "200":
          description: ok
components:
  schemas:
    ErrorResponse:
      type: object
"""


def test_derived_spec_prefixes_paths_and_remounts_on_validator_server() -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    families = module.normalized_families(_derived_source_config())
    derived = module.derived_spec_configs(families)
    assert list(derived) == ["scan-proxy-token-metadata-v1.yaml"]

    import yaml

    base = yaml.safe_load(_TOKEN_METADATA_SPEC)
    payload = module.derive_spec_payload(
        base_spec=base, spec_config=derived["scan-proxy-token-metadata-v1.yaml"]
    )

    assert list(payload) == ["openapi", "info", "servers", "paths", "components"]
    assert payload["servers"] == [{"url": "https://example.com/api/validator"}]
    assert payload["info"]["title"] == "token metadata service (validator scan proxy)"
    assert payload["info"]["version"] == "1.2.0"
    assert payload["info"]["description"].startswith("Implemented by token registries.\n\n")
    assert "`/api/validator/v0/scan-proxy`" in payload["info"]["description"]
    assert "`token-metadata-v1.yaml`" in payload["info"]["description"]
    assert list(payload["paths"]) == [
        "/v0/scan-proxy/registry/metadata/v1/info",
        "/v0/scan-proxy/registry/metadata/v1/instruments/{instrumentId}",
    ]
    assert payload["paths"]["/v0/scan-proxy/registry/metadata/v1/info"]["get"]["operationId"] == "getRegistryInfo"
    assert payload["components"] == base["components"]
    # The base document is not mutated.
    assert list(base["paths"]) == [
        "/registry/metadata/v1/info",
        "/registry/metadata/v1/instruments/{instrumentId}",
    ]

    dumped = module.dump_openapi_yaml(payload).decode("utf-8")
    assert "  description: |-\n    Implemented by token registries.\n" in dumped
    assert module.manual_operation_page_refs(
        spec=payload, directory="reference/splice-scan-proxy-token-metadata-service"
    ) == [
        "reference/splice-scan-proxy-token-metadata-service/get-v0scan-proxyregistrymetadatav1info",
        "reference/splice-scan-proxy-token-metadata-service/get-v0scan-proxyregistrymetadatav1instruments:instrumentid",
    ]


def test_derived_spec_bytes_are_built_from_archive_specs() -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    families = module.normalized_families(_derived_source_config())
    derived = module.derived_spec_configs(families)

    produced = module.derived_spec_bytes(
        derived_specs=derived,
        spec_bytes={"token-metadata-v1.yaml": _TOKEN_METADATA_SPEC.encode("utf-8")},
    )

    assert list(produced) == ["scan-proxy-token-metadata-v1.yaml"]
    text = produced["scan-proxy-token-metadata-v1.yaml"].decode("utf-8")
    assert "/v0/scan-proxy/registry/metadata/v1/info:" in text
    assert "url: https://example.com/api/validator" in text


def test_derived_specs_require_a_configured_non_derived_base() -> None:
    import pytest

    module = load_script_module("generate_splice_mintlify_openapi.py")

    missing_base = _derived_source_config()
    missing_base["families"] = missing_base["families"][:1]
    with pytest.raises(ValueError, match="not a configured spec"):
        module.normalized_families(missing_base)

    chained = _derived_source_config()
    chained["families"][1]["specs"][0]["derived_from"] = {
        "filename": "scan-proxy.yaml",
        "path_prefix": "/v0/scan-proxy",
        "server_url": "https://example.com/api/validator",
    }
    with pytest.raises(ValueError, match="itself derived"):
        module.normalized_families(chained)

    bad_prefix = _derived_source_config()
    bad_prefix["families"][0]["specs"][1]["derived_from"]["path_prefix"] = "v0/scan-proxy/"
    with pytest.raises(ValueError, match="path_prefix"):
        module.normalized_families(bad_prefix)


def test_materialize_release_specs_synthesizes_derived_snapshots(tmp_path: Path, monkeypatch) -> None:
    import io
    import tarfile

    module = load_script_module("generate_splice_mintlify_openapi.py")
    families = module.normalized_families(_derived_source_config())
    derived = module.derived_spec_configs(families)

    archive = tmp_path / "0.9.1_openapi.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for name, text in {
            "token-standard/openapi/token-metadata-v1.yaml": _TOKEN_METADATA_SPEC,
            "validator/openapi/scan-proxy.yaml": "openapi: 3.0.0\ninfo:\n  title: Validator API\npaths:\n  /v0/scan-proxy/dso:\n    get:\n      operationId: getDso\n      summary: Dso\n      responses:\n        '200':\n          description: ok\n",
        }.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            handle.addfile(info, io.BytesIO(data))
    monkeypatch.setattr(module, "ensure_archive", lambda **_kwargs: archive)

    release = {"version": "0.9.1", "tag": "v0.9.1", "asset_name": archive.name, "download_url": "https://example.invalid"}
    parsed = module.materialize_release_specs(
        cache_dir=tmp_path / "cache",
        release=release,
        spec_filenames={"scan-proxy.yaml", "scan-proxy-token-metadata-v1.yaml"},
        force_refresh=False,
        derived_specs=derived,
    )

    assert sorted(parsed) == ["scan-proxy-token-metadata-v1.yaml", "scan-proxy.yaml"]
    assert list(parsed["scan-proxy-token-metadata-v1.yaml"]["paths"]) == [
        "/v0/scan-proxy/registry/metadata/v1/info",
        "/v0/scan-proxy/registry/metadata/v1/instruments/{instrumentId}",
    ]
    assert (tmp_path / "cache" / "fixtures" / "0.9.1" / "scan-proxy-token-metadata-v1.yaml").exists()

    # A release that predates the base spec yields no derived snapshot either.
    older = tmp_path / "0.5.10_openapi.tar.gz"
    with tarfile.open(older, "w:gz") as handle:
        data = b"openapi: 3.0.0\ninfo:\n  title: Validator API\npaths: {}\n"
        info = tarfile.TarInfo("validator/openapi/scan-proxy.yaml")
        info.size = len(data)
        handle.addfile(info, io.BytesIO(data))
    monkeypatch.setattr(module, "ensure_archive", lambda **_kwargs: older)
    parsed_older = module.materialize_release_specs(
        cache_dir=tmp_path / "cache",
        release={**release, "version": "0.5.10", "tag": "v0.5.10"},
        spec_filenames={"scan-proxy.yaml", "scan-proxy-token-metadata-v1.yaml"},
        force_refresh=False,
        derived_specs=derived,
    )
    assert sorted(parsed_older) == ["scan-proxy.yaml"]


def test_checked_in_source_config_derives_every_token_standard_spec_for_scan_proxy() -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    source_config = module.load_json(module.DEFAULT_SOURCE_CONFIG)
    families = module.normalized_families(source_config)
    derived = module.derived_spec_configs(families)
    token_standard = {
        spec["filename"]
        for family in families
        if family["group"] == "Token Standard APIs"
        for spec in family["specs"]
    }

    assert {spec["derived_from"]["filename"] for spec in derived.values()} == token_standard
    assert all(filename.startswith("scan-proxy-") for filename in derived)
    assert set(derived) <= set(source_config["enabled_nav_specs"])
    validator_specs = [
        spec["filename"]
        for family in families
        if family["group"] == "Validator APIs"
        for spec in family["specs"]
    ]
    assert validator_specs.index("scan-proxy.yaml") < min(
        validator_specs.index(filename) for filename in derived
    )
    for spec in derived.values():
        assert spec["derived_from"]["path_prefix"] == "/v0/scan-proxy"
        assert spec["derived_from"]["server_url"] == "https://example.com/api/validator"
        assert spec["directory"].startswith("reference/splice-scan-proxy-")

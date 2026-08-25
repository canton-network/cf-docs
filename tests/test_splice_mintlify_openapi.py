from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType


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

    written = module.write_manual_operation_pages(
        docs_json_path=docs_json,
        families=[
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
        snapshots={"scan.yaml": {"0.7.4": spec}},
        release_versions=["0.7.4"],
        publish_version="0.7.4",
        source_name="test fixtures",
    )

    assert len(written) == 1
    rendered = next(iter(written)).read_text(encoding="utf-8")
    assert "x2mdx-ref-breadcrumbs" not in rendered
    assert '<span class="x2mdx-ref-meta-label">Operation ID</span>' in rendered


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


def test_splice_openapi_route_baseline_covers_manual_reader_routes() -> None:
    module = load_script_module("generate_splice_mintlify_openapi.py")
    spec = {
        "openapi": "3.0.3",
        "paths": {
            "/v0/items/{item_id}": {"get": {"operationId": "getItem", "responses": {}}}
        },
    }
    route = "/reference/splice-items/get-v0items:item_id\n"
    module.validate_manual_route_baseline(
        {
            "legacy_manual_route_baseline": {
                "operation_count": 1,
                "sha256": hashlib.sha256(route.encode("utf-8")).hexdigest(),
            }
        },
        families=[
            {
                "group": "APIs",
                "specs": [
                    {
                        "filename": "items.yaml",
                        "directory": "reference/splice-items",
                    }
                ],
            }
        ],
        snapshots={"items.yaml": {"0.7.4": spec}},
        publish_version="0.7.4",
    )

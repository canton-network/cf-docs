from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from x2mdx.render import render_page


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


def test_add_missing_operation_summaries_uses_method_path_labels_for_mintlify_nav() -> None:
    module = load_script_module("generate_json_api_reference.py")
    source = """  openapi: 3.0.3
  paths:
    /v2/commands/submit-and-wait:
      post:
        description: Submit and wait.
        operationId: postV2CommandsSubmit-and-wait
    /v2/version:
      get:
        summary: Existing summary
        description: Read the version.
        operationId: getV2Version
  components: {}
"""

    rendered = module.add_missing_operation_summaries(source)

    assert '        summary: "POST /v2/commands/submit-and-wait"' in rendered
    assert "summary: Existing summary" in rendered
    assert "summary: \"/v2/commands/submit-and-wait\"" not in rendered
    assert module.missing_operation_summaries(module.yaml.safe_load(rendered)) == set()


def test_add_missing_operation_summaries_disambiguates_methods_on_same_path() -> None:
    module = load_script_module("generate_json_api_reference.py")
    source = """openapi: 3.0.3
paths:
  /v2/users/{user-id}:
    get:
      description: Get user.
      operationId: getV2UsersUser-id
    delete:
      description: Delete user.
      operationId: deleteV2UsersUser-id
    patch:
      description: Update user.
      operationId: patchV2UsersUser-id
components: {}
"""

    rendered = module.add_missing_operation_summaries(source)
    spec = module.yaml.safe_load(rendered)
    operations = spec["paths"]["/v2/users/{user-id}"]

    assert operations["get"]["summary"] == "GET /v2/users/:user-id"
    assert operations["delete"]["summary"] == "DELETE /v2/users/:user-id"
    assert operations["patch"]["summary"] == "PATCH /v2/users/:user-id"


def test_add_missing_operation_summaries_preserves_specs_that_already_have_summaries() -> None:
    module = load_script_module("generate_json_api_reference.py")
    source = """openapi: 3.0.3
paths:
  /v2/version:
    get:
      summary: /v2/version
      description: Read the version.
      operationId: getV2Version
components: {}
"""

    assert module.add_missing_operation_summaries(source) == source


def test_openapi_operation_page_refs_lists_endpoint_refs_in_source_order() -> None:
    module = load_script_module("generate_json_api_reference.py")
    spec = {
        "paths": {
            "/v2/packages": {
                "get": {"summary": "/v2/packages"},
                "post": {"summary": "/v2/packages"},
                "parameters": [],
            },
            "/v2/version": {
                "get": {"summary": "/v2/version"},
            },
        }
    }

    assert module.openapi_operation_page_refs(spec) == [
        "GET /v2/packages",
        "POST /v2/packages",
        "GET /v2/version",
    ]


def test_update_docs_navigation_supports_product_navigation(tmp_path: Path) -> None:
    module = load_script_module("generate_json_api_reference.py")
    docs_json = tmp_path / "docs.json"
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "products": [
                        {
                            "product": "API Reference",
                            "pages": [
                                "api-reference",
                                {
                                    "group": "Ledger API",
                                    "pages": [
                                        {
                                            "group": "OpenAPI",
                                            "openapi": {
                                                "source": "stale.yaml",
                                                "directory": "stale-directory",
                                            },
                                            "pages": ["stale-page"],
                                        },
                                        {"group": "AsyncAPI", "pages": ["reference/asyncapi"]},
                                    ],
                                },
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    module.update_docs_navigation(
        docs_json_path=docs_json,
        dropdown_label="API Reference",
        parent_group_label="Ledger API",
        group_label="OpenAPI",
        openapi_source_ref="openapi/json-ledger-api/openapi.yaml",
        openapi_directory="reference/json-api-reference",
        details_page_ref="reference/json-api-reference/details",
        openapi_page_refs=["GET /v2/users", "POST /v2/users"],
    )

    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    ledger_pages = docs["navigation"]["products"][0]["pages"][1]["pages"]

    assert ledger_pages == [
        {
            "group": "OpenAPI",
            "openapi": {
                "source": "openapi/json-ledger-api/openapi.yaml",
                "directory": "reference/json-api-reference",
            },
            "pages": ["GET /v2/users", "POST /v2/users", "reference/json-api-reference/details"],
        },
        {"group": "AsyncAPI", "pages": ["reference/asyncapi"]},
    ]


def test_operation_summary_uses_descriptions_for_generated_method_path_summaries() -> None:
    module = load_script_module("generate_json_api_reference.py")
    path_item = {
        "get": {
            "summary": "GET /v2/users/:user-id",
            "description": "Get user.",
        },
        "patch": {
            "summary": "PATCH /v2/users/:user-id",
            "description": "Update user.",
        },
    }

    assert module.operation_summary("/v2/users/{user-id}", path_item) == "GET: Get user.; PATCH: Update user."


def test_build_openapi_details_page_uses_reference_overview_layout() -> None:
    module = load_script_module("generate_json_api_reference.py")
    specs = {
        "3.4": {
            "paths": {
                "/v2/version": {
                    "get": {
                        "summary": "/v2/version",
                        "description": "Read the version.",
                    }
                }
            }
        },
        "3.5": {
            "paths": {
                "/v2/version": {
                    "get": {
                        "summary": "/v2/version",
                        "description": "Read the Ledger API version.",
                    }
                },
                "/readyz": {
                    "get": {
                        "summary": "/readyz",
                        "description": "Check readiness.",
                    }
                },
            }
        },
    }

    rendered = render_page(
        module.build_openapi_details_page(
            specs_by_version=specs,
            versions=["3.4", "3.5"],
            publish_version="3.5",
            details_page_ref="reference/json-api-reference/details",
            source_name="unit test OpenAPI fixtures",
        )
    )

    assert '<div class="x2mdx-ref-hero">' in rendered
    assert '<p class="x2mdx-ref-eyebrow">OpenAPI Reference</p>' in rendered
    assert '<a class="x2mdx-ref-card"' not in rendered
    assert '<div class="x2mdx-ref-card x2mdx-ref-card--static">' in rendered
    assert "Changed 3.5" in rendered
    assert "## Endpoint Reference (Latest)" not in rendered


def test_enrich_mintlify_operation_history_writes_visible_endpoint_notes(tmp_path: Path) -> None:
    module = load_script_module("generate_json_api_reference.py")
    openapi_path = tmp_path / "openapi.yaml"
    openapi_path.write_text(
        """openapi: 3.0.3
paths:
  /livez:
    get:
      summary: GET /livez
      operationId: getLivez
      responses:
        '200':
          description: OK
  /v2/version:
    get:
      summary: GET /v2/version
      description: Current version.
      operationId: getV2Version
      responses:
        '200':
          description: OK
components: {}
""",
        encoding="utf-8",
    )
    specs = {
        "3.4": {
            "paths": {
                "/v2/version": {
                    "get": {
                        "summary": "GET /v2/version",
                        "description": "Old version.",
                        "operationId": "getV2Version",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            }
        },
        "3.5": {
            "paths": {
                "/livez": {
                    "get": {
                        "summary": "GET /livez",
                        "operationId": "getLivez",
                        "responses": {"200": {"description": "OK"}},
                    }
                },
                "/v2/version": {
                    "get": {
                        "summary": "GET /v2/version",
                        "description": "Current version.",
                        "operationId": "getV2Version",
                        "responses": {"200": {"description": "OK"}},
                    }
                },
            }
        },
    }

    module.enrich_mintlify_operation_history(
        openapi_path=openapi_path,
        specs_by_version=specs,
        versions=["3.4", "3.5"],
    )

    rendered = openapi_path.read_text(encoding="utf-8")
    assert "**Endpoint history**: Added in 3.5." in rendered
    assert "**Endpoint history**: Added in 3.4. Modified in 3.5: description updated." in rendered
    assert rendered.count("x-mint:") == 2

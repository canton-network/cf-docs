from __future__ import annotations

import importlib.util
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
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


def versioned_specs() -> dict[str, dict]:
    return {
        "1.0": {
            "openapi": "3.0.3",
            "paths": {
                "/unchanged": {
                    "get": {
                        "summary": "GET /unchanged",
                        "description": "Same endpoint.",
                        "operationId": "getUnchanged",
                        "responses": {"200": {"description": "OK"}},
                    }
                },
                "/modified": {
                    "post": {
                        "summary": "POST /modified",
                        "description": "Old description.",
                        "operationId": "postModified",
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/Request"}}
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {"schema": {"$ref": "#/components/schemas/Response"}}
                                },
                            },
                            "400": {"description": "Old error."},
                        },
                    }
                },
                "/deprecated": {
                    "get": {
                        "summary": "GET /deprecated",
                        "operationId": "getDeprecated",
                        "responses": {"200": {"description": "OK"}},
                    }
                },
                "/removed": {
                    "delete": {
                        "summary": "DELETE /removed",
                        "operationId": "deleteRemoved",
                        "responses": {"204": {"description": "Removed."}},
                    }
                },
            },
            "components": {
                "schemas": {
                    "Request": {"type": "object", "properties": {"id": {"type": "string"}}},
                    "Response": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                }
            },
        },
        "2.0": {
            "openapi": "3.0.3",
            "paths": {
                "/unchanged": {
                    "get": {
                        "summary": "GET /unchanged",
                        "description": "Same endpoint.",
                        "operationId": "getUnchanged",
                        "responses": {"200": {"description": "OK"}},
                    }
                },
                "/modified": {
                    "post": {
                        "summary": "POST /modified",
                        "description": "New description.",
                        "operationId": "postModified",
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/Request"}}
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {"schema": {"$ref": "#/components/schemas/Response"}}
                                },
                            },
                            "400": {"description": "New error."},
                        },
                    }
                },
                "/deprecated": {
                    "get": {
                        "summary": "GET /deprecated",
                        "operationId": "getDeprecated",
                        "deprecated": True,
                        "responses": {"200": {"description": "OK"}},
                    }
                },
                "/added": {
                    "get": {
                        "summary": "GET /added",
                        "operationId": "getAdded",
                        "responses": {"200": {"description": "OK"}},
                    }
                },
            },
            "components": {
                "schemas": {
                    "Request": {"type": "object", "properties": {"id": {"type": "integer"}}},
                    "Response": {"type": "object", "properties": {"ok": {"type": "string"}}},
                }
            },
        },
    }


def test_operation_histories_track_added_modified_deprecated_and_removed() -> None:
    module = load_script_module("openapi_history.py")

    histories = module.build_operation_histories(versioned_specs(), ["1.0", "2.0"])

    assert histories["GET /added"].added_version == "2.0"
    assert histories["DELETE /removed"].removed_version == "2.0"
    assert histories["GET /deprecated"].deprecated is True

    modified = histories["POST /modified"].changed_versions[0]
    assert modified.version == "2.0"
    assert "description updated" in modified.changes
    assert "request body schema changed" in modified.changes
    assert "response `200` schema changed" in modified.changes
    assert "response `400` description updated" in modified.changes


def test_enrich_openapi_text_uses_visible_x_mint_content_without_tombstones() -> None:
    module = load_script_module("openapi_history.py")
    histories = module.build_operation_histories(versioned_specs(), ["1.0", "2.0"])
    latest_text = """openapi: 3.0.3
paths:
  /unchanged:
    get:
      summary: GET /unchanged
      operationId: getUnchanged
  /modified:
    post:
      summary: POST /modified
      operationId: postModified
  /deprecated:
    get:
      summary: GET /deprecated
      operationId: getDeprecated
      deprecated: true
  /added:
    get:
      summary: GET /added
      operationId: getAdded
components: {}
"""

    enriched = module.enrich_openapi_text_with_history(latest_text, histories, first_version="1.0")

    assert "**Endpoint history**: Added in 2.0." in enriched
    assert "Modified in 2.0: description updated; request body schema changed" in enriched
    assert "Currently deprecated." in enriched
    assert "DELETE /removed" not in enriched
    assert enriched.count("x-mint:") == 3

    assert module.enrich_openapi_text_with_history(enriched, histories, first_version="1.0") == enriched


def test_history_note_omits_unchanged_first_version_operations() -> None:
    module = load_script_module("openapi_history.py")
    histories = module.build_operation_histories(versioned_specs(), ["1.0", "2.0"])

    assert module.history_note(histories["GET /unchanged"], "1.0") is None

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
    spec.loader.exec_module(module)
    return module


def test_add_missing_operation_summaries_uses_path_only_labels_for_mintlify_nav() -> None:
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

    assert '        summary: "/v2/commands/submit-and-wait"' in rendered
    assert "summary: Existing summary" in rendered
    assert "summary: \"POST /v2/commands/submit-and-wait\"" not in rendered
    assert module.missing_operation_summaries(module.yaml.safe_load(rendered)) == set()


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

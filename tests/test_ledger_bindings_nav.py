from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_mdx(path: Path, title: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\ntitle: "{title}"\n---\n{body}', encoding="utf-8")


def test_java_bindings_nav_includes_details_and_history_page(tmp_path: Path) -> None:
    generate_ledger_bindings_api_reference = load_script("generate_ledger_bindings_api_reference")
    reference_nav = load_script("reference_nav")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "dropdowns": [
                        {
                            "dropdown": "API Reference",
                            "pages": [
                                {"group": "Ledger API", "pages": [{"group": "OpenAPI", "pages": []}]},
                                {"group": "Splice APIs", "pages": []},
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    publish_root = docs_json.parent / "reference"
    overview_file = publish_root / "java-bindings.mdx"
    write_mdx(overview_file, "Details and history")
    write_mdx(publish_root / "java" / "index.mdx", "Javadocs")
    write_mdx(
        publish_root / "java" / "com-example" / "index.mdx",
        "com.example",
        "## Package `com.example`\n",
    )
    write_mdx(publish_root / "java" / "com-example" / "Client.mdx", "Client")

    generate_ledger_bindings_api_reference.update_docs_navigation(
        docs_json_path=docs_json,
        dropdown_label="API Reference",
        parent_groups=[],
        group_label="Java Bindings",
        overview_file=overview_file,
        publish_root=publish_root,
    )
    reference_nav.regroup_ledger_api_nav(docs_json_path=docs_json, dropdown_label="API Reference")

    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    ledger_pages = docs["navigation"]["dropdowns"][0]["pages"][0]["pages"]
    assert ledger_pages[-1] == {
        "group": "Java Bindings",
        "pages": [
            "reference/java-bindings",
            {
                "group": "Javadocs",
                "pages": [{"group": "com.example", "pages": ["reference/java/com-example/Client"]}],
            },
        ],
    }


def test_java_bindings_overview_is_published_as_details_and_history() -> None:
    generate_ledger_bindings_api_reference = load_script("generate_ledger_bindings_api_reference")

    assert (
        generate_ledger_bindings_api_reference.rewrite_overview_as_details_page(
            '---\ntitle: "Java Bindings"\ndescription: "Generated lifecycle timeline"\n---\nBody\n'
        )
        == '---\ntitle: "Details and history"\ndescription: "Generated lifecycle timeline"\n---\n\nBody\n'
    )

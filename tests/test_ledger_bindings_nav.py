from __future__ import annotations

import importlib.util
import io
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


def test_java_bindings_discovers_all_stable_maven_versions_from_lower_bound(
    monkeypatch,
) -> None:
    generate_ledger_bindings_api_reference = load_script("generate_ledger_bindings_api_reference")
    metadata = b"""\
<metadata>
  <versioning>
    <versions>
      <version>3.4.7</version>
      <version>3.4.8</version>
      <version>3.5.1</version>
      <version>3.5.2-snapshot</version>
      <version>3.5.10</version>
      <version>4.0.0-rc1</version>
    </versions>
  </versioning>
</metadata>
"""
    monkeypatch.setattr(
        generate_ledger_bindings_api_reference.urllib.request,
        "urlopen",
        lambda _request, timeout: io.BytesIO(metadata),
    )

    assert generate_ledger_bindings_api_reference.discover_stable_maven_versions(
        repo_base="https://repo.example.test/maven2",
        group="com.daml",
        artifact="bindings-java",
        min_version="3.4.8",
    ) == ["3.4.8", "3.5.1", "3.5.10"]


def test_java_bindings_nav_puts_overview_before_packages(tmp_path: Path) -> None:
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
    write_mdx(overview_file, "Java Bindings")
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
                "group": "Packages",
                "pages": [{"group": "com.example", "pages": ["reference/java/com-example/Client"]}],
            },
        ],
    }


def test_java_bindings_nav_supports_product_navigation(tmp_path: Path) -> None:
    generate_ledger_bindings_api_reference = load_script("generate_ledger_bindings_api_reference")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "products": [
                        {
                            "product": "API Reference",
                            "pages": [{"group": "Ledger API", "pages": []}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    publish_root = docs_json.parent / "reference"
    overview_file = publish_root / "java-bindings.mdx"
    write_mdx(overview_file, "Java Bindings")
    write_mdx(
        publish_root / "java" / "com-example" / "index.mdx",
        "com.example",
        "## Package `com.example`\n",
    )
    write_mdx(publish_root / "java" / "com-example" / "Client.mdx", "Client")

    generate_ledger_bindings_api_reference.update_docs_navigation(
        docs_json_path=docs_json,
        dropdown_label="API Reference",
        parent_groups=["Ledger API"],
        group_label="Java Bindings",
        overview_file=overview_file,
        publish_root=publish_root,
    )

    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    assert docs["navigation"]["products"][0]["pages"] == [
        {
            "group": "Ledger API",
            "pages": [
                {
                    "group": "Java Bindings",
                    "pages": [
                        "reference/java-bindings",
                        {
                            "group": "Packages",
                            "pages": [{"group": "com.example", "pages": ["reference/java/com-example/Client"]}],
                        },
                    ],
                }
            ],
        }
    ]


def test_daml_standard_library_nav_supports_product_navigation(tmp_path: Path) -> None:
    generate_daml_standard_library_reference = load_script("generate_daml_standard_library_reference")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "products": [
                        {
                            "product": "API Reference",
                            "pages": [{"group": "Daml APIs", "pages": []}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    output_dir = docs_json.parent / "appdev" / "reference" / "daml-standard-library"
    write_mdx(output_dir / "index.mdx", "Daml Standard Library")
    write_mdx(output_dir / "da-list.mdx", "DA.List")

    generate_daml_standard_library_reference.update_docs_navigation(
        docs_json_path=docs_json,
        dropdown_label="API Reference",
        parent_groups=["Daml APIs"],
        output_dir=output_dir,
    )

    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    assert docs["navigation"]["products"][0]["pages"] == [
        {
            "group": "Daml APIs",
            "pages": [
                {
                    "group": "Daml Standard Library",
                    "pages": [
                        {
                            "group": "Modules",
                            "pages": ["appdev/reference/daml-standard-library/da-list"],
                        },
                        "appdev/reference/daml-standard-library/index",
                    ],
                }
            ],
        }
    ]
    assert (output_dir / "index.mdx").read_text(encoding="utf-8").startswith(
        '---\ntitle: "Details and history"\n---'
    )


def test_daml_script_nav_is_top_level_in_api_reference(tmp_path: Path) -> None:
    generate_daml_script_reference = load_script("generate_daml_script_reference")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "products": [
                        {
                            "product": "API Reference",
                            "pages": [
                                {
                                    "group": "Daml Standard Library",
                                    "pages": [{"group": "Modules", "pages": ["appdev/reference/daml-standard-library/da-list"]}],
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    output_dir = docs_json.parent / "appdev" / "reference" / "daml-script"
    write_mdx(output_dir / "index.mdx", "Daml Script")
    write_mdx(output_dir / "daml-script.mdx", "Daml.Script")
    write_mdx(output_dir / "daml-script-internal.mdx", "Daml.Script.Internal")

    generate_daml_script_reference.update_docs_navigation(
        docs_json_path=docs_json,
        dropdown_label="API Reference",
        parent_groups=[],
        output_dir=output_dir,
    )

    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    assert docs["navigation"]["products"][0]["pages"] == [
        {
            "group": "Daml Standard Library",
            "pages": [{"group": "Modules", "pages": ["appdev/reference/daml-standard-library/da-list"]}],
        },
        {
            "group": "Daml Script",
            "pages": [
                {
                    "group": "Modules",
                    "pages": [
                        "appdev/reference/daml-script/daml-script",
                        "appdev/reference/daml-script/daml-script-internal",
                    ],
                },
            ],
        },
    ]


def test_java_bindings_redirects_are_idempotent(tmp_path: Path) -> None:
    generate_ledger_bindings_api_reference = load_script("generate_ledger_bindings_api_reference")
    docs_json = tmp_path / "docs.json"
    docs_json.write_text('{"redirects": []}\n', encoding="utf-8")

    for _ in range(2):
        generate_ledger_bindings_api_reference.ensure_java_bindings_redirects(
            docs_json_path=docs_json,
        )

    assert json.loads(docs_json.read_text(encoding="utf-8"))["redirects"] == [
        {
            "source": "/reference/java",
            "destination": "/reference/java-bindings",
        },
        {
            "source": "/reference/java/index",
            "destination": "/reference/java-bindings",
        },
    ]


def test_java_bindings_publish_rewrites_standardized_html_links() -> None:
    generate_ledger_bindings_api_reference = load_script("generate_ledger_bindings_api_reference")

    assert generate_ledger_bindings_api_reference.rewrite_markdown_links(
        '<a href="./bindings-java-packages/com-example/index">Package</a>\n'
        '<a href="../../bindings-java">Back</a>\n',
        [
            ("./bindings-java-packages/", "./java/"),
            ("../../bindings-java", "../../java-bindings"),
        ],
    ) == (
        '<a href="./java/com-example/index">Package</a>\n'
        '<a href="../../java-bindings">Back</a>\n'
    )

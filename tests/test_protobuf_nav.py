from __future__ import annotations

import importlib.util
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


def test_protobuf_nav_keeps_packages_category_with_details_last(tmp_path: Path) -> None:
    generated_reference_nav = load_script("generated_reference_nav")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text("{}", encoding="utf-8")
    output_dir = docs_json.parent / "reference" / "protobuf"

    write_mdx(output_dir / "index.mdx", "Details and History")
    write_mdx(output_dir / "packages" / "com-example.mdx", "com.example")
    write_mdx(
        output_dir / "operations" / "com-example" / "exampleservice" / "getexample.mdx",
        "GetExample",
        "<dl><dt>Service</dt>\n<dd>ExampleService</dd></dl>\n",
    )

    group = generated_reference_nav.build_protobuf_nav_group(
        output_dir=output_dir,
        docs_json_path=docs_json,
        group_label="Protobufs",
    )

    assert group == {
        "group": "Protobufs",
        "pages": [
            {
                "group": "Packages",
                "pages": [
                    {
                        "group": "com.example",
                        "pages": [
                            "reference/protobuf/packages/com-example",
                            {
                                "group": "Services",
                                "pages": [
                                    {
                                        "group": "ExampleService",
                                        "pages": [
                                            "reference/protobuf/operations/com-example/exampleservice/getexample"
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            },
            "reference/protobuf/index",
        ],
    }

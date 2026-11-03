from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "validate_mdx_components.py"
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


def undeclared(tmp_path: Path, text: str) -> list[tuple[int, str]]:
    module = load_script_module()
    page = tmp_path / "page.mdx"
    page.write_text(text, encoding="utf-8")
    return [(item.line, item.name) for item in module.undeclared_components(page)]


def test_reports_component_without_import(tmp_path: Path) -> None:
    text = (
        '---\ntitle: "Page"\n---\n\n'
        'import Used from "/snippets/used.mdx";\n\n'
        "<Used />\n\n"
        "<Missing />\n"
    )
    assert undeclared(tmp_path, text) == [(9, "Missing")]


def test_accepts_named_namespace_and_exported_components(tmp_path: Path) -> None:
    text = (
        'import { First, Second as Renamed } from "/snippets/named.mdx";\n'
        'import * as Lib from "/snippets/lib.mdx";\n'
        "export const Local = () => <span />;\n\n"
        "<First />\n<Renamed />\n<Lib.Item />\n<Local />\n"
    )
    assert undeclared(tmp_path, text) == []


def test_accepts_mintlify_built_ins(tmp_path: Path) -> None:
    text = (
        "<Tabs>\n  <Tab title=\"A\">\n    <Note>n</Note>\n  </Tab>\n</Tabs>\n"
        "<Tree>\n  <Tree.File name=\"a\" />\n</Tree>\n"
    )
    assert undeclared(tmp_path, text) == []


def test_ignores_code_comments_and_escaped_angle_brackets(tmp_path: Path) -> None:
    text = (
        "```bash\n./start.sh <SPONSOR_SV_URL>\n```\n\n"
        "> ```bash\n> run <MIGRATION_ID>\n> ```\n\n"
        "Use `List<String>` here.\n\n"
        "{/* <Commented /> */}\n\n"
        "### Error: \"\\<X\\> is not authorized\"\n"
    )
    assert undeclared(tmp_path, text) == []


def test_docs_main_has_no_undeclared_components() -> None:
    module = load_script_module()
    found = [
        f"{item.path.relative_to(REPO_ROOT)}:{item.line}: <{item.name}>"
        for item in module.audit()
    ]
    assert found == []

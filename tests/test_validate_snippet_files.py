from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "validate_snippet_files.py"
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


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def layout(tmp_path: Path) -> tuple[Path, Path]:
    docs_main = tmp_path / "docs-main"
    snippets = docs_main / "snippets"
    snippets.mkdir(parents=True)
    return docs_main, snippets


def test_audit_reports_missing_and_orphan_snippets(tmp_path: Path) -> None:
    module = load_script_module()
    docs_main, snippets = layout(tmp_path)
    write(
        docs_main / "page.mdx",
        'import Used from "/snippets/used.mdx";\n\n<Used />\n',
    )
    write(snippets / "used.mdx", "```text\nused\n```\n")
    write(snippets / "orphan.mdx", "```text\norphan\n```\n")
    write(
        docs_main / "missing.mdx",
        'import Missing from "/snippets/missing.mdx";\n\n<Missing />\n',
    )

    result = module.audit(docs_main, snippets)

    assert result.content_pages == 2
    assert result.missing == ("/snippets/missing.mdx",)
    assert result.orphans == ("/snippets/orphan.mdx",)


def test_audit_follows_nested_and_networkvars_references(tmp_path: Path) -> None:
    module = load_script_module()
    docs_main, snippets = layout(tmp_path)
    write(
        docs_main / "page.mdx",
        '{/* NETWORKVARS_START source="/snippets/networkvars/block.mdx" */}\n',
    )
    write(
        snippets / "networkvars" / "block.mdx",
        'import Nested from "/snippets/internal/nested.mdx";\n\n<Nested />\n',
    )
    write(snippets / "internal" / "nested.mdx", "```bash\necho nested\n```\n")
    write(
        docs_main / "named.mdx",
        "import { networkData } from '/snippets/generated/data.mdx';\n",
    )
    write(snippets / "generated" / "data.mdx", "export const networkData = {};\n")

    result = module.audit(docs_main, snippets)

    assert result.missing == ()
    assert result.orphans == ()
    assert "/snippets/networkvars/block.mdx" in result.referenced
    assert "/snippets/internal/nested.mdx" in result.referenced
    assert "/snippets/generated/data.mdx" in result.referenced


def test_main_writes_logs_and_respects_no_fail(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    module = load_script_module()
    docs_main, snippets = layout(tmp_path)
    write(
        docs_main / "page.mdx",
        'import Missing from "/snippets/missing.mdx";\n',
    )
    write(snippets / "orphan.mdx", "orphan\n")
    output_dir = tmp_path / "logs"

    monkeypatch.setattr(module, "DOCS_MAIN", docs_main)
    monkeypatch.setattr(module, "SNIPPETS_ROOT", snippets)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    failing = module.main(["--output-path", str(output_dir)])
    assert failing == 1
    assert (output_dir / "snippets-missing.log").read_text(encoding="utf-8") == (
        "/snippets/missing.mdx\n"
    )
    assert (output_dir / "snippets-orphan.log").read_text(encoding="utf-8") == (
        "/snippets/orphan.mdx\n"
    )

    capsys.readouterr()
    quiet = module.main(["--quiet", "--no-fail", "--output-path", str(output_dir)])
    assert quiet == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "/snippets/missing.mdx" in captured.err
    assert "/snippets/orphan.mdx" in captured.err


def test_delete_orphan_snippets_removes_only_orphans(tmp_path: Path, monkeypatch) -> None:
    module = load_script_module()
    docs_main, snippets = layout(tmp_path)
    used = snippets / "used.mdx"
    orphan = snippets / "orphan.mdx"
    write(docs_main / "page.mdx", 'import Used from "/snippets/used.mdx";\n')
    write(used, "used\n")
    write(orphan, "orphan\n")

    monkeypatch.setattr(module, "DOCS_MAIN", docs_main)
    monkeypatch.setattr(module, "SNIPPETS_ROOT", snippets)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    exit_code = module.main(
        ["--delete-orphan-snippets", "--no-fail", "--output-path", str(tmp_path / "logs")]
    )

    assert exit_code == 0
    assert used.is_file()
    assert not orphan.exists()

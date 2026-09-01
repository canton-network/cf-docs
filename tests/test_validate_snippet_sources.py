from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "validate_snippet_sources.py"
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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def snippet(
    name: str,
    filepath: str,
    location: dict,
    repo: str = "daml",
) -> dict:
    return {
        "snippetName": name,
        "sourceRepo": repo,
        "sourceFilepath": filepath,
        "location": location,
        "description": "",
        "options": {"language": "text"},
    }


def config_layout(tmp_path: Path, snippets: list[dict], repo: str = "daml") -> Path:
    config_dir = tmp_path / "config"
    filename = f"{repo}-snippet-list-remote.json"
    write_json(config_dir / "remote-snippet-lists.json", {"snippetLists": [filename]})
    write_json(config_dir / filename, {"snippets": snippets})
    return config_dir


def test_full_file_and_line_and_marker_validation(tmp_path: Path) -> None:
    module = load_script_module()
    source = tmp_path / "daml"
    write_text(source / "examples" / "full.txt", "alpha\nbeta\ngamma\n")
    write_text(
        source / "examples" / "marked.txt",
        "header\n-- BEGIN\nbody\n-- END\nfooter\n",
    )
    config_dir = config_layout(
        tmp_path,
        [
            snippet("full-ok", "examples/full.txt", {"type": "fullFile"}),
            snippet("lines-ok", "examples/full.txt", {"type": "lines", "start": 1, "end": 3}),
            snippet("lines-oob", "examples/full.txt", {"type": "lines", "start": 2, "end": 9}),
            snippet("marker-ok", "examples/marked.txt", {
                "type": "stringMarker",
                "start": "-- BEGIN",
                "end": "-- END",
            }),
            snippet("marker-missing", "examples/marked.txt", {
                "type": "stringMarker",
                "start": "-- BEGIN",
                "end": "-- NOPE",
            }),
            snippet("missing-file", "examples/absent.txt", {"type": "fullFile"}),
        ],
    )

    result = module.audit(config_dir=config_dir, repo="daml", source_dir=source)
    messages = [error.format() for error in result.errors]
    assert result.snippet_count == 6
    assert any("line range 2-9 is out of bounds" in message for message in messages)
    assert any("end marker not found: '-- NOPE'" in message for message in messages)
    assert any("source file not found: examples/absent.txt" in message for message in messages)
    assert not any("full-ok:" in message or "lines-ok:" in message or "marker-ok:" in message for message in messages)


def test_json_index_out_of_bounds(tmp_path: Path) -> None:
    module = load_script_module()
    source = tmp_path / "canton"
    write_text(source / "snippets.json", json.dumps(["one", "two"]))
    config_dir = config_layout(
        tmp_path,
        [snippet("json-oob", "snippets.json", {"type": "jsonIndex", "start": 0, "end": 4}, repo="canton")],
        repo="canton",
    )

    result = module.audit(config_dir=config_dir, repo="canton", source_dir=source)
    assert len(result.errors) == 1
    assert "jsonIndex 0-4 is out of bounds (array length 2)" in result.errors[0].message


def test_main_writes_log_and_respects_flags(tmp_path: Path, monkeypatch, capsys) -> None:
    module = load_script_module()
    source = tmp_path / "dpm"
    write_text(source / "docs" / "file.rst", "only one line\n")
    config_dir = config_layout(
        tmp_path,
        [snippet("oob", "docs/file.rst", {"type": "lines", "start": 5, "end": 6}, repo="dpm")],
        repo="dpm",
    )
    output_dir = tmp_path / "logs"

    monkeypatch.setattr(module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    failing = module.main(
        ["dpm", "--source-dir", str(source), "--output-path", str(output_dir)]
    )
    assert failing == 1
    log = (output_dir / "snippet-source-errors.log").read_text(encoding="utf-8")
    assert "dpm oob:" in log
    assert "out of bounds" in log

    capsys.readouterr()
    quiet = module.main(
        [
            "--quiet",
            "--no-fail",
            "dpm",
            "--source-dir",
            str(source),
            "--output-path",
            str(output_dir),
        ]
    )
    assert quiet == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "out of bounds" in captured.err


def test_source_dir_requires_single_repo(tmp_path: Path) -> None:
    module = load_script_module()
    config_dir = tmp_path / "config"
    write_json(
        config_dir / "remote-snippet-lists.json",
        {"snippetLists": ["daml-snippet-list-remote.json", "dpm-snippet-list-remote.json"]},
    )
    write_json(config_dir / "daml-snippet-list-remote.json", {"snippets": []})
    write_json(config_dir / "dpm-snippet-list-remote.json", {"snippets": []})

    try:
        module.audit(config_dir=config_dir, source_dir=tmp_path / "somewhere")
    except SystemExit as error:
        assert "Pass a repo name when using --source-dir" in str(error)
    else:
        raise AssertionError("expected SystemExit")

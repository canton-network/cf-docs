from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from scripts import manage_external_snippets as author

# Deliberately non-canonical formatting: trailing spaces and 3-space indent inside
# an entry. Add must preserve every byte outside the inserted entry.
MANIFEST_TEXT = (
    '{\n'
    '  "urlSubstitutions": {"https://example.invalid": "replacement"},  \n'
    '  "snippets": [\n'
    '    {\n'
    '       "snippetName": "splice-literal-full-aaa",\n'
    '      "sourceRepo": "splice",\n'
    '      "sourceFilepath": "aaa.py",\n'
    '      "location": {"type": "fullFile"},\n'
    '      "description": "",\n'
    '      "options": {"language": "python"}\n'
    '    },\n'
    '    {\n'
    '      "snippetName": "splice-literal-full-zzz",\n'
    '      "sourceRepo": "splice",\n'
    '      "sourceFilepath": "zzz.py",\n'
    '      "location": {"type": "fullFile"},\n'
    '      "description": "",\n'
    '      "options": {"language": "python"}\n'
    '    }\n'
    '  ]\n'
    '}\n'
)


@pytest.fixture
def authoring_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    root = tmp_path / "cf-docs"
    helper = root / "scripts" / "helpers" / "generateOutputDocs.js"
    helper.parent.mkdir(parents=True)
    shutil.copy2(author.helper_path(), helper)
    manifest = root / "config" / "snippet-config" / "splice-snippet-list-remote.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(MANIFEST_TEXT, encoding="utf-8")
    source_dir = tmp_path / "splice"
    source_dir.mkdir()
    monkeypatch.setattr(author, "CF_DOCS_ROOT", root)
    return root, manifest, source_dir


def add_args(source_dir: Path, source: str, *extra: str) -> list[str]:
    return ["add", "splice", "--source-dir", str(source_dir), "--source", source, *extra]


def output_for(root: Path, name: str) -> Path:
    return root / "docs-main" / "snippets" / "external" / "splice" / "main" / f"{name}.mdx"


def test_add_full_file_inserts_alphabetically_and_preserves_other_bytes(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "examples" / "hello.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('hello')\n", encoding="utf-8")

    assert author.main(add_args(source_dir, "examples/hello.py")) == 0

    name = "splice-literal-full-examples-hello"
    text = manifest.read_text(encoding="utf-8")
    names = [s["snippetName"] for s in json.loads(text)["snippets"]]
    assert names == ["splice-literal-full-aaa", name, "splice-literal-full-zzz"]
    assert json.loads(text)["snippets"][1] == {
        "snippetName": name,
        "sourceRepo": "splice",
        "sourceFilepath": "examples/hello.py",
        "location": {"type": "fullFile"},
        "description": "",
        "options": {"language": "python"},
    }
    # Removing the inserted block restores the original bytes exactly.
    start = text.index("    {\n      \"snippetName\": \"splice-literal-full-examples-hello\"")
    end = text.index("    {\n      \"snippetName\": \"splice-literal-full-zzz\"")
    assert text[:start] + text[end:] == MANIFEST_TEXT

    assert output_for(root, name).read_text(encoding="utf-8") == "```python\nprint('hello')\n```"
    out = capsys.readouterr().out
    assert (
        "import ExternalSpliceMainSpliceLiteralFullExamplesHello from "
        "'/snippets/external/splice/main/splice-literal-full-examples-hello.mdx';"
    ) in out
    assert "<ExternalSpliceMainSpliceLiteralFullExamplesHello />" in out
    assert not (root / "config" / "snippet-config" / "snippet-source-lock.json").exists()


def test_add_appends_when_name_sorts_last(authoring_fixture: tuple[Path, Path, Path]) -> None:
    _, manifest, source_dir = authoring_fixture
    (source_dir / "zzzz.py").write_text("x = 1\n", encoding="utf-8")
    assert author.main(add_args(source_dir, "zzzz.py")) == 0
    names = [s["snippetName"] for s in json.loads(manifest.read_text(encoding="utf-8"))["snippets"]]
    assert names[-1] == "splice-literal-full-zzzz"


def test_add_into_empty_snippets_array(authoring_fixture: tuple[Path, Path, Path]) -> None:
    _, manifest, source_dir = authoring_fixture
    manifest.write_text('{\n  "snippets": []\n}\n', encoding="utf-8")
    (source_dir / "one.py").write_text("x = 1\n", encoding="utf-8")
    assert author.main(add_args(source_dir, "one.py")) == 0
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert [s["snippetName"] for s in data["snippets"]] == ["splice-literal-full-one"]


def test_add_marker_expands_pair_and_rejects_duplicate_name(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, manifest, source_dir = authoring_fixture
    (source_dir / "values.yaml").write_text(
        "before\n# DEMO_START\nenabled: true\n# DEMO_END\nafter\n", encoding="utf-8"
    )
    arguments = add_args(source_dir, "values.yaml", "--marker", "DEMO")

    assert author.main(arguments) == 0
    original = manifest.read_bytes()
    assert author.main(arguments) == 1

    entry = next(
        s for s in json.loads(original)["snippets"]
        if s["snippetName"] == "splice-literal-marker-values-demo-start"
    )
    assert entry["location"] == {"type": "stringMarker", "start": "DEMO_START", "end": "DEMO_END"}
    assert manifest.read_bytes() == original
    assert "Snippet name already exists" in capsys.readouterr().err


def test_add_accepts_locally_modified_source(authoring_fixture: tuple[Path, Path, Path]) -> None:
    """No provenance is recorded, so working-tree content is what gets extracted."""
    root, _, source_dir = authoring_fixture
    (source_dir / "values.yaml").write_text("# NEW_START\nfresh: true\n# NEW_END\n", encoding="utf-8")
    assert author.main(add_args(source_dir, "values.yaml", "--marker", "NEW")) == 0
    assert "fresh: true" in output_for(root, "splice-literal-marker-values-new-start").read_text(encoding="utf-8")


def test_add_does_not_write_when_marker_validation_fails(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "values.yaml").write_text("enabled: true\n", encoding="utf-8")
    original = manifest.read_bytes()

    assert author.main(add_args(source_dir, "values.yaml", "--marker", "MISSING")) == 1
    assert manifest.read_bytes() == original
    assert not (root / "docs-main").exists()
    assert "Marker not found" in capsys.readouterr().err


def test_add_requires_source_dir_and_rejects_unknown_repo(authoring_fixture: tuple[Path, Path, Path]) -> None:
    _, _, source_dir = authoring_fixture
    (source_dir / "one.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        author.main(["add", "splice", "--source", "one.py"])
    with pytest.raises(SystemExit):
        author.main(["add", "nonesuch", "--source-dir", str(source_dir), "--source", "one.py"])


@pytest.mark.parametrize("source", ["../outside.py", "/abs/outside.py", "a/../../outside.py"])
def test_add_rejects_paths_escaping_the_checkout(
    authoring_fixture: tuple[Path, Path, Path], tmp_path: Path, source: str
) -> None:
    _, manifest, source_dir = authoring_fixture
    (tmp_path / "outside.py").write_text("x = 1\n", encoding="utf-8")
    original = manifest.read_bytes()
    assert author.main(add_args(source_dir, source)) == 1
    assert manifest.read_bytes() == original


def test_language_defaults_from_table_and_flag_overrides(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, manifest, source_dir = authoring_fixture
    (source_dir / "app.conf").write_text("canton { x = 1 }\n", encoding="utf-8")
    (source_dir / "data.xyz").write_text("payload\n", encoding="utf-8")

    assert author.main(add_args(source_dir, "app.conf")) == 0
    assert author.main(add_args(source_dir, "data.xyz")) == 1
    assert "Cannot infer a language" in capsys.readouterr().err
    assert author.main(add_args(source_dir, "data.xyz", "--language", "text")) == 0

    by_name = {s["snippetName"]: s for s in json.loads(manifest.read_text(encoding="utf-8"))["snippets"]}
    assert by_name["splice-literal-full-app"]["options"] == {"language": "hocon"}
    assert by_name["splice-literal-full-data"]["options"] == {"language": "text"}


def test_derive_snippet_name_shortens_long_paths_deterministically() -> None:
    repo = author.discover_repos(author.config_dir())["splice"]
    short = "apps/app/src/pack/examples/sv-helm/validator-values.yaml"
    assert author.derive_snippet_name(repo, short, {"type": "fullFile"}) == (
        "splice-literal-full-apps-app-src-pack-examples-sv-helm-validator-values"
    )
    assert author.derive_snippet_name(
        repo, short, {"type": "stringMarker", "start": "SWEEP_START", "end": "SWEEP_END"}
    ) == "splice-literal-marker-apps-app-src-pack-examples-sv-helm-validator-values-sweep-start"

    deep = "cluster/helm/splice-cometbft/templates/extra/long/path/to/some/deeply/nested/component-values-template.yaml"
    middle = "helm/splice-cometbft/templates/extra/long/path/to/some/deeply/nested"
    digest = hashlib.sha256(middle.encode()).hexdigest()[:6]
    name = author.derive_snippet_name(repo, deep, {"type": "fullFile"})
    assert name == f"splice-literal-full-cluster-{digest}-component-values-template"
    assert len(name) <= author.NAME_LENGTH_LIMIT
    assert name == author.derive_snippet_name(repo, deep, {"type": "fullFile"})

    # Marker suffix is never shortened, even if the result stays over the limit.
    marker = {"type": "stringMarker", "start": "PARTICIPANT_BOOTSTRAP_MIGRATE_TO_NEW_PARTICIPANT_START", "end": "X_END"}
    assert author.derive_snippet_name(repo, deep, marker).endswith(
        "-component-values-template-participant-bootstrap-migrate-to-new-participant-start"
    )


def test_add_dry_run_prints_diffs_with_no_newline_marker_and_writes_nothing(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "example.py").write_text("print('preview')\n", encoding="utf-8")
    original = manifest.read_bytes()

    assert author.main(add_args(source_dir, "example.py", "--dry-run")) == 0
    assert manifest.read_bytes() == original
    assert not (root / "docs-main").exists()
    out = capsys.readouterr().out
    assert "Dry run: would add splice-literal-full-example; no files written" in out
    assert "Manifest diff:" in out
    assert '+      "snippetName": "splice-literal-full-example"' in out
    assert "Generated MDX diff:" in out
    assert "+```python\n+print('preview')\n+```\n\\ No newline at end of file\n" in out
    assert "Source lock diff:" not in out


def test_add_refuses_to_overwrite_an_orphaned_output(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "example.py").write_text("print('new')\n", encoding="utf-8")
    output = output_for(root, "splice-literal-full-example")
    output.parent.mkdir(parents=True)
    output.write_text("existing\n", encoding="utf-8")
    original = manifest.read_bytes()

    assert author.main(add_args(source_dir, "example.py")) == 1
    assert manifest.read_bytes() == original
    assert output.read_text(encoding="utf-8") == "existing\n"
    assert "Refusing to overwrite" in capsys.readouterr().err


def test_insert_preserves_real_canton_manifest_bytes() -> None:
    """The canton manifest is not json.dumps-canonical; textual insertion must not reformat it."""
    path = Path(author.__file__).resolve().parents[1] / "config" / "snippet-config" / "canton-snippet-list-remote.json"
    text = path.read_text(encoding="utf-8")
    entry = {"snippetName": "zzz-probe", "sourceRepo": "canton", "sourceFilepath": "x.yaml",
             "location": {"type": "fullFile"}, "description": "", "options": {"language": "yaml"}}
    new = author.insert_manifest_entry(text, entry)
    assert json.loads(new)["snippets"][-1] == entry
    rendered = json.dumps(entry, indent=2, ensure_ascii=False).replace("\n", "\n    ")
    assert new.replace(",\n    " + rendered, "", 1) == text


def edit_args(source_dir: Path, name: str, *extra: str) -> list[str]:
    return ["edit", "splice", name, "--source-dir", str(source_dir), *extra]


def entry_span(text: str, name: str) -> tuple[int, int]:
    _, _, elements = author.manifest_elements(text)
    element = next(e for e in elements if e.value["snippetName"] == name)
    return element.start, element.end


def test_edit_rerenders_changed_source_without_touching_the_manifest(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "aaa.py"
    source.write_text("x = 1\n", encoding="utf-8")
    name = "splice-literal-full-aaa"
    assert author.main(edit_args(source_dir, name)) == 0
    assert output_for(root, name).read_text(encoding="utf-8") == "```python\nx = 1\n```"

    source.write_text("x = 2\n", encoding="utf-8")
    assert author.main(edit_args(source_dir, name)) == 0

    assert output_for(root, name).read_text(encoding="utf-8") == "```python\nx = 2\n```"
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert "its import path is unchanged" in capsys.readouterr().out


def test_edit_reports_an_up_to_date_snippet_and_writes_nothing(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "aaa.py").write_text("x = 1\n", encoding="utf-8")
    name = "splice-literal-full-aaa"
    assert author.main(edit_args(source_dir, name)) == 0
    output = output_for(root, name)
    stamp = output.stat().st_mtime_ns
    capsys.readouterr()

    assert author.main(edit_args(source_dir, name)) == 0

    assert output.stat().st_mtime_ns == stamp
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert "already up to date" in capsys.readouterr().out


def test_edit_marker_keeps_the_name_and_preserves_other_manifest_bytes(
    authoring_fixture: tuple[Path, Path, Path]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "zzz.py").write_text("a\n# DEMO_START\nb = 1\n# DEMO_END\n", encoding="utf-8")
    name = "splice-literal-full-zzz"

    assert author.main(edit_args(source_dir, name, "--marker", "DEMO")) == 0

    text = manifest.read_text(encoding="utf-8")
    entry = next(s for s in json.loads(text)["snippets"] if s["snippetName"] == name)
    assert entry["location"] == {"type": "stringMarker", "start": "DEMO_START", "end": "DEMO_END"}
    start, end = entry_span(text, name)
    old_start, old_end = entry_span(MANIFEST_TEXT, name)
    assert text[:start] == MANIFEST_TEXT[:old_start]
    assert text[end:] == MANIFEST_TEXT[old_end:]
    assert output_for(root, name).read_text(encoding="utf-8") == "```python\nb = 1\n```"


def test_edit_full_file_and_language_change_the_entry(authoring_fixture: tuple[Path, Path, Path]) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "zzz.py").write_text("# DEMO_START\nb = 1\n# DEMO_END\n", encoding="utf-8")
    name = "splice-literal-full-zzz"
    assert author.main(edit_args(source_dir, name, "--marker", "DEMO")) == 0

    assert author.main(edit_args(source_dir, name, "--full-file", "--language", "text")) == 0

    entry = next(
        s for s in json.loads(manifest.read_text(encoding="utf-8"))["snippets"]
        if s["snippetName"] == name
    )
    assert entry["location"] == {"type": "fullFile"}
    assert entry["options"] == {"language": "text"}
    assert output_for(root, name).read_text(encoding="utf-8").startswith("```text\n# DEMO_START")


def test_edit_refuses_marker_and_full_file_together(authoring_fixture: tuple[Path, Path, Path]) -> None:
    _, _, source_dir = authoring_fixture
    with pytest.raises(SystemExit):
        author.main(edit_args(source_dir, "splice-literal-full-aaa", "--marker", "X", "--full-file"))


@pytest.mark.parametrize(
    ("name", "extra", "message"),
    [
        ("splice-literal-full-missing", (), "Expected exactly one snippet"),
        ("splice-literal-full-aaa", ("--marker", "ABSENT"), "Snippet extraction failed"),
        ("splice-literal-full-zzz", (), "Snippet source file does not exist"),
    ],
)
def test_edit_refusals_write_nothing(
    authoring_fixture: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
    name: str,
    extra: tuple[str, ...],
    message: str,
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "aaa.py").write_text("x = 1\n", encoding="utf-8")

    assert author.main(edit_args(source_dir, name, *extra)) == 1

    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert not (root / "docs-main").exists()
    assert message in capsys.readouterr().err


def test_edit_refuses_a_selector_another_snippet_uses(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, manifest, source_dir = authoring_fixture
    (source_dir / "aaa.py").write_text("# DEMO_START\nx\n# DEMO_END\n", encoding="utf-8")
    assert author.main(add_args(source_dir, "aaa.py", "--marker", "DEMO")) == 0
    before = manifest.read_bytes()

    assert author.main(edit_args(source_dir, "splice-literal-full-aaa", "--marker", "DEMO")) == 1

    assert manifest.read_bytes() == before
    assert "already uses this source and selector" in capsys.readouterr().err


def test_edit_dry_run_prints_diffs_and_writes_nothing(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "aaa.py").write_text("x = 1\n", encoding="utf-8")

    assert author.main(edit_args(source_dir, "splice-literal-full-aaa", "--language", "text", "--dry-run")) == 0

    out = capsys.readouterr().out
    assert "Dry run: would edit splice-literal-full-aaa; no files written" in out
    assert re.search(r'^\+\s+"language": "text"$', out, re.MULTILINE)
    assert "+```text" in out
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert not (root / "docs-main").exists()


def test_replace_preserves_real_canton_manifest_bytes() -> None:
    path = Path(author.__file__).resolve().parents[1] / "config" / "snippet-config" / "canton-snippet-list-remote.json"
    text = path.read_text(encoding="utf-8")
    _, _, elements = author.manifest_elements(text)
    target = elements[len(elements) // 2]
    changed = {**target.value, "description": "probe"}

    new = author.replace_manifest_entry(text, changed)

    start, end = entry_span(new, target.value["snippetName"])
    assert new[:start] == text[:target.start]
    assert new[end:] == text[target.end:]
    assert json.loads(new)["snippets"][len(elements) // 2] == changed


def test_delete_removes_entry_and_output_and_preserves_other_bytes(
    authoring_fixture: tuple[Path, Path, Path]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "examples").mkdir()
    (source_dir / "examples" / "hello.py").write_text("x = 1\n", encoding="utf-8")
    assert author.main(add_args(source_dir, "examples/hello.py")) == 0
    name = "splice-literal-full-examples-hello"

    assert author.main(["delete", "splice", name]) == 0

    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert not output_for(root, name).exists()


@pytest.mark.parametrize("position", ["first", "last"])
def test_delete_handles_first_and_last_entries(
    authoring_fixture: tuple[Path, Path, Path], position: str
) -> None:
    _, manifest, _ = authoring_fixture
    removed, kept = ("aaa", "zzz") if position == "first" else ("zzz", "aaa")

    assert author.main(["delete", "splice", f"splice-literal-full-{removed}"]) == 0

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert [s["snippetName"] for s in data["snippets"]] == [f"splice-literal-full-{kept}"]
    assert data["urlSubstitutions"] == {"https://example.invalid": "replacement"}


def test_delete_last_remaining_entry_leaves_an_empty_array(
    authoring_fixture: tuple[Path, Path, Path]
) -> None:
    _, manifest, _ = authoring_fixture
    assert author.main(["delete", "splice", "splice-literal-full-aaa"]) == 0
    assert author.main(["delete", "splice", "splice-literal-full-zzz"]) == 0
    assert json.loads(manifest.read_text(encoding="utf-8"))["snippets"] == []


def test_delete_refuses_while_a_page_references_the_snippet(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "aaa.py").write_text("x = 1\n", encoding="utf-8")
    name = "splice-literal-full-aaa"
    assert author.main(edit_args(source_dir, name)) == 0
    page = root / "docs-main" / "guide.mdx"
    page.write_text(
        f"import A from '/snippets/external/splice/main/{name}.mdx';\n\n<A />\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    assert author.main(["delete", "splice", name]) == 1

    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert output_for(root, name).exists()
    assert "docs-main/guide.mdx:1" in capsys.readouterr().err


def test_delete_ignores_references_to_names_sharing_a_prefix(
    authoring_fixture: tuple[Path, Path, Path]
) -> None:
    root, _, _ = authoring_fixture
    page = root / "docs-main" / "guide.mdx"
    page.parent.mkdir(parents=True)
    page.write_text(
        "import A from '/snippets/external/splice/main/splice-literal-full-aaa-longer.mdx';\n",
        encoding="utf-8",
    )
    assert author.main(["delete", "splice", "splice-literal-full-aaa"]) == 0


def test_delete_dry_run_prints_diffs_and_writes_nothing(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "aaa.py").write_text("x = 1\n", encoding="utf-8")
    name = "splice-literal-full-aaa"
    assert author.main(edit_args(source_dir, name)) == 0
    capsys.readouterr()

    assert author.main(["delete", "splice", name, "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert f"Dry run: would delete {name}; no files written" in out
    assert "+++ /dev/null" in out
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert output_for(root, name).exists()


def test_delete_unknown_name_is_refused(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, manifest, _ = authoring_fixture
    assert author.main(["delete", "splice", "splice-literal-full-missing"]) == 1
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert "Expected exactly one snippet" in capsys.readouterr().err


def move_args(source_dir: Path, name: str, source: str, *extra: str) -> list[str]:
    return ["move", "splice", name, "--source-dir", str(source_dir), "--source", source, *extra]


def test_move_points_the_entry_at_a_new_path_and_keeps_the_name(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "moved").mkdir()
    (source_dir / "moved" / "aaa.py").write_text("x = 3\n", encoding="utf-8")
    name = "splice-literal-full-aaa"

    assert author.main(move_args(source_dir, name, "moved/aaa.py")) == 0

    text = manifest.read_text(encoding="utf-8")
    entry = next(s for s in json.loads(text)["snippets"] if s["snippetName"] == name)
    assert entry["sourceFilepath"] == "moved/aaa.py"
    assert entry["location"] == {"type": "fullFile"}
    assert entry["options"] == {"language": "python"}
    start, end = entry_span(text, name)
    old_start, old_end = entry_span(MANIFEST_TEXT, name)
    assert text[:start] == MANIFEST_TEXT[:old_start]
    assert text[end:] == MANIFEST_TEXT[old_end:]
    assert output_for(root, name).read_text(encoding="utf-8") == "```python\nx = 3\n```"
    assert f"Moved {name}; its import path is unchanged" in capsys.readouterr().out


def test_move_language_follows_a_new_extension_unless_given(
    authoring_fixture: tuple[Path, Path, Path]
) -> None:
    _, manifest, source_dir = authoring_fixture
    (source_dir / "aaa.yaml").write_text("a: 1\n", encoding="utf-8")
    (source_dir / "zzz.yaml").write_text("z: 1\n", encoding="utf-8")

    assert author.main(move_args(source_dir, "splice-literal-full-aaa", "aaa.yaml")) == 0
    assert author.main(
        move_args(source_dir, "splice-literal-full-zzz", "zzz.yaml", "--language", "text")
    ) == 0

    languages = {
        s["snippetName"]: s["options"]["language"]
        for s in json.loads(manifest.read_text(encoding="utf-8"))["snippets"]
    }
    assert languages == {"splice-literal-full-aaa": "yaml", "splice-literal-full-zzz": "text"}


def test_move_can_change_the_selector(authoring_fixture: tuple[Path, Path, Path]) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "new.py").write_text("# DEMO_START\nb = 1\n# DEMO_END\n", encoding="utf-8")
    name = "splice-literal-full-aaa"

    assert author.main(move_args(source_dir, name, "new.py", "--marker", "DEMO")) == 0

    entry = next(
        s for s in json.loads(manifest.read_text(encoding="utf-8"))["snippets"]
        if s["snippetName"] == name
    )
    assert entry["location"] == {"type": "stringMarker", "start": "DEMO_START", "end": "DEMO_END"}
    assert output_for(root, name).read_text(encoding="utf-8") == "```python\nb = 1\n```"


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("absent.py", "Snippet source file does not exist"),
        ("../outside.py", "must not contain empty, '.' or '..'"),
        ("zzz.py", "already uses this source and selector"),
    ],
)
def test_move_refusals_write_nothing(
    authoring_fixture: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
    source: str,
    message: str,
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "zzz.py").write_text("z = 1\n", encoding="utf-8")

    assert author.main(move_args(source_dir, "splice-literal-full-aaa", source)) == 1

    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert not (root / "docs-main").exists()
    assert message in capsys.readouterr().err


def test_move_dry_run_prints_diffs_and_writes_nothing(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    (source_dir / "new.py").write_text("x = 1\n", encoding="utf-8")

    assert author.main(move_args(source_dir, "splice-literal-full-aaa", "new.py", "--dry-run")) == 0

    out = capsys.readouterr().out
    assert "Dry run: would move splice-literal-full-aaa; no files written" in out
    assert re.search(r'^\+\s+"sourceFilepath": "new.py",$', out, re.MULTILINE)
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert not (root / "docs-main").exists()


def test_move_requires_a_source(authoring_fixture: tuple[Path, Path, Path]) -> None:
    _, _, source_dir = authoring_fixture
    with pytest.raises(SystemExit):
        author.main(["move", "splice", "splice-literal-full-aaa", "--source-dir", str(source_dir)])


def test_add_repo_creates_an_empty_manifest_that_add_can_use(
    authoring_fixture: tuple[Path, Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _, _ = authoring_fixture
    manifest = root / "config" / "snippet-config" / "dpm-snippet-list-remote.json"

    assert author.main(["add-repo", "dpm"]) == 0

    assert manifest.read_text(encoding="utf-8") == '{\n  "snippets": []\n}\n'
    assert "npm run snippets:add -- dpm --source-dir" in capsys.readouterr().out

    source_dir = tmp_path / "dpm"
    source_dir.mkdir()
    (source_dir / "hello.sh").write_text("echo hi\n", encoding="utf-8")
    assert author.main(["add", "dpm", "--source-dir", str(source_dir), "--source", "hello.sh"]) == 0
    entry = json.loads(manifest.read_text(encoding="utf-8"))["snippets"][0]
    assert entry["snippetName"] == "dpm-literal-full-hello"
    assert entry["sourceRepo"] == "dpm"
    output = root / "docs-main" / "snippets" / "external" / "dpm" / "main" / "dpm-literal-full-hello.mdx"
    assert output.read_text(encoding="utf-8") == "```bash\necho hi\n```"


@pytest.mark.parametrize("name", ["Dpm", "dpm_tool", "dpm-", "dpm--tool", "dpm/tool", ""])
def test_add_repo_rejects_malformed_keys(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str], name: str
) -> None:
    root, _, _ = authoring_fixture
    before = sorted(p.name for p in (root / "config" / "snippet-config").iterdir())

    assert author.main(["add-repo", name]) == 1

    assert sorted(p.name for p in (root / "config" / "snippet-config").iterdir()) == before
    assert "must be lowercase letters and digits" in capsys.readouterr().err


def test_add_repo_refuses_an_existing_repository(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, manifest, _ = authoring_fixture
    assert author.main(["add-repo", "splice"]) == 1
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TEXT
    assert "Repository already exists" in capsys.readouterr().err


def test_add_repo_refuses_orphaned_output(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _, _ = authoring_fixture
    (root / "docs-main" / "snippets" / "external" / "dpm").mkdir(parents=True)

    assert author.main(["add-repo", "dpm"]) == 1

    assert not (root / "config" / "snippet-config" / "dpm-snippet-list-remote.json").exists()
    assert "already exists without a manifest" in capsys.readouterr().err


def test_add_repo_dry_run_writes_nothing(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _, _ = authoring_fixture

    assert author.main(["add-repo", "dpm", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "Dry run: would add repository dpm; no files written" in out
    assert '+  "snippets": []' in out
    assert not (root / "config" / "snippet-config" / "dpm-snippet-list-remote.json").exists()

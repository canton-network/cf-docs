from __future__ import annotations

import hashlib
import json
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
    repo = author.REPOS["splice"]
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

"""Spec-first invariants for ``npm run snippets:add`` (cf-docs #1659).

Spec: control/.worktrees/spec-first-harness/spec_trials/snippet-authoring-cli/spec.md
Run alone:  python3 -m pytest tests/test_spec_add.py -q
On ``main`` every test fails at the same point: there is no ``snippets:add`` script.

Seams (agent-proposed, user-accepted):
  1. Tests run the command inside a scratch copy of cf-docs, assuming the command
     finds its cf-docs root from its own file location like the existing generator.
  2. The source checkout is a throwaway git repo with ``origin`` on github.com.
  3. Invocation goes through ``npm run snippets:add --`` because that is the interface S1 fixes.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CF_DOCS_ROOT = Path(__file__).resolve().parents[1]
REPO = "splice"
REMOTE = "git@github.com:hyperledger-labs/splice.git"
MANIFEST_REL = Path("config/snippet-config/splice-snippet-list-remote.json")
OUTPUT_REL = Path("docs-main/snippets/external/splice/main")

SOURCE_FILE = "apps/app/src/pack/examples/sv-helm/spec-values.yaml"
SOURCE_TEXT = "a: 1\n# SWEEP_START\nsweep:\n  enabled: true\n# SWEEP_END\nb: 2\n"
DEEP_FILE = (
    "cluster/helm/splice-cometbft/templates/extra/long/path/to/some/deeply/nested/"
    "component-values-template.yaml"
)
EXTRA_FILES = {
    "docs/example.conf": "canton { x = 1 }\n",
    "docs/weird.xyz": "payload\n",
    "docs/dup.yaml": "# DUP_START\none\n# DUP_END\n# DUP_START\ntwo\n",
    "docs/rev.yaml": "# REV_END\nbody\n# REV_START\n",
    DEEP_FILE: "deep: true\n",
}
SPEC_OPTIONS = {"--source-dir", "--source", "--marker", "--language", "--dry-run"}


# --------------------------------------------------------------------------- helpers
def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=spec", "-c", "user.email=spec@example.invalid", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout


def tree_hash(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file() and not {".git", "node_modules", "__pycache__"} & set(p.parts):
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def porcelain(root: Path) -> list[str]:
    lines = _git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
    return sorted(line for line in lines if line and "__pycache__" not in line)


def base_name(repo: str, source: str, marker: str | None = None) -> str:
    """S7 base rule, before any shortening."""
    stem_path = re.sub(r"\.[^./]+$", "", source)
    slug = re.sub(r"[/.]", "-", stem_path)
    kind = "marker" if marker else "full"
    suffix = f"-{marker.lower().replace('_', '-')}-start" if marker else ""
    return f"{repo}-literal-{kind}-{slug}{suffix}"


def derive_name(repo: str, source: str, marker: str | None = None) -> str:
    """Independent statement of S7, written from the spec text, not from the tool."""
    stem_path = re.sub(r"\.[^./]+$", "", source)
    kind = "marker" if marker else "full"
    suffix = f"-{marker.lower().replace('_', '-')}-start" if marker else ""
    base = base_name(repo, source, marker)
    segs = stem_path.split("/")
    if len(base) <= 100 or len(segs) < 3:
        return base
    first, stem, middle = segs[0].replace(".", "-"), segs[-1].replace(".", "-"), segs[1:-1]
    h = hashlib.sha256("/".join(middle).encode()).hexdigest()[:6]
    return f"{repo}-literal-{kind}-{first}-{h}-{stem}{suffix}"


def make_cfdocs(tmp_path: Path) -> Path:
    root = tmp_path / "cf-docs"
    root.mkdir(parents=True)
    for rel in ("package.json", "package-lock.json"):
        if (CF_DOCS_ROOT / rel).exists():
            shutil.copy2(CF_DOCS_ROOT / rel, root / rel)
    shutil.copytree(CF_DOCS_ROOT / "scripts", root / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(CF_DOCS_ROOT / "config" / "snippet-config", root / "config" / "snippet-config")
    shutil.copytree(CF_DOCS_ROOT / "docs-main" / "snippets" / "external",
                    root / "docs-main" / "snippets" / "external")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def make_source(tmp_path: Path, name: str = "splice", remote: str = REMOTE) -> Path:
    src = tmp_path / name
    src.mkdir()
    _git(src, "init", "-q")
    _git(src, "remote", "add", "origin", remote)
    for rel, text in {SOURCE_FILE: SOURCE_TEXT, **EXTRA_FILES}.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "source")
    _git(src, "update-ref", "refs/remotes/origin/main", "HEAD")
    return src


def run_add(cfdocs: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**(env or os.environ), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        ["npm", "run", "--silent", "snippets:add", "--", *args],
        cwd=cfdocs, capture_output=True, text=True, env=env,
    )


def base_args(src: Path, source: str = SOURCE_FILE) -> list[str]:
    return [REPO, "--source-dir", str(src), "--source", source]


def manifest(cfdocs: Path) -> dict:
    return json.loads((cfdocs / MANIFEST_REL).read_text(encoding="utf-8"))


def entry(cfdocs: Path, name: str) -> dict:
    found = [s for s in manifest(cfdocs)["snippets"] if s["snippetName"] == name]
    assert len(found) == 1, f"expected exactly one manifest entry named {name}, got {len(found)}"
    return found[0]


def assert_refused(cfdocs: Path, before: dict[str, str], result: subprocess.CompletedProcess[str]) -> None:
    """S15 folded into every refusal: nonzero exit and a byte-identical tree."""
    assert result.returncode != 0, f"expected refusal, got exit 0\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert tree_hash(cfdocs) == before, "refusal changed the cf-docs tree (S15)"


def assert_ok(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, f"expected success\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


@pytest.fixture
def cfdocs(tmp_path: Path) -> Path:
    return make_cfdocs(tmp_path)


@pytest.fixture
def src(tmp_path: Path) -> Path:
    return make_source(tmp_path)


FULL_NAME = derive_name(REPO, SOURCE_FILE)
MARKER_NAME = derive_name(REPO, SOURCE_FILE, "SWEEP")


# --------------------------------------------------------------------------- interface
def test_s1_help_lists_exactly_the_spec_options(cfdocs: Path) -> None:
    result = run_add(cfdocs, "--help")
    text = result.stdout + result.stderr
    assert result.returncode == 0, text
    options = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", text)) - {"--help"}
    assert options == SPEC_OPTIONS, f"options differ from spec: extra={options - SPEC_OPTIONS} missing={SPEC_OPTIONS - options}"
    assert re.search(r"\brepo\b", text), "positional repo not shown in --help"


@pytest.mark.parametrize("drop", ["repo", "--source-dir", "--source"])
def test_s2_missing_required_argument_is_refused(cfdocs: Path, src: Path, drop: str) -> None:
    args = base_args(src)
    if drop == "repo":
        args = args[1:]
    else:
        i = args.index(drop)
        del args[i:i + 2]
    before = tree_hash(cfdocs)
    assert_refused(cfdocs, before, run_add(cfdocs, *args))


def test_s3_unknown_repo_is_refused(cfdocs: Path, src: Path) -> None:
    before = tree_hash(cfdocs)
    args = base_args(src)
    args[0] = "nonesuch"
    assert_refused(cfdocs, before, run_add(cfdocs, *args))


def test_s4_marker_yields_string_marker_location(cfdocs: Path, src: Path) -> None:
    assert_ok(run_add(cfdocs, *base_args(src), "--marker", "SWEEP"))
    assert entry(cfdocs, MARKER_NAME)["location"] == {"type": "stringMarker", "start": "SWEEP_START", "end": "SWEEP_END"}


def test_s4_no_marker_yields_full_file_location(cfdocs: Path, src: Path) -> None:
    assert_ok(run_add(cfdocs, *base_args(src)))
    assert entry(cfdocs, FULL_NAME)["location"] == {"type": "fullFile"}


@pytest.mark.parametrize("source,language", [(SOURCE_FILE, "yaml"), ("docs/example.conf", "hocon")])
def test_s5_language_defaults_from_extension_table(cfdocs: Path, src: Path, source: str, language: str) -> None:
    assert_ok(run_add(cfdocs, *base_args(src, source)))
    assert entry(cfdocs, derive_name(REPO, source))["options"]["language"] == language


def test_s5_unknown_extension_without_language_is_refused(cfdocs: Path, src: Path) -> None:
    before = tree_hash(cfdocs)
    assert_refused(cfdocs, before, run_add(cfdocs, *base_args(src, "docs/weird.xyz")))


def test_s5_language_flag_overrides_table(cfdocs: Path, src: Path) -> None:
    assert_ok(run_add(cfdocs, *base_args(src, "docs/weird.xyz"), "--language", "text"))
    assert entry(cfdocs, derive_name(REPO, "docs/weird.xyz"))["options"]["language"] == "text"


def test_s6_description_is_empty_string(cfdocs: Path, src: Path) -> None:
    assert_ok(run_add(cfdocs, *base_args(src)))
    assert entry(cfdocs, FULL_NAME)["description"] == ""


def test_s7_base_rule_reproduces_existing_splice_names() -> None:
    """Checks the rule as written in the spec against the corpus. Passes on main by design."""
    data = json.loads((CF_DOCS_ROOT / MANIFEST_REL).read_text(encoding="utf-8"))
    compared = 0
    for s in data["snippets"]:
        marker = s["location"].get("start")
        if marker is not None:
            assert marker.endswith("_START")
            marker = marker[: -len("_START")]
        if len(base_name(REPO, s["sourceFilepath"], marker)) <= 100:
            assert derive_name(REPO, s["sourceFilepath"], marker) == s["snippetName"]
            compared += 1
    assert compared == 7, "seven of the thirteen splice names are within the 100-character threshold"


def test_s7_long_path_is_shortened_deterministically(cfdocs: Path, src: Path) -> None:
    expected = derive_name(REPO, DEEP_FILE)
    assert len(expected) <= 100 and "-literal-full-cluster-" in expected
    assert_ok(run_add(cfdocs, *base_args(src, DEEP_FILE)))
    entry(cfdocs, expected)
    assert (cfdocs / OUTPUT_REL / f"{expected}.mdx").is_file()


# --------------------------------------------------------------------------- guards
def test_s8_sibling_entries_with_missing_sources_do_not_block(cfdocs: Path, src: Path) -> None:
    siblings = [s["sourceFilepath"] for s in manifest(cfdocs)["snippets"]]
    assert siblings and not any((src / p).exists() for p in siblings), "fixture must lack every sibling source"
    assert_ok(run_add(cfdocs, *base_args(src)))


def test_s9_locally_modified_tracked_source_is_accepted(cfdocs: Path, src: Path) -> None:
    p = src / SOURCE_FILE
    p.write_text(p.read_text(encoding="utf-8") + "# MODIFIED_START\nnew: region\n# MODIFIED_END\n", encoding="utf-8")
    assert porcelain(src) == [f" M {SOURCE_FILE}"]
    assert_ok(run_add(cfdocs, *base_args(src), "--marker", "MODIFIED"))
    mdx = (cfdocs / OUTPUT_REL / f"{derive_name(REPO, SOURCE_FILE, 'MODIFIED')}.mdx").read_text(encoding="utf-8")
    assert "new: region" in mdx


@pytest.mark.parametrize("kind", ["dotdot", "absolute", "symlink"])
def test_s10_source_escaping_checkout_is_refused(cfdocs: Path, src: Path, tmp_path: Path, kind: str) -> None:
    outside = tmp_path / "outside.yaml"
    outside.write_text("leak: true\n", encoding="utf-8")
    if kind == "dotdot":
        source = "../outside.yaml"
    elif kind == "absolute":
        source = str(src / SOURCE_FILE)
    else:
        (src / "link.yaml").symlink_to(outside)
        source = "link.yaml"
    before = tree_hash(cfdocs)
    assert_refused(cfdocs, before, run_add(cfdocs, *base_args(src, source)))


def test_s11_missing_source_is_refused(cfdocs: Path, src: Path) -> None:
    before = tree_hash(cfdocs)
    assert_refused(cfdocs, before, run_add(cfdocs, *base_args(src, "does/not/exist.yaml")))


@pytest.mark.parametrize("source,marker", [(SOURCE_FILE, "NOPE"), ("docs/dup.yaml", "DUP"), ("docs/rev.yaml", "REV")])
def test_s12_bad_markers_are_refused(cfdocs: Path, src: Path, source: str, marker: str) -> None:
    before = tree_hash(cfdocs)
    assert_refused(cfdocs, before, run_add(cfdocs, *base_args(src, source), "--marker", marker))


def test_s13_duplicate_name_is_refused(cfdocs: Path, src: Path) -> None:
    assert_ok(run_add(cfdocs, *base_args(src)))
    before = tree_hash(cfdocs)
    assert_refused(cfdocs, before, run_add(cfdocs, *base_args(src)))


def test_s13_duplicate_selector_under_other_name_is_refused(cfdocs: Path, src: Path) -> None:
    path = cfdocs / MANIFEST_REL
    data = json.loads(path.read_text(encoding="utf-8"))
    data["snippets"].append({
        "snippetName": "hand-named-copy", "sourceRepo": REPO, "sourceFilepath": SOURCE_FILE,
        "location": {"type": "fullFile"}, "description": "", "options": {"language": "yaml"},
    })
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _git(cfdocs, "commit", "-qam", "seed duplicate selector")
    before = tree_hash(cfdocs)
    assert_refused(cfdocs, before, run_add(cfdocs, *base_args(src)))


def test_s14_orphaned_output_is_refused(cfdocs: Path, src: Path) -> None:
    orphan = cfdocs / OUTPUT_REL / f"{FULL_NAME}.mdx"
    orphan.write_text("```yaml\nstale\n```", encoding="utf-8")
    _git(cfdocs, "add", "-A")
    _git(cfdocs, "commit", "-qm", "seed orphan")
    before = tree_hash(cfdocs)
    assert_refused(cfdocs, before, run_add(cfdocs, *base_args(src)))


def test_s16_source_checkout_is_untouched(cfdocs: Path, src: Path) -> None:
    before_status, before_tree = porcelain(src), tree_hash(src)
    assert_ok(run_add(cfdocs, *base_args(src), "--marker", "SWEEP"))
    assert porcelain(src) == before_status
    assert tree_hash(src) == before_tree
    assert not (src / "docs-output").exists()


def test_s17_no_prepare_or_docker_for_canton(cfdocs: Path, tmp_path: Path) -> None:
    src = make_source(tmp_path, "canton", "https://github.com/digital-asset/canton.git")
    shims = tmp_path / "shims"
    shims.mkdir()
    log = tmp_path / "invocations.log"
    for tool in ("sbt", "docker"):
        shim = shims / tool
        shim.write_text(f"#!/bin/sh\necho {tool} \"$@\" >> '{log}'\nexit 1\n", encoding="utf-8")
        shim.chmod(0o755)
    env = {**os.environ, "PATH": f"{shims}{os.pathsep}{os.environ['PATH']}"}
    result = run_add(cfdocs, "canton", "--source-dir", str(src), "--source", SOURCE_FILE, env=env)
    assert_ok(result)
    assert not log.exists(), f"prepare tooling was invoked:\n{log.read_text()}"


# --------------------------------------------------------------------------- writes
def test_s18_manifest_changes_by_exactly_one_alphabetically_placed_entry(cfdocs: Path, src: Path) -> None:
    before_text = (cfdocs / MANIFEST_REL).read_text(encoding="utf-8")
    before = json.loads(before_text)
    assert_ok(run_add(cfdocs, *base_args(src)))
    after_text = (cfdocs / MANIFEST_REL).read_text(encoding="utf-8")
    after = json.loads(after_text)

    names_before = [s["snippetName"] for s in before["snippets"]]
    expected_index = next((i for i, n in enumerate(names_before) if n > FULL_NAME), len(names_before))
    names_after = [s["snippetName"] for s in after["snippets"]]
    assert names_after == names_before[:expected_index] + [FULL_NAME] + names_before[expected_index:]
    assert {k: v for k, v in after.items() if k != "snippets"} == {k: v for k, v in before.items() if k != "snippets"}

    removed = [line[1:] for line in difflib.unified_diff(before_text.splitlines(), after_text.splitlines(), lineterm="", n=0) if line.startswith("-") and not line.startswith("---")]
    added = [line[1:] for line in difflib.unified_diff(before_text.splitlines(), after_text.splitlines(), lineterm="", n=0) if line.startswith("+") and not line.startswith("+++")]
    # The only tolerated rewrite of an existing line is gaining a trailing comma.
    for line in removed:
        assert line + "," in added, f"existing line altered beyond a trailing comma: {line!r}"
    assert len(added) - len(removed) >= 3, "inserted entry should span several lines"


def test_s19_mdx_equals_extractor_output_for_single_entry(cfdocs: Path, src: Path, tmp_path: Path) -> None:
    assert_ok(run_add(cfdocs, *base_args(src), "--marker", "SWEEP"))
    written = (cfdocs / OUTPUT_REL / f"{MARKER_NAME}.mdx").read_bytes()

    scratch = tmp_path / "extract"
    shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(".git"))
    helper_dir = scratch / "scripts" / "docs"
    helper_dir.mkdir(parents=True)
    shutil.copy2(CF_DOCS_ROOT / "scripts" / "helpers" / "generateOutputDocs.js", helper_dir / "generateOutputDocs.js")
    (helper_dir / "exportConfig.json").write_text(json.dumps({"snippets": [entry(cfdocs, MARKER_NAME)]}), encoding="utf-8")
    subprocess.run(["node", "scripts/docs/generateOutputDocs.js"], cwd=scratch, check=True, capture_output=True)
    reference = (scratch / "docs-output" / f"{MARKER_NAME}.mdx").read_bytes()

    assert written == reference
    assert written.startswith(b"```yaml")


def test_s21_printed_import_path_resolves(cfdocs: Path, src: Path) -> None:
    result = run_add(cfdocs, *base_args(src))
    assert_ok(result)
    m = re.search(r"""import\s+\w+\s+from\s+["'](/snippets/external/[^"']+\.mdx)["']""", result.stdout)
    assert m, f"no import line in stdout:\n{result.stdout}"
    assert (cfdocs / "docs-main" / m.group(1).lstrip("/")).is_file()


def test_s24_exactly_two_files_change(cfdocs: Path, src: Path) -> None:
    assert_ok(run_add(cfdocs, *base_args(src)))
    assert porcelain(cfdocs) == sorted([f" M {MANIFEST_REL}", f"?? {OUTPUT_REL / (FULL_NAME + '.mdx')}"])


# --------------------------------------------------------------------------- dry run
REFUSALS = {
    "unknown-repo": lambda src: ["nonesuch", "--source-dir", str(src), "--source", SOURCE_FILE],
    "missing-source": lambda src: base_args(src, "does/not/exist.yaml"),
    "bad-marker": lambda src: [*base_args(src), "--marker", "NOPE"],
    "unknown-extension": lambda src: base_args(src, "docs/weird.xyz"),
}


@pytest.mark.parametrize("case", list(REFUSALS))
def test_s22_dry_run_refuses_identically(cfdocs: Path, src: Path, case: str) -> None:
    args = REFUSALS[case](src)
    before = tree_hash(cfdocs)
    dry = run_add(cfdocs, *args, "--dry-run")
    assert tree_hash(cfdocs) == before
    real = run_add(cfdocs, *args)
    assert dry.returncode == real.returncode != 0
    assert dry.stderr == real.stderr


def test_s22_dry_run_succeeds_without_writing(cfdocs: Path, src: Path) -> None:
    before = tree_hash(cfdocs)
    dry = run_add(cfdocs, *base_args(src), "--dry-run")
    assert_ok(dry)
    assert tree_hash(cfdocs) == before
    assert_ok(run_add(cfdocs, *base_args(src)))


def test_s23_dry_run_diffs_apply_to_the_real_result(cfdocs: Path, src: Path, tmp_path: Path) -> None:
    dry = run_add(cfdocs, *base_args(src), "--dry-run")
    assert_ok(dry)
    start = next((i for i, line in enumerate(dry.stdout.splitlines()) if line.startswith(("diff ", "--- "))), None)
    assert start is not None, f"no unified diff in dry-run stdout:\n{dry.stdout}"
    patch_text = "\n".join(dry.stdout.splitlines()[start:]) + "\n"

    applied = False
    for strip in ("-p1", "-p0"):
        r = subprocess.run(["git", "apply", strip], cwd=cfdocs, input=patch_text, text=True, capture_output=True)
        if r.returncode == 0:
            applied = True
            break
    assert applied, f"dry-run diff did not apply:\n{r.stderr}\n{patch_text}"
    from_diff = tree_hash(cfdocs)

    other = make_cfdocs(tmp_path / "second")
    assert_ok(run_add(other, *base_args(src)))
    assert from_diff == tree_hash(other)

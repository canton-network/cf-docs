from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "generate_external_snippet_target.py"
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_load_sources_reads_external_snippet_manifest() -> None:
    module = load_script_module()

    sources = module.load_sources(module.DEFAULT_CONFIG)

    assert [source.key for source in sources] == [
        "canton",
        "cn-quickstart",
        "daml",
        "daml-shell",
        "dpm",
        "scribe",
        "splice",
    ]
    assert sources[0].repository == "DACH-NY/canton"
    assert sources[0].requires_docker is True


def test_generate_source_clones_checks_out_and_delegates_to_wrapper(
    monkeypatch, tmp_path: Path
) -> None:
    module = load_script_module()
    source = module.ExternalSnippetSource(
        key="example",
        label="Example snippets",
        repository="example/repo",
        ref="main",
        version="main",
        repo_arg="example",
        output_path="docs-main/snippets/external/example/main",
    )
    calls: list[tuple[tuple[str, ...], Path, bool]] = []

    def fake_run(command: list[str], *, cwd: Path, dry_run: bool = False) -> str:
        calls.append((tuple(command), cwd, dry_run))
        if command[:2] == ["git", "clone"]:
            checkout = Path(command[-1])
            (checkout / ".git").mkdir(parents=True)
        return ""

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module, "allow_direnv", lambda checkout, *, dry_run: None)
    monkeypatch.setattr(module, "check_docker", lambda source, *, dry_run: None)

    module.generate_source(source, cache_dir=tmp_path, dry_run=False)

    checkout = tmp_path / "example" / "repo"
    assert (("git", "clone", "https://github.com/example/repo.git", str(checkout)), module.REPO_ROOT, False) in calls
    assert any(call[0][:5] == ("git", "-c", "gc.auto=0", "-c", "maintenance.auto=false") for call in calls)
    assert any(
        call[0][:3] == (sys.executable, str(module.REPO_ROOT / "scripts" / "generate_external_snippets.py"), "example")
        and "--copy-output" in call[0]
        and "--replace-output" in call[0]
        for call in calls
    )

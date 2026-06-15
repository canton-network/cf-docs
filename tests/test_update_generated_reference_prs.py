from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "update_generated_reference_prs.py"
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


def test_targets_to_run_accepts_all() -> None:
    module = load_script_module()

    assert module.targets_to_run(["all"]) == module.UPDATE_TARGETS


def test_targets_to_run_requires_at_least_one_target() -> None:
    module = load_script_module()

    try:
        module.targets_to_run([])
    except ValueError as error:
        assert str(error) == "No update targets selected"
    else:
        raise AssertionError("Expected targets_to_run to reject an empty target selection")


def test_targets_to_run_rejects_mixed_all_and_target_keys() -> None:
    module = load_script_module()

    try:
        module.targets_to_run(["all", "version-dashboard"])
    except ValueError as error:
        assert str(error) == "'all' cannot be combined with specific update targets"
    else:
        raise AssertionError("Expected targets_to_run to reject mixed all and target keys")


def test_targets_to_run_accepts_dashboard_target_key() -> None:
    module = load_script_module()

    targets = module.targets_to_run(["version-dashboard"])

    assert [target.key for target in targets] == ["version-dashboard"]


def test_generated_clean_paths_include_target_paths_and_internal_output() -> None:
    module = load_script_module()

    clean_paths = module.generated_clean_paths()

    assert ".internal" in clean_paths
    assert "docs-main/snippets/generated/version-dashboard-data.mdx" in clean_paths


def test_body_markdown_includes_description_changes_and_validation() -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "version-dashboard")

    body = module.body_markdown(
        target=target,
        changes=["- DevNet Splice: 0.6.6 -> 0.6.7"],
    )

    assert body.startswith("Updates the committed Canton Network version dashboard data")
    assert "Version changes:\n- DevNet Splice: 0.6.6 -> 0.6.7" in body
    assert "- `npm run generate:version-compatibility-dashboard`" in body


def test_body_markdown_notes_when_no_versions_changed() -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "version-dashboard")

    body = module.body_markdown(target=target, changes=[])

    assert "Version changes:\n- No version values changed." in body


def test_parse_args_defaults_base_branch_and_repository_from_local_context(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_generated_reference_prs.py",
            "--targets",
            "all",
        ],
    )
    monkeypatch.setattr(
        module.pr_utils,
        "git",
        lambda *args, capture=False: "wallet-gateway-openrpc-refresh"
        if args == ("branch", "--show-current") and capture
        else "",
    )
    monkeypatch.setattr(module.pr_utils, "current_repository", lambda: "canton-network/cf-docs")

    args = module.parse_args()

    assert args.base_branch == "wallet-gateway-openrpc-refresh"
    assert args.repository == "canton-network/cf-docs"


def test_parse_args_accepts_explicit_base_branch_and_repository(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_generated_reference_prs.py",
            "--targets",
            "all",
            "--base-branch",
            "main",
            "--repository",
            "canton-network/cf-docs",
        ],
    )

    args = module.parse_args()

    assert args.base_branch == "main"
    assert args.repository == "canton-network/cf-docs"


def test_current_base_branch_uses_github_ref_name_for_detached_checkout(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setattr(
        module.pr_utils,
        "git",
        lambda *args, capture=False: "" if args == ("branch", "--show-current") and capture else "",
    )
    monkeypatch.setenv("GITHUB_REF_NAME", "main")

    assert module.current_base_branch() == "main"

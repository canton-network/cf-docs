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


def test_targets_to_run_preserves_declared_target_order_for_target_keys() -> None:
    module = load_script_module()

    targets = module.targets_to_run(["wallet-gateway-openrpc", "version-dashboard"])

    assert [target.key for target in targets] == ["version-dashboard", "wallet-gateway-openrpc"]


def test_generated_clean_paths_include_target_paths_and_internal_output() -> None:
    module = load_script_module()

    clean_paths = module.generated_clean_paths()

    assert ".internal" in clean_paths
    assert "docs-main/openapi/splice" in clean_paths
    assert "docs-main/openapi/json-ledger-api" in clean_paths
    assert "docs-main/reference/grpc-ledger-api-reference" in clean_paths
    assert "docs-main/reference/java" in clean_paths
    assert "docs-main/appdev/reference/daml-standard-library" in clean_paths
    assert "docs-main/reference/wallet-gateway-json-rpc" in clean_paths
    assert "docs-main/reference/typescript" in clean_paths
    assert "docs-main/snippets/generated/version-dashboard-data.mdx" in clean_paths


def test_body_markdown_includes_description_changes_and_validation() -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "wallet-gateway-openrpc")

    body = module.body_markdown(
        target=target,
        changes=["- Wallet Gateway OpenRPC publish_version: 0.25.0 -> 1.4.0"],
    )

    assert body.startswith("Updates the Wallet Gateway OpenRPC source pin")
    assert "Version changes:\n- Wallet Gateway OpenRPC publish_version: 0.25.0 -> 1.4.0" in body
    assert "- `npm run generate:wallet-gateway-openrpc-reference`" in body


def test_body_markdown_notes_when_no_versions_changed() -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "version-dashboard")

    body = module.body_markdown(target=target, changes=[])

    assert "Version changes:\n- No version values changed." in body


def test_summarize_target_changes_supports_versioned_source_configs(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "json-api-reference")
    before = tmp_path / "before.json"
    before.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    after = tmp_path / target.summary_path
    after.parent.mkdir(parents=True)
    after.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        module.summarize_version_changes,
        "versioned_source_config_changes",
        lambda before_path, after_path, *, label: [f"{label}:{before_path.name}:{after_path.name}"],
    )

    assert module.summarize_target_changes(target, before) == [
        "JSON Ledger API OpenAPI:before.json:source-artifacts.json"
    ]


def test_summarize_target_changes_supports_artifact_source_configs(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "ledger-bindings")
    before = tmp_path / "before.json"
    before.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    after = tmp_path / target.summary_path
    after.parent.mkdir(parents=True)
    after.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        module.summarize_version_changes,
        "artifact_source_config_changes",
        lambda before_path, after_path, *, label: [f"{label}:{before_path.name}:{after_path.name}"],
    )

    assert module.summarize_target_changes(target, before) == [
        "Java ledger bindings:before.json:source-artifacts.json"
    ]


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


def test_create_or_update_pull_request_signs_generated_commit(monkeypatch, tmp_path: Path) -> None:
    load_script_module()
    import generated_reference_pr_utils as pr_utils

    git_calls: list[tuple[str, ...]] = []
    gh_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str, capture: bool = False) -> str:
        git_calls.append(args)
        if args[:2] == ("status", "--porcelain"):
            return " M generated.mdx"
        return ""

    def fake_gh(*args: str, capture: bool = False) -> str:
        gh_calls.append(args)
        return ""

    monkeypatch.setattr(pr_utils, "git", fake_git)
    monkeypatch.setattr(pr_utils, "gh", fake_gh)
    monkeypatch.setattr(pr_utils, "push_branch", lambda branch: None)
    body_path = tmp_path / "body.md"
    body_path.write_text("body", encoding="utf-8")

    pr_utils.create_or_update_pull_request(
        title="Update generated docs",
        branch="generated/update",
        paths=("generated.mdx",),
        body_path=body_path,
        base_branch="main",
        repository="canton-network/cf-docs",
    )

    assert ("commit", "--signoff", "-m", "Update generated docs") in git_calls
    assert any(call[:2] == ("pr", "create") for call in gh_calls)

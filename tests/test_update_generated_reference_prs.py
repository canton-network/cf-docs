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


def test_update_targets_cover_all_generated_doc_surfaces() -> None:
    module = load_script_module()

    assert [target.key for target in module.UPDATE_TARGETS] == [
        "version-dashboard",
        "splice-openapi",
        "wallet-gateway-openrpc",
        "json-api-reference",
        "json-api-asyncapi-reference",
        "grpc-ledger-api-reference",
        "canton-protobuf-history",
        "ledger-bindings",
        "daml-standard-library",
        "typescript-bindings",
        "canton-metrics-reference",
    ]


def test_dashboard_target_runs_network_variable_tabs_after_dashboard_data_generation() -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "version-dashboard")

    assert target.source_update_commands == (
        ("nix-shell", "--run", "npm run generate:version-compatibility-dashboard"),
    )
    assert target.generate_commands == (
        ("nix-shell", "--run", "npm run generate:network-variable-tabs"),
    )
    assert target.source_update_paths == (
        "config/repo-version-config.json",
        "docs-main/snippets/generated/version-dashboard-data.mdx",
    )
    assert target.paths == (
        "config/repo-version-config.json",
        "docs-main/snippets/generated/version-dashboard-data.mdx",
        *module.NETWORK_VARIABLE_TAB_PAGES,
    )


def test_source_update_targets_skip_generation_when_source_is_unchanged(monkeypatch) -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "wallet-gateway-openrpc")
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(module, "reset_to_base", lambda base_sha: calls.append(("reset", base_sha)))
    monkeypatch.setattr(module.pr_utils, "write_base_file", lambda base_sha, path: Path("/tmp/before.json"))
    monkeypatch.setattr(module.pr_utils, "has_changes", lambda paths: False)
    monkeypatch.setattr(
        module.pr_utils,
        "close_stale_pull_request",
        lambda **kwargs: calls.append(("close", kwargs["branch"])),
    )
    monkeypatch.setattr(module, "create_or_update_pull_request", lambda **kwargs: calls.append(("pr",)))

    def fake_run(command: tuple[str, ...]) -> None:
        calls.append(command)

    monkeypatch.setattr(module.pr_utils, "run", fake_run)

    module.process_target(
        target=target,
        base_sha="base-sha",
        base_branch="main",
        repository="canton-network/cf-docs",
    )

    assert calls == [
        ("reset", "base-sha"),
        ("nix-shell", "--run", "npm run update:generated-reference-sources -- --source wallet-gateway-openrpc"),
        ("close", "generated-references/wallet-gateway-openrpc/update"),
    ]


def test_source_update_targets_generate_when_source_changed(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    target = next(target for target in module.UPDATE_TARGETS if target.key == "wallet-gateway-openrpc")
    calls: list[tuple[str, ...]] = []
    body_paths: list[Path] = []

    monkeypatch.setattr(module, "reset_to_base", lambda base_sha: calls.append(("reset", base_sha)))
    monkeypatch.setattr(module.pr_utils, "write_base_file", lambda base_sha, path: tmp_path / "before.json")
    monkeypatch.setattr(module.pr_utils, "has_changes", lambda paths: True)
    monkeypatch.setattr(module, "summarize_target_changes", lambda target, before_path: ["- changed"])

    def fake_pr(**kwargs) -> None:
        calls.append(("pr", kwargs["target"].key))
        body_paths.append(kwargs["body_path"])

    monkeypatch.setattr(module, "create_or_update_pull_request", fake_pr)

    def fake_run(command: tuple[str, ...]) -> None:
        calls.append(command)

    monkeypatch.setattr(module.pr_utils, "run", fake_run)

    module.process_target(
        target=target,
        base_sha="base-sha",
        base_branch="main",
        repository="canton-network/cf-docs",
    )

    assert calls == [
        ("reset", "base-sha"),
        ("nix-shell", "--run", "npm run update:generated-reference-sources -- --source wallet-gateway-openrpc"),
        ("nix-shell", "--run", "npm run generate:wallet-gateway-openrpc-reference"),
        ("pr", "wallet-gateway-openrpc"),
    ]
    assert body_paths


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
    assert "docs-main/global-synchronizer/deployment/validator-kubernetes.mdx" in clean_paths
    assert "docs-main/global-synchronizer/reference/canton-metrics.mdx" in clean_paths


def test_target_paths_exist_in_base_checkout() -> None:
    module = load_script_module()

    missing_paths = {
        target.key: [path for path in target.paths if not (REPO_ROOT / path).exists()]
        for target in module.UPDATE_TARGETS
    }

    assert {key: paths for key, paths in missing_paths.items() if paths} == {}


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


def test_parse_args_dry_run_does_not_require_repository_context(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_generated_reference_prs.py",
            "--targets",
            "all",
            "--dry-run",
        ],
    )
    monkeypatch.setattr(
        module.pr_utils,
        "current_repository",
        lambda: (_ for _ in ()).throw(AssertionError("repository should not be resolved")),
    )

    args = module.parse_args()

    assert args.dry_run is True
    assert args.repository == ""


def test_main_dry_run_lists_targets_without_git_or_gh(monkeypatch, capsys) -> None:
    module = load_script_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_generated_reference_prs.py",
            "--targets",
            "version-dashboard",
            "--dry-run",
        ],
    )
    monkeypatch.setattr(
        module.pr_utils,
        "git",
        lambda *args, capture=False: (_ for _ in ()).throw(AssertionError("git should not run")),
    )

    assert module.main() == 0
    output = capsys.readouterr().out
    assert "version-dashboard: Update generated docs" in output
    assert "source $ nix-shell --run npm run generate:version-compatibility-dashboard" in output
    assert "npm run generate:network-variable-tabs" in output


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
    assert not any(call[:1] == ("switch",) for call in git_calls)
    assert any(call[:2] == ("pr", "create") for call in gh_calls)


def test_create_or_update_pull_request_closes_stale_pr_when_no_changes(
    monkeypatch, tmp_path: Path
) -> None:
    load_script_module()
    import generated_reference_pr_utils as pr_utils

    gh_calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(pr_utils, "has_changes", lambda paths: False)

    def fake_gh(*args: str, capture: bool = False) -> str:
        gh_calls.append(args)
        if args[:2] == ("pr", "list"):
            return "825"
        return ""

    monkeypatch.setattr(pr_utils, "gh", fake_gh)
    body_path = tmp_path / "body.md"
    body_path.write_text("body", encoding="utf-8")

    pr_utils.create_or_update_pull_request(
        title="Update generated docs",
        branch="version-dashboard/update",
        paths=("docs-main/snippets/generated/version-dashboard-data.mdx",),
        body_path=body_path,
        base_branch="remaining-generated-reference-pr-targets",
        repository="canton-network/cf-docs",
    )

    assert any(call[:2] == ("pr", "close") and call[2] == "825" for call in gh_calls)
    assert any("--delete-branch" in call for call in gh_calls)


def test_push_branch_uses_full_ref_for_detached_head(monkeypatch) -> None:
    load_script_module()
    import generated_reference_pr_utils as pr_utils

    git_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str, capture: bool = False) -> str:
        git_calls.append(args)
        if args[:3] == ("ls-remote", "--heads", "origin"):
            return ""
        return ""

    monkeypatch.setattr(pr_utils, "git", fake_git)

    pr_utils.push_branch("version-dashboard/update")

    assert (
        "push",
        "origin",
        "HEAD:refs/heads/version-dashboard/update",
    ) in git_calls

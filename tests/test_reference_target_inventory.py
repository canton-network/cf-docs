from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_all_reference_docs  # noqa: E402
from reference_target_inventory import (  # noqa: E402
    load_reference_target_inventory,
    validate_runner_targets,
)


EXPECTED_TARGET_IDS = {
    "admin-api-protobuf",
    "daml-script",
    "daml-standard-library",
    "java-bindings",
    "json-ledger-api-asyncapi",
    "json-ledger-api-openapi",
    "ledger-api-grpc",
    "ledger-api-protobuf",
    "splice-openapi",
    "splice-token-standard-v2-daml",
    "typescript-bindings",
    "wallet-gateway-openrpc",
}


def runner_targets() -> dict[str, tuple[str, ...]]:
    return {
        job.script_path.relative_to(REPO_ROOT).as_posix(): tuple(sorted(job.target_ids))
        for job in generate_all_reference_docs.SCRIPT_JOBS
    }


def test_inventory_declares_every_current_reader_target() -> None:
    inventory = load_reference_target_inventory()

    assert set(inventory.by_id()) == EXPECTED_TARGET_IDS
    assert len(inventory.targets) == 12
    validate_runner_targets(inventory, runner_targets())


def test_every_target_converges_on_checked_in_mdx() -> None:
    inventory = load_reference_target_inventory()

    assert {target.target_page_renderer for target in inventory.targets} == {
        "x2mdx_mdx"
    }
    assert {
        target.id
        for target in inventory.targets
        if target.current_page_renderer == "native_mintlify_openapi"
    } == {"json-ledger-api-openapi", "splice-openapi"}


def test_scala_is_not_an_active_reader_target() -> None:
    inventory = load_reference_target_inventory()

    assert "scala-bindings" not in inventory.by_id()
    assert all(
        "scala" not in output_root
        for target in inventory.targets
        for output_root in target.reader_output_roots
    )


def test_inventory_rejects_runner_drift() -> None:
    inventory = load_reference_target_inventory()
    drifted = runner_targets()
    drifted["scripts/generate_new_reference.py"] = ("new-reference",)

    try:
        validate_runner_targets(inventory, drifted)
    except ValueError as error:
        assert "runner generators missing from inventory" in str(error)
    else:
        raise AssertionError("Expected aggregate-runner drift to fail validation")

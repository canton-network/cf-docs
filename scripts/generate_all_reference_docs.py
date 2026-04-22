#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import reference_nav


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "x2mdx"
DOCS_JSON_PATH = REPO_ROOT / "docs-main" / "docs.json"
DOCS_ROOT = DOCS_JSON_PATH.parent
API_REFERENCE_DROPDOWN = "API Reference"
LEGACY_PAGE_REFS = {
    "appdev/reference/json-api-reference",
    "appdev/reference/json-api-asyncapi-reference",
}


@dataclass(frozen=True)
class NavSlice:
    kind: Literal["ledger_child", "top_group", "nested_group"]
    labels: tuple[str, ...]


@dataclass(frozen=True)
class ScriptJob:
    script_path: Path
    nav_slice: NavSlice
    extra_args: tuple[str, ...] = ()


SCRIPT_JOBS = [
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_json_api_reference.py",
        nav_slice=NavSlice("ledger_child", (reference_nav.OPENAPI_GROUP,)),
    ),
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_json_api_asyncapi_reference.py",
        nav_slice=NavSlice("ledger_child", (reference_nav.ASYNCAPI_GROUP,)),
    ),
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_grpc_ledger_api_reference.py",
        nav_slice=NavSlice("ledger_child", (reference_nav.GRPC_GROUP,)),
        extra_args=(
            # The gRPC and protobuf wrappers both default to the same protobuf-history
            # cache tree, so parallel fanout gives the gRPC wrapper its own cache root.
            "--cache-dir",
            str(DEFAULT_CACHE_ROOT / "grpc-ledger-api-reference"),
            "--repo-dir",
            str(DEFAULT_CACHE_ROOT / "grpc-ledger-api-reference" / "repos" / "canton"),
        ),
    ),
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_ledger_bindings_api_reference.py",
        nav_slice=NavSlice("ledger_child", (reference_nav.BINDINGS_GROUP,)),
    ),
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_daml_standard_library_reference.py",
        nav_slice=NavSlice("top_group", ("Daml Standard Library",)),
    ),
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_canton_protobuf_history.py",
        nav_slice=NavSlice("ledger_child", (reference_nav.PROTOBUF_GROUP,)),
    ),
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_wallet_gateway_openrpc_reference.py",
        nav_slice=NavSlice("top_group", ("Wallet Gateway JSON-RPC",)),
    ),
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_splice_scan_openapi_reference.py",
        nav_slice=NavSlice("nested_group", ("Splice APIs", "Scan APIs")),
    ),
    ScriptJob(
        script_path=REPO_ROOT / "scripts" / "generate_typescript_bindings_reference.py",
        nav_slice=NavSlice("top_group", ("Daml TypeScript Bindings",)),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run every generated reference-doc wrapper in parallel, then consolidate docs.json once."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    return parser.parse_args()


def print_banner(*, index: int, total: int, job: ScriptJob) -> None:
    title = f"[{index}/{total}] {job.script_path.name}"
    print(f"\n=== {title} ===", flush=True)


def scratch_docs_json_path(job: ScriptJob) -> Path:
    return DOCS_ROOT / f".{job.script_path.stem}.docs.json"


def build_command(job: ScriptJob) -> list[str]:
    command = [sys.executable, str(job.script_path)]
    command.extend(job.extra_args)
    command.extend(["--docs-json", str(scratch_docs_json_path(job))])
    return command


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def dropdown_pages(docs: dict[str, Any], *, dropdown_label: str) -> list[Any]:
    navigation = docs.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json missing navigation object: {DOCS_JSON_PATH}")
    dropdowns = navigation.get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"docs.json navigation.dropdowns must be a list: {DOCS_JSON_PATH}")
    dropdown = next(
        (item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == dropdown_label),
        None,
    )
    if dropdown is None:
        raise ValueError(f"Dropdown not found in docs.json: {dropdown_label}")
    pages = dropdown.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Dropdown does not expose a pages list: {dropdown_label}")
    return pages


def find_group(items: list[Any], label: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and item.get("group") == label:
            return item
    return None


def require_group(items: list[Any], label: str, *, source_path: Path) -> dict[str, Any]:
    group = find_group(items, label)
    if group is None:
        raise ValueError(f"Group '{label}' not found in {source_path}")
    return group


def group_pages(group: dict[str, Any], *, source_path: Path) -> list[Any]:
    pages = group.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Group '{group.get('group')}' in {source_path} does not expose a pages list")
    return pages


def replace_group(items: list[Any], group: dict[str, Any]) -> None:
    label = group.get("group")
    if not isinstance(label, str) or not label:
        raise ValueError(f"Expected group label on item: {group}")
    for index, item in enumerate(items):
        if isinstance(item, dict) and item.get("group") == label:
            items[index] = copy.deepcopy(group)
            return
    items.append(copy.deepcopy(group))


def ensure_group(items: list[Any], label: str) -> dict[str, Any]:
    existing = find_group(items, label)
    if existing is not None:
        return existing
    group = {"group": label, "pages": []}
    items.append(group)
    return group


def prune_page_refs(node: object, page_refs: set[str]) -> object | None:
    if isinstance(node, list):
        items: list[object] = []
        for item in node:
            pruned = prune_page_refs(item, page_refs)
            if pruned is not None:
                items.append(pruned)
        return items
    if isinstance(node, dict):
        updated = {key: prune_page_refs(value, page_refs) for key, value in node.items()}
        if updated.get("group") and not updated.get("pages") and not updated.get("groups"):
            return None
        return updated
    if isinstance(node, str) and node in page_refs:
        return None
    return node


def merge_nav_slice(*, final_docs: dict[str, Any], scratch_docs: dict[str, Any], nav_slice: NavSlice, scratch_path: Path) -> None:
    final_pages = dropdown_pages(final_docs, dropdown_label=API_REFERENCE_DROPDOWN)
    scratch_pages = dropdown_pages(scratch_docs, dropdown_label=API_REFERENCE_DROPDOWN)

    if nav_slice.kind == "ledger_child":
        ledger_parent = require_group(
            scratch_pages,
            reference_nav.LEDGER_API_PARENT_GROUP,
            source_path=scratch_path,
        )
        child_group = require_group(
            group_pages(ledger_parent, source_path=scratch_path),
            nav_slice.labels[0],
            source_path=scratch_path,
        )
        final_ledger_parent = ensure_group(final_pages, reference_nav.LEDGER_API_PARENT_GROUP)
        replace_group(group_pages(final_ledger_parent, source_path=DOCS_JSON_PATH), child_group)
        return

    if nav_slice.kind == "top_group":
        replace_group(
            final_pages,
            require_group(scratch_pages, nav_slice.labels[0], source_path=scratch_path),
        )
        return

    if nav_slice.kind == "nested_group":
        parent_group = require_group(scratch_pages, nav_slice.labels[0], source_path=scratch_path)
        child_group = require_group(
            group_pages(parent_group, source_path=scratch_path),
            nav_slice.labels[1],
            source_path=scratch_path,
        )
        final_parent = ensure_group(final_pages, nav_slice.labels[0])
        replace_group(group_pages(final_parent, source_path=DOCS_JSON_PATH), child_group)
        return

    raise ValueError(f"Unsupported nav slice kind: {nav_slice.kind}")


def prepare_scratch_docs_json_files() -> None:
    baseline = DOCS_JSON_PATH.read_text(encoding="utf-8")
    for job in SCRIPT_JOBS:
        scratch_path = scratch_docs_json_path(job)
        scratch_path.write_text(baseline, encoding="utf-8")


def cleanup_scratch_docs_json_files() -> None:
    for job in SCRIPT_JOBS:
        scratch_path = scratch_docs_json_path(job)
        if scratch_path.exists():
            scratch_path.unlink()


def consolidate_docs_json() -> None:
    final_docs = load_json(DOCS_JSON_PATH)
    for job in SCRIPT_JOBS:
        merge_nav_slice(
            final_docs=final_docs,
            scratch_docs=load_json(scratch_docs_json_path(job)),
            nav_slice=job.nav_slice,
            scratch_path=scratch_docs_json_path(job),
        )

    cleaned = prune_page_refs(final_docs, LEGACY_PAGE_REFS)
    if not isinstance(cleaned, dict):
        raise ValueError(f"Expected cleaned docs.json object for {DOCS_JSON_PATH}")
    write_json(DOCS_JSON_PATH, cleaned)
    reference_nav.regroup_ledger_api_nav(
        docs_json_path=DOCS_JSON_PATH,
        dropdown_label=API_REFERENCE_DROPDOWN,
    )


def main() -> int:
    args = parse_args()
    total = len(SCRIPT_JOBS)
    running_processes: list[tuple[ScriptJob, subprocess.Popen[bytes]]] = []
    prepared_scratch_docs = False

    try:
        for index, job in enumerate(SCRIPT_JOBS, start=1):
            command = build_command(job)
            print_banner(index=index, total=total, job=job)
            print("Command:", shlex.join(command), flush=True)
            if args.dry_run:
                continue

            if not prepared_scratch_docs:
                cleanup_scratch_docs_json_files()
                prepare_scratch_docs_json_files()
                prepared_scratch_docs = True
            running_processes.append((job, subprocess.Popen(command, cwd=REPO_ROOT)))

        if args.dry_run:
            print(f"\nDry run complete: {total} commands listed.", flush=True)
            return 0

        failures: list[tuple[Path, int]] = []
        for job, process in running_processes:
            return_code = process.wait()
            if return_code == 0:
                print(f"[{job.script_path.name}] completed successfully.", flush=True)
                continue
            print(f"[{job.script_path.name}] failed with exit code {return_code}.", flush=True)
            failures.append((job.script_path, return_code))

        if failures:
            failed_names = ", ".join(script_path.name for script_path, _return_code in failures)
            print(f"\nParallel reference-doc run finished with failures: {failed_names}", flush=True)
            return failures[0][1]

        consolidate_docs_json()
        print(
            f"\nCompleted {total} reference-doc generation steps with centralized docs.json consolidation.",
            flush=True,
        )
        return 0
    finally:
        if prepared_scratch_docs:
            cleanup_scratch_docs_json_files()


if __name__ == "__main__":
    raise SystemExit(main())

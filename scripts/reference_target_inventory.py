from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY_PATH = REPO_ROOT / "config" / "x2mdx" / "reference-targets.json"
TARGET_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

HistoryMode = Literal["snapshots", "authored", "unavailable"]
PageRenderer = Literal["native_mintlify_openapi", "x2mdx_mdx"]
ReferenceFormat = Literal[
    "asyncapi",
    "daml_json",
    "grpc",
    "jvm_docs",
    "openapi",
    "openrpc",
    "protobuf",
    "typedoc",
]
RoutePolicy = Literal["preserve_or_redirect"]
VersionPolicy = Literal[
    "configured_publish_version",
    "configured_publish_version_per_package",
    "latest_configured_version_per_artifact",
    "latest_selected_release",
]


@dataclass(frozen=True)
class ReferenceTarget:
    id: str
    title: str
    generator: str
    format: ReferenceFormat
    owner: str
    item_boundary: str
    identity_policy: str
    history_mode: HistoryMode
    version_policy: VersionPolicy
    source_config: str
    reader_output_roots: tuple[str, ...]
    history_report_paths: tuple[str, ...]
    source_artifact_roots: tuple[str, ...]
    current_page_renderer: PageRenderer
    target_page_renderer: PageRenderer
    route_policy: RoutePolicy
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceTargetInventory:
    schema_version: int
    targets: tuple[ReferenceTarget, ...]

    def by_id(self) -> dict[str, ReferenceTarget]:
        return {target.id: target for target in self.targets}

    def target_ids_by_generator(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for target in self.targets:
            grouped.setdefault(target.generator, []).append(target.id)
        return {
            generator: tuple(sorted(target_ids))
            for generator, target_ids in sorted(grouped.items())
        }


def _required_string(payload: dict[str, object], field: str, *, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{field} must be a non-empty string")
    return value


def _string_tuple(
    payload: dict[str, object],
    field: str,
    *,
    context: str,
    required: bool,
) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{context}.{field} must be a list of non-empty strings")
    if required and not value:
        raise ValueError(f"{context}.{field} must not be empty")
    return tuple(value)


def _literal(
    payload: dict[str, object],
    field: str,
    allowed: set[str],
    *,
    context: str,
) -> str:
    value = _required_string(payload, field, context=context)
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{context}.{field} must be one of: {choices}")
    return value


def _validate_repo_path(
    path: str, *, field: str, context: str, prefix: str | None = None
) -> None:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(
            f"{context}.{field} must be a repository-relative path: {path}"
        )
    if prefix is not None and not path.startswith(prefix):
        raise ValueError(f"{context}.{field} must start with {prefix}: {path}")


def _parse_target(payload: object, *, index: int, repo_root: Path) -> ReferenceTarget:
    context = f"targets[{index}]"
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be an object")

    target_id = _required_string(payload, "id", context=context)
    if not TARGET_ID_RE.fullmatch(target_id):
        raise ValueError(f"{context}.id must be lower kebab case: {target_id}")

    generator = _required_string(payload, "generator", context=context)
    source_config = _required_string(payload, "source_config", context=context)
    reader_output_roots = _string_tuple(
        payload,
        "reader_output_roots",
        context=context,
        required=True,
    )
    history_report_paths = _string_tuple(
        payload,
        "history_report_paths",
        context=context,
        required=True,
    )
    source_artifact_roots = _string_tuple(
        payload,
        "source_artifact_roots",
        context=context,
        required=False,
    )
    limitations_raw = payload.get("limitations", [])
    if not isinstance(limitations_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in limitations_raw
    ):
        raise ValueError(f"{context}.limitations must be a list of non-empty strings")

    _validate_repo_path(
        generator, field="generator", context=context, prefix="scripts/"
    )
    _validate_repo_path(
        source_config, field="source_config", context=context, prefix="config/"
    )
    if not (repo_root / generator).is_file():
        raise ValueError(f"{context}.generator does not exist: {generator}")
    if not (repo_root / source_config).is_file():
        raise ValueError(f"{context}.source_config does not exist: {source_config}")
    for field, paths in (
        ("reader_output_roots", reader_output_roots),
        ("history_report_paths", history_report_paths),
        ("source_artifact_roots", source_artifact_roots),
    ):
        for path in paths:
            _validate_repo_path(path, field=field, context=context, prefix="docs-main/")

    history_mode = _literal(
        payload,
        "history_mode",
        {"snapshots", "authored", "unavailable"},
        context=context,
    )
    version_policy = _literal(
        payload,
        "version_policy",
        {
            "configured_publish_version",
            "configured_publish_version_per_package",
            "latest_configured_version_per_artifact",
            "latest_selected_release",
        },
        context=context,
    )
    current_page_renderer = _literal(
        payload,
        "current_page_renderer",
        {"native_mintlify_openapi", "x2mdx_mdx"},
        context=context,
    )
    target_page_renderer = _literal(
        payload,
        "target_page_renderer",
        {"native_mintlify_openapi", "x2mdx_mdx"},
        context=context,
    )
    route_policy = _literal(
        payload,
        "route_policy",
        {"preserve_or_redirect"},
        context=context,
    )
    reference_format = _literal(
        payload,
        "format",
        {
            "asyncapi",
            "daml_json",
            "grpc",
            "jvm_docs",
            "openapi",
            "openrpc",
            "protobuf",
            "typedoc",
        },
        context=context,
    )
    if (
        current_page_renderer == "native_mintlify_openapi"
        and reference_format != "openapi"
    ):
        raise ValueError(
            f"{context} can use native_mintlify_openapi only for format=openapi"
        )

    return ReferenceTarget(
        id=target_id,
        title=_required_string(payload, "title", context=context),
        generator=generator,
        format=cast(ReferenceFormat, reference_format),
        owner=_required_string(payload, "owner", context=context),
        item_boundary=_required_string(payload, "item_boundary", context=context),
        identity_policy=_required_string(payload, "identity_policy", context=context),
        history_mode=cast(HistoryMode, history_mode),
        version_policy=cast(VersionPolicy, version_policy),
        source_config=source_config,
        reader_output_roots=reader_output_roots,
        history_report_paths=history_report_paths,
        source_artifact_roots=source_artifact_roots,
        current_page_renderer=cast(PageRenderer, current_page_renderer),
        target_page_renderer=cast(PageRenderer, target_page_renderer),
        route_policy=cast(RoutePolicy, route_policy),
        limitations=tuple(limitations_raw),
    )


def load_reference_target_inventory(
    path: Path = DEFAULT_INVENTORY_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> ReferenceTargetInventory:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Reference target inventory must be an object: {path}")
    schema_version = payload.get("schema_version")
    if schema_version != 1:
        raise ValueError(
            f"Unsupported reference target inventory schema_version: {schema_version}"
        )
    targets_raw = payload.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ValueError(
            "Reference target inventory must contain a non-empty targets list"
        )

    targets = tuple(
        _parse_target(target, index=index, repo_root=repo_root)
        for index, target in enumerate(targets_raw)
    )
    target_ids = [target.id for target in targets]
    if len(target_ids) != len(set(target_ids)):
        duplicates = sorted(
            {target_id for target_id in target_ids if target_ids.count(target_id) > 1}
        )
        raise ValueError(f"Duplicate reference target IDs: {', '.join(duplicates)}")
    if any(target.target_page_renderer != "x2mdx_mdx" for target in targets):
        raise ValueError(
            "Every reference target must converge on target_page_renderer=x2mdx_mdx"
        )

    return ReferenceTargetInventory(schema_version=schema_version, targets=targets)


def validate_runner_targets(
    inventory: ReferenceTargetInventory,
    runner_targets: dict[str, tuple[str, ...]],
) -> None:
    inventory_targets = inventory.target_ids_by_generator()
    if runner_targets == inventory_targets:
        return

    runner_generators = set(runner_targets)
    inventory_generators = set(inventory_targets)
    missing_generators = sorted(runner_generators - inventory_generators)
    orphan_generators = sorted(inventory_generators - runner_generators)
    mismatched_generators = sorted(
        generator
        for generator in runner_generators & inventory_generators
        if tuple(sorted(runner_targets[generator])) != inventory_targets[generator]
    )
    details: list[str] = []
    if missing_generators:
        details.append(
            f"runner generators missing from inventory: {', '.join(missing_generators)}"
        )
    if orphan_generators:
        details.append(
            f"inventory generators missing from runner: {', '.join(orphan_generators)}"
        )
    if mismatched_generators:
        details.append(f"target ownership differs: {', '.join(mismatched_generators)}")
    raise ValueError(
        "Reference target inventory does not match aggregate runner; "
        + "; ".join(details)
    )

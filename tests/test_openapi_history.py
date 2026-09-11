from __future__ import annotations

import pytest

from x2mdx.history import (
    HistoryEventKind,
    IdentityConfidence,
    LifecycleState,
    SourceArtifact,
    VersionSelectionPolicy,
    history_events_for_item,
    validate_history_report,
)
from x2mdx.openapi import OpenAPIHistoryScope, build_openapi_history_report


def operation(
    operation_id: str | None,
    *,
    deprecated: bool = False,
    remove_as_of: str | None = None,
    replaces: str | None = None,
    state: str | None = None,
    response_type: str = "string",
) -> dict[str, object]:
    value: dict[str, object] = {
        "responses": {
            "200": {
                "description": "Success",
                "content": {"application/json": {"schema": {"type": response_type}}},
            }
        }
    }
    if operation_id is not None:
        value["operationId"] = operation_id
    if deprecated:
        value["deprecated"] = True
    if remove_as_of is not None:
        value["x-remove-as-of"] = remove_as_of
    if replaces is not None:
        value["x-replaces"] = replaces
    if state is not None:
        value["x-state"] = state
    return value


def test_openapi_report_normalizes_current_removed_and_fallback_operations() -> None:
    first = {
        "openapi": "3.0.3",
        "paths": {
            "/old": {
                "post": operation(
                    "oldOperation",
                    deprecated=True,
                    remove_as_of="2.0.0",
                )
            },
            "/moving": {"get": operation("movingOperation")},
            "/fallback": {"get": operation(None)},
        },
    }
    second = {
        "openapi": "3.0.3",
        "paths": {
            "/moved": {"get": operation("movingOperation", response_type="object")},
            "/replacement": {
                "post": operation(
                    "newOperation",
                    replaces="oldOperation",
                    state="stable",
                )
            },
            "/fallback": {"get": operation(None)},
        },
    }
    report = build_openapi_history_report(
        surface_id="example-openapi",
        title="Example OpenAPI",
        configured_scope="Public operations.",
        scopes=(
            OpenAPIHistoryScope(
                id="public.yaml",
                specs_by_version={"1.0.0": first, "2.0.0": second},
                current_routes={
                    ("get", "/moved"): "/reference/get-moved",
                    ("post", "/replacement"): "/reference/post-replacement",
                    ("get", "/fallback"): "/reference/get-fallback",
                },
            ),
        ),
        comparison_versions=("1.0.0", "2.0.0"),
        publish_version="2.0.0",
        source_artifacts=(
            SourceArtifact("1.0.0", "https://example.com/1.0.0.tgz", "v1.0.0"),
            SourceArtifact("2.0.0", "https://example.com/2.0.0.tgz", "v2.0.0"),
        ),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
    )

    validate_history_report(report)
    items = report.items_by_id()

    removed = items["public.yaml::oldOperation"]
    assert removed.current_present is False
    assert removed.route is None
    assert removed.last_seen == "1.0.0"
    assert removed.observed_removal == "2.0.0"
    assert removed.remove_as_of == "2.0.0"
    assert removed.lifecycle_state == LifecycleState.DEPRECATED
    assert removed.replacement_edges[0].to_item_id == "public.yaml::newOperation"

    moved = items["public.yaml::movingOperation"]
    assert moved.route == "/reference/get-moved"
    assert moved.last_changed == "2.0.0"
    assert "moved from GET /moving to GET /moved" in moved.changes[0].summary
    assert [
        event.kind
        for event in history_events_for_item(
            moved,
            comparison_versions=report.comparison_versions,
        )
    ] == [HistoryEventKind.CHANGED]

    successor = items["public.yaml::newOperation"]
    assert successor.lifecycle_state == LifecycleState.STABLE
    assert successor.replacement_edges[0].from_item_id == "public.yaml::oldOperation"
    assert HistoryEventKind.INTRODUCED in {
        event.kind
        for event in history_events_for_item(
            successor,
            comparison_versions=report.comparison_versions,
        )
    }

    fallback = items["public.yaml::GET /fallback"]
    assert fallback.identity_confidence == IdentityConfidence.FALLBACK
    assert len(fallback.identity_evidence) == 2
    assert "METHOD path" in report.limitations[-1]


def test_openapi_report_scopes_reused_operation_ids_by_specification() -> None:
    spec = {
        "openapi": "3.0.3",
        "paths": {"/status": {"get": operation("getStatus")}},
    }
    report = build_openapi_history_report(
        surface_id="combined",
        title="Combined",
        configured_scope="Two specifications.",
        scopes=(
            OpenAPIHistoryScope(
                id="one.yaml",
                specs_by_version={"1.0.0": spec},
                current_routes={("get", "/status"): "/reference/one/status"},
            ),
            OpenAPIHistoryScope(
                id="two.yaml",
                specs_by_version={"1.0.0": spec},
                current_routes={("get", "/status"): "/reference/two/status"},
            ),
        ),
        comparison_versions=("1.0.0",),
        publish_version="1.0.0",
        source_artifacts=(
            SourceArtifact("1.0.0", "https://example.com/1.0.0.tgz", "v1.0.0"),
        ),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
    )

    validate_history_report(report)
    assert {item.id for item in report.items} == {
        "one.yaml::getStatus",
        "two.yaml::getStatus",
    }


def test_openapi_report_uses_next_available_spec_for_removal_evidence() -> None:
    first = {
        "openapi": "3.0.3",
        "paths": {"/legacy": {"get": operation("legacyOperation")}},
    }
    last = {"openapi": "3.0.3", "paths": {}}
    report = build_openapi_history_report(
        surface_id="example",
        title="Example",
        configured_scope="One specification with a missing bundle member.",
        scopes=(
            OpenAPIHistoryScope(
                id="public.yaml",
                specs_by_version={"1.0.0": first, "2.0.0": last},
                current_routes={},
            ),
        ),
        comparison_versions=("1.0.0", "1.1.0", "2.0.0"),
        publish_version="2.0.0",
        source_artifacts=(
            SourceArtifact("1.0.0", "https://example.com/1.0.0.tgz"),
            SourceArtifact("1.1.0", "https://example.com/1.1.0.tgz"),
            SourceArtifact("2.0.0", "https://example.com/2.0.0.tgz"),
        ),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
    )

    validate_history_report(report)
    removed = report.items_by_id()["public.yaml::legacyOperation"]
    assert removed.observed_removal == "2.0.0"
    assert (
        "public.yaml is absent from 1 selected release snapshot"
        in report.limitations[0]
    )


def test_openapi_report_correlates_missing_current_id_at_a_stable_location() -> None:
    first = {
        "openapi": "3.0.3",
        "paths": {"/status": {"get": operation("getStatus")}},
    }
    current = {
        "openapi": "3.0.3",
        "paths": {"/status": {"get": operation(None)}},
    }
    report = build_openapi_history_report(
        surface_id="example",
        title="Example",
        configured_scope="One specification.",
        scopes=(
            OpenAPIHistoryScope(
                id="public.yaml",
                specs_by_version={"1.0.0": first, "2.0.0": current},
                current_routes={("get", "/status"): "/reference/status"},
            ),
        ),
        comparison_versions=("1.0.0", "2.0.0"),
        publish_version="2.0.0",
        source_artifacts=(
            SourceArtifact("1.0.0", "https://example.com/1.0.0.tgz"),
            SourceArtifact("2.0.0", "https://example.com/2.0.0.tgz"),
        ),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
    )

    validate_history_report(report)
    item = report.items_by_id()["public.yaml::getStatus"]
    assert item.current_present is True
    assert item.route == "/reference/status"
    assert item.identity_confidence == IdentityConfidence.FALLBACK


def test_openapi_report_rejects_disappear_then_reappear_continuity() -> None:
    present = {
        "openapi": "3.0.3",
        "paths": {"/status": {"get": operation("getStatus")}},
    }
    missing = {"openapi": "3.0.3", "paths": {}}

    with pytest.raises(ValueError, match="disappears and later reappears"):
        build_openapi_history_report(
            surface_id="example",
            title="Example",
            configured_scope="One specification.",
            scopes=(
                OpenAPIHistoryScope(
                    id="public.yaml",
                    specs_by_version={
                        "1.0.0": present,
                        "1.1.0": missing,
                        "2.0.0": present,
                    },
                    current_routes={("get", "/status"): "/reference/status"},
                ),
            ),
            comparison_versions=("1.0.0", "1.1.0", "2.0.0"),
            publish_version="2.0.0",
            source_artifacts=(
                SourceArtifact("1.0.0", "https://example.com/1.0.0.tgz"),
                SourceArtifact("1.1.0", "https://example.com/1.1.0.tgz"),
                SourceArtifact("2.0.0", "https://example.com/2.0.0.tgz"),
            ),
            version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
        )


def test_openapi_report_does_not_carry_a_cancelled_removal_schedule_forward() -> None:
    scheduled = {
        "openapi": "3.0.3",
        "paths": {"/status": {"get": operation("getStatus", remove_as_of="3.0.0")}},
    }
    current = {
        "openapi": "3.0.3",
        "paths": {"/status": {"get": operation("getStatus")}},
    }
    report = build_openapi_history_report(
        surface_id="example",
        title="Example",
        configured_scope="One specification.",
        scopes=(
            OpenAPIHistoryScope(
                id="public.yaml",
                specs_by_version={"1.0.0": scheduled, "2.0.0": current},
                current_routes={("get", "/status"): "/reference/status"},
            ),
        ),
        comparison_versions=("1.0.0", "2.0.0"),
        publish_version="2.0.0",
        source_artifacts=(
            SourceArtifact("1.0.0", "https://example.com/1.0.0.tgz"),
            SourceArtifact("2.0.0", "https://example.com/2.0.0.tgz"),
        ),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
    )

    validate_history_report(report)
    item = report.items_by_id()["public.yaml::getStatus"]
    assert item.remove_as_of is None
    assert item.remove_as_of_evidence is None

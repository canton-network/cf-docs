"""Render AsyncAPI lifecycle reports into Mintlify-like collection and operation pages."""

from __future__ import annotations

import json
import re
from functools import cmp_to_key
from pathlib import Path
from typing import Any

from x2mdx.asyncapi.history import asyncapi_item_id
from x2mdx.asyncapi.models import (
    AsyncApiActionDetail,
    AsyncApiChannelLifecycle,
    AsyncApiReport,
    AsyncApiSchemaVariantDetail,
)
from x2mdx.history.events import history_events_for_item
from x2mdx.history.models import (
    HistoryEvent,
    HistoryEventKind,
    HistoryItem,
    SurfaceHistoryReport,
)
from x2mdx.history.versioning import compare_versions
from x2mdx.reference_pages import (
    ReferenceBadge,
    ReferenceBreadcrumb,
    ReferenceCard,
    ReferenceChange,
    ReferenceCollectionPage,
    ReferenceExample,
    ReferenceMetaItem,
    ReferenceOperationPage,
    ReferencePanel,
    ReferenceSchema,
    ReferenceSection,
    compact_text,
    markdown_page_from_template,
    relative_page_ref,
    reference_badges_for_history_events,
    reference_badges_for_history_item,
    render_collection_page,
    render_operation_page,
    safe_markdown_text,
    schema_from_sample,
)


def slugify(value: str) -> str:
    output = value.lower()
    output = re.sub(r"[^a-z0-9]+", "-", output)
    output = re.sub(r"-{2,}", "-", output).strip("-")
    return output


def channel_page_path(output_dir: Path, channel: AsyncApiChannelLifecycle) -> Path:
    return output_dir / "channels" / f"{slugify(channel.channel)}.mdx"


def operation_page_path(output_dir: Path, channel: AsyncApiChannelLifecycle, action_name: str) -> Path:
    return output_dir / "operations" / slugify(channel.channel) / f"{slugify(action_name)}.mdx"


def page_ref(from_path: Path, to_path: Path) -> str:
    return relative_page_ref(from_path, to_path)


def lifecycle_state_label(state: str | None) -> str | None:
    if not state:
        return None
    return state.title()


def lifecycle_state_tone(state: str | None) -> str:
    return {
        "alpha": "changed",
        "beta": "neutral",
        "stable": "added",
        "deprecated": "removed",
    }.get(state or "", "neutral")


def lifecycle_badges(
    channel: AsyncApiChannelLifecycle,
    *,
    item: HistoryItem | None = None,
    events: list[HistoryEvent] | None = None,
    comparison_versions: tuple[str, ...] = (),
    linked: bool = True,
) -> list[ReferenceBadge]:
    if item is not None:
        return reference_badges_for_history_item(
            item,
            kind_label="WebSocket",
            comparison_versions=comparison_versions,
            linked=linked,
        )
    channel_events = events or legacy_channel_history_events(channel)
    return reference_badges_for_history_events(
        channel_events,
        kind_label="WebSocket",
        linked=linked,
    )


def legacy_channel_history_events(
    channel: AsyncApiChannelLifecycle,
) -> list[HistoryEvent]:
    events = [
        HistoryEvent(
            kind=HistoryEventKind.CHANGED,
            version=str(entry["version"]),
            label="Updated",
            details=tuple(str(change) for change in entry["changes"]),
            evidence=(),
        )
        for entry in reversed(channel.change_details)
    ]
    if channel.lifecycle_state == "deprecated":
        events.append(
            HistoryEvent(
                kind=HistoryEventKind.DEPRECATED,
                version=(channel.changed_in_versions[-1] if channel.changed_in_versions else channel.introduced_version),
                label="Deprecated",
                details=(),
                evidence=(),
            )
        )
    events.append(
        HistoryEvent(
            kind=HistoryEventKind.INTRODUCED,
            version=channel.introduced_version,
            label="Added",
            details=(),
            evidence=(),
        )
    )
    return events


def channel_history_events(
    items: list[HistoryItem],
    *,
    comparison_versions: tuple[str, ...],
) -> list[HistoryEvent]:
    combined: dict[tuple[HistoryEventKind, str], HistoryEvent] = {}
    for item in items:
        action = item.id.rsplit("#", 1)[-1]
        for event in history_events_for_item(
            item,
            comparison_versions=comparison_versions,
        ):
            key = (event.kind, event.version)
            details = tuple(
                f"{action}: {detail}" for detail in event.details
            )
            existing = combined.get(key)
            if existing is None:
                combined[key] = HistoryEvent(
                    kind=event.kind,
                    version=event.version,
                    label=event.label,
                    details=details,
                    evidence=event.evidence,
                )
            else:
                combined[key] = HistoryEvent(
                    kind=existing.kind,
                    version=existing.version,
                    label=existing.label,
                    details=tuple(dict.fromkeys((*existing.details, *details))),
                    evidence=tuple(dict.fromkeys((*existing.evidence, *event.evidence))),
                )

    priority = {
        HistoryEventKind.REMOVE_AS_OF: 0,
        HistoryEventKind.DEPRECATED: 1,
        HistoryEventKind.CHANGED: 2,
        HistoryEventKind.INTRODUCED: 3,
        HistoryEventKind.REPLACEMENT: 4,
    }

    def compare(left: HistoryEvent, right: HistoryEvent) -> int:
        version_comparison = compare_versions(
            left.version,
            right.version,
            known_order=comparison_versions,
        )
        if version_comparison:
            return -version_comparison
        return priority[left.kind] - priority[right.kind]

    return sorted(combined.values(), key=cmp_to_key(compare))


def lifecycle_meta_items(channel: AsyncApiChannelLifecycle) -> list[ReferenceMetaItem]:
    items: list[ReferenceMetaItem] = []
    state_label = lifecycle_state_label(channel.lifecycle_state)
    if state_label:
        items.append(ReferenceMetaItem("Lifecycle", state_label))
    if channel.replaces:
        items.append(ReferenceMetaItem("Replaces", channel.replaces))
    return items


def channel_summary(channel: AsyncApiChannelLifecycle) -> str:
    description = str(channel.latest.get("description") or "").strip()
    if description:
        return compact_text(description, limit=180)
    action_names = list(channel.latest.get("action_names") or [])
    if action_names:
        return ", ".join(action_names)
    return "AsyncAPI channel"


def channel_short_label(channel_name: str) -> str:
    parts = [part for part in channel_name.strip("/").split("/") if part]
    label = parts[-1] if parts else channel_name.strip("/") or channel_name
    return label.replace("-", " ").replace("_", " ")


def action_display_title(channel: AsyncApiChannelLifecycle, action_name: str) -> str:
    return f"{action_name.title()} {channel_short_label(channel.channel)}"


def action_schema(action: AsyncApiActionDetail, *, anchor: str):
    message = action["message"]
    sample = message.get("sample")
    required_fields = list(message.get("required_fields") or [])
    variant_schemas = [schema_from_variant(variant) for variant in message.get("variants") or []]
    if sample is None and not required_fields and not variant_schemas:
        return None
    if variant_schemas:
        return ReferenceSchema(
            name=str(message.get("name") or action["action"]),
            summary=str(message.get("payload_schema") or "-"),
            description=str(action.get("description") or ""),
            anchor=anchor,
            variants=variant_schemas,
        )
    return schema_from_sample(
        name=str(message.get("name") or action["action"]),
        sample=sample,
        required_fields=required_fields,
        summary=str(message.get("payload_schema") or "-"),
        description=str(action.get("description") or ""),
        anchor=anchor,
    )


def schema_from_variant(variant: AsyncApiSchemaVariantDetail) -> ReferenceSchema:
    return schema_from_sample(
        name=str(variant.get("name") or "Variant"),
        sample=variant.get("sample"),
        required_fields=list(variant.get("required_fields") or []),
        summary=str(variant.get("payload_schema") or "-"),
        variants=[schema_from_variant(child) for child in variant.get("variants") or []],
    )


def wscat_example(action: AsyncApiActionDetail) -> str:
    sample = action["message"].get("sample")
    if action["action"] == "publish" and sample is not None:
        return "\n".join(
            [
                "npx wscat \\",
                "  -c <WEBSOCKET_URL> \\",
                f"  -x '{json.dumps(sample, ensure_ascii=False)}' \\",
                "  -w -1",
            ]
        )
    return "npx wscat -c <WEBSOCKET_URL>"


def build_action_operation(
    channel: AsyncApiChannelLifecycle,
    action: AsyncApiActionDetail,
    *,
    output_dir: Path | None,
    history_item: HistoryItem | None = None,
    comparison_versions: tuple[str, ...] | None = None,
) -> ReferenceOperationPage:
    is_publish = action["action"] == "publish"
    schema = action_schema(action, anchor=f"schema-{slugify(channel.channel)}-{slugify(action['action'])}")
    examples = [ReferenceExample(title="wscat", body=wscat_example(action), language="bash")]
    if action["message"].get("sample") is not None:
        examples.append(
            ReferenceExample(
                title="message",
                body=json.dumps(action["message"]["sample"], indent=2, ensure_ascii=False),
                kind="response",
                media_type=str(action["message"].get("content_type") or "application/json"),
            )
        )

    path = operation_page_path(output_dir, channel, action["action"]) if output_dir is not None else Path("unused.mdx")
    channel_path = channel_page_path(output_dir, channel) if output_dir is not None else Path("unused.mdx")
    history_events = (
        list(
            history_events_for_item(
                history_item,
                comparison_versions=comparison_versions or (),
            )
        )
        if history_item is not None
        else legacy_channel_history_events(channel)
    )
    inputs = []
    outputs = []
    if is_publish:
        inputs.append(
            ReferencePanel(
                title=str(action["message"].get("name") or "Message payload"),
                meta_items=[
                    ReferenceMetaItem("Direction", "Client -> Server"),
                    ReferenceMetaItem("Message", str(action["message"].get("name") or "-")),
                ],
                schema=schema,
            )
        )
    else:
        outputs.append(
            ReferencePanel(
                title=str(action["message"].get("name") or "Message payload"),
                meta_items=[
                    ReferenceMetaItem("Direction", "Server -> Client"),
                    ReferenceMetaItem("Message", str(action["message"].get("name") or "-")),
                ],
                schema=schema,
            )
        )

    return ReferenceOperationPage(
        path=path.relative_to(output_dir).as_posix() if output_dir is not None else "single-page",
        anchor=f"operation-{slugify(channel.channel)}-{slugify(action['action'])}",
        title=action_display_title(channel, str(action["action"])),
        description=str(action.get("description") or channel.latest.get("description") or "") or None,
        eyebrow=str(channel.channel),
        summary=None,
        back_link=page_ref(path, channel_path) if output_dir is not None else None,
        back_label="Back to channel",
        breadcrumbs=[
            ReferenceBreadcrumb("JSON API AsyncAPI", page_ref(path, output_dir / "index.mdx") if output_dir is not None else None),
            ReferenceBreadcrumb(channel.channel, page_ref(path, channel_path) if output_dir is not None else None),
            ReferenceBreadcrumb(str(action["action"])),
        ]
        if output_dir is not None
        else [],
        badges=lifecycle_badges(
            channel,
            item=history_item,
            events=history_events,
            comparison_versions=comparison_versions or (),
        ),
        meta_items=[
            ReferenceMetaItem("Channel", channel.channel),
            ReferenceMetaItem("Action", str(action["action"])),
            *lifecycle_meta_items(channel),
        ],
        operation_method=str(action["action"]).upper(),
        operation_target=channel.channel,
        overview_markdown=safe_markdown_text(
            str(action.get("description") or channel.latest.get("description") or "")
        )
        or None,
        protocol_items=[
            ReferenceMetaItem("Protocol", "WebSocket"),
            ReferenceMetaItem("Channel", channel.channel),
            ReferenceMetaItem("Action", str(action["action"])),
            ReferenceMetaItem("Operation ID", str(action.get("operation_id") or "-")),
            ReferenceMetaItem("Content type", str(action["message"].get("content_type") or "-")),
            ReferenceMetaItem("Payload", str(action["message"].get("payload_schema") or "-")),
            *lifecycle_meta_items(channel),
        ],
        inputs=inputs,
        outputs=outputs,
        examples=examples,
        lifecycle_changes=[
            ReferenceChange(
                version=str(entry["version"]),
                details="; ".join(str(change) for change in entry["changes"]),
            )
            for entry in channel.change_details
        ]
        if history_item is None
        else [],
        related_schemas=[schema] if schema is not None else [],
        history_events=history_events,
    )


def build_overview_page(
    report: AsyncApiReport,
    *,
    output_dir: Path,
    overview_name: str,
    page_title: str,
    page_description: str,
    history_report: SurfaceHistoryReport,
) -> ReferenceCollectionPage:
    overview_path = output_dir / overview_name
    items_by_id = history_report.items_by_id()
    cards = []
    for channel in (candidate for candidate in report.channels if candidate.status == "active"):
        channel_items = [
            items_by_id[asyncapi_item_id(channel.channel, action["action"])]
            for action in channel.latest.get("actions", [])
        ]
        events = channel_history_events(
            channel_items,
            comparison_versions=history_report.comparison_versions,
        )
        cards.append(
            ReferenceCard(
                title=channel.channel,
                href=page_ref(overview_path, channel_page_path(output_dir, channel)),
                summary=channel_summary(channel),
                badges=lifecycle_badges(channel, events=events, linked=False),
                meta_items=[
                    ReferenceMetaItem("Actions", ", ".join(channel.latest.get("action_names") or [])),
                    ReferenceMetaItem("Last seen", channel.last_seen_in),
                    *lifecycle_meta_items(channel),
                ],
            )
        )
    return ReferenceCollectionPage(
        path=overview_name,
        title=page_title,
        description=page_description,
        eyebrow="AsyncAPI Reference",
        summary="Operation-first WebSocket reference pages built from AsyncAPI channel snapshots and lifecycle deltas.",
        badges=[ReferenceBadge("AsyncAPI", tone="protocol"), ReferenceBadge(report.publish_version, tone="neutral")],
        meta_items=[
            ReferenceMetaItem("Publish version", report.publish_version),
            ReferenceMetaItem("AsyncAPI version", report.asyncapi_version or "-"),
            ReferenceMetaItem("Source", report.source_name),
            ReferenceMetaItem("Version filter", report.version_filter),
        ],
        sections=[
            ReferenceSection(
                heading="Channels",
                body_markdown=safe_markdown_text("Use the channel page to choose a specific `publish` or `subscribe` action. Action pages are the primary reference surface."),
                cards=cards,
            )
        ],
    )


def build_channel_page(
    channel: AsyncApiChannelLifecycle,
    *,
    output_dir: Path,
    overview_name: str,
    history_report: SurfaceHistoryReport,
) -> ReferenceCollectionPage:
    page_path = channel_page_path(output_dir, channel)
    overview_path = output_dir / overview_name
    items_by_id = history_report.items_by_id()
    channel_items = [
        items_by_id[asyncapi_item_id(channel.channel, action["action"])]
        for action in channel.latest.get("actions", [])
    ]
    events = channel_history_events(
        channel_items,
        comparison_versions=history_report.comparison_versions,
    )
    cards = []
    for action in channel.latest.get("actions", []):
        item = items_by_id[asyncapi_item_id(channel.channel, action["action"])]
        cards.append(
            ReferenceCard(
                title=f"{action['action']} {channel.channel}",
                href=page_ref(page_path, operation_page_path(output_dir, channel, action["action"])),
                summary=compact_text(action.get("description") or channel.latest.get("description") or "", limit=170),
                badges=lifecycle_badges(
                    channel,
                    item=item,
                    comparison_versions=history_report.comparison_versions,
                    linked=False,
                ),
                meta_items=[
                    ReferenceMetaItem("Operation ID", str(action.get("operation_id") or "-")),
                    ReferenceMetaItem("Method", str(action.get("ws_method") or "-")),
                    ReferenceMetaItem("Payload", str(action["message"].get("payload_schema") or "-")),
                    *lifecycle_meta_items(channel),
                ],
            )
        )
    return ReferenceCollectionPage(
        path=page_path.relative_to(output_dir).as_posix(),
        title=channel.channel,
        description=str(channel.latest.get("description") or "AsyncAPI channel overview."),
        eyebrow="AsyncAPI Channel",
        summary=channel_summary(channel),
        back_link=page_ref(page_path, overview_path),
        back_label="Back to overview",
        badges=lifecycle_badges(channel, events=events),
        meta_items=[
            ReferenceMetaItem("Channel", channel.channel),
            ReferenceMetaItem("Actions", ", ".join(channel.latest.get("action_names") or []) or "-"),
            *lifecycle_meta_items(channel),
        ],
        sections=[
            ReferenceSection(
                heading="Actions",
                body_markdown=safe_markdown_text(channel.latest.get("description") or "") or None,
                cards=cards,
            )
        ],
        history_events=events,
    )


def build_pages(
    report: AsyncApiReport,
    *,
    output_dir: Path,
    overview_name: str = "index.mdx",
    page_title: str = "AsyncAPI WebSocket Reference",
    page_description: str = "WebSocket AsyncAPI reference and version history.",
    history_report: SurfaceHistoryReport,
) -> tuple[Path, list[Any]]:
    items_by_id = history_report.items_by_id()
    active_channels = [channel for channel in report.channels if channel.status == "active"]
    pages = [
        render_collection_page(
            build_overview_page(
                report,
                output_dir=output_dir,
                overview_name=overview_name,
                page_title=page_title,
                page_description=page_description,
                history_report=history_report,
            )
        )
    ]
    for channel in active_channels:
        pages.append(
            render_collection_page(
                build_channel_page(
                    channel,
                    output_dir=output_dir,
                    overview_name=overview_name,
                    history_report=history_report,
                )
            )
        )
        for action in channel.latest.get("actions", []):
            history_item = items_by_id[asyncapi_item_id(channel.channel, action["action"])]
            pages.append(
                render_operation_page(
                    build_action_operation(
                        channel,
                        action,
                        output_dir=output_dir,
                        history_item=history_item,
                        comparison_versions=history_report.comparison_versions,
                    )
                )
            )
    return output_dir, pages


def build_page(
    report: AsyncApiReport,
    *,
    output_path: str,
    page_title: str,
    page_description: str,
):
    header = ReferenceCollectionPage(
        path=Path(output_path).as_posix(),
        title=page_title,
        description=page_description,
        eyebrow="AsyncAPI Reference",
        summary="Single-page compatibility view for the new operation-first AsyncAPI renderer.",
        badges=[ReferenceBadge("AsyncAPI", tone="protocol"), ReferenceBadge(report.publish_version, tone="neutral")],
        meta_items=[
            ReferenceMetaItem("Publish version", report.publish_version),
            ReferenceMetaItem("AsyncAPI version", report.asyncapi_version or "-"),
            ReferenceMetaItem("Source", report.source_name),
            ReferenceMetaItem("Version filter", report.version_filter),
        ],
    )
    channels = []
    for channel in report.channels:
        operations = [build_action_operation(channel, action, output_dir=None) for action in channel.latest.get("actions", [])]
        cards = [
            ReferenceCard(
                title=operation.title,
                href=f"#{operation.anchor}",
                summary=operation.summary or "",
                badges=operation.badges,
                meta_items=[
                    ReferenceMetaItem("Action", next((item.value for item in operation.protocol_items if item.label == "Action"), "-")),
                    ReferenceMetaItem("Payload", next((item.value for item in operation.protocol_items if item.label == "Payload"), "-")),
                ],
            )
            for operation in operations
        ]
        channels.append(
            {
                "heading": channel.channel,
                "body_markdown": str(channel.latest.get("description") or "") or None,
                "cards": cards,
                "operations": operations,
            }
        )
    return markdown_page_from_template(
        path=Path(output_path).as_posix(),
        title=page_title,
        description=page_description,
        template_name="asyncapi/single_page.md.j2",
        page=header,
        channels=channels,
    )

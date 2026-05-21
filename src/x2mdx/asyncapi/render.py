"""Render AsyncAPI lifecycle reports into Mintlify-like collection and operation pages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from x2mdx.asyncapi.models import AsyncApiChannelLifecycle, AsyncApiReport
from x2mdx.reference_pages import (
    DetailsHistoryChange,
    DetailsHistoryPage,
    DetailsHistoryVersionRow,
    ReferenceBadge,
    ReferenceBreadcrumb,
    ReferenceCard,
    ReferenceChange,
    ReferenceCollectionPage,
    ReferenceExample,
    ReferenceMetaItem,
    ReferenceOperationPage,
    ReferencePanel,
    ReferenceSection,
    compact_text,
    markdown_page_from_template,
    relative_page_ref,
    render_collection_page,
    render_details_history_page,
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


def lifecycle_badges(channel: AsyncApiChannelLifecycle) -> list[ReferenceBadge]:
    badges = [ReferenceBadge("WebSocket", tone="protocol"), ReferenceBadge(f"Since {channel.introduced_version}", tone="added")]
    state_label = lifecycle_state_label(channel.lifecycle_state)
    if state_label:
        badges.append(ReferenceBadge(state_label, tone=lifecycle_state_tone(channel.lifecycle_state)))
    if channel.changed_in_versions:
        badges.append(ReferenceBadge(f"Changed {channel.changed_in_versions[-1]}", tone="changed"))
    if channel.removed_version:
        badges.append(ReferenceBadge(f"Removed {channel.removed_version}", tone="removed"))
    return badges


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


def action_schema(action: dict[str, Any], *, anchor: str):
    message = dict(action.get("message") or {})
    sample = message.get("sample")
    required_fields = list(message.get("required_fields") or [])
    if sample is None and not required_fields:
        return None
    return schema_from_sample(
        name=str(message.get("name") or action["action"]),
        sample=sample,
        required_fields=required_fields,
        summary=str(message.get("payload_schema") or "-"),
        description=str(action.get("description") or ""),
        anchor=anchor,
    )


def wscat_example(action: dict[str, Any]) -> str:
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
    action: dict[str, Any],
    *,
    output_dir: Path | None,
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
        description=None,
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
        badges=lifecycle_badges(channel),
        meta_items=[
            ReferenceMetaItem("Channel", channel.channel),
            ReferenceMetaItem("Action", str(action["action"])),
            ReferenceMetaItem("Introduced", channel.introduced_version),
            ReferenceMetaItem("Removed", channel.removed_version or "-"),
            *lifecycle_meta_items(channel),
        ],
        operation_method=str(action["action"]).upper(),
        operation_target=channel.channel,
        overview_markdown=None,
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
            ReferenceChange(version=str(entry["version"]), details="; ".join(str(change) for change in entry["changes"]))
            for entry in channel.change_details
        ],
        related_schemas=[schema] if schema is not None else [],
    )


def build_overview_page(
    report: AsyncApiReport,
    *,
    output_dir: Path,
    overview_name: str,
    page_title: str,
    page_description: str,
) -> ReferenceCollectionPage:
    overview_path = output_dir / overview_name
    cards = [
        ReferenceCard(
            title=channel.channel,
            href=page_ref(overview_path, channel_page_path(output_dir, channel)),
            summary=channel_summary(channel),
            badges=lifecycle_badges(channel),
            meta_items=[
                ReferenceMetaItem("Actions", ", ".join(channel.latest.get("action_names") or []) or "-"),
                ReferenceMetaItem("Last seen", channel.last_seen_in),
                *lifecycle_meta_items(channel),
            ],
        )
        for channel in report.channels
    ]
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


def version_summary_rows(report: AsyncApiReport) -> list[DetailsHistoryVersionRow]:
    rows: list[DetailsHistoryVersionRow] = []
    for version in report.versions:
        deltas = report.per_version_deltas.get(version, {})
        deprecated_count = sum(
            1
            for channel in report.channels
            if channel.lifecycle_state == "deprecated"
            and (channel.introduced_version == version or version in channel.changed_in_versions)
        )
        replaced_count = sum(
            1
            for channel in report.channels
            if channel.replaces
            and (channel.introduced_version == version or version in channel.changed_in_versions)
        )
        rows.append(
            DetailsHistoryVersionRow(
                version=version,
                added=str(deltas.get("added_count", 0)),
                changed=str(deltas.get("changed_count", 0)),
                removed=str(deltas.get("removed_count", 0)),
                deprecated=str(deprecated_count or "-"),
                replaced=str(replaced_count or "-"),
            )
        )
    return rows


def details_history_changes(report: AsyncApiReport, *, details_path: Path, output_dir: Path) -> list[DetailsHistoryChange]:
    changes: list[DetailsHistoryChange] = [
        DetailsHistoryChange(
            version=report.versions[0],
            title="Initial selected snapshot",
            details=f"{sum(1 for channel in report.channels if channel.introduced_version == report.versions[0])} channels were present when this source stream first appears in the selected inputs.",
            tone="added",
        )
    ]
    for channel in report.channels:
        href = page_ref(details_path, channel_page_path(output_dir, channel))
        if channel.introduced_version != report.versions[0]:
            changes.append(
                DetailsHistoryChange(
                    version=channel.introduced_version,
                    title=f"Added {channel.channel}",
                    details="Channel added to the published WebSocket surface.",
                    tone="added",
                    href=href,
                )
            )
        for entry in channel.change_details:
            changes.append(
                DetailsHistoryChange(
                    version=str(entry["version"]),
                    title=f"Changed {channel.channel}",
                    details="; ".join(str(change) for change in entry.get("changes", [])) or "details updated",
                    tone="changed",
                    href=href,
                )
            )
        if channel.removed_version:
            changes.append(
                DetailsHistoryChange(
                    version=channel.removed_version,
                    title=f"Removed {channel.channel}",
                    details=f"Last seen in {channel.last_seen_in}.",
                    tone="removed",
                    href=href,
                )
            )
    version_order = {version: index for index, version in enumerate(report.versions)}
    tone_order = {"added": 0, "changed": 1, "removed": 2}
    return sorted(changes, key=lambda change: (version_order.get(change.version, len(version_order)), tone_order.get(change.tone, 9), change.title))


def build_details_history_page(
    report: AsyncApiReport,
    *,
    output_dir: Path,
    overview_name: str,
    page_title: str,
    page_description: str,
) -> DetailsHistoryPage:
    details_path = output_dir / overview_name
    active_channels = [channel for channel in report.channels if channel.status != "removed"]
    removed_channels = [channel for channel in report.channels if channel.status == "removed"]

    def channel_cards(channels: list[AsyncApiChannelLifecycle]) -> list[ReferenceCard]:
        return [
            ReferenceCard(
                title=channel.channel,
                href=page_ref(details_path, channel_page_path(output_dir, channel)),
                summary=channel_summary(channel),
                badges=lifecycle_badges(channel),
                meta_items=[
                    ReferenceMetaItem("Actions", ", ".join(channel.latest.get("action_names") or []) or "-"),
                    ReferenceMetaItem("Last seen", channel.last_seen_in),
                    *lifecycle_meta_items(channel),
                ],
            )
            for channel in channels
        ]

    inventory_sections = [
        ReferenceSection(
            heading="Published channels",
            body_markdown=safe_markdown_text("These channels are present in the publish version and link to channel pages for publish and subscribe actions."),
            meta_items=[
                ReferenceMetaItem("Channels", str(len(active_channels))),
                ReferenceMetaItem("Publish version", report.publish_version),
            ],
            cards=channel_cards(active_channels),
        )
    ]
    if removed_channels:
        inventory_sections.append(
            ReferenceSection(
                heading="Removed channels",
                body_markdown=safe_markdown_text("These channels are retained for history because they appeared in earlier selected inputs."),
                meta_items=[ReferenceMetaItem("Channels", str(len(removed_channels)))],
                cards=channel_cards(removed_channels),
            )
        )

    return DetailsHistoryPage(
        path=overview_name,
        title=f"{page_title} details and history",
        description=page_description,
        eyebrow="Details and history",
        summary="Generated-source metadata, version coverage, channel inventory, and per-version changes for this source stream.",
        badges=[ReferenceBadge("AsyncAPI", tone="protocol"), ReferenceBadge(report.publish_version, tone="neutral")],
        meta_items=[
            ReferenceMetaItem("Source stream", page_title),
            ReferenceMetaItem("Publish version", report.publish_version),
            ReferenceMetaItem("Versions compared", ", ".join(report.versions)),
        ],
        source_items=[
            ReferenceMetaItem("Input family", report.source_name),
            ReferenceMetaItem("Version filter", report.version_filter),
            ReferenceMetaItem("Latest source path", report.latest_source_path),
            ReferenceMetaItem("AsyncAPI version", report.asyncapi_version or "-"),
        ],
        source_cards=[
            ReferenceCard(
                title="Generated reference pages",
                summary="Channel and action pages are generated from the publish-version AsyncAPI document, with history calculated across selected snapshots.",
                meta_items=[
                    ReferenceMetaItem("Channels", str(len(report.channels))),
                    ReferenceMetaItem("Actions", str(sum(len(channel.latest.get("actions", [])) for channel in report.channels))),
                ],
            )
        ],
        version_rows=version_summary_rows(report),
        inventory_sections=inventory_sections,
        changes=details_history_changes(report, details_path=details_path, output_dir=output_dir),
        limitations=[
            "Change detection is structural and compares selected generated inputs; it does not infer behavioral compatibility.",
            "Channel-level additions, removals, and changed message shapes are tracked when they are present in the selected snapshots.",
            "Lifecycle labels and replacement links are included only when the source document carries that metadata.",
        ],
    )


def build_channel_page(
    channel: AsyncApiChannelLifecycle,
    *,
    output_dir: Path,
    overview_name: str,
) -> ReferenceCollectionPage:
    page_path = channel_page_path(output_dir, channel)
    overview_path = output_dir / overview_name
    cards = [
        ReferenceCard(
            title=f"{action['action']} {channel.channel}",
            href=page_ref(page_path, operation_page_path(output_dir, channel, action["action"])),
            summary=compact_text(action.get("description") or channel.latest.get("description") or "", limit=170),
            badges=lifecycle_badges(channel),
            meta_items=[
                ReferenceMetaItem("Operation ID", str(action.get("operation_id") or "-")),
                ReferenceMetaItem("Method", str(action.get("ws_method") or "-")),
                ReferenceMetaItem("Payload", str(action["message"].get("payload_schema") or "-")),
                *lifecycle_meta_items(channel),
            ],
        )
        for action in channel.latest.get("actions", [])
    ]
    return ReferenceCollectionPage(
        path=page_path.relative_to(output_dir).as_posix(),
        title=channel.channel,
        description=str(channel.latest.get("description") or "AsyncAPI channel overview."),
        eyebrow="AsyncAPI Channel",
        summary=channel_summary(channel),
        back_link=page_ref(page_path, overview_path),
        back_label="Back to overview",
        badges=lifecycle_badges(channel),
        meta_items=[
            ReferenceMetaItem("Channel", channel.channel),
            ReferenceMetaItem("Actions", ", ".join(channel.latest.get("action_names") or []) or "-"),
            ReferenceMetaItem("Introduced", channel.introduced_version),
            ReferenceMetaItem("Removed", channel.removed_version or "-"),
            *lifecycle_meta_items(channel),
        ],
        sections=[
            ReferenceSection(
                heading="Actions",
                body_markdown=safe_markdown_text(channel.latest.get("description") or "") or None,
                cards=cards,
            )
        ],
    )


def build_pages(
    report: AsyncApiReport,
    *,
    output_dir: Path,
    overview_name: str = "index.mdx",
    page_title: str = "AsyncAPI WebSocket Reference",
    page_description: str = "WebSocket AsyncAPI reference and version history.",
) -> tuple[Path, list[Any]]:
    pages = [
        render_details_history_page(
            build_details_history_page(
                report,
                output_dir=output_dir,
                overview_name=overview_name,
                page_title=page_title,
                page_description=page_description,
            )
        )
    ]
    for channel in report.channels:
        pages.append(render_collection_page(build_channel_page(channel, output_dir=output_dir, overview_name=overview_name)))
        for action in channel.latest.get("actions", []):
            pages.append(render_operation_page(build_action_operation(channel, action, output_dir=output_dir)))
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

"""Render OpenRPC reports into Mintlify-like overview, supporting, and operation pages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from x2mdx.openrpc.models import OpenRpcMethodLifecycle, OpenRpcReport, OpenRpcSpecLifecycle
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
    relative_page_ref,
    render_collection_page,
    render_operation_page,
    rooted_page_ref,
    safe_markdown_text,
    schema_from_sample,
)


def slugify(value: str) -> str:
    output = value.lower()
    output = re.sub(r"[^a-z0-9]+", "-", output)
    output = re.sub(r"-{2,}", "-", output).strip("-")
    return output


def spec_page_path(output_dir: Path, spec: OpenRpcSpecLifecycle, *, spec_dir_name: str) -> Path:
    return output_dir / spec_dir_name / f"{slugify(spec.spec_id)}.mdx"


def operation_page_path(output_dir: Path, spec: OpenRpcSpecLifecycle, method: OpenRpcMethodLifecycle) -> Path:
    return output_dir / "operations" / slugify(spec.spec_id) / f"{slugify(method.method)}.mdx"


def normalize_link_prefix(link_prefix: str) -> str:
    trimmed = link_prefix.strip()
    if not trimmed:
        raise ValueError("link_prefix must not be empty")
    if trimmed == "/":
        return ""
    return trimmed.strip("/")


def page_ref(from_path: Path, to_path: Path, *, output_dir: Path, link_prefix: str | None) -> str:
    if link_prefix is not None:
        return rooted_page_ref(link_prefix, to_path, output_dir)
    return relative_page_ref(from_path, to_path)


def lifecycle_badges(
    *,
    protocol_label: str,
    introduced: str,
    changed: list[str] | None = None,
    removed: str | None = None,
) -> list[ReferenceBadge]:
    badges = [ReferenceBadge(protocol_label, tone="protocol"), ReferenceBadge(f"Since {introduced}", tone="added")]
    if changed:
        badges.append(ReferenceBadge(f"Changed {changed[-1]}", tone="changed"))
    if removed:
        badges.append(ReferenceBadge(f"Removed {removed}", tone="removed"))
    return badges


def info_summary(spec: OpenRpcSpecLifecycle) -> str:
    if spec.info_description:
        return compact_text(spec.info_description, limit=200)
    if spec.info_title and spec.info_title != spec.display_name:
        return spec.info_title
    return f"{len(spec.methods)} methods"


def schema_meta_items(schema_name: str | None, schema_brief: str, required_fields: list[str]) -> list[ReferenceMetaItem]:
    items = [ReferenceMetaItem("Shape", schema_brief)]
    if schema_name:
        items.append(ReferenceMetaItem("Schema", schema_name))
    if required_fields:
        items.append(ReferenceMetaItem("Required", ", ".join(required_fields)))
    return items


def schema_for_detail(name: str, detail: dict[str, Any], *, anchor: str) -> ReferenceSchema | None:
    sample = detail.get("sample")
    if sample is None and not detail.get("required_fields"):
        return None
    return schema_from_sample(
        name=name,
        sample=sample,
        required_fields=list(detail.get("required_fields") or []),
        summary=str(detail.get("schema") or "-"),
        description=str(detail.get("description") or ""),
        anchor=anchor,
    )


def json_rpc_request_body(method_name: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method_name,
    }
    if request_payload:
        body["params"] = request_payload
    return body


def curl_example(request_body: dict[str, Any]) -> str:
    return "\n".join(
        [
            "curl \\",
            "  <JSON_RPC_URL> \\",
            "  -H 'content-type: application/json' \\",
            "  --data @- <<'EOF'",
            json.dumps(request_body, indent=2, ensure_ascii=False),
            "EOF",
        ]
    )


def build_overview_page(
    report: OpenRpcReport,
    *,
    output_dir: Path,
    overview_name: str,
    overview_title: str,
    spec_dir_name: str,
    link_prefix: str | None = None,
) -> ReferenceCollectionPage:
    overview_path = output_dir / overview_name
    cards = []
    for spec in report.specs:
        spec_path = spec_page_path(output_dir, spec, spec_dir_name=spec_dir_name)
        cards.append(
            ReferenceCard(
                title=spec.display_name,
                href=page_ref(overview_path, spec_path, output_dir=output_dir, link_prefix=link_prefix),
                summary=info_summary(spec),
                badges=lifecycle_badges(
                    protocol_label="JSON-RPC",
                    introduced=spec.introduced_version,
                    changed=spec.changed_in_versions,
                    removed=spec.removed_version,
                ),
                meta_items=[
                    ReferenceMetaItem("Methods", str(len(spec.methods))),
                    ReferenceMetaItem("Latest version", spec.latest_version),
                    ReferenceMetaItem("OpenRPC", spec.openrpc_version or "-"),
                ],
            )
        )
    return ReferenceCollectionPage(
        path=overview_name,
        title=overview_title,
        description="Versioned OpenRPC reference docs.",
        eyebrow="OpenRPC Reference",
        summary="Operation-first JSON-RPC reference pages with version history carried from the snapshot lifecycle report.",
        badges=[ReferenceBadge("OpenRPC", tone="protocol"), ReferenceBadge(report.publish_version, tone="neutral")],
        meta_items=[
            ReferenceMetaItem("Publish version", report.publish_version),
            ReferenceMetaItem("Versions compared", ", ".join(report.versions)),
            ReferenceMetaItem("Source", report.source_name),
            ReferenceMetaItem("Version filter", report.version_filter),
        ],
        sections=[
            ReferenceSection(
                heading="Specs",
                body_markdown=safe_markdown_text("Choose a spec page to browse its methods, then drill into operation pages for request/response details."),
                cards=cards,
            )
        ],
    )


def build_spec_page(
    spec: OpenRpcSpecLifecycle,
    *,
    output_dir: Path,
    overview_name: str,
    spec_dir_name: str,
    link_prefix: str | None = None,
) -> ReferenceCollectionPage:
    spec_path = spec_page_path(output_dir, spec, spec_dir_name=spec_dir_name)
    overview_path = output_dir / overview_name
    method_cards = [
        ReferenceCard(
            title=method.method,
            href=page_ref(spec_path, operation_page_path(output_dir, spec, method), output_dir=output_dir, link_prefix=link_prefix),
            summary=compact_text(method.latest.get("summary") or method.latest.get("description") or "", limit=170),
            badges=lifecycle_badges(
                protocol_label="JSON-RPC",
                introduced=method.introduced_version,
                changed=method.changed_in_versions,
                removed=method.removed_version,
            ),
            meta_items=[
                ReferenceMetaItem("Parameters", str(len(method.latest.get("params", [])))),
                ReferenceMetaItem("Result", str(method.latest.get("result", {}).get("schema") or "-")),
            ],
        )
        for method in spec.methods
    ]

    return ReferenceCollectionPage(
        path=spec_path.relative_to(output_dir).as_posix(),
        title=spec.display_name,
        description=spec.info_description or "OpenRPC supporting overview.",
        eyebrow="OpenRPC Spec",
        summary=spec.info_description or info_summary(spec),
        back_link=page_ref(spec_path, overview_path, output_dir=output_dir, link_prefix=link_prefix),
        back_label="Back to overview",
        badges=lifecycle_badges(
            protocol_label="JSON-RPC",
            introduced=spec.introduced_version,
            changed=spec.changed_in_versions,
            removed=spec.removed_version,
        ),
        meta_items=[
            ReferenceMetaItem("Latest source path", spec.latest_source_path),
            ReferenceMetaItem("Publish version", spec.latest_version),
            ReferenceMetaItem("OpenRPC version", spec.openrpc_version or "-"),
            ReferenceMetaItem("Spec info.version", spec.info_version or "-"),
        ],
        sections=[
            ReferenceSection(
                heading="Methods",
                body_markdown=safe_markdown_text("Method pages are the primary reference surface. This spec page stays focused on grouping and discovery."),
                cards=method_cards,
            )
        ],
    )


def build_method_page(
    spec: OpenRpcSpecLifecycle,
    method: OpenRpcMethodLifecycle,
    *,
    output_dir: Path,
    spec_dir_name: str,
    link_prefix: str | None = None,
) -> ReferenceOperationPage:
    page_path = operation_page_path(output_dir, spec, method)
    spec_path = spec_page_path(output_dir, spec, spec_dir_name=spec_dir_name)
    params = list(method.latest.get("params") or [])
    result = dict(method.latest.get("result") or {})

    param_panels = []
    related_schemas = []
    request_payload: dict[str, Any] = {}
    for index, param in enumerate(params):
        schema_anchor = f"schema-param-{slugify(method.method)}-{index}"
        schema = schema_for_detail(param.get("schema_name") or param.get("name") or f"param-{index + 1}", param, anchor=schema_anchor)
        if schema is not None:
            related_schemas.append(schema)
        if param.get("sample") is not None:
            request_payload[str(param.get("name") or f"param{index + 1}")] = param["sample"]
        param_panels.append(
            ReferencePanel(
                title=str(param.get("name") or f"param-{index + 1}"),
                meta_items=schema_meta_items(
                    str(param.get("schema_name") or "") or None,
                    str(param.get("schema") or "-"),
                    list(param.get("required_fields") or []),
                ),
                schema=schema,
            )
        )

    result_schema = schema_for_detail(result.get("schema_name") or result.get("name") or "result", result, anchor=f"schema-result-{slugify(method.method)}")
    if result_schema is not None:
        related_schemas.append(result_schema)

    request_body = json_rpc_request_body(method.method, request_payload)
    examples = []
    examples.append(ReferenceExample(title="cURL", body=curl_example(request_body), language="bash"))
    if result.get("sample") is not None:
        examples.append(
            ReferenceExample(
                title="Result",
                body=json.dumps(result["sample"], indent=2, ensure_ascii=False),
                kind="response",
                media_type="application/json",
            )
        )

    overview_parts = [part for part in [method.latest.get("summary"), method.latest.get("description")] if part]
    return ReferenceOperationPage(
        path=page_path.relative_to(output_dir).as_posix(),
        title=method.method,
        description=None,
        eyebrow=spec.display_name,
        summary=None,
        back_link=page_ref(page_path, spec_path, output_dir=output_dir, link_prefix=link_prefix),
        back_label="Back to spec",
        breadcrumbs=[
            ReferenceBreadcrumb("Wallet Gateway JSON-RPC"),
            ReferenceBreadcrumb(spec.display_name, page_ref(page_path, spec_path, output_dir=output_dir, link_prefix=link_prefix)),
            ReferenceBreadcrumb(method.method),
        ],
        badges=lifecycle_badges(
            protocol_label="JSON-RPC",
            introduced=method.introduced_version,
            changed=method.changed_in_versions,
            removed=method.removed_version,
        ),
        meta_items=[
            ReferenceMetaItem("Spec", spec.display_name),
            ReferenceMetaItem("Introduced", method.introduced_version),
            ReferenceMetaItem("Last seen", method.last_seen_in),
            ReferenceMetaItem("Removed", method.removed_version or "-"),
        ],
        operation_method="POST",
        operation_target=f"JSON-RPC {method.method}",
        overview_markdown=None,
        protocol_items=[
            ReferenceMetaItem("Protocol", "JSON-RPC"),
            ReferenceMetaItem("Transport", "HTTP POST"),
            ReferenceMetaItem("Method", method.method),
            ReferenceMetaItem("Parameters", str(len(params))),
            ReferenceMetaItem("Result", str(result.get("schema") or "-")),
        ],
        inputs=param_panels,
        outputs=[
            ReferencePanel(
                title=result.get("name") or "result",
                meta_items=schema_meta_items(
                    str(result.get("schema_name") or "") or None,
                    str(result.get("schema") or "-"),
                    list(result.get("required_fields") or []),
                ),
                schema=result_schema,
            )
        ],
        examples=examples,
        lifecycle_changes=[
            ReferenceChange(version=str(entry["version"]), details="; ".join(str(change) for change in entry["changes"]))
            for entry in method.change_details
        ],
        related_schemas=related_schemas,
    )


def build_pages(
    report: OpenRpcReport,
    *,
    output_dir: Path,
    overview_name: str = "index.mdx",
    spec_dir_name: str = "specs",
    overview_title: str = "Wallet Gateway OpenRPC",
    link_prefix: str | None = None,
) -> tuple[Path, list[Any]]:
    normalized_link_prefix = normalize_link_prefix(link_prefix) if link_prefix else None
    pages = [
        render_collection_page(
            build_overview_page(
                report,
                output_dir=output_dir,
                overview_name=overview_name,
                overview_title=overview_title,
                spec_dir_name=spec_dir_name,
                link_prefix=normalized_link_prefix,
            )
        )
    ]
    for spec in report.specs:
        pages.append(
            render_collection_page(
                build_spec_page(
                    spec,
                    output_dir=output_dir,
                    overview_name=overview_name,
                    spec_dir_name=spec_dir_name,
                    link_prefix=normalized_link_prefix,
                )
            )
        )
        for method in spec.methods:
            pages.append(
                render_operation_page(
                    build_method_page(
                        spec,
                        method,
                        output_dir=output_dir,
                        spec_dir_name=spec_dir_name,
                        link_prefix=normalized_link_prefix,
                    )
                )
            )
    return output_dir, pages

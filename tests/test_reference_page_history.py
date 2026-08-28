from __future__ import annotations

from pathlib import Path

from x2mdx.history import history_events_for_item, load_history_report
from x2mdx.reference_pages import (
    ReferenceBreadcrumb,
    ReferenceCollectionPage,
    ReferenceExample,
    ReferenceField,
    ReferenceMetaItem,
    ReferenceOperationPage,
    ReferencePanel,
    ReferenceSchema,
    reference_badges_for_history_item,
    render_collection_page,
    render_operation_page,
)
from x2mdx.render import render_page


REPORT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "history" / "conformance" / "report.json"
)


def render_synthetic_operation() -> str:
    report = load_history_report(REPORT_FIXTURE)
    item = report.items_by_id()["payments.create"]
    request_schema = ReferenceSchema(
        name="CreatePaymentRequest",
        fields=[
            ReferenceField("amount", "string", required=True),
            ReferenceField("idempotencyKey", "string"),
        ],
    )
    response_schema = ReferenceSchema(
        name="Payment",
        fields=[
            ReferenceField("id", "string", required=True),
            ReferenceField("status", "string", required=True),
        ],
    )
    page = ReferenceOperationPage(
        path="reference/payments/create.mdx",
        title="Create a payment",
        eyebrow="Payments API",
        breadcrumbs=[
            ReferenceBreadcrumb("Payments", "/reference/payments"),
            ReferenceBreadcrumb("Create a payment"),
        ],
        badges=reference_badges_for_history_item(item, kind_label="REST"),
        operation_method="POST",
        operation_target="/payments",
        protocol_items=[
            ReferenceMetaItem("Operation ID", item.id),
            ReferenceMetaItem("Authentication", "Bearer token"),
        ],
        inputs=[ReferencePanel("Request body", schema=request_schema)],
        outputs=[ReferencePanel("201 Created", schema=response_schema)],
        examples=[
            ReferenceExample(
                title="Request",
                body='{\n  "amount": "42.00"\n}',
                kind="request",
            ),
            ReferenceExample(
                title="201 response",
                body='{\n  "id": "payment-123",\n  "status": "created"\n}',
                kind="response",
                media_type="application/json",
            ),
        ],
        related_schemas=[response_schema],
        history_events=list(
            history_events_for_item(
                item,
                comparison_versions=report.comparison_versions,
            )
        ),
    )
    return render_page(render_operation_page(page))


def test_standard_page_puts_contract_badges_near_the_title_in_order() -> None:
    rendered = render_synthetic_operation()

    badge_labels = [
        "REST",
        "Since 1.0.0",
        "Changed 1.1.0",
        "Remove as of 2.1.0",
    ]
    badge_positions = [rendered.index(label) for label in badge_labels]

    assert badge_positions == sorted(badge_positions)
    assert badge_positions[-1] < rendered.index('<div class="x2mdx-ref-operation-bar">')


def test_history_is_the_final_main_column_section_without_a_count() -> None:
    rendered = render_synthetic_operation()

    expected_headings = [
        "## Protocol Details",
        "## Inputs",
        "## Outputs",
        "## Related Schemas",
        "## History",
    ]
    heading_positions = [rendered.index(heading) for heading in expected_headings]

    assert heading_positions == sorted(heading_positions)
    assert rendered.rfind("## History") > rendered.rfind("## Related Schemas")
    assert "lifecycle events" not in rendered.lower()
    assert "details and history" not in rendered.lower()


def test_history_renders_newest_first_with_text_bearing_event_labels() -> None:
    rendered = render_synthetic_operation()
    history = rendered[rendered.index("## History") :]
    labels = [
        "Remove as of",
        "Replacement",
        "Deprecated",
        "Changed",
        "Introduced",
    ]
    positions = [history.index(label) for label in labels]

    assert positions == sorted(positions)
    assert "Replaced by payments.createV2" in history
    assert "Added an optional idempotency key." in history


def test_history_styles_cover_desktop_dark_mode_and_narrow_layouts() -> None:
    styles = (Path(__file__).parents[1] / "docs-main" / "styles.css").read_text(
        encoding="utf-8"
    )

    assert ".x2mdx-ref-history-event" in styles
    assert '[data-theme="dark"] .x2mdx-ref-history-event' in styles
    assert "@media (max-width: 640px)" in styles
    assert ".x2mdx-ref-hero > *" in styles
    assert "overflow-wrap: anywhere;" in styles


def test_collection_pages_mark_the_standardized_reference_canvas() -> None:
    rendered = render_page(
        render_collection_page(
            ReferenceCollectionPage(
                path="reference/payments/index.mdx",
                title="Payments API",
                eyebrow="API Reference",
            )
        )
    )

    assert rendered.count("x2mdx-ref-page--collection") == 1

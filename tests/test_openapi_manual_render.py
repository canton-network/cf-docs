from __future__ import annotations

from x2mdx.history.models import HistoryEventKind
from x2mdx.openapi import (
    ManualOpenAPIRenderOptions,
    operation_history_events,
    render_manual_openapi_operation,
)
from x2mdx.render import render_page


def operation_spec(*, changed: bool) -> dict:
    description = "Query flat transactions."
    parameters = [
        {
            "name": "limit",
            "in": "query",
            "required": False,
            "description": "Maximum number of updates.",
            "schema": {"type": "integer", "format": "int64"},
        }
    ]
    if changed:
        description += (
            " Provided for backwards compatibility; it will be removed in the Canton "
            "version 3.5.0."
        )
        parameters.append(
            {
                "name": "stream_idle_timeout_ms",
                "in": "query",
                "required": False,
                "schema": {"type": "integer", "format": "int64"},
            }
        )
    return {
        "openapi": "3.0.3",
        "paths": {
            "/v2/updates/flats": {
                "post": {
                    "summary": "POST /v2/updates/flats",
                    "description": description,
                    "operationId": "postV2UpdatesFlats",
                    "deprecated": changed,
                    "security": [{"httpAuth": []}],
                    "parameters": parameters,
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/GetUpdatesRequest"
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/Update"
                                        },
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {"text/plain": {"schema": {"type": "string"}}},
                        },
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "GetUpdatesRequest": {
                    "type": "object",
                    "required": ["beginExclusive", "commands"],
                    "properties": {
                        "beginExclusive": {
                            "type": "integer",
                            "format": "int64",
                            "description": "First offset to read after.",
                        },
                        "verbose": {"type": "boolean", "default": False},
                        "commands": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Command"},
                        },
                    },
                },
                "Command": {
                    "type": "object",
                    "required": ["commandId", "payload"],
                    "properties": {
                        "commandId": {"type": "string"},
                        "payload": {"$ref": "#/components/schemas/CommandPayload"},
                    },
                },
                "CommandPayload": {
                    "type": "object",
                    "required": ["templateId"],
                    "properties": {
                        "templateId": {"type": "string"},
                        "arguments": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                    },
                },
                "Update": {
                    "type": "object",
                    "required": ["offset"],
                    "properties": {"offset": {"type": "integer", "format": "int64"}},
                },
            },
            "securitySchemes": {
                "httpAuth": {"type": "http", "scheme": "bearer"},
            },
        },
    }


def test_operation_history_uses_authored_remove_as_of_and_snapshot_changes() -> None:
    events = operation_history_events(
        specs_by_version={
            "3.4": operation_spec(changed=False),
            "3.5": operation_spec(changed=True),
        },
        versions=["3.4", "3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    assert [(event.kind, event.version) for event in events] == [
        (HistoryEventKind.REMOVE_AS_OF, "3.5.0"),
        (HistoryEventKind.DEPRECATED, "3.5"),
        (HistoryEventKind.CHANGED, "3.5"),
        (HistoryEventKind.INTRODUCED, "3.4"),
    ]
    assert events[-1].label == "Present since at least"
    assert events[0].evidence[0].kind.value == "source_metadata"
    assert events[2].evidence[0].kind.value == "snapshot_diff"


def test_operation_history_tracks_operation_id_across_route_move() -> None:
    original = operation_spec(changed=False)
    moved = operation_spec(changed=False)
    operation = moved["paths"].pop("/v2/updates/flats")["post"]
    moved["paths"]["/v2/updates/flat-transactions"] = {"post": operation}

    events = operation_history_events(
        specs_by_version={"3.4": original, "3.5": moved},
        versions=["3.4", "3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flat-transactions",
        source_name="release fixtures",
    )

    assert [(event.kind, event.version) for event in events] == [
        (HistoryEventKind.CHANGED, "3.5"),
        (HistoryEventKind.INTRODUCED, "3.4"),
    ]
    assert "moved from POST /v2/updates/flats" in events[0].details[0]


def test_operation_history_rejects_duplicate_operation_ids() -> None:
    duplicate = operation_spec(changed=False)
    duplicate["paths"]["/duplicate"] = {
        "get": {
            "operationId": "postV2UpdatesFlats",
            "responses": {},
        }
    }

    try:
        operation_history_events(
            specs_by_version={"3.5": duplicate},
            versions=["3.5"],
            publish_version="3.5",
            method="post",
            path="/v2/updates/flats",
            source_name="release fixtures",
        )
    except ValueError as error:
        assert "Duplicate OpenAPI operationId" in str(error)
    else:
        raise AssertionError("Expected duplicate operation IDs to fail")


def test_operation_history_reads_lifecycle_extensions() -> None:
    spec = operation_spec(changed=False)
    operation = spec["paths"]["/v2/updates/flats"]["post"]
    operation["x-remove-as-of"] = "v4.0.0"
    operation["x-replaces"] = "legacyFlatUpdates"

    events = operation_history_events(
        specs_by_version={"3.5": spec},
        versions=["3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    assert [(event.kind, event.version) for event in events] == [
        (HistoryEventKind.REMOVE_AS_OF, "4.0.0"),
        (HistoryEventKind.INTRODUCED, "3.5"),
        (HistoryEventKind.REPLACEMENT, "3.5"),
    ]
    assert events[1].label == "Present since at least"


def test_operation_history_calls_a_later_first_observation_added() -> None:
    earlier = operation_spec(changed=False)
    earlier["paths"] = {}
    current = operation_spec(changed=False)

    events = operation_history_events(
        specs_by_version={"3.4": earlier, "3.5": current},
        versions=["3.4", "3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    assert events[-1].kind == HistoryEventKind.INTRODUCED
    assert events[-1].version == "3.5"
    assert events[-1].label == "Added"


def test_manual_openapi_page_preserves_playground_and_standard_history_layout() -> None:
    specs = {
        "3.4": operation_spec(changed=False),
        "3.5": operation_spec(changed=True),
    }
    history = operation_history_events(
        specs_by_version=specs,
        versions=["3.4", "3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )
    rendered = render_page(
        render_manual_openapi_operation(
            spec=specs["3.5"],
            options=ManualOpenAPIRenderOptions(
                method="post",
                path="/v2/updates/flats",
                output_path="reference/json-api-reference/post-v2updatesflats.mdx",
            ),
            history_events=history,
            publish_version="3.5",
        )
    )

    assert 'api: "POST http://localhost:7575/v2/updates/flats"' in rendered
    assert 'authMethod: "bearer"' in rendered
    assert 'playground: "interactive"' in rendered
    assert 'title: "POST /v2/updates/flats"' in rendered
    assert 'sidebarTitle: "/v2/updates/flats"' in rendered
    assert "Present since at least 3.4" in rendered
    assert 'description: "Query flat transactions.' in rendered
    assert (
        '<p class="x2mdx-ref-summary">Query flat transactions. Provided for '
        "backwards compatibility"
    ) in rendered
    assert "## Authorizations" in rendered
    assert '<ParamField header="Authorization" type="string" required>' in rendered
    assert '<ParamField query="limit" type="number">' in rendered
    assert "OpenAPI type: <code>integer (int64)</code>." in rendered
    assert '<ParamField body="beginExclusive" type="number" required>' in rendered
    assert '<ParamField body="commands" type="object[]" required>' in rendered
    assert '<Expandable title="child attributes">' in rendered
    assert '<ParamField body="commandId" type="string" required>' in rendered
    assert '<ParamField body="templateId" type="string" required>' in rendered
    assert '<ResponseField name="value" type="Update[]" required>' in rendered
    assert "<RequestExample>" in rendered
    assert "<ResponseExample>" in rendered
    assert "```bash cURL" in rendered
    assert "```python Python" in rendered
    assert "```javascript JavaScript" in rendered
    assert "```php PHP" in rendered
    assert "```go Go" in rendered
    assert "```java Java" in rendered
    assert "```ruby Ruby" in rendered
    assert "```text 400" in rendered
    assert '"commands": [' in rendered
    assert '"templateId": "<string>"' in rendered
    assert "x2mdx-ref-operation-shell" not in rendered
    assert "## Protocol Details" not in rendered
    assert "## Inputs" not in rendered
    assert "## Outputs" not in rendered
    assert rendered.index("## Authorizations") < rendered.index("## Body")
    assert rendered.index("## Body") < rendered.index("## Responses")
    assert rendered.index("## Responses") < rendered.index("## History")
    assert "## History" in rendered
    assert "Removal scheduled" in rendered
    assert 'href="#history-removal-scheduled-3-5-0"' in rendered
    assert "3.5.0" in rendered
    assert "details and history" not in rendered.lower()


def test_binary_request_example_uses_file_upload_curl() -> None:
    spec = operation_spec(changed=False)
    operation = spec["paths"]["/v2/updates/flats"]["post"]
    operation["requestBody"] = {
        "content": {
            "application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}
            }
        }
    }
    history = operation_history_events(
        specs_by_version={"3.5": spec},
        versions=["3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    rendered = render_page(
        render_manual_openapi_operation(
            spec=spec,
            options=ManualOpenAPIRenderOptions(
                method="post",
                path="/v2/updates/flats",
                output_path="reference/json-api-reference/post-v2updatesflats.mdx",
            ),
            history_events=history,
            publish_version="3.5",
        )
    )

    assert "--header 'Content-Type: application/octet-stream'" in rendered
    assert "--data-binary '@request.bin'" in rendered


def test_public_operation_omits_authentication_ui_and_headers() -> None:
    spec = operation_spec(changed=False)
    operation = spec["paths"]["/v2/updates/flats"]["post"]
    operation["security"] = []
    history = operation_history_events(
        specs_by_version={"3.5": spec},
        versions=["3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    rendered = render_page(
        render_manual_openapi_operation(
            spec=spec,
            options=ManualOpenAPIRenderOptions(
                method="post",
                path="/v2/updates/flats",
                output_path="reference/json-api-reference/post-v2updatesflats.mdx",
            ),
            history_events=history,
            publish_version="3.5",
        )
    )

    assert "authMethod:" not in rendered
    assert "## Authorizations" not in rendered
    assert "Authorization: Bearer" not in rendered


def test_authored_media_examples_override_generated_placeholders() -> None:
    spec = operation_spec(changed=False)
    operation = spec["paths"]["/v2/updates/flats"]["post"]
    request_media = operation["requestBody"]["content"]["application/json"]
    request_media["example"] = {
        "beginExclusive": 42,
        "commands": [],
        "verbose": True,
    }
    response_media = operation["responses"]["200"]["content"]["application/json"]
    response_media["examples"] = {
        "success": {"value": [{"offset": 84}]},
    }
    history = operation_history_events(
        specs_by_version={"3.5": spec},
        versions=["3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    rendered = render_page(
        render_manual_openapi_operation(
            spec=spec,
            options=ManualOpenAPIRenderOptions(
                method="post",
                path="/v2/updates/flats",
                output_path="reference/json-api-reference/post-v2updatesflats.mdx",
            ),
            history_events=history,
            publish_version="3.5",
        )
    )

    assert '"beginExclusive": 42' in rendered
    assert '"offset": 84' in rendered


def test_long_generated_title_falls_back_to_humanized_operation_id() -> None:
    spec = operation_spec(changed=False)
    operation = spec["paths"]["/v2/updates/flats"]["post"]
    operation["description"] = (
        "You may use this endpoint to generate a result that requires a very long "
        "explanation before the source reaches its first sentence boundary and that "
        "explanation does not belong in the page title."
    )
    history = operation_history_events(
        specs_by_version={"3.5": spec},
        versions=["3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    rendered = render_page(
        render_manual_openapi_operation(
            spec=spec,
            options=ManualOpenAPIRenderOptions(
                method="post",
                path="/v2/updates/flats",
                output_path="reference/json-api-reference/post-v2updatesflats.mdx",
            ),
            history_events=history,
            publish_version="3.5",
        )
    )

    assert 'title: "POST /v2/updates/flats"' in rendered
    assert 'description: "You may use this endpoint' in rendered


def test_lifecycle_prefix_is_not_used_as_the_operation_title() -> None:
    spec = operation_spec(changed=True)
    operation = spec["paths"]["/v2/updates/flats"]["post"]
    operation["summary"] = "POST /v2/updates/flats"
    operation["description"] = "Deprecated. Please use /v3/updates/flats instead."
    history = operation_history_events(
        specs_by_version={"3.5": spec},
        versions=["3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    rendered = render_page(
        render_manual_openapi_operation(
            spec=spec,
            options=ManualOpenAPIRenderOptions(
                method="post",
                path="/v2/updates/flats",
                output_path="reference/json-api-reference/post-v2updatesflats.mdx",
            ),
            history_events=history,
            publish_version="3.5",
        )
    )

    assert 'title: "POST /v2/updates/flats"' in rendered
    assert '<h1 class="x2mdx-ref-title">Deprecated</h1>' not in rendered


def test_humanized_operation_title_drops_a_dangling_preposition() -> None:
    spec = operation_spec(changed=True)
    operation = spec["paths"]["/v2/updates/flats"]["post"]
    operation["summary"] = "POST /v2/updates/flats"
    operation["description"] = "Deprecated. Please use /v3/updates/flats instead."
    operation["operationId"] = "getHoldingsSummaryAt"
    history = operation_history_events(
        specs_by_version={"3.5": spec},
        versions=["3.5"],
        publish_version="3.5",
        method="post",
        path="/v2/updates/flats",
        source_name="release fixtures",
    )

    rendered = render_page(
        render_manual_openapi_operation(
            spec=spec,
            options=ManualOpenAPIRenderOptions(
                method="post",
                path="/v2/updates/flats",
                output_path="reference/json-api-reference/post-v2updatesflats.mdx",
            ),
            history_events=history,
            publish_version="3.5",
        )
    )

    assert 'title: "POST /v2/updates/flats"' in rendered

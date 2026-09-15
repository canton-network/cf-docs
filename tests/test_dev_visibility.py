"""Development-only APIs stay out of public reports until a public observation."""

from copy import deepcopy

import pytest

from x2mdx.openapi.history import filter_dev_openapi_specs
from x2mdx.openrpc.lifecycle import build_openrpc_report_from_sources
from x2mdx.openrpc.models import OpenRpcSourceSnapshot
from x2mdx.openrpc.history import build_openrpc_history_report
from x2mdx.asyncapi.lifecycle import build_asyncapi_report_from_sources
from x2mdx.asyncapi.models import AsyncApiSourceSnapshot
from x2mdx.asyncapi.history import build_asyncapi_history_report
from x2mdx.typedoc.lifecycle import build_typedoc_report_from_sources
from x2mdx.typedoc.models import TypeDocSnapshot, TypeDocSources
from x2mdx.daml_json.lifecycle import build_daml_doc_report_from_sources
from x2mdx.daml_json.models import DamlDocsSnapshot, DamlDocsSources
from tests.minimal_characterization.test_daml_json_lifecycle import module_doc
from x2mdx.visibility import dev_only_identities


@pytest.mark.parametrize(
    "states,hidden",
    [
        (["dev"], True),
        (["dev", "beta"], False),
        (["dev", None], False),
        (["beta", "dev"], True),
        (["dev", "deprecated"], False),
    ],
)
def test_last_present_state_controls_visibility(states, hidden):
    observations = [{"example": state} for state in states] + [{}]
    assert ("example" in dev_only_identities(observations)) == hidden


@pytest.mark.parametrize(
    "later", ["dev", "alpha", "beta", "stable", "deprecated", None]
)
def test_source_annotation_visibility(later):
    versions = ["1.0.0", "1.1.0"]
    specs, rpc, asyncapi, typedoc, daml = {}, [], [], [], []
    for version, state in zip(versions, ["dev", later]):
        annotation = {"x-state": state} if state else {}
        operation = {"operationId": "example", "responses": {}, **annotation}
        specs[version] = {"openapi": "3.0.0", "paths": {"/example": {"get": operation}}}
        rpc.append(
            OpenRpcSourceSnapshot(
                version,
                "api",
                "API",
                "api.json",
                {
                    "methods": [
                        {
                            "name": "example",
                            "params": [],
                            "result": {"name": "result", "schema": {"type": "string"}},
                            **annotation,
                        }
                    ]
                },
            )
        )
        asyncapi.append(
            AsyncApiSourceSnapshot(
                version,
                "api.yaml",
                {
                    "channels": {
                        "example": {
                            "subscribe": {
                                "message": {"payload": {"type": "string"}},
                                **annotation,
                            }
                        }
                    }
                },
            )
        )
        typedoc.append(
            TypeDocSnapshot(
                version,
                "api.json",
                {
                    "name": "example",
                    "groups": [{"title": "Interfaces", "children": [1]}],
                    "children": [
                        {
                            "id": 1,
                            "kind": 256,
                            "name": "Example",
                            "comment": {"modifierTags": [f"@{state}"] if state else []},
                        }
                    ],
                },
            )
        )
        mod = module_doc(
            "Example",
            "Example module",
            warnings=[f"{state}: experimental"] if state else [],
        )
        daml.append(DamlDocsSnapshot(version, "api.json", [mod]))
    for publish in versions:
        expected = publish == "1.1.0" and later != "dev"
        assert (
            bool(
                filter_dev_openapi_specs(
                    specs, versions=versions, publish_version=publish
                )[publish]["paths"]
            )
            == expected
        )
        report = build_openrpc_report_from_sources(
            rpc, source_name="test", version_filter="all", publish_version=publish
        )
        assert bool(report.specs[0].methods) == expected
        assert (
            bool(
                build_openrpc_history_report(
                    sources=rpc,
                    routes={("api", "example"): "/api/example"},
                    publish_version=publish,
                ).items
            )
            == expected
        )
        report = build_asyncapi_report_from_sources(
            asyncapi, source_name="test", version_filter="all", publish_version=publish
        )
        assert bool(report.channels) == expected
        assert (
            bool(
                build_asyncapi_history_report(
                    sources=asyncapi,
                    routes={("example", "subscribe"): "/api/example"},
                    publish_version=publish,
                ).items
            )
            == expected
        )
        report = build_typedoc_report_from_sources(
            TypeDocSources(typedoc),
            source_name="test",
            version_filter="all",
            publish_version=publish,
        )
        assert bool(report.exports) == expected
        report = build_daml_doc_report_from_sources(
            DamlDocsSources(daml),
            source_name="test",
            version_filter="all",
            publish_version=publish,
        )
        assert bool(report.modules) == expected


def test_openapi_tracks_moved_operation_and_does_not_mutate_inputs():
    specs = {
        "1.0.0": {
            "paths": {"/old": {"get": {"operationId": "example", "x-state": "dev"}}}
        },
        "1.1.0": {
            "paths": {"/new": {"get": {"operationId": "example", "x-state": "beta"}}}
        },
        "1.2.0": {"paths": {}},
    }
    original = deepcopy(specs)
    public = filter_dev_openapi_specs(
        specs, versions=list(specs), publish_version="1.2.0"
    )
    assert "/old" in public["1.0.0"]["paths"]
    assert specs == original
    specs["1.1.0"]["paths"]["/new"]["get"]["x-state"] = "dev"
    assert all(
        not spec["paths"]
        for spec in filter_dev_openapi_specs(
            specs, versions=list(specs), publish_version="1.2.0"
        ).values()
    )


def test_asyncapi_action_override_preserves_public_sibling():
    source = AsyncApiSourceSnapshot(
        "1.0.0",
        "api.yaml",
        {
            "channels": {
                "example": {
                    "x-state": "dev",
                    "subscribe": {"message": {}},
                    "publish": {"x-state": "beta", "message": {}},
                }
            }
        },
    )
    report = build_asyncapi_report_from_sources(
        [source], source_name="test", version_filter="all"
    )
    assert [action["action"] for action in report.channels[0].latest["actions"]] == [
        "publish"
    ]


def test_daml_function_filter_does_not_hide_module():
    mod = module_doc("Example", "A module")
    mod["md_functions"][0]["fct_warns"] = [{"WarnData": "Dev: hidden"}]
    report = build_daml_doc_report_from_sources(
        DamlDocsSources([DamlDocsSnapshot("1.0.0", "api.json", [mod])]),
        source_name="test",
        version_filter="all",
    )
    assert report.modules[0]["md_functions"] == []
    assert mod["md_functions"]


@pytest.mark.parametrize("later", ["dev", "beta", "deprecated", None])
def test_protobuf_versioned_overlay_filters_pages_and_history(later):
    from tests.minimal_characterization.test_protobuf_lifecycle import (
        ProtobufMinimalLifecycleTests,
    )
    from x2mdx.protobuf.snapshots import load_protobuf_sources
    from x2mdx.protobuf.lifecycle import build_protobuf_history_report_from_sources

    fixture = ProtobufMinimalLifecycleTests()
    fixture.setUp()
    try:
        key = "com.example.payments.v1.PaymentService/CreatePayment"
        manifest = fixture._write_manifest(
            metadata_overlay={
                "endpoints": {
                    key: {"lifecycle": {"state": "dev", "versions": {"1.1.0": later}}}
                }
            }
        )
        sources = load_protobuf_sources(manifest)
        report = build_protobuf_history_report_from_sources(
            sources, source_name="test", version_filter="all"
        )
        assert (key in report["latestSnapshot"]["endpoints"]) == (later != "dev")
        assert any(item["id"] == key for item in report["endpointLifecycle"]) == (
            later != "dev"
        )
        for release in report["releases"]:
            snapshot = release["snapshot"]
            assert snapshot["stats"]["endpoints"] == len(snapshot["endpoints"])
            if later == "dev":
                assert all(
                    key not in service["endpointIds"]
                    for service in snapshot["services"].values()
                )
                assert all(
                    key not in package["endpointIds"]
                    for package in snapshot["packages"]
                )
    finally:
        fixture.tearDown()


def test_openrpc_cli_prunes_dev_only_pages(tmp_path):
    import json
    from tests.minimal_characterization.test_openrpc_lifecycle import (
        OpenRpcMinimalLifecycleTests,
    )
    from tests.minimal_characterization.helpers import run_x2mdx

    fixture = OpenRpcMinimalLifecycleTests()
    fixture.setUp()
    try:
        manifest = fixture._write_manifest()
        output = tmp_path / "pages"
        args = [
            "openrpc",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output),
            "--history-report",
            str(output / "history.json"),
        ]
        run_x2mdx(args)
        assert any("alphapayments" in path.name for path in output.rglob("*.mdx"))
        spec_path = manifest.parent / "1.1.0/wallet.json"
        spec = json.loads(spec_path.read_text())
        for method in spec["methods"]:
            if method["name"] == "alphaPayments":
                method["x-state"] = "dev"
        spec_path.write_text(json.dumps(spec))
        run_x2mdx(args)
        assert not any("alphapayments" in path.name for path in output.rglob("*.mdx"))
        assert "alphaPayments" not in (output / "history.json").read_text()
        assert all(
            "alphaPayments" not in path.read_text() for path in output.rglob("*.mdx")
        )
    finally:
        fixture.tearDown()

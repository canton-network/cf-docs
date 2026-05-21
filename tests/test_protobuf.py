from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from google.protobuf import descriptor_pb2

from x2mdx.cli import main as cli_main
from x2mdx.protobuf.lifecycle import build_protobuf_history_report_from_sources
from x2mdx.protobuf.render import build_operation_page
from x2mdx.protobuf.snapshots import load_protobuf_sources


def make_field(name: str, number: int, *, type_name: str = "", scalar_type: int | None = None) -> descriptor_pb2.FieldDescriptorProto:
    field = descriptor_pb2.FieldDescriptorProto(name=name, number=number, label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL)
    if type_name:
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
        field.type_name = type_name
    else:
        field.type = scalar_type or descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    return field


def make_message(name: str, fields: list[descriptor_pb2.FieldDescriptorProto]) -> descriptor_pb2.DescriptorProto:
    message = descriptor_pb2.DescriptorProto(name=name)
    message.field.extend(fields)
    return message


def make_method(name: str, request_type: str, response_type: str) -> descriptor_pb2.MethodDescriptorProto:
    return descriptor_pb2.MethodDescriptorProto(name=name, input_type=request_type, output_type=response_type)


class ProtobufTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_descriptor_image(self, relative_path: str, file_proto: descriptor_pb2.FileDescriptorProto) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor_set = descriptor_pb2.FileDescriptorSet()
        descriptor_set.file.extend([file_proto])
        path.write_bytes(gzip.compress(descriptor_set.SerializeToString()))
        return path

    def _write_manifest(self) -> Path:
        base_import = "com/example/service.proto"
        repo_path = "community/example/src/main/protobuf/com/example/service.proto"

        v1 = descriptor_pb2.FileDescriptorProto(name=base_import, package="com.example.v1", syntax="proto3")
        v1.message_type.extend(
            [
                make_message("FooRequest", [make_field("id", 1)]),
                make_message("FooResponse", [make_field("name", 1)]),
            ]
        )
        service_v1 = descriptor_pb2.ServiceDescriptorProto(name="ExampleService")
        service_v1.method.extend([make_method("GetFoo", ".com.example.v1.FooRequest", ".com.example.v1.FooResponse")])
        v1.service.extend([service_v1])

        v2 = descriptor_pb2.FileDescriptorProto(name=base_import, package="com.example.v1", syntax="proto3")
        v2.message_type.extend(
            [
                make_message("FooRequest", [make_field("id", 1)]),
                make_message("FooResponseV2", [make_field("name", 1), make_field("verbose", 2, scalar_type=descriptor_pb2.FieldDescriptorProto.TYPE_BOOL)]),
                make_message("BarRequest", [make_field("query", 1)]),
                make_message("BarResponse", [make_field("count", 1, scalar_type=descriptor_pb2.FieldDescriptorProto.TYPE_INT32)]),
            ]
        )
        service_v2 = descriptor_pb2.ServiceDescriptorProto(name="ExampleService")
        service_v2.method.extend(
            [
                make_method("GetFoo", ".com.example.v1.FooRequest", ".com.example.v1.FooResponseV2"),
                make_method("GetBar", ".com.example.v1.BarRequest", ".com.example.v1.BarResponse"),
            ]
        )
        v2.service.extend([service_v2])

        image_v1 = self._write_descriptor_image("snapshots/1.0.0/image.bin.gz", v1)
        image_v2 = self._write_descriptor_image("snapshots/1.1.0/image.bin.gz", v2)

        metadata = {
            "schemaVersion": 1,
            "files": {},
            "services": {},
            "endpoints": {},
            "messages": {},
            "fields": {},
            "enums": {},
            "enumValues": {},
        }
        metadata_path = self.root / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

        manifest = {
            "source": "unit test protobuf snapshots",
            "repo": {
                "remote": "https://github.com/example/repo.git",
                "web_url": "https://github.com/example/repo",
            },
            "metadata_path": str(metadata_path),
            "versions": [
                {
                    "version": "1.0.0",
                    "tag": "v1.0.0",
                    "date": "2026-01-01",
                    "descriptor_image_path": str(image_v1),
                    "import_to_repo_path": {base_import: repo_path},
                },
                {
                    "version": "1.1.0",
                    "tag": "v1.1.0",
                    "date": "2026-02-01",
                    "descriptor_image_path": str(image_v2),
                    "import_to_repo_path": {base_import: repo_path},
                },
            ],
        }
        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest_path

    def test_build_report_tracks_endpoint_lifecycle(self) -> None:
        manifest_path = self._write_manifest()
        sources = load_protobuf_sources(manifest_path)
        report = build_protobuf_history_report_from_sources(
            sources,
            source_name="unit test protobuf snapshots",
            version_filter="unit test versions",
        )

        self.assertEqual(report["latestSnapshot"]["stats"]["endpoints"], 2)
        lifecycle = {entry["id"]: entry for entry in report["endpointLifecycle"]}
        self.assertEqual(
            lifecycle["com.example.v1.ExampleService/GetFoo"]["lastChangedIn"],
            "1.1.0",
        )
        self.assertEqual(
            lifecycle["com.example.v1.ExampleService/GetBar"]["introducedIn"],
            "1.1.0",
        )

    def test_cli_builds_overview_and_package_pages(self) -> None:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out" / "protobuf-history"
        stale_endpoint_file = output_dir / "endpoints" / "stale" / "index.mdx"
        stale_endpoint_file.parent.mkdir(parents=True, exist_ok=True)
        stale_endpoint_file.write_text("stale\n", encoding="utf-8")

        result = cli_main(
            [
                "protobuf",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--source-name",
                "unit test protobuf snapshots",
                "--version-filter",
                "unit test versions",
            ]
        )

        self.assertEqual(result, 0)
        overview_text = (output_dir / "index.mdx").read_text(encoding="utf-8")
        package_text = (
            output_dir
            / "packages"
            / "com-example-v1.mdx"
        ).read_text(encoding="utf-8")
        operation_text = (
            output_dir
            / "operations"
            / "com-example-v1"
            / "exampleservice"
            / "getfoo.mdx"
        ).read_text(encoding="utf-8")

        self.assertIn("Protobuf details and history", overview_text)
        self.assertIn("## Generated from", overview_text)
        self.assertIn("## Version summary", overview_text)
        self.assertIn("## Current reference inventory", overview_text)
        self.assertIn("x2mdx-ref-status-table--inventory", overview_text)
        self.assertIn("com.example.v1", overview_text)
        self.assertIn('href="./packages/com-example-v1"', overview_text)
        self.assertIn("## ExampleService", package_text)
        self.assertIn("ExampleService.GetFoo", package_text)
        self.assertIn("## Protocol Details", operation_text)
        self.assertIn("<dt>Service</dt>", operation_text)
        self.assertIn("<dd>ExampleService</dd>", operation_text)
        self.assertIn("x2mdx-ref-right-rail", operation_text)
        self.assertIn("x2mdx-ref-rail-panel", operation_text)
        self.assertIn("```bash grpcurl", operation_text)
        self.assertIn("x2mdx-ref-breadcrumbs", operation_text)
        self.assertIn('<h1 class="x2mdx-ref-title">GetFoo</h1>', operation_text)
        self.assertNotIn("x2mdx-ref-summary", operation_text)
        self.assertIn("x2mdx-ref-operation-bar", operation_text)
        self.assertIn("/com.example.v1.ExampleService/GetFoo", operation_text)
        self.assertNotIn("## Overview", operation_text)
        self.assertIn("grpcurl", operation_text)
        self.assertIn("```json OK", operation_text)
        self.assertIn("x2mdx-ref-response-label", operation_text)
        self.assertIn("<HOST:PORT>", operation_text)
        self.assertIn("## Related Schemas", operation_text)
        self.assertIn("<AccordionGroup>", operation_text)
        self.assertIn("com.example.v1.FooResponseV2", operation_text)
        self.assertEqual(operation_text.count('class="x2mdx-ref-schema"'), 2)
        self.assertFalse(stale_endpoint_file.exists())

    def test_operation_adapter_collects_request_and_response_schemas(self) -> None:
        ctx = {
            "messages": {
                "com.example.v1.FooRequest": {
                    "id": "com.example.v1.FooRequest",
                    "description": "",
                    "fieldIds": ["request:id"],
                    "enumIds": [],
                    "nestedMessageIds": [],
                },
                "com.example.v1.FooResponse": {
                    "id": "com.example.v1.FooResponse",
                    "description": "",
                    "fieldIds": ["response:name"],
                    "enumIds": [],
                    "nestedMessageIds": [],
                },
            },
            "fields": {
                "request:id": {"name": "id", "type": "string", "label": "optional", "description": ""},
                "response:name": {"name": "name", "type": "string", "label": "optional", "description": ""},
            },
            "enums": {},
            "enumValues": {},
        }
        endpoint = {
            "service": "ExampleService",
            "name": "GetFoo",
            "requestType": "com.example.v1.FooRequest",
            "responseType": "com.example.v1.FooResponse",
            "clientStreaming": False,
            "serverStreaming": False,
            "description": "Fetch a foo.",
            "file": "com/example/service.proto",
            "sourceUrl": None,
        }
        lifecycle = {
            "introducedIn": "1.0.0",
            "removedIn": None,
            "history": [{"version": "1.0.0", "changeTypes": ["added"], "kind": "added"}],
        }

        page = build_operation_page("com.example.v1", endpoint, lifecycle, output_dir=self.root / "out", ctx=ctx)

        self.assertEqual(page.path, "operations/com-example-v1/exampleservice/getfoo.mdx")
        self.assertEqual(page.title, "GetFoo")
        self.assertEqual(page.operation_method, "RPC")
        self.assertEqual(page.operation_target, "/com.example.v1.ExampleService/GetFoo")
        self.assertEqual([schema.name for schema in page.related_schemas], ["com.example.v1.FooRequest", "com.example.v1.FooResponse"])
        self.assertEqual(page.examples[0].title, "grpcurl")
        self.assertEqual(page.examples[1].title, "OK")
        self.assertEqual(page.examples[1].kind, "response")
        self.assertIn("com.example.v1.ExampleService/GetFoo", page.examples[0].body)
        self.assertIn('"id": "string"', page.examples[0].body)
        self.assertIn('"name": "string"', page.examples[1].body)

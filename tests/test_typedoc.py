from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from x2mdx.cli import main as cli_main
from x2mdx.typedoc.lifecycle import build_typedoc_report_from_sources
from x2mdx.typedoc.snapshots import load_typedoc_sources


def comment(summary: str | None = None, *, internal: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {"summary": []}
    if summary:
        payload["summary"] = [{"kind": "text", "text": summary}]
    if internal:
        payload["modifierTags"] = ["@internal"]
    return payload


def source(line: int) -> list[dict[str, object]]:
    return [{"fileName": "index.d.ts", "line": line, "character": 1}]


def interface_export(
    export_id: int,
    name: str,
    *,
    summary: str,
    member_specs: list[tuple[int, str, str, str, bool]] | None = None,
) -> dict[str, object]:
    children = []
    for member_id, member_name, member_type, member_summary, internal in member_specs or []:
        children.append(
            {
                "id": member_id,
                "name": member_name,
                "kind": 1024,
                "flags": {},
                "comment": comment(member_summary, internal=internal),
                "sources": source(member_id),
                "type": {"type": "intrinsic", "name": member_type},
            }
        )
    return {
        "id": export_id,
        "name": name,
        "variant": "declaration",
        "kind": 256,
        "flags": {},
        "comment": comment(summary),
        "children": children,
        "groups": [{"title": "Properties", "children": [child["id"] for child in children]}] if children else [],
        "sources": source(export_id),
        "typeParameters": [{"id": export_id + 1000, "name": "T", "kind": 131072, "flags": {}}],
    }


def type_alias_export(export_id: int, name: str, summary: str, rendered_type: str) -> dict[str, object]:
    return {
        "id": export_id,
        "name": name,
        "variant": "declaration",
        "kind": 2097152,
        "flags": {},
        "comment": comment(summary),
        "sources": source(export_id),
        "type": {"type": "intrinsic", "name": rendered_type},
    }


def variable_export(export_id: int, name: str, summary: str, rendered_type: str) -> dict[str, object]:
    return {
        "id": export_id,
        "name": name,
        "variant": "declaration",
        "kind": 32,
        "flags": {},
        "comment": comment(summary),
        "sources": source(export_id),
        "type": {"type": "intrinsic", "name": rendered_type},
    }


def function_export(
    export_id: int,
    name: str,
    *,
    summary: str | None = None,
    parameter_type: str = "string",
    return_type: str = "Widget",
    internal: bool = False,
) -> dict[str, object]:
    signature = {
        "id": export_id + 1,
        "name": name,
        "variant": "signature",
        "kind": 4096,
        "flags": {},
        "comment": comment(summary, internal=internal),
        "sources": source(export_id + 1),
        "parameters": [
            {
                "id": export_id + 2,
                "name": "value",
                "variant": "param",
                "kind": 32768,
                "flags": {},
                "type": {"type": "intrinsic", "name": parameter_type},
            }
        ],
        "type": {"type": "reference", "name": return_type},
    }
    return {
        "id": export_id,
        "name": name,
        "variant": "declaration",
        "kind": 64,
        "flags": {},
        "sources": source(export_id),
        "signatures": [signature],
    }


def typedoc_document(children: list[dict[str, object]]) -> dict[str, object]:
    groups = {
        "Interfaces": [],
        "Type Aliases": [],
        "Variables": [],
        "Functions": [],
    }
    for child in children:
        kind = child["kind"]
        if kind == 256:
            groups["Interfaces"].append(child["id"])
        elif kind == 2097152:
            groups["Type Aliases"].append(child["id"])
        elif kind == 32:
            groups["Variables"].append(child["id"])
        elif kind == 64:
            groups["Functions"].append(child["id"])
    return {
        "id": 0,
        "name": "@daml/types",
        "packageName": "@daml/types",
        "kind": 1,
        "variant": "project",
        "children": children,
        "groups": [
            {"title": "Interfaces", "children": groups["Interfaces"]},
            {"title": "Type Aliases", "children": groups["Type Aliases"]},
            {"title": "Variables", "children": groups["Variables"]},
            {"title": "Functions", "children": groups["Functions"]},
        ],
    }


class TypeDocTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, relative_path: str, payload: object) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def _write_manifest(self) -> Path:
        first = self._write_json(
            "snapshots/1.0.0/typedoc.json",
            typedoc_document(
                [
                    interface_export(
                        1,
                        "Widget",
                        summary="Widget interface.",
                        member_specs=[
                            (2, "debug", "string", "", True),
                            (3, "name", "string", "Public widget name.", False),
                        ],
                    ),
                    type_alias_export(10, "Thing", "Alias docs.", "string"),
                    variable_export(20, "Thing", "Variable docs.", "string"),
                    function_export(30, "makeWidget", summary="Create a widget.", parameter_type="string"),
                    function_export(40, "internalOnly", internal=True),
                ]
            ),
        )
        second = self._write_json(
            "snapshots/1.1.0/typedoc.json",
            typedoc_document(
                [
                    interface_export(
                        1,
                        "Widget",
                        summary="Widget interface updated.",
                        member_specs=[
                            (3, "name", "string", "Public widget name.", False),
                            (4, "kind", "string", "Public widget kind.", False),
                        ],
                    ),
                    variable_export(20, "Thing", "Variable docs.", "string"),
                    function_export(30, "makeWidget", summary="Create a widget.", parameter_type="number"),
                    function_export(50, "createHelper", summary="Create a helper.", parameter_type="string", return_type="Helper"),
                    function_export(40, "internalOnly", internal=True),
                ]
            ),
        )
        return self._write_json(
            "manifest.json",
            {
                "source": "unit test typedoc snapshots",
                "package_name": "@daml/types",
                "publish_version": "1.1.0",
                "versions": [
                    {"version": "1.0.0", "json_path": str(first)},
                    {"version": "1.1.0", "json_path": str(second)},
                ],
            },
        )

    def test_build_report_tracks_changes_removed_exports_and_group_scoped_names(self) -> None:
        manifest_path = self._write_manifest()
        sources = load_typedoc_sources(manifest_path)
        report = build_typedoc_report_from_sources(
            sources,
            source_name="unit test typedoc snapshots",
            version_filter="unit test versions",
        )

        exports = {(export["name"], export["kind_label"]): export for export in report.exports}
        self.assertEqual(report.package_name, "@daml/types")
        self.assertEqual(report.publish_version, "1.1.0")
        self.assertEqual(exports[("Widget", "Interface")]["changed_in"], ["1.1.0"])
        self.assertEqual(
            exports[("Widget", "Interface")]["change_details"],
            [
                {
                    "version": "1.1.0",
                    "changes": [
                        "summary updated",
                        "members added: `kind`",
                    ],
                }
            ],
        )
        self.assertEqual(exports[("Thing", "Type Alias")]["status"], "removed")
        self.assertEqual(exports[("Thing", "Type Alias")]["removed_in"], "1.1.0")
        self.assertEqual(exports[("Thing", "Variable")]["status"], "active")
        self.assertEqual(exports[("createHelper", "Function")]["introduced_in"], "1.1.0")
        self.assertEqual(
            exports[("makeWidget", "Function")]["change_details"],
            [{"version": "1.1.0", "changes": ["call signatures updated"]}],
        )

    def test_cli_builds_single_page_and_filters_internal_members(self) -> None:
        manifest_path = self._write_manifest()
        output_file = self.root / "out" / "typescript.mdx"

        result = cli_main(
            [
                "typedoc",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-file",
                str(output_file),
                "--source-name",
                "unit test typedoc snapshots",
                "--version-filter",
                "unit test versions",
            ]
        )

        self.assertEqual(result, 0)
        text = output_file.read_text(encoding="utf-8")
        self.assertIn('title: "TypeScript/JavaScript"', text)
        self.assertIn("## Table of Contents", text)
        self.assertIn("## Version Change Summary", text)
        self.assertIn("## Reference", text)
        self.assertIn("[`Thing`](#type-alias-thing)", text)
        self.assertIn("[`Thing`](#variable-thing)", text)
        self.assertIn("`1.1.0`: summary updated; members added: `kind`", text)
        self.assertIn("| Name | Kind | Summary | Introduced | Changed | Deprecated | Removed |", text)
        self.assertIn("| Version | Added | Changed | Removed |", text)
        self.assertIn("Removed in: `1.1.0`", text)
        self.assertIn("Shown for historical reference.", text)
        self.assertIn("Widget interface updated.", text)
        self.assertIn("**Version Changes**", text)
        self.assertIn("call signatures updated", text)
        self.assertIn("`kind`", text)
        self.assertNotIn("internalOnly", text)
        self.assertNotIn("`debug`", text)

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.minimal_characterization.helpers import (
    assert_contains_all,
    assert_contains_none,
    assert_text_file_matches_fixture,
    read_mdx,
    run_x2mdx,
)


def comment(
    summary: str,
    *,
    modifier_tags: list[str] | None = None,
    block_tags: list[tuple[str, str]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"summary": [{"kind": "text", "text": summary}]}
    if modifier_tags:
        payload["modifierTags"] = modifier_tags
    if block_tags:
        payload["blockTags"] = [
            {"tag": tag, "content": [{"kind": "text", "text": text}]}
            for tag, text in block_tags
        ]
    return payload


def source(line: int) -> list[dict[str, object]]:
    return [{"fileName": "index.d.ts", "line": line, "character": 1}]


def interface_export(
    export_id: int,
    name: str,
    summary: str,
    *,
    modifier_tags: list[str] | None = None,
    block_tags: list[tuple[str, str]] | None = None,
    members: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "id": export_id,
        "name": name,
        "variant": "declaration",
        "kind": 256,
        "flags": {},
        "comment": comment(summary, modifier_tags=modifier_tags, block_tags=block_tags),
        "children": members or [],
        "groups": [{"title": "Properties", "children": [item["id"] for item in members or []]}],
        "sources": source(export_id),
    }


def function_export(
    export_id: int,
    name: str,
    summary: str,
    *,
    modifier_tags: list[str] | None = None,
    block_tags: list[tuple[str, str]] | None = None,
    parameter_type: str = "string",
) -> dict[str, object]:
    signature = {
        "id": export_id + 1,
        "name": name,
        "variant": "signature",
        "kind": 4096,
        "flags": {},
        "comment": comment(summary, modifier_tags=modifier_tags, block_tags=block_tags),
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
        "type": {"type": "reference", "name": "Result"},
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
    interface_ids = [child["id"] for child in children if child["kind"] == 256]
    function_ids = [child["id"] for child in children if child["kind"] == 64]
    return {
        "id": 0,
        "name": "@daml/types",
        "packageName": "@daml/types",
        "kind": 1,
        "variant": "project",
        "children": children,
        "groups": [
            {"title": "Interfaces", "children": interface_ids},
            {"title": "Functions", "children": function_ids},
        ],
    }


class TypeDocMinimalLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, relative_path: str, payload: object) -> Path:
        path = self.root / "fixtures" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def _write_manifest(self) -> Path:
        first = self._write_json(
            "1.0.0/typedoc.json",
            typedoc_document(
                [
                    interface_export(1, "LegacyWidget", "Legacy widget API."),
                    function_export(20, "makeWidget", "Create a widget.", parameter_type="string"),
                ]
            ),
        )
        second = self._write_json(
            "1.1.0/typedoc.json",
            typedoc_document(
                [
                    interface_export(2, "AlphaWidget", "Experimental widget API.", modifier_tags=["@alpha"]),
                    interface_export(3, "BetaWidget", "Preview widget API.", modifier_tags=["@beta"]),
                    interface_export(
                        4,
                        "StableWidget",
                        "Stable widget API.",
                        modifier_tags=["@stable"],
                        block_tags=[("@replaces", "LegacyWidget")],
                    ),
                    interface_export(
                        1,
                        "LegacyWidget",
                        "Legacy widget API.",
                        block_tags=[("@deprecated", "Use StableWidget instead.")],
                    ),
                    function_export(
                        20,
                        "makeWidget",
                        "Create a widget.",
                        modifier_tags=["@stable"],
                        block_tags=[("@replaces", "makeLegacyWidget")],
                        parameter_type="number",
                    ),
                ]
            ),
        )
        return self._write_json(
            "manifest.json",
            {
                "source": "minimal typedoc lifecycle fixtures",
                "package_name": "@daml/types",
                "publish_version": "1.1.0",
                "versions": [
                    {"version": "1.0.0", "json_path": str(first)},
                    {"version": "1.1.0", "json_path": str(second)},
                ],
            },
        )

    def _render_page(self, relative_output_file: str = "typescript.mdx") -> Path:
        manifest_path = self._write_manifest()
        output_file = self.root / "out" / relative_output_file

        run_x2mdx(
            [
                "typedoc",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-file",
                str(output_file),
                "--source-name",
                "minimal typedoc lifecycle fixtures",
                "--version-filter",
                "minimal versions",
            ]
        )
        return output_file

    def test_cli_renders_minimal_source_contract(self) -> None:
        output_file = self._render_page()
        assert_text_file_matches_fixture(output_file, "typedoc/typescript.mdx")
        page = read_mdx(output_file.parent, output_file.name)

        assert_contains_all(
            page,
            [
                "## Table of Contents",
                "## Version Change Summary",
                "## Reference",
                "makeWidget(value: number): Result",
                "lifecycle state updated",
            ],
        )

    def test_cli_renders_explicit_lifecycle_states(self) -> None:
        output_file = self._render_page("typescript-lifecycle.mdx")
        assert_text_file_matches_fixture(output_file, "typedoc/typescript.mdx")
        page = read_mdx(output_file.parent, output_file.name)

        assert_contains_all(
            page,
            [
                "AlphaWidget",
                "Lifecycle: `Alpha`",
                "BetaWidget",
                "Lifecycle: `Beta`",
                "StableWidget",
                "Lifecycle: `Stable`",
                "Replaces: `LegacyWidget`",
                "LegacyWidget",
                "Lifecycle: `Deprecated`",
                "Deprecated: Use StableWidget instead.",
            ],
        )

    def test_cli_renders_replacement_metadata(self) -> None:
        output_file = self._render_page("typescript-replacements.mdx")
        assert_text_file_matches_fixture(output_file, "typedoc/typescript.mdx")
        page = read_mdx(output_file.parent, output_file.name)

        assert_contains_all(
            page,
            [
                "StableWidget",
                "Replaces: `LegacyWidget`",
                "Replaces: `makeLegacyWidget`",
                "replacement target updated",
            ],
        )
        assert_contains_none(page, ["@alpha", "@beta", "@stable", "@replaces", "@deprecated"])

    @unittest.skip("typedoc writes a single output file, not a pruned output directory")
    def test_cli_prunes_stale_output(self) -> None:
        pass

    @unittest.skip("typedoc CLI does not expose docs-json navigation flags")
    def test_cli_updates_docs_json_navigation_idempotently(self) -> None:
        pass

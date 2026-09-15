from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_canton_config_reference as generator


def option(path: str, **overrides) -> dict:
    base = {
        "path": path,
        "declaredBy": "Test.field",
        "scalaType": "String",
        "valueType": {"kind": "scalar", "name": "string"},
        "required": False,
        "optional": False,
        "defaultExpr": None,
        "defaultValue": None,
        "defaultOrigin": None,
        "observedValue": None,
        "doc": None,
        "docFormat": None,
        "maturity": "stable",
        "appliesWhen": [],
        "provenance": {"file": "Test.scala", "line": 1},
        "evidence": ["scaladoc"],
    }
    base.update(overrides)
    return base


AGGREGATION = "canton.monitoring.metrics.histograms[].aggregation"


def when(tag: str) -> list[dict]:
    return [{"at": f"{AGGREGATION}.type", "equals": tag, "of": "AggregationType"}]


def sample_artifact() -> dict:
    return {
        "schemaVersion": "2.0.0",
        "cantonVersion": "3.7.0-test",
        "gitSha": "abc123",
        "rootPath": "canton",
        "defaultsFrom": None,
        "pathPlaceholders": {"<participant>": "user-chosen name of each entry under canton.participants"},
        "options": [
            option("canton.monitoring.metrics.histograms", valueType={"kind": "array", "element": "HistogramDefinition"}, defaultValue=[], defaultOrigin="source", doc="customized histogram definitions"),
            option("canton.monitoring.metrics.histograms[].name", required=True, doc="Instrument name with wildcards * and ?"),
            option(f"{AGGREGATION}.type", valueType={"kind": "enum", "type": "AggregationType", "values": ["buckets", "exponential"]}, required=True),
            option(f"{AGGREGATION}.boundaries", valueType={"kind": "array", "element": "Double"}, required=True, appliesWhen=when("buckets")),
            option(f"{AGGREGATION}.max-buckets", valueType={"kind": "scalar", "name": "int"}, required=True, appliesWhen=when("exponential")),
            option(f"{AGGREGATION}.max-scale", valueType={"kind": "scalar", "name": "int"}, required=True, appliesWhen=when("exponential")),
            option("canton.participants.<participant>.admin-api.port", valueType={"kind": "scalar", "name": "int", "scalaType": "Port"}, defaultValue=30002, defaultOrigin="load-time", doc="Braces {x} and <angles> must survive MDX"),
            option("canton.participants.<participant>.parameters.engine.extensions.<extension>.address", required=True),
        ],
        "types": [
            {"name": "AggregationType", "kind": "coproduct", "discriminator": "type", "variants": [{"tag": "buckets", "type": "Buckets"}, {"tag": "exponential", "type": "Exponential"}], "values": []},
        ],
        "deprecatedPaths": [],
        "diagnostics": {"filesParsed": 1, "filesFailed": 0, "optionsTotal": 7, "optionsDocumented": 3},
    }


class CantonConfigReferenceTests(unittest.TestCase):
    def test_types_page_renders_one_block_per_variant_inside_the_list(self) -> None:
        types = generator.render_pages(sample_artifact())["types.mdx"]
        self.assertIn("## AggregationType", types)
        self.assertIn("Set `type` to one of `buckets`, `exponential`.", types)
        self.assertIn("- `canton.monitoring.metrics.histograms[].aggregation`", types)
        # The list belongs to `histograms`; the aggregation is an object inside an element of it.
        self.assertIn("canton.monitoring.metrics.histograms = [\n  {\n    aggregation {\n      type = buckets\n      boundaries = [ ]   # required\n    }\n  }\n]", types)
        self.assertIn("      type = exponential\n      max-buckets = 0   # required\n      max-scale = 0   # required", types)
        # Alternatives are separate blocks, never siblings in one list.
        self.assertEqual(types.count("```hocon"), 2)
        # Each variant's keys are tabulated beneath its block.
        self.assertIn("| `max-scale` | int | **required** |  |", types)

    def test_required_section_says_when_and_links_types(self) -> None:
        monitoring = generator.render_pages(sample_artifact())["monitoring.mdx"]
        required = monitoring.split("## Required")[1].split("## All options")[0]
        link = f"{generator.PAGE_URL_PREFIX}/types#aggregationtype"
        self.assertIn("| `metrics.histograms[].name` | string | `metrics.histograms[]` is configured | Instrument name with wildcards * and ? |", required)
        self.assertIn(
            "| `metrics.histograms[].aggregation.type` | one of `buckets`, `exponential` | "
            f"`metrics.histograms[].aggregation` is configured | Choose one type — see [AggregationType]({link}). |",
            required,
        )
        self.assertIn(
            "| `metrics.histograms[].aggregation.boundaries` | array of Double | "
            "`metrics.histograms[].aggregation` is configured and `metrics.histograms[].aggregation.type` is `buckets` |",
            required,
        )
        # Nothing that has a default appears here.
        self.assertNotIn("| `metrics.histograms` |", required)
        # The required view also has the skeleton as HOCON, first; variant-gated keys are commented
        # with their condition so the block stays one valid document.
        self.assertLess(required.index("```hocon"), required.index("| Key | Type | Required when |"))
        self.assertIn(
            "canton.monitoring {\n  metrics {\n    histograms = [\n      {\n        aggregation {\n"
            "          # boundaries = [ ]   # required when type = buckets\n"
            "          # max-buckets = 0   # required when type = exponential\n"
            "          # max-scale = 0   # required when type = exponential\n"
            "          type = buckets|exponential   # required\n        }\n"
            "        name = \"...\"   # required\n      }\n    ]\n  }\n}",
            required,
        )

    def test_sections_pair_hocon_with_the_table_over_the_same_keys(self) -> None:
        monitoring = generator.render_pages(sample_artifact())["monitoring.mdx"]
        all_options = monitoring.split("## All options")[1]
        self.assertNotIn("<Tabs>", monitoring)
        self.assertLess(all_options.index("```hocon"), all_options.index("| Key | Type | Default | Description |"))
        # The section-level block lists every key not gated by a nested type, defaults included,
        # and shows a discriminator as the values it accepts.
        # The section HOCON is exhaustive: gated keys are commented with their condition, so the
        # block and the table beneath it cover the same keys.
        self.assertIn(
            "canton.monitoring.metrics {\n  histograms = [\n    {\n      aggregation {\n"
            "        # boundaries = [ ]   # required when type = buckets\n"
            "        # max-buckets = 0   # required when type = exponential\n"
            "        # max-scale = 0   # required when type = exponential\n"
            "        type = buckets|exponential   # required\n      }\n      name = \"...\"   # required\n"
            "    }\n  ]\n}",
            all_options,
        )
        self.assertIn(
            f"Takes a `type`: [AggregationType]({generator.PAGE_URL_PREFIX}/types#aggregationtype) at `histograms[].aggregation`.",
            monitoring,
        )

    def test_table_groups_variant_keys_under_type_headers(self) -> None:
        monitoring = generator.render_pages(sample_artifact())["monitoring.mdx"]
        rows = [line for line in monitoring.splitlines() if line.startswith("|")]
        text = "\n".join(rows).replace(" ", ".")
        # Plain section header carries the discriminator row; variant headers carry their keys.
        self.assertIn("| ....**aggregation** |", text)
        self.assertIn("| ........`type` | one of `buckets`, `exponential` | **required** | Choose one type — see [AggregationType](" + generator.PAGE_URL_PREFIX + "/types#aggregationtype). |", text)
        self.assertIn("| ....**aggregation** `type = buckets` |", text)
        self.assertIn("| ........`boundaries` | array of Double | **required** |  |", text)
        self.assertIn("| ....**aggregation** `type = exponential` |", text)
        # The discriminator row leads its group.
        self.assertLess(text.index("`type` | one of"), text.index("`boundaries`"))

    def test_prose_is_mdx_safe_and_load_time_defaults_are_marked(self) -> None:
        participant = generator.render_pages(sample_artifact())["participant-node.mdx"]
        self.assertIn("Braces \\{x\\} and &lt;angles&gt; must survive MDX", participant)
        self.assertIn("| `port` | int (Port) | `30002` † |", participant)
        self.assertIn("- `<participant>` — `user-chosen name of each entry under canton.participants`", participant)
        # A placeholder that is itself a section header must not become a JSX tag.
        self.assertIn("**&lt;extension&gt;**", participant)
        self.assertNotIn("**<extension>**", participant)

    def test_overview_links_every_page_and_marks_provenance(self) -> None:
        pages = generator.render_pages(sample_artifact())
        overview = pages["overview.mdx"]
        self.assertIn('GENERATED_FROM source="digital-asset/canton" ref="abc123"', overview)
        for name in pages:
            if name != "overview.mdx":
                self.assertIn(f'href="{generator.PAGE_URL_PREFIX}/{name[:-4]}"', overview)
        self.assertIn("types.mdx", pages)

    def test_nav_insertion_is_idempotent_and_anchored(self) -> None:
        docs = {
            "navigation": {
                "products": [
                    {
                        "product": "Global Synchronizer",
                        "pages": [
                            {"group": "Reference", "pages": ["a", generator.NAV_ANCHOR_PAGE, "b"]},
                        ],
                    }
                ]
            }
        }
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "docs.json"
            path.write_text(json.dumps(docs), encoding="utf-8")
            generator.update_nav(path, ["x/overview", "x/participant-node"])
            generator.update_nav(path, ["x/overview", "x/participant-node", "x/features"])
            pages = json.loads(path.read_text())["navigation"]["products"][0]["pages"][0]["pages"]
        self.assertEqual(pages[0], "a")
        self.assertEqual(pages[1], generator.NAV_ANCHOR_PAGE)
        self.assertEqual(pages[2], {"group": "Canton Configuration", "pages": ["x/overview", "x/participant-node", "x/features"]})
        self.assertEqual(pages[3], "b")
        self.assertEqual(len(pages), 4)


if __name__ == "__main__":
    unittest.main()

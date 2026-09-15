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
    def test_union_renders_one_block_per_variant_inside_the_list(self) -> None:
        pages = generator.render_pages(sample_artifact())
        monitoring = pages["monitoring.mdx"]
        # The label is relative to the `## metrics` section the example sits under.
        self.assertIn("**`histograms[].aggregation`** supports these types: `buckets`, `exponential`.", monitoring)
        # The list belongs to `histograms`; the aggregation is an object inside an element of it.
        self.assertIn("canton.monitoring.metrics.histograms = [\n  {\n    aggregation {\n      type = buckets\n      boundaries = [ ]   # required\n    }\n  }\n]", monitoring)
        self.assertIn("      type = exponential\n      max-buckets = 0   # required\n      max-scale = 0   # required", monitoring)
        # Alternatives are separate blocks, never siblings in one list; the third block is the
        # section-level HOCON view that precedes them.
        self.assertEqual(monitoring.count("```hocon"), 3)

    def test_sections_offer_hocon_first_then_table(self) -> None:
        monitoring = generator.render_pages(sample_artifact())["monitoring.mdx"]
        self.assertLess(monitoring.index('<Tab title="HOCON">'), monitoring.index('<Tab title="Table">'))
        # The section-level block lists every key not gated by a nested type, defaults included,
        # and shows a discriminator as the values it accepts.
        self.assertIn(
            "canton.monitoring.metrics {\n  histograms = [\n    {\n      aggregation {\n"
            "        type = buckets|exponential   # required\n      }\n      name = \"...\"   # required\n"
            "    }\n  ]\n}",
            monitoring,
        )
        # Variant-specific keys live only in their variant's block.
        section_block = monitoring.split("```hocon")[1]
        self.assertNotIn("boundaries", section_block)

    def test_table_groups_variant_keys_under_type_headers(self) -> None:
        monitoring = generator.render_pages(sample_artifact())["monitoring.mdx"]
        rows = [line for line in monitoring.splitlines() if line.startswith("|")]
        text = "\n".join(rows).replace(" ", ".")
        # Plain section header carries the discriminator row; variant headers carry their keys.
        self.assertIn("| ....**aggregation** |", text)
        self.assertIn("| ........`type` | one of `buckets`, `exponential` | **required** | Selects which of the keys below apply; see the example above. |", text)
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

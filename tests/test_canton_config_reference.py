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
        "schemaVersion": "2.1.0",
        "cantonVersion": "3.7.0-test",
        "gitSha": "abc123",
        "rootPath": "canton",
        "defaultsFrom": None,
        "pathPlaceholders": {"<participant>": "user-chosen name of each entry under canton.participants"},
        "options": [
            # Sections say whether the object exists by default; a participant constructs every
            # section, a remote participant declares its client sections without defaults.
            option("canton.monitoring.metrics", valueType={"kind": "section", "type": "MetricsConfig"}, defaultExpr="MetricsConfig()"),
            option("canton.participants.<participant>.admin-api", valueType={"kind": "section", "type": "AdminServerConfig"}, defaultExpr="AdminServerConfig()"),
            option("canton.remote-participants.<remote-participant>.admin-api", valueType={"kind": "section", "type": "FullClientConfig"}, required=True),
            option("canton.remote-participants.<remote-participant>.admin-api.address", defaultValue="127.0.0.1", defaultOrigin="source"),
            option("canton.remote-participants.<remote-participant>.admin-api.port", valueType={"kind": "scalar", "name": "int", "scalaType": "Port"}, required=True, doc="Port of the admin API"),
            option("canton.remote-participants.<remote-participant>.ledger-api", valueType={"kind": "section", "type": "FullClientConfig"}, required=True),
            option("canton.remote-participants.<remote-participant>.ledger-api.address", defaultValue="127.0.0.1", defaultOrigin="source"),
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
        self.assertNotIn("**Path**", types)
        # Each variant's keys are tabulated in the tab behind its block.
        self.assertIn("### `type = exponential`\n\n<Tabs>\n<Tab title=\"HOCON\">", types)
        self.assertIn("| `max-scale` | int | **required** |  |", types)

    def test_minimum_required_is_what_must_be_written_for_the_node_to_start(self) -> None:
        pages = generator.render_pages(sample_artifact())
        title = generator.REQUIRED_TITLE
        self.assertEqual(title, "Minimum Required Fields")
        # A participant constructs every section by default, so nothing has to be written except
        # the entry itself. Keys that are required *within* an optional section are not listed.
        participant = pages["participant-node.mdx"].split(f"## {title}")[1].split(f"## {generator.ALL_OPTIONS_TITLE}")[0]
        self.assertIn("Nothing under `canton.participants.<participant>` has to be set", participant)
        self.assertIn("```hocon\ncanton.participants.<participant> { }\n```", participant)
        self.assertNotIn("| Key |", participant)
        self.assertNotIn("extensions", participant)
        # Under monitoring the required keys live inside list elements, which exist only when
        # written, so the minimum is empty and there is no node entry to show.
        monitoring = pages["monitoring.mdx"].split(f"## {title}")[1].split(f"## {generator.ALL_OPTIONS_TITLE}")[0]
        self.assertIn("Nothing under `canton.monitoring` has to be set", monitoring)
        self.assertNotIn("```hocon", monitoring)
        self.assertNotIn("histograms", monitoring)
        # A remote participant declares its client sections without defaults: the port with no
        # default must be written; a section with only defaulted keys must still be present.
        remote = pages["remote-participant.mdx"].split(f"## {title}")[1].split(f"## {generator.ALL_OPTIONS_TITLE}")[0]
        self.assertIn(
            "```hocon\ncanton.remote-participants.<remote-participant> {\n  admin-api {\n    port = 0   # required\n  }\n"
            "  ledger-api { }   # required\n}\n```",
            remote,
        )
        self.assertIn("| `admin-api.port` | int (Port) | always | Port of the admin API |", remote)
        self.assertIn("| `ledger-api` | section (FullClientConfig) | always |  |", remote)
        self.assertNotIn("`admin-api.address`", remote)
        self.assertLess(remote.index("```hocon"), remote.index("| Key | Type | Required when |"))

    def test_every_page_documents_the_types_it_uses(self) -> None:
        pages = generator.render_pages(sample_artifact())
        monitoring = pages["monitoring.mdx"]
        types_section = monitoring.split(f"## {generator.TYPES_TITLE}")[1]
        self.assertIn("### AggregationType\n\nSet `type` to one of `buckets`, `exponential`.", types_section)
        self.assertIn("- `canton.monitoring.metrics.histograms[].aggregation`", types_section)
        self.assertIn("#### `type = buckets`\n\n<Tabs>\n<Tab title=\"HOCON\">", types_section)
        self.assertIn("| `boundaries` | array of Double | **required** |  |", types_section)
        # Links from the tables stay on the page.
        self.assertIn("Choose one type — see [AggregationType](#aggregationtype).", monitoring)
        # A page that uses no type has no such section; the types page still collects everything.
        self.assertNotIn(f"## {generator.TYPES_TITLE}", pages["remote-participant.mdx"])
        self.assertIn("## AggregationType", pages["types.mdx"])

    def test_sections_pair_hocon_with_the_table_over_the_same_keys(self) -> None:
        monitoring = generator.render_pages(sample_artifact())["monitoring.mdx"]
        all_options = monitoring.split(f"## {generator.ALL_OPTIONS_TITLE}")[1].split(f"## {generator.TYPES_TITLE}")[0]
        # Every section heading is its absolute path, and the pair beneath is tabbed: HOCON first,
        # the table behind it.
        self.assertIn(
            "### `canton.monitoring.metrics`\n\n<Tabs>\n<Tab title=\"HOCON\">\n\n```hocon",
            all_options,
        )
        self.assertNotIn("**Path**", monitoring)
        self.assertIn("</Tab>\n<Tab title=\"Table\">\n\n| Key | Type | Default | Description |", all_options)
        self.assertLess(all_options.index("```hocon"), all_options.index("| Key | Type | Default | Description |"))
        # No separate "Takes a `type`" announcement: the discriminator rows carry the link.
        self.assertNotIn("Takes a `type`", monitoring)
        # The section block holds the keys that apply whatever the type; then every type site is
        # enumerated, one complete block per variant, so the HOCON tab and the table cover the same
        # keys without merging alternatives into one block.
        hocon_tab = all_options.split('<Tab title="HOCON">')[1].split("</Tab>")[0]
        self.assertIn(
            "canton.monitoring.metrics {\n  histograms = [\n    {\n      aggregation {\n"
            "        type = buckets|exponential   # required\n      }\n      name = \"...\"   # required\n"
            "    }\n  ]\n}",
            hocon_tab,
        )
        self.assertNotIn("# boundaries", hocon_tab)
        self.assertIn(
            "`histograms[].aggregation` supports these types: `buckets`, `exponential`. "
            "Pick one; each block is a complete example of that choice.",
            hocon_tab,
        )
        self.assertIn("      type = buckets\n      boundaries = [ ]   # required\n", hocon_tab)
        self.assertIn("      type = exponential\n      max-buckets = 0   # required\n      max-scale = 0   # required\n", hocon_tab)
        self.assertEqual(hocon_tab.count("```hocon"), 3)
        # The section-level HOCON never lists a section entry as if it were a key.
        self.assertNotIn("metrics = ", hocon_tab)

    def test_table_groups_variant_keys_under_type_headers(self) -> None:
        monitoring = generator.render_pages(sample_artifact())["monitoring.mdx"]
        rows = [line for line in monitoring.splitlines() if line.startswith("|")]
        text = "\n".join(rows).replace(" ", ".")
        # Plain section header carries the discriminator row; variant headers carry their keys.
        self.assertIn("| ....**aggregation** |", text)
        self.assertIn("| ........`type` | one of `buckets`, `exponential` | **required** | Choose one type — see [AggregationType](#aggregationtype). |", text)
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

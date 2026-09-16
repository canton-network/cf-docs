#!/usr/bin/env python3
"""Generate the Canton configuration reference pages from Canton's config-reference.json.

Canton's `docs-open/generateConfigReference` sbt task parses the config case classes and their
Scaladoc into one JSON artifact: every HOCON key with its type, default, prose, and the `type`
discriminators that gate it. This script renders that artifact as one MDX page per node type plus an
overview, and registers them in docs.json.

    python3 scripts/generate_canton_config_reference.py --artifact path/to/config-reference.json

The artifact is not yet published with Canton releases, so for now it is produced locally with
`sbt docs-open/generateConfigReference` in a Canton checkout and passed in. When it ships as a
release asset the download will slot in here the way generate_canton_metrics_reference.py resolves
its Canton ref.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

from docs_env import ensure_repo_direnv

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_JSON_PATH = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs-main" / "global-synchronizer" / "reference" / "canton-config"
PAGE_URL_PREFIX = "/global-synchronizer/reference/canton-config"
SOURCE_REPO = "digital-asset/canton"
ARTIFACT_PATH_IN_CANTON = "docs-open/target/config-reference.json"
SUPPORTED_SCHEMA_MAJOR = "2"
TYPES_PAGE = "types"

PRODUCT_LABEL = "Global Synchronizer"
PARENT_GROUP_LABEL = "Reference"
NAV_GROUP_LABEL = "Canton Configuration"
NAV_ANCHOR_PAGE = "global-synchronizer/reference/configuration-reference"

# Top-level sections, in the order an operator meets them: a path prefix as it appears in the
# artifact, the page title, and a one-line description for the overview card.
SECTIONS = [
    ("canton.participants.<participant>", "Participant node", "Ledger API, admin API, storage, crypto and parameters of a participant."),
    ("canton.sequencers.<sequencer>", "Sequencer node", "Sequencer implementation, public and admin APIs, storage and ordering."),
    ("canton.mediators.<mediator>", "Mediator node", "Admin API, storage, crypto and parameters of a mediator."),
    ("canton.remote-participants.<remote-participant>", "Remote participant", "How the console reaches a participant running elsewhere."),
    ("canton.remote-sequencers.<remote-sequencer>", "Remote sequencer", "How the console reaches a sequencer running elsewhere."),
    ("canton.remote-mediators.<remote-mediator>", "Remote mediator", "How the console reaches a mediator running elsewhere."),
    ("canton.monitoring", "Monitoring", "Logging, metrics, tracing and health checks."),
    ("canton.parameters", "Global parameters", "Process-wide settings: clock, timeouts, startup behaviour."),
    ("canton.features", "Features", "Feature flags for preview, testing and repair commands."),
]

MATURITY_BADGE = {"alpha": "**alpha**", "beta": "**beta**", "deprecated": "**deprecated**", "stable": ""}

# Literal non-breaking spaces, not `&nbsp;` entities: MDX passes entities through, but a plain
# markdown preview shows them as text, and the pages are reviewed in both.
INDENT = " " * 4

PLACEHOLDERS = {
    "string": '"..."',
    "path": '"/path/to/file"',
    "int": "0",
    "number": "0",
    "boolean": "false",
    "duration": '"30 seconds"',
    "config-object": "{ }",
    "config-value": "{ }",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifact", type=Path, required=True, help="config-reference.json from Canton")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-json", type=Path, default=DOCS_JSON_PATH)
    parser.add_argument("--skip-nav", action="store_true", help="Write pages without touching docs.json")
    parser.add_argument("--skip-direnv", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


# -- MDX text ----------------------------------------------------------------------------------


def mdx_text(text: str) -> str:
    """Make prose safe outside a code span: MDX reads `<` and `{` as JSX."""
    return text.replace("{", "\\{").replace("}", "\\}").replace("<", "&lt;").replace(">", "&gt;")


def clean_prose(text: str | None) -> str:
    """Flatten Scaladoc prose into a table cell.

    Scaladoc `[[Foo]]` links become `Foo`: a wiki link to a Scala symbol means nothing to someone
    reading config docs. Everything else is left as written, then escaped for MDX and for the
    table.
    """
    if not text:
        return ""
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda m: m.group(1).split(".")[-1], text)
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    text = re.sub(r"^[-*]\s+", "", text)
    # Escape outside code spans only; a code span keeps its braces and brackets literally.
    parts = re.split(r"(`[^`]*`)", text)
    escaped = "".join(part if part.startswith("`") else mdx_text(part) for part in parts)
    return escaped.replace("|", "\\|")


def render_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if isinstance(value, (int, float)):
        return f"`{value}`"
    if isinstance(value, str):
        return '`""`' if value == "" else f"`{value}`"
    if isinstance(value, list):
        return "`[]`" if not value else "`" + ", ".join(str(v) for v in value) + "`"
    if isinstance(value, dict):
        return "`{}`" if not value else "`" + json.dumps(value) + "`"
    return f"`{value}`"


def render_type(value_type: dict) -> str:
    kind = value_type.get("kind")
    if kind == "scalar":
        name = value_type.get("name", "string")
        scala = value_type.get("scalaType")
        return f"{name} ({scala})" if scala and scala != name else name
    if kind == "array":
        element = value_type.get("element", "value")
        return "array of " + {"String": "string", "Int": "int", "Long": "int", "Boolean": "boolean"}.get(element, element)
    if kind == "enum":
        values = value_type.get("values")
        if values:
            return "one of " + ", ".join(f"`{v}`" for v in values)
        return f"enum ({value_type.get('type', 'see types')})"
    if kind == "object":
        return "object"
    if kind == "generic":
        return f"depends on use ({value_type.get('typeParameter', '?')})"
    if kind == "unresolved":
        return f"{value_type.get('scalaType', 'unknown')} (unclassified)"
    return kind or "unknown"


def render_default(option: dict) -> str:
    origin = option.get("defaultOrigin")
    value = option.get("defaultValue")
    observed = option.get("observedValue")
    if value is not None or origin:
        rendered = render_value(value)
        if origin == "load-time":
            return f"{rendered} †"
        if observed is not None:
            return f"{rendered} (in practice {render_value(observed)}) ◊"
        return rendered
    if option.get("required"):
        return "**required**"
    expr = option.get("defaultExpr")
    if expr:
        if expr.strip() == "None":
            return "_unset_"
        return f"`{expr.replace('|', '\\|')}` ‡"
    if option.get("optional"):
        return "_unset_"
    return ""


# -- structure ---------------------------------------------------------------------------------


def group_options(options: list[dict]) -> "OrderedDict[str, list[dict]]":
    buckets: "OrderedDict[str, list[dict]]" = OrderedDict((prefix, []) for prefix, _, _ in SECTIONS)
    other: list[dict] = []
    for option in options:
        for prefix, _, _ in SECTIONS:
            if option["path"] == prefix or option["path"].startswith(prefix + "."):
                buckets[prefix].append(option)
                break
        else:
            other.append(option)
    if other:
        buckets["other"] = other
    return buckets


def subsection_key(path: str, prefix: str) -> str:
    relative = path[len(prefix) :].lstrip(".")
    segments = [segment for segment in relative.split(".") if segment]
    return segments[0] if len(segments) > 1 else ""


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


# -- tables ------------------------------------------------------------------------------------


def collapse_variants(options: list[dict]) -> list[tuple[dict, dict[str, set[str]]]]:
    """Merge rows that differ only in which variant of a union they belong to."""
    merged: "OrderedDict[tuple, tuple[dict, dict[str, set[str]]]]" = OrderedDict()
    for option in options:
        signature = (
            option["path"],
            json.dumps(option["valueType"], sort_keys=True),
            render_default(option),
            option.get("doc"),
            option.get("maturity"),
            tuple(sorted(condition["at"] for condition in option["appliesWhen"])),
        )
        entry = merged.setdefault(signature, (option, {}))
        for condition in option["appliesWhen"]:
            entry[1].setdefault(condition["at"], set()).add(condition["equals"])
    return list(merged.values())


Row = tuple[int, str, "dict | None", str]


def group_rows(
    rows: list[tuple[dict, dict[str, set[str]]]],
    prefix: str,
    variants_by_type: dict[str, list[str]],
) -> list[Row]:
    """Order rows into a tree walk that shows both nesting and variant membership.

    Each entry is (depth, label, option-or-None, header note). A discriminated section becomes one
    header per `type` value with the keys that value accepts beneath it; keys every variant accepts
    sit under a plain header for the section together with the `type` row. A key accepted by several
    but not all variants is repeated under each, so every variant header is a complete list -- the
    same shape as the example blocks above the table.
    """
    tree: "OrderedDict" = OrderedDict()

    def block(node: "OrderedDict", key) -> "OrderedDict":
        child = node.get(key)
        if not isinstance(child, dict) or "__leaf__" in child:
            node[key] = OrderedDict()
        return node[key]

    def split(conditions: dict[str, set[str]], section: str):
        return next((at for at in conditions if at.rsplit(".", 1)[0] == section), None)

    def variant_labels(section_label: str, split_at: str, conditions, union_of):
        accepted = conditions[split_at]
        known = variants_by_type.get(union_of.get(split_at, ""), [])
        if known and accepted >= set(known):
            return None
        key = split_at.rsplit(".", 1)[1]
        ordered = [tag for tag in known if tag in accepted] or sorted(accepted)
        return [
            (section_label, f"{key} = {tag}", known.index(tag) if tag in known else index)
            for index, tag in enumerate(ordered)
        ]

    def insert(node, segments, absolute, option, conditions, union_of) -> None:
        split_at = split(conditions, absolute)
        if split_at is not None:
            remaining = {at: tags for at, tags in conditions.items() if at != split_at}
            labels = variant_labels(absolute.rsplit(".", 1)[-1], split_at, conditions, union_of)
            if labels is None:
                insert(node, segments, absolute, option, remaining, union_of)
            else:
                for label in labels:
                    insert(block(node, label), segments, absolute, option, remaining, union_of)
            return

        if not segments:
            return
        head, rest = segments[0], segments[1:]
        section = f"{absolute}.{head}"
        if not rest:
            existing = node.get(head)
            if isinstance(existing, dict) and "__leaf__" not in existing:
                return
            node[head] = {"__leaf__": option}
            return

        split_at = split(conditions, section)
        if split_at is None:
            insert(block(node, head), rest, section, option, conditions, union_of)
            return

        remaining = {at: tags for at, tags in conditions.items() if at != split_at}
        labels = variant_labels(head, split_at, conditions, union_of)
        if labels is None:
            insert(block(node, head), rest, section, option, remaining, union_of)
        else:
            for label in labels:
                insert(block(node, label), rest, section, option, remaining, union_of)

    for option, conditions in rows:
        relative = option["path"][len(prefix) :].lstrip(".") or option["path"].split(".")[-1]
        union_of = {condition["at"]: condition["of"] for condition in option["appliesWhen"]}
        insert(tree, relative.split("."), prefix, option, dict(conditions), union_of)

    out: list[Row] = []

    def walk(node: "OrderedDict", depth: int) -> None:
        leaves = [(k, v) for k, v in node.items() if "__leaf__" in v]
        sections = [(k, v) for k, v in node.items() if "__leaf__" not in v]
        first_seen: dict[str, int] = {}
        for k, _ in sections:
            first_seen.setdefault(k[0] if isinstance(k, tuple) else k, len(first_seen))
        sections.sort(
            key=lambda kv: (
                first_seen[kv[0][0] if isinstance(kv[0], tuple) else kv[0]],
                isinstance(kv[0], tuple),
                kv[0][2] if isinstance(kv[0], tuple) else 0,
            )
        )
        for name, child in leaves:
            out.append((depth, name, child["__leaf__"], ""))
        for name, child in sections:
            if isinstance(name, tuple):
                out.append((depth, name[0], None, name[1]))
            else:
                out.append((depth, name, None, ""))
            walk(child, depth + 1)

    walk(tree, 0)
    return out


def union_link(union: str) -> str:
    return f"{PAGE_URL_PREFIX}/{TYPES_PAGE}#{slug(union)}"


def discriminator_index(options: list[dict]) -> dict[str, str]:
    """Discriminator path -> the union it selects, for every union any of these keys depends on."""
    return {condition["at"]: condition["of"] for option in options for condition in option["appliesWhen"]}


def render_table(options: list[dict], prefix: str, variants_by_type: dict[str, list[str]]) -> list[str]:
    discriminators = discriminator_index(options)
    lines = ["| Key | Type | Default | Description |", "|---|---|---|---|"]
    for depth, label, option, note in group_rows(collapse_variants(options), prefix, variants_by_type):
        pad = INDENT * depth
        if option is None:
            # Bold text, not bold code: in the site theme a bold code chip is indistinguishable from a
            # plain one, and the section rows must read as headers at a glance.
            # A header can be a placeholder such as `<key>`; outside a code span MDX would read
            # that as a JSX tag, so the label is escaped.
            title = f"{pad}**{mdx_text(label)}**" + (f" `{note}`" if note else "")
            lines.append(f"| {title} |  |  |  |")
            continue
        badge = MATURITY_BADGE.get(option.get("maturity", "stable"), "")
        key = f"{pad}`{label}`" + (f" {badge}" if badge else "")
        description = clean_prose(option.get("doc"))
        if option["path"] in discriminators:
            union = discriminators[option["path"]]
            description = f"Choose one type — see [{union}]({union_link(union)})." + (f" {description}" if description else "")
        lines.append(f"| {key} | {render_type(option['valueType'])} | {render_default(option)} | {description} |")
    return lines


# -- HOCON examples ----------------------------------------------------------------------------


def placeholder_for(option: dict) -> str:
    value_type = option["valueType"]
    kind = value_type.get("kind")
    if kind == "enum":
        values = value_type.get("values") or []
        return values[0] if values else '"..."'
    if kind == "array":
        return "[ ]"
    return PLACEHOLDERS.get(value_type.get("name", ""), '"..."')


def type_hint(option: dict) -> str:
    value_type = option["valueType"]
    kind = value_type.get("kind")
    if kind == "enum":
        return "|".join(value_type.get("values") or ["..."])
    if kind == "array":
        return "[ ... ]"
    return f"<{value_type.get('name', kind or 'value')}>"


def example_value(option: dict) -> str | None:
    """A real default, or nothing: an invented value in an example someone may copy is worse than
    an omitted key."""
    value = option.get("defaultValue")
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[ ]"
    if isinstance(value, dict):
        return "{ }"
    if isinstance(value, str):
        if option["valueType"].get("kind") == "enum":
            return value
        return f'"{value}"' if not value.isdigit() else value
    return None


def find_unions(options: list[dict]) -> "OrderedDict[str, dict]":
    unions: "OrderedDict[str, dict]" = OrderedDict()
    for option in options:
        for condition in option["appliesWhen"]:
            entry = unions.setdefault(condition["of"], {"paths": set()})
            entry["paths"].add(condition["at"])
    return unions


def applicable_keys(section: str, discriminator: str, tag: str, options_by_path: dict[str, list[dict]]) -> "OrderedDict[str, dict]":
    """Every key this variant accepts, relative to the section; keys gated by a deeper union are
    left to that union's own example."""
    keys: "OrderedDict[str, dict]" = OrderedDict()
    discriminator_key = discriminator.rsplit(".", 1)[1]
    for path, entries in options_by_path.items():
        if not path.startswith(section + "."):
            continue
        relative = path[len(section) + 1 :]
        if relative == discriminator_key:
            continue
        for option in entries:
            conditions = option["appliesWhen"]
            if not any(c["at"] == discriminator and c["equals"] == tag for c in conditions):
                continue
            if any(c["at"] != discriminator and c["at"].startswith(section + ".") for c in conditions):
                continue
            keys.setdefault(relative, option)
    return OrderedDict(sorted(keys.items()))


def nest(keys: "OrderedDict[str, dict]") -> dict:
    tree: dict = {}
    for relative, option in keys.items():
        node = tree
        segments = relative.split(".")
        for segment in segments[:-1]:
            existing = node.get(segment)
            if not isinstance(existing, dict) or existing.get("__leaf__") is not None:
                node[segment] = {}
            node = node[segment]
        leaf_name = segments[-1]
        if isinstance(node.get(leaf_name), dict) and node[leaf_name].get("__leaf__") is None:
            continue
        node[leaf_name] = {"__leaf__": option}

    def drop_redundant_arrays(node: dict) -> None:
        for name in list(node):
            if name.endswith("[]") and name[:-2] in node:
                node.pop(name[:-2], None)
        for child in node.values():
            if child.get("__leaf__") is None:
                drop_redundant_arrays(child)

    drop_redundant_arrays(tree)
    return tree


def condition_text(scope: str, relative: str, gates: list[tuple[str, set[str]]]) -> str:
    """`type = a|b` when the discriminator sits beside the key, otherwise its path from the section,
    so a condition inside a nested block stays unambiguous."""
    key_parent = relative.rsplit(".", 1)[0] if "." in relative else ""
    clauses = []
    for at, tags in gates:
        disc = at[len(scope) + 1 :] if at.startswith(scope + ".") else at
        disc_parent = disc.rsplit(".", 1)[0] if "." in disc else ""
        label = disc.rsplit(".", 1)[-1] if disc_parent == key_parent else disc
        clauses.append(f"{label} = " + "|".join(sorted(tags)))
    return " and ".join(clauses)


def render_block(tree: dict, indent: str, lines: list[str], seen: set[str], path: str = "") -> None:
    for name, child in tree.items():
        here = f"{path}.{name}" if path else name
        option = child.get("__leaf__")
        if option is None:
            if name.endswith("[]"):
                lines.append(f"{indent}{name[:-2]} = [")
                lines.append(f"{indent}  {{")
                render_block(child, indent + "    ", lines, seen, here)
                lines.append(f"{indent}  }}")
                lines.append(f"{indent}]")
            else:
                lines.append(f"{indent}{name} {{")
                render_block(child, indent + "  ", lines, seen, here)
                lines.append(f"{indent}}}")
            continue
        seen.add(here)
        # A key that only applies under a particular `type` is written as a comment carrying the
        # condition, so the block stays one valid document while still listing everything.
        when = option.get("__when__")
        if option["required"]:
            hint = type_hint(option) if option["valueType"].get("kind") == "enum" else placeholder_for(option)
            if when:
                lines.append(f"{indent}# {name} = {hint}   # required when {when}")
            else:
                lines.append(f"{indent}{name} = {hint}   # required")
            continue
        value = example_value(option)
        if when:
            lines.append(f"{indent}# {name} = {value if value is not None else type_hint(option)}   # when {when}")
        elif value is not None:
            lines.append(f"{indent}{name} = {value}")
        else:
            lines.append(f"{indent}# {name} = {type_hint(option)}")


def open_path(section: str) -> tuple[list[str], list[str], str]:
    """HOCON scaffolding down to a section. A `[]` segment is a list, so the path breaks there and
    reopens inside an element: `histograms[].aggregation` is `histograms = [ { aggregation { } } ]`."""
    opening: list[str] = []
    closing: list[str] = []
    indent = ""
    pending: list[str] = []
    for segment in section.split("."):
        if segment.endswith("[]"):
            pending.append(segment[:-2])
            opening += [f"{indent}{'.'.join(pending)} = [", f"{indent}  {{"]
            closing = [f"{indent}  }}", f"{indent}]"] + closing
            indent += "    "
            pending = []
        else:
            pending.append(segment)
    if pending:
        opening.append(f"{indent}{'.'.join(pending)} {{")
        closing = [f"{indent}}}"] + closing
        indent += "  "
    return opening, closing, indent


def render_variant_block(
    section: str, discriminator: str, tag: str, options_by_path: dict[str, list[dict]]
) -> tuple[list[str], "OrderedDict[str, str]"]:
    """A complete, standalone HOCON block for one variant, plus the unions nested inside it
    (relative path -> union name), which get their own sections rather than being expanded here."""
    discriminator_key = discriminator.rsplit(".", 1)[1]
    keys = applicable_keys(section, discriminator, tag, options_by_path)
    nested: "OrderedDict[str, str]" = OrderedDict()
    for entries in options_by_path.values():
        for option in entries:
            if not any(c["at"] == discriminator and c["equals"] == tag for c in option["appliesWhen"]):
                continue
            for condition in option["appliesWhen"]:
                if condition["at"] != discriminator and condition["at"].startswith(section + "."):
                    nested.setdefault(condition["at"][len(section) + 1 :], condition["of"])
    opening, closing, indent = open_path(section)
    block = ["```hocon", *opening, f"{indent}{discriminator_key} = {tag}"]
    seen: set[str] = set()
    render_block(nest(keys), indent, block, seen)
    if not keys and not nested:
        block.append(f"{indent}# takes no further keys")
    for path in nested:
        if path not in seen:
            block.append(f"{indent}# {path} takes a type of its own, documented separately")
    block += [*closing, "```", ""]
    return block, nested


def render_scope_hocon(scope: str, entries: list[dict], variants_by_type: dict[str, list[str]]) -> list[str]:
    """The whole section as HOCON: every key, with a discriminator shown as the values it accepts
    and a key that only applies under some `type` commented with that condition -- the same key set
    as the table that follows it."""
    keys: "OrderedDict[str, dict]" = OrderedDict()
    for option, conditions in collapse_variants(entries):
        union_of = {c["at"]: c["of"] for c in option["appliesWhen"]}
        gates: list[tuple[str, set[str]]] = []
        for at, accepted in conditions.items():
            if not at.startswith(scope + "."):
                continue
            known = set(variants_by_type.get(union_of.get(at, ""), []))
            if known and accepted >= known:
                continue
            gates.append((at, accepted))
        relative = option["path"][len(scope) :].lstrip(".")
        if not relative:
            continue
        tagged = dict(option)
        if gates:
            tagged["__when__"] = condition_text(scope, relative, gates)
        keys.setdefault(relative, tagged)
    if not keys:
        return []
    opening, closing, indent = open_path(scope)
    block = ["```hocon", *opening]
    render_block(nest(OrderedDict(sorted(keys.items()))), indent, block, set())
    block += [*closing, "```", ""]
    return block


def tabbed_pair(hocon: list[str], table: list[str]) -> list[str]:
    """The same keys two ways, one visible at a time: HOCON first, the table behind it."""
    # Tab bodies are left unindented: four leading spaces would turn a line into a code block.
    return [
        "<Tabs>",
        '<Tab title="HOCON">',
        "",
        *hocon,
        "",
        "</Tab>",
        '<Tab title="Table">',
        "",
        *table,
        "",
        "</Tab>",
        "</Tabs>",
        "",
    ]


def render_section_views(scope: str, entries: list[dict], variants_by_type: dict[str, list[str]]) -> list[str]:
    """One section as a labelled, tabbed pair: HOCON as you would write it, or the same keys as a
    table with their descriptions. Both cover exactly the same keys. Sections inside that take a
    `type` are not announced here: the table's discriminator rows link to the types page."""
    hocon = render_scope_hocon(scope, entries, variants_by_type)
    table = render_table(entries, scope, variants_by_type)
    if not hocon:
        return table + [""]
    return tabbed_pair(hocon, table)


def required_rows(prefix: str, entries: list[dict], variants_by_type: dict[str, list[str]]):
    """(relative path, option, enclosing section, variant conditions) for every required key."""
    rows = []
    for option, conditions in collapse_variants(entries):
        if not option["required"]:
            continue
        relative = option["path"][len(prefix) :].lstrip(".") or option["path"].split(".")[-1]
        parent = relative.rsplit(".", 1)[0] if "." in relative else ""
        union_of = {c["at"]: c["of"] for c in option["appliesWhen"]}
        gates: list[tuple[str, set[str]]] = []
        for at in sorted(conditions):
            tags = conditions[at]
            known = set(variants_by_type.get(union_of.get(at, ""), []))
            if known and tags >= known:
                continue
            gates.append((at[len(prefix) :].lstrip("."), tags))
        rows.append((relative, option, parent, gates))
    return rows


def render_required_hocon(prefix: str, entries: list[dict], variants_by_type: dict[str, list[str]]) -> list[str]:
    """The minimal skeleton: only the keys that must be set. A key required only under a particular
    `type` is written as a comment carrying that condition, so the block stays a single valid
    document rather than a mash of mutually exclusive variants."""
    rows = required_rows(prefix, entries, variants_by_type)
    if not rows:
        return []
    keys: "OrderedDict[str, dict]" = OrderedDict()
    for relative, option, _parent, gates in rows:
        tagged = dict(option)
        if gates:
            tagged["__when__"] = condition_text(prefix, relative, [(prefix + "." + at, tags) for at, tags in gates])
        keys.setdefault(relative, tagged)

    def write(tree: dict, indent: str, out: list[str]) -> None:
        for name, child in tree.items():
            option = child.get("__leaf__")
            if option is None:
                if name.endswith("[]"):
                    out += [f"{indent}{name[:-2]} = [", f"{indent}  {{"]
                    write(child, indent + "    ", out)
                    out += [f"{indent}  }}", f"{indent}]"]
                else:
                    out.append(f"{indent}{name} {{")
                    write(child, indent + "  ", out)
                    out.append(f"{indent}}}")
                continue
            hint = type_hint(option) if option["valueType"].get("kind") == "enum" else placeholder_for(option)
            when = option.get("__when__")
            if when:
                out.append(f"{indent}# {name} = {hint}   # required when {when}")
            else:
                out.append(f"{indent}{name} = {hint}   # required")

    opening, closing, indent = open_path(prefix)
    block = ["```hocon", *opening]
    write(nest(OrderedDict(sorted(keys.items()))), indent, block)
    block += [*closing, "```", ""]
    return block


def render_required_views(prefix: str, entries: list[dict], variants_by_type: dict[str, list[str]]) -> list[str]:
    hocon = render_required_hocon(prefix, entries, variants_by_type)
    if not hocon:
        return ["Nothing under this section has to be set: every key has a default.", ""]
    return tabbed_pair(hocon, render_required(prefix, entries, variants_by_type))


def render_required(prefix: str, entries: list[dict], variants_by_type: dict[str, list[str]]) -> list[str]:
    """Only what has to be set, and under what circumstances.

    Almost nothing in a node's configuration is required outright -- the required keys live inside
    sections you may or may not use, so each row says when it applies: when its enclosing section
    is configured, when a `type` has been chosen, or always. A discriminator is itself required
    whenever its section is, and links to the types page rather than repeating the choice here.
    """
    discriminators = discriminator_index(entries)
    rows: list[str] = []
    for relative, option, parent, gates in required_rows(prefix, entries, variants_by_type):
        when: list[str] = []
        if parent:
            when.append(f"`{parent}` is configured")
        for rel_at, tags in gates:
            listed = ", ".join(f"`{tag}`" for tag in sorted(tags))
            when.append(f"`{rel_at}` is " + ("one of " if len(tags) > 1 else "") + listed)
        union = discriminators.get(option["path"])
        if union:
            description = f"Choose one type — see [{union}]({union_link(union)})."
        else:
            description = clean_prose(option.get("doc"))
        rows.append(f"| `{relative}` | {render_type(option['valueType'])} | {' and '.join(when) or 'always'} | {description} |")
    if not rows:
        return ["Nothing under this section has to be set: every key has a default.", ""]
    return ["| Key | Type | Required when | Description |", "|---|---|---|---|", *rows, ""]


# -- pages -------------------------------------------------------------------------------------


def frontmatter(title: str, description: str) -> list[str]:
    return ["---", f'title: "{title}"', f'description: "{description}"', "---", ""]


def generated_marker(artifact: dict) -> str:
    return (
        f'{{/* GENERATED_FROM source="{SOURCE_REPO}" ref="{artifact["gitSha"]}" '
        f'version="{artifact["cantonVersion"]}" path="{ARTIFACT_PATH_IN_CANTON}" */}}'
    )


def reading_guide(artifact: dict, options: list[dict] | None) -> list[str]:
    declared = artifact.get("pathPlaceholders") or {}
    if options is None:
        used = set(declared)
    else:
        used = {seg for option in options for seg in option["path"].split(".") if seg.startswith("<") and seg.endswith(">")}
    placeholder_lines = [f"- `{token}` — `{meaning}`" for token, meaning in sorted(declared.items()) if token in used]

    return [
        "Canton is configured with [HOCON](https://github.com/lightbend/config/blob/master/HOCON.md). "
        "Scala field names appear as lowercase-with-dashes, so `maxInboundMessageSize` is written "
        "`max-inbound-message-size`. **The key set is closed**: an unrecognised key fails startup rather "
        "than being ignored, so a typo is caught immediately.",
        "",
        "Paths are rooted at `canton`. Segments in angle brackets are names you choose:",
        "",
        *placeholder_lines,
        "",
        "A `[]` suffix marks the fields of a list element. Keys marked **alpha** or **beta** are not "
        "covered by compatibility guarantees.",
        "",
        "**Required** lists only what you must set, and when: always, when you configure a particular "
        "section, or when you have chosen a particular `type`. **All options** covers every key, one "
        "section per heading, where the heading is the section's absolute path. Each is shown two "
        "ways behind tabs: **HOCON** as you would write it from the root, every key with its default, "
        "and **Table**, the same keys relative to the heading with their descriptions. A key that only "
        "applies under a particular `type` appears in the HOCON as a comment carrying that condition; in "
        "the table a **bold** row names a section and the keys indented beneath it live inside it.",
        "",
        "Some sections take a `type` that decides which other keys they accept. Those are documented "
        f"once on the [types page]({PAGE_URL_PREFIX}/{TYPES_PAGE}) and linked from wherever they occur.",
        "",
        "In the Default column:",
        "",
        "- a value is what the key holds when you do not set it;",
        "- **required** means startup fails unless you set it;",
        "- _unset_ means the feature is off, or the surrounding section is absent, until you set it;",
        "- † marks a value assigned while the configuration loads (a port, for example). The number shown "
        "is an example from the environment the defaults were captured in, not a guaranteed default;",
        "- ‡ marks a default written as an expression in the source that has not been evaluated; the "
        "expression is shown so you can find it;",
        "- ◊ marks a field that declares one default but was seen holding another in a running "
        "configuration, because the section that builds it passes an explicit value. Both are shown.",
        "",
    ]


def render_node_page(prefix: str, title: str, description: str, options: list[dict], artifact: dict, variants_by_type, unions, options_by_path) -> str:
    lines = [
        *frontmatter(title, description),
        generated_marker(artifact),
        "",
        f"Configuration under `{prefix}` for Canton {artifact['cantonVersion']}: {len(options)} keys. "
        f"Part of the [Canton configuration reference]({PAGE_URL_PREFIX}/overview).",
        "",
        '<Accordion title="How to read this page">',
        "",
        *reading_guide(artifact, options),
        "</Accordion>",
        "",
        "## Required",
        "",
        *render_required_views(prefix, options, variants_by_type),
        "## All options",
        "",
    ]

    by_subsection: "OrderedDict[str, list[dict]]" = OrderedDict()
    for option in options:
        by_subsection.setdefault(subsection_key(option["path"], prefix), []).append(option)

    direct = by_subsection.pop("", [])
    # Each heading is the section's absolute path, so a reader knows where in the configuration
    # the HOCON and table beneath it sit. The HOCON is written from the root; the table is
    # relative to the heading.
    if direct:
        lines += [f"### `{prefix}`", ""]
        lines += render_section_views(prefix, direct, variants_by_type)

    for subsection, entries in by_subsection.items():
        scope = prefix + "." + subsection
        lines += [f"### `{scope}`", ""]
        lines += render_section_views(scope, entries, variants_by_type)

    return "\n".join(lines).rstrip() + "\n"


def render_types_page(artifact: dict, variants_by_type, unions, options_by_path) -> str:
    """Every section that takes a `type`, documented once: what each type accepts, as HOCON and as
    a table, with the places in the configuration where the section occurs."""
    lines = [
        *frontmatter("Configuration types", "Sections of the Canton configuration that take a type, and the keys each type accepts."),
        generated_marker(artifact),
        "",
        "Some sections are a choice between shapes. You pick one by setting a `type` key, and that "
        "choice decides which other keys the section accepts; a key belonging to another type fails "
        "startup. Each such section is documented here once and linked from every page it appears on. "
        "Independent choices nest, so a type can contain further `type` keys; those link onward.",
        "",
    ]
    for union in sorted(unions):
        entry = unions[union]
        variants = variants_by_type.get(union) or []
        discriminator = min(entry["paths"], key=lambda path: (path.count("."), path))
        section = discriminator.rsplit(".", 1)[0]
        occurrences = sorted(path.rsplit(".", 1)[0] for path in entry["paths"])
        lines += [f"## {union}", ""]
        lines.append("Set `type` to one of " + ", ".join(f"`{tag}`" for tag in variants) + ".")
        lines += ["", "Occurs at:", ""]
        shown = occurrences[:8]
        lines += [f"- `{path}`" for path in shown]
        if len(occurrences) > len(shown):
            lines.append(f"- … and {len(occurrences) - len(shown)} more")
        lines.append("")
        for tag in variants:
            lines += [f"### `type = {tag}`", ""]
            block, nested = render_variant_block(section, discriminator, tag, options_by_path)
            keys = applicable_keys(section, discriminator, tag, options_by_path)
            if keys:
                table = ["| Key | Type | Default | Description |", "|---|---|---|---|"]
                for relative, option in keys.items():
                    table.append(f"| `{relative}` | {render_type(option['valueType'])} | {render_default(option)} | {clean_prose(option.get('doc'))} |")
                lines += tabbed_pair(block, table)
            else:
                lines += block
            if nested:
                links = ", ".join(f"[{inner}]({union_link(inner)}) at `{path}`" for path, inner in nested.items())
                lines += [f"Further types inside this one: {links}.", ""]
    return "\n".join(lines).rstrip() + "\n"


def render_overview(artifact: dict, buckets: "OrderedDict[str, list[dict]]") -> str:
    diagnostics = artifact.get("diagnostics", {})
    total = diagnostics.get("optionsTotal", len(artifact["options"]))
    documented = diagnostics.get("optionsDocumented", 0)
    coverage = round(documented * 100 / total) if total else 0
    titles = {prefix: (title, blurb) for prefix, title, blurb in SECTIONS}

    lines = [
        *frontmatter("Canton Configuration Reference", "Every configuration key a Canton node accepts, generated from the Canton sources."),
        generated_marker(artifact),
        "",
        f"Every configuration key Canton {artifact['cantonVersion']} accepts: {total} keys, {documented} ({coverage}%) "
        "with a description. Generated from the Canton sources; do not edit by hand.",
        "",
        "<CardGroup cols={2}>",
    ]
    for prefix, entries in buckets.items():
        if not entries or prefix not in titles:
            continue
        title, blurb = titles[prefix]
        lines += [
            f'  <Card title="{title}" href="{PAGE_URL_PREFIX}/{slug(title)}">',
            f"    {blurb} {len(entries)} keys under `{prefix}`.",
            "  </Card>",
        ]
    lines += [
        f'  <Card title="Configuration types" href="{PAGE_URL_PREFIX}/{TYPES_PAGE}">',
        "    Sections that take a `type`, with the keys each type accepts and an example of each.",
        "  </Card>",
        "</CardGroup>",
        "",
        "## How to read these pages",
        "",
    ]
    lines += reading_guide(artifact, None)

    lines += [
        "## Provenance",
        "",
        "| | |",
        "|---|---|",
        f"| Canton version | `{artifact['cantonVersion']}` |",
        f"| Commit | `{artifact['gitSha']}` |",
        f"| Artifact schema | `{artifact['schemaVersion']}` |",
        f"| Load-time defaults from | `{artifact.get('defaultsFrom') or 'source only'}` |",
        "",
    ]

    moves = artifact.get("deprecatedPaths", [])
    if moves:
        lines += [
            "## Renamed and moved keys",
            "",
            "Canton still reads the old path and logs a notice. Paths are relative to the config class that moved them.",
            "",
            "| Old path | Reads as | Since | Declared by |",
            "|---|---|---|---|",
        ]
        for move in moves:
            targets = ", ".join(f"`{t}`" for t in move["to"]) or "_removed_"
            lines.append(f"| `{move['from']}` | {targets} | {move['since']} | `{move['declaredBy']}` |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_pages(artifact: dict) -> "OrderedDict[str, str]":
    variants_by_type = {entry["name"]: [v["tag"] for v in entry["variants"]] for entry in artifact["types"]}
    unions = find_unions(artifact["options"])
    options_by_path: dict[str, list[dict]] = {}
    for option in artifact["options"]:
        options_by_path.setdefault(option["path"], []).append(option)
    buckets = group_options(artifact["options"])

    pages: "OrderedDict[str, str]" = OrderedDict()
    pages["overview.mdx"] = render_overview(artifact, buckets)
    for prefix, title, blurb in SECTIONS:
        entries = buckets.get(prefix) or []
        if entries:
            pages[f"{slug(title)}.mdx"] = render_node_page(prefix, title, blurb, entries, artifact, variants_by_type, unions, options_by_path)
    pages[f"{TYPES_PAGE}.mdx"] = render_types_page(artifact, variants_by_type, unions, options_by_path)
    return pages


# -- navigation --------------------------------------------------------------------------------


def nav_group(page_refs: list[str]) -> dict:
    return {"group": NAV_GROUP_LABEL, "pages": page_refs}


def update_nav(docs_json_path: Path, page_refs: list[str]) -> None:
    """Insert (or replace) the group inside Global Synchronizer > Reference, right after the
    hand-written configuration page it complements."""
    payload = json.loads(docs_json_path.read_text(encoding="utf-8"))
    products = payload["navigation"]["products"]
    product = next(item for item in products if item.get("product") == PRODUCT_LABEL)
    # Products carry their groups under `groups`; older shapes used `pages`.
    parent = _find_group(product.get("groups") or product.get("pages") or [], PARENT_GROUP_LABEL)
    if parent is None:
        raise ValueError(f"docs.json has no '{PARENT_GROUP_LABEL}' group under '{PRODUCT_LABEL}'")
    pages = parent["pages"]
    group = nav_group(page_refs)
    for index, item in enumerate(pages):
        if isinstance(item, dict) and item.get("group") == NAV_GROUP_LABEL:
            pages[index] = group
            break
    else:
        anchor = pages.index(NAV_ANCHOR_PAGE) + 1 if NAV_ANCHOR_PAGE in pages else len(pages)
        pages.insert(anchor, group)
    docs_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _find_group(items: list, label: str) -> dict | None:
    for item in items:
        if isinstance(item, dict):
            if item.get("group") == label:
                return item
            nested = item.get("pages")
            if isinstance(nested, list):
                found = _find_group(nested, label)
                if found is not None:
                    return found
    return None


# -- main --------------------------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    if not args.skip_direnv:
        ensure_repo_direnv(repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:])

    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    major = str(artifact.get("schemaVersion", "")).split(".")[0]
    if major != SUPPORTED_SCHEMA_MAJOR:
        raise SystemExit(f"unsupported schemaVersion {artifact.get('schemaVersion')!r}; this generator handles {SUPPORTED_SCHEMA_MAJOR}.x")

    pages = render_pages(artifact)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for stale in args.output_dir.glob("*.mdx"):
        if stale.name not in pages:
            stale.unlink()
    for name, text in pages.items():
        (args.output_dir / name).write_text(text, encoding="utf-8")
        print(f"wrote {args.output_dir / name} ({text.count(chr(10)):,} lines)")

    if not args.skip_nav:
        refs = [f"{PAGE_URL_PREFIX.lstrip('/')}/{name[:-4]}" for name in pages]
        update_nav(args.docs_json, refs)
        print(f"updated {args.docs_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

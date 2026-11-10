from __future__ import annotations

import argparse
import json
import re
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_MAIN = REPO_ROOT / "docs-main"
NETWORK_DATA_PATH = DOCS_MAIN / "snippets" / "generated" / "version-dashboard-data.mdx"
# Page templates live under docs-main/src/ and render to the same relative path
# under docs-main/. Templates are hidden pages so the Mintlify editor can open them.
SOURCE_DIR_NAME = "src"
NETWORK_ORDER = ["devnet", "testnet", "mainnet"]

IMPORT_RE = re.compile(
    r"^import\s+(?P<name>[A-Za-z_$][\w$]*)\s+from\s+[\"'](?P<path>[^\"']+\.mdx)[\"'];\s*$",
    re.MULTILINE,
)
NETWORK_DATA_IMPORT_RE = re.compile(
    r"^import\s+\{\s*networkData\s*\}\s+from\s+[\"']/snippets/generated/version-dashboard-data\.mdx[\"'];\s*\n?",
    re.MULTILINE,
)
# A network-specific block in a template is a single "All networks" tab. It uses a
# built-in component because the Mintlify editor cannot render components exported
# from snippet files. The generator expands it into one tab per network.
TEMPLATE_TAB_TITLE = "All networks"
NETWORKVARS_BLOCK_RE = re.compile(
    r"<Tabs>\s*<Tab\s+title=\"" + re.escape(TEMPLATE_TAB_TITLE) + r"\"\s*>(?P<body>.*?)</Tab>\s*</Tabs>",
    re.DOTALL,
)
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?\n)---\n", re.DOTALL)
GENERATED_NOTICE_PREFIX = "{/* Generated from "
TOKEN_RE = re.compile(r"\|([A-Za-z0-9_]+)\|")


@dataclass(frozen=True)
class ImportRef:
    name: str
    import_path: str
    file_path: Path
    line: str


def load_network_data(path: Path = NETWORK_DATA_PATH) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    node_script = """
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
// Strip only top-level export declarations (e.g. `export const networkData`),
// not the word "export" inside string substitution values.
const body = source.replace(/^export\\s+/gm, '');
const networkData = Function(`${body}; return networkData;`)();
process.stdout.write(JSON.stringify(networkData));
"""
    result = subprocess.run(
        ["node", "-e", node_script, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def resolve_mdx_import(import_path: str, docs_main: Path = DOCS_MAIN) -> Path:
    if import_path.startswith("/"):
        return docs_main / import_path.removeprefix("/")
    return docs_main / import_path


def find_imports(text: str, docs_main: Path = DOCS_MAIN) -> dict[str, ImportRef]:
    imports: dict[str, ImportRef] = {}
    for match in IMPORT_RE.finditer(text):
        import_path = match.group("path")
        imports[match.group("name")] = ImportRef(
            name=match.group("name"),
            import_path=import_path,
            file_path=resolve_mdx_import(import_path, docs_main),
            line=match.group(0),
        )
    return imports


def split_source_imports(text: str, docs_main: Path = DOCS_MAIN) -> tuple[dict[str, ImportRef], str]:
    imports = find_imports(text, docs_main)
    body = IMPORT_RE.sub("", text).strip()
    return imports, body


def imported_components_used(body: str, imports: dict[str, ImportRef]) -> list[ImportRef]:
    used: list[ImportRef] = []
    for name, ref in imports.items():
        if re.search(rf"<{re.escape(name)}(?:\s*/|\s|>)", body):
            used.append(ref)
    return used


def source_ref_for_path(source_path: Path, docs_main: Path = DOCS_MAIN) -> str:
    return "/" + source_path.relative_to(docs_main).as_posix()


def network_label(network_key: str, network: dict[str, Any]) -> str:
    name = network.get("name", network_key)
    version = network.get("versions", {}).get("splice")
    return f"{name} ({version})" if version else str(name)


def link_label(network_key: str, network: dict[str, Any], replacement: dict[str, Any]) -> str:
    label = replacement.get("label") or replacement.get("href") or ""
    version = network.get("versions", {}).get("splice")
    name = network.get("name", network_key)
    network_suffix = f"{name} {version}" if version else str(name)
    return f"{label} ({network_suffix})" if network_suffix else str(label)


def replacement_text(token: str, network_key: str, network: dict[str, Any]) -> str | None:
    replacement = network.get("substitutions", {}).get(token)
    if replacement is None:
        return None
    if isinstance(replacement, dict) and replacement.get("href"):
        href = str(replacement["href"])
        return f'<a href="{href}">{link_label(network_key, network, replacement)}</a>'
    return str(replacement)


def replace_tokens(text: str, network_key: str, network: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        replacement = replacement_text(token, network_key, network)
        return match.group(0) if replacement is None else replacement

    return TOKEN_RE.sub(replace, text)


def expand_network_only_blocks(text: str, network_key: str) -> str:
    def replace_div(match: re.Match[str]) -> str:
        networks = [item.strip() for item in match.group("networks").split(",") if item.strip()]
        return match.group("body").strip() if network_key in networks else ""

    return re.sub(
        r"<div\s+data-network-only=\"(?P<networks>[^\"]+)\">\s*(?P<body>.*?)\s*</div>",
        replace_div,
        text,
        flags=re.DOTALL,
    )


def prefix_lines(text: str, prefix: str) -> str:
    if not prefix:
        return text
    blank_prefix = ">" if ">" in prefix else ""
    return "\n".join(f"{prefix}{line}" if line else blank_prefix for line in text.splitlines())


def inline_imported_components(
    text: str,
    imports: dict[str, ImportRef],
    docs_main: Path = DOCS_MAIN,
    stack: tuple[Path, ...] = (),
) -> str:
    rendered = text
    for name, ref in imports.items():
        if not ref.file_path.exists():
            raise FileNotFoundError(f"Missing imported snippet for {name}: {ref.file_path}")
        if ref.file_path in stack:
            cycle = " -> ".join(path.as_posix() for path in (*stack, ref.file_path))
            raise ValueError(f"Recursive network variable snippet import: {cycle}")
        imported_text = ref.file_path.read_text(encoding="utf-8").strip()
        nested_imports, imported_body = split_source_imports(imported_text, docs_main)
        imported_body = inline_imported_components(
            imported_body,
            nested_imports,
            docs_main,
            (*stack, ref.file_path),
        )
        rendered = re.sub(
            rf"(?m)^(?P<prefix>[ \t>]*)<{re.escape(name)}\s*/>\s*$",
            lambda match: prefix_lines(imported_body, match.group("prefix")),
            rendered,
        )
        rendered = re.sub(
            rf"(?m)^(?P<prefix>[ \t>]*)<{re.escape(name)}>\s*</{re.escape(name)}>\s*$",
            lambda match: prefix_lines(imported_body, match.group("prefix")),
            rendered,
        )
        rendered = re.sub(rf"<{re.escape(name)}\s*/>", imported_body, rendered)
        rendered = re.sub(rf"<{re.escape(name)}>\s*</{re.escape(name)}>", imported_body, rendered)
    return rendered


def render_network_body(
    source_body: str,
    imports: dict[str, ImportRef],
    network_key: str,
    network: dict[str, Any],
    docs_main: Path = DOCS_MAIN,
) -> str:
    body = inline_imported_components(source_body, imports, docs_main)
    body = expand_network_only_blocks(body, network_key)
    body = replace_tokens(body, network_key, network)
    return body.strip()


def render_network_tabs(
    block_body: str,
    imports: dict[str, ImportRef],
    network_data: dict[str, Any],
    docs_main: Path = DOCS_MAIN,
) -> str:
    tabs: list[str] = ["<Tabs>"]
    for network_key in NETWORK_ORDER:
        network = network_data.get(network_key)
        if not network or not network.get("substitutions"):
            continue
        body = render_network_body(block_body, imports, network_key, network, docs_main)
        tabs.extend(
            [
                "",
                f'<Tab title="{network_label(network_key, network)}">',
                "",
                body,
                "",
                "</Tab>",
            ]
        )
    tabs.extend(["", "</Tabs>"])
    return re.sub(r"\n{3,}", "\n\n", "\n".join(tabs))


def remove_unused_imports(text: str) -> str:
    network_data_match = NETWORK_DATA_IMPORT_RE.search(text)
    if network_data_match:
        without_network_data_import = text[: network_data_match.start()] + text[network_data_match.end() :]
        if "networkData" not in without_network_data_import:
            text = without_network_data_import

    while True:
        removed = False
        for match in IMPORT_RE.finditer(text):
            name = match.group("name")
            without_line = text[: match.start()] + text[match.end() :]
            if not re.search(rf"\b{re.escape(name)}\b", without_line):
                text = without_line
                removed = True
                break
        if not removed:
            break
    return text


def collapse_import_header_blank_lines(text: str) -> str:
    """Collapse blank-line runs left behind in the leading import block only."""
    end = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and not stripped.startswith("import "):
            break
        end += len(line)
    return re.sub(r"\n{3,}", "\n\n", text[:end]) + text[end:]


def published_frontmatter(text: str, source_ref: str) -> tuple[str, str]:
    """Return the published frontmatter (without `hidden: true`) and the remaining body."""
    frontmatter = FRONTMATTER_RE.match(text)
    if not frontmatter:
        raise ValueError(f"{source_ref} must start with frontmatter that sets `hidden: true`.")
    lines = frontmatter.group("body").splitlines(keepends=True)
    kept = [line for line in lines if line.strip() != "hidden: true"]
    if len(kept) == len(lines):
        raise ValueError(
            f"{source_ref} must set `hidden: true` so the template is not published as a visible page."
        )
    return f"---\n{''.join(kept)}---\n", text[frontmatter.end() :]


def generated_notice(source_ref: str) -> str:
    return (
        f"{GENERATED_NOTICE_PREFIX}{source_ref} by `npm run generate:network-variable-tabs`. "
        "Edit that file, not this one. */}"
    )


def render_page(source_path: Path, network_data: dict[str, Any], docs_main: Path = DOCS_MAIN) -> str:
    source_ref = source_ref_for_path(source_path, docs_main)
    text = source_path.read_bytes().decode("utf-8")
    frontmatter, body = published_frontmatter(text, source_ref)
    page_imports = find_imports(body, docs_main)

    def replace_block(match: re.Match[str]) -> str:
        # The editor may indent tab children; dedent so code blocks keep their meaning.
        block_body = textwrap.dedent(match.group("body").strip("\n")).strip()
        if re.search(r"</?Tabs?[\s>]", block_body):
            raise ValueError(
                f'{source_ref}: a <Tab title="{TEMPLATE_TAB_TITLE}"> must be the only tab in its <Tabs> block '
                "and cannot contain tabs. Remove the other tabs."
            )
        used_imports = {ref.name: ref for ref in imported_components_used(block_body, page_imports)}
        return render_network_tabs(block_body, used_imports, network_data, docs_main)

    body = NETWORKVARS_BLOCK_RE.sub(replace_block, body)
    if re.search(rf'<Tab\s+title="{re.escape(TEMPLATE_TAB_TITLE)}"', body):
        raise ValueError(
            f'{source_ref}: a <Tab title="{TEMPLATE_TAB_TITLE}"> must be the only tab in its <Tabs> block. '
            "Remove the other tabs; network-specific content belongs inside it."
        )
    body = collapse_import_header_blank_lines(remove_unused_imports(body)).lstrip("\n")
    return f"{frontmatter}{generated_notice(source_ref)}\n\n{body}"


def output_path_for_source(source_path: Path, docs_main: Path = DOCS_MAIN) -> Path:
    return docs_main / source_path.relative_to(docs_main / SOURCE_DIR_NAME)


def update_page(
    source_path: Path,
    network_data: dict[str, Any],
    docs_main: Path = DOCS_MAIN,
    *,
    check: bool = False,
) -> bool:
    output_path = output_path_for_source(source_path, docs_main)
    rendered = render_page(source_path, network_data, docs_main)
    current = output_path.read_bytes().decode("utf-8") if output_path.exists() else None
    if rendered != current and not check:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(rendered.encode("utf-8"))
    return rendered != current


def iter_sources(docs_main: Path = DOCS_MAIN) -> list[Path]:
    source_root = docs_main / SOURCE_DIR_NAME
    if not source_root.is_dir():
        return []
    return sorted(source_root.rglob("*.mdx"))


def orphaned_outputs(docs_main: Path = DOCS_MAIN) -> list[Path]:
    """Generated pages whose template no longer exists."""
    source_root = docs_main / SOURCE_DIR_NAME
    orphans: list[Path] = []
    for path in sorted(docs_main.rglob("*.mdx")):
        if source_root in path.parents or "/snippets/" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        if GENERATED_NOTICE_PREFIX + "/" + SOURCE_DIR_NAME + "/" not in text:
            continue
        if not (source_root / path.relative_to(docs_main)).exists():
            orphans.append(path)
    return orphans


def relative_to_repo(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render docs-main/src/ page templates into published pages with static network tabs."
    )
    parser.add_argument("--check", action="store_true", help="Check generated pages without changing any files.")
    parser.add_argument(
        "--report",
        type=Path,
        help="Write stale pages, orphaned pages, and template errors to this JSON file.",
    )
    args = parser.parse_args()

    network_data = load_network_data()
    changed_pages: list[Path] = []
    stale: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for source_path in iter_sources():
        output_path = output_path_for_source(source_path)
        try:
            changed = update_page(source_path, network_data, check=args.check)
        except ValueError as error:
            errors.append({"template": relative_to_repo(source_path), "message": str(error)})
            continue
        if changed:
            changed_pages.append(output_path)
            stale.append({"page": relative_to_repo(output_path), "template": relative_to_repo(source_path)})
    orphans = [relative_to_repo(path) for path in orphaned_outputs()]

    if args.report:
        report = {"stale": stale if args.check else [], "orphans": orphans, "errors": errors}
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    problems: list[str] = []
    if errors:
        problems.append("Page templates could not be rendered.\n" + "\n".join(error["message"] for error in errors))
    if orphans:
        problems.append(
            "Generated pages have no template under docs-main/src/. "
            "Restore the template or delete the page.\n" + "\n".join(orphans)
        )
    if args.check and changed_pages:
        problems.append(
            "Network variable tabs are stale. Edit the template under docs-main/src/, "
            "run `npm run generate:network-variable-tabs`, and commit the rendered MDX changes.\n"
            + "\n".join(relative_to_repo(path) for path in changed_pages)
        )
    if problems:
        raise SystemExit("\n\n".join(problems))

    if changed_pages:
        print(f"Updated {len(changed_pages)} page(s).")
    else:
        print("Network variable tabs are rendered and up to date.")


if __name__ == "__main__":
    main()

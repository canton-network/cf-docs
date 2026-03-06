#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Tuple


ADMONITION_MAP = {
    "warning": "Warning",
    "note": "Note",
    "tip": "Tip",
    "important": "Important",
    "caution": "Caution",
}

TITLE_OVERRIDES = {
    "how-tos": "How Tos",
    "daml-api-reference": "DAML API Reference",
}


def titleize_folder(name: str) -> str:
    if name in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[name]
    parts = re.split(r"[-_]+", name)
    return " ".join(p.capitalize() for p in parts if p)


def strip_local_link_ext(text: str) -> str:
    def repl(match: re.Match) -> str:
        url = match.group(1)
        if url.startswith(("http://", "https://", "mailto:", "#")):
            return match.group(0)
        if url.startswith("docs-main/"):
            url = f"/{url}"
        if url.endswith(".md") or url.endswith(".mdx"):
            url = url.rsplit(".", 1)[0]
        elif ".md#" in url:
            url = url.replace(".md#", "#")
        elif ".mdx#" in url:
            url = url.replace(".mdx#", "#")
        return f"]({url})"

    return re.sub(r"\]\(([^)]+)\)", repl, text)


def convert_myst_blocks(lines: List[str]) -> List[str]:
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```{toctree}"):
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                i += 1
            if i < len(lines):
                i += 1
            continue

        image_match = re.match(r"^```{image}\s+(.+)$", stripped)
        if image_match:
            image_path = image_match.group(1).strip()
            alt_text = ""
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                alt_match = re.match(r"^:alt:\s*(.+)$", lines[i].strip())
                if alt_match:
                    alt_text = alt_match.group(1).strip()
                i += 1
            if i < len(lines):
                i += 1
            out.append(f"![{alt_text}]({image_path})\n")
            continue

        admonition_match = re.match(r"^```{(\w+)}$", stripped)
        if admonition_match:
            kind = admonition_match.group(1).lower()
            component = ADMONITION_MAP.get(kind)
            if component:
                out.append(f"<{component}>\n")
                i += 1
                while i < len(lines) and lines[i].strip() != "```":
                    out.append(lines[i])
                    i += 1
                if i < len(lines):
                    i += 1
                out.append(f"</{component}>\n")
                continue

        anchor_match = re.match(r"^\(([^)]+)\)=$", stripped)
        if anchor_match:
            anchor_id = anchor_match.group(1)
            out.append(f'<a id="{anchor_id}"></a>\n')
            i += 1
            continue

        out.append(line)
        i += 1
    return out


def convert_markdown(content: str, label_map: dict) -> str:
    lines = []
    for line in content.splitlines(keepends=True):
        if "<!--" in line and "-->" in line:
            lines.append(line.replace("<!--", "{/*").replace("-->", "*/}"))
        else:
            lines.append(line)
    converted = convert_myst_blocks(lines)
    text = "".join(converted)
    text = convert_myst_doc_roles(text)
    text = convert_myst_ref_roles(text, label_map)
    text = normalize_inline_html(text)
    return strip_local_link_ext(text)


def convert_rst_to_markdown(content: str, source_path: Path) -> str:
    result = subprocess.run(
        ["pandoc", "-f", "rst", "-t", "gfm", "--wrap=none"],
        input=content,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed for {source_path}: {result.stderr}")
    return result.stdout


def normalize_inline_html(text: str) -> str:
    text = text.replace("<br>", "<br />")

    def repl(match: re.Match) -> str:
        name = match.group(1)
        return f"&lt;{name}&gt;"

    return re.sub(r"<([A-Za-z0-9_-]*-[A-Za-z0-9_-]+)>", repl, text)


def convert_myst_doc_roles(text: str) -> str:
    def repl(match: re.Match) -> str:
        inner = match.group(1).strip()
        if "<" in inner and inner.endswith(">"):
            label, target = inner.rsplit("<", 1)
            label = label.strip()
            target = target[:-1].strip()
            return f"[{label}]({target})"
        return f"[{inner}]({inner})"

    return re.sub(r"\{doc\}`([^`]+)`", repl, text)


def convert_myst_ref_roles(text: str, label_map: dict) -> str:
    def repl(match: re.Match) -> str:
        inner = match.group(1).strip()
        label = inner
        title = inner
        if "<" in inner and inner.endswith(">"):
            title, label = inner.rsplit("<", 1)
            title = title.strip()
            label = label[:-1].strip()
        href = label_map.get(label)
        if href:
            return f"[{title}]({href})"
        return f"[{title}](#{label})"

    return re.sub(r"\{ref\}`([^`]+)`", repl, text)


def iter_source_files(source_root: Path, scope: List[str]) -> Iterable[Path]:
    if scope:
        paths = [source_root / "index.md", source_root / "index.rst"]
        for item in scope:
            paths.append(source_root / item)
        for path in paths:
            if path.is_dir():
                yield from path.rglob("*")
            elif path.is_file():
                yield path
        return
    yield from source_root.rglob("*")


def build_label_index(source_root: Path, dest_root: Path, repo_root: Path, scope: List[str]) -> dict:
    label_map = {}
    for src_path in iter_source_files(source_root, scope):
        if src_path.is_dir() or src_path.suffix.lower() not in (".md", ".rst"):
            continue
        if src_path.name in ("index.md", "index.rst"):
            continue
        rel = src_path.relative_to(source_root)
        dest_rel = rel.with_suffix(".mdx")
        page_path = (dest_root / dest_rel).relative_to(repo_root).with_suffix("")
        content = src_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            match = re.match(r"^\(([^)]+)\)=$", line.strip())
            if match:
                label = match.group(1)
                label_map[label] = f"/{page_path}#{label}"
            rst_match = re.match(r"^\.\.\s+_([^:]+):$", line.strip())
            if rst_match:
                label = rst_match.group(1).strip()
                label_map[label] = f"/{page_path}#{label}"
    return label_map


def copy_and_convert(source_root: Path, dest_root: Path, repo_root: Path, scope: List[str]) -> None:
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    label_map = build_label_index(source_root, dest_root, repo_root, scope)

    for src_path in iter_source_files(source_root, scope):
        if src_path.is_dir():
            continue
        rel = src_path.relative_to(source_root)
        if src_path.name in ("index.md", "index.rst", "_toc.yml"):
            continue
        if src_path.suffix.lower() == ".md":
            dest_rel = rel.with_suffix(".mdx")
            dest_path = dest_root / dest_rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            content = src_path.read_text(encoding="utf-8")
            converted = convert_markdown(content, label_map)
            dest_path.write_text(converted, encoding="utf-8")
        elif src_path.suffix.lower() == ".rst":
            dest_rel = rel.with_suffix(".mdx")
            dest_path = dest_root / dest_rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            content = src_path.read_text(encoding="utf-8")
            markdown = convert_rst_to_markdown(content, src_path)
            converted = convert_markdown(markdown, label_map)
            dest_path.write_text(converted, encoding="utf-8")
        else:
            dest_path = dest_root / rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)


def parse_toctree_entries(index_path: Path) -> List[str]:
    if not index_path.exists():
        return []
    lines = index_path.read_text(encoding="utf-8").splitlines()
    entries: List[str] = []
    in_toctree = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```{toctree}"):
            in_toctree = True
            continue
        if in_toctree and stripped == "```":
            in_toctree = False
            continue
        if not in_toctree:
            continue
        if not stripped or stripped.startswith(":"):
            continue
        title_match = re.match(r".*<([^>]+)>", stripped)
        entry = title_match.group(1).strip() if title_match else stripped
        entry = entry.replace("\\", "/")
        if entry.endswith(".md"):
            entry = entry[:-3]
        entries.append(entry)
    return entries


def parse_toctree_entries_rst(index_path: Path) -> List[str]:
    if not index_path.exists():
        return []
    lines = index_path.read_text(encoding="utf-8").splitlines()
    entries: List[str] = []
    in_toctree = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(".. toctree::"):
            in_toctree = True
            continue
        if not in_toctree:
            continue
        if not line.startswith((" ", "\t")) and stripped:
            break
        if not stripped or stripped.startswith(":"):
            continue
        title_match = re.match(r".*<([^>]+)>", stripped)
        entry = title_match.group(1).strip() if title_match else stripped
        entry = entry.replace("\\", "/")
        if entry.endswith(".rst"):
            entry = entry[:-4]
        entries.append(entry)
    return entries


def collect_pages(section_root: Path, repo_root: Path, source_root: Path, dest_root: Path) -> List[str]:
    pages: List[str] = []

    def add_page(path: Path) -> None:
        rel = path.relative_to(repo_root).with_suffix("")
        pages.append(str(rel))

    def walk_dir(dir_path: Path) -> None:
        rel_dir = dir_path.relative_to(dest_root)
        source_dir = source_root / rel_dir
        toctree_entries = parse_toctree_entries(source_dir / "index.md")
        if not toctree_entries:
            toctree_entries = parse_toctree_entries_rst(source_dir / "index.rst")

        referenced = set()
        for entry in toctree_entries:
            entry_path = dir_path / entry
            file_path = entry_path.with_suffix(".mdx")
            dir_index = entry_path / "index.mdx"
            if file_path.exists():
                add_page(file_path)
                referenced.add(file_path)
            elif dir_index.exists():
                add_page(dir_index)
                referenced.add(dir_index)

        files = sorted(
            [
                p
                for p in dir_path.iterdir()
                if p.is_file() and p.suffix == ".mdx" and p.name != "index.mdx" and p not in referenced
            ]
        )
        for file_path in files:
            add_page(file_path)

        dirs = sorted([p for p in dir_path.iterdir() if p.is_dir()])
        for subdir in dirs:
            walk_dir(subdir)

    walk_dir(section_root)
    return pages


def build_utilities_groups(dest_root: Path, repo_root: Path, source_root: Path) -> List[dict]:
    groups: List[dict] = []

    for entry in sorted(dest_root.iterdir()):
        if not entry.is_dir():
            continue
        subdirs = sorted([p for p in entry.iterdir() if p.is_dir()])
        subdir_with_content = [
            p for p in subdirs if any(child.suffix == ".mdx" for child in p.rglob("*.mdx"))
        ]
        if subdir_with_content:
            for subdir in subdir_with_content:
                pages = collect_pages(subdir, repo_root, source_root, dest_root)
                if pages:
                    groups.append({"group": titleize_folder(subdir.name), "pages": pages})
            continue

        pages = collect_pages(entry, repo_root, source_root, dest_root)
        if pages:
            groups.append({"group": titleize_folder(entry.name), "pages": pages})
    return groups


def update_docs_json(docs_json_path: Path, groups: List[dict]) -> None:
    data = json.loads(docs_json_path.read_text(encoding="utf-8"))
    navigation = data.get("navigation", {})
    dropdowns = navigation.get("dropdowns", [])

    dropdowns = [d for d in dropdowns if d.get("dropdown") != "Utilities"]
    dropdowns.append(
        {
            "dropdown": "Utilities",
            "icon": "grid",
            "groups": groups,
        }
    )
    navigation["dropdowns"] = dropdowns
    data["navigation"] = navigation
    docs_json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_source = repo_root.parent / "canton-network-utilities" / "docs" / "generated"
    default_dest = repo_root / "docs-main" / "utilities"
    default_docs_json = repo_root / "docs.json"

    parser = argparse.ArgumentParser(description="Migrate utilities docs from generated to Mintlify.")
    parser.add_argument(
        "--source",
        type=Path,
        default=default_source,
        help="Source docs root (default: canton-network-utilities/docs/generated).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=default_dest,
        help="Destination root in docs repo (default: docs-main/utilities).",
    )
    parser.add_argument("--docs-json", type=Path, default=default_docs_json)
    parser.add_argument(
        "--scope",
        type=str,
        default="",
        help="Comma-separated list of top-level folders to migrate (e.g. setup,tutorials).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_root = args.source.resolve()
    dest_root = args.dest.resolve()
    docs_json_path = args.docs_json.resolve()

    if not source_root.exists():
        raise SystemExit(f"Source not found: {source_root}")
    if not docs_json_path.exists():
        raise SystemExit(f"docs.json not found: {docs_json_path}")

    scope_items = [s.strip() for s in args.scope.split(",") if s.strip()] if args.scope else []
    copy_and_convert(source_root, dest_root, docs_json_path.parent, scope_items)
    groups = build_utilities_groups(dest_root, docs_json_path.parent, source_root)
    update_docs_json(docs_json_path, groups)


if __name__ == "__main__":
    main()

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shutil

from x2mdx.mintlify import MintlifyGroup, write_docs_json
from x2mdx.output import Page, RawMarkdown
from x2mdx.render import write_page

from tests.harness.characterization_cases import CHARACTERIZATION_CASES, CharacterizationCase
from tests.harness.characterization_common import REPO_ROOT, reset_dir


DEFAULT_PREVIEW_ROOT = REPO_ROOT / ".cache" / "characterization_preview" / "site"

TOKEN_LABELS = {
    "api": "API",
    "asyncapi": "AsyncAPI",
    "daml": "DAML",
    "docs": "Docs",
    "json": "JSON",
    "jvm": "JVM",
    "mdx": "MDX",
    "openrpc": "OpenRPC",
    "protobuf": "Protobuf",
    "rpc": "RPC",
    "typedoc": "TypeDoc",
}


@dataclass(frozen=True)
class StagedPreviewCase:
    case: CharacterizationCase
    entry_ref: str
    nav_page_refs: tuple[str, ...]
    page_count: int
    docs_json_covered: bool


def _rewrite_text(text: str, replacements: tuple[tuple[str, str], ...]) -> str:
    output = text
    for old, new in replacements:
        output = output.replace(old, new)
    return output


def _copy_mdx(source: Path, target: Path, *, replacements: tuple[tuple[str, str], ...]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    target.write_text(_rewrite_text(text, replacements), encoding="utf-8")
    return target


def _page_ref(root: Path, path: Path) -> str:
    return path.relative_to(root).with_suffix("").as_posix()


def _segment_label(segment: str) -> str:
    return " ".join(TOKEN_LABELS.get(token, token.capitalize()) for token in segment.split("-"))


def _grouped_page_refs(base_ref: PurePosixPath, paths: list[PurePosixPath]) -> list[str | MintlifyGroup]:
    files: list[str] = []
    directories: dict[str, list[PurePosixPath]] = {}
    for path in paths:
        if len(path.parts) == 1:
            files.append((base_ref / path).as_posix())
            continue
        directories.setdefault(path.parts[0], []).append(PurePosixPath(*path.parts[1:]))

    items: list[str | MintlifyGroup] = sorted(files)
    for segment in sorted(directories):
        child_base = base_ref / segment
        items.append(
            MintlifyGroup(
                group=_segment_label(segment),
                pages=_grouped_page_refs(child_base, directories[segment]),
                expanded=False,
            )
        )
    return items


def _copy_case_tree(case: CharacterizationCase, output_root: Path) -> tuple[list[Path], str, set[str]]:
    preview = case.preview
    target_root = output_root / preview.target_root
    target_root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    hidden_page_refs: set[str] = set()

    if case.expected_file is not None:
        target_file = target_root / preview.entry_file
        written.append(_copy_mdx(case.expected_file, target_file, replacements=preview.link_rewrites))
        return written, _page_ref(output_root, target_file), hidden_page_refs

    if case.expected_tree is None:
        raise ValueError(f"Case has no expected output to preview: {case.name}")

    for source in sorted(case.expected_tree.rglob("*.mdx")):
        relative = source.relative_to(case.expected_tree)
        target = target_root / relative
        written.append(_copy_mdx(source, target, replacements=preview.link_rewrites))

    entry_source_file = preview.entry_source_file or preview.entry_file
    if preview.entry_source_file is not None:
        aliased_entry = target_root / preview.entry_file
        source_entry = target_root / preview.entry_source_file
        written.append(_copy_mdx(source_entry, aliased_entry, replacements=()))
        hidden_page_refs.add(_page_ref(output_root, source_entry))

    entry_ref = (PurePosixPath(preview.target_root) / entry_source_file).with_suffix("").as_posix()
    if preview.entry_source_file is not None:
        entry_ref = (PurePosixPath(preview.target_root) / preview.entry_file).with_suffix("").as_posix()
    return written, entry_ref, hidden_page_refs


def _stage_preview_case(case: CharacterizationCase, output_root: Path) -> StagedPreviewCase:
    written, entry_ref, hidden_page_refs = _copy_case_tree(case, output_root)
    page_refs = sorted(
        page_ref
        for page_ref in (_page_ref(output_root, path) for path in written)
        if page_ref not in hidden_page_refs
    )
    return StagedPreviewCase(
        case=case,
        entry_ref=entry_ref,
        nav_page_refs=tuple(page_refs),
        page_count=len(page_refs),
        docs_json_covered=case.docs_json_after is not None,
    )


def _case_group(staged: StagedPreviewCase) -> MintlifyGroup:
    entry_path = PurePosixPath(staged.entry_ref)
    remaining_paths = [
        PurePosixPath(page_ref).relative_to(entry_path.parent)
        for page_ref in staged.nav_page_refs
        if page_ref != staged.entry_ref
    ]
    pages: list[str | MintlifyGroup] = [staged.entry_ref]
    pages.extend(_grouped_page_refs(entry_path.parent, remaining_paths))
    return MintlifyGroup(group=staged.case.preview.case_label, pages=pages, expanded=False)


def _build_docs_groups(staged_cases: list[StagedPreviewCase]) -> list[MintlifyGroup]:
    grouped: OrderedDict[str, list[MintlifyGroup]] = OrderedDict()
    for staged in staged_cases:
        grouped.setdefault(staged.case.preview.format_group, []).append(_case_group(staged))

    groups = [MintlifyGroup(group="Overview", pages=["index"], expanded=True)]
    for label, cases in grouped.items():
        groups.append(MintlifyGroup(group=label, pages=cases, expanded=True))
    return groups


def _overview_body(staged_cases: list[StagedPreviewCase]) -> str:
    lines = [
        "This local Mintlify site assembles the checked-in characterization fixtures that freeze current `x2mdx` output shapes.",
        "",
        "It does not rerender from manifests. Every page here is copied from the checked-in golden fixtures under `tests/fixtures/characterization`.",
        "",
        "## Covered Cases",
        "",
        "| Format | Case | Pages | Docs Nav Snapshot | Entry Page |",
        "| --- | --- | --- | --- | --- |",
    ]
    for staged in staged_cases:
        lines.append(
            f"| {staged.case.preview.format_group} | {staged.case.preview.case_label} | {staged.page_count} | {'Yes' if staged.docs_json_covered else 'No'} | [Open](/{staged.entry_ref}) |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- The docs-nav cases still freeze their `docs.json` before/after snapshots in the characterization tests; this preview only adds a root Mintlify `docs.json` so the frozen MDX can be browsed together.",
            "- The alternate OpenRPC layout is staged under `/reference/wallet-gateway-json-rpc-alt` and gets preview-only link rewrites so its absolute links do not collide with the standard Wallet Gateway preview tree.",
            "- The Daml Standard Library tree stays under `/appdev/reference/daml-standard-library` so its absolute `link-prefix` links remain valid inside the preview.",
        ]
    )
    return "\n".join(lines)


def build_characterization_preview_site(output_root: Path = DEFAULT_PREVIEW_ROOT) -> list[Path]:
    reset_dir(output_root)
    staged_cases = [_stage_preview_case(case, output_root) for case in CHARACTERIZATION_CASES]

    written = [output_root / "index.mdx"]
    write_page(
        Page(
            path="index.mdx",
            title="x2mdx Characterization Preview",
            description="Mintlify preview site for the checked-in x2mdx characterization fixtures.",
            blocks=[RawMarkdown(_overview_body(staged_cases))],
        ),
        output_root / "index.mdx",
    )
    write_docs_json(
        output_root,
        site_name="x2mdx Characterization Preview",
        groups=_build_docs_groups(staged_cases),
    )
    written.append(output_root / "docs.json")
    written.extend(output_root / f"{page_ref}.mdx" for staged in staged_cases for page_ref in staged.nav_page_refs)
    return written


def clean_characterization_preview_site(output_root: Path = DEFAULT_PREVIEW_ROOT) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)

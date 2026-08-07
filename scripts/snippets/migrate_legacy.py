from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compiler import render_snippet
from .parser import load_registry, parse_page
from .source import GitHubClient, SourceResolutionError, SourceResolver


CF_DOCS_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = CF_DOCS_ROOT / "config" / "snippet-config"
DOCS_ROOT = CF_DOCS_ROOT / "docs-main"
DEFAULT_PLAN = CONFIG_ROOT / "legacy-inline-migration.json"
LIST_INDEX = CONFIG_ROOT / "remote-snippet-lists.json"
IMPORT_RE = re.compile(
    r"^import\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s+from\s+"
    r'(?P<quote>["\'])(?P<source>/snippets/external/(?P<repo>[^/]+)/main/'
    r"(?P<snippet>.+)\.mdx)(?P=quote);?\s*$"
)


class LegacyMigrationError(Exception):
    pass


@dataclass(frozen=True)
class SourcePin:
    alias: str
    repository: str
    commit: str


@dataclass(frozen=True)
class LegacySnippet:
    manifest_path: Path
    global_substitutions: dict[str, str]
    entry: dict[str, Any]

    @property
    def alias(self) -> str:
        value = self.entry.get("sourceRepo")
        if not isinstance(value, str):
            raise LegacyMigrationError(f"Invalid sourceRepo in {self.manifest_path}")
        return value

    @property
    def name(self) -> str:
        value = self.entry.get("snippetName")
        if not isinstance(value, str):
            raise LegacyMigrationError(f"Invalid snippetName in {self.manifest_path}")
        return value

    @property
    def source_path(self) -> str:
        value = self.entry.get("sourceFilepath")
        if not isinstance(value, str):
            raise LegacyMigrationError(
                f"Invalid sourceFilepath for {self.name} in {self.manifest_path}"
            )
        return value

    @property
    def location(self) -> dict[str, Any]:
        value = self.entry.get("location")
        if not isinstance(value, dict):
            raise LegacyMigrationError(
                f"Invalid location for {self.name} in {self.manifest_path}"
            )
        return value

    @property
    def options(self) -> dict[str, Any]:
        value = self.entry.get("options", {})
        if not isinstance(value, dict):
            raise LegacyMigrationError(
                f"Invalid options for {self.name} in {self.manifest_path}"
            )
        return value

    @property
    def output_path(self) -> Path:
        return (
            DOCS_ROOT
            / "snippets"
            / "external"
            / self.alias
            / "main"
            / f"{self.name}.mdx"
        )

    @property
    def blocked_reason(self) -> str | None:
        location_type = self.location.get("type")
        if location_type == "jsonIndex" or self.options.get("transform") == "rstjson":
            return "generated Canton JSON source is not committed upstream"
        if location_type not in {"fullFile", "lines", "stringMarker"}:
            return f"unsupported legacy selector {location_type!r}"
        return None

    @property
    def orphan_reason(self) -> str | None:
        if not self.output_path.is_file():
            return "legacy manifest entry has no generated output"
        return None


def load_plan(path: Path) -> dict[str, SourcePin]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_repositories = payload.get("repositories")
    if not isinstance(raw_repositories, dict):
        raise LegacyMigrationError(f"{path} must contain repositories")
    pins: dict[str, SourcePin] = {}
    for alias, raw in raw_repositories.items():
        if not isinstance(alias, str) or not isinstance(raw, dict):
            raise LegacyMigrationError(f"Invalid repository entry in {path}")
        repository = raw.get("repository")
        commit = raw.get("commit")
        if not isinstance(repository, str) or not isinstance(commit, str):
            raise LegacyMigrationError(f"Invalid source pin for {alias} in {path}")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise LegacyMigrationError(f"Invalid commit for {alias} in {path}")
        pins[alias] = SourcePin(alias, repository, commit)
    raw_overrides = payload.get("overrides", {})
    if not isinstance(raw_overrides, dict):
        raise LegacyMigrationError(f"Invalid overrides in {path}")
    for key, raw in raw_overrides.items():
        if not isinstance(key, str) or ":" not in key or not isinstance(raw, dict):
            raise LegacyMigrationError(f"Invalid source override in {path}")
        alias, _ = key.split(":", 1)
        parent = pins.get(alias)
        repository = raw.get("repository", parent.repository if parent else None)
        commit = raw.get("commit")
        if not isinstance(repository, str) or not isinstance(commit, str):
            raise LegacyMigrationError(f"Invalid source override for {key} in {path}")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise LegacyMigrationError(f"Invalid override commit for {key} in {path}")
        pins[key] = SourcePin(alias, repository, commit)
    return pins


def load_legacy_snippets() -> list[LegacySnippet]:
    index = json.loads(LIST_INDEX.read_text(encoding="utf-8"))
    names = index.get("snippetLists")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise LegacyMigrationError(f"Invalid snippet list index {LIST_INDEX}")
    snippets: list[LegacySnippet] = []
    for name in names:
        manifest_path = CONFIG_ROOT / name
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = payload.get("snippets")
        substitutions = payload.get("urlSubstitutions", {})
        if not isinstance(entries, list) or not isinstance(substitutions, dict):
            raise LegacyMigrationError(f"Invalid legacy manifest {manifest_path}")
        if not all(
            isinstance(source, str) and isinstance(target, str)
            for source, target in substitutions.items()
        ):
            raise LegacyMigrationError(
                f"Invalid URL substitutions in legacy manifest {manifest_path}"
            )
        snippets.extend(
            LegacySnippet(manifest_path, substitutions, entry)
            for entry in entries
            if isinstance(entry, dict)
        )
    return snippets


def _quoted(value: str) -> str:
    return json.dumps(value)


def declaration(snippet: LegacySnippet, pin: SourcePin, source_text: str) -> str:
    location = snippet.location
    options = snippet.options
    language = options.get("language")
    if not isinstance(language, str) or not language:
        language = "none"
    attributes = [
        f"source={_quoted(f'https://github.com/{pin.repository}/blob/{pin.commit}/{snippet.source_path}')}"
    ]
    location_type = location.get("type")
    if location_type == "stringMarker":
        attributes.extend(
            (
                f"startAfter={_quoted(str(location.get('start', '')))}",
                f"endBefore={_quoted(str(location.get('end', '')))}",
            )
        )
        normalization = "baseline"
    elif location_type == "lines":
        attributes.append(
            f"lines={_quoted(f'{location.get("start")}..{location.get("end")}')}"
        )
        normalization = "preserve"
    elif location_type == "fullFile":
        normalization = "two-spaces" if snippet.alias == "canton" else "baseline"
    else:
        raise LegacyMigrationError(
            f"Cannot declare blocked snippet {snippet.alias}:{snippet.name}"
        )
    attributes.append(f"normalize={_quoted(normalization)}")
    if snippet.alias == "splice" and "kms-participant-" in snippet.name:
        attributes.append('trim="true"')
    matching_substitutions = [
        (source, target)
        for source, target in snippet.global_substitutions.items()
        if source in source_text
    ]
    if len(matching_substitutions) > 1:
        raise LegacyMigrationError(
            f"More than one URL substitution applies to {snippet.alias}:{snippet.name}"
        )
    if matching_substitutions:
        source, target = matching_substitutions[0]
        attributes.extend(
            (f"replaceFrom={_quoted(source)}", f"replaceWith={_quoted(target)}")
        )
    attributes.append(f"language={_quoted(language)}")
    if len(attributes) <= 3:
        return f"<Snippet {' '.join(attributes)} />"
    return "<Snippet\n  " + "\n  ".join(attributes) + "\n/>"


def _render_without_provenance(
    declaration_text: str,
    *,
    repositories: dict[str, dict[str, Any]],
    resolver: SourceResolver,
) -> str:
    parsed = parse_page(
        declaration_text,
        path=Path("legacy-migration.source.mdx"),
        repositories=repositories,
    )
    directive = parsed.snippets[0]
    source = resolver.resolve(directive.source, production=True)
    rendered = render_snippet(
        directive,
        source,
        page_path=Path("legacy-migration.source.mdx"),
    )
    _, separator, body = rendered.partition("\n")
    if not separator:
        raise AssertionError("Rendered snippet has no provenance line")
    return body


def audit(
    snippets: list[LegacySnippet],
    pins: dict[str, SourcePin],
    *,
    aliases: set[str],
    names: set[str],
    registry: dict[str, dict[str, Any]],
    resolver: SourceResolver,
) -> tuple[dict[tuple[str, str], str], list[str]]:
    declarations: dict[tuple[str, str], str] = {}
    failures: list[str] = []
    source_cache: dict[tuple[str, str, str], bytes] = {}
    for snippet in snippets:
        if aliases and snippet.alias not in aliases:
            continue
        if names and snippet.name not in names:
            continue
        if snippet.blocked_reason:
            continue
        if snippet.orphan_reason:
            continue
        pin = pins.get(f"{snippet.alias}:{snippet.name}") or pins.get(snippet.alias)
        if pin is None:
            failures.append(f"{snippet.alias}:{snippet.name}: no source pin")
            continue
        source_key = (pin.repository, pin.commit, snippet.source_path)
        try:
            if source_key not in source_cache:
                source_cache[source_key] = resolver.github.read_file(*source_key)
        except SourceResolutionError as error:
            failures.append(f"{snippet.alias}:{snippet.name}: {error}")
            continue
        source = source_cache[source_key]
        try:
            source_text = source.decode("utf-8")
        except UnicodeDecodeError:
            failures.append(f"{snippet.alias}:{snippet.name}: source is not UTF-8")
            continue
        declaration_text = declaration(snippet, pin, source_text)
        try:
            rendered = _render_without_provenance(
                declaration_text,
                repositories=registry,
                resolver=resolver,
            )
            existing = snippet.output_path.read_text(encoding="utf-8")
        except (OSError, SourceResolutionError, ValueError) as error:
            failures.append(f"{snippet.alias}:{snippet.name}: {error}")
            continue
        if rendered != existing:
            failures.append(f"{snippet.alias}:{snippet.name}: rendered content differs")
            continue
        declarations[(snippet.alias, snippet.name)] = declaration_text
    return declarations, failures


def _component_pattern(identifier: str) -> re.Pattern[str]:
    return re.compile(rf"<{re.escape(identifier)}\s*/>")


def migrate_pages(
    declarations: dict[tuple[str, str], str],
) -> tuple[set[tuple[str, str]], set[Path]]:
    used: set[tuple[str, str]] = set()
    changed_pages: set[Path] = set()
    for page in sorted(DOCS_ROOT.rglob("*.mdx")):
        if page.name.endswith(".source.mdx") or "snippets" in page.parts:
            continue
        original = page.read_text(encoding="utf-8")
        imports: list[tuple[re.Match[str], tuple[str, str]]] = []
        for match in re.finditer(r"(?m)^.*$", original):
            import_match = IMPORT_RE.fullmatch(match.group(0))
            if not import_match:
                continue
            key = (import_match.group("repo"), import_match.group("snippet"))
            if key in declarations:
                imports.append((import_match, key))
        if not imports:
            continue
        rewritten = original
        for import_match, key in reversed(imports):
            identifier = import_match.group("name")
            component = _component_pattern(identifier)
            matches = list(component.finditer(rewritten))
            if not matches:
                raise LegacyMigrationError(
                    f"{page}: imported {identifier} has no self-closing component use"
                )
            rewritten = component.sub(declarations[key], rewritten)
            rewritten = (
                rewritten[: import_match.start()] + rewritten[import_match.end() :]
            )
            used.add(key)
        source_page = page.with_name(f"{page.stem}.source.mdx")
        source_page.write_text(rewritten, encoding="utf-8")
        changed_pages.add(source_page)
    return used, changed_pages


def remove_migrated_entries(
    snippets: list[LegacySnippet], migrated: set[tuple[str, str]]
) -> None:
    by_manifest: dict[Path, list[LegacySnippet]] = {}
    for snippet in snippets:
        by_manifest.setdefault(snippet.manifest_path, []).append(snippet)
    for manifest_path, manifest_snippets in by_manifest.items():
        removed = {
            snippet.name
            for snippet in manifest_snippets
            if (snippet.alias, snippet.name) in migrated
        }
        if not removed:
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["snippets"] = [
            entry
            for entry in payload["snippets"]
            if entry.get("snippetName") not in removed
        ]
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        for snippet in manifest_snippets:
            if snippet.name in removed:
                snippet.output_path.unlink()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit and migrate legacy manifest snippets into inline pages"
    )
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--repo", action="append", default=[])
    parser.add_argument("--snippet", action="append", default=[])
    parser.add_argument(
        "--commit",
        action="append",
        default=[],
        metavar="ALIAS=SHA",
        help="Temporarily override a repository pin while auditing.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-mismatch",
        action="store_true",
        help="Apply only byte-identical entries while leaving mismatches in the legacy manifest.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        pins = load_plan(args.plan)
        aliases = set(args.repo)
        names = set(args.snippet)
        unknown = aliases - {key for key in pins if ":" not in key}
        if unknown:
            raise LegacyMigrationError(
                f"Unknown migration repository alias(es): {', '.join(sorted(unknown))}"
            )
        for raw_override in args.commit:
            alias, separator, commit = raw_override.partition("=")
            parent = pins.get(alias)
            if (
                not separator
                or parent is None
                or not re.fullmatch(r"[0-9a-f]{40}", commit)
            ):
                raise LegacyMigrationError(
                    f"Commit override must be a known ALIAS=40_CHARACTER_SHA: {raw_override}"
                )
            pins[alias] = SourcePin(alias, parent.repository, commit)
        registry = load_registry(CF_DOCS_ROOT / "config" / "snippet-repositories.json")
        snippets = load_legacy_snippets()
        resolver = SourceResolver(
            GitHubClient(), repositories=set(registry), allow_local=False
        )
        declarations, failures = audit(
            snippets,
            pins,
            aliases=aliases,
            names=names,
            registry=registry,
            resolver=resolver,
        )
        selected = [
            snippet
            for snippet in snippets
            if not aliases or snippet.alias in aliases
            if not names or snippet.name in names
        ]
        blocked = [
            snippet
            for snippet in selected
            if snippet.blocked_reason or snippet.orphan_reason
        ]
        print(
            f"Audited {len(declarations)} reproducible snippet(s); "
            f"{len(blocked)} blocked; {len(failures)} mismatch(es)"
        )
        for failure in failures:
            print(failure, file=sys.stderr)
        if failures and not args.allow_mismatch:
            return 1
        if args.apply:
            used, pages = migrate_pages(declarations)
            unused = set(declarations) - used
            if unused:
                rendered = ", ".join(f"{repo}:{name}" for repo, name in sorted(unused))
                raise LegacyMigrationError(
                    f"Refusing to remove {len(unused)} unreferenced snippet(s): {rendered}"
                )
            remove_migrated_entries(snippets, used)
            print(f"Migrated {len(used)} snippet(s) across {len(pages)} page(s)")
        return 0
    except (LegacyMigrationError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

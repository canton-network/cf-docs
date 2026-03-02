#!/usr/bin/env python3
"""
MVP: Consolidate versioned JavaDoc/ScalaDoc artifacts into one API lifecycle JSON.

This script intentionally favors speed and robustness over perfect fidelity:
- Inputs are published `-javadoc.jar` artifacts from Maven repositories.
- Java symbols are parsed from `type-search-index.js` and `member-search-index.js`.
- Scala symbols are parsed from Scaladoc's `index.js` (`Index.PACKAGES`).
- Deprecation is best-effort:
  - Java: parsed from `deprecated-list.html` links/comments when present.
  - Scala: currently not extracted (Scaladoc index does not expose deprecations).
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def normalize_href(href: str) -> str:
    out = html.unescape(href.strip())
    if out.startswith("./"):
        out = out[2:]
    if out.startswith("/"):
        out = out[1:]
    return out


def strip_html_tags(fragment: str) -> str:
    no_tags = re.sub(r"<[^>]+>", "", fragment, flags=re.S)
    text = html.unescape(no_tags)
    return re.sub(r"\s+", " ", text).strip()


def include_name(name: str, prefixes: List[str]) -> bool:
    if not prefixes:
        return True
    for p in prefixes:
        if name == p or name.startswith(p + ".") or name.startswith(p + "$"):
            return True
    return False


def js_assignment_to_json(text: str, variable: str) -> Any:
    """
    Parse assignments like:
      memberSearchIndex = [...];updateSearchResults();
      Index.PACKAGES = {...};
    """
    pattern = re.compile(
        rf"{re.escape(variable)}\s*=\s*(.+?)\s*;\s*(?:updateSearchResults\(\)\s*;?)?\s*$",
        flags=re.S,
    )
    m = pattern.search(text)
    if not m:
        raise ValueError(f"Could not parse JS assignment for {variable}")
    payload = m.group(1).strip()
    return json.loads(payload)


def maven_javadoc_url(repo_base: str, group: str, artifact: str, version: str) -> str:
    group_path = group.replace(".", "/")
    base = repo_base.rstrip("/")
    filename = f"{artifact}-{version}-javadoc.jar"
    return f"{base}/{group_path}/{artifact}/{version}/{filename}"


def javadocio_symbol_url(group: str, artifact: str, version: str, doc_path: str) -> str:
    g = urllib.parse.quote(group, safe="")
    a = urllib.parse.quote(artifact, safe="")
    v = urllib.parse.quote(version, safe="")
    p = doc_path.lstrip("/")
    return f"https://javadoc.io/doc/{g}/{a}/{v}/{p}"


def fetch_file(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        return
    req = urllib.request.Request(url, headers={"User-Agent": "daml-doc-lifecycle-mvp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            out_path.write_bytes(resp.read())
    except urllib.error.HTTPError as ex:
        raise RuntimeError(f"HTTP {ex.code} while downloading {url}") from ex
    except urllib.error.URLError as ex:
        raise RuntimeError(f"Network error while downloading {url}: {ex}") from ex


def deprecated_refs_from_java_html(text: str) -> Dict[str, str]:
    """
    Parse javadoc deprecated-list.html table rows into:
      normalized_href -> deprecation_comment
    """
    out: Dict[str, str] = {}
    row_pattern = re.compile(
        r'<div class="col-summary-item-name[^"]*">\s*<a href="([^"]+)".*?</a>\s*</div>\s*'
        r'<div class="col-last[^"]*">\s*(?:<div class="deprecation-comment">(.*?)</div>)?',
        flags=re.S,
    )
    for href, comment_html in row_pattern.findall(text):
        comment = strip_html_tags(comment_html) if comment_html else ""

        norm = normalize_href(href)
        out[norm] = comment
        out[urllib.parse.unquote(norm)] = comment
    return out


def java_member_hrefs(entry: Dict[str, Any]) -> Set[str]:
    p = entry.get("p", "")
    c = entry.get("c", "")
    if not p or not c:
        return set()
    base = f"{p.replace('.', '/')}/{c}.html"

    raw_anchor = entry.get("u")
    if raw_anchor is None:
        raw_anchor = urllib.parse.quote(str(entry.get("l", "")), safe="")
    href = f"{base}#{raw_anchor}" if raw_anchor else base
    href = normalize_href(href)
    return {href, urllib.parse.unquote(href)}


def java_type_href(entry: Dict[str, Any]) -> Optional[str]:
    if entry.get("u"):
        return normalize_href(str(entry["u"]))
    p = entry.get("p", "")
    l = entry.get("l", "")
    if not l or l == "All Classes and Interfaces":
        return None
    if p:
        return normalize_href(f"{p.replace('.', '/')}/{l}.html")
    return normalize_href(f"{l}.html")


def parse_since_from_note(note: str) -> Optional[str]:
    m = re.search(r"\bsince\s+([A-Za-z0-9._-]+)", note, flags=re.I)
    if m:
        return m.group(1).strip()
    return None


def parse_java_symbols(
    zf: zipfile.ZipFile,
    group: str,
    artifact: str,
    version: str,
    include_prefixes: List[str],
) -> List[Dict[str, Any]]:
    symbols: List[Dict[str, Any]] = []

    deprecated_ref_map: Dict[str, str] = {}
    if "deprecated-list.html" in zf.namelist():
        try:
            dep_text = zf.read("deprecated-list.html").decode("utf-8", errors="replace")
            deprecated_ref_map = deprecated_refs_from_java_html(dep_text)
        except Exception as ex:  # pragma: no cover - defensive
            eprint(f"[warn] failed parsing deprecated-list.html for {artifact}:{version}: {ex}")

    type_entries: List[Dict[str, Any]] = []
    member_entries: List[Dict[str, Any]] = []

    if "type-search-index.js" in zf.namelist():
        raw = zf.read("type-search-index.js").decode("utf-8", errors="replace")
        type_entries = js_assignment_to_json(raw, "typeSearchIndex")
    if "member-search-index.js" in zf.namelist():
        raw = zf.read("member-search-index.js").decode("utf-8", errors="replace")
        member_entries = js_assignment_to_json(raw, "memberSearchIndex")

    for e in type_entries:
        pkg = str(e.get("p", "")).strip()
        label = str(e.get("l", "")).strip()
        if not label or label == "All Classes and Interfaces":
            continue
        fqn = f"{pkg}.{label}" if pkg else label
        if not include_name(fqn, include_prefixes):
            continue

        doc_path = java_type_href(e)
        if not doc_path:
            continue
        dep_note = deprecated_ref_map.get(doc_path) or deprecated_ref_map.get(urllib.parse.unquote(doc_path))
        symbols.append(
            {
                "symbol_key": f"{artifact}:java:type:{fqn}",
                "language": "java",
                "kind": "type",
                "symbol": fqn,
                "doc_path": doc_path,
                "doc_url": javadocio_symbol_url(group, artifact, version, doc_path),
                "deprecated_note": dep_note,
            }
        )

    for e in member_entries:
        pkg = str(e.get("p", "")).strip()
        owner = str(e.get("c", "")).strip()
        label = str(e.get("l", "")).strip()
        if not pkg or not owner or not label:
            continue
        owner_fqn = f"{pkg}.{owner}"
        if not include_name(owner_fqn, include_prefixes):
            continue

        sig = str(e.get("u", "") or label)
        symbol = f"{owner_fqn}#{label}"
        hrefs = java_member_hrefs(e)
        if not hrefs:
            continue
        # Preserve one stable path for display URL.
        doc_path = sorted(hrefs)[0]

        dep_note: Optional[str] = None
        for href in hrefs:
            if href in deprecated_ref_map:
                dep_note = deprecated_ref_map[href]
                break

        symbols.append(
            {
                "symbol_key": f"{artifact}:java:member:{owner_fqn}#{sig}",
                "language": "java",
                "kind": "member",
                "symbol": symbol,
                "doc_path": doc_path,
                "doc_url": javadocio_symbol_url(group, artifact, version, doc_path),
                "deprecated_note": dep_note,
            }
        )

    return symbols


def first_doc_path_from_scaladoc_entry(entry: Dict[str, Any]) -> Optional[str]:
    preferred_keys = [
        "final case class",
        "case class",
        "class",
        "sealed trait",
        "trait",
        "enum",
        "object",
        "case object",
    ]
    for key in preferred_keys:
        v = entry.get(key)
        if isinstance(v, str) and v.endswith(".html"):
            return normalize_href(v)

    skip = {"name", "shortDescription", "kind"}
    for k, v in entry.items():
        if k in skip or k.startswith("members_"):
            continue
        if isinstance(v, str) and v.endswith(".html"):
            return normalize_href(v)
    return None


def parse_scala_symbols(
    zf: zipfile.ZipFile,
    group: str,
    artifact: str,
    version: str,
    include_prefixes: List[str],
) -> List[Dict[str, Any]]:
    if "index.js" not in zf.namelist():
        return []
    raw = zf.read("index.js").decode("utf-8", errors="replace")
    data = js_assignment_to_json(raw, "Index.PACKAGES")

    symbols: List[Dict[str, Any]] = []

    for _pkg, entries in data.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if name and include_name(name, include_prefixes):
                doc_path = first_doc_path_from_scaladoc_entry(entry)
                if doc_path:
                    symbols.append(
                        {
                            "symbol_key": f"{artifact}:scala:type:{name}",
                            "language": "scala",
                            "kind": "type",
                            "symbol": name,
                            "doc_path": doc_path,
                            "doc_url": javadocio_symbol_url(group, artifact, version, doc_path),
                            "deprecated_note": None,
                        }
                    )

            for mk, members in entry.items():
                if not mk.startswith("members_") or not isinstance(members, list):
                    continue
                for m in members:
                    if not isinstance(m, dict):
                        continue
                    member_fqn = str(m.get("member", "")).strip()
                    tail = str(m.get("tail", "")).strip()
                    link = str(m.get("link", "")).strip()
                    label = str(m.get("label", "")).strip()
                    if not member_fqn or not link:
                        continue
                    if not include_name(member_fqn, include_prefixes):
                        continue
                    display = f"{member_fqn}{tail}" if tail else member_fqn
                    symbols.append(
                        {
                            "symbol_key": f"{artifact}:scala:member:{member_fqn}|{tail}|{link}",
                            "language": "scala",
                            "kind": "member",
                            "symbol": display if display else label,
                            "doc_path": normalize_href(link),
                            "doc_url": javadocio_symbol_url(group, artifact, version, normalize_href(link)),
                            "deprecated_note": None,
                        }
                    )

    return symbols


def parse_symbols_from_javadoc_jar(
    jar_path: Path,
    language: str,
    group: str,
    artifact: str,
    version: str,
    include_prefixes: List[str],
) -> List[Dict[str, Any]]:
    with zipfile.ZipFile(jar_path) as zf:
        if language == "java":
            return parse_java_symbols(zf, group, artifact, version, include_prefixes)
        if language == "scala":
            return parse_scala_symbols(zf, group, artifact, version, include_prefixes)
        raise ValueError(f"Unsupported language: {language}")


def consolidate_lifecycle(
    artifact_cfg: Dict[str, Any],
    version_symbols: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    versions: List[str] = artifact_cfg["versions"]
    version_index = {v: i for i, v in enumerate(versions)}

    aggregate: Dict[str, Dict[str, Any]] = {}

    for version, symbols in version_symbols.items():
        for s in symbols:
            key = s["symbol_key"]
            rec = aggregate.get(key)
            if rec is None:
                rec = {
                    "symbol_key": key,
                    "language": s["language"],
                    "kind": s["kind"],
                    "symbol": s["symbol"],
                    "versions_present": set(),
                    "doc_links": {},
                    "deprecation_notes": {},
                }
                aggregate[key] = rec
            rec["versions_present"].add(version)
            rec["doc_links"][version] = s["doc_url"]
            if s.get("deprecated_note") is not None:
                rec["deprecation_notes"][version] = s.get("deprecated_note", "")

    lifecycle_records: List[Dict[str, Any]] = []
    for rec in aggregate.values():
        present = sorted(rec["versions_present"], key=lambda v: version_index[v])
        introduced = present[0]
        last_seen_idx = max(version_index[v] for v in present)
        removed = versions[last_seen_idx + 1] if (last_seen_idx + 1) < len(versions) else None

        deprecated_version: Optional[str] = None
        deprecation_note: Optional[str] = None
        dep_notes = rec["deprecation_notes"]
        if dep_notes:
            observed = sorted(dep_notes.keys(), key=lambda v: version_index[v])
            deprecated_version = observed[0]
            deprecation_note = dep_notes[deprecated_version] or None

            # If note says "since x.y.z" and that version is in this sequence, prefer it.
            inferred: Optional[str] = None
            for v in observed:
                candidate = parse_since_from_note(dep_notes[v] or "")
                if candidate and candidate in version_index:
                    if inferred is None or version_index[candidate] < version_index[inferred]:
                        inferred = candidate
            if inferred:
                deprecated_version = inferred

        lifecycle_records.append(
            {
                "symbol_key": rec["symbol_key"],
                "language": rec["language"],
                "kind": rec["kind"],
                "symbol": rec["symbol"],
                "introduced_version": introduced,
                "deprecated_version": deprecated_version,
                "removed_version": removed,
                "versions_present": present,
                "doc_links": rec["doc_links"],
                "deprecation_note": deprecation_note,
            }
        )

    # Deterministic output order.
    lifecycle_records.sort(
        key=lambda r: (
            r["language"],
            r["kind"],
            r["symbol"],
        )
    )
    return lifecycle_records


def process_artifact(
    artifact_cfg: Dict[str, Any],
    repo_base: str,
    cache_dir: Path,
) -> Dict[str, Any]:
    group = artifact_cfg["group"]
    artifact = artifact_cfg["artifact"]
    language = artifact_cfg["language"]
    versions = artifact_cfg["versions"]
    include_prefixes = artifact_cfg.get("include_prefixes", [])

    version_symbols: Dict[str, List[Dict[str, Any]]] = {}
    failures: List[Dict[str, str]] = []

    for version in versions:
        url = maven_javadoc_url(repo_base, group, artifact, version)
        jar_path = cache_dir / group / artifact / version / f"{artifact}-{version}-javadoc.jar"
        try:
            fetch_file(url, jar_path)
            symbols = parse_symbols_from_javadoc_jar(
                jar_path=jar_path,
                language=language,
                group=group,
                artifact=artifact,
                version=version,
                include_prefixes=include_prefixes,
            )
            version_symbols[version] = symbols
            eprint(
                f"[ok] {group}:{artifact}:{version} parsed {len(symbols)} symbols"
            )
        except Exception as ex:
            failures.append({"version": version, "error": str(ex), "url": url})
            version_symbols[version] = []
            eprint(f"[warn] {group}:{artifact}:{version} failed: {ex}")

    lifecycle = consolidate_lifecycle(artifact_cfg, version_symbols)
    return {
        "artifact": artifact,
        "group": group,
        "language": language,
        "versions": versions,
        "symbol_count": len(lifecycle),
        "failures": failures,
        "symbols": lifecycle,
    }


def validate_config(config: Dict[str, Any]) -> None:
    if "artifacts" not in config or not isinstance(config["artifacts"], list):
        raise ValueError("Config must contain `artifacts` array.")
    for i, a in enumerate(config["artifacts"]):
        for req in ("group", "artifact", "language", "versions"):
            if req not in a:
                raise ValueError(f"artifacts[{i}] is missing `{req}`")
        if a["language"] not in ("java", "scala"):
            raise ValueError(f"artifacts[{i}].language must be `java` or `scala`")
        if not isinstance(a["versions"], list) or not a["versions"]:
            raise ValueError(f"artifacts[{i}].versions must be a non-empty list")


def main() -> int:
    parser = argparse.ArgumentParser(description="DAML JavaDoc/ScalaDoc lifecycle MVP")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to JSON config that lists artifacts and versions.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--cache-dir",
        default=".internal/cache/daml-doc-lifecycle-mvp",
        help="Directory used to cache downloaded javadoc jars.",
    )
    parser.add_argument(
        "--repo-base",
        default="https://repo1.maven.org/maven2",
        help="Base Maven repository URL.",
    )
    args = parser.parse_args()

    cfg_path = Path(args.config)
    out_path = Path(args.output)
    cache_dir = Path(args.cache_dir)

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    validate_config(cfg)

    results: List[Dict[str, Any]] = []
    for artifact_cfg in cfg["artifacts"]:
        results.append(process_artifact(artifact_cfg, args.repo_base, cache_dir))

    final = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_base": args.repo_base,
        "config_path": str(cfg_path),
        "artifacts": results,
        "summary": {
            "artifacts": len(results),
            "total_symbols": sum(r["symbol_count"] for r in results),
            "total_failures": sum(len(r["failures"]) for r in results),
        },
        "notes": [
            "MVP parser: Java deprecation uses deprecated-list.html when present.",
            "Scala deprecation is not inferred in this MVP because Scaladoc index.js does not expose it.",
            "removed_version means first version after the last observed presence in the configured version sequence.",
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(final, indent=2, sort_keys=False), encoding="utf-8")
    eprint(f"[done] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

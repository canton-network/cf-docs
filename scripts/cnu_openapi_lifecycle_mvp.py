#!/usr/bin/env python3
"""
Build lifecycle metadata for OpenAPI specs across clean semver release tags.

Inputs:
  - Local canton-network-utilities git repository
  - Clean semver tags only: ^(v)?X.Y.Z$

Output:
  - JSON with spec-level and entity-level lifecycle markers:
      introduced_version / changed_in_versions / removed_version
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}

OPENAPI_ROOTS = [
    "app/backend/utility-api-services/src/main/openapi",
    "app/common/resources/openapi",
    "app/openapi",
]


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def run(cmd: List[str], stdin_text: Optional[str] = None) -> str:
    proc = subprocess.run(
        cmd,
        input=stdin_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc.stdout


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def semver_key(tag: str) -> Tuple[int, int, int]:
    t = tag[1:] if tag.startswith("v") else tag
    major, minor, patch = t.split(".", 2)
    return int(major), int(minor), int(patch)


def clean_semver_tags(repo: Path, tag_regex: str) -> List[str]:
    raw = run(["git", "-C", str(repo), "tag", "--list"]).splitlines()
    pat = re.compile(tag_regex)
    out = [t.strip() for t in raw if pat.match(t.strip())]
    out.sort(key=semver_key)
    return out


def list_tag_files(repo: Path, tag: str, roots: List[str]) -> List[str]:
    cmd = ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", tag, "--", *roots]
    raw = run(cmd).splitlines()
    out: List[str] = []
    for p in raw:
        p = p.strip()
        if not p:
            continue
        if p.endswith(".yaml") or p.endswith(".yml") or p.endswith(".json"):
            out.append(p)
    return sorted(set(out))


def git_show(repo: Path, tag: str, path: str) -> str:
    return run(["git", "-C", str(repo), "show", f"{tag}:{path}"])


def parse_openapi_with_yq(raw_text: str) -> Dict[str, Any]:
    parsed = run(["yq", "-o=json", ".", "-"], stdin_text=raw_text)
    obj = json.loads(parsed)
    if not isinstance(obj, dict):
        raise ValueError("OpenAPI document is not a JSON object after conversion")
    if "openapi" not in obj:
        raise ValueError("Document does not contain top-level `openapi` key")
    return obj


def normalize_relative_path(path: str) -> str:
    for prefix in OPENAPI_ROOTS:
        marker = prefix.rstrip("/") + "/"
        if path.startswith(marker):
            return path[len(marker) :]
    return path


def canonical_spec_id(path: str) -> str:
    rel = normalize_relative_path(path)

    if rel.startswith("cn-token-standard/"):
        rel = "cn-validator/" + rel[len("cn-token-standard/") :]

    if rel == "cn-validator/scan-internal.yaml":
        rel = "cn-validator/scan.yaml"

    legacy_utility_map = {
        "utility-token-standard/allocation.yaml": "utility-token-standard/v1/allocation-v1.yaml",
        "utility-token-standard/allocation-instruction.yaml": "utility-token-standard/v1/allocation-instruction-v1.yaml",
        "utility-token-standard/token-metadata.yaml": "utility-token-standard/v1/token-metadata-v1.yaml",
        "utility-token-standard/transfer-instruction.yaml": "utility-token-standard/v1/transfer-instruction-v1.yaml",
    }
    rel = legacy_utility_map.get(rel, rel)

    # Roll up allocation instruction variants that moved/renamed over time.
    if rel in {
        "cn-validator/allocation-instruction.yaml",
        "cn-validator/allocation-instruction-v1.yaml",
        "utility-token-standard/v1/allocation-instruction-v1.yaml",
    }:
        return "utility-token-standard/v1/allocation-instruction-v1.yaml"

    # Roll up allocation variants that moved/renamed over time.
    if rel in {
        "cn-validator/allocation.yaml",
        "cn-validator/allocation-v1.yaml",
        "utility-token-standard/v1/allocation-v1.yaml",
    }:
        return "utility-token-standard/v1/allocation-v1.yaml"

    if rel.startswith("canton-json-apidocs_") and rel.endswith("/openapi.yaml"):
        return "canton-json-apidocs/openapi.yaml"

    return rel


def path_priority(path: str) -> int:
    if path.startswith("app/common/resources/openapi/"):
        return 3
    if path.startswith("app/backend/utility-api-services/src/main/openapi/"):
        return 2
    if path.startswith("app/openapi/"):
        return 1
    return 0


def entity_name(entity_type: str, key_parts: Tuple[str, ...]) -> str:
    if entity_type == "operation":
        method, path = key_parts
        return f"{method.upper()} {path}"
    if entity_type == "path":
        return key_parts[0]
    if entity_type == "component":
        kind, name = key_parts
        return f"{kind}.{name}"
    if entity_type == "tag":
        return key_parts[0]
    return ":".join(key_parts)


def extract_entities(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    entities: Dict[str, Dict[str, Any]] = {}

    paths = doc.get("paths", {})
    if isinstance(paths, dict):
        for p in sorted(paths):
            path_item = paths[p]
            if not isinstance(path_item, dict):
                continue

            key = f"path::{p}"
            entities[key] = {
                "entity_key": key,
                "entity_type": "path",
                "name": entity_name("path", (p,)),
                "hash": sha256_json(path_item),
                "path": p,
            }

            for method in sorted(path_item):
                operation = path_item[method]
                method_l = str(method).lower()
                if method_l not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                op_key = f"operation::{method_l.upper()}::{p}"
                entities[op_key] = {
                    "entity_key": op_key,
                    "entity_type": "operation",
                    "name": entity_name("operation", (method_l, p)),
                    "hash": sha256_json(operation),
                    "method": method_l.upper(),
                    "path": p,
                    "operation_id": operation.get("operationId"),
                }

    components = doc.get("components", {})
    if isinstance(components, dict):
        for comp_kind in sorted(components):
            comp_map = components[comp_kind]
            if not isinstance(comp_map, dict):
                continue
            for comp_name in sorted(comp_map):
                comp_value = comp_map[comp_name]
                key = f"component::{comp_kind}::{comp_name}"
                entities[key] = {
                    "entity_key": key,
                    "entity_type": "component",
                    "name": entity_name("component", (comp_kind, comp_name)),
                    "hash": sha256_json(comp_value),
                    "component_kind": comp_kind,
                    "component_name": comp_name,
                }

    tags = doc.get("tags", [])
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            tag_name = tag.get("name")
            if not isinstance(tag_name, str) or not tag_name.strip():
                continue
            key = f"tag::{tag_name}"
            entities[key] = {
                "entity_key": key,
                "entity_type": "tag",
                "name": entity_name("tag", (tag_name,)),
                "hash": sha256_json(tag),
                "tag_name": tag_name,
            }

    return entities


def resolve_local_ref(doc: Dict[str, Any], node: Any, max_depth: int = 6) -> Any:
    current = node
    depth = 0
    while isinstance(current, dict) and "$ref" in current and depth < max_depth:
        ref = current["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            break
        parts = ref[2:].split("/")
        target: Any = doc
        ok = True
        for part in parts:
            if isinstance(target, dict) and part in target:
                target = target[part]
            else:
                ok = False
                break
        if not ok:
            break
        current = target
        depth += 1
    return current


def schema_brief(doc: Dict[str, Any], schema: Any) -> str:
    resolved = resolve_local_ref(doc, schema)
    if not isinstance(resolved, dict):
        return "-"

    t = resolved.get("type")
    if isinstance(t, str):
        if t == "array":
            items = resolved.get("items")
            inner = schema_brief(doc, items)
            return f"array[{inner}]"
        return t

    if "oneOf" in resolved and isinstance(resolved["oneOf"], list):
        return "oneOf"
    if "anyOf" in resolved and isinstance(resolved["anyOf"], list):
        return "anyOf"
    if "allOf" in resolved and isinstance(resolved["allOf"], list):
        return "allOf"
    if "properties" in resolved and isinstance(resolved["properties"], dict):
        return "object"
    return "-"


def extract_latest_operation_details(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    paths = doc.get("paths", {})
    if not isinstance(paths, dict):
        return out

    for path in sorted(paths):
        path_item = paths[path]
        if not isinstance(path_item, dict):
            continue

        path_level_params = path_item.get("parameters", [])
        if not isinstance(path_level_params, list):
            path_level_params = []

        for method in sorted(path_item):
            operation = path_item[method]
            method_l = str(method).lower()
            if method_l not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            params: List[Dict[str, Any]] = []
            op_params = operation.get("parameters", [])
            if not isinstance(op_params, list):
                op_params = []
            merged_params = path_level_params + op_params

            for p in merged_params:
                p_resolved = resolve_local_ref(doc, p)
                if not isinstance(p_resolved, dict):
                    continue
                schema = p_resolved.get("schema")
                params.append(
                    {
                        "name": p_resolved.get("name"),
                        "in": p_resolved.get("in"),
                        "required": bool(p_resolved.get("required", False)),
                        "description": p_resolved.get("description", ""),
                        "schema": schema_brief(doc, schema),
                    }
                )

            req_info: Dict[str, Any] = {}
            req = operation.get("requestBody")
            if req is not None:
                req_resolved = resolve_local_ref(doc, req)
                if isinstance(req_resolved, dict):
                    content = req_resolved.get("content", {})
                    content_types: List[str] = []
                    schema_by_content_type: Dict[str, str] = {}
                    if isinstance(content, dict):
                        for ct in sorted(content):
                            val = content[ct]
                            content_types.append(ct)
                            if isinstance(val, dict):
                                schema_by_content_type[ct] = schema_brief(doc, val.get("schema"))
                            else:
                                schema_by_content_type[ct] = "-"
                    req_info = {
                        "required": bool(req_resolved.get("required", False)),
                        "content_types": content_types,
                        "schema_by_content_type": schema_by_content_type,
                    }

            responses: List[Dict[str, Any]] = []
            responses_raw = operation.get("responses", {})
            if isinstance(responses_raw, dict):
                for code in sorted(responses_raw):
                    r = resolve_local_ref(doc, responses_raw[code])
                    if not isinstance(r, dict):
                        continue
                    content = r.get("content", {})
                    content_types: List[str] = []
                    schema_by_content_type: Dict[str, str] = {}
                    if isinstance(content, dict):
                        for ct in sorted(content):
                            content_types.append(ct)
                            val = content[ct]
                            if isinstance(val, dict):
                                schema_by_content_type[ct] = schema_brief(doc, val.get("schema"))
                            else:
                                schema_by_content_type[ct] = "-"
                    responses.append(
                        {
                            "code": code,
                            "description": r.get("description", ""),
                            "content_types": content_types,
                            "schema_by_content_type": schema_by_content_type,
                        }
                    )

            tags = operation.get("tags", [])
            if not isinstance(tags, list):
                tags = []

            out.append(
                {
                    "method": method_l.upper(),
                    "path": path,
                    "operation_id": operation.get("operationId"),
                    "summary": operation.get("summary", ""),
                    "description": operation.get("description", ""),
                    "tags": [str(t) for t in tags],
                    "parameters": params,
                    "request_body": req_info,
                    "responses": responses,
                }
            )

    return out


def pick_spec_variant(existing: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    existing_hash = existing["spec_hash"]
    candidate_hash = candidate["spec_hash"]
    if existing_hash == candidate_hash:
        aliases = sorted(set(existing.get("aliases", []) + [candidate["git_path"]]))
        existing["aliases"] = aliases
        return existing

    keep = existing
    other = candidate
    if existing.get("spec_id") in {
        "utility-token-standard/v1/allocation-instruction-v1.yaml",
        "utility-token-standard/v1/allocation-v1.yaml",
    }:
        def rollup_priority(path: str) -> int:
            if "/utility-token-standard/" in path:
                return 3
            if "/cn-token-standard/" in path:
                return 2
            if "/cn-validator/" in path:
                return 1
            return 0

        if rollup_priority(candidate["git_path"]) > rollup_priority(existing["git_path"]):
            keep, other = candidate, existing
    elif path_priority(candidate["git_path"]) > path_priority(existing["git_path"]):
        keep, other = candidate, existing

    keep_aliases = set(keep.get("aliases", []))
    keep_aliases.add(keep["git_path"])
    keep_aliases.add(other["git_path"])
    keep["aliases"] = sorted(keep_aliases)
    keep.setdefault("shadowed_variants", []).append(
        {
            "git_path": other["git_path"],
            "spec_hash": other["spec_hash"],
            "info_title": other.get("info_title"),
            "info_version": other.get("info_version"),
        }
    )
    return keep


def load_tag_specs(
    repo: Path,
    tag: str,
    include_spec_re: Optional[re.Pattern[str]],
    exclude_spec_re: Optional[re.Pattern[str]],
    exclude_source_re: Optional[re.Pattern[str]],
) -> Dict[str, Dict[str, Any]]:
    files = list_tag_files(repo, tag, OPENAPI_ROOTS)
    spec_map: Dict[str, Dict[str, Any]] = {}

    for path in files:
        if exclude_source_re and exclude_source_re.search(path):
            continue

        spec_id = canonical_spec_id(path)
        if include_spec_re and not include_spec_re.search(spec_id):
            continue
        if exclude_spec_re and exclude_spec_re.search(spec_id):
            continue

        try:
            raw = git_show(repo, tag, path)
            doc = parse_openapi_with_yq(raw)
        except ValueError as ex:
            if "top-level `openapi` key" in str(ex):
                # Expected for sibling AsyncAPI files under the same roots.
                continue
            eprint(f"[warn] {tag}:{path} skipped ({ex})")
            continue
        except Exception as ex:
            eprint(f"[warn] {tag}:{path} skipped ({ex})")
            continue

        entities = extract_entities(doc)
        spec_hash = sha256_json(doc)
        info = doc.get("info", {}) if isinstance(doc.get("info"), dict) else {}
        candidate = {
            "spec_id": spec_id,
            "git_path": path,
            "aliases": [path],
            "openapi_version": doc.get("openapi"),
            "info_title": info.get("title"),
            "info_version": info.get("version"),
            "spec_hash": spec_hash,
            "entity_count": len(entities),
            "entities": entities,
            "doc": doc,
        }

        if spec_id in spec_map:
            spec_map[spec_id] = pick_spec_variant(spec_map[spec_id], candidate)
        else:
            spec_map[spec_id] = candidate

    return spec_map


def next_tag_after(tags: List[str], tag: str) -> Optional[str]:
    idx = tags.index(tag)
    if idx + 1 < len(tags):
        return tags[idx + 1]
    return None


def entity_lifecycle_for_spec(spec_versions: Dict[str, Dict[str, Any]], tags: List[str]) -> List[Dict[str, Any]]:
    all_keys: set[str] = set()
    for tag in tags:
        snap = spec_versions.get(tag)
        if not snap:
            continue
        all_keys.update(snap["entities"].keys())

    out: List[Dict[str, Any]] = []
    for key in sorted(all_keys):
        present = [t for t in tags if t in spec_versions and key in spec_versions[t]["entities"]]
        if not present:
            continue

        introduced = present[0]
        removed = next_tag_after(tags, present[-1])

        changed_in: List[str] = []
        prev_hash: Optional[str] = None
        for t in present:
            h = spec_versions[t]["entities"][key]["hash"]
            if prev_hash is not None and h != prev_hash:
                changed_in.append(t)
            prev_hash = h

        latest_meta = spec_versions[present[-1]]["entities"][key]
        out.append(
            {
                "entity_key": key,
                "entity_type": latest_meta["entity_type"],
                "name": latest_meta["name"],
                "introduced_version": introduced,
                "changed_in_versions": changed_in,
                "removed_version": removed,
                "versions_present": present,
                "latest": {
                    k: v
                    for k, v in latest_meta.items()
                    if k not in {"hash"}
                },
            }
        )
    return out


def per_version_entity_deltas(spec_versions: Dict[str, Dict[str, Any]], tags: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    prev: Dict[str, Dict[str, Any]] = {}

    for tag in tags:
        curr = spec_versions.get(tag, {}).get("entities", {})
        added = sorted(set(curr) - set(prev))
        removed = sorted(set(prev) - set(curr))
        changed = sorted(
            k
            for k in (set(curr) & set(prev))
            if curr[k]["hash"] != prev[k]["hash"]
        )

        if added or removed or changed:
            out[tag] = {
                "added_count": len(added),
                "removed_count": len(removed),
                "changed_count": len(changed),
                "added": added,
                "removed": removed,
                "changed": changed,
            }
        prev = curr
    return out


def summarize_latest_entities(entity_records: List[Dict[str, Any]], latest_version: str) -> Dict[str, List[Dict[str, Any]]]:
    operations: List[Dict[str, Any]] = []
    components: List[Dict[str, Any]] = []
    paths: List[Dict[str, Any]] = []
    tags: List[Dict[str, Any]] = []

    for rec in entity_records:
        if latest_version not in rec["versions_present"]:
            continue
        row = {
            "entity_key": rec["entity_key"],
            "name": rec["name"],
            "introduced_version": rec["introduced_version"],
            "changed_in_versions": rec["changed_in_versions"],
            "removed_version": rec["removed_version"],
            "latest": rec["latest"],
        }
        kind = rec["entity_type"]
        if kind == "operation":
            operations.append(row)
        elif kind == "component":
            components.append(row)
        elif kind == "path":
            paths.append(row)
        elif kind == "tag":
            tags.append(row)

    operations.sort(key=lambda r: r["name"])
    components.sort(key=lambda r: r["name"])
    paths.sort(key=lambda r: r["name"])
    tags.sort(key=lambda r: r["name"])
    return {
        "operations": operations,
        "components": components,
        "paths": paths,
        "tags": tags,
    }


def build_lifecycle(
    repo: Path,
    tags: List[str],
    include_spec_re: Optional[re.Pattern[str]],
    exclude_spec_re: Optional[re.Pattern[str]],
    exclude_source_re: Optional[re.Pattern[str]],
    tag_regex: str,
) -> Dict[str, Any]:
    all_specs: Dict[str, Dict[str, Dict[str, Any]]] = {}
    all_spec_docs: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for i, tag in enumerate(tags, start=1):
        eprint(f"[{i}/{len(tags)}] scanning tag {tag}")
        tag_specs = load_tag_specs(
            repo=repo,
            tag=tag,
            include_spec_re=include_spec_re,
            exclude_spec_re=exclude_spec_re,
            exclude_source_re=exclude_source_re,
        )
        for spec_id, snap in tag_specs.items():
            all_specs.setdefault(spec_id, {})[tag] = {
                k: v for k, v in snap.items() if k not in {"doc"}
            }
            all_spec_docs.setdefault(spec_id, {})[tag] = snap["doc"]

    spec_rows: List[Dict[str, Any]] = []
    total_entities = 0
    total_entity_changes = 0

    for spec_id in sorted(all_specs):
        versions = all_specs[spec_id]
        versions_present = [t for t in tags if t in versions]
        if not versions_present:
            continue

        introduced = versions_present[0]
        removed = next_tag_after(tags, versions_present[-1])
        latest = versions_present[-1]

        entity_records = entity_lifecycle_for_spec(versions, tags)
        total_entities += len(entity_records)
        total_entity_changes += sum(len(r["changed_in_versions"]) for r in entity_records)

        deltas = per_version_entity_deltas(versions, tags)

        changed_in_versions: List[str] = []
        prev_hash: Optional[str] = None
        for t in versions_present:
            h = versions[t]["spec_hash"]
            if prev_hash is not None and h != prev_hash:
                changed_in_versions.append(t)
            prev_hash = h

        snapshots: Dict[str, Dict[str, Any]] = {}
        for t in versions_present:
            snap = versions[t]
            snapshots[t] = {
                "git_path": snap["git_path"],
                "aliases": snap.get("aliases", []),
                "openapi_version": snap.get("openapi_version"),
                "info_title": snap.get("info_title"),
                "info_version": snap.get("info_version"),
                "spec_hash": snap.get("spec_hash"),
                "entity_count": snap.get("entity_count", 0),
                "shadowed_variants": snap.get("shadowed_variants", []),
            }

        latest_snapshot = versions[latest]
        latest_doc = all_spec_docs.get(spec_id, {}).get(latest, {})
        spec_rows.append(
            {
                "spec_id": spec_id,
                "display_name": latest_snapshot.get("info_title") or spec_id,
                "introduced_version": introduced,
                "changed_in_versions": changed_in_versions,
                "removed_version": removed,
                "versions_present": versions_present,
                "latest_version": latest,
                "latest_git_path": latest_snapshot["git_path"],
                "latest_openapi_version": latest_snapshot.get("openapi_version"),
                "latest_info_version": latest_snapshot.get("info_version"),
                "version_snapshots": snapshots,
                "entity_count": len(entity_records),
                "entity_lifecycle": entity_records,
                "per_version_entity_deltas": deltas,
                "latest_entities": summarize_latest_entities(entity_records, latest),
                "latest_operation_details": extract_latest_operation_details(latest_doc)
                if isinstance(latest_doc, dict)
                else [],
            }
        )

    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_repo": str(repo),
        "tag_filter": f"clean semver only ({tag_regex})",
        "tags": tags,
        "specs": spec_rows,
        "summary": {
            "tag_count": len(tags),
            "spec_count": len(spec_rows),
            "total_entities": total_entities,
            "total_entity_change_events": total_entity_changes,
        },
        "notes": [
            "Specs are discovered from OpenAPI roots in canton-network-utilities at each tag.",
            "Entity types tracked: path, operation, component, tag.",
            "changed_in_versions is computed by hash diff against previous observed presence.",
            "removed_version is the first clean-semver tag after last presence.",
            "Path canonicalization includes known migrations (cn-token-standard -> cn-validator, utility-token-standard legacy -> v1).",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Canton Network Utilities OpenAPI lifecycle MVP")
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to local canton-network-utilities git checkout",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON path",
    )
    parser.add_argument(
        "--include-spec",
        default="",
        help="Optional regex filter for canonical spec_id",
    )
    parser.add_argument(
        "--exclude-spec",
        default="",
        help="Optional regex exclusion for canonical spec_id",
    )
    parser.add_argument(
        "--exclude-source",
        default="",
        help="Optional regex exclusion for source git path before canonicalization",
    )
    parser.add_argument(
        "--tag-regex",
        default=r"^(v)?0\.[0-9]+\.[0-9]+$",
        help="Regex used to select release tags (default keeps v0.x.y line only)",
    )
    parser.add_argument(
        "--max-tags",
        type=int,
        default=0,
        help="Optional limit for number of tags (from oldest forward); 0 = all",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    out_path = Path(args.output)
    include_spec_re = re.compile(args.include_spec) if args.include_spec else None
    exclude_spec_re = re.compile(args.exclude_spec) if args.exclude_spec else None
    exclude_source_re = re.compile(args.exclude_source) if args.exclude_source else None

    tags = clean_semver_tags(repo, args.tag_regex)
    if args.max_tags > 0:
        tags = tags[: args.max_tags]
    if not tags:
        raise RuntimeError("No clean semver tags found")

    payload = build_lifecycle(
        repo=repo,
        tags=tags,
        include_spec_re=include_spec_re,
        exclude_spec_re=exclude_spec_re,
        exclude_source_re=exclude_source_re,
        tag_regex=args.tag_regex,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    eprint(f"[done] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

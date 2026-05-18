"""Build TypeDoc lifecycle reports from versioned TypeDoc JSON snapshots."""

from __future__ import annotations

import json
import re
from typing import Any

from x2mdx.typedoc.models import TypeDocReport, TypeDocSources

SNAPSHOT_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-snapshot\.(\d{8})\.(\d+)")
RC_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-rc(\d+)$")
STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

GROUP_KIND_LABELS = {
    "Interfaces": "Interface",
    "Type Aliases": "Type Alias",
    "Variables": "Variable",
    "Functions": "Function",
}


def version_sort_key(version: str) -> tuple[Any, ...]:
    if m := SNAPSHOT_VERSION_RE.fullmatch(version):
        major, minor, patch, yyyymmdd, seq = m.groups()
        return (0, int(major), int(minor), int(patch), 0, int(yyyymmdd), int(seq))
    if m := RC_VERSION_RE.fullmatch(version):
        major, minor, patch, rc = m.groups()
        return (0, int(major), int(minor), int(patch), 1, int(rc), 0)
    if m := STABLE_VERSION_RE.fullmatch(version):
        major, minor, patch = m.groups()
        return (0, int(major), int(minor), int(patch), 2, 0, 0)
    return (1, version)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def anchor_for_export(group_title: str, export_name: str) -> str:
    return f"{slugify(GROUP_KIND_LABELS.get(group_title, group_title))}-{slugify(export_name)}"


def render_comment_inline(parts: list[dict[str, Any]] | None) -> str | None:
    if not isinstance(parts, list):
        return None
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = str(part.get("text", ""))
        if not text:
            continue
        if part.get("kind") == "code":
            chunks.append(f"`{text}`")
        else:
            chunks.append(text)
    rendered = "".join(chunks).strip()
    return rendered or None


def extract_block_tag_texts(comment: dict[str, Any] | None, tag_name: str) -> list[str]:
    if not isinstance(comment, dict):
        return []
    block_tags = comment.get("blockTags")
    if not isinstance(block_tags, list):
        return []
    out: list[str] = []
    for tag in block_tags:
        if not isinstance(tag, dict) or tag.get("tag") != tag_name:
            continue
        rendered = render_comment_inline(tag.get("content"))
        if rendered:
            out.append(rendered)
    return out


def comment_has_tag(comment: dict[str, Any] | None, tag_name: str) -> bool:
    if not isinstance(comment, dict):
        return False
    modifier_tags = comment.get("modifierTags")
    if isinstance(modifier_tags, list) and tag_name in modifier_tags:
        return True
    block_tags = comment.get("blockTags")
    return isinstance(block_tags, list) and any(isinstance(tag, dict) and tag.get("tag") == tag_name for tag in block_tags)


def normalize_lifecycle_state(comment: dict[str, Any] | None) -> str | None:
    if comment_has_tag(comment, "@deprecated"):
        return "deprecated"
    for tag_name, state in [
        ("@alpha", "alpha"),
        ("@beta", "beta"),
        ("@stable", "stable"),
    ]:
        if comment_has_tag(comment, tag_name):
            return state
    return None


def lifecycle_state_label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def extract_first_block_tag_text(comment: dict[str, Any] | None, tag_name: str) -> str | None:
    texts = extract_block_tag_texts(comment, tag_name)
    return texts[0] if texts else None


def parse_named_tag_map(comment: dict[str, Any] | None, tag_name: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in extract_block_tag_texts(comment, tag_name):
        parts = item.split(None, 1)
        if not parts:
            continue
        mapping[parts[0]] = parts[1] if len(parts) > 1 else ""
    return mapping


def comment_has_internal_tag(comment: dict[str, Any] | None) -> bool:
    if not isinstance(comment, dict):
        return False
    tags = comment.get("modifierTags")
    return isinstance(tags, list) and "@internal" in tags


def is_internal_node(node: dict[str, Any]) -> bool:
    if comment_has_internal_tag(node.get("comment")):
        return True
    signatures = node.get("signatures")
    if isinstance(signatures, list) and signatures:
        public_signatures = [signature for signature in signatures if isinstance(signature, dict) and not comment_has_internal_tag(signature.get("comment"))]
        if not public_signatures:
            return True
    return False


def normalize_reference_target(target: Any) -> Any:
    if isinstance(target, dict):
        return {
            key: normalize_for_fingerprint(value)
            for key, value in target.items()
            if key in {"packageName", "packagePath", "qualifiedName"}
        }
    return None


def normalize_for_fingerprint(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_for_fingerprint(item) for item in value]
    if isinstance(value, dict):
        node_type = value.get("type")
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"id", "sources", "source", "files", "symbolIdMap"}:
                continue
            if key == "groups":
                if isinstance(item, list):
                    normalized[key] = [group.get("title") for group in item if isinstance(group, dict) and group.get("title")]
                continue
            if key == "children":
                if isinstance(item, list):
                    normalized[key] = [
                        normalize_for_fingerprint(child)
                        for child in item
                        if isinstance(child, dict) and not is_internal_node(child)
                    ]
                continue
            if key == "signatures":
                if isinstance(item, list):
                    normalized[key] = [
                        normalize_for_fingerprint(signature)
                        for signature in item
                        if isinstance(signature, dict) and not comment_has_internal_tag(signature.get("comment"))
                    ]
                continue
            if key == "target" and node_type == "reference":
                normalized[key] = normalize_reference_target(item)
                continue
            normalized[key] = normalize_for_fingerprint(item)
        return normalized
    return value


def type_parameter_text(type_parameter: dict[str, Any]) -> str:
    name = str(type_parameter.get("name", "T"))
    out = name
    constraint = render_type(type_parameter.get("type"))
    if constraint:
        out += f" extends {constraint}"
    default = render_type(type_parameter.get("default"))
    if default:
        out += f" = {default}"
    return out


def render_parameters(parameters: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for parameter in parameters:
        name = str(parameter.get("name", "arg"))
        flags = parameter.get("flags") if isinstance(parameter.get("flags"), dict) else {}
        prefix = "..." if flags.get("isRest") else ""
        suffix = "?" if flags.get("isOptional") else ""
        rendered.append(f"{prefix}{name}{suffix}: {render_type(parameter.get('type'))}")
    return ", ".join(rendered)


def render_signature(signature: dict[str, Any], *, include_name: bool = True) -> str:
    type_parameters = signature.get("typeParameters") if isinstance(signature.get("typeParameters"), list) else []
    type_params_text = ""
    if type_parameters:
        type_params_text = "<" + ", ".join(type_parameter_text(item) for item in type_parameters if isinstance(item, dict)) + ">"
    name = str(signature.get("name", "fn")) if include_name else ""
    prefix = f"{name}{type_params_text}" if include_name else type_params_text
    params = render_parameters([item for item in signature.get("parameters", []) if isinstance(item, dict)])
    return_type = render_type(signature.get("type"))
    if include_name:
        return f"{prefix}({params}): {return_type}"
    return f"({params}) => {return_type}"


def render_property_shape(node: dict[str, Any]) -> str:
    flags = node.get("flags") if isinstance(node.get("flags"), dict) else {}
    prefix = "readonly " if flags.get("isReadonly") else ""
    suffix = "?" if flags.get("isOptional") else ""
    return f"{prefix}{node.get('name', 'value')}{suffix}: {render_type(node.get('type'))}"


def render_type(type_obj: Any) -> str:
    if type_obj is None:
        return "void"
    if not isinstance(type_obj, dict):
        return str(type_obj)

    kind = type_obj.get("type")
    if kind == "intrinsic":
        return str(type_obj.get("name", "unknown"))
    if kind == "literal":
        return json.dumps(type_obj.get("value"))
    if kind == "reference":
        name = str(type_obj.get("name") or "unknown")
        type_arguments = type_obj.get("typeArguments") if isinstance(type_obj.get("typeArguments"), list) else []
        if type_arguments:
            name += "<" + ", ".join(render_type(arg) for arg in type_arguments) + ">"
        return name
    if kind == "array":
        return f"{render_type(type_obj.get('elementType'))}[]"
    if kind == "union":
        parts = [render_type(item) for item in type_obj.get("types", []) if isinstance(item, dict)]
        return " | ".join(parts) if parts else "unknown"
    if kind == "intersection":
        parts = [render_type(item) for item in type_obj.get("types", []) if isinstance(item, dict)]
        return " & ".join(parts) if parts else "unknown"
    if kind == "tuple":
        parts = [render_type(item) for item in type_obj.get("elements", []) if isinstance(item, dict)]
        return "[" + ", ".join(parts) + "]"
    if kind == "reflection":
        declaration = type_obj.get("declaration")
        if not isinstance(declaration, dict):
            return "{}"
        signatures = declaration.get("signatures")
        if isinstance(signatures, list) and signatures:
            first_signature = next((item for item in signatures if isinstance(item, dict)), None)
            if first_signature is not None:
                return render_signature(first_signature, include_name=False)
        children = declaration.get("children")
        if isinstance(children, list) and children:
            members = [render_property_shape(child) for child in children if isinstance(child, dict) and not is_internal_node(child)]
            return "{ " + "; ".join(members) + " }" if members else "{}"
        return "{}"
    return str(type_obj)


def build_member_docs(children: list[dict[str, Any]]) -> list[dict[str, str]]:
    member_docs: list[dict[str, str]] = []
    for child in children:
        if not isinstance(child, dict) or is_internal_node(child):
            continue
        summary = render_comment_inline((child.get("comment") or {}).get("summary")) or ""
        member_docs.append(
            {
                "name": str(child.get("name", "")),
                "type": render_type(child.get("type")),
                "summary": summary,
            }
        )
    return member_docs


def render_name_list(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def strip_named_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "name"}


def describe_named_item_changes(
    previous_items: list[dict[str, Any]],
    current_items: list[dict[str, Any]],
    *,
    singular_label: str,
    plural_label: str,
) -> list[str]:
    previous_by_name = {str(item["name"]): item for item in previous_items}
    current_by_name = {str(item["name"]): item for item in current_items}

    added = sorted(name for name in current_by_name if name not in previous_by_name)
    removed = sorted(name for name in previous_by_name if name not in current_by_name)
    updated = sorted(
        name
        for name in previous_by_name.keys() & current_by_name.keys()
        if strip_named_item(previous_by_name[name]) != strip_named_item(current_by_name[name])
    )

    changes: list[str] = []
    if len(added) == 1 and len(removed) == 1 and not updated:
        removed_name = removed[0]
        added_name = added[0]
        if strip_named_item(previous_by_name[removed_name]) == strip_named_item(current_by_name[added_name]):
            changes.append(f"{singular_label} renamed: `{removed_name}` -> `{added_name}`")
            return changes

    if added:
        changes.append(f"{plural_label} added: {render_name_list(added)}")
    if removed:
        changes.append(f"{plural_label} removed: {render_name_list(removed)}")
    if updated:
        changes.append(f"{plural_label} updated: {render_name_list(updated)}")
    return changes


def describe_signature_changes(previous_export: dict[str, Any], current_export: dict[str, Any]) -> list[str]:
    previous_declarations = [signature["declaration"] for signature in previous_export["signature_docs"]]
    current_declarations = [signature["declaration"] for signature in current_export["signature_docs"]]
    if previous_declarations != current_declarations:
        return ["call signatures updated"]
    if previous_export["signature_docs"] != current_export["signature_docs"]:
        return ["call signature details updated"]
    return []


def describe_export_changes(previous_export: dict[str, Any], current_export: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    if previous_export["summary"] != current_export["summary"]:
        changes.append("summary updated")
    if previous_export.get("lifecycle_state") != current_export.get("lifecycle_state"):
        changes.append("lifecycle state updated")
    if previous_export.get("replaces") != current_export.get("replaces"):
        changes.append("replacement target updated")
    if previous_export.get("deprecated_text") != current_export.get("deprecated_text"):
        changes.append("deprecation text updated")
    if (
        previous_export["signature"] != current_export["signature"]
        and not previous_export["signature_docs"]
        and not current_export["signature_docs"]
    ):
        changes.append("signature updated")

    changes.extend(
        describe_named_item_changes(
            previous_export["type_parameters"],
            current_export["type_parameters"],
            singular_label="type parameter",
            plural_label="type parameters",
        )
    )
    changes.extend(describe_signature_changes(previous_export, current_export))
    changes.extend(
        describe_named_item_changes(
            previous_export["members"],
            current_export["members"],
            singular_label="member",
            plural_label="members",
        )
    )
    return changes


def extract_type_parameter_docs(
    node: dict[str, Any],
    *,
    fallback_comment: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    comment = node.get("comment") if isinstance(node.get("comment"), dict) else fallback_comment
    descriptions = parse_named_tag_map(comment, "@typeparam")
    type_parameters = node.get("typeParameters")
    if not isinstance(type_parameters, list):
        return []
    docs: list[dict[str, str]] = []
    for item in type_parameters:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "T"))
        docs.append(
            {
                "name": name,
                "constraint": render_type(item.get("type")) if item.get("type") is not None else "",
                "default": render_type(item.get("default")) if item.get("default") is not None else "",
                "description": descriptions.get(name, ""),
            }
        )
    return docs


def extract_signature_docs(signatures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for signature in signatures:
        if not isinstance(signature, dict) or comment_has_internal_tag(signature.get("comment")):
            continue
        comment = signature.get("comment") if isinstance(signature.get("comment"), dict) else None
        param_descriptions = parse_named_tag_map(comment, "@param")
        parameters = []
        for parameter in signature.get("parameters", []):
            if not isinstance(parameter, dict):
                continue
            name = str(parameter.get("name", "arg"))
            flags = parameter.get("flags") if isinstance(parameter.get("flags"), dict) else {}
            parameters.append(
                {
                    "name": name,
                    "type": render_type(parameter.get("type")),
                    "required": "no" if flags.get("isOptional") else "yes",
                    "description": param_descriptions.get(name, ""),
                }
            )
        docs.append(
            {
                "declaration": render_signature(signature),
                "summary": render_comment_inline((comment or {}).get("summary")) or "",
                "type_parameters": extract_type_parameter_docs(signature, fallback_comment=comment),
                "parameters": parameters,
                "returns": render_type(signature.get("type")),
            }
        )
    return docs


def build_export_doc(group_title: str, node: dict[str, Any], *, group_index: int, item_index: int) -> dict[str, Any]:
    name = str(node.get("name", ""))
    kind_label = GROUP_KIND_LABELS.get(group_title, group_title.rstrip("s") or "Export")
    summary = render_comment_inline((node.get("comment") or {}).get("summary"))
    children = [child for child in node.get("children", []) if isinstance(child, dict) and not is_internal_node(child)]
    public_signatures = [
        signature
        for signature in node.get("signatures", [])
        if isinstance(signature, dict) and not comment_has_internal_tag(signature.get("comment"))
    ]
    if summary is None and public_signatures:
        summary = render_comment_inline((public_signatures[0].get("comment") or {}).get("summary"))

    signature = ""
    if group_title == "Interfaces":
        type_parameters = node.get("typeParameters") if isinstance(node.get("typeParameters"), list) else []
        type_param_text = ""
        if type_parameters:
            type_param_text = "<" + ", ".join(type_parameter_text(item) for item in type_parameters if isinstance(item, dict)) + ">"
        extends = node.get("extendedTypes") if isinstance(node.get("extendedTypes"), list) else []
        extends_text = ""
        if extends:
            extends_text = " extends " + ", ".join(render_type(item) for item in extends if isinstance(item, dict))
        signature = f"interface {name}{type_param_text}{extends_text}"
    elif group_title == "Type Aliases":
        type_parameters = node.get("typeParameters") if isinstance(node.get("typeParameters"), list) else []
        type_param_text = ""
        if type_parameters:
            type_param_text = "<" + ", ".join(type_parameter_text(item) for item in type_parameters if isinstance(item, dict)) + ">"
        rendered_type = render_type(node.get("type"))
        if not node.get("type") and children:
            rendered_type = "{ " + "; ".join(render_property_shape(child) for child in children) + " }"
        signature = f"type {name}{type_param_text} = {rendered_type}"
    elif group_title == "Variables":
        signature = f"const {name}: {render_type(node.get('type'))}"
    elif group_title == "Functions" and public_signatures:
        signature = render_signature(public_signatures[0])

    source_location = ""
    sources = node.get("sources")
    if isinstance(sources, list) and sources:
        first = sources[0]
        if isinstance(first, dict):
            file_name = first.get("fileName")
            line = first.get("line")
            if file_name and line:
                source_location = f"{file_name}:{line}"
            elif file_name:
                source_location = str(file_name)

    export_comment = node.get("comment") if isinstance(node.get("comment"), dict) else None
    lifecycle_comment = export_comment
    if lifecycle_comment is None and public_signatures:
        lifecycle_comment = public_signatures[0].get("comment") if isinstance(public_signatures[0].get("comment"), dict) else None
    lifecycle_state = normalize_lifecycle_state(lifecycle_comment)
    deprecated_text = extract_first_block_tag_text(lifecycle_comment, "@deprecated") if lifecycle_state == "deprecated" else None
    replaces = extract_first_block_tag_text(lifecycle_comment, "@replaces")
    type_parameter_docs = extract_type_parameter_docs(node, fallback_comment=export_comment)
    signature_docs = extract_signature_docs(public_signatures)
    fingerprint = json.dumps(
        {
            "group": group_title,
            "name": name,
            "doc": normalize_for_fingerprint(node),
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    return {
        "key": f"{group_title}::{name}",
        "name": name,
        "group": group_title,
        "kind_label": kind_label,
        "anchor": anchor_for_export(group_title, name),
        "summary": summary or "",
        "signature": signature,
        "signature_docs": signature_docs,
        "type_parameters": type_parameter_docs,
        "members": build_member_docs(children),
        "source_location": source_location,
        "lifecycle_state": lifecycle_state,
        "lifecycle_label": lifecycle_state_label(lifecycle_state) if lifecycle_state else "",
        "deprecated_text": deprecated_text or "",
        "replaces": replaces or "",
        "sort_group_index": group_index,
        "sort_item_index": item_index,
        "fingerprint": fingerprint,
    }


def collect_snapshot_exports(document: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    group_titles: list[str] = []
    group_indices: dict[str, int] = {}
    child_group: dict[int, tuple[str, int, int]] = {}
    groups = document.get("groups")
    if isinstance(groups, list):
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            title = str(group.get("title", "")).strip()
            if not title:
                continue
            group_titles.append(title)
            group_indices[title] = group_index
            for item_index, child_id in enumerate(group.get("children", [])):
                if isinstance(child_id, int):
                    child_group[child_id] = (title, group_index, item_index)

    exports: dict[str, dict[str, Any]] = {}
    for fallback_index, child in enumerate(document.get("children", [])):
        if not isinstance(child, dict) or is_internal_node(child):
            continue
        child_id = child.get("id")
        group_title, group_index, item_index = child_group.get(child_id, ("Other Exports", len(group_titles), fallback_index))
        if group_title not in group_indices and group_title != "Other Exports":
            group_titles.append(group_title)
            group_indices[group_title] = group_index
        export_doc = build_export_doc(group_title, child, group_index=group_index, item_index=item_index)
        exports[export_doc["key"]] = export_doc
    return group_titles, exports


def build_typedoc_report_from_sources(
    sources: TypeDocSources,
    *,
    source_name: str,
    version_filter: str,
    publish_version: str | None = None,
) -> TypeDocReport:
    ordered_snapshots = sorted(sources.snapshots, key=lambda snapshot: version_sort_key(snapshot.version))
    selected_publish_version = publish_version or sources.publish_version or ordered_snapshots[-1].version
    ordered_versions = [snapshot.version for snapshot in ordered_snapshots]
    if selected_publish_version not in ordered_versions:
        raise ValueError(
            f"Publish version '{selected_publish_version}' is not present in selected snapshots: {ordered_versions}"
        )

    publish_index = ordered_versions.index(selected_publish_version)
    scoped_snapshots = ordered_snapshots[: publish_index + 1]

    snapshot_groups: dict[str, list[str]] = {}
    snapshot_exports: dict[str, dict[str, dict[str, Any]]] = {}
    for snapshot in scoped_snapshots:
        groups, exports = collect_snapshot_exports(snapshot.document)
        snapshot_groups[snapshot.version] = groups
        snapshot_exports[snapshot.version] = exports

    export_history: dict[str, dict[str, Any]] = {}
    for snapshot in scoped_snapshots:
        current_exports = snapshot_exports[snapshot.version]
        for key, export_doc in current_exports.items():
            history = export_history.setdefault(
                key,
                {
                    "versions": [],
                    "docs": {},
                    "fingerprints": {},
                    "changed_in": [],
                    "change_details": [],
                },
            )
            history["versions"].append(snapshot.version)
            history["docs"][snapshot.version] = export_doc
            previous_version = history["versions"][-2] if len(history["versions"]) > 1 else None
            if previous_version is not None:
                previous_fingerprint = history["fingerprints"].get(previous_version)
                if previous_fingerprint != export_doc["fingerprint"]:
                    changes = describe_export_changes(history["docs"][previous_version], export_doc)
                    history["changed_in"].append(snapshot.version)
                    history["change_details"].append(
                        {
                            "version": snapshot.version,
                            "changes": changes or ["details updated"],
                        }
                    )
            history["fingerprints"][snapshot.version] = export_doc["fingerprint"]

    publish_exports = snapshot_exports[selected_publish_version]
    merged_exports: list[dict[str, Any]] = []
    publish_keys: set[str] = set()
    for key, export_doc in publish_exports.items():
        merged = dict(export_doc)
        history = export_history[key]
        merged.update(
            {
                "introduced_in": history["versions"][0],
                "changed_in": list(history["changed_in"]),
                "change_details": list(history["change_details"]),
                "removed_in": None,
                "last_seen_in": history["versions"][-1],
                "status": "active",
            }
        )
        merged_exports.append(merged)
        publish_keys.add(key)

    for key, history in export_history.items():
        if key in publish_keys:
            continue
        last_seen_in = history["versions"][-1]
        last_seen_index = ordered_versions.index(last_seen_in)
        removed_in = None
        for candidate in ordered_versions[last_seen_index + 1 : publish_index + 1]:
            if candidate not in history["versions"]:
                removed_in = candidate
                break
        merged = dict(history["docs"][last_seen_in])
        merged.update(
            {
                "introduced_in": history["versions"][0],
                "changed_in": list(history["changed_in"]),
                "change_details": list(history["change_details"]),
                "removed_in": removed_in,
                "last_seen_in": last_seen_in,
                "status": "removed",
            }
        )
        merged_exports.append(merged)

    publish_groups = list(snapshot_groups[selected_publish_version])
    for export in merged_exports:
        if export["group"] not in publish_groups:
            publish_groups.append(export["group"])

    group_order = {group: index for index, group in enumerate(publish_groups)}
    merged_exports.sort(
        key=lambda export: (
            group_order.get(export["group"], len(group_order)),
            1 if export["status"] == "removed" else 0,
            export["sort_item_index"],
            export["name"].lower(),
            export["kind_label"].lower(),
        )
    )

    package_name = sources.package_name or str(scoped_snapshots[-1].document.get("packageName") or scoped_snapshots[-1].document.get("name") or "@daml/types")

    return TypeDocReport(
        source_name=source_name,
        version_filter=version_filter,
        package_name=package_name,
        publish_version=selected_publish_version,
        versions=[snapshot.version for snapshot in scoped_snapshots],
        export_groups=publish_groups,
        exports=merged_exports,
    )

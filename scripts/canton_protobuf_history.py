#!/usr/bin/env python3

# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Generate a descriptor-backed JSON manifest and consolidated MDX page for Canton protobuf history.

This script treats stable Canton release tags (`vX.Y.Z`) as the version axis for protobuf history.
It clones Canton on demand, reads each release tag's checked-in descriptor image with source info,
extracts a normalized schema graph, merges optional metadata overlays, computes release diffs, and
renders a single MDX page that combines the latest schema details with release-by-release history.

Runtime dependencies:
- protobuf

Example:
  python3 scripts/canton_protobuf_history.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from google.protobuf import descriptor_pb2
    from google.protobuf.json_format import MessageToDict
except ImportError as exc:  # pragma: no cover - handled at runtime
    IMPORT_ERROR: Exception | None = exc
    descriptor_pb2 = None  # type: ignore[assignment]
    MessageToDict = None  # type: ignore[assignment]
else:
    IMPORT_ERROR = None


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs-main" / "appdev" / "reference" / "protobuf-history"
DEFAULT_WORKDIR = REPO_ROOT / ".cache" / "protobuf-history"
DEFAULT_METADATA_FILE = REPO_ROOT / "scripts" / "protobuf_history_metadata.json"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs.json"
DEFAULT_CANTON_REPO_DIR = DEFAULT_WORKDIR / "repos" / "canton"
DEFAULT_CANTON_REPO_URL = "https://github.com/DACH-NY/canton.git"
DESCRIPTOR_IMAGE_NAME = ".proto_snapshot_image.bin.gz"
MIN_CANTON_VERSION = (3, 2, 0)
ENDPOINT_PAGE_SUBDIR = "endpoints"

STABLE_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
OWNED_PROTO_RE = re.compile(r"^community/.+/src/main/protobuf/.+\.proto$")

FILE_MESSAGE_FIELD_NUMBER = 4
FILE_ENUM_FIELD_NUMBER = 5
FILE_SERVICE_FIELD_NUMBER = 6
MESSAGE_FIELD_FIELD_NUMBER = 2
MESSAGE_NESTED_FIELD_NUMBER = 3
MESSAGE_ENUM_FIELD_NUMBER = 4
MESSAGE_ONEOF_FIELD_NUMBER = 8
ENUM_VALUE_FIELD_NUMBER = 2
SERVICE_METHOD_FIELD_NUMBER = 2

DEFAULT_METADATA_SHAPE = {
    "schemaVersion": 1,
    "files": {},
    "services": {},
    "endpoints": {},
    "messages": {},
    "fields": {},
    "enums": {},
    "enumValues": {},
}

SCALAR_TYPE_NAMES: dict[int, str] = {}
LABEL_NAMES: dict[int, str] = {}


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
) -> str:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd else None,
        "check": True,
        "text": True,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    completed = subprocess.run(args, **kwargs)
    if capture:
        return completed.stdout.strip()
    return ""


def run_bytes(args: list[str], *, cwd: Path | None = None) -> bytes:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def git(args: list[str], *, cwd: Path, capture: bool = False) -> str:
    return run(["git", *args], cwd=cwd, capture=capture)


def git_bytes(args: list[str], *, cwd: Path) -> bytes:
    return run_bytes(["git", *args], cwd=cwd)


def ensure_runtime_dependencies() -> None:
    if IMPORT_ERROR is not None:
        raise RuntimeError(
            "Missing runtime dependency for descriptor parsing. Enter the repo's direnv/nix shell first:\n"
            "  direnv allow\n"
            "or run via nix-shell:\n"
            "  nix-shell --run 'python3 scripts/canton_protobuf_history.py'"
        ) from IMPORT_ERROR


def ensure_descriptor_constants() -> None:
    ensure_runtime_dependencies()
    if SCALAR_TYPE_NAMES:
        return
    for enum_value in descriptor_pb2.FieldDescriptorProto.Type.values():
        name = descriptor_pb2.FieldDescriptorProto.Type.Name(enum_value)
        if name.startswith("TYPE_"):
            SCALAR_TYPE_NAMES[enum_value] = name.removeprefix("TYPE_").lower()
    for enum_value in descriptor_pb2.FieldDescriptorProto.Label.values():
        name = descriptor_pb2.FieldDescriptorProto.Label.Name(enum_value)
        if name.startswith("LABEL_"):
            LABEL_NAMES[enum_value] = name.removeprefix("LABEL_").lower()


def parse_repo_slug(repo: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        return repo
    match = re.search(r"github\.com[:/]+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$", repo)
    if match:
        return match.group(1)
    raise ValueError(f"Unable to parse GitHub repo slug from '{repo}'")


def normalize_remote_to_web_url(remote: str) -> str:
    slug = parse_repo_slug(remote)
    return f"https://github.com/{slug}"


def safe_relative_to(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def is_git_repo(repo_dir: Path) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "--git-dir"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.returncode == 0


def ensure_canton_repo(
    repo_dir: Path,
    *,
    repo_url: str,
    fetch: bool,
) -> Path:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        run(["git", "clone", "--bare", repo_url, str(repo_dir)])
    elif not is_git_repo(repo_dir):
        raise RuntimeError(f"Expected a git repository at {repo_dir}")

    if fetch:
        git(["fetch", "origin", "--tags", "--prune"], cwd=repo_dir)
    return repo_dir


def semver_key(tag: str) -> tuple[int, int, int]:
    match = STABLE_TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError(f"Not a stable semver tag: {tag}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def format_semver(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def to_release_line(tag: str) -> str:
    major, minor, _patch = semver_key(tag)
    return f"{major}.{minor}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_leading_dot(value: str) -> str:
    return value[1:] if value.startswith(".") else value


def join_full_name(package: str, parts: list[str]) -> str:
    return ".".join([p for p in [package, *parts] if p])


def escape_md(text: str) -> str:
    return text.replace("|", r"\|")


def escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_md_cell(text: str) -> str:
    return escape_text(escape_md(text)).replace("\n", "<br/>")


def md_link(label: str, url: str | None) -> str:
    if not url:
        return label
    return f"[{label}]({url})"


def slugify_segment(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "item"


def normalize_comment(raw: str) -> str:
    lines = [line.rstrip() for line in raw.strip("\n").splitlines()]
    return "\n".join(lines).strip()


def render_description(text: str) -> str:
    return escape_text(text.strip()) if text.strip() else "_No description._"


def render_list(items: list[str], *, prefix: str = "- ") -> str:
    if not items:
        return f"{prefix}None"
    return "\n".join(f"{prefix}{item}" for item in items)


def render_limited_list(items: list[Any], *, formatter, limit: int = 25) -> list[str]:
    if not items:
        return ["- None"]
    shown = items[:limit]
    lines = [f"- {formatter(item)}" for item in shown]
    remaining = len(items) - len(shown)
    if remaining > 0:
        lines.append(f"- ... {remaining} more")
    return lines


def load_metadata_overlay(path: Path) -> dict[str, Any]:
    data = json.loads(json.dumps(DEFAULT_METADATA_SHAPE))
    if not path.exists():
        return data
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in data:
        if key == "schemaVersion":
            data[key] = raw.get(key, data[key])
        else:
            value = raw.get(key, {})
            if isinstance(value, dict):
                data[key] = value
    return data


def metadata_for(overlay: dict[str, Any], kind: str, entity_id: str) -> dict[str, Any]:
    value = overlay.get(kind, {}).get(entity_id, {})
    return value if isinstance(value, dict) else {}


def repo_path_to_import_path(rel_path: str) -> str:
    marker = "/src/main/protobuf/"
    if marker not in rel_path:
        raise ValueError(f"Unable to derive import path from '{rel_path}'")
    return rel_path.split(marker, 1)[1]


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_stable_tags(repo_dir: Path) -> list[dict[str, Any]]:
    tags_raw = git(["tag", "--list", "v*"], cwd=repo_dir, capture=True)
    selected: list[str] = []
    for line in tags_raw.splitlines():
        tag = line.strip()
        match = STABLE_TAG_RE.fullmatch(tag)
        if not match:
            continue
        if semver_key(tag) < MIN_CANTON_VERSION:
            continue
        selected.append(tag)
    selected.sort(key=semver_key)

    releases: list[dict[str, Any]] = []
    for tag in selected:
        date = git(
            ["for-each-ref", "--format=%(creatordate:short)", f"refs/tags/{tag}"],
            cwd=repo_dir,
            capture=True,
        )
        releases.append(
            {
                "tag": tag,
                "version": tag.removeprefix("v"),
                "releaseLine": to_release_line(tag),
                "date": date,
            }
        )
    return releases


def list_owned_proto_paths(repo_dir: Path, tag: str) -> list[str]:
    tree = git(["ls-tree", "-r", "--name-only", tag, "community"], cwd=repo_dir, capture=True)
    return sorted(
        line.strip()
        for line in tree.splitlines()
        if OWNED_PROTO_RE.fullmatch(line.strip()) and "/target/" not in line
    )


def materialize_tag_protos(
    repo_dir: Path,
    *,
    tag: str,
    snapshot_dir: Path,
    refresh: bool,
) -> list[str]:
    owned_paths = list_owned_proto_paths(repo_dir, tag)
    meta_path = snapshot_dir / ".snapshot.json"
    if snapshot_dir.exists() and meta_path.exists() and not refresh:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if metadata.get("tag") == tag and metadata.get("files") == owned_paths:
            return owned_paths

    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for rel_path in owned_paths:
        text = git(["show", f"{tag}:{rel_path}"], cwd=repo_dir, capture=True)
        if not text.endswith("\n"):
            text += "\n"
        write_text_file(snapshot_dir / rel_path, text)

    meta_path.write_text(
        json.dumps({"tag": tag, "files": owned_paths}, indent=2) + "\n",
        encoding="utf-8",
    )
    return owned_paths


def descriptor_cache_path(snapshot_dir: Path) -> Path:
    return snapshot_dir / ".descriptor-set.pb"


def descriptor_image_cache_path(snapshot_dir: Path) -> Path:
    return snapshot_dir / DESCRIPTOR_IMAGE_NAME


def load_descriptor_set_from_image(
    repo_dir: Path,
    *,
    tag: str,
    snapshot_dir: Path,
    refresh: bool,
) -> Any:
    ensure_runtime_dependencies()
    image_path = descriptor_image_cache_path(snapshot_dir)
    descriptor_path = descriptor_cache_path(snapshot_dir)

    if not image_path.exists() or refresh:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        image_bytes = git_bytes(["show", f"{tag}:{DESCRIPTOR_IMAGE_NAME}"], cwd=repo_dir)
        image_path.write_bytes(image_bytes)

    if descriptor_path.exists() and not refresh:
        descriptor_set = descriptor_pb2.FileDescriptorSet()
        descriptor_set.ParseFromString(descriptor_path.read_bytes())
        return descriptor_set

    raw = gzip.decompress(image_path.read_bytes())
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    descriptor_set.ParseFromString(raw)
    descriptor_path.write_bytes(raw)
    return descriptor_set


def build_location_map(file_proto: Any) -> dict[tuple[int, ...], Any]:
    return {tuple(location.path): location for location in file_proto.source_code_info.location}


def location_comment(location: Any | None) -> str:
    if location is None:
        return ""
    parts: list[str] = []
    for detached in location.leading_detached_comments:
        normalized = normalize_comment(detached)
        if normalized:
            parts.append(normalized)
    if location.leading_comments:
        normalized = normalize_comment(location.leading_comments)
        if normalized:
            parts.append(normalized)
    elif location.trailing_comments:
        normalized = normalize_comment(location.trailing_comments)
        if normalized:
            parts.append(normalized)
    return "\n\n".join(parts).strip()


def location_line(location: Any | None) -> int | None:
    if location is None or not location.span:
        return None
    return location.span[0] + 1


def comment_and_line(location_map: dict[tuple[int, ...], Any], path: tuple[int, ...]) -> tuple[str, int | None]:
    location = location_map.get(path)
    return location_comment(location), location_line(location)


def source_url(repo_web_url: str, tag: str, repo_path: str, line: int | None) -> str:
    base = f"{repo_web_url}/blob/{tag}/{repo_path}"
    if line is not None:
        return f"{base}#L{line}"
    return base


def options_dict(options_message: Any) -> dict[str, Any]:
    ensure_runtime_dependencies()
    if not options_message.ListFields():
        return {}
    return MessageToDict(
        options_message,
        preserving_proto_field_name=True,
        use_integers_for_enums=False,
    )


def collect_type_indexes(descriptor_set: Any) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    message_index: dict[str, dict[str, Any]] = {}
    enum_index: dict[str, dict[str, Any]] = {}

    def walk_enum(file_proto: Any, package: str, enum_proto: Any, path: tuple[int, ...], parents: list[str]) -> None:
        full_name = join_full_name(package, parents + [enum_proto.name])
        enum_index[full_name] = {
            "descriptor": enum_proto,
            "file": file_proto,
            "path": path,
        }

    def walk_message(
        file_proto: Any,
        package: str,
        message_proto: Any,
        path: tuple[int, ...],
        parents: list[str],
    ) -> None:
        full_name = join_full_name(package, parents + [message_proto.name])
        message_index[full_name] = {
            "descriptor": message_proto,
            "file": file_proto,
            "path": path,
            "mapEntry": bool(message_proto.options.map_entry),
        }
        child_parents = parents + [message_proto.name]
        for idx, nested in enumerate(message_proto.nested_type):
            walk_message(
                file_proto,
                package,
                nested,
                path + (MESSAGE_NESTED_FIELD_NUMBER, idx),
                child_parents,
            )
        for idx, enum_proto in enumerate(message_proto.enum_type):
            walk_enum(
                file_proto,
                package,
                enum_proto,
                path + (MESSAGE_ENUM_FIELD_NUMBER, idx),
                child_parents,
            )

    for file_proto in descriptor_set.file:
        package = file_proto.package
        for idx, message_proto in enumerate(file_proto.message_type):
            walk_message(file_proto, package, message_proto, (FILE_MESSAGE_FIELD_NUMBER, idx), [])
        for idx, enum_proto in enumerate(file_proto.enum_type):
            walk_enum(file_proto, package, enum_proto, (FILE_ENUM_FIELD_NUMBER, idx), [])

    return message_index, enum_index


class DescriptorSnapshotBuilder:
    def __init__(
        self,
        *,
        tag: str,
        repo_web_url: str,
        snapshot_dir: Path,
        descriptor_set: Any,
        import_to_repo_path: dict[str, str],
        metadata_overlay: dict[str, Any],
    ) -> None:
        ensure_descriptor_constants()
        self.tag = tag
        self.repo_web_url = repo_web_url
        self.snapshot_dir = snapshot_dir
        self.descriptor_set = descriptor_set
        self.import_to_repo_path = import_to_repo_path
        self.owned_import_paths = set(import_to_repo_path)
        self.metadata_overlay = metadata_overlay
        self.location_maps = {file_proto.name: build_location_map(file_proto) for file_proto in descriptor_set.file}
        self.file_by_import = {file_proto.name: file_proto for file_proto in descriptor_set.file}
        self.message_index, self.enum_index = collect_type_indexes(descriptor_set)

        self.files: dict[str, dict[str, Any]] = {}
        self.services: dict[str, dict[str, Any]] = {}
        self.endpoints: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, dict[str, Any]] = {}
        self.fields: dict[str, dict[str, Any]] = {}
        self.enums: dict[str, dict[str, Any]] = {}
        self.enum_values: dict[str, dict[str, Any]] = {}

    def metadata(self, kind: str, entity_id: str) -> dict[str, Any]:
        return metadata_for(self.metadata_overlay, kind, entity_id)

    def repo_path(self, import_path: str) -> str:
        return self.import_to_repo_path[import_path]

    def file_source_url(self, import_path: str, line: int | None) -> str:
        return source_url(self.repo_web_url, self.tag, self.repo_path(import_path), line)

    def file_locmap(self, import_path: str) -> dict[tuple[int, ...], Any]:
        return self.location_maps[import_path]

    def message_full_name(self, file_proto: Any, parent_message_id: str | None, name: str) -> str:
        if parent_message_id:
            return f"{parent_message_id}.{name}"
        return join_full_name(file_proto.package, [name])

    def enum_full_name(self, file_proto: Any, parent_message_id: str | None, name: str) -> str:
        if parent_message_id:
            return f"{parent_message_id}.{name}"
        return join_full_name(file_proto.package, [name])

    def real_oneof_indexes(self, message_proto: Any) -> set[int]:
        field_indexes_by_oneof: dict[int, list[int]] = defaultdict(list)
        for idx, field in enumerate(message_proto.field):
            if field.HasField("oneof_index"):
                field_indexes_by_oneof[field.oneof_index].append(idx)

        real_indexes: set[int] = set()
        for oneof_idx, _oneof in enumerate(message_proto.oneof_decl):
            field_indexes = field_indexes_by_oneof.get(oneof_idx, [])
            if len(field_indexes) == 1 and message_proto.field[field_indexes[0]].proto3_optional:
                continue
            real_indexes.add(oneof_idx)
        return real_indexes

    def resolve_type_ref(self, field_proto: Any) -> dict[str, Any]:
        type_name = strip_leading_dot(field_proto.type_name)
        if field_proto.type == descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE:
            entry = self.message_index.get(type_name)
            if entry and entry["mapEntry"]:
                map_descriptor = entry["descriptor"]
                key_info = self.resolve_type_ref(map_descriptor.field[0])
                value_info = self.resolve_type_ref(map_descriptor.field[1])
                return {
                    "kind": "map",
                    "displayType": f"map<{key_info['displayType']}, {value_info['displayType']}>",
                    "fullName": type_name,
                    "keyType": key_info["displayType"],
                    "valueType": value_info["displayType"],
                }
            return {
                "kind": "message",
                "displayType": type_name,
                "fullName": type_name,
            }
        if field_proto.type == descriptor_pb2.FieldDescriptorProto.TYPE_ENUM:
            return {
                "kind": "enum",
                "displayType": type_name,
                "fullName": type_name,
            }
        return {
            "kind": "scalar",
            "displayType": SCALAR_TYPE_NAMES.get(field_proto.type, str(field_proto.type).lower()),
            "fullName": None,
        }

    def build_field_shape(self, field_doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "number": field_doc["number"],
            "name": field_doc["name"],
            "jsonName": field_doc["jsonName"],
            "label": field_doc["label"],
            "type": field_doc["type"],
            "typeKind": field_doc["typeKind"],
            "typeName": field_doc["typeName"],
            "oneof": field_doc["oneof"],
            "map": field_doc["map"],
            "keyType": field_doc["keyType"],
            "valueType": field_doc["valueType"],
            "proto3Optional": field_doc["proto3Optional"],
            "defaultValue": field_doc["defaultValue"],
        }

    def build_enum_value_shape(self, enum_value_doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": enum_value_doc["name"],
            "number": enum_value_doc["number"],
        }

    def build_field(
        self,
        *,
        file_proto: Any,
        message_proto: Any,
        message_full_name: str,
        message_path: tuple[int, ...],
        field_idx: int,
        real_oneof_indexes: set[int],
    ) -> dict[str, Any]:
        locmap = self.file_locmap(file_proto.name)
        path = message_path + (MESSAGE_FIELD_FIELD_NUMBER, field_idx)
        description, line = comment_and_line(locmap, path)
        field_proto = message_proto.field[field_idx]
        field_id = f"{message_full_name}#{field_proto.name}"
        resolved = self.resolve_type_ref(field_proto)
        oneof_name = None
        if field_proto.HasField("oneof_index") and field_proto.oneof_index in real_oneof_indexes:
            oneof_name = message_proto.oneof_decl[field_proto.oneof_index].name

        field_doc = {
            "id": field_id,
            "name": field_proto.name,
            "fullName": field_id,
            "package": file_proto.package,
            "messageId": message_full_name,
            "file": self.repo_path(file_proto.name),
            "importPath": file_proto.name,
            "number": field_proto.number,
            "label": LABEL_NAMES.get(field_proto.label, str(field_proto.label).lower()),
            "jsonName": field_proto.json_name,
            "type": resolved["displayType"],
            "typeKind": resolved["kind"],
            "typeName": resolved["fullName"],
            "map": resolved["kind"] == "map",
            "keyType": resolved.get("keyType"),
            "valueType": resolved.get("valueType"),
            "oneof": oneof_name,
            "proto3Optional": bool(field_proto.proto3_optional),
            "defaultValue": field_proto.default_value or None,
            "description": description,
            "line": line,
            "sourceUrl": self.file_source_url(file_proto.name, line),
            "metadata": self.metadata("fields", field_id),
            "options": options_dict(field_proto.options),
        }
        self.fields[field_id] = field_doc
        return field_doc

    def build_enum_value(
        self,
        *,
        file_proto: Any,
        enum_full_name: str,
        enum_path: tuple[int, ...],
        value_idx: int,
        value_proto: Any,
    ) -> dict[str, Any]:
        locmap = self.file_locmap(file_proto.name)
        path = enum_path + (ENUM_VALUE_FIELD_NUMBER, value_idx)
        description, line = comment_and_line(locmap, path)
        value_id = f"{enum_full_name}#{value_proto.name}"
        value_doc = {
            "id": value_id,
            "name": value_proto.name,
            "fullName": value_id,
            "package": file_proto.package,
            "enumId": enum_full_name,
            "file": self.repo_path(file_proto.name),
            "importPath": file_proto.name,
            "number": value_proto.number,
            "description": description,
            "line": line,
            "sourceUrl": self.file_source_url(file_proto.name, line),
            "metadata": self.metadata("enumValues", value_id),
        }
        self.enum_values[value_id] = value_doc
        return value_doc

    def build_enum(
        self,
        *,
        file_proto: Any,
        enum_proto: Any,
        enum_path: tuple[int, ...],
        parent_message_id: str | None,
    ) -> dict[str, Any]:
        locmap = self.file_locmap(file_proto.name)
        description, line = comment_and_line(locmap, enum_path)
        enum_full_name = self.enum_full_name(file_proto, parent_message_id, enum_proto.name)
        values: list[dict[str, Any]] = []
        for value_idx, value_proto in enumerate(enum_proto.value):
            values.append(
                self.build_enum_value(
                    file_proto=file_proto,
                    enum_full_name=enum_full_name,
                    enum_path=enum_path,
                    value_idx=value_idx,
                    value_proto=value_proto,
                )
            )

        enum_doc = {
            "id": enum_full_name,
            "name": enum_proto.name,
            "fullName": enum_full_name,
            "package": file_proto.package,
            "file": self.repo_path(file_proto.name),
            "importPath": file_proto.name,
            "parentMessageId": parent_message_id,
            "description": description,
            "line": line,
            "sourceUrl": self.file_source_url(file_proto.name, line),
            "metadata": self.metadata("enums", enum_full_name),
            "options": options_dict(enum_proto.options),
            "valueIds": [value["id"] for value in values],
            "valueShape": [self.build_enum_value_shape(value) for value in values],
            "reservedRanges": [
                {"start": reserved.start, "end": reserved.end}
                for reserved in enum_proto.reserved_range
            ],
            "reservedNames": list(enum_proto.reserved_name),
        }
        self.enums[enum_full_name] = enum_doc
        return enum_doc

    def build_message(
        self,
        *,
        file_proto: Any,
        message_proto: Any,
        message_path: tuple[int, ...],
        parent_message_id: str | None,
    ) -> dict[str, Any]:
        locmap = self.file_locmap(file_proto.name)
        description, line = comment_and_line(locmap, message_path)
        message_full_name = self.message_full_name(file_proto, parent_message_id, message_proto.name)
        real_oneof_indexes = self.real_oneof_indexes(message_proto)

        fields: list[dict[str, Any]] = []
        for field_idx, _field_proto in enumerate(message_proto.field):
            fields.append(
                self.build_field(
                    file_proto=file_proto,
                    message_proto=message_proto,
                    message_full_name=message_full_name,
                    message_path=message_path,
                    field_idx=field_idx,
                    real_oneof_indexes=real_oneof_indexes,
                )
            )

        oneofs: list[dict[str, Any]] = []
        for oneof_idx, oneof_proto in enumerate(message_proto.oneof_decl):
            if oneof_idx not in real_oneof_indexes:
                continue
            oneof_path = message_path + (MESSAGE_ONEOF_FIELD_NUMBER, oneof_idx)
            oneof_description, oneof_line = comment_and_line(locmap, oneof_path)
            member_ids = [
                field["id"]
                for field in fields
                if field["oneof"] == oneof_proto.name
            ]
            oneofs.append(
                {
                    "name": oneof_proto.name,
                    "description": oneof_description,
                    "line": oneof_line,
                    "fieldIds": member_ids,
                }
            )

        nested_message_ids: list[str] = []
        for nested_idx, nested_proto in enumerate(message_proto.nested_type):
            if nested_proto.options.map_entry:
                continue
            nested_doc = self.build_message(
                file_proto=file_proto,
                message_proto=nested_proto,
                message_path=message_path + (MESSAGE_NESTED_FIELD_NUMBER, nested_idx),
                parent_message_id=message_full_name,
            )
            nested_message_ids.append(nested_doc["id"])

        enum_ids: list[str] = []
        for enum_idx, enum_proto in enumerate(message_proto.enum_type):
            enum_doc = self.build_enum(
                file_proto=file_proto,
                enum_proto=enum_proto,
                enum_path=message_path + (MESSAGE_ENUM_FIELD_NUMBER, enum_idx),
                parent_message_id=message_full_name,
            )
            enum_ids.append(enum_doc["id"])

        message_doc = {
            "id": message_full_name,
            "name": message_proto.name,
            "fullName": message_full_name,
            "package": file_proto.package,
            "file": self.repo_path(file_proto.name),
            "importPath": file_proto.name,
            "parentMessageId": parent_message_id,
            "description": description,
            "line": line,
            "sourceUrl": self.file_source_url(file_proto.name, line),
            "metadata": self.metadata("messages", message_full_name),
            "options": options_dict(message_proto.options),
            "fieldIds": [field["id"] for field in fields],
            "fieldShape": [self.build_field_shape(field) for field in fields],
            "oneofs": oneofs,
            "nestedMessageIds": nested_message_ids,
            "enumIds": enum_ids,
            "reservedRanges": [
                {"start": reserved.start, "end": reserved.end}
                for reserved in message_proto.reserved_range
            ],
            "reservedNames": list(message_proto.reserved_name),
        }
        self.messages[message_full_name] = message_doc
        return message_doc

    def build_method(
        self,
        *,
        file_proto: Any,
        service_doc: dict[str, Any],
        service_idx: int,
        method_idx: int,
        method_proto: Any,
    ) -> dict[str, Any]:
        locmap = self.file_locmap(file_proto.name)
        path = (FILE_SERVICE_FIELD_NUMBER, service_idx, SERVICE_METHOD_FIELD_NUMBER, method_idx)
        description, line = comment_and_line(locmap, path)
        endpoint_id = f"{service_doc['id']}/{method_proto.name}"
        endpoint_doc = {
            "id": endpoint_id,
            "name": method_proto.name,
            "package": file_proto.package,
            "service": service_doc["name"],
            "serviceFullName": service_doc["fullName"],
            "file": self.repo_path(file_proto.name),
            "importPath": file_proto.name,
            "description": description,
            "line": line,
            "sourceUrl": self.file_source_url(file_proto.name, line),
            "metadata": self.metadata("endpoints", endpoint_id),
            "options": options_dict(method_proto.options),
            "requestType": strip_leading_dot(method_proto.input_type),
            "responseType": strip_leading_dot(method_proto.output_type),
            "clientStreaming": bool(method_proto.client_streaming),
            "serverStreaming": bool(method_proto.server_streaming),
        }
        self.endpoints[endpoint_id] = endpoint_doc
        return endpoint_doc

    def build_service(self, *, file_proto: Any, service_idx: int, service_proto: Any) -> dict[str, Any]:
        locmap = self.file_locmap(file_proto.name)
        path = (FILE_SERVICE_FIELD_NUMBER, service_idx)
        description, line = comment_and_line(locmap, path)
        service_full_name = join_full_name(file_proto.package, [service_proto.name])
        service_doc = {
            "id": service_full_name,
            "name": service_proto.name,
            "fullName": service_full_name,
            "package": file_proto.package,
            "file": self.repo_path(file_proto.name),
            "importPath": file_proto.name,
            "description": description,
            "line": line,
            "sourceUrl": self.file_source_url(file_proto.name, line),
            "metadata": self.metadata("services", service_full_name),
            "options": options_dict(service_proto.options),
            "endpointIds": [],
        }
        self.services[service_full_name] = service_doc

        endpoint_ids: list[str] = []
        for method_idx, method_proto in enumerate(service_proto.method):
            endpoint_doc = self.build_method(
                file_proto=file_proto,
                service_doc=service_doc,
                service_idx=service_idx,
                method_idx=method_idx,
                method_proto=method_proto,
            )
            endpoint_ids.append(endpoint_doc["id"])
        service_doc["endpointIds"] = endpoint_ids
        return service_doc

    def build_packages(self) -> list[dict[str, Any]]:
        package_map: dict[str, dict[str, Any]] = {}

        for file_doc in self.files.values():
            package = file_doc["package"] or "(no package)"
            bucket = package_map.setdefault(
                package,
                {
                    "package": package,
                    "fileIds": [],
                    "serviceIds": [],
                    "endpointIds": [],
                    "messageIds": [],
                    "fieldIds": [],
                    "enumIds": [],
                    "enumValueIds": [],
                },
            )
            bucket["fileIds"].append(file_doc["id"])

        for collection_name, source in (
            ("serviceIds", self.services),
            ("endpointIds", self.endpoints),
            ("messageIds", self.messages),
            ("fieldIds", self.fields),
            ("enumIds", self.enums),
            ("enumValueIds", self.enum_values),
        ):
            for entity in source.values():
                package = entity["package"] or "(no package)"
                bucket = package_map.setdefault(
                    package,
                    {
                        "package": package,
                        "fileIds": [],
                        "serviceIds": [],
                        "endpointIds": [],
                        "messageIds": [],
                        "fieldIds": [],
                        "enumIds": [],
                        "enumValueIds": [],
                    },
                )
                bucket[collection_name].append(entity["id"])

        packages: list[dict[str, Any]] = []
        for package_name in sorted(package_map):
            bucket = package_map[package_name]
            for key in bucket:
                if key.endswith("Ids"):
                    bucket[key] = sorted(bucket[key])
            packages.append(
                {
                    "package": package_name,
                    "fileIds": bucket["fileIds"],
                    "fileCount": len(bucket["fileIds"]),
                    "serviceIds": bucket["serviceIds"],
                    "serviceCount": len(bucket["serviceIds"]),
                    "endpointIds": bucket["endpointIds"],
                    "endpointCount": len(bucket["endpointIds"]),
                    "messageIds": bucket["messageIds"],
                    "messageCount": len(bucket["messageIds"]),
                    "fieldIds": bucket["fieldIds"],
                    "fieldCount": len(bucket["fieldIds"]),
                    "enumIds": bucket["enumIds"],
                    "enumCount": len(bucket["enumIds"]),
                    "enumValueIds": bucket["enumValueIds"],
                    "enumValueCount": len(bucket["enumValueIds"]),
                }
            )
        return packages

    def build(self) -> dict[str, Any]:
        for file_proto in self.descriptor_set.file:
            if file_proto.name not in self.owned_import_paths:
                continue

            locmap = self.file_locmap(file_proto.name)
            repo_path = self.repo_path(file_proto.name)
            description, line = comment_and_line(locmap, ())
            file_doc = {
                "id": repo_path,
                "importPath": file_proto.name,
                "repoPath": repo_path,
                "package": file_proto.package,
                "syntax": file_proto.syntax or "proto2",
                "description": description,
                "line": line,
                "sourceUrl": self.file_source_url(file_proto.name, line),
                "metadata": self.metadata("files", repo_path),
                "options": options_dict(file_proto.options),
                "dependencies": list(file_proto.dependency),
                "serviceIds": [],
                "messageIds": [],
                "enumIds": [],
                "declarations": [],
                "hash": sha256_text((self.snapshot_dir / repo_path).read_text(encoding="utf-8")),
            }

            declarations: list[dict[str, Any]] = []

            for idx, service_proto in enumerate(file_proto.service):
                service_doc = self.build_service(file_proto=file_proto, service_idx=idx, service_proto=service_proto)
                file_doc["serviceIds"].append(service_doc["id"])
                declarations.append({"kind": "service", "id": service_doc["id"], "line": service_doc["line"] or 0})

            for idx, message_proto in enumerate(file_proto.message_type):
                if message_proto.options.map_entry:
                    continue
                message_doc = self.build_message(
                    file_proto=file_proto,
                    message_proto=message_proto,
                    message_path=(FILE_MESSAGE_FIELD_NUMBER, idx),
                    parent_message_id=None,
                )
                file_doc["messageIds"].append(message_doc["id"])
                declarations.append({"kind": "message", "id": message_doc["id"], "line": message_doc["line"] or 0})

            for idx, enum_proto in enumerate(file_proto.enum_type):
                enum_doc = self.build_enum(
                    file_proto=file_proto,
                    enum_proto=enum_proto,
                    enum_path=(FILE_ENUM_FIELD_NUMBER, idx),
                    parent_message_id=None,
                )
                file_doc["enumIds"].append(enum_doc["id"])
                declarations.append({"kind": "enum", "id": enum_doc["id"], "line": enum_doc["line"] or 0})

            file_doc["declarations"] = sorted(
                declarations,
                key=lambda item: (item["line"], item["kind"], item["id"]),
            )
            self.files[repo_path] = file_doc

        packages = self.build_packages()
        return {
            "tag": self.tag,
            "snapshotDir": safe_relative_to(self.snapshot_dir, REPO_ROOT),
            "descriptorPath": safe_relative_to(descriptor_cache_path(self.snapshot_dir), REPO_ROOT),
            "files": self.files,
            "services": self.services,
            "endpoints": self.endpoints,
            "messages": self.messages,
            "fields": self.fields,
            "enums": self.enums,
            "enumValues": self.enum_values,
            "packages": packages,
            "stats": {
                "protoFiles": len(self.files),
                "packages": len(packages),
                "services": len(self.services),
                "endpoints": len(self.endpoints),
                "messages": len(self.messages),
                "fields": len(self.fields),
                "enums": len(self.enums),
                "enumValues": len(self.enum_values),
            },
        }


def build_snapshot(
    repo_dir: Path,
    *,
    tag: str,
    snapshot_dir: Path,
    repo_web_url: str,
    metadata_overlay: dict[str, Any],
    refresh_snapshots: bool,
    refresh_descriptors: bool,
) -> dict[str, Any]:
    owned_rel_paths = materialize_tag_protos(
        repo_dir,
        tag=tag,
        snapshot_dir=snapshot_dir,
        refresh=refresh_snapshots,
    )
    descriptor_set = load_descriptor_set_from_image(
        repo_dir,
        tag=tag,
        snapshot_dir=snapshot_dir,
        refresh=refresh_snapshots or refresh_descriptors,
    )
    import_to_repo_path = {repo_path_to_import_path(rel_path): rel_path for rel_path in owned_rel_paths}
    builder = DescriptorSnapshotBuilder(
        tag=tag,
        repo_web_url=repo_web_url,
        snapshot_dir=snapshot_dir,
        descriptor_set=descriptor_set,
        import_to_repo_path=import_to_repo_path,
        metadata_overlay=metadata_overlay,
    )
    return builder.build()


def entity_signature(entity: dict[str, Any], *, keys: tuple[str, ...]) -> str:
    return json.dumps({key: entity.get(key) for key in keys}, sort_keys=True, separators=(",", ":"))


def endpoint_signature(entity: dict[str, Any]) -> str:
    return entity_signature(
        entity,
        keys=("file", "requestType", "responseType", "clientStreaming", "serverStreaming"),
    )


def service_signature(entity: dict[str, Any]) -> str:
    return entity_signature(entity, keys=("file", "endpointIds"))


def message_signature(entity: dict[str, Any]) -> str:
    return entity_signature(
        entity,
        keys=("file", "fieldShape", "oneofs", "reservedRanges", "reservedNames"),
    )


def enum_signature(entity: dict[str, Any]) -> str:
    return entity_signature(entity, keys=("file", "valueShape", "reservedRanges", "reservedNames"))


def diff_file_maps(previous: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]]) -> dict[str, list[Any]]:
    previous_ids = set(previous)
    current_ids = set(current)
    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)
    modified = sorted(
        key for key in previous_ids & current_ids if previous[key]["hash"] != current[key]["hash"]
    )
    return {"added": added, "removed": removed, "modified": modified}


def diff_keyed_entities(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
    *,
    signature_fn,
    change_type_fn,
) -> dict[str, list[Any]]:
    previous_ids = set(previous)
    current_ids = set(current)
    added = [current[key] for key in sorted(current_ids - previous_ids)]
    removed = [previous[key] for key in sorted(previous_ids - current_ids)]
    modified: list[dict[str, Any]] = []
    for key in sorted(previous_ids & current_ids):
        prev_entity = previous[key]
        cur_entity = current[key]
        if signature_fn(prev_entity) == signature_fn(cur_entity):
            continue
        modified.append(
            {
                "id": key,
                "changeTypes": change_type_fn(prev_entity, cur_entity),
                "previous": prev_entity,
                "current": cur_entity,
            }
        )
    return {"added": added, "removed": removed, "modified": modified}


def endpoint_change_types(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    change_types: list[str] = []
    if previous["file"] != current["file"]:
        change_types.append("file")
    if previous["requestType"] != current["requestType"]:
        change_types.append("request_type")
    if previous["responseType"] != current["responseType"]:
        change_types.append("response_type")
    if previous["clientStreaming"] != current["clientStreaming"]:
        change_types.append("client_streaming")
    if previous["serverStreaming"] != current["serverStreaming"]:
        change_types.append("server_streaming")
    return change_types


def service_change_types(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    change_types: list[str] = []
    if previous["file"] != current["file"]:
        change_types.append("file")
    if previous["endpointIds"] != current["endpointIds"]:
        change_types.append("endpoints")
    return change_types


def message_change_types(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    change_types: list[str] = []
    if previous["file"] != current["file"]:
        change_types.append("file")
    if previous["fieldShape"] != current["fieldShape"]:
        change_types.append("fields")
    if previous["oneofs"] != current["oneofs"]:
        change_types.append("oneofs")
    if previous["reservedRanges"] != current["reservedRanges"] or previous["reservedNames"] != current["reservedNames"]:
        change_types.append("reserved")
    return change_types


def enum_change_types(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    change_types: list[str] = []
    if previous["file"] != current["file"]:
        change_types.append("file")
    if previous["valueShape"] != current["valueShape"]:
        change_types.append("values")
    if previous["reservedRanges"] != current["reservedRanges"] or previous["reservedNames"] != current["reservedNames"]:
        change_types.append("reserved")
    return change_types


def build_release_diffs(releases: list[dict[str, Any]]) -> None:
    previous_schema_tag: str | None = None

    for index, release in enumerate(releases):
        current_snapshot = release["snapshot"]
        previous_release = releases[index - 1] if index > 0 else None
        previous_snapshot = previous_release["snapshot"] if previous_release else None

        if previous_snapshot is None:
            file_changes = {
                "added": sorted(current_snapshot["files"].keys()),
                "removed": [],
                "modified": [],
            }
            service_changes = {
                "added": [current_snapshot["services"][key] for key in sorted(current_snapshot["services"])],
                "removed": [],
                "modified": [],
            }
            endpoint_changes = {
                "added": [current_snapshot["endpoints"][key] for key in sorted(current_snapshot["endpoints"])],
                "removed": [],
                "modified": [],
            }
            message_changes = {
                "added": [current_snapshot["messages"][key] for key in sorted(current_snapshot["messages"])],
                "removed": [],
                "modified": [],
            }
            enum_changes = {
                "added": [current_snapshot["enums"][key] for key in sorted(current_snapshot["enums"])],
                "removed": [],
                "modified": [],
            }
        else:
            file_changes = diff_file_maps(previous_snapshot["files"], current_snapshot["files"])
            service_changes = diff_keyed_entities(
                previous_snapshot["services"],
                current_snapshot["services"],
                signature_fn=service_signature,
                change_type_fn=service_change_types,
            )
            endpoint_changes = diff_keyed_entities(
                previous_snapshot["endpoints"],
                current_snapshot["endpoints"],
                signature_fn=endpoint_signature,
                change_type_fn=endpoint_change_types,
            )
            message_changes = diff_keyed_entities(
                previous_snapshot["messages"],
                current_snapshot["messages"],
                signature_fn=message_signature,
                change_type_fn=message_change_types,
            )
            enum_changes = diff_keyed_entities(
                previous_snapshot["enums"],
                current_snapshot["enums"],
                signature_fn=enum_signature,
                change_type_fn=enum_change_types,
            )

        schema_changed = (
            index == 0
            or bool(file_changes["added"] or file_changes["removed"])
            or bool(service_changes["added"] or service_changes["removed"] or service_changes["modified"])
            or bool(endpoint_changes["added"] or endpoint_changes["removed"] or endpoint_changes["modified"])
            or bool(message_changes["added"] or message_changes["removed"] or message_changes["modified"])
            or bool(enum_changes["added"] or enum_changes["removed"] or enum_changes["modified"])
        )
        source_changed = index == 0 or any(file_changes.values())

        compare_url = None
        if previous_release:
            compare_url = f"{release['repoWebUrl']}/compare/{previous_release['tag']}...{release['tag']}"
        schema_compare_url = None
        if previous_schema_tag:
            schema_compare_url = f"{release['repoWebUrl']}/compare/{previous_schema_tag}...{release['tag']}"

        release["previousTag"] = previous_release["tag"] if previous_release else None
        release["previousSchemaTag"] = previous_schema_tag
        release["sourceChanged"] = source_changed
        release["schemaChanged"] = schema_changed
        release["compareUrl"] = compare_url
        release["schemaCompareUrl"] = schema_compare_url
        release["changes"] = {
            "counts": {
                "files": {
                    "added": len(file_changes["added"]),
                    "removed": len(file_changes["removed"]),
                    "modified": len(file_changes["modified"]),
                },
                "services": {
                    "added": len(service_changes["added"]),
                    "removed": len(service_changes["removed"]),
                    "modified": len(service_changes["modified"]),
                },
                "endpoints": {
                    "added": len(endpoint_changes["added"]),
                    "removed": len(endpoint_changes["removed"]),
                    "modified": len(endpoint_changes["modified"]),
                },
                "messages": {
                    "added": len(message_changes["added"]),
                    "removed": len(message_changes["removed"]),
                    "modified": len(message_changes["modified"]),
                },
                "enums": {
                    "added": len(enum_changes["added"]),
                    "removed": len(enum_changes["removed"]),
                    "modified": len(enum_changes["modified"]),
                },
            },
            "files": file_changes,
            "services": service_changes,
            "endpoints": endpoint_changes,
            "messages": message_changes,
            "enums": enum_changes,
        }

        if schema_changed:
            previous_schema_tag = release["tag"]


def build_endpoint_lifecycle(releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lifecycle: dict[str, dict[str, Any]] = {}

    for release in releases:
        tag = release["tag"]
        changes = release["changes"]["endpoints"]
        for endpoint in changes["added"]:
            lifecycle[endpoint["id"]] = {
                "id": endpoint["id"],
                "package": endpoint["package"],
                "service": endpoint["service"],
                "serviceFullName": endpoint["serviceFullName"],
                "name": endpoint["name"],
                "introducedIn": tag,
                "lastChangedIn": tag,
                "removedIn": None,
                "current": True,
                "sourceUrl": endpoint["sourceUrl"],
                "metadata": endpoint.get("metadata", {}),
                "replacedBy": endpoint.get("metadata", {}).get("replacedBy"),
                "history": [
                    {
                        "release": tag,
                        "kind": "added",
                        "changeTypes": [],
                    }
                ],
            }
        for modified in changes["modified"]:
            current = modified["current"]
            entry = lifecycle.setdefault(
                modified["id"],
                {
                    "id": modified["id"],
                    "package": current["package"],
                    "service": current["service"],
                    "serviceFullName": current["serviceFullName"],
                    "name": current["name"],
                    "introducedIn": tag,
                    "lastChangedIn": tag,
                    "removedIn": None,
                    "current": True,
                    "sourceUrl": current["sourceUrl"],
                    "metadata": current.get("metadata", {}),
                    "replacedBy": current.get("metadata", {}).get("replacedBy"),
                    "history": [],
                },
            )
            entry["lastChangedIn"] = tag
            entry["removedIn"] = None
            entry["current"] = True
            entry["sourceUrl"] = current["sourceUrl"]
            entry["metadata"] = current.get("metadata", {})
            entry["replacedBy"] = current.get("metadata", {}).get("replacedBy")
            entry["history"].append(
                {
                    "release": tag,
                    "kind": "modified",
                    "changeTypes": modified["changeTypes"],
                }
            )
        for endpoint in changes["removed"]:
            entry = lifecycle.setdefault(
                endpoint["id"],
                {
                    "id": endpoint["id"],
                    "package": endpoint["package"],
                    "service": endpoint["service"],
                    "serviceFullName": endpoint["serviceFullName"],
                    "name": endpoint["name"],
                    "introducedIn": tag,
                    "lastChangedIn": tag,
                    "removedIn": tag,
                    "current": False,
                    "sourceUrl": endpoint["sourceUrl"],
                    "metadata": endpoint.get("metadata", {}),
                    "replacedBy": endpoint.get("metadata", {}).get("replacedBy"),
                    "history": [],
                },
            )
            entry["lastChangedIn"] = tag
            entry["removedIn"] = tag
            entry["current"] = False
            entry["metadata"] = endpoint.get("metadata", {})
            entry["replacedBy"] = endpoint.get("metadata", {}).get("replacedBy")
            entry["history"].append(
                {
                    "release": tag,
                    "kind": "removed",
                    "changeTypes": [],
                }
            )

    latest_endpoints = releases[-1]["snapshot"]["endpoints"]
    for endpoint_id, endpoint in latest_endpoints.items():
        entry = lifecycle.setdefault(
            endpoint_id,
            {
                "id": endpoint_id,
                "package": endpoint["package"],
                "service": endpoint["service"],
                "serviceFullName": endpoint["serviceFullName"],
                "name": endpoint["name"],
                "introducedIn": releases[0]["tag"],
                "lastChangedIn": releases[0]["tag"],
                "removedIn": None,
                "current": True,
                "sourceUrl": endpoint["sourceUrl"],
                "metadata": endpoint.get("metadata", {}),
                "replacedBy": endpoint.get("metadata", {}).get("replacedBy"),
                "history": [],
            },
        )
        entry["current"] = True
        entry["removedIn"] = None
        entry["sourceUrl"] = endpoint["sourceUrl"]
        entry["metadata"] = endpoint.get("metadata", {})
        entry["replacedBy"] = endpoint.get("metadata", {}).get("replacedBy")

    return [lifecycle[key] for key in sorted(lifecycle)]


def build_manifest(
    repo_dir: Path,
    *,
    output_dir: Path,
    workdir: Path,
    metadata_file: Path,
    refresh_snapshots: bool,
    refresh_descriptors: bool,
) -> dict[str, Any]:
    requested_min_version = f"v{format_semver(MIN_CANTON_VERSION)}"
    remote = git(["remote", "get-url", "origin"], cwd=repo_dir, capture=True)
    repo_web_url = normalize_remote_to_web_url(remote)
    head_ref = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, capture=True)
    head_commit = git(["rev-parse", "--short", "HEAD"], cwd=repo_dir, capture=True)
    releases = load_stable_tags(repo_dir)
    if not releases:
        raise RuntimeError(f"No stable Canton tags found for version >= {requested_min_version}")

    metadata_overlay = load_metadata_overlay(metadata_file)
    snapshots_dir = workdir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    for release in releases:
        tag = release["tag"]
        snapshot_dir = snapshots_dir / tag
        release["repoWebUrl"] = repo_web_url
        release["snapshot"] = build_snapshot(
            repo_dir,
            tag=tag,
            snapshot_dir=snapshot_dir,
            repo_web_url=repo_web_url,
            metadata_overlay=metadata_overlay,
            refresh_snapshots=refresh_snapshots,
            refresh_descriptors=refresh_descriptors,
        )

    build_release_diffs(releases)
    endpoint_lifecycle = build_endpoint_lifecycle(releases)
    latest_release = releases[-1]
    latest_snapshot = latest_release["snapshot"]

    manifest = {
        "schemaVersion": 5,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": {
            "path": str(repo_dir),
            "remote": remote,
            "webUrl": repo_web_url,
            "headRef": head_ref,
            "headCommit": head_commit,
        },
        "selection": {
            "stableTagsOnly": True,
            "requestedMinVersion": requested_min_version,
            "discoveredFirstTag": releases[0]["tag"],
            "discoveredLastTag": releases[-1]["tag"],
            "releaseLines": sorted({release["releaseLine"] for release in releases}),
            "tagPattern": "^v[0-9]+\\.[0-9]+\\.[0-9]+$",
            "pathPattern": OWNED_PROTO_RE.pattern,
            "note": (
                "This generator uses stable Canton release tags as the protobuf version axis and "
                "reads each release tag's checked-in .proto_snapshot_image.bin.gz descriptor image with "
                "source info. The image contains both Canton-owned protos and the external imports needed "
                "for descriptor-backed rendering."
            ),
        },
        "artifacts": {
            "outputDir": safe_relative_to(output_dir, REPO_ROOT),
            "workdir": safe_relative_to(workdir, REPO_ROOT),
            "metadataFile": safe_relative_to(metadata_file, REPO_ROOT),
        },
        "latestRelease": latest_release["tag"],
        "latestSnapshot": {
            "tag": latest_release["tag"],
            "date": latest_release["date"],
            "releaseLine": latest_release["releaseLine"],
            "stats": latest_snapshot["stats"],
            "packages": latest_snapshot["packages"],
            "files": [latest_snapshot["files"][key] for key in sorted(latest_snapshot["files"])],
            "services": [latest_snapshot["services"][key] for key in sorted(latest_snapshot["services"])],
            "endpoints": [latest_snapshot["endpoints"][key] for key in sorted(latest_snapshot["endpoints"])],
            "messages": [latest_snapshot["messages"][key] for key in sorted(latest_snapshot["messages"])],
            "fields": [latest_snapshot["fields"][key] for key in sorted(latest_snapshot["fields"])],
            "enums": [latest_snapshot["enums"][key] for key in sorted(latest_snapshot["enums"])],
            "enumValues": [latest_snapshot["enumValues"][key] for key in sorted(latest_snapshot["enumValues"])],
        },
        "endpointLifecycle": endpoint_lifecycle,
        "endpointPages": build_endpoint_page_entries(endpoint_lifecycle, output_dir),
        "releases": [
            {
                "tag": release["tag"],
                "version": release["version"],
                "releaseLine": release["releaseLine"],
                "date": release["date"],
                "previousTag": release["previousTag"],
                "previousSchemaTag": release["previousSchemaTag"],
                "sourceChanged": release["sourceChanged"],
                "schemaChanged": release["schemaChanged"],
                "compareUrl": release["compareUrl"],
                "schemaCompareUrl": release["schemaCompareUrl"],
                "snapshotDir": release["snapshot"]["snapshotDir"],
                "descriptorPath": release["snapshot"]["descriptorPath"],
                "stats": release["snapshot"]["stats"],
                "changes": release["changes"],
            }
            for release in releases
        ],
    }
    return manifest


def package_sort_key(item: dict[str, Any]) -> tuple[str, int]:
    return (item["package"], item["endpointCount"])


def build_latest_context(latest_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "files": {item["id"]: item for item in latest_snapshot["files"]},
        "services": {item["id"]: item for item in latest_snapshot["services"]},
        "endpoints": {item["id"]: item for item in latest_snapshot["endpoints"]},
        "messages": {item["id"]: item for item in latest_snapshot["messages"]},
        "fields": {item["id"]: item for item in latest_snapshot["fields"]},
        "enums": {item["id"]: item for item in latest_snapshot["enums"]},
        "enumValues": {item["id"]: item for item in latest_snapshot["enumValues"]},
    }


def build_endpoint_page_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in manifest.get("endpointPages", [])}


def endpoint_page_url(endpoint_pages: dict[str, dict[str, Any]], endpoint_id: str) -> str | None:
    page = endpoint_pages.get(endpoint_id)
    if not page:
        return None
    return f"/{page['pageId']}"


def metadata_lines(entity: dict[str, Any]) -> list[str]:
    metadata = entity.get("metadata", {})
    if not metadata:
        return []
    lines: list[str] = []
    replaced_by = metadata.get("replacedBy")
    if replaced_by:
        lines.append(f"- Replaced by: `{escape_text(replaced_by)}`")
    notes = metadata.get("notes")
    if notes:
        lines.append(f"- Notes: {escape_text(str(notes))}")
    for key in sorted(metadata):
        if key in {"replacedBy", "notes"}:
            continue
        lines.append(f"- {escape_text(key)}: `{escape_text(json.dumps(metadata[key], sort_keys=True))}`")
    return lines


def render_options(options: dict[str, Any]) -> str:
    if not options:
        return ""
    return "```json\n" + json.dumps(options, indent=2, sort_keys=True) + "\n```"


def render_field_table(field_ids: list[str], ctx: dict[str, dict[str, Any]]) -> str:
    if not field_ids:
        return "No fields."
    rows = [
        "| # | Field | Type | Label | Oneof | Description | Metadata |",
        "| -: | :---- | :--- | :---- | :---- | :---------- | :------- |",
    ]
    for field_id in field_ids:
        field = ctx["fields"][field_id]
        metadata_summary = ", ".join(metadata_lines(field)) or ""
        rows.append(
            "| "
            + " | ".join(
                [
                    str(field["number"]),
                    f"`{escape_md(field['name'])}`",
                    f"`{escape_md(field['type'])}`",
                    escape_md(field["label"]),
                    f"`{escape_md(field['oneof'])}`" if field["oneof"] else "",
                    escape_md_cell(field["description"]),
                    escape_md_cell(metadata_summary.removeprefix("- ").replace("\n", "; ")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_enum_table(enum_value_ids: list[str], ctx: dict[str, dict[str, Any]]) -> str:
    if not enum_value_ids:
        return "No enum values."
    rows = [
        "| Name | Number | Description | Metadata |",
        "| :--- | -----: | :---------- | :------- |",
    ]
    for value_id in enum_value_ids:
        value = ctx["enumValues"][value_id]
        metadata_summary = ", ".join(metadata_lines(value)) or ""
        rows.append(
            "| "
            + " | ".join(
                [
                    f"`{escape_md(value['name'])}`",
                    str(value["number"]),
                    escape_md_cell(value["description"]),
                    escape_md_cell(metadata_summary.removeprefix("- ").replace("\n", "; ")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_endpoint_signature(endpoint: dict[str, Any]) -> str:
    request_prefix = "stream " if endpoint["clientStreaming"] else ""
    response_prefix = "stream " if endpoint["serverStreaming"] else ""
    return (
        f"{endpoint['service']}.{endpoint['name']}("
        f"{request_prefix}{endpoint['requestType']}) returns "
        f"({response_prefix}{endpoint['responseType']})"
    )


def render_endpoint_block(
    endpoint: dict[str, Any],
    endpoint_pages: dict[str, dict[str, Any]],
    level: int = 5,
) -> str:
    lines = [
        f"{'#' * level} Endpoint `{endpoint['serviceFullName']}/{endpoint['name']}`",
        "",
        f"- Source: {md_link(endpoint['file'], endpoint['sourceUrl'])}",
        f"- Endpoint page: {md_link('reference', endpoint_page_url(endpoint_pages, endpoint['id']))}",
        f"- Request: `{endpoint['requestType']}`",
        f"- Response: `{endpoint['responseType']}`",
        f"- Client streaming: {'yes' if endpoint['clientStreaming'] else 'no'}",
        f"- Server streaming: {'yes' if endpoint['serverStreaming'] else 'no'}",
    ]
    lines.extend(metadata_lines(endpoint))
    lines.extend(["", render_description(endpoint["description"])])
    options = render_options(endpoint["options"])
    if options:
        lines.extend(["", "Options:", "", options])
    return "\n".join(lines)


def render_service_block(
    service: dict[str, Any],
    ctx: dict[str, dict[str, Any]],
    endpoint_pages: dict[str, dict[str, Any]],
    level: int = 4,
) -> str:
    lines = [
        f"{'#' * level} Service `{service['fullName']}`",
        "",
        f"- Source: {md_link(service['file'], service['sourceUrl'])}",
        f"- Endpoints: {len(service['endpointIds'])}",
    ]
    lines.extend(metadata_lines(service))
    lines.extend(["", render_description(service["description"])])
    options = render_options(service["options"])
    if options:
        lines.extend(["", "Options:", "", options])
    for endpoint_id in service["endpointIds"]:
        lines.extend(
            [
                "",
                render_endpoint_block(
                    ctx["endpoints"][endpoint_id],
                    endpoint_pages,
                    level=min(level + 1, 6),
                ),
            ]
        )
    return "\n".join(lines)


def render_enum_block(enum_doc: dict[str, Any], ctx: dict[str, dict[str, Any]], level: int = 4) -> str:
    lines = [
        f"{'#' * level} Enum `{enum_doc['fullName']}`",
        "",
        f"- Source: {md_link(enum_doc['file'], enum_doc['sourceUrl'])}",
        f"- Values: {len(enum_doc['valueIds'])}",
    ]
    if enum_doc["reservedRanges"]:
        lines.append(f"- Reserved ranges: `{json.dumps(enum_doc['reservedRanges'])}`")
    if enum_doc["reservedNames"]:
        lines.append(f"- Reserved names: `{json.dumps(enum_doc['reservedNames'])}`")
    lines.extend(metadata_lines(enum_doc))
    lines.extend(["", render_description(enum_doc["description"]), "", render_enum_table(enum_doc["valueIds"], ctx)])
    options = render_options(enum_doc["options"])
    if options:
        lines.extend(["", "Options:", "", options])
    return "\n".join(lines)


def render_message_block(message: dict[str, Any], ctx: dict[str, dict[str, Any]], level: int = 4) -> str:
    lines = [
        f"{'#' * level} Message `{message['fullName']}`",
        "",
        f"- Source: {md_link(message['file'], message['sourceUrl'])}",
        f"- Fields: {len(message['fieldIds'])}",
        f"- Nested messages: {len(message['nestedMessageIds'])}",
        f"- Nested enums: {len(message['enumIds'])}",
    ]
    if message["reservedRanges"]:
        lines.append(f"- Reserved ranges: `{json.dumps(message['reservedRanges'])}`")
    if message["reservedNames"]:
        lines.append(f"- Reserved names: `{json.dumps(message['reservedNames'])}`")
    lines.extend(metadata_lines(message))
    lines.extend(["", render_description(message["description"])])
    if message["oneofs"]:
        lines.extend(["", "Oneofs:"])
        for oneof in message["oneofs"]:
            lines.append(f"- `{oneof['name']}` ({len(oneof['fieldIds'])} fields)")
            if oneof["description"]:
                lines.append(f"  {escape_text(oneof['description'])}")
    lines.extend(["", render_field_table(message["fieldIds"], ctx)])
    options = render_options(message["options"])
    if options:
        lines.extend(["", "Options:", "", options])
    for enum_id in message["enumIds"]:
        lines.extend(["", render_enum_block(ctx["enums"][enum_id], ctx, level=min(level + 1, 6))])
    for nested_id in message["nestedMessageIds"]:
        lines.extend(["", render_message_block(ctx["messages"][nested_id], ctx, level=min(level + 1, 6))])
    return "\n".join(lines)


def render_file_block(
    file_doc: dict[str, Any],
    ctx: dict[str, dict[str, Any]],
    endpoint_pages: dict[str, dict[str, Any]],
) -> str:
    summary = (
        f"<summary><code>{file_doc['importPath']}</code> · "
        f"{len(file_doc['serviceIds'])} services · {len(file_doc['messageIds'])} messages · "
        f"{len(file_doc['enumIds'])} enums</summary>"
    )
    lines = [
        "<details>",
        summary,
        "",
        f"- Repo path: `{file_doc['repoPath']}`",
        f"- Source: {md_link(file_doc['repoPath'], file_doc['sourceUrl'])}",
        f"- Package: `{file_doc['package']}`",
        f"- Syntax: `{file_doc['syntax']}`",
        f"- Imports: {len(file_doc['dependencies'])}",
    ]
    lines.extend(metadata_lines(file_doc))
    lines.extend(["", render_description(file_doc["description"])])
    if file_doc["dependencies"]:
        lines.extend(["", "Imports:", render_list([f"`{dep}`" for dep in file_doc["dependencies"]])])
    options = render_options(file_doc["options"])
    if options:
        lines.extend(["", "Options:", "", options])

    for declaration in file_doc["declarations"]:
        kind = declaration["kind"]
        entity_id = declaration["id"]
        if kind == "service":
            lines.extend(["", render_service_block(ctx["services"][entity_id], ctx, endpoint_pages)])
        elif kind == "message":
            lines.extend(["", render_message_block(ctx["messages"][entity_id], ctx)])
        elif kind == "enum":
            lines.extend(["", render_enum_block(ctx["enums"][entity_id], ctx)])
    lines.extend(["", "</details>"])
    return "\n".join(lines)


def render_package_summary_table(latest_snapshot: dict[str, Any]) -> str:
    rows = [
        "| Package | Files | Services | Endpoints | Messages | Fields | Enums |",
        "| :------ | ----: | -------: | --------: | -------: | -----: | ----: |",
    ]
    for package in sorted(latest_snapshot["packages"], key=package_sort_key):
        rows.append(
            "| "
            + " | ".join(
                [
                    f"`{escape_md(package['package'])}`",
                    str(package["fileCount"]),
                    str(package["serviceCount"]),
                    str(package["endpointCount"]),
                    str(package["messageCount"]),
                    str(package["fieldCount"]),
                    str(package["enumCount"]),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_package_details(
    latest_snapshot: dict[str, Any],
    ctx: dict[str, dict[str, Any]],
    endpoint_pages: dict[str, dict[str, Any]],
) -> str:
    blocks: list[str] = []
    for package in sorted(latest_snapshot["packages"], key=package_sort_key):
        blocks.append(
            "<details>\n"
            f"<summary><code>{package['package']}</code> · {package['fileCount']} files · "
            f"{package['endpointCount']} endpoints · {package['messageCount']} messages</summary>\n"
        )
        for file_id in package["fileIds"]:
            blocks.append(render_file_block(ctx["files"][file_id], ctx, endpoint_pages))
        blocks.append("</details>")
    return "\n\n".join(blocks)


def render_release_timeline_table(releases: list[dict[str, Any]]) -> str:
    rows = [
        "| Release | Date | Line | Source Changed | Schema Changed | File +/~/- | Endpoint +/~/- | Message +/~/- |",
        "| :------ | :--- | :--- | :------------- | :------------- | ----------: | --------------: | -------------: |",
    ]
    for release in releases:
        file_counts = release["changes"]["counts"]["files"]
        endpoint_counts = release["changes"]["counts"]["endpoints"]
        message_counts = release["changes"]["counts"]["messages"]
        release_label = md_link(release["tag"], release["compareUrl"]) if release["compareUrl"] else f"`{release['tag']}`"
        rows.append(
            "| "
            + " | ".join(
                [
                    release_label,
                    release["date"],
                    escape_md(release["releaseLine"]),
                    "yes" if release["sourceChanged"] else "no",
                    "yes" if release["schemaChanged"] else "no",
                    f"{file_counts['added']}/{file_counts['modified']}/{file_counts['removed']}",
                    f"{endpoint_counts['added']}/{endpoint_counts['modified']}/{endpoint_counts['removed']}",
                    f"{message_counts['added']}/{message_counts['modified']}/{message_counts['removed']}",
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_add_remove_summary_table(releases: list[dict[str, Any]]) -> str:
    if len(releases) <= 1:
        return "No releases after the baseline are in scope."

    category_labels = [
        ("files", "file"),
        ("services", "service"),
        ("endpoints", "endpoint"),
        ("messages", "message"),
        ("enums", "enum"),
    ]
    rows = [
        "| Release | Date | Added | Removed |",
        "| :------ | :--- | :---- | :------ |",
    ]

    def summarize(counts: dict[str, Any], direction: str) -> str:
        parts: list[str] = []
        for key, label in category_labels:
            count = counts[key][direction]
            if count:
                suffix = "" if count == 1 else "s"
                parts.append(f"{count} {label}{suffix}")
        return ", ".join(parts)

    has_rows = False
    for release in releases[1:]:
        counts = release["changes"]["counts"]
        added = summarize(counts, "added")
        removed = summarize(counts, "removed")
        if not added and not removed:
            continue
        has_rows = True
        compare_url = release["schemaCompareUrl"] or release["compareUrl"]
        release_label = md_link(release["tag"], compare_url) if compare_url else f"`{release['tag']}`"
        rows.append(
            "| "
            + " | ".join(
                [
                    release_label,
                    release["date"],
                    added or "",
                    removed or "",
                ]
            )
            + " |"
        )

    if not has_rows:
        return f"No additions or removals after `{releases[0]['tag']}`."
    return "\n".join(rows)


def render_endpoint_lifecycle_table(
    endpoint_lifecycle: list[dict[str, Any]],
    endpoint_pages: dict[str, dict[str, Any]],
) -> str:
    rows = [
        "| Endpoint | Introduced | Last Changed | Removed | Status | Replaced By | Source |",
        "| :------- | :--------- | :----------- | :------ | :----- | :---------- | :----- |",
    ]
    for endpoint in endpoint_lifecycle:
        rows.append(
            "| "
            + " | ".join(
                [
                    md_link(f"`{escape_md(endpoint['id'])}`", endpoint_page_url(endpoint_pages, endpoint["id"])),
                    endpoint["introducedIn"],
                    endpoint["lastChangedIn"],
                    endpoint["removedIn"] or "",
                    "current" if endpoint["current"] else "removed",
                    f"`{escape_md(endpoint['replacedBy'])}`" if endpoint.get("replacedBy") else "",
                    md_link("file", endpoint["sourceUrl"]),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_release_changes(
    releases: list[dict[str, Any]],
    endpoint_pages: dict[str, dict[str, Any]],
) -> str:
    blocks: list[str] = []
    for release in releases:
        if not release["schemaChanged"]:
            continue
        counts = release["changes"]["counts"]
        summary = " · ".join(
            [
                f"files {counts['files']['added']}/{counts['files']['modified']}/{counts['files']['removed']}",
                f"endpoints {counts['endpoints']['added']}/{counts['endpoints']['modified']}/{counts['endpoints']['removed']}",
                f"messages {counts['messages']['added']}/{counts['messages']['modified']}/{counts['messages']['removed']}",
                f"enums {counts['enums']['added']}/{counts['enums']['modified']}/{counts['enums']['removed']}",
            ]
        )
        compare = md_link("compare", release["schemaCompareUrl"]) if release["schemaCompareUrl"] else "baseline"
        details = [
            "<details>",
            f"<summary><code>{release['tag']}</code> · {release['date']} · {summary} · {compare}</summary>",
            "",
        ]

        file_changes = release["changes"]["files"]
        if file_changes["added"] or file_changes["removed"] or file_changes["modified"]:
            details.append("Files:")
            if file_changes["added"]:
                details.append("Added:")
                details.extend(render_limited_list(file_changes["added"], formatter=lambda path: f"`{path}`"))
            if file_changes["modified"]:
                details.append("Modified:")
                details.extend(render_limited_list(file_changes["modified"], formatter=lambda path: f"`{path}`"))
            if file_changes["removed"]:
                details.append("Removed:")
                details.extend(render_limited_list(file_changes["removed"], formatter=lambda path: f"`{path}`"))
            details.append("")

        endpoint_changes = release["changes"]["endpoints"]
        if endpoint_changes["added"]:
            details.append("Added endpoints:")
            details.extend(
                render_limited_list(
                    endpoint_changes["added"],
                    formatter=lambda endpoint: (
                        f"{md_link(f'`{render_endpoint_signature(endpoint)}`', endpoint_page_url(endpoint_pages, endpoint['id']))} "
                        f"in `{endpoint['file']}`"
                    ),
                )
            )
            details.append("")
        if endpoint_changes["modified"]:
            details.append("Modified endpoints:")
            details.extend(
                render_limited_list(
                    endpoint_changes["modified"],
                    formatter=lambda change: (
                        f"{md_link(f'`{change['id']}`', endpoint_page_url(endpoint_pages, change['id']))} "
                        f"({', '.join(change['changeTypes'])})"
                    ),
                )
            )
            details.append("")
        if endpoint_changes["removed"]:
            details.append("Removed endpoints:")
            details.extend(
                render_limited_list(
                    endpoint_changes["removed"],
                    formatter=lambda endpoint: md_link(
                        f"`{endpoint['id']}`",
                        endpoint_page_url(endpoint_pages, endpoint["id"]),
                    ),
                )
            )
            details.append("")

        message_changes = release["changes"]["messages"]
        if message_changes["added"]:
            details.append("Added messages:")
            details.extend(
                render_limited_list(
                    message_changes["added"],
                    formatter=lambda message: f"`{message['id']}`",
                )
            )
            details.append("")
        if message_changes["modified"]:
            details.append("Modified messages:")
            details.extend(
                render_limited_list(
                    message_changes["modified"],
                    formatter=lambda change: f"`{change['id']}` ({', '.join(change['changeTypes'])})",
                )
            )
            details.append("")
        if message_changes["removed"]:
            details.append("Removed messages:")
            details.extend(
                render_limited_list(
                    message_changes["removed"],
                    formatter=lambda message: f"`{message['id']}`",
                )
            )
            details.append("")

        enum_changes = release["changes"]["enums"]
        if enum_changes["added"]:
            details.append("Added enums:")
            details.extend(
                render_limited_list(
                    enum_changes["added"],
                    formatter=lambda enum_doc: f"`{enum_doc['id']}`",
                )
            )
            details.append("")
        if enum_changes["modified"]:
            details.append("Modified enums:")
            details.extend(
                render_limited_list(
                    enum_changes["modified"],
                    formatter=lambda change: f"`{change['id']}` ({', '.join(change['changeTypes'])})",
                )
            )
            details.append("")
        if enum_changes["removed"]:
            details.append("Removed enums:")
            details.extend(
                render_limited_list(
                    enum_changes["removed"],
                    formatter=lambda enum_doc: f"`{enum_doc['id']}`",
                )
            )
            details.append("")

        details.append("</details>")
        blocks.append("\n".join(details).rstrip())
    return "\n\n".join(blocks)


def write_manifest_json(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_mdx(manifest: dict[str, Any], path: Path) -> None:
    latest = manifest["latestSnapshot"]
    releases = manifest["releases"]
    endpoint_lifecycle = manifest["endpointLifecycle"]
    ctx = build_latest_context(latest)
    endpoint_pages = build_endpoint_page_map(manifest)
    baseline_release = releases[0]["tag"] if releases else None
    selection = manifest["selection"]
    discovered_first = selection["discoveredFirstTag"]
    discovered_last = selection["discoveredLastTag"]
    if discovered_first == discovered_last:
        discovered_range = f"`{discovered_first}`"
    else:
        discovered_range = f"`{discovered_first}` through `{discovered_last}`"
    release_lines = ", ".join(f"`{line}`" for line in selection["releaseLines"])

    lines = [
        "---",
        "title: Canton Protobuf History",
        "description: Descriptor-backed stable Canton protobuf inventory and history for Canton releases from v3.2.0 onward.",
        "---",
        "",
        "# Canton Protobuf History",
        "",
        "This page is generated from `FileDescriptorSet` snapshots with source info.",
        "It shows the latest stable schema in full detail and the release-by-release history on the same page.",
        "Each endpoint in the latest and historical snapshots also has its own generated reference page.",
        "",
        "## Scope",
        "",
        f"- Requested stable tag floor: `{selection['requestedMinVersion']}`",
        f"- Stable tags discovered in repo: {discovered_range}",
        f"- Release lines in scope: {release_lines}",
        "- Included paths: `community/**/src/main/protobuf/**/*.proto`",
        "- Version axis: stable Canton release tags, not protobuf package suffixes",
        f"- Metadata overlay: `{manifest['artifacts']['metadataFile']}`",
        f"- Generated at: `{manifest['generatedAt']}`",
        f"- Source repo: `{manifest['repo']['remote']}`",
        f"- Source ref at generation time: `{manifest['repo']['headRef']}` / `{manifest['repo']['headCommit']}`",
        "",
        "## Latest Snapshot",
        "",
        f"- Latest stable release in scope: `{latest['tag']}` ({latest['date']})",
        f"- Release line: `{latest['releaseLine']}`",
        f"- Proto files: {latest['stats']['protoFiles']}",
        f"- Packages: {latest['stats']['packages']}",
        f"- Services: {latest['stats']['services']}",
        f"- Endpoints: {latest['stats']['endpoints']}",
        f"- Messages: {latest['stats']['messages']}",
        f"- Fields: {latest['stats']['fields']}",
        f"- Enums: {latest['stats']['enums']}",
        "",
        f"## Additions And Removals Since `{baseline_release}`",
        "",
        "This summary excludes the baseline release and ignores pure modifications.",
        "",
        render_add_remove_summary_table(releases),
        "",
        "## Release Timeline",
        "",
        render_release_timeline_table(releases),
        "",
        "## Endpoint Lifecycle",
        "",
        "The lifecycle table tracks when endpoints were introduced, when their signatures last changed,",
        "whether they are still present, and whether the metadata overlay marks them as replaced.",
        "",
        render_endpoint_lifecycle_table(endpoint_lifecycle, endpoint_pages),
        "",
        "## Current Schema Summary",
        "",
        render_package_summary_table(latest),
        "",
        "## Current Schema Details",
        "",
        render_package_details(latest, ctx, endpoint_pages),
        "",
        "## Schema Change History",
        "",
        render_release_changes(releases, endpoint_pages),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def page_id_for_index_dir(relative_output_dir: Path) -> str:
    page_dir = relative_output_dir.as_posix().strip("/")
    if not page_dir:
        raise ValueError("Output directory must not resolve to repository root")
    return f"{page_dir}/index"


def endpoint_page_relative_dir(relative_output_dir: Path, endpoint: dict[str, Any]) -> Path:
    package_parts = [
        slugify_segment(part)
        for part in endpoint["package"].split(".")
        if part
    ]
    return relative_output_dir.joinpath(
        ENDPOINT_PAGE_SUBDIR,
        *package_parts,
        slugify_segment(endpoint["service"]),
        slugify_segment(endpoint["name"]),
    )


def build_endpoint_page_entries(
    endpoint_lifecycle: list[dict[str, Any]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    relative_output_dir = output_dir.relative_to(REPO_ROOT)
    entries: list[dict[str, Any]] = []
    for endpoint in endpoint_lifecycle:
        relative_dir = endpoint_page_relative_dir(relative_output_dir, endpoint)
        page_id = page_id_for_index_dir(relative_dir)
        entries.append(
            {
                "id": endpoint["id"],
                "package": endpoint["package"],
                "service": endpoint["service"],
                "name": endpoint["name"],
                "pageId": page_id,
                "path": f"{page_id}.mdx",
            }
        )
    return entries


def resolve_endpoint_entity(
    endpoint_id: str,
    latest_ctx: dict[str, dict[str, Any]],
    releases: list[dict[str, Any]],
) -> dict[str, Any] | None:
    endpoint = latest_ctx["endpoints"].get(endpoint_id)
    if endpoint is not None:
        return endpoint

    for release in reversed(releases):
        changes = release["changes"]["endpoints"]
        for removed in changes["removed"]:
            if removed["id"] == endpoint_id:
                return removed
        for modified in changes["modified"]:
            if modified["id"] == endpoint_id:
                return modified["current"]
        for added in changes["added"]:
            if added["id"] == endpoint_id:
                return added
    return None


def render_endpoint_history_table(
    endpoint_lifecycle_entry: dict[str, Any],
    releases_by_tag: dict[str, dict[str, Any]],
) -> str:
    rows = [
        "| Release | Date | Event | Change Types | Compare |",
        "| :------ | :--- | :---- | :----------- | :------ |",
    ]
    for event in endpoint_lifecycle_entry["history"]:
        release = releases_by_tag[event["release"]]
        compare_url = release["schemaCompareUrl"] or release["compareUrl"]
        compare = md_link("compare", compare_url) if compare_url else ""
        change_types = ", ".join(f"`{change}`" for change in event["changeTypes"]) or ""
        rows.append(
            "| "
            + " | ".join(
                [
                    f"`{release['tag']}`",
                    release["date"],
                    event["kind"],
                    change_types,
                    compare,
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_endpoint_type_section(
    title: str,
    type_name: str,
    ctx: dict[str, dict[str, Any]],
) -> str:
    lines = [f"## {title}", ""]
    message = ctx["messages"].get(type_name)
    if message is not None:
        lines.append(render_message_block(message, ctx, level=3))
        return "\n".join(lines)

    enum_doc = ctx["enums"].get(type_name)
    if enum_doc is not None:
        lines.append(render_enum_block(enum_doc, ctx, level=3))
        return "\n".join(lines)

    lines.append(
        f"`{type_name}` is not part of the latest Canton-owned protobuf snapshot rendered on this site."
    )
    return "\n".join(lines)


def render_service_context(
    endpoint_doc: dict[str, Any],
    ctx: dict[str, dict[str, Any]],
    endpoint_pages: dict[str, dict[str, Any]],
) -> str:
    service = ctx["services"].get(endpoint_doc["serviceFullName"])
    if service is None:
        return ""

    sibling_links = []
    for endpoint_id in service["endpointIds"]:
        sibling = ctx["endpoints"][endpoint_id]
        sibling_links.append(
            md_link(
                f"`{sibling['name']}`",
                endpoint_page_url(endpoint_pages, endpoint_id),
            )
        )

    lines = [
        "## Service Context",
        "",
        f"- Service: `{service['fullName']}`",
        f"- Source: {md_link(service['file'], service['sourceUrl'])}",
        f"- Endpoints in service: {len(service['endpointIds'])}",
        "",
        render_description(service["description"]),
        "",
        "Endpoints in this service:",
        render_list(sibling_links),
    ]
    options = render_options(service["options"])
    if options:
        lines.extend(["", "Service options:", "", options])
    return "\n".join(lines)


def write_endpoint_pages(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
) -> list[Path]:
    latest = manifest["latestSnapshot"]
    releases = manifest["releases"]
    releases_by_tag = {release["tag"]: release for release in releases}
    latest_ctx = build_latest_context(latest)
    endpoint_pages = build_endpoint_page_map(manifest)
    index_page_url = f"/{page_id_for_index_dir(output_dir.relative_to(REPO_ROOT))}"
    written_paths: list[Path] = []

    for lifecycle_entry in manifest["endpointLifecycle"]:
        page_info = endpoint_pages[lifecycle_entry["id"]]
        page_path = REPO_ROOT / page_info["path"]
        endpoint_doc = resolve_endpoint_entity(lifecycle_entry["id"], latest_ctx, releases)
        if endpoint_doc is None:
            continue

        replaced_by = lifecycle_entry.get("replacedBy")
        replaced_by_link = None
        if replaced_by:
            replaced_by_link = md_link(
                f"`{replaced_by}`",
                endpoint_page_url(endpoint_pages, replaced_by),
            )

        lines = [
            "---",
            f"title: {endpoint_doc['service']}.{endpoint_doc['name']}",
            (
                "description: Descriptor-backed protobuf endpoint reference and history for "
                f"{endpoint_doc['serviceFullName']}/{endpoint_doc['name']}."
            ),
            "---",
            "",
            f"# Endpoint `{endpoint_doc['id']}`",
            "",
            f"[Back to Canton Protobuf History]({index_page_url})",
            "",
            "## Overview",
            "",
            f"- Status: {'current' if lifecycle_entry['current'] else 'removed'}",
            f"- Package: `{endpoint_doc['package']}`",
            f"- Service: `{endpoint_doc['serviceFullName']}`",
            f"- Source: {md_link(endpoint_doc['file'], endpoint_doc['sourceUrl'])}",
            f"- Request: `{endpoint_doc['requestType']}`",
            f"- Response: `{endpoint_doc['responseType']}`",
            f"- Client streaming: {'yes' if endpoint_doc['clientStreaming'] else 'no'}",
            f"- Server streaming: {'yes' if endpoint_doc['serverStreaming'] else 'no'}",
            f"- Introduced in: `{lifecycle_entry['introducedIn']}`",
            f"- Last changed in: `{lifecycle_entry['lastChangedIn']}`",
        ]
        if lifecycle_entry["removedIn"]:
            lines.append(f"- Removed in: `{lifecycle_entry['removedIn']}`")
        if replaced_by_link:
            lines.append(f"- Replaced by: {replaced_by_link}")
        lines.extend(
            line
            for line in metadata_lines(endpoint_doc)
            if not line.startswith("- Replaced by:")
        )
        lines.extend(
            [
                "",
                "## Signature",
                "",
                "```proto",
                f"rpc {render_endpoint_signature(endpoint_doc)};",
                "```",
                "",
                render_description(endpoint_doc["description"]),
            ]
        )

        options = render_options(endpoint_doc["options"])
        if options:
            lines.extend(["", "## Options", "", options])

        lines.extend(
            [
                "",
                "## Release History",
                "",
                render_endpoint_history_table(lifecycle_entry, releases_by_tag),
                "",
            ]
        )

        if endpoint_doc["requestType"] == endpoint_doc["responseType"]:
            lines.extend(
                [
                    render_endpoint_type_section("Request / Response Type", endpoint_doc["requestType"], latest_ctx),
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    render_endpoint_type_section("Request Type", endpoint_doc["requestType"], latest_ctx),
                    "",
                    render_endpoint_type_section("Response Type", endpoint_doc["responseType"], latest_ctx),
                    "",
                ]
            )

        service_context = render_service_context(endpoint_doc, latest_ctx, endpoint_pages)
        if service_context:
            lines.extend([service_context, ""])

        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        written_paths.append(page_path)

    return written_paths


def update_docs_json(
    docs_json_path: Path,
    *,
    dropdown_name: str,
    group_name: str,
    page_id: str,
) -> None:
    data = json.loads(docs_json_path.read_text(encoding="utf-8"))
    navigation = data.get("navigation")
    if isinstance(navigation, list):
        dropdowns = navigation
    elif isinstance(navigation, dict):
        dropdowns = navigation.get("dropdowns")
    else:
        dropdowns = None
    if not isinstance(dropdowns, list):
        raise ValueError("docs.json: expected 'navigation' to be a list or object with 'dropdowns' list")

    target_dropdown = next(
        (
            item
            for item in dropdowns
            if isinstance(item, dict) and item.get("dropdown") == dropdown_name
        ),
        None,
    )
    if target_dropdown is None:
        raise ValueError(f"docs.json: unable to find '{dropdown_name}' dropdown")

    versions = target_dropdown.get("versions")
    if not isinstance(versions, list):
        raise ValueError(f"docs.json: '{dropdown_name}' dropdown must contain 'versions' list")

    for version in versions:
        groups = version.get("groups")
        if not isinstance(groups, list):
            raise ValueError(f"docs.json: expected 'groups' list in '{dropdown_name}' version")

        existing_group = next(
            (
                group
                for group in groups
                if isinstance(group, dict) and group.get("group") == group_name
            ),
            None,
        )
        if existing_group is not None:
            pages = existing_group.get("pages")
            if not isinstance(pages, list):
                raise ValueError(f"docs.json: expected 'pages' list in '{group_name}' group")
            if page_id not in pages:
                pages.append(page_id)
            continue

        insert_at = next(
            (
                idx
                for idx, group in enumerate(groups)
                if isinstance(group, dict) and group.get("group") == "Help"
            ),
            len(groups),
        )
        groups.insert(insert_at, {"group": group_name, "pages": [page_id]})

    docs_json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_docs_bundle(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
    docs_json_path: Path | None,
    dropdown_name: str,
    group_name: str,
) -> tuple[Path, Path | None]:
    write_manifest_json(manifest, output_dir / "manifest.json")
    write_mdx(manifest, output_dir / "index.mdx")
    write_endpoint_pages(manifest, output_dir=output_dir)

    if docs_json_path is not None:
        if not docs_json_path.exists():
            raise FileNotFoundError(f"docs.json not found: {docs_json_path}")
        page_id = page_id_for_index_dir(output_dir.relative_to(REPO_ROOT))
        update_docs_json(
            docs_json_path,
            dropdown_name=dropdown_name,
            group_name=group_name,
            page_id=page_id,
        )
    return output_dir / "index.mdx", docs_json_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canton-repo-dir",
        type=Path,
        default=DEFAULT_CANTON_REPO_DIR,
        help="Local Canton checkout used as the source of tags and descriptor images. Cloned automatically if missing.",
    )
    parser.add_argument(
        "--canton-repo-url",
        default=DEFAULT_CANTON_REPO_URL,
        help="Git URL used when cloning Canton into --canton-repo-dir.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where manifest.json and index.mdx are written.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=DEFAULT_WORKDIR,
        help="Directory used for materialized release snapshots and descriptor caches.",
    )
    parser.add_argument(
        "--metadata-file",
        type=Path,
        default=DEFAULT_METADATA_FILE,
        help="JSON metadata overlay file with manual annotations such as replacedBy.",
    )
    parser.add_argument(
        "--refresh-snapshots",
        action="store_true",
        help="Re-materialize release snapshots from git even if cached locally.",
    )
    parser.add_argument(
        "--refresh-descriptors",
        action="store_true",
        help="Re-read descriptor images even if cached locally.",
    )
    parser.add_argument(
        "--docs-json",
        type=Path,
        default=DEFAULT_DOCS_JSON,
        help="Path to the local docs.json that should be updated with the generated page.",
    )
    parser.add_argument(
        "--dropdown",
        default="App Development",
        help="Dropdown name in docs.json that should include the generated page.",
    )
    parser.add_argument(
        "--group",
        default="Reference",
        help="Group name in docs.json that should include the generated page.",
    )
    parser.add_argument(
        "--skip-docs-json",
        action="store_true",
        help="Generate manifest and MDX without updating docs.json.",
    )
    parser.add_argument(
        "--skip-canton-fetch",
        action="store_true",
        help="Use the existing Canton clone as-is without fetching updated tags from origin.",
    )
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    ensure_runtime_dependencies()
    canton_repo_dir = ensure_canton_repo(
        args.canton_repo_dir.resolve(),
        repo_url=args.canton_repo_url,
        fetch=not args.skip_canton_fetch,
    )
    output_dir = args.output_dir.resolve()
    metadata_file = args.metadata_file.resolve()
    docs_json_path = None if args.skip_docs_json else args.docs_json.resolve()

    manifest = build_manifest(
        canton_repo_dir,
        output_dir=output_dir,
        workdir=workdir,
        metadata_file=metadata_file,
        refresh_snapshots=args.refresh_snapshots,
        refresh_descriptors=args.refresh_descriptors,
    )

    index_path, updated_docs_json = write_docs_bundle(
        manifest,
        output_dir=output_dir,
        docs_json_path=docs_json_path,
        dropdown_name=args.dropdown,
        group_name=args.group,
    )

    print(f"Canton repo: {canton_repo_dir}")
    print(f"Manifest: {output_dir / 'manifest.json'}")
    print(f"MDX: {index_path}")
    print(f"Cache: {workdir}")
    if updated_docs_json is not None:
        print(f"docs.json: {updated_docs_json}")


if __name__ == "__main__":
    main()

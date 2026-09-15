"""Read declaration annotations from Javadoc and Scala 2.13 Scaladoc HTML."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from collections.abc import Iterator
from html.parser import HTMLParser


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    children: list[Element | str] = field(default_factory=list)

    def text(self) -> str:
        return "".join(
            child if isinstance(child, str) else child.text() for child in self.children
        )

    def elements(self) -> Iterator[Element]:
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.elements()

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()


class DocParser(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = Element("root", {})
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def marker_state(text: str) -> str | None:
    states = {
        match.lower()
        for match in re.findall(r"@(?:[\w$]+\.)*(Alpha|Beta|Stable)(?![\w$.])", text)
    }
    if len(states) > 1:
        raise ValueError(
            f"Conflicting JVM lifecycle annotations: {', '.join(sorted(states))}"
        )
    return next(iter(states), None)


def scala_metadata(node: Element) -> tuple[str | None, str | None]:
    annotations: list[str] = []
    deprecated = None
    for element in node.elements():
        if element.tag != "dl":
            continue
        label = ""
        for child in element.children:
            if not isinstance(child, Element):
                continue
            if child.tag == "dt":
                label = child.text().strip()
            elif child.tag == "dd" and label == "Annotations":
                # Only annotation-name spans: argument strings and prose are not markers.
                annotations.extend(
                    n.text() for n in child.elements() if n.has_class("name")
                )
            elif child.tag == "dd" and label == "Deprecated":
                deprecated = " ".join(child.text().split())
    return marker_state(" ".join(annotations)), deprecated


def doc_annotations(
    source: str, *, language: str
) -> dict[str, tuple[str | None, str | None]]:
    root = DocParser(source).root
    result: dict[str, tuple[str | None, str | None]] = {}
    if language == "java":
        for node in root.elements():
            if node.has_class("type-signature"):
                result[""] = java_metadata(node)
            elif node.tag == "section" and node.has_class("detail"):
                signature = next(
                    (n for n in node.elements() if n.has_class("member-signature")),
                    None,
                )
                if signature is not None:
                    result[node.attrs.get("id", "")] = java_metadata(signature)
    else:
        for node in root.elements():
            if node.attrs.get("id") == "comment" and node.has_class("fullcommenttop"):
                result[""] = scala_metadata(node)
            elif node.tag == "li" and "name" in node.attrs:
                metadata = scala_metadata(node)
                for anchor in node.elements():
                    if anchor.tag == "a" and anchor.has_class("anchorToMember"):
                        result[anchor.attrs.get("id", "")] = metadata
    return result


def java_metadata(signature: Element) -> tuple[str | None, str | None]:
    annotations = " ".join(
        node.text() for node in signature.elements() if node.has_class("annotations")
    )
    deprecated = re.search(
        r"@(?:java\.lang\.)?Deprecated\b(?:\((.*?)\))?", annotations, re.S
    )
    note = None
    if deprecated:
        since = re.search(r'\bsince\s*=\s*"([^"\n]+)"', deprecated.group(1) or "")
        note = f"Deprecated since {since.group(1)}" if since else "Deprecated"
    # Strip string arguments so text such as @Description("@Alpha") cannot mark an API.
    annotations = re.sub(r'"(?:\\.|[^"\\])*"', '""', annotations)
    return marker_state(annotations), note

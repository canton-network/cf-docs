// Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates.
// SPDX-License-Identifier: Apache-2.0

package convert

import (
	"regexp"
	"strings"
)

// RST admonitions wrap short callouts. Mintlify has Note/Tip/Warning/Info
// JSX components that render as colored boxes. The mapping (per the
// migration guide):
//
//	.. note::        → <Note>
//	.. attention::   → <Note>
//	.. tip::         → <Tip>
//	.. hint::        → <Tip>
//	.. warning::     → <Warning>
//	.. caution::     → <Warning>
//	.. danger::      → <Warning>  (prefixed "**Danger:** ")
//	.. important::   → <Warning>  (prefixed "**Important:** ")
//	.. seealso::     → <Info>
//	.. deprecated::  → <Warning>  (version note prefix)
//	.. versionadded:: → <Note>    (version note prefix)
//	.. versionchanged:: → <Note>  (version note prefix)
//
// Some admonitions have content on the same line (inline) and some have
// an indented block that follows. We handle both.

type admonitionSpec struct {
	kind    string // RST directive name, without ::
	tag     string // JSX component name (Note, Tip, Warning, Info)
	prefix  string // optional body prefix like "**Important:** "
	argBold bool   // if true, emit the directive argument as bold prefix
}

var admonitions = []admonitionSpec{
	{kind: "note", tag: "Note"},
	{kind: "attention", tag: "Note"},
	{kind: "tip", tag: "Tip"},
	{kind: "hint", tag: "Tip"},
	{kind: "warning", tag: "Warning"},
	{kind: "caution", tag: "Warning"},
	{kind: "danger", tag: "Warning", prefix: "**Danger:** "},
	{kind: "important", tag: "Warning", prefix: "**Important:** "},
	{kind: "seealso", tag: "Info"},
	{kind: "deprecated", tag: "Warning", argBold: true},
	{kind: "versionadded", tag: "Note", argBold: true},
	{kind: "versionchanged", tag: "Note", argBold: true},
}

// convertAdmonitions walks the input line-by-line and rewrites RST
// admonition directives into JSX component blocks.
func convertAdmonitions(s string) string {
	lines := strings.Split(s, "\n")
	var out []string

	// Precompile the directive matchers for speed and to capture the
	// indent + optional argument.
	matchers := make(map[string]*regexp.Regexp, len(admonitions))
	for _, a := range admonitions {
		matchers[a.kind] = regexp.MustCompile(
			`^(\s*)\.\.\s+` + regexp.QuoteMeta(a.kind) + `::\s*(.*)$`)
	}

	i := 0
	for i < len(lines) {
		line := lines[i]
		matched := false
		for _, a := range admonitions {
			m := matchers[a.kind].FindStringSubmatch(line)
			if m == nil {
				continue
			}
			indent := m[1]
			arg := strings.TrimSpace(m[2])
			i++

			body, consumed := collectAdmonitionBody(lines[i:], indent, arg, a)
			i += consumed

			out = append(out, indent+"<"+a.tag+">")
			out = append(out, body...)
			out = append(out, indent+"</"+a.tag+">")
			matched = true
			break
		}
		if matched {
			continue
		}
		out = append(out, line)
		i++
	}
	return strings.Join(out, "\n")
}

// collectAdmonitionBody gathers the indented content (or inline arg) of
// an admonition. It returns the body lines, dedented and with the
// configured prefix applied, plus how many input lines were consumed.
func collectAdmonitionBody(lines []string, parentIndent, arg string, a admonitionSpec) ([]string, int) {
	// Inline form: `.. note:: some text` puts the content on the same
	// line; no indented block follows.
	if arg != "" {
		body := arg
		switch {
		case a.argBold:
			body = "**" + a.prefix + capitalize(a.kind) + " " + arg + ":** "
			// The argument is usually a version; any text that
			// follows it lives in the indented block below.
		case a.prefix != "":
			body = a.prefix + arg
		}
		// Check whether there's ALSO an indented block; if so, merge.
		indented, consumed := consumeIndentedBlock(lines, parentIndent)
		if len(indented) == 0 {
			return []string{body}, consumed
		}
		var combined []string
		combined = append(combined, body)
		combined = append(combined, indented...)
		return combined, consumed
	}

	// Block form: indented lines after a blank separator.
	// Skip blank separator(s).
	skip := 0
	for skip < len(lines) && strings.TrimSpace(lines[skip]) == "" {
		skip++
	}
	body, consumed := consumeIndentedBlock(lines[skip:], parentIndent)
	if a.prefix != "" && len(body) > 0 {
		body[0] = a.prefix + body[0]
	}
	return body, skip + consumed
}

func capitalize(s string) string {
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}

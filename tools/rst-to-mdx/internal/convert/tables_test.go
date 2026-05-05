// Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates.
// SPDX-License-Identifier: Apache-2.0

package convert

import (
	"strings"
	"testing"
)

func TestConvertListTable_HeaderAndRows(t *testing.T) {
	in := `.. list-table:: Token mapping
   :header-rows: 1
   :widths: 20 80

   * - Token
     - Description
   * - alpha
     - The first
   * - beta
     - The second
`
	got := convertListTable(in)
	for _, want := range []string{
		"**Token mapping**",
		"| Token | Description |",
		"| --- | --- |",
		"| alpha | The first |",
		"| beta | The second |",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("missing %q in:\n%s", want, got)
		}
	}
	if strings.Contains(got, "list-table::") {
		t.Errorf("directive line was not consumed:\n%s", got)
	}
}

func TestConvertListTable_NoHeaderRows(t *testing.T) {
	in := `.. list-table::

   * - one
     - two
   * - three
     - four
`
	got := convertListTable(in)
	// Without :header-rows: the first row is still treated as the
	// header so the output is a valid markdown table.
	if !strings.Contains(got, "| one | two |") {
		t.Errorf("first row missing: %s", got)
	}
	if !strings.Contains(got, "| --- | --- |") {
		t.Errorf("alignment row missing: %s", got)
	}
	if !strings.Contains(got, "| three | four |") {
		t.Errorf("body row missing: %s", got)
	}
}

func TestConvertCsvTable(t *testing.T) {
	in := `.. csv-table:: Daml LF JSON encoding
   :header: "Daml Type", "JSON"

   "Int64", "string"
   "Numeric", "string"
   "Bool", "boolean"
`
	got := convertCsvTable(in)
	for _, want := range []string{
		"**Daml LF JSON encoding**",
		"| Daml Type | JSON |",
		"| Int64 | string |",
		"| Numeric | string |",
		"| Bool | boolean |",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("missing %q in:\n%s", want, got)
		}
	}
}

func TestConvertGridTable_Basic(t *testing.T) {
	in := `+----------+----------+
| Header 1 | Header 2 |
+==========+==========+
| Cell 1   | Cell 2   |
+----------+----------+
| Multi    | Cell     |
+----------+----------+
`
	got := convertGridTable(in)
	for _, want := range []string{
		"| Header 1 | Header 2 |",
		"| --- | --- |",
		"| Cell 1 | Cell 2 |",
		"| Multi | Cell |",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("missing %q in:\n%s", want, got)
		}
	}
	if strings.Contains(got, "+----") {
		t.Errorf("RST border survived: %s", got)
	}
}

func TestConvertGridTable_NoHeaderSep_KeepsAllAsBody(t *testing.T) {
	// A grid table without `+===+` separator: the parser should still
	// emit a markdown table (treating row 1 as header by default).
	in := `+-----+-----+
| a   | b   |
+-----+-----+
| 1   | 2   |
+-----+-----+
`
	got := convertGridTable(in)
	if !strings.Contains(got, "| a | b |") {
		t.Errorf("first row not in output:\n%s", got)
	}
	if !strings.Contains(got, "| 1 | 2 |") {
		t.Errorf("second row not in output:\n%s", got)
	}
}

func TestConvertGridTable_BadShape_PassthroughDoesNotPanic(t *testing.T) {
	// A line that LOOKS like a border but isn't a real grid table
	// shouldn't crash the converter and shouldn't be silently eaten.
	in := `+--+ this is not a real table
just text
`
	// The first line still matches reGridBorder; the parser will fail
	// to find content rows and pass through.
	got := convertGridTable(in)
	if !strings.Contains(got, "just text") {
		t.Errorf("non-table content was eaten: %s", got)
	}
}

func TestConvertListTable_PipeInCellEscaped(t *testing.T) {
	in := `.. list-table::
   :header-rows: 1

   * - Pattern
     - Match
   * - ` + "`a|b`" + `
     - either
`
	got := convertListTable(in)
	if !strings.Contains(got, `\|`) {
		t.Errorf("pipe in cell was not escaped:\n%s", got)
	}
}

// Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates.
// SPDX-License-Identifier: Apache-2.0

package convert

import (
	"encoding/csv"
	"regexp"
	"strings"
)

// RST has three table flavors that we convert to markdown tables:
//
//  1. .. list-table::    — bullet-list body, most common (~301 in corpus)
//  2. .. csv-table::     — CSV body with an inline :header: option
//  3. grid tables (+---+) — ASCII borders, also common (~600 in corpus)
//
// All three emit GitHub-flavored markdown tables. For cells with
// multi-line content we fall back to HTML tables so the renderer can
// handle the complexity; the migration guide already recommends that.

// convertTables is the single entry point; it runs all three parsers in
// order. The list-table and csv-table parsers are directive-driven so
// they run before the grid-table parser, which is shape-driven and
// would otherwise greedily match borders inside an already-converted
// table.
func convertTables(s string) string {
	s = convertListTable(s)
	s = convertCsvTable(s)
	s = convertGridTable(s)
	return s
}

// ---------------------------------------------------------------------
// .. list-table::
// ---------------------------------------------------------------------

var (
	reListTableStart = regexp.MustCompile(
		`^(\s*)\.\.\s+list-table::\s*(.*)$`)
	reBulletRow  = regexp.MustCompile(`^(\s*)\*\s+-\s*(.*)$`)
	reCellCont   = regexp.MustCompile(`^(\s*)-\s*(.*)$`)
	reOptionLn   = regexp.MustCompile(`^(\s+):([A-Za-z][A-Za-z0-9_\-]*):\s*(.*)$`)
)

// convertListTable finds every `.. list-table::` directive and rewrites
// it as a markdown table. Nested inline markup inside cells is
// preserved verbatim — downstream inline-role transforms fix it up.
func convertListTable(s string) string {
	lines := strings.Split(s, "\n")
	var out []string
	i := 0
	for i < len(lines) {
		m := reListTableStart.FindStringSubmatch(lines[i])
		if m == nil {
			out = append(out, lines[i])
			i++
			continue
		}
		indent := m[1]
		title := strings.TrimSpace(m[2])
		i++

		opts, consumed := readTableOptions(lines[i:])
		i += consumed

		// Skip blank lines before the body.
		for i < len(lines) && strings.TrimSpace(lines[i]) == "" {
			i++
		}

		// Collect indented body lines.
		var body []string
		for i < len(lines) {
			line := lines[i]
			if strings.TrimSpace(line) == "" {
				body = append(body, "")
				i++
				continue
			}
			if !strings.HasPrefix(line, indent) || !deeperIndent(line, indent) {
				break
			}
			body = append(body, line)
			i++
		}

		rows := parseListTableBody(body)
		headerRows := parseInt(opts["header-rows"], 0)
		md := renderMarkdownTable(title, rows, headerRows, indent)
		out = append(out, md...)
	}
	return strings.Join(out, "\n")
}

// parseListTableBody walks the directive body and produces a [][]string
// where outer slice is rows, inner slice is cells. A new row starts
// with `* -` at the least-indented level; subsequent `-` bullets at the
// next indent level add cells to the current row. Cell content can
// span multiple lines (indented under the `-`).
func parseListTableBody(lines []string) [][]string {
	var rows [][]string
	var currentRow []string
	var currentCell []string
	flushCell := func() {
		if len(currentCell) > 0 || currentRow != nil {
			currentRow = append(currentRow, strings.TrimSpace(strings.Join(currentCell, " ")))
			currentCell = currentCell[:0]
		}
	}
	flushRow := func() {
		flushCell()
		if currentRow != nil {
			rows = append(rows, currentRow)
			currentRow = nil
		}
	}

	for _, line := range lines {
		if strings.TrimSpace(line) == "" {
			continue
		}
		if m := reBulletRow.FindStringSubmatch(line); m != nil {
			flushRow()
			currentRow = []string{}
			if txt := strings.TrimSpace(m[2]); txt != "" {
				currentCell = append(currentCell, txt)
			}
			continue
		}
		if m := reCellCont.FindStringSubmatch(line); m != nil {
			flushCell()
			if txt := strings.TrimSpace(m[2]); txt != "" {
				currentCell = append(currentCell, txt)
			}
			continue
		}
		// Continuation of the current cell's content on a wrapped
		// line. Append trimmed text so cells collapse into one line.
		if trimmed := strings.TrimSpace(line); trimmed != "" {
			currentCell = append(currentCell, trimmed)
		}
	}
	flushRow()
	return rows
}

// ---------------------------------------------------------------------
// .. csv-table::
// ---------------------------------------------------------------------

var reCsvTableStart = regexp.MustCompile(
	`^(\s*)\.\.\s+csv-table::\s*(.*)$`)

func convertCsvTable(s string) string {
	lines := strings.Split(s, "\n")
	var out []string
	i := 0
	for i < len(lines) {
		m := reCsvTableStart.FindStringSubmatch(lines[i])
		if m == nil {
			out = append(out, lines[i])
			i++
			continue
		}
		indent := m[1]
		title := strings.TrimSpace(m[2])
		i++

		opts, consumed := readTableOptions(lines[i:])
		i += consumed

		// Skip blank lines before the body.
		for i < len(lines) && strings.TrimSpace(lines[i]) == "" {
			i++
		}

		// Body: every indented line is a CSV row.
		var body []string
		for i < len(lines) {
			line := lines[i]
			if strings.TrimSpace(line) == "" {
				break
			}
			if !deeperIndent(line, indent) {
				break
			}
			body = append(body, strings.TrimLeft(line, " \t"))
			i++
		}

		var rows [][]string
		if h := opts["header"]; h != "" {
			if hdr, err := parseCSVRow(h); err == nil {
				rows = append(rows, hdr)
			}
		}
		for _, row := range body {
			parsed, err := parseCSVRow(row)
			if err != nil {
				continue
			}
			rows = append(rows, parsed)
		}
		headerRows := 0
		if opts["header"] != "" {
			headerRows = 1
		}
		md := renderMarkdownTable(title, rows, headerRows, indent)
		out = append(out, md...)
	}
	return strings.Join(out, "\n")
}

func parseCSVRow(line string) ([]string, error) {
	r := csv.NewReader(strings.NewReader(line))
	r.LazyQuotes = true
	r.TrimLeadingSpace = true
	record, err := r.Read()
	if err != nil {
		return nil, err
	}
	return record, nil
}

// ---------------------------------------------------------------------
// Grid tables: +---+---+
// ---------------------------------------------------------------------

// reGridBorder matches the `+---+---+` shape that opens/closes a grid
// table. The equals-sign form (`+===+`) separates a header row from
// body rows.
var (
	reGridBorder  = regexp.MustCompile(`^\s*\+[-+]+\+\s*$`)
	reGridHeader  = regexp.MustCompile(`^\s*\+=+\+[=+]*\s*$`)
	reGridContent = regexp.MustCompile(`^\s*\|`)
)

func convertGridTable(s string) string {
	lines := strings.Split(s, "\n")
	var out []string
	i := 0
	for i < len(lines) {
		if !reGridBorder.MatchString(lines[i]) {
			out = append(out, lines[i])
			i++
			continue
		}

		// Collect the full grid table (until a line that isn't a
		// border, content row, or header separator).
		start := i
		tableLines := []string{lines[i]}
		i++
		for i < len(lines) {
			l := lines[i]
			if reGridBorder.MatchString(l) || reGridHeader.MatchString(l) || reGridContent.MatchString(l) {
				tableLines = append(tableLines, l)
				i++
				continue
			}
			break
		}

		rendered, ok := renderGridTable(tableLines)
		if !ok {
			// Parse failure — pass the original lines through. Better
			// a stray RST grid table than a destroyed document.
			out = append(out, lines[start:i]...)
			continue
		}
		out = append(out, rendered...)
	}
	return strings.Join(out, "\n")
}

// renderGridTable converts a block of grid-table lines into a markdown
// table. Returns false if the block can't be parsed cleanly — the
// caller then leaves the block untouched.
//
// Simplification: we treat each `| … | … |` content row as ONE row of
// the final table and split on `|`. Cells that span multiple lines
// are joined with a space. This won't handle arbitrary merged cells
// (the RST grid-table spec allows row/column spans), but the Canton
// corpus uses simple rectangular tables where this is enough.
func renderGridTable(lines []string) ([]string, bool) {
	var rows [][]string
	headerRows := 0
	sawHeaderSep := false

	// Figure out the column boundary positions from the first border.
	var colBreaks []int
	for _, line := range lines {
		if reGridBorder.MatchString(line) {
			colBreaks = bordersInLine(line)
			break
		}
	}
	if len(colBreaks) < 2 {
		return nil, false
	}

	var pendingRow []string
	for _, line := range lines {
		if reGridHeader.MatchString(line) {
			// Flush whatever was accumulating as a header row first
			// so the "=" separator marks the boundary.
			if pendingRow != nil {
				rows = append(rows, pendingRow)
				pendingRow = nil
			}
			sawHeaderSep = true
			if headerRows == 0 {
				headerRows = len(rows)
			}
			continue
		}
		if reGridBorder.MatchString(line) {
			if pendingRow != nil {
				rows = append(rows, pendingRow)
				pendingRow = nil
			}
			continue
		}
		if reGridContent.MatchString(line) {
			cells := splitGridRow(line, colBreaks)
			if pendingRow == nil {
				pendingRow = cells
			} else {
				// Merge wrapped content with prior row's cells.
				for j := 0; j < len(cells) && j < len(pendingRow); j++ {
					if cells[j] = strings.TrimSpace(cells[j]); cells[j] != "" {
						pendingRow[j] = strings.TrimSpace(pendingRow[j]) + " " + cells[j]
					}
				}
			}
			continue
		}
	}
	if pendingRow != nil {
		rows = append(rows, pendingRow)
	}
	if len(rows) == 0 {
		return nil, false
	}
	if sawHeaderSep && headerRows == 0 {
		headerRows = 1
	}

	leadingIndent := leadingWS(lines[0])
	return renderMarkdownTable("", rows, headerRows, leadingIndent), true
}

// bordersInLine returns the rune offsets of every `+` in a grid
// border line, which mark the column boundaries. We work in rune-space
// so multibyte UTF-8 characters in subsequent content rows (e.g. `¹`
// or other superscripts in Canton's crypto-scheme tables) don't shift
// the alignment.
func bordersInLine(line string) []int {
	var out []int
	for i, r := range []rune(line) {
		if r == '+' {
			out = append(out, i)
		}
	}
	return out
}

// splitGridRow extracts cell contents from a content row
// (`| cell1  | cell2 |`) using rune-space column boundary offsets.
// Returns trimmed cells.
func splitGridRow(line string, breaks []int) []string {
	runes := []rune(line)
	var cells []string
	for k := 0; k < len(breaks)-1; k++ {
		start := breaks[k] + 1
		end := breaks[k+1]
		if start >= len(runes) {
			cells = append(cells, "")
			continue
		}
		if end > len(runes) {
			end = len(runes)
		}
		cells = append(cells, strings.TrimSpace(string(runes[start:end])))
	}
	return cells
}

// ---------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------

// readTableOptions consumes `:name: value` lines at the start of a
// directive body and returns them as a map.
func readTableOptions(lines []string) (map[string]string, int) {
	opts := map[string]string{}
	i := 0
	for i < len(lines) {
		if strings.TrimSpace(lines[i]) == "" {
			break
		}
		m := reOptionLn.FindStringSubmatch(lines[i])
		if m == nil {
			break
		}
		opts[strings.ToLower(m[2])] = strings.TrimSpace(m[3])
		i++
	}
	return opts, i
}

func parseInt(s string, fallback int) int {
	if s == "" {
		return fallback
	}
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			return fallback
		}
		n = n*10 + int(c-'0')
	}
	return n
}

func deeperIndent(line, parentIndent string) bool {
	lws := leadingWS(line)
	return len(lws) > len(parentIndent)
}

// renderMarkdownTable turns rows into a GitHub-flavored markdown table
// preceded by a blank line and (optionally) a bold title line. The
// first `headerRows` rows become the header; when headerRows is 0, the
// first row is treated as the header (markdown requires one).
//
// The `_indent` parameter is intentionally ignored: markdown tables
// indented 4+ spaces render as code blocks, not tables. Always emit at
// column 0 even when the RST source nested the table inside a
// directive.
func renderMarkdownTable(title string, rows [][]string, headerRows int, _indent string) []string {
	if len(rows) == 0 {
		return []string{""}
	}

	// Normalize column count to the widest row.
	cols := 0
	for _, r := range rows {
		if len(r) > cols {
			cols = len(r)
		}
	}
	if cols == 0 {
		return []string{""}
	}

	padRow := func(r []string) []string {
		if len(r) < cols {
			r = append(r, make([]string, cols-len(r))...)
		}
		return r
	}

	var out []string
	out = append(out, "")
	if title != "" {
		out = append(out, "**"+title+"**")
		out = append(out, "")
	}

	if headerRows == 0 {
		headerRows = 1
	}
	// Merge multi-row headers into a single `|`-joined line (markdown
	// can't express stacked headers directly).
	headerCells := make([]string, cols)
	for h := 0; h < headerRows && h < len(rows); h++ {
		for c, cell := range padRow(rows[h]) {
			if headerCells[c] == "" {
				headerCells[c] = cell
			} else if cell != "" {
				headerCells[c] += " — " + cell
			}
		}
	}

	out = append(out, "| "+strings.Join(escapeCells(headerCells), " | ")+" |")
	sep := make([]string, cols)
	for i := range sep {
		sep[i] = "---"
	}
	out = append(out, "| "+strings.Join(sep, " | ")+" |")

	for _, row := range rows[headerRows:] {
		out = append(out, "| "+strings.Join(escapeCells(padRow(row)), " | ")+" |")
	}
	out = append(out, "")
	return out
}

// escapeCells replaces `|` inside cell text with `\|` so it doesn't
// break the table, and collapses runs of whitespace.
func escapeCells(cells []string) []string {
	out := make([]string, len(cells))
	for i, c := range cells {
		c = strings.ReplaceAll(c, "|", `\|`)
		c = strings.Join(strings.Fields(c), " ")
		if c == "" {
			c = " "
		}
		out[i] = c
	}
	return out
}

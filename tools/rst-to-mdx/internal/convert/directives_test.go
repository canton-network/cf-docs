// Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates.
// SPDX-License-Identifier: Apache-2.0

package convert

import "testing"

func TestStripCopyrightHeader(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{
			name: "copyright + SPDX",
			in: `..
   Copyright (c) 2026 Digital Asset.
..
   SPDX-License-Identifier: Apache-2.0

Content
`,
			want: `{/* Copyright (c) 2026 Digital Asset. — SPDX-License-Identifier: Apache-2.0 */}

Content
`,
		},
		{
			name: "copyright only",
			in: `..
   Copyright (c) 2026 Digital Asset.

Content
`,
			want: `{/* Copyright (c) 2026 Digital Asset. */}

Content
`,
		},
		{
			name: "no header passes through",
			in: `Content starts immediately
`,
			want: `Content starts immediately
`,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := stripCopyrightHeader(tc.in)
			if got != tc.want {
				t.Errorf("mismatch\nwant:\n%q\n got:\n%q", tc.want, got)
			}
		})
	}
}

func TestStripSimpleDirectives(t *testing.T) {
	// `.. todo::` is intentionally NOT stripped here — convertTodo
	// renders it as a visible Note so the body isn't lost.
	in := `:orphan:

.. contents:: Table of contents
   :depth: 2
   :local:

.. toctree::
   :maxdepth: 2

   tutorials/install
   tutorials/first-steps

Real content follows.
`
	got := stripSimpleDirectives(in)
	if got == in {
		t.Fatal("directives were not stripped")
	}
	for _, banned := range []string{":orphan:", "contents::", "toctree::"} {
		if contains(got, banned) {
			t.Errorf("%q still present in:\n%s", banned, got)
		}
	}
	if !contains(got, "Real content follows.") {
		t.Errorf("real content was eaten:\n%s", got)
	}
}

func TestStripLabels(t *testing.T) {
	in := `.. _canton-getting-started:

Getting Started
===============
`
	want := `Getting Started
===============
`
	if got := stripLabels(in); got != want {
		t.Errorf("want:\n%q\n got:\n%q", want, got)
	}
}

func TestConvertRubric(t *testing.T) {
	in := `.. rubric:: Footnotes`
	want := `**Footnotes**`
	if got := convertRubric(in); got != want {
		t.Errorf("want %q got %q", want, got)
	}
}

func TestConvertRawHTMLVideo_CantonDemoPattern(t *testing.T) {
	in := `.. raw:: html

    <video id="clip" controls="controls" preload="none" onclick="this.paused ? this.play() : this.pause();" width=640 height=400 data-setup="{}">
        <source src="https://www.canton.io/videos/canton-demo.mp4" type='video/mp4'/>
    </video>
`
	got := convertRawHTMLVideo(in)
	want := `<video src="https://www.canton.io/videos/canton-demo.mp4" controls width="640" height="400" />
`
	if got != want {
		t.Errorf("mismatch\nwant:\n%q\n got:\n%q", want, got)
	}
}

func TestConvertRawHTMLVideo_NonVideoPassesThrough(t *testing.T) {
	in := `.. raw:: html

    <div class="custom">hello</div>

After.
`
	if got := convertRawHTMLVideo(in); got != in {
		t.Errorf("non-video raw block was rewritten:\n%s", got)
	}
}

func TestConvertRawHTMLVideo_MultipleSources(t *testing.T) {
	in := `.. raw:: html

    <video controls width=320 height=240>
      <source src="a.mp4" type="video/mp4">
      <source src="b.webm" type="video/webm">
    </video>
`
	got := convertRawHTMLVideo(in)
	for _, want := range []string{
		`<video controls width="320" height="240">`,
		`<source src="a.mp4" type="video/mp4" />`,
		`<source src="b.webm" type="video/webm" />`,
		`</video>`,
	} {
		if !contains(got, want) {
			t.Errorf("missing %q in:\n%s", want, got)
		}
	}
}

func TestConvertTodo_InlineSummaryWithAutolink(t *testing.T) {
	// The inline summary often contains a `<https://...>` autolink.
	// convertTodo preserves the summary verbatim; convertLinks runs
	// later in the pipeline to rewrite the autolink. This test covers
	// just the convertTodo half — the autolink rewrite is asserted in
	// links_test.go.
	in := `.. todo:: Write this section <https://github.com/DACH-NY/canton/issues/25689>
`
	got := convertTodo(in)
	want := "<Note>\n**TODO:** Write this section <https://github.com/DACH-NY/canton/issues/25689>\n</Note>"
	if !contains(got, want) {
		t.Errorf("want substring:\n%s\ngot:\n%s", want, got)
	}
}

// contains is a local helper so we don't import strings just for Contains
// in tests — keeps the file self-contained.
func contains(haystack, needle string) bool {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}

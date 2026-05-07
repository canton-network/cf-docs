// Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates.
// SPDX-License-Identifier: Apache-2.0

package convert

import "regexp"

// After the code-block transform emits fenced sections, we normalize the
// language tags to what Mintlify / Shiki expects:
//
//	none     → text
//	console  → bash   (treated as shell session)
//	haskell  → daml   (Daml was historically tagged haskell; the
//	                   migration guide calls this out as a class of bug)

var (
	reLangNone    = regexp.MustCompile("(?m)^(\\s*)```none\\b")
	reLangConsole = regexp.MustCompile("(?m)^(\\s*)```console\\b")
	reLangHaskell = regexp.MustCompile("(?m)^(\\s*)```haskell\\b")
)

func normalizeLanguages(s string) string {
	s = reLangNone.ReplaceAllString(s, "$1```text")
	s = reLangConsole.ReplaceAllString(s, "$1```bash")
	s = reLangHaskell.ReplaceAllString(s, "$1```daml")
	return s
}

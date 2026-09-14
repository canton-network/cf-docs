# PR body attachment test

Purpose: verify that a cf-docs draft PR can display an uploaded screenshot in its body without adding an image to the branch diff.

This test-only draft is not intended to merge. Its sole changed file is this note.

Steps:
1. Create a draft with GitHub CLI attachment support.
2. Verify that the body contains a GitHub attachment URL and that the diff contains only this note.
3. Retain the draft and worktree for user review; clean up after acceptance.

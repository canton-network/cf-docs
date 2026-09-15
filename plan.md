# PR body attachment test

Purpose: verify that a cf-docs draft PR can display an uploaded screenshot in its body without adding an image to the branch diff.

This test-only draft is not intended to merge. Its sole changed file is this note.

Verified on 2026-09-14:
1. Draft PR: https://github.com/canton-network/cf-docs/pull/1670
2. GitHub CLI 2.100.0 uploaded the existing screenshot with `gh pr create --attach`; installed 2.90.0 lacks this flag.
3. The saved body references `https://github.com/user-attachments/assets/a0ce4e61-a080-4f6e-b2e1-fa7875dd2806`.
4. GitHub reports the PR as a draft and this note as its only changed file.

Next: retain the draft and worktree for user review; clean up after acceptance.

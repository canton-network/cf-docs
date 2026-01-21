Copyright (c) 2025 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
SPDX-License-Identifier: Apache-2.0

docs
====

This repo manages the contents of the docs.canton.network website.

Local preview
=============

Run `mintlify dev` to preview the docs site locally.

System dependencies
===================

This repo uses direnv + Nix to provide a consistent Node.js toolchain.

Required:
- `direnv` (to auto-load the Nix shell via `.envrc`)
- `nix` (to provide Node.js 23 and install the Mintlify CLI)

After installing those, run `direnv allow` once in this repo. The shell will
install npm dependencies on first load, so `mintlify dev` is available.

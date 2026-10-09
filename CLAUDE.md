# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

This repository is at its starting point: the only file is `mise.toml`. No source code, build system, tests, or dependencies exist yet. Update this file as the project takes shape (build/test commands, architecture).

## Toolchain

- Python 3.11, pinned via [mise](https://mise.jdx.dev/) in `mise.toml`. Run `mise install` to get the interpreter; `mise exec -- python ...` (or an activated mise shell) to use it.

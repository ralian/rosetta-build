# Changelog

## [0.1.1] — 2026-09-24

Self-hosting packaging release: Rosetta builds itself.

### Changed

- Switched `[build-system]` from `uv_build` to `rosetta-build>=0.1.0` with
  `build-backend = "rosetta_build.backend"`.
- Added a `WheelTarget` for this repo (`src/target.toml` → `src/rosetta_build`)
  under `[tool.rosetta-build]`.
- Dropped unused `[tool.uv.build-backend]` configuration.

### Added

- PEP 660 editable install hooks (`build_editable`,
  `prepare_metadata_for_build_editable`, `get_requires_for_build_editable`)
  using a `.pth` pointing at package source parents.
- Wheel assembler copies `[project] license-files` into
  `.dist-info/licenses/` (PEP 639 layout, matching uv_build).

## [0.1.0] — 2026-09-24

Initial public release on PyPI.

### Packaging

- Pure-Python `WheelTarget` planning and execution (wheel + sdist).
- PEP 517 build backend (`rosetta_build.backend`) and PEP 621 metadata
  loading for build-backend usage.
- Source-tree-relative sdists so unpacked trees remain rebuildable via
  `collect()`.
- Project metadata for PyPI: license, classifiers, keywords, URLs, and
  uv build-backend layout.

### Collection and graph

- Target schemas and CLI for collecting build targets from
  `[tool.rosetta-build]`.
- Executable, static library, and dynamic library target types, with
  cycle detection and fixture trees.
- Graphviz output for the target graph.
- Git dependency provider with optional `sha256:` checkout pinning.

### Modules (C++)

- First-class module interface, partition, and implementation targets in
  the graph.
- Cross-target module visibility rules.
- Compile-stage handling of built module interfaces (BMI).
- P1689 dependency interchange format support.

### Compilation and planning

- Compiler API surface and stubs for planned toolchains.
- Basic g++ implementation with C++ modules.
- Planner and executor for native GCC/g++ builds (compile, link).

### Docs

- Conversion outlines for non-module and modules-first C++ projects.

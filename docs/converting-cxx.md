# Converting a C++ project (no modules)

Map a traditional header-and-`.cpp` tree onto rosetta’s collection model: one root
`pyproject.toml`, plus one `target.toml` per artifact.

Build (`compile` / `link`) is still evolving; start by making `rosetta-build collect`
succeed. See also [converting-cxx-modules.md](converting-cxx-modules.md) if you use
`import` / `export module`.

---

## 1. Root `pyproject.toml`

At the source-tree root:

```toml
[project]
name = "my-app"
version = "0.1.0"

[tool.rosetta-build]
targets = [
  "libs/core/target.toml",
  "libs/plugin/target.toml",
  "apps/hello/target.toml",
]
```

Paths are **source-tree relative**. Every native artifact you want collected must
appear in this list.

Optional git deps (FetchContent-style) go under
`[tool.rosetta-build.dependencies]`; see the schema in `schema.py`.

---

## 2. One `target.toml` per artifact

| Old idea (CMake / Make) | Rosetta `type` |
|-------------------------|----------------|
| `add_executable` | `executable` |
| `add_library(… STATIC)` | `static_library` |
| `add_library(… SHARED)` | `dynamic_library` |

Minimal executable:

```toml
type = "executable"
language = "cxx"
name = "hello"
sources = ["main.cpp"]
link_libraries = ["core"]
```

Minimal static library:

```toml
type = "static_library"
language = "cxx"
name = "core"
sources = ["core.cpp"]
include_dirs = ["include"]
compile_defs = { NDEBUG = true, VERSION = 2 }
compile_opts = ["-Wall"]
```

`sources`, `include_dirs`, and similar paths are relative to the directory that
contains that `target.toml`.

### Field cheat sheet

| Field | Maps from | Notes |
|-------|-----------|--------|
| `name` | target / lib name | Unique across the tree |
| `language` | `CXX` | Use `"cxx"` (or `"c"` for C) |
| `sources` | `target_sources` / `SOURCES` | Explicit list; no globs yet |
| `include_dirs` | `target_include_directories` | Become portable `-I` / `/I` |
| `compile_defs` | `target_compile_definitions` | `true` → define; `false` → undef; other → `NAME=value` |
| `compile_opts` | `target_compile_options` | Raw flags (escape hatch) |
| `link_opts` | `target_link_options` | Raw linker flags |
| `usage` | interface / “uses headers from” | Soft dep; **cycles allowed** |
| `link_libraries` | `target_link_libraries` | Must name other collected targets |

Leave `module_visibility` empty for non-module projects.

---

## 3. Edges: `usage` vs `link_libraries`

Rosetta splits two graphs that CMake often conflates:

- **`usage`** — “I need this target’s headers / interface.” Cycles are fine
  (two static libs that include each other’s headers).
- **`link_libraries`** — “Link my object code against that target.”

Hard **dynamic-link** edges (A lists B and B is a `dynamic_library`) must form a
**DAG**. Static-only link refs are recorded but not cycle-checked the same way.

Typical mapping:

```text
exe  --link_libraries-->  static_lib, shared_lib
shared_lib --link_libraries--> static_lib
static_a --usage--> static_b   (and maybe the reverse)
```

---

## 4. Suggested layout

Mirror the product, not the build system:

```text
my-app/
  pyproject.toml
  apps/hello/
    target.toml
    main.cpp
  libs/core/
    target.toml
    core.cpp
    include/core.h
  libs/plugin/
    target.toml
    plugin.cpp
```

One translation unit set per target is enough; split libraries the way you
already split link units.

---

## 5. From CMake, briefly

1. Each `add_executable` / `add_library` → one `target.toml` + list it in
   `tool.rosetta-build.targets`.
2. Copy `SOURCES` and public include dirs into `sources` / `include_dirs`.
3. Put compile definitions in `compile_defs`; keep toolchain-specific `-W` /
   `-O` flags in `compile_opts` until portable options cover them.
4. Split `target_link_libraries` PUBLIC/INTERFACE vs link needs into `usage`
   vs `link_libraries`.
5. Drop generated `compile_commands` / custom commands for now; collection only
   needs the static graph.

---

## 6. Check the conversion

```bash
uv run rosetta-build collect path/to/tree
uv run rosetta-build collect path/to/tree --graphviz graph.dot
```

Collection prints targets and writes Graphviz when requested. Fix unknown names,
self-edges, and dynamic-link cycles until collect exits 0.

Reference tree: `tests/trees/example/`.

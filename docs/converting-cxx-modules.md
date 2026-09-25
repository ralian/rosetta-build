# Converting a C++ modules project

Rosetta models C++20 named modules as **first-class targets**, not as ordinary
libraries with extra flags. Convert headers/`.cpp` first if needed
([converting-cxx.md](converting-cxx.md)), then split each module unit into its
own `target.toml`.

`collect` validates the module BMI graph today; compile adapters (e.g. g++) map
objects + CMIs/BMIs when you build.

---

## 1. What becomes a target

| Source role | File shape | Rosetta `type` |
|-------------|------------|----------------|
| Primary interface | `export module M;` | `module_interface` |
| Partition interface | `export module M:part;` | `module_partition` |
| Implementation unit | `module M;` | `module_implementation` |
| Importer (exe / lib) | `import M;` in `.cpp` | `executable` / `*_library` + `module_visibility` |

Rules enforced at collect time:

- Exactly **one** `module_interface` per logical `module` name.
- Every partition / implementation must name a `module` that has an interface
  target.
- `imports` may only reference **module** targets (not plain libraries).
- `module_visibility` may only name **exporters** (`module_interface` or
  `module_partition`).
- The module graph (`imports` ∪ `module_visibility`) must be a **DAG**.

---

## 2. Root listing

Same as non-modules: list every `target.toml` under `[tool.rosetta-build]`.

```toml
[tool.rosetta-build]
targets = [
  "modules/math/target.toml",
  "modules/math_detail/target.toml",
  "modules/math_impl/target.toml",
  "apps/app/target.toml",
]
```

---

## 3. Module unit targets

### Interface

```toml
type = "module_interface"
name = "math"
module = "math"
sources = ["math.cppm"]
```

`module` is the logical C++ module name (`export module math;`). `name` is the
rosetta target id (often the same string).

### Partition

```toml
type = "module_partition"
name = "math_detail"
module = "math"
partition = "detail"
sources = ["detail.cppm"]
imports = ["math"]
```

Logical export is `math:detail`. List BMI prerequisites in `imports` (usually
the primary interface, and any partitions this unit imports).

### Implementation

```toml
type = "module_implementation"
name = "math_impl"
module = "math"
sources = ["math.cpp"]
imports = ["math", "math_detail"]
```

Implementation targets **do not** export BMIs for others to import; they still
participate in link via `link_libraries` on dependents.

---

## 4. Consumers: visibility ≠ link

An executable that writes `import math;` needs **two** edges:

1. **`module_visibility`** — which exporters’ BMIs may be visible when compiling
   this target (explicit; **not** the same as `usage`).
2. **`link_libraries`** — which targets provide object code to link (often the
   `module_implementation`).

```toml
type = "executable"
name = "app"
language = "cxx"
sources = ["main.cpp"]
module_visibility = ["math"]
link_libraries = ["math_impl"]
```

Do **not** put the interface target only in `usage` and expect modules to work:
BMI ordering comes from the module graph.

`module_visibility` entries must be exporters. Naming an implementation target
here fails collect.

---

## 5. `imports` vs `module_visibility`

| Edge | On whom | Points at | Purpose |
|------|---------|-----------|---------|
| `imports` | module targets | other module targets | BMI build order among units of a module (and cross-module imports between module targets) |
| `module_visibility` | any native target | interface / partition exporters | Allow that target’s TUs to `import` those modules |

Inside one logical module, partitions and implementations typically `imports`
the interface (and sibling partitions they need). Apps and non-module libraries
use `module_visibility` instead of `imports`.

---

## 6. Migration checklist

1. **Identify units** — one interface, zero or more partitions, zero or more
   implementation TUs per logical module. Prefer one source file per module
   target.
2. **Name consistently** — `module` / `partition` match the `export module`
   lines; `name` is unique in the tree.
3. **Wire `imports`** — follow real `import` edges between module units; keep
   the graph acyclic.
4. **Wire consumers** — `module_visibility` → interfaces/partitions;
   `link_libraries` → implementations (and any normal libs).
5. **Drop header-only “module” hacks** — replace umbrella headers with interface
   targets; keep `include_dirs` only for non-modular code.
6. **Collect** — `uv run rosetta-build collect . --graphviz modules.dot` and
   inspect module edges.

---

## 7. Common collect failures

| Symptom | Fix |
|---------|-----|
| multiple interface targets for `M` | Keep a single `module_interface` with `module = "M"` |
| implementation has no interface | Add the `module_interface` for that `module` |
| `imports` names a static library | Point at module targets only; use `link_libraries` for libs |
| `module_visibility` names an implementation | Point at interface/partition exporters |
| module dependency cycle | Break cycles in `imports` / visibility (BMI graph is a DAG) |

---

## 8. How this meets the compiler

At compile time, module requests carry `object_output` plus optional `bmi_output`
/ `bmi_inputs`. Adapters with `cxx_modules` capability map those to vendor flags
(GCC: `-fmodules` + `-fmodule-mapper=`; Clang/MSVC: their BMI/IFC spellings).
P1689 scan JSON can feed the same BMI edges later.

Reference tree: `tests/trees/cxx_modules/`.

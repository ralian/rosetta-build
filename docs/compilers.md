# Implementing compiler adapters

Scaffolding lives under `src/rosetta_build/compilers/`. Each adapter is one **family × language**. Portable settings go in `options.py`; each adapter **maps or raises** (`UnsupportedCompileOption` / `UnsupportedLinkOption`). Raw flags are an escape hatch only—never auto-translate them.

Shared work for every adapter:

1. Grow the portable option enums / `CompileSettings` / `LinkSettings` fields as needed.
2. Extend that adapter’s flag tables; reject anything it cannot honor.
3. Implement `async compile` / `async link` (run the driver, capture streams, return `CompileResult` / `LinkResult`).
4. Add argv mapping tests for each new portable key; no need to shell out until execution is wired.

---

## GCC (`gcc` / `g++`)

**Modules:** `gcc_c.py`, `gcc_cxx.py` (shared tables: `_gnu.py`)

- Map C/C++ standards, defines (`-D`/`-U`), includes (`-I`), and later warnings / opt / PIC / LTO from GCC docs.
- Compile: `gcc|g++ -c … -o <obj>`; link: same driver to the artifact (or `ar` for static libs—decide and document).
- Cover response files (`@file`) and depfiles (`-MD`/`-MF`) when the planner needs them.
- Keep C vs C++ drivers separate (`gcc` vs `g++`); do not compile `.cpp` with `gcc` unless `-x` is intentional.

## Clang (`clang` / `clang++`)

**Modules:** `clang_c.py`, `clang_cxx.py` (reuse `_gnu.py` where flags match)

- Start from the GCC mapping; diff against Clang docs for divergences (e.g. some `-f` / sanitizer / modules flags).
- Same argv shape as GCC for basic compile/link; override only where Clang differs.
- Note Apple Clang vs LLVM Clang only if a portable option needs different spellings.

## MSVC (`cl` / `link`)

**Modules:** `msvc_c.py`, `msvc_cxx.py` (shared tables: `_msvc.py`)

- Map standards (`/std:…`), defines (`/D`/`/U`), includes (`/I`), and later `/W`, `/O`, `/MD` vs `/MT`, etc. from MSVC docs.
- Compile: `cl /c … /Fo<obj>`; link: `link … /OUT:<out>` (already sketched).
- Handle `.obj` / `.lib` / `.dll` / `.exe` naming and import libs for dynamic libraries.
- Response files (`@`), PDB (`/Zi`/`/DEBUG`), and UTF-8 (`/utf-8`) as portable options appear.
- Keep separate C and C++ adapters even though both use `cl`.

## rustc

**Modules:** `rustc.py` (helpers: `_rust.py`)

- Map editions (`--edition=`), crate types, `--crate-name`, `--emit`, and later cfg / target / codegen flags from rustc docs.
- Prefer **one** `rustc` invocation per crate (`capabilities.separate_link = False`); do not invent a multi-`.o` link step.
- Reject C-style `defines` / `include_dirs` (already); add Rust-native equivalents (e.g. `--cfg`) as portable fields when needed.
- Wire `RustcLinker` only if a real separate link ever appears; otherwise keep it unimplemented and have the planner skip it.

## gccrs

**Modules:** `gccrs.py` (reuse `_rust.py` where CLI matches)

- Diff gccrs CLI against rustc docs; share edition mapping only where flags are identical.
- Same one-shot compile model as rustc unless gccrs docs require a GCC link stage—then set `separate_link` accordingly and implement `GccrsLinker`.
- Flag any Rust portable option gccrs does not support and raise.

---

## Language notes (planner-facing)

| Language | Unit of compile | Typical link |
|----------|-----------------|--------------|
| C / CXX  | One translation unit → object | Separate link of objects + libs |
| Rust     | Crate root (+ modules via rustc) | Usually folded into `rustc` / `gccrs` |

When adding a portable option, decide: C-only, CXX-only, Rust-only, or shared. Shared bags are fine; adapters must still type-check / raise on mismatch.

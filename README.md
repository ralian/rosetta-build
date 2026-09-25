# rosetta-build

Experimental Python-based multilanguage build tool. You declare targets in
`target.toml` files, list them under `[tool.rosetta-build]` in a root
`pyproject.toml`, then collect → plan → build (and link for native artifacts).

## Example: pure Python wheel

Layout:

```text
example_pkg/
  pyproject.toml
  python/pkg/
    target.toml
    src/example_pkg/
      __init__.py
```

Root `pyproject.toml`:

```toml
[project]
name = "example_pkg"
version = "1.2.3"
requires-python = ">=3.14"

[build-system]
requires = ["rosetta-build"]
build-backend = "rosetta_build.backend"

[tool.rosetta-build]
targets = ["python/pkg/target.toml"]
```

`python/pkg/target.toml`:

```toml
type = "wheel"
name = "example_pkg"
sources = ["src/example_pkg"]
```

`sources` paths are relative to the directory that contains that `target.toml`.
The wheel target name should match `[project].name`.

### Build by hand

CLI:

```bash
uv run rosetta-build collect .
uv run rosetta-build build .
```

Artifacts land under `build/wheels/` and `build/sdists/` by default
(`--build-dir` to override).

Same flow via the Python API:

```python
import asyncio
from pathlib import Path

from rosetta_build.collect import collect
from rosetta_build.execute import run_build
from rosetta_build.plan import plan_build

collection = collect(Path("."))
plan = plan_build(collection, build_dir=Path("build"))
asyncio.run(run_build(plan))
print(plan.wheel_artifact_by_target["example_pkg"])
```

### Build with a frontend (uv)

With `[build-system]` pointing at `rosetta_build.backend`, any PEP 517 frontend
can drive the same plan. With uv:

```bash
uv build
uv build --sdist
uv build --wheel
```

`uv sync` / editable installs use the same backend (PEP 660 `.pth` editable
wheels).

## Example: C++ (no modules)

A small static library linked into an executable. Layout:

```text
hello/
  pyproject.toml
  apps/hello/
    target.toml
    main.cpp
  libs/core/
    target.toml
    core.cpp
    include/core.h
```

Root `pyproject.toml`:

```toml
[project]
name = "hello"
version = "0.0.0"

[tool.rosetta-build]
targets = [
  "libs/core/target.toml",
  "apps/hello/target.toml",
]
```

`libs/core/target.toml`:

```toml
type = "static_library"
language = "cxx"
name = "core"
sources = ["core.cpp"]
include_dirs = ["include"]
```

`apps/hello/target.toml`:

```toml
type = "executable"
language = "cxx"
name = "hello"
sources = ["main.cpp"]
link_libraries = ["core"]
```

`include_dirs` become portable include paths for dependents; `link_libraries`
names other collected targets. Paths in each `target.toml` are relative to that
file’s directory.

Sources (illustrative):

```cpp
// libs/core/include/core.h
int answer();

// libs/core/core.cpp
#include "core.h"
int answer() { return 42; }

// apps/hello/main.cpp
#include "core.h"
int main() { return answer() == 42 ? 0 : 1; }
```

Validate the graph, then compile and link (GCC/g++ for now):

```bash
uv run rosetta-build collect .
uv run rosetta-build build .
uv run rosetta-build link .
```

`build` runs compile (and any wheel steps); `link` produces the executable under
the build directory. Optional Graphviz of the collected graphs:

```bash
uv run rosetta-build collect . --graphviz graph.dot
```

For a fuller conversion guide from CMake-style trees, see
[`docs/converting-cxx.md`](docs/converting-cxx.md).

## Example: C++ modules

Named modules are first-class targets: an interface unit, an optional
implementation unit, and consumers that declare both BMI visibility and link
deps. Layout:

```text
math_app/
  pyproject.toml
  modules/math/
    target.toml
    math.cppm
  modules/math_impl/
    target.toml
    math.cpp
  apps/app/
    target.toml
    main.cpp
```

Root `pyproject.toml`:

```toml
[project]
name = "math_app"
version = "0.0.0"

[tool.rosetta-build]
targets = [
  "modules/math/target.toml",
  "modules/math_impl/target.toml",
  "apps/app/target.toml",
]
```

`modules/math/target.toml` (primary interface — `export module math;`):

```toml
type = "module_interface"
name = "math"
module = "math"
sources = ["math.cppm"]
```

`modules/math_impl/target.toml` (implementation — `module math;`):

```toml
type = "module_implementation"
name = "math_impl"
module = "math"
sources = ["math.cpp"]
imports = ["math"]
```

`apps/app/target.toml` — `module_visibility` for BMIs at compile time,
`link_libraries` for object code at link time:

```toml
type = "executable"
language = "cxx"
name = "app"
sources = ["main.cpp"]
module_visibility = ["math"]
link_libraries = ["math_impl"]
```

Sources (illustrative):

```cpp
// modules/math/math.cppm
export module math;
export int add(int a, int b);

// modules/math_impl/math.cpp
module math;
int add(int a, int b) { return a + b; }

// apps/app/main.cpp
import math;
int main() { return add(40, 2) == 42 ? 0 : 1; }
```

Same build commands as the non-modules example; `collect` orders the module BMI
graph, then `build` / `link` compile and link (GCC/g++ for now):

```bash
uv run rosetta-build collect .
uv run rosetta-build build .
uv run rosetta-build link .
```

Built module interfaces land under `build/bmi/` (e.g. `math.gcm` with g++).
Partitions (`module_partition`) and richer graphs are covered in
[`docs/converting-cxx-modules.md`](docs/converting-cxx-modules.md).

## Development Checks

```
uv sync --all-groups
uv run ruff check --fix
uv run ruff format --preview
uv run mypy --strict .
uv run pytest .
```

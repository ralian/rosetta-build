# rosetta-build: experimental python-based direct multilanguage build tool

The vision:
- Abstract compiler and language-independent build planner and executor
- Rosetta will handle build configuration, planning, and build execution
- Bring Your Own Compiler: As long as you have a compiler in your environment, Rosetta will handle everything else.

The roadmap:
- Start with a Python API, types, and build tests which implementations should pass.
- Each compiler/linker/tool will implement an interace Rosetta defines. We will target the big three C++ compilers and rustc first.
- Support C++ modules early on, shortly after the basic Big 3 implementation. We should encourage modules-first. Strike while the iron is hot.
- Add some packaging and dependency resolution niceities after. Implement common package spec?

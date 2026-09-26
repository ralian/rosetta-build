# Depfile parsing

`parse_depfile_text` reads the Make depfiles GCC and Clang write with `-MD -MF`. It returns prerequisite paths. Target names are ignored, and repeated prerequisites are returned once.

The lexer matches the subset of Make syntax [Ninja accepts for GCC and Clang depfiles](https://github.com/ninja-build/ninja/blob/master/src/depfile_parser.in.cc).

## Rule separator

A colon separates the target from the prerequisites only when it is the last character of a filename. GCC writes that colon with no space before it:

```text
C:\build\foo.obj: C:\src\foo.cpp C:\include\bar.h
```

The first filename token is `C:\build\foo.obj:`. The drive-letter colon sits in the middle of the token (`C:\…` or `C:/…`) and stays part of the path. The same line with forward slashes is `C:/build/foo.obj:` followed by `C:/src/foo.cpp`.

A colon with spaces around it also works (`foo.o : bar.h`): the `:` token itself ends the target list. Tokens before the separator are extra targets (`foo.o bar.o: baz.h`) and are ignored.

A line whose filenames never end in `:` is an error, including a bare Windows path such as `C:\src\foo.cpp`. The drive-letter colon is not a rule separator.

## Escapes

Backslash and `$` are the only escapes. Every other backslash is a path separator and is kept, so `C:\src\foo.h` stays `C:\src\foo.h`.

| Input | Result |
| --- | --- |
| `2N+1` backslashes, then a space | `N` backslashes and a space inside the filename |
| `2N` backslashes (`N >= 1`), then a space | `2N` literal backslashes, and the space ends the filename |
| `\#` | a literal `#`; one backslash is the escape, extras stay (`\\#` is `\#`) |
| `\:` followed by more path characters | a literal colon; one backslash is the escape, extras stay |
| `\:` at the end of the target, before whitespace | the rule separator; those backslashes stay on the target |
| `$$` | a literal `$` |

`weird\ name.h` is one backslash before a space (`N = 0`), so the path is `weird name.h`. `C:\Program\ Files\bar.h` is `C:\Program Files\bar.h`: the backslash before the space is the escape, and the other backslashes are separators.

GCC 10.0 through 10.2 wrote a backslash before every colon, so `C\:/src/foo.h` is `C:/src/foo.h`. Later GCC leaves the colon alone. `foo1\: x` is still the rule separator: the target is `foo1\` and `x` is the prerequisite.

## Line continuations

A `\` at the end of a line joins with the next line, and that backslash is removed. Compilers put a space before the continuation backslash, so it is not a path separator:

```text
foo.obj: C:\src\foo.cpp \
  C:\include\bar.h
```

## Comments

`#` starts a comment through the end of the line. `\#` is a literal `#` inside a filename, which is why hash signs are escaped above. A line whose first non-whitespace character is `#` is ignored.

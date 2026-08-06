# reference/ — third-party material we study but do not own

Everything in this directory except this file is **git-ignored on purpose**. It is
other people's work: prior-art source code, a community tool, and the official
Myth II editor manuals. We read it, cite it, and record what we learned in
[../NOTES.md](../NOTES.md) — we do not redistribute it.

That means a fresh clone of this repository gets an empty `reference/`. Nothing
in the project *needs* these files to build, run, or pass its tests; they are for
humans reading the format. Below is how to get each one back.

| Directory | What it is | Licence / permission |
|---|---|---|
| `mythextract/` | The reverse-engineering project this is built on | MIT, © 2025 James Wheare |
| `manuals/` | Official Fear and Loathing editor manuals, v1.8.5 | © 1998 Bungie Software / Tyson (Ferrex) Green |
| `mesh-converter/` | Iron's TFL→Myth II mesh converter, C source | "released as-is with permission from iron" |

## mythextract — the format research

The single most important source. Container layouts, tag header structures, the
TFL→SB tag header conversion, and the annotated format notes in its `docs/`.

```sh
git clone https://github.com/jwheare/mythextract reference/mythextract
```

Pinned commit studied: `c747909f4d68cc37958c3704a6f4d2d14efdd4fc`. Source
citations throughout `src/` name the exact file and line, so a different commit
may shift line numbers.

## manuals — what the fields actually *mean*

Saved HTML of the official editor documentation:

- **Fear** — the tag editor. *Section III: Tag Specific Documentation* is a
  field-by-field reference for every tag type, and is the authority on what a
  field does and what a sane value looks like.
- **Loathing** — the map editor. Covers meshes, submeshes, markers, passability
  and map actions from the map-maker's point of view.

Both are distributed by [Project Magma](http://projectmagma.net). Search the
tag-making sections of <https://tain.totalcodex.net> to find them.

These answered a question no amount of struct analysis could: a submesh is
256×256 colormap pixels, which is what established that Myth II has double TFL's
linear terrain resolution rather than merely different bookkeeping. See NOTES.md
section 15.

`src/fieldinfo.py` carries short factual summaries of the field semantics learned
here — written in our own words, with the manual cited — so the application can
explain itself without the manual being present.

## mesh-converter — a working 2011 conversion, in C

Iron's Mesh Converter, released with source. The only known working
implementation of TFL→Myth II mesh body conversion, and the corroborating
source for the marker/map-action structures in `src/mesh.py`.

<https://tain.totalcodex.net/items/show/mesh-converter-mac-and-windows-w-source-code>

Only `ReadMe.txt`, `converter.c` and `winconverter.c` are kept here — the
compiled Mac/Windows binaries in the original archive are not needed to read the
logic. See NOTES.md section 14 for what was taken from it, and for the two
places its approach was improved on rather than copied.

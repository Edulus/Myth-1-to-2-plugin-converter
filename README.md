# myth-plugin-converter

Converts **Myth: The Fallen Lords (TFL)** plugin files into **Myth II: Soulblighter (SB)**
plugin files.

TFL and Myth II share a common tag architecture -- a monolithic container holding a header,
a tag directory, and concatenated tag bodies -- but differ in the tag header layout, the
container header layout, and in the internal layout of many tag bodies. This tool aims to
read a TFL monolith/plugin, rewrite the tags it contains into Myth II form, and **write out
a working Myth II plugin**.

Built on the research and format work in [jwheare/mythextract](https://github.com/jwheare/mythextract),
which provides the reading and single-tag-header conversion side of the problem. See
[NOTES.md](NOTES.md) for a detailed account of what mythextract gives us and what this
project still has to build.

## Status

**Phase 0 complete** -- scaffolding and research only. No conversion code yet.

Phase 0 established the shape of the work. mythextract solves reading, and already converts
a single tag *header* from TFL to SB form (`myth_headers.tfl2sb`). What it has no code path
for at all is **writing a monolithic container** -- a rebuilt tag directory with recomputed
offsets, a `size` field, checksums, and synthesised entrypoints. That packer, plus per-tag
body conversion and tag-ID remapping, is this project's work. Details, verified struct
sizes, and the open questions (chiefly: nothing anywhere computes the SB container
checksums) are in [NOTES.md](NOTES.md).

Next: Phase 1 -- read an SB plugin and write it back byte-for-byte. Nothing else proceeds
until that round-trip passes.

## Requirements

- Python 3.12+

## Layout

```
src/        package source
tests/      tests
reference/  git-ignored clone of jwheare/mythextract (prior art, not ours)
NOTES.md    research notes on the reference implementation and the format
```

## Game data

No copyrighted Bungie game data (plugins, `.gor` monoliths, extracted tags, sounds, art)
is ever committed to this repository. `.gitignore` is set up to keep it out. You supply
your own legally obtained Myth installation when running the tool.

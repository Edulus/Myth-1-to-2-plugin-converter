"""The website's in-browser converter calls this, under Pyodide.

The page (web/convert/) puts the visitor's TFL plugin and the stock TFL tags
into Pyodide's in-memory filesystem, calls `convert`, and offers the result for
download. Nothing leaves the visitor's computer. This module only shapes the
answer for that page: a filename Myth II will list, and a short report in plain
words, with the full technical report kept for anyone who wants it.
"""

import pathlib
import re

from . import codec, reader, writer
from .convert import plugin

# Characters Windows and macOS refuse in a filename.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SUFFIX = " for M2"


def output_name(upload_name):
    """The converted plugin's filename, which is also its in-game name.

    The upload's name, without ``.gor``, plus " for M2", at most 32
    characters: Myth II does not list a plugin with a longer filename. Dots
    become spaces: Chrome took ``cbc.TFL.mauriac for M2`` to end in a file
    type and saved it as ``cbc.TFL.mauriac for M2.mauriac for M2.mauriac for M2``.
    """
    stem = _UNSAFE.sub("", upload_name).strip()
    if stem.lower().endswith(".gor"):
        stem = stem[:-4]
    stem = " ".join(stem.replace(".", " ").split()) or "Converted plugin"
    stem = stem[: plugin.MAX_PLUGIN_FILENAME - len(_SUFFIX)].rstrip()
    return stem + _SUFFIX


def convert(plugin_path, upload_name, out_dir, stock_paths):
    """Convert one uploaded plugin with the stock tags built in.

    Returns a dict for the page: ``filename``, ``path``, ``bytes``, ``levels``
    (the names the game will list), ``notes`` (plain-words sentences) and
    ``details`` (the full technical report). Raises `Problem` with a message
    fit to show the visitor.
    """
    filename = output_name(upload_name)
    out_path = pathlib.Path(out_dir) / filename
    try:
        report, written = plugin.convert_file(
            plugin_path, out_path, stock_paths=stock_paths
        )
    except reader.FormatError as exc:
        raise Problem(
            "This doesn't look like a Myth: The Fallen Lords plugin. Pick the "
            "plugin's .gor file (unzip it first if it came as a zip)."
        ) from exc
    except plugin.ConversionError as exc:
        if "already a Myth II" in str(exc):
            raise Problem(
                "This is already a Myth II plugin, so it needs no converting."
            ) from exc
        raise Problem(f"The converter couldn't finish: {exc}") from exc
    except writer.PackError as exc:
        raise Problem(f"The converter couldn't write the plugin: {exc}") from exc

    levels = [codec.decode_string(e.entry_long_name) for e in report.entrypoints]
    return {
        "filename": filename,
        "path": str(out_path),
        "bytes": written,
        "levels": levels,
        "notes": _notes(report, levels),
        "details": "\n".join(plugin.format_report(report, upload_name, filename)),
    }


class Problem(Exception):
    """Something the visitor needs to hear about, in plain words."""


def _notes(report, levels):
    notes = []
    if not levels:
        notes.append(
            "No playable levels were found, so Myth II will not list this as a "
            "campaign. It may be a tagset or a multiplayer-only plugin."
        )
    passed = len(report.passed_through())
    if passed:
        notes.append(
            f"{passed} parts were copied over unchanged, because the converter "
            "cannot convert them yet. Most are pictures and sounds. Some may "
            "not work in Myth II."
        )
    if report.unresolved:
        notes.append(
            f"{len(report.unresolved)} things this plugin points to were not "
            "found in it or in the original game files. Parts of some levels "
            "may be missing."
        )
    return notes

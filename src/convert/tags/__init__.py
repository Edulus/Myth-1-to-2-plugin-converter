"""Per-tag-type body converters.

Each module here exposes ``convert(body, context) -> (new_body, warnings)`` and
registers the tag types it handles in `CONVERTERS`. A tag type absent from the
registry is passed through unchanged, and the conversion reports it as such --
pass-through is a documented outcome, not a silent one.
"""

from . import arti, collection, geom, meef, meli, mesh, mode, mons, obje, part, proj, scen, text, unit

# Raw 4-byte tag type -> converter module.
CONVERTERS = {}
for module in (arti, collection, geom, meef, meli, mesh, mode, mons, obje, part, proj, scen, text, unit):
    for tag_type in module.HANDLES:
        CONVERTERS[tag_type] = module


def converter_for(tag_type):
    """Return the converter for a raw 4-byte tag type, or None."""
    return CONVERTERS.get(tag_type)


def supported_types():
    return sorted(CONVERTERS)

"""Convert a ``unit`` tag body from TFL to Myth II.

mythextract declares a single ``UnitTagFmt`` (`src/mons.py` ``UnitTag``) with
no TFL/SB split -- 8 bytes, a `mons` reference and a `core` reference, byte-
identical in both games. There is no layout to convert; the only thing that
can be wrong is the two tag IDs it carries, if the community port renamed the
`mons` or `core` tag they point at. Real unit bodies are 128 bytes in both games
(93 stock TFL, 98 in Magma); the undeclared 120 after the struct are kept.
"""

from ... import codec, mons as mons_module

HANDLES = (b"unit",)


def convert(body, context=None):
    """Convert a TFL unit body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map`` to remap the `mons`/`core` references.
    """
    warnings = []
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) < mons_module.UnitTag.size:
        return body, [
            f"unit body is {len(body)} bytes, shorter than the "
            f"{mons_module.UnitTag.size}-byte unit tag; left unconverted"
        ]

    tag = mons_module.UnitTag.unpack(body)
    values = {"mons": tag.mons, "core": tag.core}

    if id_map is not None:
        for field, tag_type in (("mons", b"mons"), ("core", b"core")):
            value = values[field]
            if codec.all_on(value) or codec.all_off(value):
                continue
            values[field] = id_map.map_id(tag_type, value)

    # Real unit bodies are 128 bytes in both games; only the first 8 are
    # declared. The rest is carried through, or Myth II reads past the end.
    converted = mons_module.UnitTag.build(**values).encode()
    return converted + body[mons_module.UnitTag.size :], warnings

"""A field-by-field record of what a conversion did, for people to check.

Keep asked (Bagrada chat, 16 November 2026) for every `mons` field the
converter edits to be written down, so he could audit its work himself, and
for an audit trail of what changes and by how much. This builds that trail as
rows, one per field per tag:

    tag type, tag id, tag name, field, value in TFL, value in Myth II,
    what happened, why

and writes them as CSV, which opens in any spreadsheet. It covers the monster
(`mons`) tags and the object (`obje`) the converter builds for each monster,
which together hold everything about a unit. Other tag types are to follow.

Values are shown raw, as stored, plus the plain number for the 8.8 fixed
fields a person reads as fractions (scale, effect modifiers): ``174 (0.680)``.
Tag references are shown as their four characters.
"""

import csv
import io
import struct

from . import codec, formats, mons as mons_module
from .convert.tags import mons as mons_converter, obje as obje_converter

COLUMNS = ("tag type", "tag id", "tag name", "field", "value in TFL", "value in Myth II", "what happened", "why")

NOT_IN_TFL = "(not in TFL)"
NOT_IN_MYTH_II = "(not in Myth II)"

# Why a field that is copied comes out different.
_CHANGED_WHY = {
    "sequence_indexes": ("TFL lists 16 animation slots, Myth II 26. Slots 1-16 are copied as they are "
                         "(assumed to mean the same in both games), the 10 new ones are none, and an empty "
                         "pause (slot 4) or turning (slot 5) takes the idle or moving animation, as Bungie's do"),
    "attacks": ("TFL's attack records are 32 bytes, Myth II's 64; each attack is rebuilt field by field. "
                "The flag word's giant bits are moved (TFL bits 12-13 to Myth II 11-12) and the random-sequences "
                "bit dropped; a unit with a giants-only attack has its other attacks prohibited against giants"),
}
_FORCED = {
    "use_attack_frequency": (1, "TFL always used the attack frequency; Myth II only does when this is on"),
}
_SB_ONLY_WHY = "Myth II only: the same value for every unit, the one Project Magma's port gives all 39 stock units"
_TFL_ONLY_WHY = {
    "object_scale_lower_bound": "moved to the unit's object, converted (see obje rows)",
    "object_scale_delta": "moved to the unit's object, converted (see obje rows)",
    "maximum_vitality": "moved to the unit's object (see obje rows)",
    "effect_modifiers": "moved to the unit's object (see obje rows)",
}


def show(value):
    """A field value as a person reads it."""
    if isinstance(value, bytes):
        if len(value) == 4:
            if value == b"\xff\xff\xff\xff":
                return "none"
            text = codec.decode_string(value)
            if text.isprintable() and text.strip("\0"):
                return text
        if len(value) > 4 and len(value) % 2 == 0:
            return " ".join(str(v) for v in struct.unpack(f">{len(value) // 2}h", value))
        return value.hex()
    return str(value)


def _fixed(value):
    return f"{value} ({value / 256:.3f})"


def mons_rows(tag_id, name, tfl_body, sb_body):
    """Rows for one monster: every Myth II field, and every TFL field with no
    Myth II place."""
    tfl = mons_module.TFLMonsHeader.unpack(tfl_body)
    sb = mons_module.SBMonsHeader.unpack(sb_body)
    per_unit = mons_converter.PER_COLLECTION.get(tfl.collection_tag)
    head = ["mons", codec.decode_string(tag_id), name]
    rows = []
    for field in mons_module.SBMonsHeader.names:
        after = getattr(sb, field)
        if field == "size":
            before = NOT_IN_TFL
            what = "Myth II only: set"
            why = ("TFL's 'intelligence' is not size (it is 2 for 40 of 46 units). Man, or giant for the "
                   "forest giant and trow, as in Bungie's and Magma's versions")
        elif field in mons_converter.SB_ONLY_DEFAULTS:
            before = NOT_IN_TFL
            if per_unit and field in ("pathfinding_radius", "more_hack_flags"):
                what = "Myth II only: per unit"
                why = (f"the value Project Magma's port gives units drawn with collection "
                       f"{codec.decode_string(tfl.collection_tag)}")
            else:
                what, why = "Myth II only: set", _SB_ONLY_WHY
        elif field in _FORCED:
            before, (_value, why) = NOT_IN_TFL, _FORCED[field]
            what = "Myth II only: set"
        else:
            before = getattr(tfl, field)
            if before == after:
                what, why = "copied", ""
            else:
                what = "converted" if field in _CHANGED_WHY else "changed"
                why = _CHANGED_WHY.get(field, "tag reference renamed by the ID map")
        rows.append(head + [field, show(before), show(after), what, why])
    rows.append(head + ["intelligence", show(tfl.intelligence), NOT_IN_MYTH_II, "dropped",
                        "TFL's AI intelligence; Myth II has no such field (it is not the size)"])
    for field in mons_converter.TFL_ONLY_FIELDS:
        before = getattr(tfl, field)
        rows.append(head + [field, show(before), NOT_IN_MYTH_II,
                            "moved" if field in _TFL_ONLY_WHY else "dropped",
                            _TFL_ONLY_WHY.get(field, "Myth II has no field for it")])
    return rows


def obje_rows(object_id, name, tfl_mons_body, sb_obje_body):
    """Rows for the object the converter built for one monster."""
    tfl = mons_module.TFLMonsHeader.unpack(tfl_mons_body)
    flags, gravity, elasticity, terminal, vit, vit_d, scale, scale_d = struct.unpack_from(">8h", sb_obje_body)
    effects = struct.unpack_from(f">{obje_converter.EFFECT_CHANNELS}h", sb_obje_body, 16)
    tfl_effects = struct.unpack_from(f">{obje_converter.TFL_EFFECT_CHANNELS}h", tfl.effect_modifiers)
    head = ["obje", codec.decode_string(object_id), name]
    factor = f"x{obje_converter.SCALE_FACTOR:.3f}"
    rows = [
        head + ["flags", NOT_IN_TFL, str(flags), "Myth II only: set", "draw the selection and vitality boxes, as on Magma's units"],
        head + ["physics (gravity, elasticity, terminal velocity)", "from the unit's TFL object",
                f"{gravity} {elasticity} {terminal}", "copied", "TFL's object holds only these"],
        head + ["maximum_vitality", str(tfl.maximum_vitality), str(vit), "moved", "from the TFL monster"],
        head + ["scale lower bound", _fixed(tfl.object_scale_lower_bound), _fixed(scale), "converted",
                f"{factor}: Bungie's own factor for the TFL sprites Myth II ships"],
        head + ["scale delta (random extra size)", _fixed(tfl.object_scale_delta), _fixed(scale_d), "converted",
                f"divided by {obje_converter.SCALE_DELTA_DIVISOR}, as Bungie did"],
    ]
    labels = ("close physical", "long-range physical", "explosive", "electric", "magical",
              "paralysis", "stone", "gas", "confusion")
    for i, label in enumerate(labels):
        if i < len(tfl_effects):
            rows.append(head + [f"effect modifier: {label}", _fixed(tfl_effects[i]), _fixed(effects[i]), "moved", "from the TFL monster"])
        else:
            rows.append(head + [f"effect modifier: {label}", NOT_IN_TFL, _fixed(effects[i]), "Myth II only: set", "1.0, as Magma's units have"])
    return rows


def to_csv(rows):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return out.getvalue()


def describe():
    """The audit's scope, for the report."""
    return "mons and obje tags, every field"


def _is_mons(tag, game_version):
    return tag.tag_type == b"mons" and len(tag.body) >= mons_module.MONS_HEADER_SIZE[game_version]


def build(source_tags, converted_tags, monster_objects):
    """Rows for a conversion. ``source_tags`` and the first ``len(source_tags)``
    of ``converted_tags`` line up one to one; ``monster_objects`` maps each
    monster's index to the id of the object built for it."""
    rows = []
    by_id = {t.tag_id: t for t in converted_tags if t.tag_type == b"obje"}
    for index, source in enumerate(source_tags):
        if not _is_mons(source, formats.TFL):
            continue
        converted = converted_tags[index]
        if len(converted.body) < mons_module.MONS_HEADER_SIZE[formats.SB]:
            continue
        try:
            rows += mons_rows(source.tag_id, source.name, source.body, converted.body)
            object_id = monster_objects.get(index)
            if object_id in by_id:
                rows += obje_rows(object_id, f"{source.name} object", source.body, by_id[object_id].body)
        except (ValueError, struct.error):
            continue
    return rows

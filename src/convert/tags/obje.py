"""Convert an ``obje`` (object) tag body from TFL to Myth II, and build the
per-monster objects Myth II expects.

A TFL object is 16 bytes of physics -- gravity, elasticity, terminal velocity --
shared widely: all 46 stock monsters use the one ``baob`` ("basic object").
Myth II's object is 64 bytes (mythextract ``mons_tag.ObjeTagFmt``) and also
carries what TFL kept on the monster: vitality, scale, and the damage-type
effect modifiers. Read as a Myth II object, a TFL one has scale 0 at byte 12 --
in-engine, every unit and tree was drawn at scale 0 (invisible) while its
shadow, sounds and minimap dot were fine (documentation/notes/stock-tags.md section 18).

So there are two conversions:

* `convert` -- any TFL object, keeping its physics and giving the Myth II-only
  fields neutral values (1.0 scale, vitality and modifiers). This is what
  projectiles and scenery use.
* `for_monster` -- an object built for one monster from its TFL header, used by
  `src.convert.plugin` to give each monster its own object, as Myth II's design
  needs and as `Magma - The Fallen Lords v1.9` does by hand. Against the 24
  monsters both carry, Magma's per-monster objects hold the TFL monster's
  ``maximum_vitality`` exactly, and its 7 ``effect_modifiers`` as the first 7 of
  9 (the 2 Myth II adds, gas and confusion, get 1.0).

**Scale is converted, not copied.** Myth II draws the same sprite larger than
TFL does at the same scale: copied verbatim, converted units stood about a
third too tall (thralls stuck out of water they stand in up to the chest in
TFL). Myth II's own stock tags ship seven of TFL's collections with the same
pixels -- thrall, dwarf, ghol, soulless, spider, avatara, balor -- and Bungie
gave every one of them TFL's scale times 0.728: the standard 0.934 became 0.680
for the thrall, dwarf, ghol and avatara, the spider's 0.797 became 0.590, the
balor's 1.188 became 0.879. Bungie also cut the random spread on top to about a
twelfth (the thrall's +0.129 became +0.012, the dwarf's +0.117 became +0.008).
`Magma - The Fallen Lords v1.9` reuses those values. So: the lower bound times
`SCALE_FACTOR`, the delta divided by `SCALE_DELTA_DIVISOR`. Two units Bungie
retuned by eye instead (villagers x0.91, the Shade x0.80) are not modelled.
"""

import struct

HANDLES = (b"obje",)

TFL_SIZE = 16
SB_SIZE = 64

ONE = 0x0100  # 1.0 as Myth II's 8.8 short fixed

# Stock TFL "basic object" physics, used when a monster's object is not in the
# container being converted (a plugin that relies on the stock tags).
BASIC_OBJECT_PHYSICS = (-2, 0x0080, 0)  # gravity, elasticity, terminal velocity

MONSTER_FLAGS = 0x0003  # DRAW_SELECTION_BOX | DRAW_VITALITY_BOX, as on Magma's
EFFECT_CHANNELS = 9
TFL_EFFECT_CHANNELS = 7

# TFL monster scale -> Myth II object scale (see the module docstring). 174/239
# maps TFL's standard 0.934 (239) onto Bungie's 0.680 (174) exactly.
SCALE_FACTOR = 174 / 239
SCALE_DELTA_DIVISOR = 12


def monster_scale(lower_bound, delta):
    """Myth II's ``(lower_bound, delta)`` for a TFL monster's scale, both 8.8 fixed."""
    return round(lower_bound * SCALE_FACTOR), round(delta / SCALE_DELTA_DIVISOR)


def _build(flags, physics, vitality, scale, effects):
    out = bytearray(SB_SIZE)
    struct.pack_into(">hhhh", out, 0, flags, *physics)
    struct.pack_into(">hhhh", out, 8, vitality[0], vitality[1], scale[0], scale[1])
    struct.pack_into(f">{EFFECT_CHANNELS}h", out, 16, *effects)
    return bytes(out)


def physics_of(tfl_body):
    """Gravity, elasticity and terminal velocity of a TFL object body."""
    return struct.unpack_from(">hhh", tfl_body, 0)


def convert(body, context=None):
    """Convert a TFL object body. Returns ``(new_body, warnings)``."""
    if len(body) != TFL_SIZE:
        return body, [
            f"obje body is {len(body)} bytes, not {TFL_SIZE}; left unconverted"
        ]
    warnings = []
    if any(body[6:]):
        warnings.append(
            f"obje bytes 6..{TFL_SIZE} are not zero ({body[6:].hex()}); not carried"
        )
    return _build(0, physics_of(body), (ONE, 0), (ONE, 0), (ONE,) * EFFECT_CHANNELS), warnings


def for_monster(tfl_mons, physics=BASIC_OBJECT_PHYSICS):
    """A Myth II object for one monster, from its parsed TFL header."""
    effects = struct.unpack_from(f">{TFL_EFFECT_CHANNELS}h", tfl_mons.effect_modifiers)
    effects = effects + (ONE,) * (EFFECT_CHANNELS - TFL_EFFECT_CHANNELS)
    return _build(
        MONSTER_FLAGS,
        physics,
        (tfl_mons.maximum_vitality, 0),
        monster_scale(tfl_mons.object_scale_lower_bound, tfl_mons.object_scale_delta),
        effects,
    )

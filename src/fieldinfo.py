"""What mesh header fields actually mean, and what a sane value looks like.

The rest of this project learned the *layout* of a mesh header from
mythextract, and reasonable *values* for the Myth II-only fields by measuring a
real community port (`src/convert/tags/mesh.py`). Neither tells you what a field
does. A user staring at `transition_point = 62259` has no way to judge it.

The official **Fear** manual (the Myth II tag editor, v1.8.5, © 1998 Bungie
Software / Tyson "Ferrex" Green, distributed by Project Magma) documents every
one of these fields from the map-maker's point of view. The summaries below are
short factual paraphrases written for this project, with the manual's own label
recorded so a user can find the same setting in Fear itself. The manual is
git-ignored and not redistributed; see `reference/README.md`.

Two things this buys the application:

* **Legible numbers.** These fields are stored as scaled integers. 229 means
  0.89 of full intensity; 2048 means 4 world units. Showing both makes a
  measured default reviewable instead of arbitrary.
* **A second opinion on our own defaults.** Where Fear states a typical range,
  `check` compares the value against it, so a user editing a decisions file
  gets told when they have wandered somewhere unusual.
"""

from dataclasses import dataclass

# Scale factors these fields are stored in. Same values as mythextract's
# scripts/codec.py, which is where the project's other scaled reads come from.
SHORT_FIXED_SF = 1 << 8  # 256   -- a fraction of 1.0 in a int16
FIXED_SF = 1 << 16  # 65536 -- a fraction of 1.0 in a int32
WORLD_POINT_SF = 512  # world units


@dataclass(frozen=True)
class FieldInfo:
    """What one mesh header field is, in terms a map-maker would recognise."""

    label: str  # what Fear's own editor calls it
    summary: str  # what it does, in our words
    scale: int = 1  # stored value / scale = the number Fear shows
    unit: str = ""  # what the scaled number is measured in
    typical: tuple = None  # (low, high) in *scaled* units, per the manual
    note: str = ""  # caveats worth surfacing

    def scaled(self, stored):
        """The stored integer as the quantity a map-maker would recognise."""
        try:
            return stored / self.scale
        except TypeError:
            return None

    def describe(self, stored):
        """A short human rendering of a stored value, e.g. '0.895 of 1.0'.

        Rounded for reading: these come from float32 fields and fixed-point
        divisions, so the raw repr is full of artefacts like
        1.4930000305175781 that carry no real precision.
        """
        value = self.scaled(stored)
        if value is None:
            return str(stored)
        if self.scale == 1 and not self.unit:
            return f"{round(value, 3):g}" if isinstance(value, float) else str(stored)
        return f"{round(value, 3):g} {self.unit}".strip()


# Only the fields a user is actually offered a choice about -- the Myth II-only
# mesh values this converter has to synthesise. Structural offsets and sizes are
# deliberately absent: they are computed, never chosen.
MESH_FIELDS = {
    "dark_fraction": FieldInfo(
        label="Dark Color Fraction",
        summary=(
            "How dark shadows are allowed to get. 1.0 is the darkest the shadow "
            "colour can render."
        ),
        scale=SHORT_FIXED_SF,
        unit="of 1.0",
        typical=(0.75, 0.90),
    ),
    "light_fraction": FieldInfo(
        label="Light Color Fraction",
        summary=(
            "How bright lit areas are allowed to get. Normally much smaller than "
            "the dark fraction."
        ),
        scale=SHORT_FIXED_SF,
        unit="of 1.0",
        typical=(0.10, 0.50),
        note=(
            "Worth knowing: the measured default sits a hair under the manual's "
            "0.10 floor, because that is what 38 of the reference port's 40 "
            "meshes actually use. Real practice and the manual disagree slightly."
        ),
    ),
    "transition_point": FieldInfo(
        label="Transition Point",
        summary=(
            "The lighting zero point: the illumination level at which the mesh is "
            "neither lightened nor darkened. Lower makes the whole map brighter, "
            "higher makes it darker."
        ),
        scale=FIXED_SF,
        unit="of 1.0",
        note=(
            "A per-map artistic choice rather than anything derived from the "
            "terrain, so a measured average is only ever a starting point."
        ),
    ),
    "ceiling_height": FieldInfo(
        label="Ceiling Height",
        summary=(
            "How high the invisible ceiling sits, which stops debris flying out "
            "of the level."
        ),
        scale=WORLD_POINT_SF,
        unit="world units",
        note=(
            "Ignored entirely unless the mesh's 'Has Ceiling' flag is set, which "
            "is normally only used on indoor maps."
        ),
    ),
    "reverb_environment": FieldInfo(
        label="Reverb Environment",
        summary="Which preset sound environment the level echoes like.",
        note="Sound reverberation is not supported on every machine.",
    ),
    "reverb_volume": FieldInfo(
        label="Reverb Volume",
        summary="How loud the reverberation is.",
    ),
    "reverb_decay_time": FieldInfo(
        label="Reverb Decay Time",
        summary=(
            "How long a sound takes to die away. Bare stone walls echo for longer; "
            "open ground with nothing to reflect off approaches zero."
        ),
    ),
    "reverb_damping": FieldInfo(
        label="Reverb Damping",
        summary="How much sound the surroundings absorb.",
    ),
    "fog_density": FieldInfo(
        label="Fog Density",
        summary=(
            "How thick the fog is. Dense fog is hard to see through; light fog is "
            "closer to atmospheric haze."
        ),
        note=(
            "Fog only renders on some hardware, so players who cannot see it gain "
            "an advantage. Worth using sparingly, especially on multiplayer maps."
        ),
    ),
    "minimum_zoom_factor": FieldInfo(
        label="Minimum Player Zoom",
        summary="How far the player is allowed to zoom out.",
        typical=(-5.0, -0.99998),
        note=(
            "Added in Myth II 1.8.2. A value of 0 means unset -- every mesh in the "
            "reference port leaves it at 0 -- so being outside the stated range is "
            "normal and not a problem."
        ),
    ),
    "min_vtfl_version": FieldInfo(
        label="TFL Min Version",
        summary=(
            "Oldest version of the vTFL / Unity gameplay patch this map will work "
            "with."
        ),
        note="Only meaningful when the mesh is marked as using vTFL gameplay.",
    ),
    "max_vtfl_version": FieldInfo(
        label="TFL Max Version",
        summary=(
            "Newest version of the vTFL / Unity gameplay patch this map will work "
            "with."
        ),
        note="Only meaningful when the mesh is marked as using vTFL gameplay.",
    ),
    "extra_flags": FieldInfo(
        label="Extra Flags",
        summary=(
            "Assorted per-map switches: last level of the scenario, cutscene "
            "ordering, secret level."
        ),
    ),
    "connector_count": FieldInfo(
        label="Connectors",
        summary=(
            "How many connectors (fence and corral links between posts) the map "
            "has."
        ),
        note="Zero on every mesh in the reference port.",
    ),
    "connectors_size": FieldInfo(
        label="Connector data size",
        summary="Size of the connector block. Follows from the connector count.",
    ),
    # Written into every terrain cell rather than the header, but from a user's
    # point of view it is the same kind of decision: a Myth II value with no TFL
    # source that somebody has to choose.
    "media_height": FieldInfo(
        label="Water level",
        summary=(
            "The height the water surface sits at. Myth II stores this per "
            "terrain cell; TFL has no equivalent, so one level is applied to "
            "the whole map."
        ),
        scale=WORLD_POINT_SF,
        unit="world units",
        note=(
            "Zero is sea level and a safe starting point. If a converted map's "
            "rivers or lakes sit too high or too low, this is the value to "
            "change. Which cells are water is preserved from the original; only "
            "the surface height has to be chosen."
        ),
    ),
}


def get(field):
    """`FieldInfo` for a mesh field name, or None if we have nothing to say."""
    return MESH_FIELDS.get(field)


def check(field, stored):
    """Warn if a value sits outside the range the Fear manual calls typical.

    Returns a message, or None when the value is fine or unjudgeable. This is
    advice, never enforcement -- an unusual map may want an unusual value, and
    the manual's ranges are described as what is *common*, not what is legal.
    """
    info = MESH_FIELDS.get(field)
    if info is None or info.typical is None:
        return None
    value = info.scaled(stored)
    if value is None:
        return None

    low, high = info.typical
    if low <= value <= high:
        return None

    # Documented-unset sentinels are not really out of range.
    if field == "minimum_zoom_factor" and stored == 0:
        return None

    return (
        f"{info.label} is {info.describe(stored)}, outside the {low:g}-{high:g} "
        f"the Fear manual describes as usual. That may be deliberate; it is not "
        f"an error."
    )

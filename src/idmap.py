"""TFL tag ID -> Myth II tag ID mapping.

Myth addresses every tag by a 4-byte ID. The community's hand-made TFL→Myth II
ports settled on their own IDs for the converted stock content, and a plugin that
uses different IDs will not interoperate with them -- so converting is not just a
format problem, it is a naming problem.

This is deliberately **data, not code**. It starts small and grows to cover units,
collections, projectiles and the rest, so the shape matters more than the current
contents.

Two things IDs need, and they are not the same:

* the *directory* entry for a tag being converted, and
* every *reference* to that tag from inside another tag's body.

`IdMap` handles lookup for both. Applying it inside bodies needs per-tag-type
field knowledge (mythextract's ``scripts/tag2local.py`` is the reference list of
which fields in which tag bodies hold IDs) and is deliberately **not** done by
blind byte substitution -- a 4-byte ID pattern occurs constantly by chance inside
bitmap and sound data, and replacing those would corrupt the tag silently.
"""

from . import codec


class IdMap:
    """Maps ``(tag_type, tfl_id)`` to a Myth II ``(tag_id, name)``.

    Tag types and IDs are raw 4-byte values throughout, matching the reader, so
    nothing depends on a lossy string decode.
    """

    def __init__(self, entries=None):
        self._entries = {}
        if entries:
            for (tag_type, tfl_id), value in entries.items():
                sb_id, name = value if isinstance(value, tuple) else (value, None)
                self.add(tag_type, tfl_id, sb_id, name)

    @staticmethod
    def _key(tag_type, tag_id):
        def as_bytes(value):
            if isinstance(value, str):
                return codec.encode_string(value)
            return bytes(value)

        tag_type, tag_id = as_bytes(tag_type), as_bytes(tag_id)
        if len(tag_type) != 4 or len(tag_id) != 4:
            raise ValueError(
                f"tag type and id must be 4 bytes, got {tag_type!r} / {tag_id!r}"
            )
        return tag_type, tag_id

    def add(self, tag_type, tfl_id, sb_id, name=None):
        """Record a mapping. ``name`` is the Myth II tag name, if it also changes."""
        key = self._key(tag_type, tfl_id)
        sb_id = self._key(tag_type, sb_id)[1]
        if isinstance(name, str):
            name = codec.encode_string(name, 32)
        existing = self._entries.get(key)
        if existing is not None and existing != (sb_id, name):
            raise ValueError(
                f"conflicting mapping for {codec.decode_string(key[0])}."
                f"{codec.decode_string(key[1])}: {existing!r} then {(sb_id, name)!r}"
            )
        self._entries[key] = (sb_id, name)

    def lookup(self, tag_type, tag_id):
        """Return ``(sb_id, name_or_None)``, or None if unmapped."""
        return self._entries.get(self._key(tag_type, tag_id))

    def map_id(self, tag_type, tag_id):
        """Return the Myth II ID, or the original when there is no mapping.

        Unmapped is the normal case for custom content: a community plugin's own
        tags keep their IDs, and only stock Bungie tags need renaming.
        """
        found = self.lookup(tag_type, tag_id)
        return found[0] if found else tag_id

    def __len__(self):
        return len(self._entries)

    def __contains__(self, key):
        return self._key(*key) in self._entries

    def items(self):
        return self._entries.items()

    def __repr__(self):
        return f"<IdMap {len(self._entries)} entries>"


# --- Stock TFL single-player text tags ---------------------------------------
# Verbatim from mythextract ``scripts/tflmeshtext2sb.py`` @ c747909 (``TFLTagMap``),
# which encodes the IDs the existing TFL→Myth II ports use for each stock level's
# narration text and string lists.
#
# Note the shape: this table is keyed by *level number*, and its values are the
# **destination** IDs. It is not an old -> new mapping and cannot be used as one
# directly. The TFL-side IDs live in the level's mesh header fields
# (`pregame_storyline_tag`, `map_description_string_list_tag`,
# `picture_caption_string_list_tag`), so turning this into `IdMap` entries needs
# mesh parsing, which lands with the mesh converter. Until then it is reference
# data -- see `stock_level_text_targets`.
#
# `None` entries are deliberate: the ports have no caption tag for levels 15 and 16.
STOCK_TFL_LEVEL_TEXT = {
    "01": (("30cb", "301 crows bridge"), ("30cc", "301 crows bridge"), ("30cb", "301 captions")),
    "02": (("30tr", "302 traitor"), ("30tr", "302 traitor"), ("30cd", "302 captions")),
    "03": (("30di", "303 diversion"), ("30di", "303 diversion"), ("30ca", "303 captions")),
    "04": (("30co", "304 covenant"), ("30co", "304 covenant"), ("30ce", "304 captions")),
    "05": (("30fl", "305 flight"), ("30fl", "305 flight"), ("30cf", "305 captions")),
    "06": (("30ft", "306 force ten"), ("30ft", "306 force ten"), ("30cg", "306 captions")),
    "07": (("30ba", "307 bagrada"), ("30ba", "307 bagrada"), ("30ci", "307 captions")),
    "08": (("30am", "308 ambush"), ("30am", "308 ambush"), ("30cj", "308 captions")),
    "09": (("30fc", "309 five champions"), ("30ch", "309 champions"), ("30ck", "309 captions")),
    "10": (("31ba", "310 barrier"), ("31ba", "310 barrier"), ("31cb", "310 captions")),
    "11": (("31si", "311 silvermines"), ("31si", "311 silvermines"), ("31cc", "311 captions")),
    "12": (("31sh", "312 shadow"), ("31sh", "312 shadow"), ("31ca", "312 captions")),
    "13": (("31sg", "313 seven gates"), ("31sg", "313 seven gates"), ("31cd", "313 captions")),
    "14": (("14fh", "314 forest heart"), ("14fh", "314 forest heart"), ("31ce", "314 captions")),
    "15": (("15ho", "315 heart of the stone"), ("15c1", "315 cave 1"), (None, None)),
    "16": (("16ts", "316 smiths of muirthemne"), ("16c2", "316 cave 2"), (None, None)),
    "17": (("17ts", "317 sons of myrgard"), ("17so", "317 myrgard 1"), ("31cf", "317 captions")),
    "18": (("18al", "318 a long awaited party"), ("18re", "318 myrgard 2"), ("31cg", "318 captions")),
    "19": (("19tr", "319 the road north"), ("19m1", "319 marsh 1"), ("31ch", "319 captions")),
    "20": (("32m2", "320 marsh 2"), ("32ma", "320 marsh2"), ("32ca", "320 captions")),
    "21": (("21ah", "321 hundred shallow graves"), ("21m3", "321 marsh 3"), ("32cb", "321 captions")),
    "22": (("22ro", "322 river of blood"), ("22rh", "322 trow 1"), ("32cc", "322 captions")),
    "23": (("23po", "323 pools of iron"), ("23t2", "323 trow 2"), ("32cd", "323 captions")),
    "24": (("24tl", "324 the last battle"), ("24t3", "325 trow 3"), ("32ce", "324 captions")),
    "25": (("25tg", "325 the great devoid"), ("25tg", "325 great devoid"), ("32cf", "325 captions")),
}

# Which tag type each slot in the tuple above refers to, in order.
STOCK_LEVEL_TEXT_TYPES = (b"text", b"stli", b"stli")


def stock_level_text_targets(level):
    """Destination ``(tag_type, sb_id, name)`` for a stock TFL level's text tags.

    Skips the slots the ports leave empty. Raises KeyError for an unknown level.
    """
    targets = []
    for tag_type, (sb_id, name) in zip(
        STOCK_LEVEL_TEXT_TYPES, STOCK_TFL_LEVEL_TEXT[level]
    ):
        if sb_id is not None:
            targets.append((tag_type, codec.encode_string(sb_id), name))
    return targets


def default_map():
    """The mapping applied when the caller supplies none.

    Empty for now, and honestly so. Every entry we could add today would be a
    guess: the stock table above is keyed by level and needs mesh parsing to
    become old -> new pairs. A custom TFL plugin's own tags keep their IDs
    anyway, so an empty map is correct for the content Phase 2 converts.
    """
    return IdMap()

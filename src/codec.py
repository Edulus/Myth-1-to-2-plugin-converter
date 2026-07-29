"""Minimal declarative binary codec for Myth tag structures.

Adapted from jwheare/mythextract ``scripts/codec.py`` @ c747909. Same core idea --
a structure is a list of ``(struct_format, field_name)`` pairs, big-endian, with a
``None`` field name marking padding -- but deliberately narrower in two ways that
Phase 1's byte-exactness gate depends on:

* **No value decoding.** Fields come back as ``int`` or ``bytes``, never ``str``
  and never scaled floats. mythextract decodes ``32s`` name fields into strings
  (``codec.String``) and divides fixed-point ints by a scale factor; both are
  lossy round-trips. ``decode_string`` in particular truncates at the first NUL,
  so re-encoding a name would silently discard any bytes after it. Display-level
  decoding lives in `decode_string` here too, but its output is never fed back
  into an encode.

* **Padding bytes are preserved from the original data**, not zero-filled.
  mythextract does this as well (``value_encoder(data_start=..., data_end=...)``
  slices the original buffer). Real Myth tags carry non-zero bytes in fields the
  format notes label "unused", so zero-filling them would break byte-exactness.

Everything Myth is big-endian; the ``>`` prefix is applied here, not by callers.
"""

import struct

__all__ = ["Struct", "Record", "decode_string", "encode_string", "all_on", "all_off"]


class Struct:
    """A binary structure definition.

    ``fields`` is a list of ``(fmt, name)`` pairs, where ``fmt`` is a single
    ``struct`` format code (e.g. ``'H'``, ``'4s'``, ``'32s'``). Padding is written
    as ``('4x', None)``: an ``x`` format with no name. The two must agree -- a
    named ``x`` field or an unnamed non-``x`` field is a definition error.
    """

    def __init__(self, name, fields):
        self.name = name
        self.fields = tuple(fields)
        self.names = tuple(n for _, n in fields if n is not None)

        # Walk the fields once to record each one's byte range, so encode() can
        # copy padding straight out of the original buffer.
        self._layout = []  # (fmt, name, start, end)
        offset = 0
        for fmt, field_name in fields:
            is_pad = fmt.endswith("x")
            if is_pad != (field_name is None):
                raise ValueError(
                    f"{name}.{field_name!r}: padding must be an 'x' format with a "
                    f"None name (got fmt={fmt!r})"
                )
            size = struct.calcsize(f">{fmt}")
            self._layout.append((fmt, field_name, offset, offset + size))
            offset += size

        self.fmt = ">" + "".join(fmt for fmt, _ in fields)
        self.size = struct.calcsize(self.fmt)
        if self.size != offset:
            # Defensive: big-endian struct never pads, so these must agree.
            raise ValueError(f"{name}: size mismatch {self.size} != {offset}")

        if len(set(self.names)) != len(self.names):
            raise ValueError(f"{name}: duplicate field names")

    def unpack(self, data, offset=0):
        """Parse one record out of ``data`` at ``offset``."""
        raw = bytes(data[offset : offset + self.size])
        if len(raw) < self.size:
            raise ValueError(
                f"{self.name}: need {self.size} bytes at offset {offset}, got {len(raw)}"
            )
        values = struct.unpack(self.fmt, raw)
        return Record(self, dict(zip(self.names, values)), raw)

    def unpack_many(self, data, offset, count):
        return [self.unpack(data, offset + i * self.size) for i in range(count)]

    def build(self, **values):
        """Construct a record from scratch. Padding is zero-filled."""
        missing = set(self.names) - set(values)
        if missing:
            raise ValueError(f"{self.name}: missing fields {sorted(missing)}")
        unknown = set(values) - set(self.names)
        if unknown:
            raise ValueError(f"{self.name}: unknown fields {sorted(unknown)}")
        return Record(self, dict(values), None)

    def __repr__(self):
        return f"<Struct {self.name} size={self.size} fields={len(self.names)}>"


class Record:
    """One parsed structure. Field values are exposed as attributes."""

    __slots__ = ("_struct", "_values", "_raw")

    def __init__(self, struct_def, values, raw):
        object.__setattr__(self, "_struct", struct_def)
        object.__setattr__(self, "_values", values)
        object.__setattr__(self, "_raw", raw)

    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, "_values")[name]
        except KeyError:
            raise AttributeError(
                f"{object.__getattribute__(self, '_struct').name} has no field {name!r}"
            ) from None

    def __setattr__(self, name, value):
        raise AttributeError("Record is immutable; use replace()")

    def replace(self, **changes):
        """Return a copy with some fields changed, keeping the original padding."""
        unknown = set(changes) - set(self._struct.names)
        if unknown:
            raise ValueError(f"{self._struct.name}: unknown fields {sorted(unknown)}")
        return Record(self._struct, {**self._values, **changes}, self._raw)

    def encode(self):
        """Serialise back to bytes.

        Named fields are packed from their current values; padding is copied from
        the original buffer when this record came from one, else zero-filled.
        """
        out = bytearray()
        raw = self._raw
        for fmt, name, start, end in self._struct._layout:
            if name is None:
                out += raw[start:end] if raw is not None else bytes(end - start)
            else:
                try:
                    out += struct.pack(f">{fmt}", self._values[name])
                except struct.error as exc:
                    raise ValueError(
                        f"{self._struct.name}.{name}: cannot pack "
                        f"{self._values[name]!r} as {fmt!r}: {exc}"
                    ) from None
        return bytes(out)

    @property
    def raw(self):
        """The bytes this record was parsed from, or None if it was built."""
        return self._raw

    @property
    def field_names(self):
        return self._struct.names

    def as_dict(self):
        return dict(self._values)

    def __eq__(self, other):
        if not isinstance(other, Record):
            return NotImplemented
        return self._struct is other._struct and self._values == other._values

    def __repr__(self):
        shown = ", ".join(f"{n}={self._values[n]!r}" for n in self._struct.names)
        return f"{self._struct.name}({shown})"


def decode_string(value):
    """Decode a fixed-width Myth string field for *display only*.

    Myth strings are mac-roman and NUL-terminated within a fixed-width field
    (mythextract ``codec.decode_string``). This is lossy -- anything after the
    first NUL is dropped -- so never feed the result back into an encode.
    """
    return value.split(b"\0", 1)[0].decode("mac-roman", errors="replace")


def encode_string(value, width=None):
    """Encode a str to mac-roman bytes, optionally NUL-padded to ``width``."""
    data = value.encode("mac-roman")
    if width is None:
        return data
    if len(data) > width:
        raise ValueError(f"{value!r} is {len(data)} bytes, does not fit in {width}")
    return data.ljust(width, b"\0")


def all_on(value):
    """True if every byte is 0xFF -- Myth's 'unset' sentinel for tag IDs."""
    return value == b"\xff" * len(value)


def all_off(value):
    """True if every byte is 0x00 -- the other 'empty' convention."""
    return value == b"\x00" * len(value)

"""Convert ``text`` and ``stli`` tag bodies from TFL to Myth II.

Both bodies are plain text with no structure beyond delimiters, which is why
this is the right first vertical slice: the only difference between the games is
the escape character that introduces a formatting code.

TFL uses a backslash, Myth II uses a pipe: ``\\i`` / ``\\b`` / ``\\p`` become
``|i`` / ``|b`` / ``|p`` for italic, bold and plain. Adapted from mythextract
``scripts/tflmeshtext2sb.py`` @ c747909, whose whole body conversion is::

    def convert_formatting(text_data):
        return text_data.replace(b'\\\\', b'|')

`stli` bodies are the same text split on NUL/CR/LF (mythextract
``myth_headers.parse_stli``), so the same substitution applies unchanged.

There are no tag IDs embedded in either body, so nothing here needs the ID map.
"""

# Raw 4-byte tag types this module converts.
HANDLES = (b"text", b"stli")

TFL_FORMAT_ESCAPE = b"\\"
SB_FORMAT_ESCAPE = b"|"


def convert(body, context=None):
    """Convert one ``text`` or ``stli`` body. Returns ``(new_body, warnings)``.

    Lossless and reversible except in one case, which is reported: a literal
    backslash in TFL text is indistinguishable from a formatting escape, so it
    becomes a pipe too. mythextract has the same behaviour. In practice Myth
    text is prose and stray backslashes are rare, but "rare" is not "never" and
    the caller should be told.
    """
    warnings = []
    if not body:
        return body, warnings

    converted = body.replace(TFL_FORMAT_ESCAPE, SB_FORMAT_ESCAPE)

    escapes = body.count(TFL_FORMAT_ESCAPE)
    if escapes:
        # A backslash followed by something other than a known format code is
        # more likely to be a literal than markup.
        suspicious = sum(
            1
            for i, byte in enumerate(body)
            if byte == TFL_FORMAT_ESCAPE[0]
            and (i + 1 >= len(body) or body[i + 1 : i + 2].lower() not in (b"i", b"b", b"p"))
        )
        if suspicious:
            warnings.append(
                f"{suspicious} of {escapes} backslashes are not a known format "
                f"code (|i, |b, |p) and may have been literal text"
            )
    return converted, warnings


def to_strings(body):
    """Split an ``stli`` body into its strings, for display and diffing.

    mythextract ``myth_headers.parse_stli``: strings are delimited by NUL, CR or
    LF, and empty runs are skipped. Lossy -- for display only.
    """
    from ... import codec

    strings = []
    current = bytearray()
    for byte in body:
        if byte in (0, 0x0A, 0x0D):
            if current:
                strings.append(codec.decode_string(bytes(current)))
                current = bytearray()
        else:
            current.append(byte)
    if current:
        strings.append(codec.decode_string(bytes(current)))
    return strings

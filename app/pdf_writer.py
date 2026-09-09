"""
Minimal, dependency-free PDF writer — enough to render a one- or two-page
business letter, deliberately not a general PDF library.

Why hand-rolled instead of reportlab/fpdf: this app's whole selling point is
that it runs from three well-known dependencies (see requirements.txt), and a
mock ERP only needs the issued document to be a *real, openable* PDF carrying
the right text — not typographic control. Everything here is stdlib.

Only the two base-14 Helvetica faces are used, so no font embedding is needed
(every PDF reader ships them). Text is encoded as WinAnsi (cp1252), which
covers the Latin-1 range these letters are written in; characters outside it
are replaced rather than silently dropped.

Usage:
    render_pdf([
        text("Acme Corporation", font="bold", size=16),
        rule(),
        space(8),
        text("Long paragraph that wraps automatically ..."),
    ])  # -> bytes
"""

# A4 in PostScript points, with a 1-inch-ish margin. Ints keep the content
# stream readable when debugging with a text editor.
PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 64
MARGIN_TOP = 72
MARGIN_BOTTOM = 72

TEXT_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)

# Helvetica's average glyph is ~0.5em wide. Wrapping by character count using a
# slightly pessimistic 0.52 keeps lines inside the margin without pulling in an
# AFM metrics table for what is, after all, a mock. Lines of mostly capitals
# ("TO WHOM IT MAY CONCERN") are the case this over-estimates, and they are
# short headings here, so they never reach the wrap point.
_AVG_CHAR_EM = 0.52

_FONT_RESOURCE = {"regular": "F1", "bold": "F2"}


def text(content: str, *, font: str = "regular", size: int = 11,
         leading: int = None, wrap: bool = True) -> dict:
    """A paragraph. Wraps to the text column unless wrap=False."""
    return {
        "kind": "text", "content": content, "font": font, "size": size,
        "leading": leading if leading is not None else round(size * 1.45),
        "wrap": wrap,
    }


def space(height: int = 12) -> dict:
    """Vertical gap, in points."""
    return {"kind": "space", "height": height}


def rule() -> dict:
    """Full-width horizontal line — the letterhead divider."""
    return {"kind": "rule"}


def _escape(value: str) -> bytes:
    """PDF string literal: cp1252 bytes, with parens and backslashes escaped."""
    raw = value.encode("cp1252", "replace")
    out = bytearray()
    for byte in raw:
        if byte in (0x28, 0x29, 0x5C):  # ( ) \
            out.append(0x5C)
        out.append(byte)
    return bytes(out)


def _wrap(content: str, size: int) -> list:
    """Character-count wrapping — see _AVG_CHAR_EM. Empty input yields one
    empty line so a blank paragraph still advances the cursor."""
    import textwrap

    max_chars = max(1, int(TEXT_WIDTH / (size * _AVG_CHAR_EM)))
    return textwrap.wrap(content, width=max_chars) or [""]


def _paginate(blocks: list) -> list:
    """Turn blocks into one content stream (bytes) per page, breaking to a new
    page whenever the cursor would cross the bottom margin."""
    pages, stream = [], bytearray()
    y = PAGE_HEIGHT - MARGIN_TOP

    def new_page():
        nonlocal stream, y
        pages.append(bytes(stream))
        stream = bytearray()
        y = PAGE_HEIGHT - MARGIN_TOP

    for block in blocks:
        if block["kind"] == "space":
            y -= block["height"]
            if y < MARGIN_BOTTOM:
                new_page()
            continue

        if block["kind"] == "rule":
            if y - 8 < MARGIN_BOTTOM:
                new_page()
            y -= 8
            stream += (f"0.6 w {MARGIN_X} {y} m {PAGE_WIDTH - MARGIN_X} {y} l S\n").encode()
            continue

        size, leading = block["size"], block["leading"]
        lines = _wrap(block["content"], size) if block["wrap"] else [block["content"]]
        for line in lines:
            if y - leading < MARGIN_BOTTOM:
                new_page()
            y -= leading
            stream += (b"BT /" + _FONT_RESOURCE[block["font"]].encode() + f" {size} Tf ".encode()
                       + f"{MARGIN_X} {y} Td ".encode() + b"(" + _escape(line) + b") Tj ET\n")

    pages.append(bytes(stream))
    return pages


def render_pdf(blocks: list) -> bytes:
    """Render blocks to PDF bytes. Object layout: 1 catalog, 2 page tree,
    3/4 the two fonts, then a (page, content) pair per page."""
    page_streams = _paginate(blocks)
    page_count = len(page_streams)
    # Pages and their content streams interleave from object 5 onwards.
    page_ids = [5 + (2 * i) for i in range(page_count)]

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Kids [%s] /Count %d >>"
         % (" ".join(f"{i} 0 R" for i in page_ids), page_count)).encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    for index, content in enumerate(page_streams):
        objects.append(
            ("<< /Type /Page /Parent 2 0 R "
             f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
             "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
             f"/Contents {page_ids[index] + 1} 0 R >>").encode()
        )
        objects.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
                       + content + b"\nendstream")

    # The binary comment on line 2 marks the file as binary for tools that
    # sniff it (a convention every real PDF writer follows).
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n").encode()
    return bytes(out)

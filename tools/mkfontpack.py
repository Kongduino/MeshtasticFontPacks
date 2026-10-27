#!/usr/bin/env python3
"""Build a Meshtastic Font Pack (.mfp, see SPEC.md) from a TrueType/OpenType font.

  mkfontpack.py --font F.ttf --size 12 --set kana,hanzi-gb2312 --out pack.mfp
  mkfontpack.py --font F.ttf --size 12 --ranges 3040-30FF,4E00-9FFF --text extra.txt --out pack.mfp

Code points the font doesn't have are left out (and counted). Needs Pillow and fontTools.
"""
import argparse, datetime, os, struct, sys, zlib

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

MAGIC = b"MFPK"
VERSION = 1
HEADER_SIZE = 64


def charset(codec, lo, hi, leads=range(0xA1, 0xFF), trails=range(0xA1, 0xFF)):
    """The code points between lo and hi of a legacy two-byte national character set (its common characters).
    Found by decoding every two-byte code: encoding would also accept characters a codec composes (EUC-KR
    encodes all 11172 Hangul syllables as jamo sequences)."""
    out = set()
    for lead in leads:
        for trail in trails:
            try:
                ch = bytes((lead, trail)).decode(codec)
            except UnicodeDecodeError:
                continue
            if len(ch) == 1 and lo <= ord(ch) <= hi:
                out.add(ord(ch))
    return sorted(out)


# Named sets; a set is a list of code points
SETS = {
    "ascii": lambda: list(range(0x20, 0x7F)),
    "latin1": lambda: list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)),
    "cyrillic": lambda: list(range(0x400, 0x460)),
    "greek": lambda: list(range(0x370, 0x400)),
    "cjk-punct": lambda: list(range(0x3000, 0x3040)) + list(range(0xFF00, 0xFFF0)),
    "kana": lambda: list(range(0x3040, 0x3100)),
    "hangul": lambda: list(range(0xAC00, 0xD7A4)),
    "hangul-ksx1001": lambda: charset("euc_kr", 0xAC00, 0xD7A3),       # 2350 common syllables
    "hanzi-gb2312": lambda: charset("gb2312", 0x4E00, 0x9FFF),         # 6763 simplified Chinese
    "kanji-jis0208": lambda: charset("euc_jp", 0x4E00, 0x9FFF),        # 6356 Japanese kanji
    # 13061 traditional Chinese (Big5)
    "hanzi-big5": lambda: charset("big5", 0x4E00, 0x9FFF, trails=list(range(0x40, 0x7F)) + list(range(0xA1, 0xFF))),
    "cjk-all": lambda: list(range(0x4E00, 0xA000)),
}


def parse_ranges(text):
    cps = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        lo = int(lo, 16)
        hi = int(hi, 16) if hi else lo
        if hi < lo or hi > 0x10FFFF:
            sys.exit("bad range: " + part)
        cps.extend(range(lo, hi + 1))
    return cps


def runs(cps):
    """Sorted code points as (first, last) runs of consecutive values."""
    out = []
    for cp in cps:
        if out and cp == out[-1][1] + 1:
            out[-1][1] = cp
        else:
            out.append([cp, cp])
    return out


def render(font, cp):
    """A glyph as (advance, ink box left, ink box top from the ascender line, width, height, bits)."""
    ch = chr(cp)
    advance = round(font.getlength(ch))
    l, t, r, b = font.getbbox(ch, anchor="la")
    if r <= l or b <= t:
        return advance, 0, 0, 0, 0, b""
    img = Image.new("1", (r - l, b - t), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"  # no anti-aliasing: 1 bit per pixel
    draw.text((-l, -t), ch, font=font, fill=1, anchor="la")
    ink = img.getbbox()
    if ink is None:
        return advance, 0, 0, 0, 0, b""
    img = img.crop(ink)
    w, h = img.size
    px = img.load()
    bits = bytearray((w * h + 7) // 8)
    n = 0
    for y in range(h):
        for x in range(w):
            if px[x, y]:
                bits[n >> 3] |= 0x80 >> (n & 7)
            n += 1
    return advance, l + ink[0], t + ink[1], w, h, bytes(bits)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font", required=True, help="TrueType/OpenType font file")
    ap.add_argument("--index", type=int, default=0, help="font index in a .ttc collection")
    ap.add_argument("--size", type=int, required=True, help="pixel size")
    ap.add_argument("--set", default="", help="named sets, comma-separated: " + ", ".join(SETS))
    ap.add_argument("--ranges", default="", help="hex code point ranges, e.g. 3040-30FF,4E00")
    ap.add_argument("--text", help="a UTF-8 file: every character in it is included")
    ap.add_argument("--line-gap", type=int, default=1, help="blank pixels between lines (default 1)")
    ap.add_argument("--line-ref", default="Hgjy\u4e2d\u3042\ud55c", help="characters whose ink sets the line box")
    ap.add_argument("--name", help="pack name (default: the output file name)")
    ap.add_argument("--license", default="", help="the font's license, e.g. OFL-1.1")
    ap.add_argument("--source", default="", help="where the font comes from")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    wanted = set()
    for name in filter(None, (s.strip() for s in a.set.split(","))):
        if name not in SETS:
            sys.exit("unknown set: %s (known: %s)" % (name, ", ".join(SETS)))
        wanted.update(SETS[name]())
    wanted.update(parse_ranges(a.ranges))
    if a.text:
        wanted.update(ord(c) for c in open(a.text, encoding="utf-8").read() if ord(c) >= 0x20)
    wanted.discard(0xFEFF)
    if not wanted:
        sys.exit("nothing selected: use --set, --ranges or --text")

    cmap = TTFont(a.font, fontNumber=a.index).getBestCmap()
    cps = sorted(cp for cp in wanted if cp in cmap)
    missing = len(wanted) - len(cps)
    font = ImageFont.truetype(a.font, a.size, index=a.index)

    glyphs = [render(font, cp) for cp in cps]
    # The line box comes from reference characters (a few outliers, accents or tall symbols, would make every
    # line taller): their ink extents, else every glyph's. A glyph outside the box gets a negative y_offset or
    # runs past the line height; the firmware clips to the screen
    ref = [render(font, ord(c)) for c in a.line_ref if ord(c) in cmap]
    inked = [g for g in ref if g[3]] or [g for g in glyphs if g[3]]
    top = min((g[2] for g in inked), default=0)
    bottom = max((g[2] + g[4] for g in inked), default=a.size)
    ascent, _ = font.getmetrics()
    line_height = bottom - top + a.line_gap
    baseline = ascent - top

    range_tab = bytearray()
    index = 0
    for lo, hi in runs(cps):
        range_tab += struct.pack("<III", lo, hi, index)
        index += hi - lo + 1
    if len(range_tab) // 12 > 0xFFFF:
        sys.exit("too many ranges")

    glyph_tab = bytearray()
    bitmaps = bytearray()
    for cp, (advance, x, y, w, h, bits) in zip(cps, glyphs):
        y -= top
        if not (0 <= advance <= 255 and w <= 255 and h <= 255 and -128 <= x <= 127 and -128 <= y <= 127):
            sys.exit("U+%04X doesn't fit the glyph fields (advance %d, box %dx%d at %d,%d)" % (cp, advance, w, h, x, y))
        if len(bitmaps) >= 1 << 24:
            sys.exit("bitmaps exceed 16 MiB")
        off = len(bitmaps)
        glyph_tab += struct.pack("<I", off)[:3] + struct.pack("<BBBbb", advance, w, h, x, y)
        bitmaps += bits

    name = a.name or os.path.splitext(os.path.basename(a.out))[0]
    meta = "\n".join([
        "name=" + name,
        "font=" + os.path.basename(a.font),
        "size=%d" % a.size,
        "license=" + a.license,
        "source=" + a.source,
        "created=" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ranges=" + ",".join(("%04X-%04X" % (lo, hi)) if hi > lo else "%04X" % lo for lo, hi in runs(cps)),
    ]).encode("utf-8")

    ranges_offset = HEADER_SIZE
    glyphs_offset = ranges_offset + len(range_tab)
    bitmaps_offset = glyphs_offset + len(glyph_tab)
    meta_offset = bitmaps_offset + len(bitmaps)
    file_size = meta_offset + len(meta)
    max_advance = max((g[0] for g in glyphs), default=0)

    tail = struct.pack("<BBBBHHIIIIIII12x", 1, line_height, baseline, max_advance, len(range_tab) // 12, 0,
                       len(cps), ranges_offset, glyphs_offset, bitmaps_offset, len(bitmaps), meta_offset, len(meta))
    body = tail + bytes(range_tab) + bytes(glyph_tab) + bytes(bitmaps) + meta
    header = MAGIC + struct.pack("<HHII", VERSION, HEADER_SIZE, file_size, zlib.crc32(body))
    with open(a.out, "wb") as f:
        f.write(header + body)

    print("%s: %d glyphs (%d not in the font), %d ranges, line height %d, baseline %d, %d bytes"
          % (a.out, len(cps), missing, len(range_tab) // 12, line_height, baseline, file_size))


if __name__ == "__main__":
    main()

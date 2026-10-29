#!/usr/bin/env python3
"""Build a Meshtastic Font Pack (.mfp, see SPEC.md) from a TrueType/OpenType font.

  mkfontpack.py --font F.ttf --size 12 --set kana,hanzi-gb2312 --out pack.mfp
  mkfontpack.py --font F.ttf --size 12 --ranges 3040-30FF,4E00-9FFF --text extra.txt --out pack.mfp

Code points the font doesn't have are left out (and counted). Needs Pillow and fontTools.
"""
import argparse, datetime, os, struct, sys, zlib
from collections import Counter

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

MAGIC = b"MFPK"
VERSION = 2
HEADER_SIZE = 80
CHECKPOINT = 64  # a range or glyph checkpoint every 64 entries


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
    """Sorted code points as (first, last) runs of consecutive values, at most 256 long and within one plane."""
    out = []
    for cp in cps:
        if out and cp == out[-1][1] + 1 and cp - out[-1][0] < 256 and (cp >> 16) == (out[-1][0] >> 16):
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
    ap.add_argument("--metric-index-size", type=int, choices=(1, 2), help="force 1- or 2-byte metrics indices (tests)")
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

    # Planes, ranges (3 bytes each) and range checkpoints
    plane_tab = bytearray()
    range_tab = bytearray()
    range_checkpoints = bytearray()
    plane = -1
    index = 0
    rs = runs(cps)
    for i, (lo, hi) in enumerate(rs):
        if lo >> 16 != plane:
            plane = lo >> 16
            plane_tab += struct.pack("<B3xI", plane, i)
        if i % CHECKPOINT == 0:
            range_checkpoints += struct.pack("<I", index)
        range_tab += struct.pack("<HB", lo & 0xFFFF, hi - lo)
        index += hi - lo + 1

    # Metrics table (most common first), a metrics index per glyph, glyph checkpoints, bitmaps
    metrics = []
    for cp, (advance, x, y, w, h, bits) in zip(cps, glyphs):
        y -= top
        if not (0 <= advance <= 255 and w <= 255 and h <= 255 and -128 <= x <= 127 and -128 <= y <= 127):
            sys.exit("U+%04X doesn't fit the glyph fields (advance %d, box %dx%d at %d,%d)" % (cp, advance, w, h, x, y))
        metrics.append((advance, w, h, x, y))
    distinct = [m for m, _ in Counter(metrics).most_common()]
    if len(distinct) > 0xFFFF:
        sys.exit("too many distinct glyph metrics")
    metric_index_size = 1 if len(distinct) <= 256 else 2
    if a.metric_index_size:
        if a.metric_index_size < metric_index_size:
            sys.exit("%d distinct metrics don't fit 1-byte indices" % len(distinct))
        metric_index_size = a.metric_index_size
    metric_index = {m: i for i, m in enumerate(distinct)}
    metrics_tab = b"".join(struct.pack("<BBBbb", *m) for m in distinct)
    glyph_tab = bytearray()
    glyph_checkpoints = bytearray()
    bitmaps = bytearray()
    for i, (m, g) in enumerate(zip(metrics, glyphs)):
        if i % CHECKPOINT == 0:
            glyph_checkpoints += struct.pack("<I", len(bitmaps))
        glyph_tab += struct.pack("<B" if metric_index_size == 1 else "<H", metric_index[m])
        bitmaps += g[5]

    name = a.name or os.path.splitext(os.path.basename(a.out))[0]
    meta_lines = [
        "name=" + name,
        "font=" + os.path.basename(a.font),
        "size=%d" % a.size,
        "license=" + a.license,
        "source=" + a.source,
        "created=" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]
    if a.set:
        meta_lines.append("sets=" + a.set)
    meta = "\n".join(meta_lines).encode("utf-8")

    parts = [plane_tab, range_tab, range_checkpoints, metrics_tab, glyph_tab, glyph_checkpoints, bitmaps, meta]
    offsets = []
    off = HEADER_SIZE
    for part in parts:
        offsets.append(off)
        off += len(part)
    file_size = off
    max_advance = max((g[0] for g in glyphs), default=0)

    tail = struct.pack("<BBBBBBHIIIIIIIIIIII8x", 1, line_height, baseline, max_advance, len(plane_tab) // 8,
                       metric_index_size, len(distinct), len(cps), len(rs), offsets[0], offsets[1], offsets[2],
                       offsets[3], offsets[4], offsets[5], offsets[6], len(bitmaps), offsets[7], len(meta))
    body = tail + b"".join(bytes(p) for p in parts)
    header = MAGIC + struct.pack("<HHII", VERSION, HEADER_SIZE, file_size, zlib.crc32(body))
    assert len(header) + len(tail) == HEADER_SIZE
    with open(a.out, "wb") as f:
        f.write(header + body)

    print("%s: %d glyphs (%d not in the font), %d ranges, %d metrics, line height %d, baseline %d, %d bytes"
          % (a.out, len(cps), missing, len(rs), len(distinct), line_height, baseline, file_size))
    print("  ranges %d, glyph table %d, checkpoints %d, metrics %d, bitmaps %d, metadata %d"
          % (len(plane_tab) + len(range_tab), len(glyph_tab), len(range_checkpoints) + len(glyph_checkpoints),
             len(metrics_tab), len(bitmaps), len(meta)))


if __name__ == "__main__":
    main()

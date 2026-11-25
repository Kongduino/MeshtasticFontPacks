#!/usr/bin/env python3
"""BDF input to mkfontpack: Unicode, JIS X 0208 and JIS X 0201 fonts give the same glyphs, and merged fonts make
a pack that the reader accepts.

  tests/test_bdf.py out/fpview
"""
import os, subprocess, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import mkfontpack  # noqa: E402

# Glyphs as (Unicode code point, rows of an 8 x 12 box with its bottom 2 px below the baseline)
SHAPES = {
    0x3042: ["00100000", "11111110", "00100000", "01111100", "10101010", "10101010", "10010010", "01100100",
             "00000000", "00000000", "00000000", "00000000"],  # あ
    0x6F22: ["01000100", "11111110", "00101000", "11111110", "00111000", "01010100", "10010010", "00010000",
             "00010000", "00000000", "00000000", "00000000"],  # 漢
    0xFF71: ["11110000", "00010000", "01100000", "01000000", "10000000", "00000000", "00000000", "00000000",
             "00000000", "00000000", "00000000", "00000000"],  # ｱ (half-width)
}


def bdf(registry, encoding, glyphs):
    """A BDF font holding the given glyphs: {code: (advance, rows)}."""
    out = ["STARTFONT 2.1", "FONT -test-%s" % registry, "SIZE 12 75 75", "FONTBOUNDINGBOX 8 12 0 -2",
           "STARTPROPERTIES 4", 'CHARSET_REGISTRY "%s"' % registry, 'CHARSET_ENCODING "%s"' % encoding,
           "FONT_ASCENT 10", "FONT_DESCENT 2", "ENDPROPERTIES", "CHARS %d" % len(glyphs)]
    for code, (advance, rows) in sorted(glyphs.items()):
        w = len(rows[0])
        out += ["STARTCHAR c%04X" % code, "ENCODING %d" % code, "SWIDTH 500 0", "DWIDTH %d 0" % advance,
                "BBX %d 12 0 -2" % w, "BITMAP"]
        out += ["%02X" % (int(r, 2) << (8 - w)) for r in rows]
        out.append("ENDCHAR")
    out.append("ENDFONT")
    return "\n".join(out) + "\n"


def main():
    fpview = sys.argv[1] if len(sys.argv) > 1 else "out/fpview"
    with tempfile.TemporaryDirectory() as tmp:
        def write(name, text):
            path = os.path.join(tmp, name)
            with open(path, "w", encoding="latin-1") as f:
                f.write(text)
            return path

        kana_kanji = {cp: (8, SHAPES[cp]) for cp in (0x3042, 0x6F22)}
        half = {0xFF71: (4, [r[:4] for r in SHAPES[0xFF71]])}
        uni = write("uni.bdf", bdf("ISO10646", "1", {**kana_kanji, **half}))
        jis = write("jis.bdf", bdf("JISX0208.1983", "0", {0x2422: kana_kanji[0x3042], 0x3441: kana_kanji[0x6F22]}))
        roman = write("roman.bdf", bdf("JISX0201.1976", "0", {0xB1: half[0xFF71]}))

        want, _ = mkfontpack.load_bdf(uni)
        got = {}
        for path in (jis, roman):
            glyphs, ascent = mkfontpack.load_bdf(path)
            assert ascent == 10, ascent
            got.update(glyphs)
        assert got == want, (sorted(got), sorted(want))
        assert want[0xFF71][0] == 4 and want[0x3042][0] == 8
        # Ink box: あ's top row is the ascender line's first row, left-aligned, 7 x 8 px
        assert want[0x3042][1:5] == (0, 0, 7, 8), want[0x3042][1:5]

        assert mkfontpack.jisx0208_to_unicode(0x2422) == 0x3042
        assert mkfontpack.jisx0208_to_unicode(0x2F21) is None  # an unassigned row
        assert mkfontpack.jisx0201_to_unicode(0x5C) == 0xA5 and mkfontpack.jisx0201_to_unicode(0xDF) == 0xFF9F

        # Merged JIS fonts make a pack the reader accepts, and the first font wins a shared character
        pack = os.path.join(tmp, "merged.mfp")
        tool = os.path.join(os.path.dirname(__file__), "..", "tools", "mkfontpack.py")
        subprocess.run([sys.executable, tool, "--font", jis, "--font", roman, "--font", uni, "--size", "12",
                        "--ranges", "3042,6F22,FF71", "--out", pack], check=True, stdout=subprocess.DEVNULL)
        subprocess.run([fpview, "-c", pack], check=True, stdout=subprocess.DEVNULL)
    print("test_bdf: OK")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Japanese character sets of mkfontpack, and --set all.

  tests/test_sets.py out/fpview
"""
import os, subprocess, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import mkfontpack  # noqa: E402
from test_bdf import SHAPES, bdf  # noqa: E402


def main():
    fpview = sys.argv[1] if len(sys.argv) > 1 else "out/fpview"
    jis = set(mkfontpack.SETS["jis0208"]())
    cp932 = set(mkfontpack.SETS["cp932"]())
    kanji = set(mkfontpack.SETS["kanji-jis0208"]())

    assert len(jis) == 6879, len(jis)
    assert kanji <= jis
    for c in "※→…“”℃○★♪■あア漢ΑЖ─":
        assert ord(c) in jis, c
    assert ord("〜") in jis and ord("～") not in jis  # JIS maps the wave dash to U+301C

    for c in "①⑳ⅠⅩ㈱㌔№髙﨑ｱﾟ～－漢※":
        assert ord(c) in cp932, c
    assert not any(0xE000 <= cp <= 0xF8FF for cp in cp932)  # the user-defined area has no glyphs
    assert len(jis | cp932) == len(jis) + 516, len(jis | cp932)  # extensions, Windows code points, half-width kana

    # --set all takes every character the font has, and nothing else
    with tempfile.TemporaryDirectory() as tmp:
        font = os.path.join(tmp, "f.bdf")
        with open(font, "w", encoding="latin-1") as f:
            f.write(bdf("ISO10646", "1", {cp: (8, rows) for cp, rows in SHAPES.items()}))
        pack = os.path.join(tmp, "all.mfp")
        tool = os.path.join(os.path.dirname(__file__), "..", "tools", "mkfontpack.py")
        out = subprocess.run([sys.executable, tool, "--font", font, "--size", "12", "--set", "all", "--out", pack],
                             check=True, capture_output=True, text=True).stdout
        assert out.split(": ")[1].startswith("%d glyphs (0 not in the font)" % len(SHAPES)), out
        subprocess.run([fpview, "-c", pack], check=True, stdout=subprocess.DEVNULL)
    print("test_sets: OK")


if __name__ == "__main__":
    main()

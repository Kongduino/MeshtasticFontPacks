# Meshtastic font packs

Unicode text (Chinese, Japanese, Korean, and any other script without shaping) on Meshtastic screens, for
any device, from font packs installed at run time. Step 1 of the plan: the format, a generator and a reader.

| Path | What |
|---|---|
| `SPEC.md` | The pack format (`.mfp`), version 2 |
| `tools/mkfontpack.py` | Builds a pack from a TrueType/OpenType font: one pixel size, chosen code points |
| `tools/upload_pack.py` | Installs (or removes) a pack on a device, over USB or TCP, with the protobuf API's XModem transfer |
| `c/fontpack.h`, `c/fontpack.c` | The reader, plain C99 with no allocation, for the firmware (and this test) |
| `c/fpview.c` | Desktop test: pack info, a full read, text laid out on a screen of a given width |
| `tests/` | UTF-8 decoder tests, and a corruption test (bad packs must never crash the reader) |

## Use

```
python3 -m venv .venv && .venv/bin/pip install pillow fonttools
make            # out/fpview and the test pack out/cjk12.mfp (downloads the test font first)
make test
out/fpview -i out/cjk12.mfp
out/fpview -o out/hello.pbm out/cjk12.mfp "你好，世界！こんにちは 안녕하세요"
python3 tools/upload_pack.py --port /dev/cu.usbmodem101 out/cjk12.mfp   # needs the meshtastic package
```

The upload needs firmware with font pack support (below); it runs at about 8 KB/s over USB (a 320 KB pack in
40 s).

Version 2 stores a range in 3 bytes and a glyph in 1 (an index into a table of the distinct glyph metrics), with
checkpoints every 64 entries: the same packs are 40 to 46% smaller than in version 1.

`mkfontpack.py --help` lists the character sets (`latin1`, `kana`, `hangul-ksx1001`, `hanzi-gb2312`,
`kanji-jis0208`, `hanzi-big5`...); `--ranges` and `--text` add any code points.

The test pack (Latin-1, CJK punctuation, kana, the 2350 common Hangul syllables and the 6763 GB2312 hanzi at
12 px) is 9613 glyphs in 174 KB, with 13-pixel lines: the Station G2's small font is 13 pixels high too.

## Firmware

Tested on a Station G2: branch `font-packs` of the Meshtastic firmware, `src/graphics/fontpack/`. Text drawn
through the emote renderer (messages, node names, notifications...) takes the glyphs the built-in font lacks from
the packs in `/fonts/*.mfp`, and a box (tofu) stands for the characters no pack has. Message lines wrap between
CJK characters. A pack is checked (CRC) when it is installed and put in place even when the one it replaces is
in use; an interrupted or damaged upload changes nothing (SPEC.md, "Installing").

Next: font pack storage other than files (a `FontStore` write side for flash regions, EEPROM...), more sizes, the
TFT (LVGL) screens, and a desktop pack builder.

## Licence

GPL-3.0 (see `LICENSE`), like the Meshtastic firmware the reader is meant for. The test font,
[Fusion Pixel Font](https://github.com/TakWolf/fusion-pixel-font) by TakWolf, is OFL-1.1; `make` downloads it
into `fonts/` and it isn't part of this repository. A pack made from a font carries that font's licence.

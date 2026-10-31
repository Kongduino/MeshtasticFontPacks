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
make cjk16      # 16 px full CJK pack from GNU Unifont, for larger (e-ink) screens
out/fpview -i out/cjk12.mfp
out/fpview -o out/hello.pbm out/cjk12.mfp "你好，世界！こんにちは 안녕하세요"
python3 tools/upload_pack.py --port /dev/cu.usbmodem101 out/cjk12.mfp   # needs the meshtastic package
```

The upload needs firmware with font pack support (below); it runs at about 8 KB/s over USB (a 320 KB pack in
40 s).

Version 2 stores a range in 3 bytes and a glyph in 1 (an index into a table of the distinct glyph metrics), with
checkpoints every 64 entries: the same packs are 40 to 46% smaller than in version 1.

`mkfontpack.py --help` lists the character sets (`latin1`, `kana`, `hangul-ksx1001`, `hanzi-gb2312`,
`kanji-jis0208`, `hanzi-big5`, `hkscs`...); `--ranges` and `--text` add any code points. `make cjk12full` and
`make cjk16` build full CJK packs (with HKSCS, for Cantonese) at 12 and 16 px.

[FontPackBuilder](https://github.com/Kongduino/FontPackBuilder) is a macOS app that does the same with a glyph editor;
`tools/export_sets.py` writes the named sets for it, so both select the same characters.

The test pack (Latin-1, CJK punctuation, kana, the 2350 common Hangul syllables and the 6763 GB2312 hanzi at
12 px) is 9613 glyphs in 174 KB, with 13-pixel lines: the Station G2's small font is 13 pixels high too.

## Firmware

Branch `font-packs` of the Meshtastic firmware, `src/graphics/fontpack/`. Text drawn through the emote renderer
(messages, node names, notifications...) takes the glyphs the built-in font lacks from the installed packs, and a box
(tofu) stands for the characters no pack has. Message lines wrap between CJK characters. A pack is checked (CRC) when
it is installed and put in place even when the one it replaces is in use; an interrupted or damaged upload changes
nothing (SPEC.md, "Installing").

Packs are kept as files in `/fonts`, or in a board's own storage: the board implements `RawFlash` (read, write,
erase), and `FlashSlots` keeps one pack per slot. Boards with packs in an nRF52840's QSPI flash (`QspiRawFlash`):

| Board | Flash | Slots |
|---|---|---|
| Nodara | 4 MB on board | 3 × 1 MB |
| WisMesh Pocket v2 with a RAK15001 (env `rak_wismesh_pocket_fontflash`) | 2 MB in slot C | 2 × 1 MB |
| Elecrow ThinkNode M1 (env `thinknode_m1`, BaseUI) | 2 MB on board (MX25R1635F) | 2 × 1 MB |

Tested on a Station G2 (OLED, 12 px pack in LittleFS), a T-Deck Pro (e-ink, 16 px pack in LittleFS), and the boards
above (16 px or 12 px packs in QSPI flash), exchanging messages in Chinese (simplified and traditional, Cantonese),
Japanese and Korean.

[FontPackBuilder](https://github.com/Kongduino/FontPackBuilder) (macOS) builds packs from any font, with a glyph
editor, and uploads them over USB serial or TCP.

Next: more sizes, the TFT (LVGL) screens, InkHUD, compressed packs.

## Licence

GPL-3.0 (see `LICENSE`), like the Meshtastic firmware the reader is meant for. The fonts aren't part of this
repository: `make` downloads them into `fonts/`. [Fusion Pixel Font](https://github.com/TakWolf/fusion-pixel-font) by
TakWolf is OFL-1.1; [GNU Unifont](https://unifoundry.com/unifont/) is OFL-1.1 or GPL-2.0-or-later with the font
embedding exception. A pack made from a font carries that font's licence.

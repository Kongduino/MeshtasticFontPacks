# Meshtastic font packs

Unicode text (Chinese, Japanese, Korean, and any other script without shaping) on Meshtastic screens, for
any device, from font packs installed at run time. Step 1 of the plan: the format, a generator and a reader.

| Path | What |
|---|---|
| `SPEC.md` | The pack format (`.mfp`), version 1 |
| `tools/mkfontpack.py` | Builds a pack from a TrueType/OpenType font: one pixel size, chosen code points |
| `tools/upload_pack.py` | Installs a pack on a device (USB or TCP) with the protobuf API's XModem transfer, to `/fonts/` |
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

The upload needs firmware with font pack support (step 2, below); it runs at about 1.1 KB/s over USB.

`mkfontpack.py --help` lists the character sets (`latin1`, `kana`, `hangul-ksx1001`, `hanzi-gb2312`,
`kanji-jis0208`, `hanzi-big5`...); `--ranges` and `--text` add any code points.

The test pack (Latin-1, CJK punctuation, kana, the 2350 common Hangul syllables and the 6763 GB2312 hanzi at
12 px) is 9613 glyphs in 320 KB, with 13-pixel lines: the Station G2's small font is 13 pixels high too.

## Firmware

Step 2 (in progress, tested on a Station G2): branch `font-packs` of the Meshtastic firmware, `src/graphics/fontpack/`.
Packs in `/fonts/*.mfp` are loaded at their first use and checked (CRC); text drawn through the emote renderer
(messages, node names, notifications...) takes its missing glyphs from them, and a box (tofu) stands for the
characters no pack has. Message lines wrap between CJK characters.

Next (step 3): replacing and removing packs safely, checking a pack once at install, a faster transfer.

## Licence

GPL-3.0 (see `LICENSE`), like the Meshtastic firmware the reader is meant for. The test font,
[Fusion Pixel Font](https://github.com/TakWolf/fusion-pixel-font) by TakWolf, is OFL-1.1; `make` downloads it
into `fonts/` and it isn't part of this repository. A pack made from a font carries that font's licence.

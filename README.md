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

## Stroke input

[STROKES.md](STROKES.md) specifies a stroke dictionary (`.msd`) for typing Chinese on a device by strokes, in
writing order (五笔画: 横 竖 撇 点 折, keys 1 to 5), simplified and traditional alike. `tools/mkstrokedict.py` builds one
from stroke tables (one `strokes<TAB>character[<TAB>standards]` per line, strokes as `h s p n z`, standards among
`hk tw cn`) and ranks the candidates with the Unicode Character Database's Unihan data; `c/strokedict.c` is the
reader the firmware uses, and `out/sdview` shows its candidates.

```
make strokes                                  # out/strokes.msd from the mainland (cn) table, Hong Kong forms first
out/sdview out/strokes.msd pzpn hszhhspn      # 风狼獄狱…  東鶇
make strokes TABLES="out/strokes-cn.txt hk.txt" PREFER=hk,tw,cn   # with a table of Hong Kong orders
make test-strokes                             # the C reader against the builder's reference lookup
```

The mainland table comes from the English Wiktionary's lists of stroke orders (`tools/wiktionary_strokes.py`, CC
BY-SA 4.0, which the table and the dictionaries built from it keep): 21,483 characters, a 252 KB dictionary. Hong
Kong and Taiwan orders are added as tables of the characters where they differ (STROKES.md).

On a device, the dictionary goes to `/fonts/strokes.msd` (`tools/upload_pack.py --port ... out/strokes.msd`), next
to a font pack that has the characters. On the T-Deck Pro, Alt+Space switches the compose screen to strokes: W E R
S D (printed 1 to 5) type 横 竖 撇 点 折 and A (printed *) any stroke; the candidates show at the bottom, Space or Enter
takes the first, Sym+1 to 9 the others, Alt+S and Alt+F page, Backspace removes a stroke and Esc all of them.

## Korean input

`c/hangul.c` types Korean with the 나랏글 (Naratgeul) keypad of Samsung phones: 12 keys (ㄱ ㄴ ㅏㅓ / ㄹ ㅁ ㅗㅜ / ㅅ ㅇ
ㅣ / 획추가 ㅡ 쌍자음), where 획추가 adds a stroke to the letter just typed (ㄴ→ㄷ→ㅌ, ㅇ→ㅎ, ㅏ→ㅑ) and 쌍자음 doubles it
(ㄱ→ㄲ). Letters build syllables as on the phone, a final consonant moving to the next syllable when a vowel follows.
Plain C99, no allocation; `tests/test_hangul.c` checks it against what the phone types (`make test`).

It needs a pack with the `hangul` set: all 11,172 syllables and the letters on their own (Compatibility Jamo), 290 KB
at 16 px. On a device without a keyboard (the Nodara), the on-screen keyboard's `;` key shows 한 and switches to the
12 keys. Korean input is a build of its own (`-DFONTPACK_INPUT_HANGUL=1 -DFONTPACK_INPUT_STROKES=0`, env `nodara-ko`),
without the stroke input.

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

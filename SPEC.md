# Meshtastic Font Pack (MFP) format, version 1

A font pack holds the bitmaps of one font at one pixel size, for a chosen set of Unicode code points.
The firmware draws with its built-in font whatever that font covers (ASCII, plus Latin-1 or a language
build such as `OLED_RU`), and uses the installed packs for every other code point. A code point that no
pack covers is drawn as an empty box ("tofu"), never skipped.

Text stays UTF-8 everywhere (messages, names, storage). The firmware decodes it to code points at
drawing time; packs are indexed by code point, so ranges above U+FFFF (emoji) need nothing special.

File extension: `.mfp`. All integers are little-endian. Offsets are from the start of the file.

## Layout

| Part | Size |
|---|---|
| Header | 64 bytes |
| Range table | `range_count` × 12 bytes |
| Glyph table | `glyph_count` × 8 bytes |
| Bitmaps | `bitmaps_size` bytes |
| Metadata | `meta_size` bytes |

The parts may come in any order and must not overlap; the generator writes them in the order above.

## Header (64 bytes)

| Offset | Type | Field | Notes |
|---|---|---|---|
| 0 | char[4] | `magic` | `"MFPK"` |
| 4 | u16 | `version` | 1. A reader rejects any other value |
| 6 | u16 | `header_size` | 64. A reader accepts larger values and ignores the extra bytes |
| 8 | u32 | `file_size` | The whole pack |
| 12 | u32 | `crc32` | CRC-32 (IEEE, as zlib) of bytes 16 to `file_size` − 1 |
| 16 | u8 | `bpp` | Bits per pixel: 1 |
| 17 | u8 | `line_height` | Pixels from the top of one line to the top of the next |
| 18 | u8 | `baseline` | Pixels from the top of the line to the baseline |
| 19 | u8 | `max_advance` | The widest advance in the pack |
| 20 | u16 | `range_count` | 1 to 65535 |
| 22 | u16 | `flags` | 0 |
| 24 | u32 | `glyph_count` | |
| 28 | u32 | `ranges_offset` | |
| 32 | u32 | `glyphs_offset` | |
| 36 | u32 | `bitmaps_offset` | |
| 40 | u32 | `bitmaps_size` | Below 16 MiB (glyphs address it with 24 bits) |
| 44 | u32 | `meta_offset` | |
| 48 | u32 | `meta_size` | May be 0 |
| 52 | u8[12] | reserved | 0 |

## Range table (12 bytes per range)

| Offset | Type | Field |
|---|---|---|
| 0 | u32 | `first_cp` |
| 4 | u32 | `last_cp` |
| 8 | u32 | `first_glyph` |

Ranges are sorted by `first_cp` and don't overlap. Code point `cp` with `first_cp <= cp <= last_cp`
is glyph `first_glyph + (cp - first_cp)`. A reader finds the range with a binary search; dense blocks
(the CJK ideographs, Hangul) cost one entry each.

## Glyph table (8 bytes per glyph)

| Offset | Type | Field | Notes |
|---|---|---|---|
| 0 | u24 | `bitmap_offset` | From `bitmaps_offset` |
| 3 | u8 | `advance` | Pixels the pen moves after the glyph |
| 4 | u8 | `width` | Ink box width; 0 for a blank glyph (space) |
| 5 | u8 | `height` | Ink box height; 0 for a blank glyph |
| 6 | i8 | `x_offset` | Ink box left, from the pen position |
| 7 | i8 | `y_offset` | Ink box top, from the top of the line |

## Bitmaps

Each glyph's ink box, `width × height` pixels, row by row, most significant bit first, packed
continuously across rows (no padding at the end of a row). The last byte is padded with zeros, so a
glyph takes `ceil(width × height / 8)` bytes. A set bit is a lit pixel.

## Metadata

UTF-8 text, one `key=value` per line, not NUL-terminated. Keys the generator writes: `name`, `font`,
`size`, `license`, `source`, `created`, `ranges`. Readers must not depend on it.

## Rules for readers

A reader treats a pack as untrusted data:

- Check `magic`, `version`, `bpp`, and that `file_size` doesn't exceed the storage it sits in.
- Check that every table lies inside the file: `ranges_offset + range_count × 12`,
  `glyphs_offset + glyph_count × 8`, `bitmaps_offset + bitmaps_size`, `meta_offset + meta_size`.
- On every lookup, check that the glyph index is below `glyph_count` and that the bitmap
  (`bitmap_offset + ceil(width × height / 8)`) lies inside `bitmaps_size`. A failed check is a missing glyph.
- Check the CRC when the pack is installed; a pack is enabled only after its CRC matches.
- Never keep the tables in RAM: look them up in storage.

## Installing (firmware, planned)

A pack is uploaded with the XModem transfer of the protobuf API, under the name `font://<name>.mfp`.
The device writes the header last, after the CRC matches, so an interrupted upload leaves no pack.

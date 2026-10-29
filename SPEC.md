# Meshtastic Font Pack (MFP) format, version 2

A font pack holds the bitmaps of one font at one pixel size, for a chosen set of Unicode code points.
The firmware draws with its built-in font whatever that font covers (ASCII, plus Latin-1 or a language
build such as `OLED_RU`), and uses the installed packs for every other code point. A code point that no
pack covers is drawn as an empty box ("tofu"), never skipped.

Text stays UTF-8 everywhere (messages, names, storage). The firmware decodes it to code points at
drawing time; packs are indexed by code point, over the whole Unicode range (U+0000 to U+10FFFF).

File extension: `.mfp`. All integers are little-endian. Offsets are from the start of the file.

Version 2 replaces version 1, which stored 12 bytes per range and 8 bytes per glyph: the same pack is
about 40% smaller. Readers support version 2 only.

## Layout

| Part | Size |
|---|---|
| Header | 80 bytes |
| Plane table | `plane_count` × 8 bytes |
| Range table | `range_count` × 3 bytes |
| Range checkpoints | ⌈`range_count` / 64⌉ × 4 bytes |
| Metrics table | `metrics_count` × 5 bytes |
| Glyph table | `glyph_count` × `metric_index_size` bytes |
| Glyph checkpoints | ⌈`glyph_count` / 64⌉ × 4 bytes |
| Bitmaps | `bitmaps_size` bytes |
| Metadata | `meta_size` bytes |

The parts may come in any order and must not overlap; the generator writes them in the order above.

## Header (80 bytes)

| Offset | Type | Field | Notes |
|---|---|---|---|
| 0 | char[4] | `magic` | `"MFPK"` |
| 4 | u16 | `version` | 2. A reader rejects any other value |
| 6 | u16 | `header_size` | 80. A reader accepts larger values and ignores the extra bytes |
| 8 | u32 | `file_size` | The whole pack |
| 12 | u32 | `crc32` | CRC-32 (IEEE, as zlib) of bytes 16 to `file_size` − 1 |
| 16 | u8 | `bpp` | Bits per pixel: 1 |
| 17 | u8 | `line_height` | Pixels from the top of one line to the top of the next |
| 18 | u8 | `baseline` | Pixels from the top of the line to the baseline |
| 19 | u8 | `max_advance` | The widest advance in the pack |
| 20 | u8 | `plane_count` | 1 to 17 |
| 21 | u8 | `metric_index_size` | 1 or 2: the bytes of a glyph's index into the metrics table |
| 22 | u16 | `metrics_count` | 1 to 256 when `metric_index_size` is 1, 1 to 65535 when it is 2 |
| 24 | u32 | `glyph_count` | At least 1 |
| 28 | u32 | `range_count` | At least 1 |
| 32 | u32 | `planes_offset` | |
| 36 | u32 | `ranges_offset` | |
| 40 | u32 | `range_checkpoints_offset` | |
| 44 | u32 | `metrics_offset` | |
| 48 | u32 | `glyphs_offset` | |
| 52 | u32 | `glyph_checkpoints_offset` | |
| 56 | u32 | `bitmaps_offset` | |
| 60 | u32 | `bitmaps_size` | |
| 64 | u32 | `meta_offset` | |
| 68 | u32 | `meta_size` | May be 0 |
| 72 | u8[8] | reserved | 0 |

## Plane table (8 bytes per plane)

Unicode is 17 planes of 65536 code points. The ranges are grouped by plane, so that a range entry only
needs the low 16 bits of its first code point.

| Offset | Type | Field | Notes |
|---|---|---|---|
| 0 | u8 | `plane` | 0 to 16: the code points' bits 16 to 20 |
| 1 | u8[3] | reserved | 0 |
| 4 | u32 | `first_range` | The index of the plane's first range in the range table |

Planes are sorted by `plane`, and only the planes the pack uses are listed. A plane's ranges run from its
`first_range` to the next plane's `first_range` (or to `range_count` for the last plane).

## Range table (3 bytes per range)

| Offset | Type | Field | Notes |
|---|---|---|---|
| 0 | u16 | `first` | The low 16 bits of the range's first code point |
| 2 | u8 | `count_minus_one` | The range covers `first` to `first + count_minus_one` (1 to 256 code points) |

Within a plane, ranges are sorted by `first` and don't overlap, and a range never crosses the end of its
plane. Longer runs of consecutive code points are split into several ranges. A reader finds the plane,
then the range with a binary search on `first`.

The ranges hold the glyphs in order: the glyph index of a code point is the number of code points in all
the ranges before its own, plus its distance from the start of its range.

## Range checkpoints (4 bytes per 64 ranges)

Entry *k* is a u32: the glyph index of the first code point of range 64 × *k*. To find a code point's glyph
index, a reader adds to the checkpoint of its range's block the counts of the ranges before it in that block
(at most 63, read in one go).

## Metrics table (5 bytes per entry)

The distinct glyph metrics of the pack (glyphs of one script mostly share the same ones).

| Offset | Type | Field | Notes |
|---|---|---|---|
| 0 | u8 | `advance` | Pixels the pen moves after the glyph |
| 1 | u8 | `width` | Ink box width; 0 for a blank glyph (space) |
| 2 | u8 | `height` | Ink box height; 0 for a blank glyph |
| 3 | i8 | `x_offset` | Ink box left, from the pen position |
| 4 | i8 | `y_offset` | Ink box top, from the top of the line |

## Glyph table (`metric_index_size` bytes per glyph)

For each glyph, in glyph index order, its index in the metrics table (u8 or u16).

## Glyph checkpoints (4 bytes per 64 glyphs)

Entry *k* is a u32: the offset, from `bitmaps_offset`, of the bitmap of glyph 64 × *k*. A glyph's bitmap
offset is its block's checkpoint plus the bitmap sizes of the glyphs before it in that block (at most 63).

## Bitmaps

Each glyph's ink box, `width × height` pixels, row by row, most significant bit first, packed
continuously across rows (no padding at the end of a row). The last byte is padded with zeros, so a
glyph takes `ceil(width × height / 8)` bytes, and a blank glyph none. A set bit is a lit pixel. The
bitmaps follow each other in glyph index order.

## Metadata

UTF-8 text, one `key=value` per line, not NUL-terminated. Keys the generator writes: `name`, `font`,
`size`, `license`, `source`, `created`, `sets` (the named character sets used, if any). Readers must not
depend on it.

## Rules for readers

A reader treats a pack as untrusted data:

- Check `magic`, `version`, `bpp`, `plane_count`, `metric_index_size` and `metrics_count`, and that
  `file_size` doesn't exceed the storage it sits in.
- Check that every part lies inside the file, with the sizes given in the layout.
- On every lookup, check what the tables give: a plane's ranges lie inside the range table, a glyph index
  is below `glyph_count`, a metrics index below `metrics_count`, and a bitmap lies inside `bitmaps_size`.
  A failed check is a missing glyph.
- Check the CRC when the pack is installed; a pack is enabled only after its CRC matches.
- Keep the tables in storage, not in RAM. The metrics table may be copied to RAM: it is small (5 bytes
  per entry), and the bitmap offsets add up the metrics of up to 63 glyphs.

## Installing (firmware)

A pack is uploaded with the XModem transfer of the protobuf API, to `/fonts/<name>.mfp`. The device receives
it into `/fonts/<name>.mfp.part`, which the loader ignores, and checks it (structure and CRC) when the transfer
ends: it acknowledges the end of the transfer (ACK) only if the pack passed and was put in place of the pack of
that name, which may be in use; otherwise it deletes the partial file and answers NAK, and nothing changes.
Packs are not checked again when they are loaded.

A pack is removed with the admin message `delete_file_request` (`/fonts/<name>.mfp`).

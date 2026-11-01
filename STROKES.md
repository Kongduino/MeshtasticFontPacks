# Meshtastic Stroke Dictionary (MSD) format, version 1

A stroke dictionary lets a device type Chinese characters by their strokes, in writing order (五笔画, "five
strokes"): the user enters the first strokes of a character and picks it from a short list of candidates, the
most frequent first. It works the same for simplified and traditional characters, and needs no reading
(pinyin, jyutping...).

| Stroke | Value | Letter | Shapes |
|---|---|---|---|
| 横 héng | 1 | `h` | 一 ㇀ (rising) |
| 竖 shù | 2 | `s` | 丨 ㇚ (hooked) |
| 撇 piě | 3 | `p` | 丿 |
| 点 diǎn / 捺 nà | 4 | `n` | 丶 ㇏ |
| 折 zhé | 5 | `z` | every stroke that turns: ㇕ ㇆ ㇗ ㇟ ㇉... |

The dictionary itself carries no font: the characters are drawn from the installed font packs (SPEC.md).

File extension: `.msd`. All integers are little-endian; `u24` is 3 bytes. Offsets are from the start of the
file.

## Layout

| Part | Size |
|---|---|
| Header | 48 bytes |
| Top table | (5 + 25 + ... + 5^`top_depth`) × `top_k` × 3 bytes |
| Entries | `entries_size` bytes |
| Entry checkpoints | ⌈`entry_count` / 64⌉ × 4 bytes |
| Metadata | `meta_size` bytes |

The parts may come in any order and must not overlap; the generator writes them in the order above.

## Header (48 bytes)

| Offset | Type | Field | Notes |
|---|---|---|---|
| 0 | char[4] | `magic` | `"MSDK"` |
| 4 | u16 | `version` | 1. A reader rejects any other value |
| 6 | u16 | `header_size` | 48. A reader accepts larger values and ignores the extra bytes |
| 8 | u32 | `file_size` | The whole dictionary |
| 12 | u32 | `crc32` | CRC-32 (IEEE, as zlib) of bytes 16 to `file_size` − 1 |
| 16 | u32 | `entry_count` | At least 1 |
| 20 | u32 | `entries_offset` | |
| 24 | u32 | `entries_size` | |
| 28 | u32 | `checkpoints_offset` | |
| 32 | u32 | `top_offset` | |
| 36 | u8 | `top_depth` | 0 to 4: the stroke counts the top table covers (1 to `top_depth`) |
| 37 | u8 | `top_k` | 1 to 64: candidates per top-table slot |
| 38 | u8 | `max_strokes` | The longest stroke sequence, at most 63 |
| 39 | u8 | reserved | 0 |
| 40 | u32 | `meta_offset` | |
| 44 | u32 | `meta_size` | |

## Entries

One entry per character and stroke sequence, variable length:

| Size | Field | Notes |
|---|---|---|
| 1 | `n` | Number of strokes, 1 to 63 (bits 6 and 7 are 0) |
| ⌈3n / 8⌉ | strokes | 3 bits per stroke (values 1 to 5), first stroke in the most significant bits of the first byte; unused low bits are 0 |
| 3 | `code_point` | u24: 1 to U+10FFFF, not a surrogate |
| 2 | `rank` | u16: 0 for the most frequent character, 65535 for unranked ones |

Entries are sorted by stroke sequence, compared stroke by stroke (a sequence comes before the longer ones it
starts), then by `rank`, then by `code_point`. Different characters may share a sequence.

## Entry checkpoints

u32 each: checkpoint `i` is the offset of entry 64 × `i`, relative to `entries_offset`. A reader finds the
first entry at or after a prefix with a binary search over the checkpoints, then reads at most 64 entries.

## Top table

For short inputs, which match thousands of characters, the generator stores the best candidates directly:
one slot per stroke sequence of 1 to `top_depth` strokes, in order of length, then of value (`h`, `s`, `p`,
`n`, `z`, `hh`, `hs`...). The slot of strokes s₁…s_d (values 1 to 5) is

    slot = (5^1 + ... + 5^(d−1)) + Σ (s_i − 1) × 5^(d−i)

and holds `top_k` u24 code points, best first, padded with 0.

## Lookup

A character matches an input of strokes s₁…s_k when its sequence starts with them. Candidates come in order of
`rank`, then `code_point`, each character once. For k ≤ `top_depth`, the top table gives the first `top_k`;
for longer inputs a reader scans the matching entries (the generator reports the longest such range).

An input may contain wildcards: any one stroke, for a stroke the user isn't sure of or learned in another order
(Hong Kong, Taiwan and mainland orders differ for some characters). A reader finds the entries that start with
the strokes before the first wildcard, and keeps those that match the whole input; a leading wildcard means
reading every entry. The top table isn't used for inputs with a wildcard.

## Metadata

UTF-8 text, one `key=value` per line, not NUL-terminated. Keys the generator writes: `name`, `table` (the stroke
table's file name), `ranking` (the frequency sources), `license`, `created`. Readers must not depend on it.

## Rules for readers

A reader treats a dictionary as untrusted data: it checks `magic`, `version`, `top_depth`, `top_k`, that every
part lies inside the file and `file_size` inside its storage, and, while reading, every entry's `n`, length,
stroke values and code point. An invalid code point in a top-table slot ends the slot.
The CRC is checked when the dictionary is installed.

## Building one

`tools/mkstrokedict.py` reads stroke tables, one `strokes<TAB>character[<TAB>standards]` per line with the
letters `hspnz`. The standards say whose stroke order the line gives: `hk` (Hong Kong, Education Bureau), `tw`
(Taiwan, Ministry of Education), `cn` (mainland, GB13000.1 字符集汉字笔顺规范 and 通用规范汉字笔顺规范); a line
without them counts for all three. The standards agree on most characters, so a table for one standard need only
list where it differs: `--standards` keeps the orders of the chosen standards, and a character none of its lines
gives for them keeps its other orders. Several `--table` are merged. A character with two orders gets two entries,
and a user finds it by either.

`tools/wiktionary_strokes.py` makes the `cn` table from the English Wiktionary's lists of stroke orders (CC BY-SA
4.0: the table and the dictionaries built from it keep that licence and its attribution, which the table's header
gives). The repository has the converter, not the data.

The characters are ranked with the Unicode Character Database's Unihan data:

1. Usage counts (`kHanyuPinlu`). A traditional character without a count of its own takes its simplified form's
   (`kSimplifiedVariant`), shared among that form's other traditional variants (`kTraditionalVariant`), and cut to
   a tenth when Hong Kong schools don't teach it (no `kGradeLevel`): 國 ranks like 国, 隻 below 只.
   On a tie, the script of the first `--prefer` standard comes first: 時 then 时 for `hk` or `tw`, 时 then 時 for
   `cn`.
2. Then Hong Kong school grade (`kGradeLevel`).
3. Then the tiers of the 2013 list of standard characters (`kTGH`: 1 to 3500, 3501 to 6500, the rest).
4. Then the others, by code point.

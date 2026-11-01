#!/usr/bin/env python3
"""Build a Meshtastic Stroke Dictionary (.msd, see STROKES.md) from a stroke table and Unihan.

  mkstrokedict.py --table strokes-cn.txt --unihan Unihan.zip --out strokes.msd
  mkstrokedict.py --table strokes-cn.txt --table hk.txt --unihan Unihan.zip --out strokes.msd   # tables merged
  mkstrokedict.py --table strokes-cn.txt --unihan Unihan.zip --lookup hspn     # the candidates, as a device lists them

A table has one "strokes<TAB>character[<TAB>standards]" per line, strokes written with h s p n z (横 竖 撇 点 折), and
standards among hk tw cn (a line without them counts for all three; tools/wiktionary_strokes.py makes the cn table). Characters are
ranked with Unihan (kHanyuPinlu, kSimplifiedVariant, kTraditionalVariant, kGradeLevel, kTGH): see STROKES.md.
"""
import argparse, datetime, io, os, re, struct, sys, zipfile, zlib
from collections import defaultdict

MAGIC = b"MSDK"
VERSION = 1
HEADER_SIZE = 48
CHECKPOINT = 64  # an entry checkpoint every 64 entries
LETTERS = "hspnz"  # stroke values 1 to 5
UNRANKED = 0xFFFF
STANDARDS = ("hk", "tw", "cn")  # Hong Kong (Education Bureau), Taiwan (Ministry of Education), mainland (GB13000.1)


def read_table(path, standards=STANDARDS):
    """(strokes as a tuple of 1..5, code point) pairs of the given standards, duplicates removed; and the number of
    duplicates. See read_tables"""
    rows, dups = read_tables([path])
    return select_standards(rows, standards), dups


def read_tables(paths):
    """{(strokes, code point): standards} from stroke tables, and the number of duplicate lines. A line is
    "strokes<TAB>character", optionally followed by <TAB> and the standards whose stroke order it is (cn hk tw,
    separated by spaces or commas); a line without them stands for every standard"""
    rows, dups = {}, 0
    for path in paths:
        dups += _read_one(path, rows)
    return rows, dups


def select_standards(rows, standards):
    """The (strokes, code point) pairs of the given standards. A character no line gives for those standards keeps
    its other orders: the tables list only where the standards differ (most characters have only the cn line)"""
    by_cp = defaultdict(list)
    for (strokes, cp), tags in rows.items():
        by_cp[cp].append((strokes, tags))
    out = []
    for cp, seqs in by_cp.items():
        chosen = [st for st, tags in seqs if tags & set(standards)] or [st for st, _ in seqs]
        out.extend((st, cp) for st in chosen)
    return out


def _read_one(path, rows):
    dups = 0
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) not in (2, 3) or len(parts[1]) != 1:
                sys.exit(f"{path}:{lineno}: expected strokes<TAB>one character[<TAB>standards]: {line!r}")
            letters, ch = parts[:2]
            if not letters or any(c not in LETTERS for c in letters) or len(letters) > 63:
                sys.exit(f"{path}:{lineno}: strokes must be 1 to 63 of {LETTERS}: {letters!r}")
            tags = set(parts[2].replace(",", " ").split()) if len(parts) == 3 else set(STANDARDS)
            if not tags or tags - set(STANDARDS):
                sys.exit(f"{path}:{lineno}: standards are {' '.join(STANDARDS)}: {parts[2]!r}")
            key = (tuple(LETTERS.index(c) + 1 for c in letters), ord(ch))
            if key in rows:
                dups += 1
            rows[key] = rows.get(key, set()) | tags
    return dups


def read_unihan(path):
    """{field: {code point: value}} for the fields the ranking uses, from Unihan.zip or its unzipped folder"""
    fields = ("kHanyuPinlu", "kSimplifiedVariant", "kTraditionalVariant", "kGradeLevel", "kTGH")
    data = {f: {} for f in fields}
    version = ""

    def lines():
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if name.startswith("Unihan_") and name.endswith(".txt"):
                    with open(os.path.join(path, name), encoding="utf-8") as f:
                        yield from f
        else:
            with zipfile.ZipFile(path) as z:
                for name in sorted(z.namelist()):
                    if name.startswith("Unihan_") and name.endswith(".txt"):
                        yield from io.TextIOWrapper(z.open(name), encoding="utf-8")

    for line in lines():
        if line.startswith("# Unicode Version"):
            version = line.split()[-1]
        if not line.startswith("U+"):
            continue
        cp, field, value = line.rstrip("\n").split("\t", 2)
        if field in data:
            data[field][int(cp[2:], 16)] = value
    if not data["kHanyuPinlu"]:
        sys.exit(f"{path}: no Unihan data found")
    return data, version


def rank_key(cp, uh, prefer_traditional=True):
    """Sort key of a character: lower is more frequent"""

    def pinlu(c):
        v = uh["kHanyuPinlu"].get(c)
        return sum(int(n) for n in re.findall(r"\((\d+)\)", v)) if v else 0

    def variants(c, field):
        return {int(v.split("<")[0][2:], 16) for v in uh[field].get(c, "").split()} - {c}

    # Its own count, or else its simplified form's, shared among that form's other traditional variants: 隻 gets a
    # third of 只's (只 also stands for 戠 and 衹), 頭 all of 头's. A form not taught in Hong Kong schools (no
    # kGradeLevel) is a minor one and gets a tenth: 齣 next to 出, 傢 next to 家
    count = pinlu(cp)
    simplified = variants(cp, "kSimplifiedVariant")
    if not count:
        for c in simplified:
            count = max(count, pinlu(c) // max(1, len(variants(c, "kTraditionalVariant"))))
        if cp not in uh["kGradeLevel"]:
            count //= 10
    if count:
        # On a tie (a traditional form taking its simplified form's count), the preferred script first, the other
        # right after: 時 then 时 for Hong Kong or Taiwan, 时 then 時 for the mainland
        traditional = bool(simplified)
        return (0, -count, 0 if traditional == prefer_traditional else 1, cp)
    grade = uh["kGradeLevel"].get(cp)
    if grade:
        return (1, int(grade), 0, cp)
    tgh = uh["kTGH"].get(cp)
    if tgh:
        n = min(int(t.split(":")[1]) for t in tgh.split())
        return (2 if n <= 3500 else 3 if n <= 6500 else 4, n, 0, cp)
    return (5, 0, 0, cp)


def ranks(cps, uh, prefer_traditional=True):
    """{code point: rank}: 0 for the most frequent, UNRANKED for characters no source mentions"""
    out = {}
    key = lambda c: rank_key(c, uh, prefer_traditional)
    for i, cp in enumerate(sorted(cps, key=key)):
        out[cp] = UNRANKED if key(cp)[0] == 5 else min(i, UNRANKED - 1)
    return out


def parse_standards(text):
    tags = [t for t in text.replace(",", " ").split()]
    if not tags or set(tags) - set(STANDARDS) or len(set(tags)) != len(tags):
        sys.exit(f"standards are {' '.join(STANDARDS)}, each once: {text!r}")
    return tags


def pack_strokes(strokes):
    bits, nbits = 0, 0
    for s in strokes:
        bits = (bits << 3) | s
        nbits += 3
    pad = (-nbits) % 8
    return (bits << pad).to_bytes((nbits + pad) // 8, "big")


def slot_index(prefix):
    base = sum(5 ** j for j in range(1, len(prefix)))
    return base + sum((s - 1) * 5 ** (len(prefix) - 1 - i) for i, s in enumerate(prefix))


def lookup(entries, rank, prefix):
    """The candidates for a stroke input, best first, each character once (the reference for the C reader)"""
    found = {cp for strokes, cp in entries if strokes[: len(prefix)] == prefix}
    return sorted(found, key=lambda cp: (rank[cp], cp))


def build(entries, rank, top_depth, top_k, meta):
    entries = sorted(entries, key=lambda e: (e[0], rank[e[1]], e[1]))

    top = defaultdict(set)
    for strokes, cp in entries:
        for d in range(1, min(top_depth, len(strokes)) + 1):
            top[strokes[:d]].add(cp)
    nslots = sum(5 ** d for d in range(1, top_depth + 1))
    top_tab = bytearray(nslots * top_k * 3)
    for prefix, cps in top.items():
        best = sorted(cps, key=lambda cp: (rank[cp], cp))[:top_k]
        off = slot_index(prefix) * top_k * 3
        for i, cp in enumerate(best):
            top_tab[off + i * 3 : off + i * 3 + 3] = cp.to_bytes(3, "little")

    entry_tab, checkpoints = bytearray(), bytearray()
    for i, (strokes, cp) in enumerate(entries):
        if i % CHECKPOINT == 0:
            checkpoints += struct.pack("<I", len(entry_tab))
        entry_tab += bytes((len(strokes),)) + pack_strokes(strokes) + cp.to_bytes(3, "little") + struct.pack("<H", rank[cp])

    meta_bytes = "\n".join(f"{k}={v}" for k, v in meta.items()).encode("utf-8")
    top_offset = HEADER_SIZE
    entries_offset = top_offset + len(top_tab)
    checkpoints_offset = entries_offset + len(entry_tab)
    meta_offset = checkpoints_offset + len(checkpoints)
    file_size = meta_offset + len(meta_bytes)
    max_strokes = max(len(s) for s, _ in entries)
    tail = struct.pack("<IIIIIBBBBII", len(entries), entries_offset, len(entry_tab), checkpoints_offset, top_offset,
                       top_depth, top_k, max_strokes, 0, meta_offset, len(meta_bytes))
    body = tail + bytes(top_tab) + bytes(entry_tab) + bytes(checkpoints) + meta_bytes
    header = MAGIC + struct.pack("<HHII", VERSION, HEADER_SIZE, file_size, zlib.crc32(body))
    data = header + body
    assert len(data) == file_size and len(header) + len(tail) == HEADER_SIZE
    return data, entries


def longest_scan(entries, top_depth):
    """The most entries an input longer than top_depth strokes matches: what a device may have to scan"""
    count = defaultdict(int)
    for strokes, _ in entries:
        if len(strokes) > top_depth:
            count[strokes[: top_depth + 1]] += 1
    return max(count.items(), key=lambda kv: kv[1]) if count else ((), 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", required=True, action="append",
                    help="stroke table: strokes<TAB>character[<TAB>standards] per line; give several to merge them")
    ap.add_argument("--standards", default="hk,tw,cn",
                    help="the stroke orders to include (default hk,tw,cn: all); a character with no line for them "
                         "keeps its other orders")
    ap.add_argument("--prefer", default="hk,tw,cn",
                    help="standards in order of preference: the first decides whether traditional (hk, tw) or "
                         "simplified (cn) forms come first in a tie (default hk,tw,cn)")
    ap.add_argument("--unihan", required=True, help="Unihan.zip, or the folder it unzips to")
    ap.add_argument("--top-depth", type=int, default=3, choices=range(0, 5), help="strokes covered by the top table (default 3)")
    ap.add_argument("--top-k", type=int, default=32, help="candidates per top-table slot, 1 to 64 (default 32)")
    ap.add_argument("--name", help="dictionary name (default: the output file name)")
    ap.add_argument("--license", default="", help="the stroke table's license")
    ap.add_argument("--out", help="output .msd file")
    ap.add_argument("--lookup", action="append", default=[], help="print the candidates for strokes (hspnz or 12345)")
    args = ap.parse_args()
    if not 1 <= args.top_k <= 64:
        ap.error("--top-k must be 1 to 64")
    if not args.out and not args.lookup:
        ap.error("give --out, --lookup or both")

    standards, prefer = parse_standards(args.standards), parse_standards(args.prefer)
    rows, dups = read_tables(args.table)
    entries = select_standards(rows, standards)
    if not entries:
        sys.exit(f"{' '.join(args.table)}: no stroke sequences for {' '.join(standards)}")
    uh, unicode_version = read_unihan(args.unihan)
    rank = ranks({cp for _, cp in entries}, uh, prefer[0] != "cn")

    for text in args.lookup:
        prefix = tuple(int(c) if c.isdigit() else LETTERS.index(c) + 1 for c in text)
        found = lookup(entries, rank, prefix)
        print(f"{text}: {len(found)} — " + "".join(chr(cp) for cp in found[:40]) + (" …" if len(found) > 40 else ""))

    if args.out:
        name = args.name or os.path.splitext(os.path.basename(args.out))[0]
        meta = {
            "name": name,
            "table": " ".join(os.path.basename(t) for t in args.table),
            "standards": " ".join(standards),
            "prefer": " ".join(prefer),
            "ranking": f"Unihan {unicode_version}: kHanyuPinlu, kSimplifiedVariant, kTraditionalVariant, kGradeLevel, kTGH",
            "license": args.license,
            "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        data, entries = build(entries, rank, args.top_depth, args.top_k, meta)
        with open(args.out, "wb") as f:
            f.write(data)
        chars = len({cp for _, cp in entries})
        ranked = sum(1 for cp in {cp for _, cp in entries} if rank[cp] != UNRANKED)
        prefix, scan = longest_scan(entries, args.top_depth)
        print(f"{args.out}: {len(data):,} bytes, {len(entries):,} entries ({chars:,} characters, {ranked:,} ranked), "
              f"{dups:,} duplicate lines skipped")
        print(f"  top table: 1 to {args.top_depth} strokes, {args.top_k} candidates; longest scan beyond it: {scan} entries "
              f"({''.join(LETTERS[s - 1] for s in prefix)})")


if __name__ == "__main__":
    main()

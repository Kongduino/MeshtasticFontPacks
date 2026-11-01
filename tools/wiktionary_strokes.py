#!/usr/bin/env python3
"""Make a stroke table (strokes<TAB>character<TAB>cn) from Wiktionary's lists of stroke orders, which follow the
mainland standards (GB13000.1 字符集汉字笔顺规范, 通用规范汉字笔顺规范).

  wiktionary_strokes.py --out strokes-cn.txt [--cache dir]

Source: the four parts of "Appendix:Stroke orders of CJK Unified Ideographs (YES order)" on the English Wiktionary,
CC BY-SA 4.0. The table keeps that licence: its header names the pages and their revisions. The lists write strokes
with the 30-stroke YES alphabet; this maps them to the five stroke types of STROKES.md: ㇐ ㇀ are 横 (h), ㇑ ㇚ 竖 (s),
㇓ 撇 (p), ㇔ ㇏ 点 (n), and every stroke that turns is 折 (z).
"""
import argparse, json, os, re, sys, urllib.parse, urllib.request

API = "https://en.wiktionary.org/w/api.php"
PAGE = "Appendix:Stroke orders of CJK Unified Ideographs in YES order, part {} of 4"
USER_AGENT = "MeshtasticFontPacks/1.0 (https://github.com/Kongduino/MeshtasticFontPacks)"
LICENSE = "CC BY-SA 4.0"

H, S, P, N = "㇐㇀", "㇑㇚丨", "㇓", "㇔㇏"
ROW = re.compile(r"\[\[wikt:([^|\]]+)\|[^\]]*\]\]\s*\|\|\s*([^|]*?)\s*\|\|\s*(\d+)\s*\|\|\s*([0-9A-Fa-f]{4,6})")
HPJ = "[[File:Cjk m str hpj.svg|15px]]"  # a turning stroke Unicode has no character for


def fetch(part, cache):
    """(wikitext, revision id) of one part, from the cache when it's there"""
    path = os.path.join(cache, f"part{part}.json") if cache else None
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        query = urllib.parse.urlencode({"action": "parse", "page": PAGE.format(part), "prop": "wikitext|revid",
                                        "format": "json", "formatversion": "2"})
        req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.load(r)
        if "parse" not in data:
            sys.exit(f"part {part}: {data.get('error', data)}")
        if path:
            os.makedirs(cache, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
    return data["parse"]["wikitext"], data["parse"]["revid"]


def five(seq):
    """A YES stroke sequence as h s p n z; None when a stroke is unknown"""
    out = []
    for c in seq.replace(HPJ, "折"):
        if c in H:
            out.append("h")
        elif c in S:
            out.append("s")
        elif c in P:
            out.append("p")
        elif c in N:
            out.append("n")
        elif 0x31C0 <= ord(c) <= 0x31EF or 0xE000 <= ord(c) <= 0xF8FF or c in "折ㄣ":
            out.append("z")  # CJK Strokes block, private-use turning strokes, the hpj image, ㄣ (竖折撇)
        else:
            return None
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="stroke table to write")
    ap.add_argument("--cache", help="folder for the downloaded pages (reused when present)")
    args = ap.parse_args()

    rows, revisions, skipped, miscounted = {}, [], [], []
    for part in range(1, 5):
        text, revid = fetch(part, args.cache)
        revisions.append((part, revid))
        for ch, seq, count, cp in ROW.findall(text.replace(HPJ, "折")):
            if len(ch) != 1 or ord(ch) != int(cp, 16) or 0xE000 <= ord(ch) <= 0xF8FF:
                if not 0xE000 <= ord(ch[0]) <= 0xF8FF:  # private-use characters are left out silently
                    skipped.append(f"{ch} U+{cp}: listed under another code point")
                continue
            strokes = five(seq)
            if not strokes:
                skipped.append(f"{ch} U+{cp}: {seq!r} has a stroke that isn't one")
                continue
            # The lists count the hpj image as 30 strokes (熱: 15 strokes, listed as 45); the sequence is kept either way
            if int(count) not in (len(strokes), len(strokes) + 30 * seq.count("折")):
                miscounted.append(f"{ch} U+{cp}: {len(strokes)} strokes, listed as {count}")
            rows.setdefault(strokes + "\t" + ch, None)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("# Stroke orders of CJK Unified Ideographs, mainland standards (GB13000.1 字符集汉字笔顺规范, 通用规范汉字笔顺规范)\n")
        f.write(f"# From the English Wiktionary, {LICENSE} (https://creativecommons.org/licenses/by-sa/4.0/):\n")
        for part, revid in revisions:
            f.write(f"#   {PAGE.format(part)}, revision {revid}\n")
        f.write("#   https://en.wiktionary.org/wiki/Appendix:Stroke_orders_of_CJK_Unified_Ideographs_(YES_order)\n")
        f.write("# Converted to five stroke types (h s p n z) by tools/wiktionary_strokes.py. Columns: strokes, character, standards\n")
        for row in sorted(rows, key=lambda r: (r.split("\t")[0], r.split("\t")[1])):
            f.write(row + "\tcn\n")
    print(f"{args.out}: {len(rows):,} characters (cn), {len(skipped)} skipped, {len(miscounted)} with a wrong stroke count")
    for s in skipped:
        print("  skipped", s)
    for s in miscounted:
        print("  count", s)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Checks the C stroke dictionary reader (out/sdview) against mkstrokedict.py's reference lookup.

  test_strokedict.py --table table.txt --unihan Unihan.zip [--sdview out/sdview]

For several top-table settings it builds a dictionary, then compares every input of 1 to 4 strokes and the prefixes
of a sample of characters: same candidates, same order, same total. Then corrupt and truncated copies must be
refused or give no candidates, never crash.
"""
import argparse, os, random, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkstrokedict as msd

LIMIT = 64  # SD_MAX_CANDIDATES


def sdview(tool, path, inputs):
    """{input: (total, [code points])} from sdview -a"""
    out = {}
    for i in range(0, len(inputs), 500):
        r = subprocess.run([tool, "-a", path] + inputs[i : i + 500], capture_output=True, text=True, errors="replace")
        if r.returncode not in (0, 1) or "runtime error" in r.stderr:
            sys.exit(f"sdview failed: {r.stderr}")
        for line in r.stdout.splitlines():
            key, rest = line.split(": ", 1)
            total, chars = (rest.split("\t") + [""])[:2]
            out[key] = (int(total), [ord(c) for c in chars])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", required=True)
    ap.add_argument("--unihan", required=True)
    ap.add_argument("--sdview", default="out/sdview")
    args = ap.parse_args()

    entries, _ = msd.read_table(args.table)  # one table, every standard
    uh, _ = msd.read_unihan(args.unihan)
    rank = msd.ranks({cp for _, cp in entries}, uh)
    rng = random.Random(1)
    sample = rng.sample(entries, 1500)
    letters = msd.LETTERS
    inputs = set()
    for d in range(1, 5):
        for v in range(5 ** d):
            inputs.add("".join(letters[(v // 5 ** (d - 1 - i)) % 5] for i in range(d)))
    for strokes, _ in sample:
        for d in range(5, len(strokes) + 1):
            inputs.add("".join(letters[s - 1] for s in strokes[:d]))
    # Wildcards: one or two strokes of a sample sequence replaced by ?, anywhere (a leading one scans everything),
    # and a few short patterns
    for strokes, _ in sample[:400]:
        text = [letters[s - 1] for s in strokes[: rng.randrange(1, len(strokes) + 1)]]
        for _ in range(rng.randrange(1, 3)):
            text[rng.randrange(len(text))] = "?"
        inputs.add("".join(text))
    inputs.update(["?", "??", "h?", "?h", "s?z", "???????????????????????????????????????????????", "p?p?p"])
    inputs = sorted(inputs)

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for depth, k in ((3, 32), (0, 1), (4, 64), (2, 7)):
            meta = {"name": "test"}
            data, _ = msd.build(entries, rank, depth, k, meta)
            path = os.path.join(tmp, f"t{depth}_{k}.msd")
            with open(path, "wb") as f:
                f.write(data)
            got = sdview(args.sdview, path, inputs)
            for text in inputs:
                prefix = msd.parse_input(text)
                ref = msd.lookup(entries, rank, prefix)
                if len(prefix) <= depth and None not in prefix:
                    want = (len(ref[:k]), ref[: min(k, LIMIT)])
                else:
                    total = sum(1 for s, _ in entries if msd.matches(s, prefix))
                    want = (total, ref[:LIMIT])
                if got.get(text) != want:
                    failures += 1
                    if failures <= 5:
                        print(f"depth {depth} k {k} {text}: got {got.get(text)}, want {want[0]} {''.join(map(chr, want[1][:20]))}")
            print(f"top depth {depth}, k {k}: {len(inputs)} inputs checked")

        # Damaged copies: refused, or no candidates; never a crash (the sanitizer stops sdview on undefined behaviour)
        data, _ = msd.build(entries, rank, 3, 32, {"name": "test"})
        bad = os.path.join(tmp, "bad.msd")
        for trial in range(300):
            b = bytearray(data)
            if trial < 100:
                b = b[: rng.randrange(len(b))]
            else:
                for _ in range(rng.randrange(1, 20)):
                    b[rng.randrange(len(b))] = rng.randrange(256)
            with open(bad, "wb") as f:
                f.write(b)
            r = subprocess.run([args.sdview, "-a", bad, "h", "szhh", "hszhhspn", "pnhhsnz"], capture_output=True)
            stdout, stderr = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
            if r.returncode not in (0, 1) or "runtime error" in stderr or "\ufffd" in stdout:
                failures += 1
                print(f"damaged copy {trial}: exit {r.returncode} {stderr[:200]} {stdout[:80]!r}")
            r = subprocess.run([args.sdview, "-i", bad], capture_output=True, text=True, errors="replace")
            if trial >= 100 and "CRC: OK" in r.stdout and b != data:
                failures += 1
                print(f"damaged copy {trial}: CRC not caught")
        print("damaged copies: 300 checked")

    print("FAIL" if failures else "OK", f"({failures} failures)" if failures else "")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

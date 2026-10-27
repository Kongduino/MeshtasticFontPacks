#!/usr/bin/env python3
"""Robustness test of the C reader: corrupted and truncated packs must give an error or missing glyphs,
never a crash or a hang. Runs out/fpview (built with UBSan) under Guard Malloc.

  fuzz.py PACK [ROUNDS]
"""
import os, random, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FPVIEW = os.path.join(HERE, "..", "out", "fpview")
ENV = dict(os.environ, DYLD_INSERT_LIBRARIES="/usr/lib/libgmalloc.dylib", MallocScribble="1")
SAMPLE = "你好，世界！こんにちは 안녕하세요 Hello ça va? 😀 \xff\xfe"


def run(args):
    try:
        p = subprocess.run([FPVIEW] + args, env=ENV, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "hang"
    if p.returncode < 0 or p.returncode > 2:  # killed by a signal, or a sanitizer report
        return "crash %d: %s" % (p.returncode, p.stderr.decode(errors="replace")[-300:])
    return None


def mutations(data, rnd):
    """A corrupted copy of the pack, and what was done."""
    d = bytearray(data)
    hdr = struct.unpack_from("<4sHHIIBBBBHHIIIIIII", d)
    ranges_off, glyphs_off = hdr[12], hdr[13]
    kind = rnd.randrange(7)
    if kind == 0:  # a header field set to an extreme value
        field = rnd.choice([8, 20, 24, 28, 32, 36, 40, 44, 48])
        value = rnd.choice([0, 1, 0x7FFFFFFF, 0xFFFFFFFF, len(d), len(d) - 1, rnd.getrandbits(32)])
        size = 2 if field == 20 else 4
        d[field:field + size] = value.to_bytes(4, "little")[:size]
        return d, "header +%d = %#x" % (field, value)
    if kind == 1:  # a range entry with random values
        i = rnd.randrange(hdr[9])
        off = ranges_off + i * 12 + rnd.choice([0, 4, 8])
        d[off:off + 4] = rnd.getrandbits(32).to_bytes(4, "little")
        return d, "range %d" % i
    if kind == 2:  # a glyph entry with random values
        i = rnd.randrange(hdr[11])
        off = glyphs_off + i * 8
        d[off:off + 8] = rnd.getrandbits(64).to_bytes(8, "little")
        return d, "glyph %d" % i
    if kind == 3:  # truncated
        n = rnd.randrange(len(d))
        return d[:n], "truncated to %d" % n
    if kind == 4:  # random bytes anywhere
        for _ in range(rnd.randrange(1, 50)):
            d[rnd.randrange(len(d))] = rnd.getrandbits(8)
        return d, "random bytes"
    if kind == 5:  # ranges out of order
        a, b = rnd.randrange(hdr[9]), rnd.randrange(hdr[9])
        ra, rb = d[ranges_off + a * 12:ranges_off + a * 12 + 12], d[ranges_off + b * 12:ranges_off + b * 12 + 12]
        d[ranges_off + a * 12:ranges_off + a * 12 + 12], d[ranges_off + b * 12:ranges_off + b * 12 + 12] = rb, ra
        return d, "ranges %d and %d swapped" % (a, b)
    return bytes(rnd.getrandbits(8) for _ in range(rnd.randrange(64, 512))), "garbage"


def main():
    pack = sys.argv[1]
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    data = open(pack, "rb").read()
    rnd = random.Random(1)
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "bad.mfp")
        for n in range(rounds):
            d, what = mutations(data, rnd)
            open(bad, "wb").write(d)
            for args in (["-i", bad], ["-c", bad], [bad, SAMPLE]):
                err = run(args)
                if err:
                    failures += 1
                    keep = os.path.join(HERE, "..", "out", "fail_%d.mfp" % n)
                    open(keep, "wb").write(d)
                    print("round %d (%s), fpview %s: %s (kept as %s)" % (n, what, args[0], err, keep))
    print("%d rounds, %d failures" % (rounds, failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

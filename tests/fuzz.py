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


HEADER = "<4sHHIIBBBBBBHIIIIIIIIIIII"
# Header fields: (offset, size)
FIELDS = [(8, 4), (20, 1), (21, 1), (22, 2), (24, 4), (28, 4), (32, 4), (36, 4), (40, 4), (44, 4), (48, 4), (52, 4),
          (56, 4), (60, 4), (64, 4), (68, 4)]


def mutations(data, rnd):
    """A corrupted copy of the pack, and what was done."""
    d = bytearray(data)
    h = struct.unpack_from(HEADER, d)
    plane_count, mis, metrics_count, glyph_count, range_count = h[9], h[10], h[11], h[12], h[13]
    planes_off, ranges_off, rcp_off, metrics_off, glyphs_off, gcp_off = h[14:20]

    def poke(off, n, what):
        d[off:off + n] = rnd.getrandbits(8 * n).to_bytes(n, "little")
        return d, what

    kind = rnd.randrange(11)
    if kind == 0:  # a header field set to an extreme value
        off, size = rnd.choice(FIELDS)
        value = rnd.choice([0, 1, 2, 17, 18, 255, 256, 0xFFFF, 0x7FFFFFFF, 0xFFFFFFFF, len(d), len(d) - 1,
                            rnd.getrandbits(32)])
        d[off:off + size] = (value & ((1 << (8 * size)) - 1)).to_bytes(size, "little")
        return d, "header +%d = %#x" % (off, value)
    if kind == 1:
        i = rnd.randrange(plane_count)
        return poke(planes_off + i * 8 + rnd.choice([0, 4]), rnd.choice([1, 4]), "plane %d" % i)
    if kind == 2:
        i = rnd.randrange(range_count)
        return poke(ranges_off + i * 3 + rnd.choice([0, 2]), 1 + rnd.randrange(2), "range %d" % i)
    if kind == 3:
        i = rnd.randrange((range_count + 63) // 64)
        return poke(rcp_off + i * 4, 4, "range checkpoint %d" % i)
    if kind == 4:
        i = rnd.randrange(metrics_count)
        return poke(metrics_off + i * 5 + rnd.randrange(5), 1, "metrics %d" % i)
    if kind == 5:
        i = rnd.randrange(glyph_count)
        return poke(glyphs_off + i * mis, mis, "glyph %d" % i)
    if kind == 6:
        i = rnd.randrange((glyph_count + 63) // 64)
        return poke(gcp_off + i * 4, 4, "glyph checkpoint %d" % i)
    if kind == 7:  # truncated
        n = rnd.randrange(len(d))
        return d[:n], "truncated to %d" % n
    if kind == 8:  # random bytes anywhere
        for _ in range(rnd.randrange(1, 50)):
            d[rnd.randrange(len(d))] = rnd.getrandbits(8)
        return d, "random bytes"
    if kind == 9:  # ranges out of order
        a, b = rnd.randrange(range_count), rnd.randrange(range_count)
        ra, rb = d[ranges_off + a * 3:ranges_off + a * 3 + 3], d[ranges_off + b * 3:ranges_off + b * 3 + 3]
        d[ranges_off + a * 3:ranges_off + a * 3 + 3], d[ranges_off + b * 3:ranges_off + b * 3 + 3] = rb, ra
        return d, "ranges %d and %d swapped" % (a, b)
    return bytes(rnd.getrandbits(8) for _ in range(rnd.randrange(80, 512))), "garbage"


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
            for args in (["-i", bad], ["-c", bad], ["-c", "-n", bad], [bad, SAMPLE], ["-n", bad, SAMPLE]):
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

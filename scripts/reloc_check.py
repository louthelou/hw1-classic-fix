#!/usr/bin/env python3
"""reloc_check.py - simulate the Windows loader's base relocation on an original and a patched
Homeworld.exe and prove that every patched byte range survives relocation as intended.

For each patch site it reports every .reloc fixup that overlaps the site, before and after, and
for the ray-cast prologue it checks that the relocated displacement dwords at the NEW operand
positions equal target + delta (what the CPU will see) and that no fixup lands on opcode bytes.

Usage: python -I reloc_check.py <original.exe> <patched.exe> [delta_hex]   (default delta -0x390000,
the base the game loaded at when it crashed: 0x70000 instead of 0x400000)
"""
import struct, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dockfix_patch import sections, va2off, hx, ALL_PATCHES, PATCHES_VIDEO   # noqa: E402

BASE = 0x400000


def relocs(d):
    secs = sections(d)
    pe = struct.unpack_from("<I", d, 0x3c)[0]
    rva, size = struct.unpack_from("<II", d, pe + 24 + 96 + 8 * 5)
    o0 = va2off(secs, BASE + rva)
    out = []
    o = o0
    while o < o0 + size:
        page, bsz = struct.unpack_from("<II", d, o)
        if bsz == 0:
            break
        for i in range((bsz - 8) // 2):
            e = struct.unpack_from("<H", d, o + 8 + 2 * i)[0]
            out.append((BASE + page + (e & 0xfff), e >> 12))
        o += bsz
    return out


def relocate(d, delta):
    d = bytearray(d); secs = sections(d)
    for va, t in relocs(bytes(d)):
        if t == 3:
            off = va2off(secs, va)
            v = struct.unpack_from("<I", d, off)[0]
            struct.pack_into("<I", d, off, (v + delta) & 0xffffffff)
        elif t != 0:
            raise ValueError("unexpected reloc type %d" % t)
    return bytes(d)


def main(argv):
    orig = open(argv[1], "rb").read(); pat = open(argv[2], "rb").read()
    delta = int(argv[3], 16) if len(argv) > 3 else -0x390000
    secs = sections(orig)
    ro, rp = relocate(orig, delta), relocate(pat, delta)
    fix_o = {va for va, t in relocs(orig) if t == 3}
    fix_p = {va for va, t in relocs(pat) if t == 3}
    print("fixups: original %d, patched %d (delta %#x)" % (len(fix_o), len(fix_p), delta & 0xffffffff))
    ok = True
    for va, old, new, note in ALL_PATCHES:
        ln = len(hx(old))
        fo = sorted(f for f in fix_o if va - 3 <= f < va + ln)
        fp = sorted(f for f in fix_p if va - 3 <= f < va + ln)
        if fo or fp:
            print("site %#x len %d (%s): fixups before %s after %s" % (va, ln, note, [hex(f) for f in fo], [hex(f) for f in fp]))
    # ray-cast prologue: new operand positions and their targets
    expect = {0x42aa7d: 0x6d1d0c, 0x42aa85: 0x7d2cc0, 0x42aa8a: 0x739c54, 0x42aa98: 0x7d2cc4,
              0x42aaa4: 0x66e664, 0x42aac4: 0x6d1d08, 0x42aade: 0x66e664}
    for pos, target in expect.items():
        got = struct.unpack_from("<I", rp, va2off(secs, pos))[0]
        want = (target + delta) & 0xffffffff
        flag = "ok" if got == want else "WRONG"
        ok &= got == want
        print("  relocated operand at %#x = %#x (want %#x) %s" % (pos, got, want, flag))
    # every fixup inside the prologue / 1-len site must be one of the expected operand positions
    for f in sorted(fix_p):
        if 0x42aa79 - 3 <= f < 0x42aa79 + 131 or 0x42abeb - 3 <= f < 0x42abeb + 8:
            if f not in expect:
                print("  STRAY fixup at %#x inside patched code" % f); ok = False
    # relocated patched code must equal the unrelocated patched code except at the operand positions
    for va, old, new, note in PATCHES_VIDEO:
        ln = len(hx(old)); off = va2off(secs, va)
        for i in range(ln):
            a = va + i
            if any(p <= a < p + 4 for p in expect):
                continue
            if rp[off + i] != pat[off + i]:
                print("  byte %#x changed by relocation unexpectedly (%s)" % (a, note)); ok = False
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

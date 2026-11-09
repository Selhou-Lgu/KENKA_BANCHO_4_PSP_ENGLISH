"""LZSS codec guess for Kenka Banchou 4 PAC files (Okumura-style, 4KB ring)."""
import sys


def decompress(data, start=0, out_limit=None, ring_init=0xFEE, fill=0):
    ring = bytearray([fill]) * 0x1000
    r = ring_init
    out = bytearray()
    i = start
    n = len(data)
    while i < n:
        flags = data[i]; i += 1
        for bit in range(8):
            if i >= n:
                break
            if flags & (1 << bit):
                c = data[i]; i += 1
                out.append(c); ring[r] = c; r = (r + 1) & 0xFFF
            else:
                if i + 1 >= n:
                    i = n; break
                b1, b2 = data[i], data[i + 1]; i += 2
                pos = b1 | ((b2 & 0xF0) << 4)
                ln = (b2 & 0x0F) + 3
                for k in range(ln):
                    c = ring[(pos + k) & 0xFFF]
                    out.append(c); ring[r] = c; r = (r + 1) & 0xFFF
            if out_limit and len(out) >= out_limit:
                return bytes(out[:out_limit]), i
    return bytes(out), i


def compress(data, ring_init=0xFEE, max_chain=24):
    """Greedy LZSS matching the decoder above (min 3, max 18, 4KB ring).

    Ring position of source byte i is (ring_init + i) & 0xFFF. Only references
    already-written data (distance <= 4078) so the zero-filled ring start is never used.
    """
    n = len(data)
    out = bytearray()
    heads = {}
    i = 0
    MAXD = 0x1000 - 18
    while i < n:
        flag_pos = len(out); out.append(0); flags = 0
        for bit in range(8):
            if i >= n:
                break
            best_len, best_pos = 0, 0
            if i + 2 < n:
                key = data[i:i + 3]
                chain = heads.get(key)
                if chain:
                    lim = min(18, n - i)
                    for p in reversed(chain[-max_chain:]):
                        if i - p > MAXD:
                            break
                        l = 3
                        while l < lim and data[p + l] == data[i + l]:
                            l += 1
                        if l > best_len:
                            best_len, best_pos = l, p
                            if l == lim:
                                break
            if best_len >= 3:
                rp = (ring_init + best_pos) & 0xFFF
                out.append(rp & 0xFF)
                out.append(((rp >> 4) & 0xF0) | (best_len - 3))
                step = best_len
            else:
                flags |= 1 << bit
                out.append(data[i])
                step = 1
            for j in range(i, min(i + step, n - 2)):
                k3 = data[j:j + 3]
                lst = heads.get(k3)
                if lst is None:
                    heads[k3] = [j]
                else:
                    lst.append(j)
                    if len(lst) > 256:
                        del lst[:128]
            i += step
        out[flag_pos] = flags
    return bytes(out)


def compress_optimal(data, ring_init=0xFEE, max_chain=128):
    """Optimal-parse LZSS (min bit cost: literal 9, match 17). Same format as compress()."""
    n = len(data)
    MAXD = 0x1000 - 18
    best = [(0, 0)] * n
    heads = {}
    for i in range(n):
        bl, bp = 0, 0
        if i + 2 < n:
            key = data[i:i + 3]
            chain = heads.get(key)
            if chain:
                lim = min(18, n - i)
                for p in reversed(chain[-max_chain:]):
                    if i - p > MAXD:
                        break
                    l = 3
                    while l < lim and data[p + l] == data[i + l]:
                        l += 1
                    if l > bl:
                        bl, bp = l, p
                        if l == lim:
                            break
            lst = heads.setdefault(key, [])
            lst.append(i)
            if len(lst) > 512:
                del lst[:256]
        best[i] = (bl, bp)
    INF = float("inf")
    cost = [0] * (n + 1)
    choice = [1] * n
    for i in range(n - 1, -1, -1):
        c, ch = 9 + cost[i + 1], 1
        bl = best[i][0]
        for l in range(3, bl + 1):
            v = 17 + cost[i + l]
            if v < c:
                c, ch = v, l
        cost[i], choice[i] = c, ch
    out = bytearray()
    i = 0
    while i < n:
        flag_pos = len(out); out.append(0); flags = 0
        for bit in range(8):
            if i >= n:
                break
            l = choice[i]
            if l >= 3:
                rp = (ring_init + best[i][1]) & 0xFFF
                out.append(rp & 0xFF); out.append(((rp >> 4) & 0xF0) | (l - 3))
                i += l
            else:
                flags |= 1 << bit; out.append(data[i]); i += 1
        out[flag_pos] = flags
    return bytes(out)


def pack(data):
    """Full PAC entry payload: u32 size + LZSS stream."""
    import struct
    return struct.pack("<I", len(data)) + compress(data)


if __name__ == "__main__":
    path, off, size = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
    with open(path, "rb") as f:
        f.seek(off)
        raw = f.read(size)
    out, used = decompress(raw, start=int(sys.argv[4], 0) if len(sys.argv) > 4 else 0)
    sys.stdout.buffer.write(out)

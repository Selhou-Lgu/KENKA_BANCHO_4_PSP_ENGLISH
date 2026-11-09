"""Minimal ISO9660 patcher: replace files in place (same/smaller size) or
relocate them to the end of the image (grown files).

usage (as module): patch_iso(src_iso, dst_iso, {"/PSP_GAME/USRDIR/PAC0.BIN": bytes or path, ...})
"""
import os, shutil, struct

SECTOR = 2048


def _records(f, lba, size):
    """Yield (abs_offset_of_record, name, is_dir, extent, length) for a directory."""
    f.seek(lba * SECTOR)
    data = f.read(size)
    pos = 0
    while pos < len(data):
        ln = data[pos]
        if ln == 0:
            pos = (pos // SECTOR + 1) * SECTOR
            continue
        rec = data[pos:pos + ln]
        ext = struct.unpack_from("<I", rec, 2)[0]
        length = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        nl = rec[32]
        name = rec[33:33 + nl]
        if name not in (b"\x00", b"\x01"):
            nm = name.decode("ascii").split(";")[0]
            yield lba * SECTOR + pos, nm, bool(flags & 2), ext, length
        pos += ln


def find(f, path):
    f.seek(16 * SECTOR + 156)
    root = f.read(34)
    lba = struct.unpack_from("<I", root, 2)[0]
    size = struct.unpack_from("<I", root, 10)[0]
    parts = [p for p in path.split("/") if p]
    for i, part in enumerate(parts):
        for roff, nm, isdir, ext, length in _records(f, lba, size):
            if nm.upper() == part.upper():
                if i == len(parts) - 1:
                    return roff, ext, length
                lba, size = ext, length
                break
        else:
            raise FileNotFoundError(path)


def _set_record(f, roff, ext, length):
    f.seek(roff + 2); f.write(struct.pack("<I", ext) + struct.pack(">I", ext))
    f.seek(roff + 10); f.write(struct.pack("<I", length) + struct.pack(">I", length))


def patch_iso(src, dst, files, log=print):
    if os.path.abspath(src) != os.path.abspath(dst):
        log(f"copying ISO -> {dst}")
        shutil.copyfile(src, dst)
    with open(dst, "r+b") as f:
        f.seek(0, 2)
        end = f.tell()
        end_lba = (end + SECTOR - 1) // SECTOR
        for path, content in files.items():
            if isinstance(content, str):
                content = open(content, "rb").read()
            roff, ext, length = find(f, path)
            alloc = (length + SECTOR - 1) // SECTOR * SECTOR
            if len(content) <= alloc:
                f.seek(ext * SECTOR); f.write(content)
                if len(content) < alloc:
                    f.write(b"\x00" * (alloc - len(content)))
                _set_record(f, roff, ext, len(content))
                log(f"  {path}: in place ({len(content)} bytes)")
            else:
                f.seek(end_lba * SECTOR); f.write(content)
                pad = (-len(content)) % SECTOR
                f.write(b"\x00" * pad)
                _set_record(f, roff, end_lba, len(content))
                log(f"  {path}: relocated to LBA {end_lba} ({len(content)} bytes)")
                end_lba += (len(content) + pad) // SECTOR
        # volume space size in PVD
        f.seek(16 * SECTOR + 80)
        f.write(struct.pack("<I", end_lba) + struct.pack(">I", end_lba))
        f.truncate(end_lba * SECTOR)

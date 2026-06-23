#!/usr/bin/env python3
"""Minimal ESP32-C3 app-image (.bin) -> ELF converter for static analysis (Ghidra)."""
import sys, struct
from esptool.bin_image import LoadFirmwareImage

if len(sys.argv) != 3:
    sys.exit("usage: esp32c3_bin2elf.py <app.bin> <out.elf>")

in_path, out_path = sys.argv[1], sys.argv[2]
img = LoadFirmwareImage('esp32c3', in_path)

EM_RISCV = 243
ELFCLASS32 = 1
ELFDATA2LSB = 1
ET_EXEC = 2
PT_LOAD = 1
SHT_NULL = 0
SHT_PROGBITS = 1
SHT_NOBITS = 8
SHT_STRTAB = 3
SHF_ALLOC = 0x2
SHF_EXECINSTR = 0x4
SHF_WRITE = 0x1

# Classify segments by load address.
def classify(addr):
    # ESP32-C3 memory map
    if 0x40380000 <= addr < 0x403E0000:
        return ('iram',  SHF_ALLOC | SHF_EXECINSTR, SHT_PROGBITS)
    if 0x42000000 <= addr < 0x42800000:
        return ('irom',  SHF_ALLOC | SHF_EXECINSTR, SHT_PROGBITS)
    if 0x3C000000 <= addr < 0x3C800000:
        return ('drom',  SHF_ALLOC,                 SHT_PROGBITS)
    if 0x3FC80000 <= addr < 0x3FCE0000:
        return ('dram',  SHF_ALLOC | SHF_WRITE,     SHT_PROGBITS)
    if 0x50000000 <= addr < 0x50002000:
        return ('rtc',   SHF_ALLOC | SHF_WRITE,     SHT_PROGBITS)
    return ('mem', SHF_ALLOC, SHT_PROGBITS)

segs = []
for s in img.segments:
    kind, flags, sh_type = classify(s.addr)
    segs.append((s.addr, s.data, kind, flags, sh_type))
    print(f"seg load=0x{s.addr:08x} size=0x{len(s.data):x} -> {kind}")

# Build section header string table
shstrtab_names = ['', '.shstrtab']
section_names = []
for i, (addr, data, kind, flags, sh_type) in enumerate(segs):
    name = f'.{kind}{i}'
    section_names.append(name)
    shstrtab_names.append(name)

shstrtab = b''
name_offsets = {}
for n in shstrtab_names:
    name_offsets[n] = len(shstrtab)
    shstrtab += n.encode() + b'\x00'

EHDR_SIZE = 52
PHDR_SIZE = 32
SHDR_SIZE = 40

n_phdr = len(segs)
n_shdr = 1 + len(segs) + 1  # NULL + segs + shstrtab

phoff = EHDR_SIZE
data_off = phoff + n_phdr * PHDR_SIZE

# Layout: ehdr | phdrs | seg data... | shstrtab | shdrs
out = bytearray()

# Reserve ehdr+phdrs
out += b'\x00' * data_off

seg_file_offsets = []
for addr, data, *_ in segs:
    # Align file offset to 4
    while len(out) % 4: out.append(0)
    seg_file_offsets.append(len(out))
    out += data

while len(out) % 4: out.append(0)
shstrtab_off = len(out)
out += shstrtab
while len(out) % 4: out.append(0)
shoff = len(out)

# Section headers
def shdr(name_off, sh_type, flags, addr, offset, size):
    return struct.pack('<IIIIIIIIII', name_off, sh_type, flags, addr, offset, size, 0, 0, 4, 0)

# NULL
out += b'\x00' * SHDR_SIZE
for i, ((addr, data, kind, flags, sh_type), file_off, name) in enumerate(zip(segs, seg_file_offsets, section_names)):
    out += shdr(name_offsets[name], sh_type, flags, addr, file_off, len(data))
# shstrtab
out += shdr(name_offsets['.shstrtab'], SHT_STRTAB, 0, 0, shstrtab_off, len(shstrtab))

shstrndx = 1 + len(segs)  # index of shstrtab

# Program headers
phdrs = b''
for (addr, data, *_), file_off in zip(segs, seg_file_offsets):
    flags = 0
    kind = classify(addr)[0]
    if kind in ('iram','irom'):
        flags = 0x5  # R+X
    elif kind == 'drom':
        flags = 0x4  # R
    else:
        flags = 0x6  # R+W
    phdrs += struct.pack('<IIIIIIII',
        PT_LOAD, file_off, addr, addr, len(data), len(data), flags, 4)

out[phoff:phoff + len(phdrs)] = phdrs

# ELF header
entry = img.entrypoint
ehdr = b'\x7fELF' + bytes([ELFCLASS32, ELFDATA2LSB, 1, 0]) + b'\x00'*8
ehdr += struct.pack('<HHIIIIIHHHHHH',
    ET_EXEC, EM_RISCV, 1,
    entry, phoff, shoff,
    0,  # flags
    EHDR_SIZE, PHDR_SIZE, n_phdr,
    SHDR_SIZE, n_shdr, shstrndx)
out[0:EHDR_SIZE] = ehdr

with open(out_path, 'wb') as f:
    f.write(out)
print(f"wrote {out_path} ({len(out)} bytes), entry=0x{entry:08x}")

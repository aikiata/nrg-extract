#!/usr/bin/env python3
"""Trích âm thanh lossless từ file .nrg kiểu Nero (CD-DA 44.1 kHz / 16-bit / stereo).

Bố cục NRG: audio nằm tuần tự từ offset 0, mỗi sector 2352 byte = 588 frame stereo
16-bit @ 44.1 kHz. Bảng TOC nằm trong chunk CUEX gần cuối file, mỗi bản ghi 8 byte:
[sector 3 byte big-endian][0x00][0x01][track][index][0x00]
  - index 0x01 = INDEX 01 (điểm bắt đầu track)
  - track 0xAA  = lead-out
  - track 1 có sector sentinel 0xFFFFFF -> dùng 0
Tên track nằm ở chunk AFNM ngay trước END!.
"""
import os
import struct
import subprocess
import sys

SR, CH, BPS = 44100, 2, 2
SECTOR = 2352


def parse(path):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        f.seek(max(0, size - 8192))
        tail = f.read()
    i = tail.rfind(b'CUEX')
    if i < 0:
        sys.exit('không thấy chunk CUEX -> không phải NRG audio chuẩn')
    body = tail[i + 12:]

    names = []
    meta = body
    p = meta.find(b'AFNM')
    if p >= 0:
        p += 4
        while p < len(meta) and meta[p] == 0:
            p += 1
        while p < len(meta):
            k = meta.find(b'\x00', p)
            if k < 0 or k == p:
                break
            name = meta[p:k].decode('latin-1')
            if name.lower().endswith('.wav'):
                # byte đệm trước tên (ký tự điều khiển của chunk)
                name = ''.join(c for c in name if 32 <= ord(c) < 127)
                names.append(name.strip())
            p = k + 1

    # bản ghi 8 byte: [sector 4 byte big-endian][0x01][track][index][0x00]
    starts, leadout = [], None
    for k in range(0, len(body) - 8, 8):
        if body[k + 4] != 0x01 or body[k + 7] != 0x00:
            continue
        sec = int.from_bytes(body[k:k + 4], 'big')
        track, index = body[k + 5], body[k + 6]
        if track == 0xAA:
            # bản ghi lead-out: sector thật nằm ở 4 byte kế tiếp (0x00AAxxxx -> lead-out)
            nxt = int.from_bytes(body[k + 8:k + 12], 'big')
            leadout = nxt if 0 < nxt < (1 << 23) else sec
            break
        if index == 0x01 and 0 < sec < (1 << 23):
            starts.append(sec)                 # số track trong CUEX là BCD
    if not starts:
        sys.exit('không đọc được TOC từ CUEX')
    if not starts or starts[0] != 0:
        starts.insert(0, 0)
    if leadout is None:
        leadout = (size - 949) // SECTOR
    return names, starts, leadout


def wav_header(nbytes):
    block = CH * BPS
    return (b'RIFF' + struct.pack('<I', 36 + nbytes) + b'WAVEfmt '
            + struct.pack('<IHHIIHH', 16, 1, CH, SR, SR * block, block, BPS * 8)
            + b'data' + struct.pack('<I', nbytes))


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    kind = sys.argv[3] if len(sys.argv) > 3 else 'flac'
    os.makedirs(outdir, exist_ok=True)
    names, starts, leadout = parse(src)
    ends = starts[1:] + [leadout]
    total = (leadout - starts[0]) * SECTOR
    print(f'{len(starts)} track | lead-out sector {leadout} | '
          f'{(leadout - starts[0]) / 75 / 60:.2f} phút')

    with open(src, 'rb') as f:
        for i, (s, e) in enumerate(zip(starts, ends)):
            f.seek(s * SECTOR)
            pcm = f.read((e - s) * SECTOR)
            label = names[i] if i < len(names) else f'Track {i + 1:02d}'
            import re
            label = re.sub(r'^\s*\d+\.\s*', '', label)
            base = f'{i + 1:02d}. {label.replace(".wav", "").strip()}'
            ext = '.wav' if kind == 'wav' else '.flac'
            dst = os.path.join(outdir, base + ext)
            print(f'  {base}  sector {s}->{e}  {len(pcm) / 4 / SR / 60:5.2f} phút')
            if kind == 'wav':
                with open(dst, 'wb') as o:
                    o.write(wav_header(len(pcm)))
                    o.write(pcm)
            else:
                r = subprocess.run(
                    ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                     '-f', 's16le', '-ar', str(SR), '-ac', str(CH), '-i', 'pipe:0',
                     '-c:a', 'flac', '-compression_level', '8', dst],
                    input=wav_header(len(pcm)) + pcm)
                if r.returncode:
                    sys.exit(f'ffmpeg lỗi ở {base}')
    print('xong ->', outdir)


if __name__ == '__main__':
    main()

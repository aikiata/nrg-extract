# nrg-extract

Trích âm thanh lossless từ ảnh CD `.nrg` kiểu Nero (CD-DA: 44.1 kHz / 16-bit / stereo)
mà không cần driver ảo đĩa, `nrg2wav` hay `cdrdao`.

## Cài đặt

Không cần thư viện Python nào. Cần `ffmpeg` **chỉ khi** xuất ra FLAC (mặc định).
Xuất WAV thì chạy được bằng stdlib thuần.

## Dùng

```bash
# FLAC (khuyến nghị — nén ~40%, lossless bit-perfect)
python3 nrg_extract.py <file.nrg> <thư_mục_đích> flac

# WAV thuần (không cần ffmpeg)
python3 nrg_extract.py <file.nrg> <thư_mục_đích> wav
```

Tên file output lấy từ bảng tên track Nero ghi trong file (chunk `AFNM`), đánh số lại
theo thứ tự TOC.

## Vì sao phải tự đọc cấu trúc

- `ffmpeg` không có demuxer NRG.
- `7z` / `p7zip` không nhận `.nrg`.
- `nrg2iso` chỉ làm được đĩa ISO9660, không dùng được cho CD-DA.
- `nrg2wav` / `cdrdao` có thể làm được nhưng thường không có sẵn trên Linux hiện đại.

## Cấu trúc NRG mà script dựa vào

Ảnh CD-DA của Nero lưu audio **tuần tự từ offset 0**, mỗi sector 2352 byte —
đúng bằng 588 frame stereo 16-bit @ 44.1 kHz, không có header xen giữa. Vì vậy
phần audio chỉ cần cắt theo biên sector.

Bảng TOC nằm trong chunk `CUEX` ở gần cuối file. Mỗi bản ghi 8 byte:

```
[sector : 4 byte big-endian][0x01][track][index][0x00]
```

- `index == 0x01` → INDEX 01, tức điểm bắt đầu track
- `track == 0xAA` → bản ghi lead-out, sector thật nằm ở 4 byte kế tiếp
- Track 1 có sector sentinel `0xFFFFFF` → dùng `0`
- Track 10 là `0x10` (BCD), dễ nhầm với 16 nếu đọc thẳng

Tên track nằm ở chunk `AFNM` trong vùng metadata, phần tử đầu có byte đệm
ký tự điều khiển và phần tử cuối là `VOLM` (volume) — script lọc theo đuôi `.wav`.

Script dùng chunk `CUEX` làm nguồn sự thật. Điều này đã được đối chiếu: mỗi điểm
bắt đầu track lấy từ CUEX đều rơi vào giữa một khoảng im lặng ~3 giây mà
`silencedetect` phát hiện trong dữ liệu gốc.

## Kiểm chứng lossless

Script không tự dùng bộ nén lossy, nhưng để chắc chắn, cách xác minh là decode
ngược FLAC ra PCM rồi so byte-by-byte với sector gốc:

```python
import subprocess, os
S = 2352
starts = [0, 21497, 41425, 64757, 88967, 110960, 138792, 165877, 188775, 203737, 227105]
src = open('file.nrg', 'rb')
flacs = sorted(os.listdir('outdir'))
for i in range(len(starts) - 1):
    pcm = src.read((starts[i + 1] - starts[i]) * S)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f'outdir/{flacs[i]}',
                    '-f', 's16le', '-ar', '44100', '-ac', '2', 'rt.pcm'], check=True)
    out = open('rt.pcm', 'rb').read()
    # ffmpeg thêm 44 byte header RIFF dù đã chỉ định -f s16le
    assert out[44:] == pcm, flacs[i]
```

Lưu ý khi verify: `ffmpeg` với `-f s16le` vẫn ghi thêm 44 byte header RIFF, nên
phải so từ offset 44 trở đi.

## Giới hạn

- Chỉ hỗ trợ CD-DA. Đĩa VCD/SVCD có Mode 2 Form 1/2 và header ISO 9660, script
  này không đọc được.
- Đĩa nhiều session: lấy session đầu tiên trong CUEX.

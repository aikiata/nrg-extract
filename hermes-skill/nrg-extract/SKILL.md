---
name: nrg-extract
version: 1.0.0
description: Extract lossless audio from Nero .nrg CD images to FLAC/WAV.
author: aikiata
license: MIT
metadata:
  hermes:
    tags:
      - audio
      - rip
      - lossless
      - nrg
      - cd-image
    related_skills:
      - media-ingest
triggers:
  - "trích xuất nhạc từ file nrg"
  - "rip cd nrg"
  - "lấy nhạc lossless từ đĩa nrg"
  - "convert .nrg to flac"
  - "file nrg này sao ffmpeg không đọc được"
  - "nrg2wav"
tools:
  - terminal
  - read_file
  - write_file
mutating: true
---

# NRG Extract

Trích âm thanh lossless từ ảnh CD `.nrg` kiểu Nero (CD-DA: 44.1 kHz / 16-bit / stereo).

## When to Use

Bắt đầu skill này khi có **một trong** các dấu hiệu:

- User đính kèm hoặc nhắc tới file có đuôi `.nrg` và muốn lấy nhạc ra
- User hỏi "rip CD này", "trích nhạc lossless từ đĩa", "convert .nrg sang flac"
- `ffprobe` / `ffmpeg` báo lỗi trên file `.nrg` và user cần biết cách xử lý
- User nhắc `nrg2wav`, `cdrdao` nhưng tool không có sẵn trên máy

**Không dùng skill này khi:**

- File là `.bin` + `.cue`, `.iso`, `.img`, `.mdf`/`.mds` → xử lý theo định dạng đó
- File `.nrg` chứa ISO 9660 (VCD/SVCD/CD dữ liệu) → `nrg2iso` hoặc `iat`, không
  phải audio
- User chỉ muốn nghe thử → dùng `sox`/`ffmpeg` để phát thẳng, không cần tách track

## Contract

Skill này đảm bảo:

- Trích đúng số track, đúng tên track, đúng biên — lấy từ TOC trong file, không đoán
- Output **bit-exact**: decode ngược lại phải khớp byte-by-byte với sector gốc
- Không cần quyền root, không cần cài driver ảo đĩa
- Có bằng chứng verify, không chỉ báo "thành công"

## Vì sao tool sẵn có đều không dùng được

Đừng thử vòng vèo — đã kiểm tra rồi:

| Tool | Kết quả |
|------|---------|
| `ffmpeg` | Không có demuxer NRG (`-f nrg` → "Unknown input format") |
| `7z` / `p7zip` | "Cannot open the file as archive" |
| `nrg2iso` | Chỉ làm đĩa ISO9660, **không** dùng được cho CD-DA |
| `nrg2wav`, `cdrdao` | Làm được nhưng thường không có sẵn; cài cần sudo |

Nếu `ffprobe` báo "Invalid data found when processing input" trên `.nrg`, đó là
bình thường — đừng kết luận file hỏng.

## Phases

### Phase 1: Xác định loại đĩa TRƯỚC khi trích

Đọc 8 KB cuối file, tìm magic:

```python
f = open(path, 'rb'); f.seek(-8192, 2); tail = f.read()
tail.rfind(b'NER5')   # footer NRG
tail.rfind(b'CUEX')   # TOC audio CD-DA
tail.rfind(b'CD001')  # ISO 9660 -> KHÔNG phải CD-DA
```

- Có `CUEX` → **CD-DA**, đi tiếp Phase 2
- Có `CD001` → đĩa dữ liệu/VCD, dừng lại, báo user (cần `nrg2iso` hoặc `iat`)

### Phase 2: Chạy script

Script ở `~/nrg-extract/nrg_extract.py`. Nếu máy khác:

```bash
git clone git@github.com:aikiata/nrg-extract.git ~/nrg-extract
```

```bash
python3 ~/nrg-extract/nrg_extract.py <file.nrg> <outdir> flac   # mặc định
python3 ~/nrg-extract/nrg_extract.py <file.nrg> <outdir> wav
```

Chỉ cần stdlib; `ffmpeg` chỉ dùng cho nhánh FLAC.

### Phase 3: Verify bit-exact — BẮT BUỘC

Không được báo xong nếu chưa chạy bước này.

```python
import subprocess, os
S, src, d = 2352, '<file.nrg>', '<outdir>'
starts, flacs = parse_starts(src), sorted(os.listdir(d))  # lấy từ script, KHÔNG hardcode
f = open(src, 'rb')
for i in range(len(starts) - 1):
    pcm = f.read((starts[i+1] - starts[i]) * S)
    subprocess.run(['ffmpeg','-v','error','-y','-i',f'{d}/{flacs[i]}',
                    '-f','s16le','-ar','44100','-ac','2','rt.pcm'], check=True)
    out = open('rt.pcm','rb').read()
    assert out[44:] == pcm, flacs[i]   # LƯU Ý: bỏ 44 byte, xem Anti-Patterns
```

Hai kiểm tra chéo độc lập với CUEX:

```bash
# 1. ffprobe: sample rate / channels / bits / codec từng file
ffprobe -v error -show_entries stream=codec_name,sample_rate,channels,bits_per_raw_sample -of csv=p=0 out.flac
# 2. Biên track phải rơi vào giữa khoảng im lặng ~3s mà silencedetect tìm thấy
ffmpeg -f s16le -ar 44100 -ac 2 -i raw.pcm -af silencedetect=n=-45dB:d=0.5 -f null -
```

Kết quả mong đợi: `flac,44100,2,16` cho mọi file, và mỗi `silence_start` trùng với
`starts[i] / 75` giây.

### Phase 4: Báo cáo

Liệt kê tên file + thời lượng + tổng dung lượng, và nói rõ **đã verify bit-exact
chưa**. Nêu các điểm bất thường thật (ví dụ vài giây silence ở đầu track 1 là dữ
liệu thật trên đĩa, không phải lỗi trích).

## Cấu trúc NRG mà script dựa vào

Ảnh CD-DA của Nero lưu audio **tuần tự từ offset 0**, mỗi sector 2352 byte =
đúng 588 frame stereo 16-bit @ 44.1 kHz, không header xen giữa. Nên phần audio chỉ
cần cắt theo biên sector.

TOC nằm trong chunk `CUEX` gần cuối file, mỗi bản ghi 8 byte:

```
[sector : 4 byte big-endian][0x01][track][index][0x00]
```

Quirk đã xác minh, đừng "sửa" thành cái khác:

- `index == 0x01` → INDEX 01 (điểm bắt đầu track); `index == 0x00` là INDEX 00
- `track == 0xAA` → bản ghi lead-out, **sector thật nằm ở 4 byte kế tiếp**, không
  phải 4 byte cùng bản ghi
- Track 1 có sector sentinel `0xFFFFFF` → dùng `0`
- Track 10 là `0x10` (BCD), dễ nhầm thành 16
- Tên track ở chunk `AFNM`; phần tử đầu có byte đệm ký tự điều khiển, phần tử cuối
  là `VOLM` (volume) → lọc theo đuôi `.wav`
- Footer `NER5` + chunk `DAOX` nằm ở 949 byte cuối file

## Output Format

```
10 track | lead-out sector 227105 | 50.47 phút
  01. Tinh Xot Xa Dua  sector 0->21497   4.78 phút
  ...
xong -> /path/to/outdir
```

Sau đó: bảng tên/thời lượng, dung lượng, xác nhận bit-exact.

## Anti-Patterns

- **Tin `ffmpeg`/`7z` là file hỏng khi chúng fail.** Chúng đơn giản là không hỗ trợ
  NRG.
- **Bỏ qua byte header RIFF 44 byte khi verify.** `ffmpeg -f s16le` vẫn ghi thêm 44
  byte header. So `out[44:] == pcm`, không phải `out == pcm`. Đây là nguyên nhân
  phổ biến nhất của báo "MISMATCH" giả.
- **Dùng `nrg2iso` cho CD-DA.** Nó chỉ extract ISO9660; chạy trên CD-DA sẽ ra rác.
- **Cắt track bằng `silencedetect` thay vì TOC.** Im lặng trong nhạc tình xuất hiện
  giữa bài; TOC mới là nguồn sự thật. Dùng `silencedetect` để *kiểm chứng* TOC.
- **Hardcode danh sách sector.** Phải lấy từ `parse()` của script cho từng file.
- **Báo "xong" mà chưa chạy Phase 3.** Không có verify thì không có bằng chứng
  lossless.
- **Dùng script trong `~/.hermes/cache/scratch/`.** Thư mục này bị dọn sau 24h; bản
  bền là `~/nrg-extract/`.

## Tools Used

- `terminal` — chạy script, ffprobe, ffmpeg verify
- `read_file` / `write_file` — đọc/ghi script khi cần sửa

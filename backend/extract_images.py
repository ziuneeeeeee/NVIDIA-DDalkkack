import zipfile
import io
import re
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
zip_path = os.path.join(base_dir, 'data', 'Training.zip')
out_dir = os.path.join(base_dir, 'data', 'images')
os.makedirs(out_dir, exist_ok=True)

GRADE_ZIPS = [
    '01.원천데이터/TS_1.문제_고등학교_공통수학.zip',
    '01.원천데이터/TS_1.문제_중학교_1학년.zip',
    '01.원천데이터/TS_1.문제_중학교_2학년.zip',
    '01.원천데이터/TS_1.문제_중학교_3학년.zip',
    '01.원천데이터/TS_1.문제_초등학교_3학년.zip',
    '01.원천데이터/TS_1.문제_초등학교_4학년.zip',
    '01.원천데이터/TS_1.문제_초등학교_5학년.zip',
    '01.원천데이터/TS_1.문제_초등학교_6학년.zip',
]

NAME_RE = re.compile(r'^/?[A-Z0-9]+_\d+_\d+_(.+)\.png$', re.IGNORECASE)

outer = zipfile.ZipFile(zip_path, metadata_encoding='cp949')

total_written = 0
for target in GRADE_ZIPS:
    print(f'[extract] {target}', flush=True)
    data = outer.read(target)
    inner = zipfile.ZipFile(io.BytesIO(data), metadata_encoding='cp949')
    count = 0
    for info in inner.infolist():
        if info.is_dir():
            continue
        m = NAME_RE.match(info.filename)
        if not m:
            print(f'  skip (no match): {info.filename}')
            continue
        qid = m.group(1)
        out_path = os.path.join(out_dir, f'{qid}.png')
        with inner.open(info) as src, open(out_path, 'wb') as dst:
            dst.write(src.read())
        count += 1
    print(f'  wrote {count} images', flush=True)
    total_written += count

print(f'DONE. total images written: {total_written}', flush=True)

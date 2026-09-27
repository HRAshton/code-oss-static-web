#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import datetime, gzip, io, os, shutil, tarfile, zipfile
from common import ROOT, DIST, ARTIFACTS, BuildError, load_json, sha256_file, write_json, require

def iter_files(root):
    return sorted((p for p in root.rglob('*') if p.is_file()), key=lambda p: p.relative_to(root).as_posix())

def build_tar(src: Path, out: Path, epoch: int):
    with out.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=epoch) as gz:
            with tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tf:
                for p in iter_files(src):
                    rel = p.relative_to(src).as_posix()
                    data = p.read_bytes()
                    info = tarfile.TarInfo(rel)
                    info.size = len(data); info.mtime = epoch
                    info.mode = 0o755 if os.access(p, os.X_OK) else 0o644
                    info.uid = info.gid = 0; info.uname = info.gname = ''
                    tf.addfile(info, io.BytesIO(data))

def build_zip(src: Path, out: Path, epoch: int):
    dt = datetime.datetime.fromtimestamp(max(epoch, 315532800), datetime.timezone.utc)
    stamp = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in iter_files(src):
            rel = p.relative_to(src).as_posix()
            info = zipfile.ZipInfo(rel, stamp)
            info.create_system = 3
            info.external_attr = ((0o755 if os.access(p, os.X_OK) else 0o644) & 0xFFFF) << 16
            z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

def main():
    require((DIST / 'index.html').is_file(), 'dist/ missing; run the build first')
    lock = load_json(ROOT / 'upstream.lock.json')
    epoch = int(lock['sourceDateEpoch'])
    ARTIFACTS.mkdir(exist_ok=True)
    for p in ARTIFACTS.iterdir():
        if p.is_file(): p.unlink()
    version = f"{lock['tag']}-web.0"
    tgz = ARTIFACTS / f'code-oss-static-web-{version}.tar.gz'
    zipf = ARTIFACTS / f'code-oss-static-web-{version}.zip'
    build_tar(DIST, tgz, epoch); build_zip(DIST, zipf, epoch)
    write_json(ARTIFACTS / 'upstream.json', {
        'repository': lock['repository'], 'tag': lock['tag'], 'commit': lock['commit'],
        'sourceDateEpoch': epoch, 'qualified': lock['qualified'],
    })
    shutil.copy2(ROOT / 'LICENSE', ARTIFACTS / 'LICENSE')
    lines = []
    for p in sorted(x for x in ARTIFACTS.iterdir() if x.is_file() and x.name != 'SHA256SUMS'):
        lines.append(f'{sha256_file(p)}  {p.name}')
    (ARTIFACTS / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'packaged {version} into {ARTIFACTS}')

if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        raise SystemExit(str(e))

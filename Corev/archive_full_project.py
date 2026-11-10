"""Create and verify a complete project ZIP without traversing external links."""
from pathlib import Path
import hashlib
import json
import os
import stat
import sys
import time
import zipfile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
root = Path(__file__).resolve().parents[1]
destination = root.parent / '제출란'
assert root == Path(r'C:\AI_Workspace\개발\GPT_AGENT_2026_STUDENT_ID')
assert destination == Path(r'C:\AI_Workspace\개발\제출란')
assert destination.is_dir() and not destination.is_relative_to(root)
archive = destination / 'GPT_AGENT_2026_STUDENT_ID-전체-PRIVATE-20261021.zip'
temporary = archive.with_suffix('.zip.partial')
if archive.exists() or temporary.exists():
    raise RuntimeError('Output exists; choose a new version instead of overwriting')
entries = []
def fail(error):
    raise error
for base, directories, names in os.walk(root, followlinks=False, onerror=fail):
    for name in directories + names:
        path = Path(base) / name
        info = path.lstat()
        tag = getattr(info, 'st_reparse_tag', 0)
        if tag and tag != 0xA000000C:
            raise RuntimeError('Unsupported reparse point: ' + str(path))
        entries.append((path, info))
total = sum(info.st_size for _, info in entries if stat.S_ISREG(info.st_mode))
print(json.dumps({'entries':len(entries),'source_bytes':total}), flush=True)
done = 0
last = time.monotonic()
links = 0
with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED,
                     compresslevel=1, allowZip64=True) as target:
    for path, before in entries:
        relative = (Path(root.name) / path.relative_to(root)).as_posix()
        if stat.S_ISLNK(before.st_mode):
            entry = zipfile.ZipInfo(relative)
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            target.writestr(entry, os.readlink(path).encode('utf-8'))
            links += 1
        elif stat.S_ISDIR(before.st_mode):
            target.write(path, relative + '/')
        else:
            info = zipfile.ZipInfo.from_file(path, relative)
            info.compress_type = zipfile.ZIP_DEFLATED
            info._compresslevel = 1
            with path.open('rb') as source, target.open(info, 'w', force_zip64=True) as output:
                while block := source.read(4 * 1024 * 1024):
                    output.write(block)
                    done += len(block)
                    if time.monotonic() - last >= 20:
                        print(f'Compressing {done/1e9:.2f}/{total/1e9:.2f} GB', flush=True)
                        last = time.monotonic()
            after = path.stat()
            if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
                raise RuntimeError('Source changed during compression: '+str(path))
print('Compression finished; checking every ZIP entry CRC...', flush=True)
with zipfile.ZipFile(temporary) as check:
    if check.testzip() is not None:
        raise RuntimeError('ZIP CRC verification failed')
with temporary.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
temporary.rename(archive)
archive.with_suffix('.sha256').write_text(digest+'  '+archive.name+'\n', encoding='utf-8')
print(json.dumps({'archive':archive.name,'bytes':archive.stat().st_size,
                  'entries':len(entries),'symbolic_links':links,'crc':'PASS','sha256':digest},ensure_ascii=False),flush=True)

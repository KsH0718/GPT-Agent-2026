"""Create submission ZIP; excludes generated caches and private data."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parent
source = root / "submission/Corev-Windows"
archive = root / "submission/Corev-Professor-PRIVATE-20261021.zip"
if archive.exists():
    raise RuntimeError("Archive already exists; use a new version name")
files = sorted(p for p in source.rglob('*') if p.is_file() and
               '__pycache__' not in p.parts and p.suffix != '.pyc')
assert not any(p.name in {'.env', 'pyvenv.cfg'} or p.suffix in {'.db', '.sqlite', '.sqlite3'} for p in files)

# Compare actual developer credentials privately, reporting only pass/fail.
from dotenv import dotenv_values
secrets = set()
for candidate in (root.parent / '.env', root.parent / 'Integrated_agent/.env'):
    if candidate.exists():
        for key, value in dotenv_values(candidate).items():
            if value and len(value) >= 8 and any(word in key.upper() for word in ('KEY','SECRET','TOKEN','CLIENT_ID')):
                secrets.add(value.encode())
for path in files:
    relative = path.relative_to(source)
    if relative.as_posix() == 'private-api.env':
        continue  # Explicitly authorized by the user for the professor-only package.
    if relative.parts[0] in {'python', 'ffmpeg'}:
        continue
    data = path.read_bytes()
    if any(secret in data for secret in secrets):
        raise RuntimeError('Credential matched in submission; packaging stopped')
print('PASS: private credential comparison and forbidden file checks', flush=True)
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as zipped:
    for i, path in enumerate(files):
        zipped.write(path, Path('Corev-Windows') / path.relative_to(source))
        if i % 5000 == 0:
            print(f'Packaged {i}/{len(files)} files', flush=True)
digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
archive.with_suffix('.sha256').write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
with zipfile.ZipFile(archive) as zipped:
    assert zipped.testzip() is None
print(json.dumps({'archive': archive.name, 'bytes': archive.stat().st_size,
                  'files': len(files), 'sha256': digest, 'crc': 'PASS'}), flush=True)

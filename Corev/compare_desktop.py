from pathlib import Path
import os, sys, json, hashlib, concurrent.futures, time

sys.stdout.reconfigure(encoding='utf-8')
desktop = Path(sys.argv[1]).resolve()
workspace = Path(__file__).resolve().parents[1]
assert desktop.name == workspace.name == 'GPT_AGENT_2026_STUDENT_ID'
assert desktop != workspace and not desktop.is_relative_to(workspace)
report_path = Path(__file__).parent / 'desktop_comparison_20261021.json'
errors = []
def inventory(root):
    files, dirs = {}, set()
    def fail(error):
        errors.append(str(error))
    for base, names, filenames in os.walk(root, followlinks=False, onerror=fail):
        if Path(base) == root and root == workspace:
            names[:] = [n for n in names if n != 'Corev']
        for name in list(names) + filenames:
            p = Path(base) / name
            try:
                s = p.lstat()
                tag = getattr(s, 'st_reparse_tag', 0)
                if tag and (tag & 0xFFFF0FFF) != 0x9000001A:
                    errors.append('Unexpected reparse point: ' + str(p))
                    if name in names:
                        names.remove(name)
                    continue
                key = p.relative_to(root).as_posix()
                if name in names:
                    dirs.add(key)
                else:
                    files[key] = (s.st_size, s.st_mtime_ns)
            except OSError as error:
                fail(error)
    return files, dirs

a, ad = inventory(desktop)
b, bd = inventory(workspace)
report = {'desktop': str(desktop), 'workspace': str(workspace), 'excluded': ['workspace/Corev'],
          'desktop_files': len(a), 'workspace_files': len(b),
          'desktop_bytes': sum(x[0] for x in a.values()),
          'desktop_only': sorted(a.keys()-b.keys()), 'workspace_only': sorted(b.keys()-a.keys()),
          'desktop_only_dirs': sorted(ad-bd), 'workspace_only_dirs': sorted(bd-ad),
          'size_different': sorted(k for k in a.keys() & b.keys() if a[k][0] != b[k][0]),
          'content_different': [], 'hash_equal': 0, 'errors': errors, 'completed': False}
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('desktop_only','workspace_only','size_different','errors')},ensure_ascii=False),flush=True)
print('Inventory differences:', {k: len(report[k]) for k in ('desktop_only','workspace_only','size_different')},flush=True)
def compare(key):
    try:
        hashes = []
        for root, snapshot in ((desktop,a), (workspace,b)):
            p = root / key
            with p.open('rb') as stream:
                hashes.append(hashlib.file_digest(stream, 'sha256').digest())
            s = p.stat()
            if (s.st_size,s.st_mtime_ns) != snapshot[key]:
                return key, 'changed during scan'
        return key, hashes[0] == hashes[1]
    except OSError as error:
        return key, str(error)
keys = sorted(k for k in a.keys() & b.keys() if a[k][0] == b[k][0])
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for index, (key, same) in enumerate(pool.map(compare, keys), 1):
        if same is True:
            report['hash_equal'] += 1
        elif same is False:
            report['content_different'].append(key)
        else:
            errors.append(key + ': ' + same)
        if index % 10000 == 0:
            print(f'Hashed {index}/{len(keys)} files',flush=True)
report['completed'] = True
report['safe_duplicate'] = not any(report[k] for k in
    ('desktop_only','desktop_only_dirs','size_different','content_different','errors'))
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:(len(v) if isinstance(v,list) else v) for k,v in report.items()},ensure_ascii=False),flush=True)

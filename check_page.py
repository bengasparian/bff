#!/usr/bin/env python3
"""Safety check before anything is saved to the site.

  python check_page.py          check index.html (data job): placeholders filled, data readable, enough players,
                                script free of syntax errors (node --check, preinstalled on GitHub's runners)
  python check_page.py --json   check the small live files (score job): live.json, news.json, lines.json, parlays.json

Anything that fails is put back to the last saved version (git checkout), so the published site never breaks.
The data check exits with an error so the run shows as failed and nothing new is saved; the next run tries again.
"""
import json, os, re, shutil, subprocess, sys, tempfile

def restore(path, why):
    print(f'CHECK FAILED for {path}: {why}')
    r = subprocess.run(['git', 'checkout', '--', path], capture_output=True, text=True)
    print('  restored the last saved version' if r.returncode == 0 else f'  (no saved version to restore: {r.stderr.strip()[:80]})')

def check_json():
    bad = 0
    for f in ('live.json', 'news.json', 'lines.json', 'parlays.json', 'parlay_history.json', 'bet_inputs.json'):
        if not os.path.exists(f): continue
        try:
            d = json.load(open(f))
            if f == 'news.json' and not isinstance(d.get('items'), list): raise ValueError('no items list')
            if f == 'lines.json' and not isinstance(d.get('lines'), list): raise ValueError('no lines list')
        except Exception as e:
            restore(f, e); bad += 1
    print('live files OK' if not bad else f'{bad} file(s) restored')
    return 0                                       # the score job always continues; restored files simply are not changed

def check_page():
    f = 'index.html'
    if not os.path.exists(f): print('no index.html built this run; nothing to check'); return 0
    h = open(f, encoding='utf-8').read()
    try:
        if '__CSS__' in h or '__DATA__' in h: raise ValueError('template placeholders were not filled')
        if len(h) > 15_000_000: raise ValueError(f'page is unexpectedly large ({len(h) // 1024} KB)')
        m = re.search(r'const D=(\{.*?\});\n', h, re.S)
        if not m: raise ValueError('embedded data not found')
        D = json.loads(m.group(1))
        n = len(D.get('players') or [])
        if n < 300: raise ValueError(f'only {n} players in the data')
        for k in ('asof', 'sched', 'dvp', 'model'):
            if k not in D: raise ValueError(f'data is missing "{k}"')
        js = h[h.rindex('<script>') + 8:h.rindex('</script>')]
        node = shutil.which('node')
        if node:
            with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as t: t.write(js)
            r = subprocess.run([node, '--check', t.name], capture_output=True, text=True); os.unlink(t.name)
            if r.returncode != 0:
                L = r.stderr.strip().splitlines(); msg = next((l for l in L if 'Error' in l), L[-1] if L else '')
                raise ValueError('script syntax error: ' + msg[:200])
        else: print('node not found; skipped the script syntax check')
    except Exception as e:
        restore(f, e); return 1
    print(f'page OK: {n} players, {len(h) // 1024} KB')
    return 0

if __name__ == '__main__':
    sys.exit(check_json() if '--json' in sys.argv else check_page())

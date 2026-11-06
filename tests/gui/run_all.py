"""Run every GUI test (gui_*.py), each in its own temporary project copy and config folder,
and print a summary. Exit code 1 when a test failed.

    python tests/gui/run_all.py                 # all
    python tests/gui/run_all.py bd_suite dm     # only the tests whose name contains one of these

The windows open on screen while a test runs: leave the mouse and keyboard alone until it ends.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 300       # seconds per test (a test hanging longer is reported, not waited for)


def main() -> int:
    """Run the selected GUI tests one after the other and print a summary; 1 when one failed."""
    wanted = sys.argv[1:]
    tests = sorted(glob.glob(os.path.join(HERE, 'gui_*.py')))
    if wanted:
        tests = [t for t in tests if any(w in os.path.basename(t) for w in wanted)]
    results = []
    for path in tests:
        name = os.path.basename(path)[:-3]
        tmp = tempfile.mkdtemp(prefix=f'hdlstudio_{name}_')
        env = dict(os.environ, HDLSTUDIO_TEST_TMP=tmp)
        t0 = time.time()
        try:
            run = subprocess.run([sys.executable, '-u', path], env=env, capture_output=True, text=True,
                                 timeout=TIMEOUT, encoding='utf-8', errors='replace')
            output, code = run.stdout + run.stderr, run.returncode
        except subprocess.TimeoutExpired as e:
            output, code = (e.stdout or '') + f'\nTIMEOUT after {TIMEOUT} s', 2
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        lines = output.splitlines()
        failed = [l for l in lines if l.startswith('FAIL ')]
        passed = sum(1 for l in lines if l.startswith('PASS'))
        broken = code != 0 and not failed           # crashed or timed out without a FAIL line
        # a FAIL line counts even when the test's own count missed it (e.g. a dialog nobody answered)
        status = 'ok' if code == 0 and not failed else 'FAILED'
        results.append((name, status, passed, failed, broken, output))
        print(f'{status:6} {name:28} {passed:3} passed, {len(failed)} failed  ({time.time() - t0:.0f} s)', flush=True)
        for l in failed:
            print('        ' + l)
        if broken:
            # e.g. 0xc0000005 (a crash in Qt on Windows) after every check passed
            print(f'        exited with code {code} ({code & 0xFFFFFFFF:#x}) without a FAIL line; last lines:')
            print('        ' + '\n        '.join(lines[-15:]))
    bad = [r for r in results if r[1] != 'ok']
    print(f'\n{len(results) - len(bad)}/{len(results)} test files passed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

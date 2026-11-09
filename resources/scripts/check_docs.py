"""Maintenance check of the documentation of the repository.

    python resources/scripts/check_docs.py

1. Every Python module, class and function of src/, bin/ and tests/ has a docstring (the
   project rule, see docs/development.md). Lists what is missing.
2. Every relative link and image of the Markdown files points at an existing file.

Exit code 1 when something is missing, so it can run before a commit.
"""
from __future__ import annotations

import ast
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# test output and scratch folders are not part of the code base
SKIP = ('/work/', '/out/', '/build/', '/dist/', '/.venv/')


def _skipped(path: str) -> bool:
    """True for files under the generated / scratch folders of SKIP."""
    q = '/' + path.replace(os.sep, '/')
    return any(s in q for s in SKIP)


def missing_docstrings() -> list[str]:
    """'file:line name' for every module / class / function without a docstring."""
    out = []
    files = (glob.glob('src/**/*.py', recursive=True) + glob.glob('bin/*.py')
             + glob.glob('tests/**/*.py', recursive=True) + glob.glob('resources/scripts/*.py') + glob.glob('scripts/*.py'))
    for path in sorted(files):
        if _skipped(path):
            continue
        tree = ast.parse(open(path, encoding='utf-8').read())
        if ast.get_docstring(tree) is None:
            out.append(f'{path}:1 <module>')
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.get_docstring(n) is None:
                out.append(f'{path}:{n.lineno} {n.name}')
    return out


def broken_links() -> list[str]:
    """'file -> target' for every relative Markdown link whose target does not exist."""
    out = []
    for md in sorted(glob.glob('**/*.md', recursive=True)):
        if _skipped(md):
            continue
        text = open(md, encoding='utf-8').read()
        for m in re.finditer(r'\]\(([^)#\s]+)', text):          # [text](target) and ![img](target)
            target = m.group(1)
            if target.startswith(('http://', 'https://', 'mailto:')):
                continue
            if not os.path.exists(os.path.join(os.path.dirname(md), target)):
                out.append(f'{md} -> {target}')
    return out


def main() -> int:
    """Run both checks from the repository root and print the problems."""
    os.chdir(ROOT)
    docs, links = missing_docstrings(), broken_links()
    for line in docs:
        print('no docstring:', line)
    for line in links:
        print('broken link: ', line)
    print(f'{len(docs)} missing docstring(s), {len(links)} broken link(s)')
    return 1 if docs or links else 0


if __name__ == '__main__':
    sys.exit(main())

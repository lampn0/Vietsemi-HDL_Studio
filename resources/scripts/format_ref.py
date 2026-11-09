"""Build docs/formats/sm-sb-bd-reference.html: the syntax reference of the legacy state diagram (.sm),
symbol (.sb) and block diagram (.bd) files, for looking things up while changing
formats/import_sm.py, export_sm.py, export_sb.py and import_bd.py.

    python resources/scripts/format_ref.py [sample folder or file ...]

Two sources are merged:
  * an inventory made by parsing sample files with formats.sexpr: every object type, every key of
    it, how often it appears, the kinds of values, the most frequent small values, where the type
    is nested (parent type and key), what `&N` references point to, and a short example;
  * the notes written by hand in format_notes.py: the meaning of types and keys, the topics
    (syntax, units, encoding, signals, ports, ...) and the change log.

For each key and type the page also lists where the code names it (a quoted 'key' in src/formats,
src/project and src/model.py), so the page shows what HDL Studio reads or writes today.

Quoted strings are shown as "…" when they are design content of the scanned projects rather than
part of the format: the strings of DESIGN_KEYS (names, libraries, ranges, expressions, values,
comments), anything that looks like a path, and any string found in fewer than MIN_FILES sample
files or in less than MIN_SHARE of the files of each kind.

Samples: the arguments, else $HDLSTUDIO_SAMPLES (default D:/workspace): its fsm.sm, symbol.sb,
struct.bd and every .sm / .sb / .bd under its src/ folder. Run it again after changing the import / export code or the
notes; the page is committed with the code.
"""
from __future__ import annotations

import collections
import datetime
import glob
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from formats.sexpr import Atom, Document, Node, Ref, parse_file  # noqa: E402
import format_notes as notes  # noqa: E402

OUT = os.path.join(ROOT, 'docs', 'formats', 'sm-sb-bd-reference.html')
CODE_DIRS = ('src/formats/*.py', 'src/project/*.py', 'src/model.py', 'src/bd_model.py')
KINDS = ('sm', 'sb', 'bd')
MAX_EXAMPLES = 3
MAX_DISTINCT = 8                 # values listed with their counts when a key takes at most this many
MIN_FILES = 3                    # a quoted string must be in at least this many sample files ...
MIN_SHARE = 0.4                  # ... and in this share of the files of one kind, else it is masked
# keys whose strings are design content (names, libraries, ranges, expressions, values, comments):
# always masked, however common they are in the samples
DESIGN_KEYS = frozenset(
    'name n value val b lb rb ub eolc iv expr defVal rstVal f duLibraryName duName libraryName entityName '
    'viewName entityPath archName archPath fileName includeRefs cond varName caseExpr comment declText '
    'stateSignalName csName nsName signalSuffix clockSuffix e pr apr po apo prec preAdd posAdd'.split())
# texts (st) are not in DESIGN_KEYS: the captions and placeholders the legacy tool writes itself
# ("Pre Actions:", "< Automatic >") are common enough to pass MIN_SHARE, design texts are not
ELLIPSIS = '\u2026'
_PATH_RE = re.compile(r'(^|[\s"])(/[\w.-]+/|[A-Za-z]:[\\/])|@|\bDESKTOP-|`include|\w\.(v|vh|sv|svh|vhd)\b')
_STRING_FILES: dict[str, collections.Counter] = {}     # quoted string -> {kind: sample files it is in}
_FILES = collections.Counter()                          # kind -> sample files scanned


# -- samples --------------------------------------------------------------------------------
def sample_files(args: list[str]) -> list[str]:
    """The .sm / .sb files to scan: the arguments (files or folders), else the default samples."""
    roots = args or [os.environ.get('HDLSTUDIO_SAMPLES', 'D:/workspace')]
    files: list[str] = []
    for r in roots:
        if os.path.isfile(r):
            files.append(r)
            continue
        if not args:             # default: the sample root's own files and its src/ tree only
            files += [p for p in (os.path.join(r, n) for n in ('fsm.sm', 'symbol.sb', 'struct.bd')) if os.path.isfile(p)]
            r = os.path.join(r, 'src')
        for ext in KINDS:
            files += glob.glob(os.path.join(r, '**', '*.' + ext), recursive=True)
    return sorted(set(os.path.normpath(f) for f in files))


# -- values ---------------------------------------------------------------------------------
def value_kind(v, doc: Document) -> str:
    """Short name of the kind of a value: int, atom, string, &ref -> Type, (Type), [list]."""
    if isinstance(v, bool) or isinstance(v, int):
        return 'int'
    if isinstance(v, Atom):
        return 'atom'
    if isinstance(v, str):
        return 'string'
    if isinstance(v, Ref):
        target = doc.labels.get(v.label)
        return f'&ref \u2192 {target.type}' if target is not None else '&ref'
    if isinstance(v, Node):
        return f'({v.type})'
    if isinstance(v, list):
        inner = sorted({value_kind(x, doc) for x in v if not (isinstance(x, Atom) and x == '')})
        return '[' + ', '.join(inner[:4]) + (', ' + ELLIPSIS if len(inner) > 4 else '') + ']'
    return type(v).__name__


def masked(v: str, key: str | None) -> bool:
    """Whether a quoted string of the samples must not be shown: a path, the value of a design key,
    or a string not common enough to be something the legacy tool writes itself."""
    if not v:
        return False
    if _PATH_RE.search(v) or key in DESIGN_KEYS:
        return True
    seen = _STRING_FILES.get(v, collections.Counter())
    return sum(seen.values()) < MIN_FILES or max(seen[k] / _FILES[k] for k in seen) < MIN_SHARE


def short(v, limit: int = 70, key: str | None = None) -> str:
    """A scalar as written in the file, cut to `limit` characters; design strings and paths masked
    (`key` is the key the value belongs to)."""
    if isinstance(v, Ref):
        s = f'&{v.label}'
    elif isinstance(v, (int, Atom)):
        s = str(v)
    elif isinstance(v, str):
        if masked(v, key):
            return f'"{ELLIPSIS}"'
        s = '"' + v.replace('\n', '\\n') + '"'
    else:
        return ''
    return s if len(s) <= limit else s[:limit - 1] + ELLIPSIS


def raw(v):
    """A hashable form of a scalar value, for counting (None for objects and lists)."""
    if isinstance(v, Ref):
        return Atom(f'&{v.label}')
    if isinstance(v, (int, str)):
        return v
    return None


# -- inventory ------------------------------------------------------------------------------
class Inventory:
    """What the sample files contain, type by type and key by key."""

    def __init__(self):
        """Empty inventory."""
        self.files = {k: 0 for k in KINDS}
        self.top = {k: collections.Counter() for k in KINDS}
        self.count = collections.defaultdict(collections.Counter)        # type -> kind -> objects
        self.labelled = collections.Counter()                           # type -> objects with *N
        self.keys = collections.defaultdict(dict)                       # type -> key -> info
        self.parents = collections.defaultdict(collections.Counter)     # type -> "Parent.key"
        self.example = {}                                               # type -> (score, Node, kind)

    def add_file(self, path: str) -> None:
        """Scan one file."""
        kind = os.path.splitext(path)[1][1:]
        try:
            doc = parse_file(path)
        except Exception as e:                       # noqa: BLE001 - a bad sample is reported, not fatal
            print(f'skipped {path}: {e}')
            return
        self.files[kind] += 1
        _FILES[kind] += 1
        strings = {v for n in doc.walk() for _, v in n.fields if isinstance(v, str) and not isinstance(v, Atom)}
        for s in strings:
            _STRING_FILES.setdefault(s, collections.Counter())[kind] += 1
        for k, v in doc.fields:
            self.top[kind][k] += 1
            self._value(doc, kind, '(file)', k, v)

    def _value(self, doc: Document, kind: str, parent: str, key: str, v) -> None:
        """Record a value found under parent.key (and everything inside it)."""
        if isinstance(v, Node):
            self._node(doc, kind, parent, key, v)
        elif isinstance(v, list):
            for x in v:
                self._value(doc, kind, parent, key + '[]', x)

    def _node(self, doc: Document, kind: str, parent: str, key: str, n: Node) -> None:
        """Record one object, its keys and its children."""
        self.count[n.type][kind] += 1
        self.parents[n.type][f'{parent}.{key}'] += 1
        if n.label is not None:
            self.labelled[n.type] += 1
        info = self.keys[n.type]
        seen = set()
        for k, v in n.fields:
            ki = info.setdefault(k, {'n': 0, 'kinds': collections.Counter(), 'values': collections.Counter(),
                                     'in': set(), 'repeat': False})
            if k in seen:
                ki['repeat'] = True
            else:
                seen.add(k)
                ki['n'] += 1
                ki['in'].add(kind)
            ki['kinds'][value_kind(v, doc)] += 1
            r = raw(v)
            if r is not None and (r in ki['values'] or len(ki['values']) < 400):
                ki['values'][r] += 1
            self._value(doc, kind, n.type, k, v)
        score = (len(n.fields), -len(str(n.fields)) // 200)
        if n.type not in self.example or score > self.example[n.type][0]:
            self.example[n.type] = (score, n, kind)


def snippet(n: Node, max_lines: int = 45) -> str:
    """The text of an object as in the file (indented), nested objects cut after three levels."""
    lines: list[str] = []

    def put(head: str, v, d: int, key: str | None) -> None:
        """Append one value of field `key` after `head` at nesting depth d."""
        pad = '  ' * d
        if isinstance(v, Node):
            lab = f'*{v.label} ' if v.label is not None else ''
            if d >= 3 and v.fields:
                lines.append(f'{pad}{head}{lab}({v.type} {ELLIPSIS})')
                return
            lines.append(f'{pad}{head}{lab}({v.type}')
            for k, x in v.fields:
                put(f'{k} ', x, d + 1, k)
            lines.append(f'{pad})')
        elif isinstance(v, list):
            if not v:
                lines.append(f'{pad}{head}[ ]')
                return
            lines.append(f'{pad}{head}[')
            for x in v[:4]:
                put('', x, d + 1, key)
            if len(v) > 4:
                lines.append(f'{pad}  {ELLIPSIS} ({len(v) - 4} more)')
            lines.append(f'{pad}]')
        else:
            lines.append(f'{pad}{head}{short(v, 90, key)}')

    put('', n, 0, None)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + ['  ' + ELLIPSIS]
    return '\n'.join(lines)


# -- code references ------------------------------------------------------------------------
def code_index() -> dict[str, list[str]]:
    """'name' -> ['src/formats/import_sm.py:422', ...]: where a quoted name appears in the code."""
    idx: dict[str, list[str]] = collections.defaultdict(list)
    for pattern in CODE_DIRS:
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            with open(path, encoding='utf-8') as f:
                for no, line in enumerate(f, 1):
                    code = line.split('#', 1)[0]
                    for m in re.finditer(r'''(['"])([A-Za-z_][A-Za-z0-9_]*)\1''', code):
                        ref = f'{rel}:{no}'
                        if ref not in idx[m.group(2)]:
                            idx[m.group(2)].append(ref)
    return idx


# -- page -----------------------------------------------------------------------------------
def git_commit() -> str:
    """Short hash of HEAD, or '' outside git."""
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def _key_entry(k: str, ki: dict | None, total: int, note: str, common: bool, code: dict) -> dict:
    """One row of a type's key table."""
    entry = {'key': k, 'n': 0, 'pct': 0, 'in': [], 'repeat': False, 'kinds': [], 'values': [], 'examples': [],
             'note': note, 'common': common, 'code': code.get(k, [])[:12], 'ncode': len(code.get(k, []))}
    if ki is None:
        return entry
    values = collections.Counter()
    for v, c in ki['values'].items():
        values[short(v, key=k)] += c
    small = len(ki['values']) <= MAX_DISTINCT and ki['n'] > 1 and f'"{ELLIPSIS}"' not in values
    entry.update({
        'n': ki['n'], 'pct': round(100 * ki['n'] / total), 'in': sorted(ki['in']), 'repeat': ki['repeat'],
        'kinds': [k2 for k2, _ in ki['kinds'].most_common()],
        'values': [[v, c] for v, c in values.most_common(MAX_DISTINCT)] if small else [],
        'examples': [] if small else [v for v, _ in values.most_common(MAX_EXAMPLES)],
    })
    return entry


def build_data(inv: Inventory, code: dict[str, list[str]]) -> dict:
    """Everything the page shows, as JSON-able data."""
    types = []
    for t in sorted(inv.count, key=lambda t: (notes.category_index(t), t.lower())):
        note = notes.TYPES.get(t, {})
        own = note.get('keys', {})
        total = sum(inv.count[t].values())
        keys = [_key_entry(k, ki, total, own.get(k) or notes.COMMON_KEYS.get(k, ''),
                           k not in own and k in notes.COMMON_KEYS, code)
                for k, ki in inv.keys[t].items()]
        keys += [_key_entry(k, None, total, text, False, code) for k, text in own.items() if k not in inv.keys[t]]
        ex = inv.example.get(t)
        types.append({
            'type': t, 'cat': notes.category_of(t), 'note': note.get('desc', ''),
            'count': dict(inv.count[t]), 'labelled': inv.labelled.get(t, 0),
            'parents': [[p, c] for p, c in inv.parents[t].most_common(6)],
            'keys': keys, 'example': snippet(ex[1]) if ex else '', 'example_in': ex[2] if ex else '',
            'code': code.get(t, [])[:12], 'ncode': len(code.get(t, [])),
        })
    return {
        'generated': datetime.date.today().isoformat(), 'commit': git_commit(),
        'files': inv.files, 'top': {k: list(c) for k, c in inv.top.items()},
        'types': types, 'categories': dict(notes.CATEGORIES),
        'topics': [{'id': i, 'title': t, 'html': h} for i, t, h in notes.TOPICS],
        'changes': notes.CHANGES,
    }


def write_page(data: dict) -> None:
    """Write the HTML page with the data embedded."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'format_ref.html'), encoding='utf-8') as f:
        page = f.read()
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = page.replace('/*DATA*/null', blob).replace('{{TITLE}}', html.escape(notes.TITLE))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(page)


def main() -> int:
    """Scan the samples, merge the notes and write the page."""
    files = sample_files(sys.argv[1:])
    if not files:
        sys.exit('no .sm / .sb / .bd sample found (give folders or set HDLSTUDIO_SAMPLES)')
    inv = Inventory()
    for path in files:
        inv.add_file(path)
    data = build_data(inv, code_index())
    write_page(data)
    undocumented = [t['type'] for t in data['types'] if not t['note']]
    print(f'{os.path.relpath(OUT, ROOT)}: ' + ', '.join(f'{inv.files[k]} .{k}' for k in KINDS) + ', '
          f'{len(data["types"])} types, {sum(len(t["keys"]) for t in data["types"])} keys; '
          f'{len(undocumented)} types without a note')
    stale = sorted(set(notes.TYPES) - set(inv.count))
    if stale:
        print('notes for types not in the samples:', ', '.join(stale))
    return 0


if __name__ == '__main__':
    sys.exit(main())

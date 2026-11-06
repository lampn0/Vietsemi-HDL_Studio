"""Reader for the S-expression text format used by legacy graphics files
(.sm state machines, .bd block diagrams, .sb symbols).

Format summary:
    (TypeName key value key value ...)
values are strings, numbers, "a,b" pairs, [lists], nested objects,
`*N (obj)` labelled objects and `&N` references to them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

_TOKEN_RE = re.compile(
    r'''
    (?P<ws>\s+)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<label>\*\d+)
  | (?P<ref>&\d+)
  | (?P<lparen>\()
  | (?P<rparen>\))
  | (?P<lbrack>\[)
  | (?P<rbrack>\])
  | (?P<atom>[^\s()\[\]"]+)
    ''',
    re.VERBOSE | re.DOTALL,
)


class Atom(str):
    """An unquoted value of the file (e.g. `uid 2742,0`, `ps CenterOffsetStrategy`): a str, so
    readers use it as any text, kept apart from quoted strings so that write() puts it back
    exactly as it was."""


@dataclass
class Ref:
    """Reference `&N` to a labelled object."""
    label: int


@dataclass
class Node:
    """One `(TypeName key value ...)` object."""
    type: str
    fields: list[tuple[str, Any]] = field(default_factory=list)
    label: int | None = None

    def get(self, key: str, default: Any = None) -> Any:
        """Value of the first field called `key` (fields may repeat), or `default`."""
        for k, v in self.fields:
            if k == key:
                return v
        return default

    def get_all(self, key: str) -> list[Any]:
        """Values of every field called `key`, in file order."""
        return [v for k, v in self.fields if k == key]

    def __repr__(self) -> str:
        """Short form for debugging: label, type and number of fields."""
        lab = f"*{self.label} " if self.label is not None else ""
        return f"{lab}({self.type} …{len(self.fields)} fields)"


@dataclass
class Document:
    """A parsed file: top-level key/value pairs plus the label table."""
    fields: list[tuple[str, Any]]
    labels: dict[int, Node]
    newline: str = '\n'          # line ending of the file read ('\r\n' for files saved on Windows)

    def get(self, key: str, default: Any = None) -> Any:
        """Value of the first top-level field called `key`, or `default`."""
        for k, v in self.fields:
            if k == key:
                return v
        return default

    def resolve(self, value: Any) -> Any:
        """Follow a Ref to the labelled object it points to; any other value is returned unchanged."""
        if isinstance(value, Ref):
            return self.labels.get(value.label)
        return value

    def walk(self) -> Iterator[Node]:
        """Yield every Node in document order (depth first)."""
        stack: list[Any] = [v for _, v in reversed(self.fields)]
        while stack:
            v = stack.pop()
            if isinstance(v, Node):
                yield v
                stack.extend(val for _, val in reversed(v.fields))
            elif isinstance(v, list):
                stack.extend(reversed(v))


class ParseError(ValueError):
    """The text is not a valid the legacy tool S-expression file."""
    pass


def _unescape(s: str) -> str:
    """Content of a quoted token: quotes removed, backslash escapes resolved."""
    return re.sub(r'\\(.)', r'\1', s[1:-1])


def _convert_atom(text: str) -> Any:
    """An unquoted token: int when it is a plain decimal integer written canonically (so writing it
    back gives the same text), otherwise an Atom.
    """
    if re.fullmatch(r'-?\d+', text) and str(int(text)) == text:
        return int(text)
    return Atom(text)


BLANK = Atom('')     # an empty line inside a list (the legacy tool writes some); written back as one


class _Parser:
    """Recursive-descent parser over the token list of one file. Labelled objects (`*N (...)`) are
    collected in `labels` so references (`&N`) can be resolved afterwards.
    """
    def __init__(self, text: str):
        """Tokenize `text` (line endings already normalized to \\n)."""
        # whitespace is dropped, except an empty line, which is kept as a 'blank' token
        self.tokens = [('blank', '') if m.lastgroup == 'ws' else (m.lastgroup, m.group())
                       for m in _TOKEN_RE.finditer(text)
                       if m.lastgroup != 'ws' or re.search(r'\n[ \t]*\n', m.group())]
        self.pos = 0
        self.labels: dict[int, Node] = {}

    def peek(self) -> tuple[str, str] | None:
        """The next token (kind, text) without consuming it; None at the end."""
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> tuple[str, str]:
        """Consume and return the next token; ParseError at the end of the text."""
        tok = self.peek()
        if tok is None:
            raise ParseError("unexpected end of file")
        self.pos += 1
        return tok

    def _skip_blanks(self):
        """Skip empty-line tokens (they matter only inside lists)."""
        while self.peek() and self.peek()[0] == 'blank':
            self.pos += 1

    def parse_value(self) -> Any:
        """One value: string, number / atom, reference, labelled object, object or list."""
        self._skip_blanks()
        kind, text = self.next()
        if kind == 'str':
            return _unescape(text)
        if kind == 'atom':
            return _convert_atom(text)
        if kind == 'ref':
            return Ref(int(text[1:]))
        if kind == 'label':
            node = self.parse_value()
            if not isinstance(node, Node):
                raise ParseError(f"label {text} not followed by an object")
            node.label = int(text[1:])
            self.labels[node.label] = node
            return node
        if kind == 'lparen':
            return self.parse_node()
        if kind == 'lbrack':
            items = []
            while self.peek() and self.peek()[0] != 'rbrack':
                if self.peek()[0] == 'blank':
                    self.next()
                    items.append(BLANK)
                    continue
                items.append(self.parse_value())
            self.next()
            return items
        raise ParseError(f"unexpected token {text!r} at token {self.pos}")

    def parse_node(self) -> Node:
        """One object, after its '(': the type name, then key / value pairs up to ')'."""
        kind, text = self.next()
        if kind != 'atom':
            raise ParseError(f"expected type name, got {text!r}")
        node = Node(text)
        while True:
            self._skip_blanks()
            tok = self.peek()
            if tok is None:
                raise ParseError(f"unterminated ({node.type}")
            if tok[0] == 'rparen':
                self.next()
                return node
            kind, key = self.next()
            if kind != 'atom':
                raise ParseError(f"expected key in ({node.type}, got {key!r}")
            node.fields.append((key, self.parse_value()))

    def parse_document(self) -> Document:
        """The whole file: top-level key / value pairs until the end of the text."""
        fields = []
        while True:
            self._skip_blanks()
            if not self.peek():
                break
            kind, key = self.next()
            if kind != 'atom':
                raise ParseError(f"expected top-level key, got {key!r}")
            fields.append((key, self.parse_value()))
        return Document(fields, self.labels)


def parse(text: str) -> Document:
    """Parse the text of a legacy file. The line ending used by the file is remembered in the
    document so write() can reproduce it.
    """
    newline = '\r\n' if '\r\n' in text else '\n'
    doc = _Parser(text.replace('\r\n', '\n')).parse_document()
    doc.newline = newline
    return doc


def parse_file(path: str) -> Document:
    """Read and parse a legacy file (.sm, .bd, .sb, ...)."""
    with open(path, encoding='utf-8', errors='replace', newline='') as f:     # keep the line endings
        return parse(f.read())


# -- writing --------------------------------------------------------------------------------
def _fmt(v: Any) -> str:
    """A scalar as the file writes it: ints and Atoms bare, references &N, other text quoted
    (backslash and double quote escaped)."""
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    if isinstance(v, Atom):
        return str(v)
    if isinstance(v, Ref):
        return f'&{v.label}'
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    raise TypeError(f'cannot write {v!r}')


def _write_value(out: list[str], head: str, v: Any) -> None:
    """Write one value after `head` ("key " for a field, "" for a list item), in the layout
    of legacy files: an object opens on the head line and closes on its own line, a list too,
    one item / field per line."""
    if isinstance(v, Node):
        lab = f'*{v.label} ' if v.label is not None else ''
        out.append(f'{head}{lab}({v.type}')
        for k, x in v.fields:
            _write_value(out, f'{k} ', x)
        out.append(')')
    elif isinstance(v, list):
        out.append(f'{head}[')
        for x in v:
            _write_value(out, '', x)
        out.append(']')
    else:
        out.append(f'{head}{_fmt(v)}')


def write(doc: Document) -> str:
    """The text of a document, in the legacy file layout (a file read and written back unchanged
    is byte for byte the same)."""
    out: list[str] = []
    for k, v in doc.fields:
        _write_value(out, f'{k} ', v)
    text = '\n'.join(out) + '\n'
    return text.replace('\n', doc.newline) if doc.newline != '\n' else text


def write_file(doc: Document, path: str) -> None:
    """Write a document to `path` with write() (same line endings as the file it came from)."""
    with open(path, 'w', encoding='utf-8', newline='') as f:      # write() chose the line endings
        f.write(write(doc))

"""Keep a unit's legacy symbol (symbol.sb) in step with the ports of its state diagram, as the legacy tool does
when it saves a diagram whose ports changed.

    sync_symbol_ports(symbol_path, signals) -> list of changes made ([] = nothing to do)

`signals` is the diagram's Signals Table (model.Signal); its inputs, outputs and inouts
are the ports. The symbol is changed in place, only where its ports differ:

  * the interface table: one LogPort per port (port (LogicalPort lang m decl (Decl n t b o
    suid))) in the table's logical list, one row (MRCItem litem &N pos P) in its sheet;
  * the drawn ports (CptPort) on the symbol body: inputs on the left edge, outputs and inouts
    on the right, one every 1000 units from 1000 under the top; a new port goes 1000 under
    the last one on its side (the body grows when it reaches the bottom). Each has its name
    text (CPTG f: "name" or "name : [7:0]"), its declaration text (dt: "input  wire  name;")
    and a copy of the LogicalPort (thePort);
  * the port order (Decl o): inputs, then outputs, then inouts, each by name, as legacy numbers
    them; the declaration texts are listed in that order (y = 3200 + 800 * o).

Read from what the legacy tool itself wrote into symbol.sb after two ports were added to
uart_tx's state diagram. The legacy tool lays the texts out again when it opens the
symbol, so their extents here are estimates. Everything else in the file is left as it was.
"""
from __future__ import annotations

import copy
from typing import Any

from .sexpr import Atom, Node, Ref, parse_file, write_file

_MODE_CODE = {'input': None, 'output': 1, 'inout': 2}
_RANK = {'input': 0, 'output': 1, 'inout': 2}
PITCH = 1000                 # between two ports on an edge
NAME_CHAR, DECL_CHAR = 380, 550          # estimated width of a character: Arial 8, Courier New 8


def _set(node: Node, key: str, value: Any, after: tuple[str, ...] = ()) -> None:
    """Set field `key` of `node` to `value`; a new field goes right after the last of the keys in
    `after` (legacy files keep a fixed field order), or at the end.
    """
    for i, (k, _) in enumerate(node.fields):
        if k == key:
            node.fields[i] = (k, value)
            return
    hits = [i for i, (k, _) in enumerate(node.fields) if k in after]
    node.fields.insert(hits[-1] + 1 if hits else len(node.fields), (key, value))


def _drop(node: Node, key: str) -> None:
    """Remove every field called `key` from `node`."""
    node.fields[:] = [(k, v) for k, v in node.fields if k != key]


def _nums(s: str) -> list[int]:
    """"x0,y0,x1,y1" -> list of ints (values rounded)."""
    return [int(round(float(v))) for v in s.split(',')]


def _join(vals) -> str:
    """List of numbers -> "a,b,c" as the legacy tool writes coordinates (rounded ints)."""
    return ','.join(str(int(round(v))) for v in vals)


def _walk(v: Any):
    """Yield every Node inside `v`, depth first in file order."""
    stack = [v]
    while stack:
        x = stack.pop()
        if isinstance(x, list):
            stack.extend(reversed(x))
        elif isinstance(x, Node):
            yield x
            stack.extend(y for _, y in reversed(x.fields))


def _decl_of(n: Node) -> Node | None:
    """The Decl (n t b o ...) of a table LogPort or of a drawn CptPort."""
    p = n.get('port') if n.type == 'LogPort' else n.get('thePort')
    return p.get('decl') if isinstance(p, Node) else None


def _write_decl(port: Node, s, order: int, suid: Atom | None) -> None:
    """LogicalPort (lang m decl) and its Decl, written whole in the legacy tool's field order
    (n t b s eolc o suid): a port drawn from a copy of another must not keep that one's
    comment or sign (the legacy tool's integrity check wants the drawn port's declaration and the table's
    to be the same)."""
    code = _MODE_CODE.get(s.mode)
    if code is None:
        _drop(port, 'm')
    else:
        _set(port, 'm', code, after=('lang',))
    decl = port.get('decl')
    fields = [('n', s.name), ('t', s.type or 'wire')]
    if s.bounds:
        fields.append(('b', s.bounds))
    if s.signed:
        fields.append(('s', 1))
    if s.comment.strip():
        fields.append(('eolc', s.comment.strip()))
    fields.append(('o', order))
    if suid is not None:
        fields.append(('suid', suid))
    known = {'n', 't', 'b', 's', 'eolc', 'o', 'suid'}
    decl.fields[:] = fields + [(k, v) for k, v in decl.fields if k not in known]


def _name_text(s) -> str:
    """Port label drawn on the symbol: "name" or "name : [7:0]"."""
    return f'{s.name} : {s.bounds}' if s.bounds else s.name


def _decl_text(s) -> str:
    """Declaration text of a port, as the symbol shows it ("input  wire       name;")."""
    kind = f'{s.type or "wire"} {s.bounds}'.strip()
    return f'{s.mode:<7}{kind:<12}{s.name};\n' if len(kind) < 12 else f'{s.mode:<7}{kind} {s.name};\n'


def sync_symbol_ports(path: str, signals: list) -> list[str]:
    """Bring the ports of the symbol file `path` in line with the ports of `signals` (the
    diagram's Signals Table) and write the file. Returns the list of changes, [] when the symbol
    already matches (the file is then not written at all).

    Order of work: find the interface table and the symbol body; compare names, modes, types,
    bounds and order; remove ports that are gone (with their table rows and cell attributes);
    add a LogPort + table row for each new port; draw each new port (a copy of a port on the same
    side) under the last one; rewrite every declaration and its texts in the legacy tool's port order.
    """
    doc = parse_file(path)
    model = doc.get('model')
    ports = [s for s in signals if s.mode in _MODE_CODE]
    want = {s.name: s for s in ports}
    # the port order the legacy tool gives: inputs, outputs, inouts, each by name (Decl o from 1)
    order = {s.name: i + 1 for i, s in enumerate(sorted(ports, key=lambda s: (_RANK[s.mode], s.name)))}

    # the interface table (its logical list holds the LogPorts) and the drawn ports
    table = None
    for n in _walk(model):
        ldm, pdm = n.get('ldm'), n.get('pdm')
        items = ldm.get('optionalChildren') if isinstance(ldm, Node) else None
        if isinstance(items, list) and isinstance(pdm, Node) and any(
                x.type == 'LogPort' for x in _walk(items)):
            sheet = next((x for x in pdm.get('optionalChildren') or [] if isinstance(x, Node) and x.type == 'Sheet'),
                         None)
            table = (items, sheet.get('sheetRow') if sheet is not None else None)
            break
    body = next((n for n in _walk(model.get('optionalChildren')) if n.type == 'SymbolBody'), None)
    if table is None or body is None:
        return []
    items, sheet_row = table
    # every port of the table, also those inside groups (LGroup optionalChildren), with the
    # list that holds it
    log_ports, holder = {}, {}
    stack = [items]
    while stack:
        lst = stack.pop()
        for x in lst:
            if isinstance(x, Node) and x.type == 'LogPort':
                log_ports.setdefault(_decl_of(x).get('n'), x)
                holder[id(x)] = lst
            elif isinstance(x, Node) and x.type == 'LGroup' and isinstance(x.get('optionalChildren'), list):
                stack.append(x.get('optionalChildren'))
    cpt_list = body.get('optionalChildren')
    cpts = {_decl_of(x).get('n'): x for x in cpt_list or [] if isinstance(x, Node) and x.type == 'CptPort'}

    def same(name) -> bool:
        """True when port `name` is already on the symbol exactly as wanted (table entry, drawn port,
        mode, type and bounds).
        """
        lp, s = log_ports.get(name), want[name]
        d = _decl_of(lp) if lp is not None else None
        p = lp.get('port') if lp is not None else None
        return (d is not None and name in cpts and p.get('m') == _MODE_CODE.get(s.mode)
                and (d.get('t') or 'wire') == (s.type or 'wire') and (d.get('b') or '') == s.bounds)
    if set(log_ports) == set(want) and all(same(n) for n in want) and \
            all(_decl_of(log_ports[n]).get('o') == order[n] for n in want):
        return []

    changes = []
    # uids, labels and suids for new objects: after the largest in use (lastUid kept up to date)
    uid = max([int(str(n.get('uid')).split(',')[0]) for n in _walk(model) if isinstance(n.get('uid'), str)
               and str(n.get('uid')).split(',')[0].isdigit()] + [int(str(model.get('lastUid') or '0').split(',')[0])])
    label = max(doc.labels or [0])
    suid = max([int(str(d.get('suid')).split(',')[0]) for x in (*log_ports.values(), *cpts.values())
                for d in [_decl_of(x)] if d is not None and d.get('suid')] or [0])

    def new_uid() -> Atom:
        """Next free uid ("N,0"); lastUid is updated at the end."""
        nonlocal uid
        uid += 1
        return Atom(f'{uid},0')

    def new_label(n: Node) -> None:
        """Give node `n` the next free *N label and register it in the document."""
        nonlocal label
        label += 1
        n.label = label
        doc.labels[label] = n

    def give_uids(n: Node) -> None:
        """New uids, and new labels (*N: the legacy tool refuses a file with one twice), for a copied
        object and its parts that have one."""
        for x in _walk(n):
            if x.get('uid') is not None:
                _set(x, 'uid', new_uid())
            if x.label is not None:
                new_label(x)

    rows = sheet_row.get('optionalChildren') if isinstance(sheet_row, Node) else None
    row_of = {r.get('litem').label: r for r in rows or [] if isinstance(r, Node) and isinstance(r.get('litem'), Ref)}

    # removed ports (and a port whose mode changed: drawn again on its side)
    removed: set[int] = set()
    for name, lp in list(log_ports.items()):
        s = want.get(name)
        moved = s is not None and lp.get('port').get('m') != _MODE_CODE.get(s.mode)
        if s is None or moved:
            removed.add(lp.label)
            if lp.label in row_of and row_of[lp.label].label is not None:
                removed.add(row_of[lp.label].label)
            if name in cpts:
                cpt_list.remove(cpts.pop(name))
            holder.get(id(lp), items).remove(lp)
            del log_ports[name]
            changes.append(f'symbol: port {name} {"moved" if moved else "removed"}')
    if rows is not None:
        gone = sorted(row_of[lab].get('pos') for lab in list(row_of) if lab in removed
                      and isinstance(row_of[lab].get('pos'), int))
        rows[:] = [r for r in rows if not (isinstance(r, Node) and r.label in removed)]
        for r in rows:
            if isinstance(r, Node) and isinstance(r.get('pos'), int):
                _set(r, 'pos', r.get('pos') - sum(1 for g in gone if g < r.get('pos')))
    for lab in removed:
        doc.labels.pop(lab, None)
    if removed:
        # the cell attributes (PVME row &N col &M) of the removed ports' rows go with them
        stack: list[Any] = [v for _, v in doc.fields]
        while stack:
            v = stack.pop()
            if isinstance(v, list):
                v[:] = [x for x in v if not (isinstance(x, Node) and x.type in ('PVME', 'MRCItem') and any(
                    isinstance(r, Ref) and r.label in removed for k, r in x.fields if k in ('litem', 'row', 'col')))]
                stack.extend(v)
            elif isinstance(v, Node):
                stack.extend(x for _, x in v.fields)

    # the body and where the next port goes on each side
    shape = body.get('shape')
    bx0, by0, bx1, by1 = _nums(shape.get('xt'))
    last_y = {'left': by0, 'right': by0}
    for c in cpts.values():
        x0, y0, x1, y1 = _nums(c.get('shape').get('xt'))
        side = 'left' if x1 <= bx0 + 1 else 'right'
        last_y[side] = max(last_y[side], (y0 + y1) // 2)
    templates = {}
    for c in cpts.values():
        side = 'left' if _nums(c.get('shape').get('xt'))[2] <= bx0 + 1 else 'right'
        templates.setdefault(side, c)

    fresh: set[str] = set()                   # ports drawn now: their texts are laid out anew
    for s in ports:
        side = 'left' if s.mode == 'input' else 'right'
        lp = log_ports.get(s.name)
        if lp is None:
            # interface table: a LogPort after the last one, and its row before the empty row
            suid += 1
            sid = Atom(f'{suid},0')
            lp = Node('LogPort', [('port', Node('LogicalPort', [('lang', _lang(log_ports, cpts)),
                                                                 ('decl', Node('Decl', []))])),
                                  ('uid', new_uid())])
            _write_decl(lp.get('port'), s, order[s.name], sid)
            new_label(lp)
            last = max((i for i, x in enumerate(items) if isinstance(x, Node) and x.type == 'LogPort'), default=-1)
            items.insert(last + 1, lp)
            log_ports[s.name] = lp
            if rows is not None:
                empty = sheet_row.get('emptyMRCItem')
                pos = empty.get('pos') if isinstance(empty, Node) and isinstance(empty.get('pos'), int) else len(rows)
                row = Node('MRCItem', [('litem', Ref(lp.label)), ('pos', pos), ('dimension', 20), ('uid', new_uid())])
                new_label(row)
                rows.append(row)
                if isinstance(empty, Node):
                    _set(empty, 'pos', pos + 1)
            changes.append(f'symbol: port {s.name} added')
        else:
            d = _decl_of(lp)
            _write_decl(lp.get('port'), s, order[s.name], d.get('suid'))
        sid = _decl_of(lp).get('suid')
        c = cpts.get(s.name)
        if c is None:
            # a drawn port: a copy of one on the same side (else the symbol's default port),
            # 1000 under the last port there
            tpl = templates.get(side) or model.get('defaultCptPort')
            c = copy.deepcopy(tpl)
            give_uids(c)
            if not c.get('uid'):
                c.fields.insert(0, ('uid', new_uid()))
            y = last_y[side] + PITCH
            last_y[side] = y
            if y > by1 - PITCH:
                by1 = y + PITCH
                _set(shape, 'xt', _join([bx0, by0, bx1, by1]))
            _place(c, side, bx0, bx1, y)
            cpt_list.append(c)
            cpts[s.name] = c
            fresh.add(s.name)
        the = c.get('thePort')
        if not isinstance(the, Node):
            the = Node('LogicalPort', [('lang', _lang(log_ports, cpts)), ('decl', Node('Decl', []))])
            _set(c, 'thePort', the)
        _write_decl(the, s, order[s.name], sid)
        _port_texts(c, s, side, order[s.name], s.name in fresh)
    if isinstance(model.get('lastUid'), str):
        _set(model, 'lastUid', Atom(f'{uid},0'))
    write_file(doc, path)
    return changes or ['symbol: port declarations / order']


def _lang(log_ports: dict, cpts: dict):
    """The `lang` code used by the existing ports (5 = Verilog when there is none)."""
    for x in (*log_ports.values(), *cpts.values()):
        p = x.get('port') if x.type == 'LogPort' else x.get('thePort')
        if isinstance(p, Node) and p.get('lang') is not None:
            return p.get('lang')
    return 5


def _place(c: Node, side: str, bx0: int, bx1: int, y: int) -> None:
    """The port's triangle on the body edge at height y (outside the body: left of its left
    edge, right of its right edge), its name text next to it inside the body."""
    tri = c.get('shape')
    _set(tri, 'ro', 90)
    if side == 'left':
        _set(tri, 'xt', _join([bx0 - 750, y - 375, bx0, y + 375]))
    else:
        _set(tri, 'xt', _join([bx1, y - 375, bx1 + 750, y + 375]))
    tg = c.get('tg')
    if isinstance(tg, Node):
        _set(tg, 'stg', 'VerticalLayoutStrategy' if side == 'left' else 'RightVerticalLayoutStrategy',
             after=('uid', 'ps'))


def _port_texts(c: Node, s, side: str, order: int, fresh: bool) -> None:
    """Name text (Arial 8; left: from 1000 inside the left edge; right: ending 1000 inside the
    right edge, justified right) and declaration text (Courier New 8, at y = 3200 + 800 * o).
    A port already drawn keeps its texts' extents while their strings are the same; only its
    declaration text moves to its place in the port order."""
    tri = _nums(c.get('shape').get('xt'))
    y = (tri[1] + tri[3]) // 2
    tg = c.get('tg')
    f = tg.get('f') if isinstance(tg, Node) else None
    dt = c.get('dt')
    if (not fresh and isinstance(dt, Node) and isinstance(f, Node) and f.get('st') == _name_text(s)
            and dt.get('st') == _decl_text(s) and isinstance(dt.get('xt'), str)):
        x0, y0, x1, y1 = _nums(dt.get('xt'))
        _set(dt, 'xt', _join([x0, 3200 + 800 * order, x1, 3200 + 800 * order + (y1 - y0)]))
        return
    if isinstance(f, Node):
        text = _name_text(s)
        w = NAME_CHAR * len(text)
        _set(f, 'st', text, after=('xt',))
        if side == 'left':
            x0 = tri[2] + PITCH
            _set(f, 'xt', _join([x0, y - 500, x0 + w, y + 500]))
            _drop(f, 'ju')
            _set(f, 'blo', _join([x0, y + 300]), after=('st',))
        else:
            x1 = tri[0] - PITCH
            _set(f, 'xt', _join([x1 - w, y - 500, x1, y + 500]))
            _set(f, 'ju', 2, after=('st',))
            _set(f, 'blo', _join([x1, y + 300]), after=('st', 'ju'))
    text = _decl_text(s)
    if not isinstance(dt, Node):
        dt = Node('MLText', [('va', Node('VaSet', [('font', 'Courier New,8,0')])), ('xt', '0,0,0,0')])
        _set(c, 'dt', dt, after=('tg',))
    y0 = 3200 + 800 * order
    _set(dt, 'xt', _join([2000, y0, 2000 + DECL_CHAR * len(text.strip()), y0 + 800]))
    _set(dt, 'st', text, after=('xt',))

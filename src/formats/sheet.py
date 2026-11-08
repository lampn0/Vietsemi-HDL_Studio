"""The layout of the Signals Table and Parameters Table pages stored in a legacy .sm / .bd file.

Each table is a `Sheet` object of the file's PhysicalDM:

    sheetRow (SheetRow  headerVa / cellVa / groupVa (MVa ...)      colours and font of header,
                        optionalChildren [MRCItem litem &N pos P dimension H [hidden 1]] ...)
                                                                    cells and group rows; one
                                                                    item per row: its display
                                                                    position and height
    sheetCol (SheetCol  optionalChildren [MRCItem litem &C pos P dimension W ...])
                                                                    one item per column: its
                                                                    position and width (pixels)
    fixedCol N, fixedRow M                                          frozen columns (the row
                                                                    number column counts) and
                                                                    header rows
    vaOverrides [(PVME row &R col &C va (MVa alignment 0 cellColor .. fontColor .. font ..))]
                                                                    the format of single cells

The row items point at the table's entries (LeafLogPort: a signal, LogGeneric: a parameter,
RefLabelRowHdr: the column letters, TitleRowHdr: the column names, FilterRowHdr, LGroup), the
column items at column headers whose manager (`tm "SmNameColHdrMgr"` ...) says what they show.

read_sheets(doc) gives two plain dicts (kept in the view as JSON, see SHEET_KEYS):

    columns     [[attr, width], ...] in display order ('#ref' is the row number column)
    fixed_col   frozen columns, the row number column included
    fixed_row   frozen rows (the two header rows)
    heights     {'#letters': h, '#title': h, '#row': h of the entries}
    order       entry names (signal / parameter) in display order
    va          {'header' | 'cell' | 'group': format}       the sheet's defaults
    cells       {'<entry name or #title>|<attr>': format}   single cells
    format      {'align': 'left' | 'center' | 'right', 'bg': '#rrggbb', 'fg': '#rrggbb',
                 'size': n, 'bold': bool}
"""
from __future__ import annotations

from typing import Any

from .sexpr import Document, Node, Ref

# column header manager -> the attribute of the row the column shows
_COLUMN_ATTR = {
    'RefLabelColHdrMgr': '#ref', 'RowExpandColHdrMgr': '#expand', 'GroupColHdrMgr': 'group',
    'SmNameColHdrMgr': 'name', 'SmModeColHdrMgr': 'mode', 'SmTypeColHdrMgr': 'type',
    'SmSignedColHdrMgr': 'signed', 'SmBoundsColHdrMgr': 'bounds', 'SmDelayColHdrMgr': 'delay',
    'SmInitColHdrMgr': 'value', 'SmCategoryColHdrMgr': 'category', 'SmAssignColHdrMgr': 'assign',
    'SmExprColHdrMgr': 'expression', 'SmSchemeColHdrMgr': 'scheme', 'SmDefValColHdrMgr': 'default',
    'SmRstValColHdrMgr': 'reset', 'SmEolColHdrMgr': 'comment',
    'BlockDiagramNameColHdrMgr': 'name', 'BlockDiagramModeColHdrMgr': 'mode',
    'BlockDiagramTypeColHdrMgr': 'type', 'BlockDiagramSignedColHdrMgr': 'signed',
    'BlockDiagramBoundsColHdrMgr': 'bounds', 'BlockDiagramDelayColHdrMgr': 'delay',
    'BlockDiagramInitColHdrMgr': 'value', 'BlockDiagramEolColHdrMgr': 'comment',
    'GenericNameColHdrMgr': 'name', 'GenericValueColHdrMgr': 'value', 'GenericTypeColHdrMgr': 'type',
    'GenericPragmaColHdrMgr': 'pragma', 'GenericEolColHdrMgr': 'comment',
}
_ROW_KEY = {'RefLabelRowHdr': '#letters', 'TitleRowHdr': '#title', 'FilterRowHdr': '#filter'}
SHEET_KEYS = ('columns', 'fixed_col', 'fixed_row', 'heights', 'order', 'va', 'cells')


def colour(text: Any) -> str | None:
    """'r,g,b' in 16-bit values (the file's colours) as '#rrggbb'."""
    try:
        r, g, b = (int(v) >> 8 for v in str(text).split(','))    # as the legacy tool shows them
    except ValueError:
        return None
    return f'#{r:02x}{g:02x}{b:02x}'


def _format(va: Node | None) -> dict:
    """A cell format (MVa): alignment, colours, font size and weight."""
    if not isinstance(va, Node):
        return {}
    out: dict[str, Any] = {}
    if va.get('alignment') is not None:
        out['align'] = {0: 'left', 1: 'center', 2: 'right'}.get(va.get('alignment'), 'center')
    for key, name in (('cellColor', 'bg'), ('fontColor', 'fg')):
        c = colour(va.get(key))
        if c:
            out[name] = c
    font = str(va.get('font') or '')
    if font:
        parts = font.split(',')
        if len(parts) > 1 and parts[1].strip().isdigit():
            out['size'] = int(parts[1])
        out['bold'] = len(parts) > 2 and parts[2].strip() == '1'
    return out


def _entry_name(n: Node) -> str | None:
    """The name a row item stands for: a signal, a parameter, a header row or a group."""
    if n.type in _ROW_KEY:
        return _ROW_KEY[n.type]
    if n.type == 'LeafLogPort':
        decl = n.get('port').get('decl') if isinstance(n.get('port'), Node) else None
        return decl.get('n') if isinstance(decl, Node) else None
    if n.type == 'LogGeneric':
        g = n.get('generic')
        return g.get('name') if isinstance(g, Node) else None
    if n.type == 'LGroup':
        return '#group:' + str(n.get('name') or '')
    return None


def _sheet(doc: Document, sheet: Node) -> tuple[str, dict]:
    """('signals' | 'parameters', layout) of one Sheet."""
    def node(v):
        return doc.resolve(v) if isinstance(v, Ref) else v
    columns, col_attr, kind = [], {}, 'signals'
    col = sheet.get('sheetCol')
    for item in (col.get('optionalChildren') or []) if isinstance(col, Node) else []:
        hdr = node(item.get('litem'))
        attr = _COLUMN_ATTR.get(str(hdr.get('tm'))) if isinstance(hdr, Node) else None
        if attr is None:
            continue
        if str(hdr.get('tm')).startswith('Generic'):
            kind = 'parameters'
        col_attr[hdr.label] = attr
        if not item.get('hidden'):
            columns.append((item.get('pos') or 0, attr, item.get('dimension') or 60))
    columns.sort()
    row = sheet.get('sheetRow')
    heights: dict[str, int] = {}
    entries = []
    row_name: dict[int, str] = {}
    for item in (row.get('optionalChildren') or []) if isinstance(row, Node) else []:
        n = node(item.get('litem'))
        name = _entry_name(n) if isinstance(n, Node) else None
        if name is None:
            continue
        row_name[n.label] = name
        if name.startswith('#') and not name.startswith('#group:'):
            heights[name] = 0 if item.get('hidden') else (item.get('dimension') or 20)
        else:
            entries.append((item.get('pos') or 0, name))
            heights.setdefault('#row', item.get('dimension') or 20)
    va = {}
    for key, name in (('headerVa', 'header'), ('cellVa', 'cell'), ('groupVa', 'group')):
        f = _format(row.get(key)) if isinstance(row, Node) else {}
        if f:
            va[name] = f
    cells = {}
    for pv in sheet.get('vaOverrides') or []:
        if not isinstance(pv, Node):
            continue
        r, c = pv.get('row'), pv.get('col')
        name = row_name.get(r.label) if isinstance(r, Ref) else None
        attr = col_attr.get(c.label) if isinstance(c, Ref) else None
        if name and attr:
            cells[f'{name}|{attr}'] = _format(pv.get('va'))
    return kind, {
        'columns': [[attr, width] for _, attr, width in columns],
        'fixed_col': sheet.get('fixedCol') or 1, 'fixed_row': sheet.get('fixedRow') or 2,
        'heights': heights, 'order': [name for _, name in sorted(entries)],
        'va': va, 'cells': cells,
    }


def read_sheets(doc: Document) -> tuple[dict, dict]:
    """(signals sheet, parameters sheet) of a parsed .sm / .bd; {} for a table the file has not."""
    out = {'signals': {}, 'parameters': {}}
    for n in doc.walk():
        if n.type == 'Sheet':
            kind, layout = _sheet(doc, n)
            if not out[kind]:
                out[kind] = layout
    return out['signals'], out['parameters']

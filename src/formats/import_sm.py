"""Import a legacy state machine view (.sm) into an FsmView.

The .sm file is an S-expression document (formats.sexpr). What is read:
  - the module: language, ports / signals (LeafLogPort), parameters (LogGeneric), the
    directive and declaration texts, the affixes of clocked / registered outputs;
  - each concurrent machine (ConcurrentSM): states (with action box geometry), hierarchical
    states (CompositeState) with entry / exit points, junctions, links, reset / clock /
    interrupt / recovery / enable points, transitions with condition, actions, priority and
    drawing (bend points, attach angles, condition box, priority circle);
  - the place of the declaration blocks and the visible area, so the diagram opens as the legacy tool
    shows it.
Every legacy coordinate is multiplied by SCALE to get scene units. Geometry the legacy tool saved is kept in
the `orig` dicts of the model so the editor can draw objects exactly where the legacy tool drew them, and
export_sm can write the file back without moving anything that was not edited.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Iterator

from model import (CATEGORY_CODES, set_category_label, FsmView, Junction, Link, Machine, Parameter, Point, Signal,
                     State, Transition)
from .sexpr import Document, Node, Ref, parse_file
from .names import META_DIR

# legacy coordinates are ~75 units per screen pixel at 100% zoom.
SCALE = 1.0 / 75.0

_MODE = {None: 'input', 1: 'output', 2: 'inout', 4: 'local'}
_SCHEME = {0: 'comb', 1: 'clocked', 2: 'registered'}
_POINT = {'SmResetPoint': 'reset', 'SmClockPoint': 'clock', 'InterruptPoint': 'interrupt',
          'SmRecoveryStatePoint': 'recovery', 'SmEnablePoint': 'enable'}


def _walk(value: Any) -> Iterator[Node]:
    """Yield every Node inside `value` (a node, a list or a scalar), depth first in file order."""
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, Node):
            yield v
            stack.extend(val for _, val in reversed(v.fields))
        elif isinstance(v, list):
            stack.extend(reversed(v))


def _text(node: Any) -> str:
    """First `st` string found in a node subtree."""
    for n in _walk(node):
        st = n.get('st')
        if isinstance(st, str):
            return st
    return ''


def _center(node: Any) -> tuple[float, float]:
    """Centre (scene units) of the first extent "xt" found in a node's shape; (0, 0) if none."""
    for n in _walk(node.get('shape') if isinstance(node, Node) else None):
        xt = n.get('xt')
        if isinstance(xt, str) and xt.count(',') == 3:
            x1, y1, x2, y2 = (float(v) for v in xt.split(','))
            return (x1 + x2) / 2 * SCALE, (y1 + y2) / 2 * SCALE
    return 0.0, 0.0


def _top_left(node: Node) -> tuple[float, float] | None:
    """Top-left corner (scene units) of a node's shape extent, or None."""
    shape = node.get('shape')
    xt = shape.get('xt') if isinstance(shape, Node) else None
    if isinstance(xt, str) and xt.count(',') == 3:
        x1, y1, _, _ = (float(v) for v in xt.split(','))
        return x1 * SCALE, y1 * SCALE
    return None


def _geo_sig(t: Transition, m: Machine) -> list:
    """What the line of a transition depends on: its route points, end angles and the places
    of its two nodes. The geometry read from the file is used while this stays the same."""
    a, b = m.node(t.src), m.node(t.dst)
    return [[list(p) for p in t.points], t.start_angle, t.end_angle,
            [a.x, a.y] if a is not None else None, [b.x, b.y] if b is not None else None]


def _transition_geometry(t: Transition, n: Node, m: Machine) -> None:
    """Bend points, attach angles and label position as drawn in the legacy tool."""
    shape = n.get('shape')
    pts = shape.get('pts') if isinstance(shape, Node) else None
    if isinstance(pts, list) and len(pts) >= 2:
        xy = [[float(v) * SCALE for v in str(p).split(',')] for p in pts]
        a, b = m.node(t.src), m.node(t.dst)
        if a is not None:
            t.start_angle = math.atan2(xy[0][1] - a.y, xy[0][0] - a.x)
        if b is not None:
            t.end_angle = math.atan2(xy[-1][1] - b.y, xy[-1][0] - b.x)
        t.points = xy[1:-1]
    tb = n.get('tb')
    if isinstance(tb, Node):
        corner = _top_left(tb)
        if corner:
            t.label_x, t.label_y = corner
            box = _rect(tb.get('shape'))
            if box:
                t.orig['sig'] = [t.cond, t.actions]
                t.orig['box_size'] = [box[2] - box[0], box[3] - box[1]]
                cond, acts = _rect(tb.get('condition')), _rect(tb.get('actions'))
                if cond:
                    t.orig['cond'] = [cond[0] - box[0], cond[1] - box[1]]
                if acts:
                    t.orig['acts'] = [acts[0] - box[0], acts[1] - box[1]]
                ls = tb.get('lineShape')
                line = _rect(ls) if isinstance(ls, Node) and not _hidden(ls) else None
                t.orig['line'] = line[1] - box[1] if line else None
    t.orig['geo_sig'] = _geo_sig(t, m)
    tp = n.get('tp')
    if isinstance(tp, Node):
        circle = _rect(tp.get('shape'))
        t.orig['prio_shown'] = not _hidden(tp.get('shape'))
        if circle:
            t.orig['prio_center'] = [(circle[0] + circle[2]) / 2, (circle[1] + circle[3]) / 2]
            t.orig['prio_r'] = (circle[2] - circle[0]) / 2


def _rect(node: Any) -> tuple[float, float, float, float] | None:
    """(x0, y0, x1, y1) in scene units of an object's extent ("xt"), or of its shape's."""
    if not isinstance(node, Node):
        return None
    xt = node.get('xt')
    if not isinstance(xt, str):
        sh = node.get('shape')
        xt = sh.get('xt') if isinstance(sh, Node) else None
    if isinstance(xt, str) and xt.count(',') == 3:
        x0, y0, x1, y1 = (float(v) * SCALE for v in xt.split(','))
        return x0, y0, x1, y1
    return None


def _font_size(node: Any) -> int | None:
    """Point size of a text object (va font "name,size,bold")."""
    va = node.get('va') if isinstance(node, Node) else None
    font = va.get('font') if isinstance(va, Node) else None
    parts = font.split(',') if isinstance(font, str) else []
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None


def _text_geo(node: Any, cx: float, cy: float) -> list | None:
    """Where the legacy tool drew a text object (Text / MLText, or the text of a TextAssociate), relative
    to its node's centre (cx, cy): [x0, y0, x1, y1, justify, baseline]. justify is the legacy tool's "ju"
    (0 centred, 2 right, None left); baseline the y of the first line's baseline ("blo"), or
    None. None when the text is not there or hidden."""
    if isinstance(node, Node) and node.type == 'TextAssociate':
        node = node.get('text')
    r = _rect(node)
    if r is None or _hidden(node):
        return None
    blo = node.get('blo')
    base = float(blo.split(',')[1]) * SCALE - cy if isinstance(blo, str) and ',' in blo else None
    return [r[0] - cx, r[1] - cy, r[2] - cx, r[3] - cy, node.get('ju'), base]


def _shape_geo(n: Node, cx: float, cy: float, kinds: tuple[str, ...]) -> list | None:
    """The first shape of one of the given kinds in a node's shape, relative to (cx, cy)."""
    for s in _walk(n.get('shape')):
        if s.type in kinds:
            r = _rect(s)
            if r:
                return [r[0] - cx, r[1] - cy, r[2] - cx, r[3] - cy]
    return None


def _node_geo(n: Node, cx: float, cy: float) -> dict:
    """The geometry of a junction, link or state point as the legacy tool saved it (see model: orig)."""
    g = {}
    shape = _shape_geo(n, cx, cy, ('Diamond', 'Pentagon', 'Circle'))
    if shape:
        g['shape'] = shape
    # the arrow's direction: the legacy tool "ro" 270 = pointing right (the usual), 180 up, 90 left, 0 down
    pent = next((s for s in _walk(n.get('shape')) if s.type == 'Pentagon'), None)
    if pent is not None and isinstance(pent.get('ro'), int) and pent.get('ro') != 270:
        g['ro'] = pent.get('ro')
    if n.type == 'SmResetPoint':
        # the reset icon: the edge (asynchronous reset) or the ring (synchronous reset), whichever
        # the legacy tool shows
        parts = [c for c in (n.get('shape').get('optionalChildren') or []) if isinstance(c, Node)]             if isinstance(n.get('shape'), Node) else []
        wave = next((c for c in parts if c.type == 'OrthoPolyLine'), None)
        ring = next((c for c in parts if c.type == 'Circle'), None)
        if ring is not None and not _hidden(ring):
            g['ring'] = True
        if wave is not None and _hidden(wave):
            g['no_wave'] = True
    for key, node in (('symbol', n.get('symbol')), ('name', n.get('name')), ('expr', n.get('caseExpr'))):
        t = _text_geo(node, cx, cy)
        if t:
            g[key] = t
    cond = n.get('cond')
    if isinstance(cond, Node):
        box = cond.get('shape')
        if isinstance(box, Node) and not _hidden(box) and _rect(box):
            r = _rect(box)
            g['cond_box'] = [r[0] - cx, r[1] - cy, r[2] - cx, r[3] - cy]
        t = _text_geo(cond.get('cond'), cx, cy)
        if t:
            g['cond'] = t
    return g


def _hidden(node: Any) -> bool:
    """Whether an object is drawn hidden (va isHidden 1)."""
    va = node.get('va') if isinstance(node, Node) else None
    return isinstance(va, Node) and va.get('isHidden') == 1


def _labelled_texts(doc: Document) -> dict[str, str]:
    """Map caption -> text for caption/text pairs ("Pre Actions:" -> "...")."""
    out: dict[str, str] = {}
    for n in doc.walk():
        if n.type == 'BiTextGroup':
            out[_text(n.get('first'))] = n.get('second').get('st') or ''
        vec = n.get('textVec')
        if isinstance(vec, list):
            for a, b in zip(vec, vec[1:]):
                if isinstance(a, Node) and isinstance(b, Node) and a.type == 'Text' and b.type == 'MLText':
                    out.setdefault(a.get('st') or '', b.get('st') or '')
    return out


def _signals(doc: Document) -> list[Signal]:
    """The ports and internal signals of the view (LeafLogPort objects of the Signals Table):
    mode, type, bounds, category (clock / reset / enable from the legacy "cat" code), scheme,
    default and reset values, group (LGroup) and comment.
    """
    group_of: dict[int, str] = {}
    for n in doc.walk():
        if n.type == 'LGroup':
            for child in n.get('optionalChildren') or []:
                if isinstance(child, Node):
                    group_of[id(child)] = n.get('name') or ''
    sigs = []
    for n in doc.walk():
        if n.type != 'LeafLogPort':
            continue
        port = n.get('port')
        decl = port.get('decl')
        mode = _MODE.get(port.get('m'), 'input')
        expr = n.get('expr') or ''
        # signal category in the legacy file: its code (model.CATEGORY_CODES), cat absent = Data
        label = next((k for k, v in CATEGORY_CODES.items() if v == n.get('cat')), 'Data')
        if n.get('cat') is not None and label == 'Data':
            label = 'Enable (High)'                  # a code not known yet: as before, an enable
        if mode in ('output', 'local'):
            scheme = 'none' if n.get('ass') == '<none>' else _SCHEME.get(n.get('scheme'), 'comb')
        else:
            scheme = 'none'
        sig = Signal(
            name=decl.get('n'), mode=mode, type=decl.get('t') or 'wire', bounds=decl.get('b') or '',
            signed=bool(decl.get('s')), group=group_of.get(id(n), ''),
            expression=expr, scheme=scheme, default=n.get('defVal') or '', reset=n.get('rstVal') or '',
            comment=re.sub(r'^\s*//\s*', '', decl.get('eolc') or ''),
            value=decl.get('iv') or '', array=decl.get('ub') or '')
        set_category_label(sig, label, keep_expression=True)
        sigs.append(sig)
    return sigs


def _row_positions(doc: Document) -> dict[int, int]:
    """Display row of each table entry (MRCItem litem &N pos P)."""
    pos = {}
    for n in doc.walk():
        if n.type == 'MRCItem' and isinstance(n.get('litem'), Ref) and isinstance(n.get('pos'), int):
            pos.setdefault(n.get('litem').label, n.get('pos'))
    return pos


def _parameters(doc: Document) -> list[Parameter]:
    """Parameters of the view (LogGeneric objects), in the row order of the parameter table."""
    rows = _row_positions(doc)
    found = []
    for n in doc.walk():
        if n.type == 'LogGeneric':
            g = n.get('generic')
            found.append((rows.get(n.label, 1 << 30),
                          Parameter(name=g.get('name'), value=g.get('value') or '', type=g.get('type') or '')))
    return [p for _, p in sorted(found, key=lambda x: x[0])]


def symbol_parameters(path: str) -> list[tuple[str, str]]:
    """(name, default declaration) rows of a legacy symbol's Parameters table, in table order."""
    return [(p.name, p.value) for p in _parameters(parse_file(path))]


def _transition_actions(n: Node) -> str:
    """Action text of a transition ('' when the legacy tool shows the placeholder "< Automatic >")."""
    tb = n.get('tb')
    actions = _text(tb.get('actions')) if isinstance(tb, Node) else ''
    return '' if actions.strip() == '< Automatic >' else actions


def _join(a: str, b: str, sep: str) -> str:
    """Join the non-blank strings among a and b with sep."""
    return sep.join(x for x in (a, b) if x.strip())


def _flat_transitions(diagram: Node, flatten: bool = True) -> list[tuple[Node, int, int, str, str]]:
    """All transitions of a diagram as (node, src label, dst label, condition, actions), with the
    hierarchical states resolved the way the legacy tool generates them.

    A CompositeState (hierarchical state) only groups states: it never becomes a state of the
    machine. The legacy tool follows the paths through it:
      - a transition into the composite state continues from the entry point of its child
        diagram, so  X --c/a--> COMPOSITE  +  ENTRY --e/b--> Y  becomes  X --c&e / a b--> Y;
      - a transition into an exit point of the child diagram continues along the transitions
        leaving the composite state:  Z --z/a--> EXIT  +  COMPOSITE --w/b--> W  becomes
        Z --z&w / a b--> W.
    The node (geometry, priority, id) of the first transition of each path is kept.
    """
    entries: dict[int, list[int]] = {}       # composite label -> entry point labels inside it
    exit_owner: dict[int, int] = {}          # exit point label -> composite label owning it
    for n in _walk(diagram):
        if n.type == 'CompositeState' and n.label is not None:
            child = n.get('childDiagram')
            for c in _walk(child):
                if c.label is None:
                    continue
                if c.type == 'EntryPoint':
                    entries.setdefault(n.label, []).append(c.label)
                elif c.type == 'ExitPoint':
                    exit_owner[c.label] = n.label
    raw = []
    for n in _walk(diagram):
        if n.type != 'Transition':
            continue
        src, dst = n.get('start'), n.get('end')
        if isinstance(src, Ref) and isinstance(dst, Ref):
            raw.append((n, src.label, dst.label, n.get('cond') or '', _transition_actions(n)))
    if not flatten or (not entries and not exit_owner):
        return raw
    out_of: dict[int, list[tuple]] = {}      # label -> transitions starting there
    for r in raw:
        out_of.setdefault(r[1], []).append(r)

    def follow(path: tuple, depth: int = 0) -> list[tuple]:
        """Extend one path (node, src, dst, cond, actions) through the entry / exit point it ends in,
        returning the resolved paths (see the docstring of _flat_transitions).
        """
        n, src, dst, cond, actions = path
        if depth > 16:                       # a malformed cycle of composites: give up on it
            return []
        if dst in entries:
            nxt = [r for e in entries[dst] for r in out_of.get(e, [])]
        elif dst in exit_owner:
            nxt = out_of.get(exit_owner[dst], [])
        else:
            return [path]
        res = []
        for r in nxt:
            cond2 = _join(f'({cond})' if cond and r[3] else cond, f'({r[3]})' if cond and r[3] else r[3], ' & ')
            res += follow((n, src, r[2], cond2, _join(actions, r[4], '\n')), depth + 1)
        return res

    flat = []
    for r in raw:
        # paths starting inside the hierarchy plumbing are reached through the paths above
        if r[1] in entries or r[1] in exit_owner.values() or any(r[1] in v for v in entries.values()):
            continue
        flat += follow(r)
    return flat


def _machine(doc: Document, csm: Node, header_machine: Node | None) -> Machine:
    """Build one Machine from a ConcurrentSM object: names of the state variables (from the
    Header and the generation properties), every node of the diagram (keeping legacy geometry), and
    the transitions as drawn. Node ids are 'n<legacy label>' so export_sm can find the original
    objects again; states are sorted by the machine's stateOrder (the encoding order).
    """
    m = Machine(name=csm.get('name') or 'fsm')
    gen = csm.get('genChar')
    m.next_state_clocking = isinstance(gen, Node) and gen.get('nextStateClocking') == 1
    top = csm.get('topDiagram')
    va = top.get('viewArea') if isinstance(top, Node) else None
    if isinstance(va, str) and va.count(',') == 3:
        m.view_area = [float(v) * SCALE for v in va.split(',')]
    if header_machine is not None and header_machine.get('stateSignalName'):
        m.current_state_name = header_machine.get('stateSignalName')
    # State Machine Properties > Advanced > State Signal Names: kept in the machine's
    # generation properties (csName / nsName) when the user typed them
    if isinstance(gen, Node):
        if isinstance(gen.get('csName'), str) and gen.get('csName'):
            m.current_state_name = gen.get('csName')
        if isinstance(gen.get('nsName'), str) and gen.get('nsName'):
            m.next_state_name = gen.get('nsName')
    ids: dict[int, str] = {}
    diagram = csm.get('topDiagram')
    order = {}
    for i, ref in enumerate(csm.get('stateOrder') or []):
        if isinstance(ref, Ref):
            order[ref.label] = i
    # the hierarchical state each node is inside (deepest one: an inner composite's walk
    # comes after its parent's)
    parent_of: dict[int, int] = {}
    for n in _walk(diagram):
        if n.type == 'CompositeState' and n.label is not None:
            for c in _walk(n.get('childDiagram')):
                if c.label is not None and c is not n:
                    parent_of[c.label] = n.label
    for n in _walk(diagram):
        if n.label is None:
            continue
        x, y = _center(n)
        nid = f'n{n.label}'
        parent = f'n{parent_of[n.label]}' if n.label in parent_of else ''
        if n.type == 'CompositeState':
            st = State(id=nid, name=_text(n.get('name')), x=x, y=y, hier=True, parent=parent)
            shape = n.get('shape')
            if isinstance(shape, Node) and isinstance(shape.get('radius'), int):
                st.radius = shape.get('radius') * SCALE
            m.states.append(st)
        elif n.type in ('EntryPoint', 'ExitPoint'):
            m.points.append(Point(id=nid, kind='entry' if n.type == 'EntryPoint' else 'exit', x=x, y=y,
                                  parent=f'n{parent_of[n.label]}' if n.label in parent_of else ''))
        elif n.type == 'State':
            st = State(id=nid, name=_text(n.get('name')), x=x, y=y, encoding=_text(n.get('encoding')))
            shape = n.get('shape')
            if isinstance(shape, Node) and isinstance(shape.get('radius'), int):
                st.radius = shape.get('radius') * SCALE
            font = _font_size(n.get('name'))
            if font:
                st.orig['font'] = font
            st.is_wait = n.get('isWait') == 1 or (isinstance(shape, Node) and shape.type == 'CircleInOctagon')
            st.wait = _text(n.get('wait')) if st.is_wait else ''
            blk = n.get('actionBlk')
            if isinstance(blk, Node):
                st.entry_actions = _text(blk.get('entryActions'))
                st.in_actions = _text(blk.get('inActions'))
                st.exit_actions = _text(blk.get('exitActions'))
                corner = _top_left(blk)
                if corner:
                    st.actions_x, st.actions_y = corner
                    box = _rect(blk.get('shape'))
                    if box:
                        st.orig['sig'] = [st.entry_actions, st.in_actions, st.exit_actions]
                        st.orig['act_size'] = [box[2] - box[0], box[3] - box[1]]
                        for key in ('tline', 'bline'):
                            ln = blk.get(key)
                            r = _rect(ln) if isinstance(ln, Node) and not _hidden(ln) else None
                            st.orig[key] = r[1] - box[1] if r else None
                        for key, field_ in (('entry', 'entryActions'), ('in', 'inActions'),
                                            ('exit', 'exitActions')):
                            r = _rect(blk.get(field_))
                            if r:
                                st.orig[key] = [r[0] - box[0], r[1] - box[1]]
            st.parent = parent
            m.states.append(st)
        elif n.type == 'Junction':
            expr = _text(n.get('caseExpr'))
            if expr.startswith('CASE:'):
                expr = expr[5:].strip()
            sym = n.get('symbol')
            m.junctions.append(Junction(id=nid, kind='case' if n.get('jType') == 1 else 'if', expr=expr, x=x, y=y,
                                        symbol=_text(sym) if isinstance(sym, Node) else '', parent=parent,
                                        orig=_node_geo(n, x, y)))
        elif n.type == 'Link':
            m.links.append(Link(id=nid, target=_text(n.get('name')), x=x, y=y, parent=parent,
                                orig=_node_geo(n, x, y)))
        elif n.type in _POINT:
            m.points.append(Point(id=nid, kind=_POINT[n.type], x=x, y=y, orig=_node_geo(n, x, y)))
        else:
            continue
        ids[n.label] = nid
    m.states.sort(key=lambda s: order.get(int(s.id[1:]), 1 << 30))
    # the transitions as drawn (to / from hierarchical states and their entry / exit points);
    # code generation follows the paths through them (codegen.hierarchy)
    for n, src, dst, cond, actions in _flat_transitions(diagram, flatten=False):
        if src not in ids or dst not in ids:
            continue
        tp = n.get('tp')
        prio = _text(tp.get('pr')) if isinstance(tp, Node) else ''
        t = Transition(
            id=f'n{n.label}' if n.label is not None else m.new_id('t'), src=ids[src], dst=ids[dst],
            cond=cond, actions=actions, priority=int(prio) if prio.isdigit() else 1)
        _transition_geometry(t, n, m)
        m.transitions.append(t)
    for i, t in enumerate(m.transitions):
        if t.id in ids.values() or any(o.id == t.id for o in m.transitions[:i]):
            t.id = m.new_id('t')
    return m


def import_sm(path: str, library: str | None = None, unit: str | None = None) -> FsmView:
    """Read a legacy state diagram file and return the view. `library` / `unit` default to the names
    in the path (<lib>/hds/<unit>/<view>.sm).
    """
    doc = parse_file(path)
    parts = os.path.normpath(os.path.abspath(path)).split(os.sep)
    view_name = os.path.splitext(parts[-1])[0]
    unit = unit or (parts[-2] if len(parts) > 1 else 'unit')
    if library is None:
        library = parts[-4] if len(parts) > 3 and parts[-3] == META_DIR else 'work'
    model = doc.get('model')
    lang = model.get('LanguageMgr') or ''
    texts = _labelled_texts(doc)
    from .sheet import read_sheets
    sheets = read_sheets(doc)
    view = FsmView(
        library=library, unit=unit, view=view_name,
        language='systemverilog' if 'SystemVerilog' in lang else 'verilog',
        signals=_signals(doc), parameters=_parameters(doc), machines=[],
        signals_sheet=sheets[0], params_sheet=sheets[1],
        pre_module_directives=texts.get('Pre-module directives:', ''),
        post_module_directives=texts.get('Post-module directives:', ''),
        end_module_directives=texts.get('End-module directives:', ''),
        concurrent_statements=texts.get('Concurrent Statements', ''),
        state_register_statements=texts.get('State Register Statements', ''),
        global_pre_actions=texts.get('Pre Actions:', ''),
        global_post_actions=texts.get('Post Actions:', ''),
        registered_affix=model.get('signalSuffix') or '_r',
        clocked_affix=model.get('clockSuffix') or '_cld',
    )
    tmpl = model.get('defaultState')
    if isinstance(tmpl, Node):
        view.default_state_name = _text(tmpl.get('name'))
    # positions of the declaration blocks drawn at the top of the diagram (their title texts)
    titles = {'Global Actions': 'global', 'Concurrent Statements': 'concurrent',
              'Module Declarations': 'module', 'Signal Status': 'status',
              'State Register Statements': 'statereg', 'Compiler Directives': 'compdir'}
    for n in doc.walk():
        key = titles.get(n.get('st')) if n.type == 'Text' else None
        xt = n.get('xt') if key else None
        if key and key not in view.decl_pos and isinstance(xt, str) and xt.count(',') == 3:
            x0, y0 = (float(v) * SCALE for v in xt.split(',')[:2])
            view.decl_pos[key] = [x0, y0]
            if _hidden(n):
                view.decl_hidden.append(key)
    tmpl = model.get('defaultJunction')
    if isinstance(tmpl, Node) and isinstance(tmpl.get('symbol'), Node):
        view.default_junction_symbol = _text(tmpl.get('symbol'))
    header = doc.get('Header')
    header_machines = []
    if isinstance(header, Node) and isinstance(header.get('machine'), Node):
        header_machines = [c for c in header.get('machine').get('children') or [] if isinstance(c, Node)]
    for i, csm in enumerate(n for n in doc.walk() if n.type == 'ConcurrentSM'):
        view.machines.append(_machine(doc, csm, header_machines[i] if i < len(header_machines) else None))
    return view

"""Import a legacy block diagram (.bd) into a BlockDiagram."""
from __future__ import annotations

import os

import re

from bd_model import (NAME_LINE_H as LINE_H, BdComment, BdEmbedded, BdFrame, BdInstance, BdJunction, BdPin,
                        BdPortIo, BdWire, BlockDiagram)
from model import Parameter
from .import_sm import SCALE, _labelled_texts, _parameters, _signals, _text, _walk
from .names import META_DIR
from .sexpr import Node, Ref, parse_file

_MODE = {None: 'input', 1: 'output', 2: 'inout', 3: 'buffer'}


def _rect(node) -> tuple[float, float, float, float]:
    """(x, y, w, h) in scene units from the first xt of a node's shape."""
    for n in _walk(node.get('shape') if isinstance(node, Node) else None):
        xt = n.get('xt')
        if isinstance(xt, str) and xt.count(',') == 3:
            x1, y1, x2, y2 = (float(v) * SCALE for v in xt.split(','))
            return x1, y1, x2 - x1, y2 - y1
    return 0.0, 0.0, 0.0, 0.0


def _color(value, default: str) -> str:
    """'#rrggbb' from a legacy 16-bit colour "r,g,b"."""
    if not isinstance(value, str) or value.count(',') != 2:
        return default
    return '#' + ''.join(f'{int(v) >> 8:02x}' for v in value.split(','))


def _extent(node) -> tuple[float, float, float, float]:
    """(x, y, w, h) of everything drawn in a node's shape (a PortIO is a body plus a stub)."""
    boxes = []
    for n in _walk(node.get('shape') if isinstance(node, Node) else None):
        xt = n.get('xt')
        if isinstance(xt, str) and xt.count(',') == 3:
            boxes.append([float(v) * SCALE for v in xt.split(',')])
    if not boxes:
        return 0.0, 0.0, 0.0, 0.0
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    return x1, y1, x2 - x1, y2 - y1


def _xt_of(node) -> tuple[float, float] | None:
    """Top-left (scene units) of a legacy text's own extent ("xt"), or None."""
    xt = node.get('xt') if isinstance(node, Node) else None
    if isinstance(xt, str) and xt.count(',') == 3:
        x1, y1 = (float(v) * SCALE for v in xt.split(',')[:2])
        return x1, y1
    return None


def _hidden_node(node) -> bool:
    """Whether a legacy text is hidden (va isHidden 1)."""
    va = node.get('va') if isinstance(node, Node) else None
    return isinstance(va, Node) and va.get('isHidden') == 1


def import_bd(path: str, library: str | None = None, unit: str | None = None) -> BlockDiagram:
    """Read a legacy block diagram (.bd) and return it as a BlockDiagram.

    `library` / `unit` default to the names in the path (<lib>/hds/<unit>/struct.bd). Steps:
      1. module data: language, ports and nets (_signals), parameters, directives, view area,
         the user text of the Declarations block;
      2. wires: points, net name, slice, name label; which object each wire end touches
         (`touches`: legacy label -> net);
      3. component instances (SaComponent, and MWC for ModuleWare gates) with their pins and
         parameter overrides (from the file's Header), embedded blocks with their Text view,
         port I/Os, generate frames, junction dots and title-block comments;
      4. wire ends are turned into attachment strings ("pin:<inst>:<pin>", "pio:<id>",
         "emb:<id>", "jct:<id>").
    Objects under model.default* are templates for new objects and are skipped. Coordinates are
    multiplied by SCALE (legacy units -> scene units).
    """
    doc = parse_file(path)
    parts = os.path.normpath(os.path.abspath(path)).split(os.sep)
    unit = unit or (parts[-2] if len(parts) > 1 else 'unit')
    if library is None:
        library = parts[-4] if len(parts) > 3 and parts[-3] == META_DIR else 'work'
    model = doc.get('model')
    lang = model.get('LanguageMgr') or ''
    texts = _labelled_texts(doc)
    from .sheet import read_sheets
    sheets = read_sheets(doc)
    bd = BlockDiagram(
        library=library, unit=unit, view=os.path.splitext(parts[-1])[0],
        language='systemverilog' if 'SystemVerilog' in lang else 'verilog',
        signals=_signals(doc), parameters=_parameters(doc),
        signals_sheet=sheets[0], params_sheet=sheets[1],
        pre_module_directives=texts.get('Pre-module directives:', ''),
        post_module_directives=texts.get('Post-module directives:', ''),
        end_module_directives=texts.get('End-module directives:', ''))
    va = model.get('viewArea')
    if isinstance(va, str) and va.count(',') == 3:
        bd.view_area = [float(v) * SCALE for v in va.split(',')]
    decl_block = next((n for n in doc.walk() if n.type == 'BdArchDeclBlock'), None)
    if decl_block is not None:
        bd.pre_user_declarations = _text(decl_block.get('preUserText'))
        bd.post_user_declarations = _text(decl_block.get('postUserText'))
    # where the Declarations and Compiler Directives blocks are drawn, and whether they show
    blocks = {b.id: b for b in bd.text_blocks}
    label = decl_block.get('declLabel') if decl_block is not None else None
    if isinstance(label, Node) and _xt_of(label):
        x, y = _xt_of(label)
        blocks['decl'].x, blocks['decl'].y = x, y
        blocks['decl'].visible = not _hidden_node(label)
        port = decl_block.get('portLabel')
        blocks['decl'].contents = isinstance(port, Node) and not _hidden_node(port)
    comp = model.get('compDirBlock')
    vec = comp.get('textVec') if isinstance(comp, Node) else None
    title = vec[0] if isinstance(vec, list) and vec and isinstance(vec[0], Node) else None
    if title is not None and _xt_of(title):
        x, y = _xt_of(title)
        blocks['dirs'].x, blocks['dirs'].y = x, y
        blocks['dirs'].visible = not _hidden_node(title)

    # net name of each Net object
    net_name = {}
    for n in doc.walk():
        if n.type == 'Net' and n.label is not None:
            net_name[n.label] = n.get('decl').get('n')

    # which net each pin / port-io / embedded block touches
    touches: dict[int, str] = {}
    slices: dict[int, str] = {}       # object label -> slice of the net its wire connects
    wire_ends: list = []
    refs: dict[int, str] = {}         # legacy object label -> our attachment reference
    for n in doc.walk():
        if n.type != 'Wire':
            continue
        on = n.get('on')
        net = net_name.get(on.label) if isinstance(on, Ref) else None
        if not net:
            continue
        pts = []
        shape = n.get('shape')
        if isinstance(shape, Node) and isinstance(shape.get('pts'), list):
            for p in shape.get('pts'):
                x, y = (float(v) * SCALE for v in str(p).split(','))
                pts.append([x, y])
        w = BdWire(f'w{n.label or len(bd.wires)}', net, pts, slice=n.get('sl') or '')
        name_text = next((t for t in _walk(n.get('tg')) if t.type == 'Text' and t.get('tm') == 'WireNameMgr'), None)
        if name_text is not None and pts:
            va = name_text.get('va')
            w.show_text = not (isinstance(va, Node) and va.get('isHidden') == 1)
            blo = name_text.get('blo')
            if isinstance(blo, str) and ',' in blo:
                bx, by = (float(v) * SCALE for v in blo.split(','))
                w.label = [bx - pts[0][0], by - pts[0][1]]
                w.label_vertical = name_text.get('ro') == 270
        bd.wires.append(w)
        ends = []
        for end in ('start', 'end'):
            r = n.get(end)
            if isinstance(r, Ref):
                touches[r.label] = net
                if n.get('sl'):                 # the wire carries only a slice of its net
                    slices[r.label] = n.get('sl')
            ends.append(r.label if isinstance(r, Ref) else None)
        wire_ends.append((w, ends))

    # objects under model.default* are templates for new objects, not diagram content
    templates = set()
    for k, v in model.fields:
        if k.startswith('default'):
            templates.update(id(n) for n in _walk(v))

    header = doc.get('Header')
    header_insts = {}
    if isinstance(header, Node):
        for inst in header.get('instances') or []:
            header_insts[inst.get('uid')] = inst
        # the instances inside generate frames are listed per frame
        for fi in header.get('frameInstances') or []:
            for inst in (fi.get('insts') if isinstance(fi, Node) else None) or []:
                header_insts[inst.get('uid')] = inst

    # components, and ModuleWare components (library moduleware, e.g. an or gate)
    for sa in (n for n in doc.walk() if n.type in ('SaComponent', 'MWC') and id(n) not in templates):
        hi = header_insts.get(sa.get('uid'))
        labels, texts = {}, {}
        for t in _walk(sa.get('ttg')):
            if t.type == 'Text' and t.get('tm'):
                labels[t.get('tm')] = t.get('st') or ''
                texts[t.get('tm')] = t
        x, y, w, h = _rect(sa)
        inst = BdInstance(
            id=f'i{sa.label}', name=(hi.get('name') if hi else labels.get('InstanceNameMgr', '')),
            library=(hi.get('duLibraryName') if hi else labels.get('BdLibraryNameMgr', '')),
            unit=(hi.get('duName') if hi else labels.get('CptNameMgr', '')), x=x, y=y, w=w, h=h)
        if sa.type == 'MWC' and not hi:
            plain = [t.get('st') or '' for t in _walk(sa.get('ttg')) if t.type == 'Text']
            inst.library = 'moduleware'
            inst.unit = labels.get('CptNameMgr') or (plain[1] if len(plain) > 1 else '')
        # name text: the library line keeps its place even when hidden, the others follow it
        first = texts.get('BdLibraryNameMgr') or texts.get('CptNameMgr')
        xt = first.get('xt') if first is not None else None
        if isinstance(xt, str) and xt.count(',') == 3:
            tx, ty = (float(v) * SCALE for v in xt.split(',')[:2])
            inst.text_pos = [tx - x, ty - y - (0 if 'BdLibraryNameMgr' in texts else LINE_H)]

        def visible(tm):
            """True when the name text with manager `tm` exists and is not hidden (va.isHidden)."""
            va = texts[tm].get('va') if tm in texts else None
            return tm in texts and not (isinstance(va, Node) and va.get('isHidden') == 1)
        if texts:
            inst.show_library, inst.show_instance = visible('BdLibraryNameMgr'), visible('InstanceNameMgr')
        if hi:
            inst.params = [Parameter(e.get('name'), e.get('value') or '') for e in hi.get('elements') or []]
        for c in sa.get('optionalChildren') or []:
            if not (isinstance(c, Node) and c.type == 'CptPort'):
                continue
            lp = c.get('thePort')
            decl = lp.get('decl')
            px, py, pw, ph = _rect(c)
            cx, cy = px + pw / 2, py + ph / 2
            side = min((('left', abs(cx - x)), ('right', abs(cx - (x + w))),
                        ('top', abs(cy - y)), ('bottom', abs(cy - (y + h)))), key=lambda s: s[1])[0]
            inst.pins.append(BdPin(decl.get('n'), _MODE.get(lp.get('m'), 'input'),
                                   touches.get(c.label, ''), decl.get('o') or 0, cx, cy, side, decl.get('b') or ''))
            tri = c.get('shape')                # the legacy triangle says where it points
            if isinstance(tri, Node) and tri.type == 'Triangle':
                inst.pins[-1].arrow = {0: 'up', 90: 'right', 180: 'down', 270: 'left'}.get(tri.get('ro') or 0, '')
            inst.pins[-1].slice = slices.get(c.label, '')
            inst.pins[-1].clock = any(isinstance(k, Node) and k.type == 'FFT' for k in c.get('optionalChildren') or [])
            refs[c.label] = f'pin:{inst.id}:{decl.get("n")}'
        bd.instances.append(inst)

    emb_names = [(n.get('name'), n.get('number')) for n in doc.walk() if n.type == 'EmbeddedInstance']
    for i, ht in enumerate(n for n in doc.walk() if n.type == 'HdlText' and id(n) not in templates):
        et = next((c for c in ht.get('optionalChildren') or [] if isinstance(c, Node) and c.type == 'EmbeddedText'), None)
        text = ''
        if et is not None:
            ct = et.get('commentText')
            text = _text(ct.get('text')) if isinstance(ct, Node) and isinstance(ct.get('text'), Node) else _text(ct)
        name, number = emb_names[i] if i < len(emb_names) else (f'eb{i + 1}', str(i + 1))
        x, y, w, h = _rect(ht)
        eb = BdEmbedded(f'e{ht.label}', name or f'eb{i + 1}', int(number or i + 1), text, x, y, w, h)
        # The block is a yellow frame (the HdlText shape); its Text view is the white box of
        # EmbeddedText.commentText, kept relative to the block.
        ct = et.get('commentText') if et is not None else None
        if isinstance(ct, Node):
            tx, ty, tw, th = _rect(ct)
            if tw > 0 and th > 0:
                eb.text_box = [tx - x, ty - y, tw, th]
        # the "eb1" name label is often hidden
        name_text = next((t for t in _walk(ht.get('ttg')) if t.type == 'Text'), None)
        va = name_text.get('va') if name_text is not None else None
        eb.show_name = not (isinstance(va, Node) and va.get('isHidden') == 1)
        bd.embedded.append(eb)
        refs[ht.label] = f'emb:e{ht.label}'

    for n in doc.walk():
        if n.type in ('PortIoIn', 'PortIoOut', 'PortIoInOut') and id(n) not in templates:
            x, y, w, h = _extent(n)
            name = touches.get(n.label) or _text(n.get('tg'))
            mode = {'PortIoIn': 'input', 'PortIoOut': 'output'}.get(n.type, 'inout')
            bd.port_ios.append(BdPortIo(f'p{n.label}', name, mode, x + w / 2, y + h / 2))
            refs[n.label] = f'pio:p{n.label}'
    # generate frames: FOR (no style), IF (style 1), ELSE (style 2); title "name: spec"
    for i, n in enumerate(n for n in doc.walk() if n.type == 'Frame' and id(n) not in templates):
        title = next((t.get('st') for t in _walk(n.get('title')) if isinstance(t.get('st'), str)), '')
        m = re.match(r'\s*([\w$]+)\s*:\s*(.*)$', title, re.S)
        name, spec = (m.group(1), m.group(2).strip()) if m else (title.strip() or f'g{i}', '')
        kind = {1: 'if', 2: 'else'}.get(n.get('style'), 'for')
        if kind == 'for' and not spec.startswith('[') and n.get('lb') is not None:
            spec = f'[{n.get("lb")}:{n.get("rb") or 0}]'
        num = next((t.get('st') for t in _walk(n.get('seqNum')) if isinstance(t.get('st'), str)), '')
        x, y, w, h = _rect(n)
        bd.frames.append(BdFrame(f'f{n.label or i}', kind, name, spec, int(num) if num.isdigit() else i + 1,
                                 x, y, w, h))
    # dots where nets meet: wire ends attach to them
    for n in doc.walk():
        if n.type == 'BdJunction' and id(n) not in templates:
            x, y, w, h = _rect(n)
            bd.junctions.append(BdJunction(f'j{n.label}', x + w / 2, y + h / 2))
            refs[n.label] = f'jct:j{n.label}'
    # title block: comment boxes of a Grouping move together
    group_of = {}
    for g in doc.walk():
        if g.type == 'Grouping' and id(g) not in templates:
            for c in g.get('optionalChildren') or []:
                if isinstance(c, Node):
                    group_of[id(c)] = f'g{g.label}'
    for n in doc.walk():
        if n.type == 'CommentText' and n.get('titleBlock') == 1 and id(n) not in templates:
            x, y, w, h = _rect(n)
            sva, tva = n.get('shape').get('va'), (n.get('text').get('va') if isinstance(n.get('text'), Node) else None)
            bd.comments.append(BdComment(f'c{n.label}', _text(n.get('text')).strip('\n'), x, y, w, h,
                                         _color(sva.get('fg') if isinstance(sva, Node) else None, ''),
                                         _color(tva.get('fg') if isinstance(tva, Node) else None, '#000080'),
                                         group_of.get(id(n), '')))
    for w, (a, b) in wire_ends:
        w.start, w.end = refs.get(a, ''), refs.get(b, '')
    return bd


def symbol_geometry(path: str):
    """Body size and ports of a legacy symbol (.sb), as the legacy tool draws a new instance of it.

    Returns (w, h, ports) in scene units, ports = [(name, mode, bounds, order, x, y, side)]
    where x, y is the centre of the port triangle relative to the body's top-left corner and
    side is the body edge it is on. None when the file has no symbol body."""
    doc = parse_file(path)
    body = next((n for n in doc.walk() if n.type == 'SymbolBody'), None)
    shape = body.get('shape') if body is not None else None
    if not isinstance(shape, Node) or not isinstance(shape.get('xt'), str):
        return None
    bx0, by0, bx1, by1 = (float(v) for v in shape.get('xt').split(','))
    ports = []
    for c in body.get('optionalChildren') or []:
        if not (isinstance(c, Node) and c.type == 'CptPort'):
            continue
        cs = c.get('shape')
        xt = cs.get('xt') if isinstance(cs, Node) else None
        if not isinstance(xt, str):
            continue
        x0, y0, x1, y1 = (float(v) for v in xt.split(','))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # the edge the triangle touches
        side = min((('left', abs(x1 - bx0)), ('right', abs(x0 - bx1)), ('top', abs(y1 - by0)),
                    ('bottom', abs(y0 - by1))), key=lambda s: s[1])[0]
        lp = c.get('thePort')
        decl = lp.get('decl')
        ports.append((decl.get('n'), _MODE.get(lp.get('m'), 'input'), decl.get('b') or '', decl.get('o') or 0,
                      (cx - bx0) * SCALE, (cy - by0) * SCALE, side))
    return (bx1 - bx0) * SCALE, (by1 - by0) * SCALE, ports

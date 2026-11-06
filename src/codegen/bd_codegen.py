"""Generate structural Verilog / SystemVerilog from a BlockDiagram.

Layout follows the legacy tool: header, directives, ANSI parameters and
ports, internal signal declarations, instances (named port mapping in
symbol order, sorted by instance name), embedded text blocks.
"""
from __future__ import annotations

import re

from bd_model import BlockDiagram
from model import Signal
from version import APP_NAME, __version__
from .common import IND, STYLE, drivers, port_lines, sv_net_type, text_lines

# ModuleWare gates: operator between the inputs, and whether the result is inverted
_MW_OPS = {'and': ('&', False), 'or': ('|', False), 'xor': ('^', False), 'nand': ('&', True),
           'nor': ('|', True), 'xnor': ('^', True), 'inv': ('', True), 'buff': ('', False), 'assignment': ('', False)}


class BdGenerator:
    """Generates one structural module from a BlockDiagram: header and directives, parameters and
    ANSI ports, internal net declarations, component instances (and instance arrays of FOR frames),
    IF / ELSE frames, embedded text blocks, endmodule. Warnings go to self.warnings.
    """
    def __init__(self, bd: BlockDiagram, language: str | None = None):
        """`language` overrides bd.language ('systemverilog' or 'verilog')."""
        self.bd = bd
        self.sv = (language or bd.language) == 'systemverilog'
        self.warnings: list[str] = []

    def _procedural(self) -> set[str]:
        """Signals assigned in procedural code of the embedded blocks (cached): in SystemVerilog they are
        declared logic instead of wire.
        """
        if not hasattr(self, '_proc'):
            self._proc = drivers('\n'.join(e.text for e in self.bd.embedded))[1]
        return self._proc

    def _port_type(self, s: Signal) -> str:
        """Declared type of a module port: SystemVerilog logic / wire by the procedural rule, Verilog wire
        for inputs / inouts and the declared wire / reg for outputs.
        """
        if self.sv:
            return sv_net_type(s.name, self._procedural())
        if s.mode in ('input', 'inout'):
            return 'wire'
        return s.type if s.type in ('wire', 'reg') else 'wire'

    def _ports(self) -> list[str]:
        """The ANSI port list: inputs, then inouts, then outputs, each group sorted by name."""
        order = {'input': 0, 'inout': 1, 'output': 2}
        ports = sorted((s for s in self.bd.signals if s.mode in order), key=lambda s: (order[s.mode], s.name))
        return port_lines([(s.mode, self._port_type(s) + (' signed' if s.signed else ''), s.bounds, s.name,
                            s.comment) for s in ports])

    def _internal(self) -> list[str]:
        """Declarations of the internal nets (signals with mode 'local'), sorted by name and aligned in
        columns exactly as the legacy tool writes them: type (with strength, expansion, signed), bounds, delay,
        name, unpacked array, initial value and end-of-line comment.
        """
        port_names = {s.name for s in self.bd.signals if s.mode != 'local'}
        nets = sorted((s for s in self.bd.signals if s.mode == 'local' and s.name not in port_names),
                      key=lambda s: s.name)
        if not nets:
            return []
        types = {}
        for s in nets:
            if self.sv and s.type in ('wire', 'reg', 'logic', ''):
                t = sv_net_type(s.name, self._procedural())
            else:
                t = s.type if s.type else 'wire'     # wire / reg / tri / supply0 / ... as declared
            if s.strength and t == 'trireg':
                t += f' ({s.strength})'
            if s.expansion and t not in ('reg', 'logic', 'integer', 'time', 'real', 'realtime'):
                t += f' {s.expansion}'
            if s.signed:
                t += ' signed'
            types[s.name] = t
        wt = max(6, max(len(t) + 2 for t in types.values()))   # longest type + 2, as the legacy tool
        bounds = {s.name: _bounds(s.bounds) for s in nets}
        wb = max(len(b) for b in bounds.values()) + 1
        extra = any(s.array or s.value or s.delay for s in nets)
        wname = max(len(s.name) for s in nets) + 2
        out = []
        for s in nets:
            delay = f'#{s.delay} ' if s.delay else ''
            if extra:
                tail = (f'{s.name:<{wname}}{s.array + " " if s.array else ""}'
                        f'{"= " + s.value if s.value else ""}').rstrip()
            else:
                tail = s.name
            # Verilog order: type [range] [#delay] name
            b = bounds[s.name]
            head = f'{b + " " if b else ""}{delay}' if delay else f'{b:<{wb}}'
            line = f'{types[s.name]:<{wt}}{head}{tail};'
            if s.comment:
                width = wt + wb + (wname + 12 if extra else max(len(n.name) + 1 for n in nets) + 3)
                line = f'{line:<{width}}// {s.comment}'
            out.append(line)
        return out

    def _moduleware(self, inst) -> list[str]:
        """ModuleWare gate: one continuous assignment from its inputs (din0, din1...) to dout."""
        ins = [p.net for p in sorted(inst.pins, key=lambda p: p.name) if p.mode != 'output' and p.net]
        out = next((p.net for p in inst.pins if p.mode == 'output' and p.net), '')
        op = _MW_OPS.get(inst.unit)
        if op is None or not out or not ins:
            self.warnings.append(f'{inst.name}: ModuleWare {inst.unit} is not generated')
            return [f"// ModuleWare {inst.unit} '{inst.name}' not generated"]
        sym, invert = op
        expr = f' {sym} '.join(ins) if sym else ins[0]
        return [f"// ModuleWare code for instance '{inst.name}' of '{inst.unit}'",
                f'assign {out} = {"~(" + expr + ")" if invert else expr};']

    def _instance(self, inst, array: str = '') -> list[str]:
        """Lines of one component instance: attributes, `unit #(params) name[array]( .pin(net), ... );`
        with the pins in symbol order. ModuleWare gates are written as assign statements instead.
        Warns about undeclared nets and unconnected inputs.
        """
        if inst.library == 'moduleware':
            return self._moduleware(inst)
        known = {s.name for s in self.bd.signals}
        head = inst.unit
        positional = STYLE['param_mapping'] == 'Positional'
        if inst.params:
            # Named (legacy layout): ".N(v)" on one line, no spaces; Positional (the legacy tool's
            # default): the values only, no spaces
            head += ' #(' + ','.join(p.value if positional else f'.{p.name}({p.value})' for p in inst.params) + ')'
        out = [l.rstrip() for l in inst.attributes.strip('\n').split('\n')] if inst.attributes.strip() else []
        out.append(f'{head} {inst.name}{array}( ')
        explicit = _port_map(inst.portmap_text) if inst.portmap_frame else {}
        pins = sorted(inst.pins, key=lambda p: p.order)
        w = max((len(p.name) for p in pins), default=0) + 1
        for i, p in enumerate(pins):
            sep = ', ' if i < len(pins) - 1 else ''
            actual = (p.net + p.slice) if p.net else explicit.get(p.name, '')
            out.append(f'{IND}.{p.name:<{w}}({actual}){sep}')
            if p.net and p.net.split('[')[0] not in known:
                self.warnings.append(f'{inst.name}.{p.name}: net "{p.net}" is not declared')
            if not actual and p.mode != 'output':
                self.warnings.append(f'{inst.name}.{p.name}: input is not connected')
        out.append('); ')
        return out

    def _instances(self) -> list[str]:
        """Instances outside frames, and instance arrays for those in a FOR frame
        (as the legacy tool writes them: unit inst[left:right](...))."""
        # legacy order (checked on every diagram of a real project): the instances outside
        # frames sorted by library, then component, then instance name; then the instance arrays
        # of the FOR frames in frame number order. The array range is the frame text as typed
        # ("[ N - 1 : 0 ]" keeps its spaces).
        key = lambda i: (i.library, i.unit, i.name)  # noqa: E731
        out = []
        for inst in sorted((i for i in self.bd.instances if self.bd.frame_of(i) is None), key=key):
            out += self._instance(inst) + ['']
        framed = [(self.bd.frame_of(i), i) for i in self.bd.instances if self.bd.frame_of(i) is not None]
        for frame, inst in sorted(framed, key=lambda fi: (fi[0].number, key(fi[1]))):
            if frame.kind == 'for':
                spec = frame.spec.strip()
                array = spec if spec.startswith('[') and spec.endswith(']') else '[{}:{}]'.format(*frame.range())
                out += self._instance(inst, array) + ['']
        return out

    @staticmethod
    def _embedded(eb, indent: str = '') -> list[str]:
        """Lines of an embedded block: the "HDL Embedded Text Block" comment and its text, each line
        prefixed with `indent`.
        """
        # The legacy tool drops one line break at the start of the text and all at its end: a text that
        # starts with an empty line ("\n\n// ...") is written with that empty line (as in the legacy tool)
        text = eb.text.rstrip('\n')
        text = text[1:] if text.startswith('\n') else text
        lines = text.split('\n') if text.strip() else []
        return [f'{indent}// HDL Embedded Text Block {eb.number} {eb.name}'] + [indent + l for l in lines]

    def _frame_body(self, frame, indent: str) -> list[str]:
        """The instances and embedded blocks of one IF / ELSE frame, indented with `indent`."""
        out = []
        for inst in sorted((i for i in self.bd.instances if self.bd.frame_of(i) is frame), key=lambda i: i.name):
            out += [indent + l for l in self._instance(inst)]
        for eb in sorted((e for e in self.bd.embedded if self.bd.frame_of(e) is frame), key=lambda e: e.number):
            out += self._embedded(eb, indent)
        return out

    def _if_frames(self) -> list[str]:
        """IF frames (with their ELSE frame): `ifdef blocks or generate-if blocks."""
        out = []
        frames = sorted(self.bd.frames, key=lambda f: f.number)
        for f in (f for f in frames if f.kind == 'if'):
            other = next((e for e in frames if e.kind == 'else' and e.name == f.name), None)
            cond = f.spec.strip()
            if cond.startswith('`'):
                out.append(cond)
                out += self._frame_body(f, IND)
                if other is not None:
                    out.append('`else')
                    out += self._frame_body(other, IND)
                out += ['`endif', '']
            else:
                cond = cond if cond.startswith('(') and cond.endswith(')') else f'({cond})'
                out += ['generate', f'{IND}if {cond} begin : {f.name}']
                out += self._frame_body(f, IND * 2)
                out.append(f'{IND}end')
                if other is not None:
                    out.append(f'{IND}else begin : {f.name}_else')
                    out += self._frame_body(other, IND * 2)
                    out.append(f'{IND}end')
                out += ['endgenerate', '']
        for f in (f for f in frames if f.kind == 'else'):
            if not any(i.kind == 'if' and i.name == f.name for i in frames):
                self.warnings.append(f'ELSE frame {f.name} has no IF frame of the same name')
        return out

    def _for_embedded(self) -> list[str]:
        """Embedded blocks inside a FOR frame: a generate loop over the frame range."""
        out = []
        for f in sorted((f for f in self.bd.frames if f.kind == 'for'), key=lambda f: f.number):
            blocks = [e for e in self.bd.embedded if self.bd.frame_of(e) is f]
            if not blocks:
                continue
            left, right = f.range()
            out += [f'genvar {f.name};', 'generate',
                    f'{IND}for ({f.name} = {right}; {f.name} <= {left}; {f.name} = {f.name} + 1) begin : {f.name}_gen']
            for eb in sorted(blocks, key=lambda e: e.number):
                out += self._embedded(eb, IND * 2)
            out += [f'{IND}end', 'endgenerate', '']
        return out

    def generate(self) -> str:
        """The whole module text, in the section order of the legacy tool's structural Verilog."""
        bd = self.bd
        lines = (bd.header or f'// Module {bd.library}.{bd.unit}.{bd.view}\n'
                 f'// Generated by {APP_NAME} {__version__} - {"SystemVerilog" if self.sv else "Verilog"}').split('\n')
        if bd.pre_module_directives.strip():
            lines += bd.pre_module_directives.rstrip('\n').split('\n')
        if bd.parameters:
            lines.append(f'module {bd.unit} #(')
            w = max(len(p.name) for p in bd.parameters)
            for i, p in enumerate(bd.parameters):
                lines.append(f'{IND}parameter {p.name:<{w}} = {p.value}' + (',' if i < len(bd.parameters) - 1 else ''))
            lines += [')', '( ']
        else:
            lines.append(f'module {bd.unit} ( ')
        lines.append(f'{IND}// Port Declarations')
        lines += self._ports()
        lines += [');', '']
        if bd.post_module_directives.strip():
            lines += bd.post_module_directives.rstrip('\n').split('\n')
        lines += ['// Internal Declarations', '', '', '// Local declarations']
        # user text of the Declarations block: "Pre User" before the signals, "Post User" after
        # them (Post User placement checked against legacy output; Pre User not yet seen)
        if bd.pre_user_declarations.strip():
            lines += bd.pre_user_declarations.strip('\n').split('\n')
        lines += ['', '// Internal signal declarations']
        lines += self._internal()
        lines += ['', '']
        if bd.post_user_declarations.strip():
            lines += bd.post_user_declarations.strip('\n').split('\n') + ['']
        lines += ['// Instances ']
        lines += self._instances()
        lines += self._if_frames()
        top_embedded = [eb for eb in sorted(bd.embedded, key=lambda e: e.number) if bd.frame_of(eb) is None]
        # consecutive embedded blocks follow each other without an empty line; one empty line
        # comes after the last one (as in the legacy tool)
        for eb in top_embedded:
            lines += self._embedded(eb)
        if top_embedded:
            lines.append('')
        lines += self._for_embedded()
        if not top_embedded:
            # The legacy tool (checked against its batch generation): with no embedded block outside
            # the frames, one more empty line comes before endmodule
            lines.append('')
        lines.append(f'endmodule // {bd.unit}')
        if bd.end_module_directives.strip():            # after the endmodule keyword (legacy user manual)
            lines += bd.end_module_directives.rstrip('\n').split('\n')
        lines += ['', '']
        return '\n'.join(lines)


def _bounds(text: str) -> str:
    """Bounds as the legacy tool writes them in declarations.

    The legacy tool rewrites only bounds in its own spaced style, "[ msb : lsb ]" -> "[msb:lsb]"; any other
    spelling is written as typed (both checked against the legacy tool: "[ N - 1 : 0 ]" becomes
    "[N - 1:0]" but "[ N - 1 : 0]" stays as it is).
    """
    m = re.fullmatch(r'\[ (\S.*?) : (\S.*?) \]', text)
    return f'[{m.group(1)}:{m.group(2)}]' if m else text


def _port_map(text: str) -> dict[str, str]:
    """".a(expr), .b(x[3])" from a port map frame -> {port: expression}."""
    out, i = {}, 0
    while True:
        i = text.find('.', i)
        if i < 0:
            return out
        j = text.find('(', i)
        if j < 0:
            return out
        name, depth, k = text[i + 1:j].strip(), 1, j + 1
        while k < len(text) and depth:
            depth += {'(': 1, ')': -1}.get(text[k], 0)
            k += 1
        if name.replace('_', '').replace('$', '').isalnum():
            expr = text[j + 1:k - 1].strip()
            if expr:
                out[name] = expr
        i = k


def generate_bd(bd: BlockDiagram, language: str | None = None) -> tuple[str, list[str]]:
    """Generate the module of a block diagram. Returns (HDL text, warnings)."""
    g = BdGenerator(bd, language)
    return g.generate(), g.warnings

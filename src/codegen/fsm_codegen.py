"""Generate Verilog-2005 or SystemVerilog from an FsmView.

Style follows the legacy tool's "3 always blocks / Case / Mixed assignment"
output (docs/codegen-reference.md): a next-state block, an output block for
combinatorial signals, a clocked block, then the clocked output assignments
and the user's concurrent statements.

Action semantics: a transition that ends in a state runs the source state's
exit actions, the destination's entry actions, then the transition's own
actions. Actions on transitions into a junction run before the junction's
decision. A state's in-actions run every cycle before its transitions are
evaluated. Each statement goes to the output block or the clocked block
depending on the signal it assigns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from model import FsmView, Machine, Signal, State
from version import APP_NAME, __version__
from .common import drivers, port_lines, sv_net_type, text_lines
from .encoding import encode

IND = '  '
# An empty line between two statements of the user's action text. It goes to the block of the
# statement after it and is written as an indentation-only line, as the legacy tool writes it.
BLANK = '\x00'
# Options > Verilog > Style > "Allow implicit event expression (@*) when appropriate": off by
# default in the legacy tool, which then writes explicit sensitivity lists (set from the preferences)
IMPLICIT_EVENT = False


# --------------------------------------------------------------------------
# Statement splitting and classification
# --------------------------------------------------------------------------
_OPEN_KW = {'begin', 'case', 'casex', 'casez', 'fork'}
_CLOSE_KW = {'end', 'endcase', 'join'}


def split_statements(text: str) -> list[str]:
    """Split HDL action text into top-level statements, keeping comments."""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            buf.append(text[i:j])
            i = j
            continue
        if text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            buf.append(text[i:j])
            i = j
            continue
        if c.isalpha() or c == '_':
            m = re.match(r'[A-Za-z_]\w*', text[i:])
            word = m.group()
            if word in _OPEN_KW:
                depth += 1
            elif word in _CLOSE_KW:
                depth -= 1
                if depth == 0:
                    buf.append(word)
                    i += len(word)
                    out.append(''.join(buf))
                    buf = []
                    continue
            buf.append(word)
            i += len(word)
            continue
        buf.append(c)
        i += 1
        if c == ';' and depth == 0:
            # keep a trailing comment on the same line with its statement
            m = re.match(r'[ \t]*//[^\n]*', text[i:])
            if m:
                buf.append(m.group())
                i += m.end()
            out.append(''.join(buf))
            buf = []
    tail = ''.join(buf)
    if tail.strip():
        if out and not _code(tail):
            # comments after the last statement stay with that statement (and its block), as the legacy tool
            out[-1] += tail.rstrip()
        else:
            out.append(tail)
    stmts: list[str] = []
    for s in out:
        # an empty line the user left between two statements is kept (the legacy tool keeps it too)
        blank_before = bool(stmts) and re.match(r'[ \t]*\n[ \t]*\n', s) is not None
        s = s.strip('\n')
        if not s.strip():
            continue
        if stmts and re.match(r'\s*else\b', s):
            stmts[-1] += '\n' + s
        else:
            if blank_before:
                stmts.append(BLANK)
            stmts.append(s)
    return [s if s == BLANK else _dedent(s) for s in stmts]


def _code(s: str) -> str:
    """The statement without its comments (empty for a comment-only statement)."""
    return re.sub(r'//[^\n]*|/\*.*?\*/', ' ', s, flags=re.S).strip()


def _dedent(s: str) -> str:
    """Remove the common indentation of the continuation lines of a multi-line statement (the
    first line is only left-stripped), so the generator can re-indent it at any level.
    """
    lines = s.split('\n')
    first = lines[0].lstrip()
    rest = lines[1:]
    pad = min((len(l) - len(l.lstrip()) for l in rest if l.strip()), default=0)
    return '\n'.join([first] + [l[pad:] for l in rest])


_ASSIGN_RE = re.compile(r'(\{[^}]*\}|[A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*(<=|=)(?!=)')


def assignment_target(stmt: str) -> tuple[str | None, str | None]:
    """Return (signal name, operator) of the first assignment in a statement."""
    s = re.sub(r'//[^\n]*|/\*.*?\*/', ' ', stmt, flags=re.S).strip()
    # skip "if (...)" / "case (...)" headers so comparisons are not taken for assignments
    while True:
        m = re.match(r'(if|else\s+if|case[xz]?|for|while)\s*\(', s)
        if not m:
            m2 = re.match(r'(else|begin)\b', s)
            if m2:
                s = s[m2.end():].lstrip()
                continue
            break
        depth, j = 0, m.end() - 1
        while j < len(s):
            if s[j] == '(':
                depth += 1
            elif s[j] == ')':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        s = s[j + 1:].lstrip()
    m = _ASSIGN_RE.search(s)
    if not m:
        return None, None
    lhs = m.group(1)
    if lhs.startswith('{'):
        ids = re.findall(r'[A-Za-z_]\w*', lhs)
        lhs = ids[0] if ids else None
    return lhs, m.group(3)


# --------------------------------------------------------------------------
# Decision tree built from the diagram
# --------------------------------------------------------------------------
@dataclass
class Leaf:
    """End of a decision path: go to state `dest` (None = stay) and run `actions`
    (source exit actions + destination entry actions + transition actions, already split).
    """
    dest: str | None                 # state name, None = stay in source state
    actions: list[str] = field(default_factory=list)


@dataclass
class Branch:
    """One branch of an if-chain or case: its condition / case label, the actions of the transition
    into a junction (`pre`, run before the junction decides) and what follows (`body`).
    """
    cond: str | None                 # if-condition / case label; None = else / default
    pre: list[str]                   # actions of the edge into a junction
    body: object                     # Leaf | Chain | Case


@dataclass
class Chain:
    """An if / else if / else chain: the transitions leaving one node, in priority order, with the
    unconditional one (if any) last as the else branch.
    """
    branches: list[Branch]


@dataclass
class Case:
    """A case statement built from a 'case' junction: `expr` is the case expression and each branch
    condition is a case item label (None = default).
    """
    expr: str
    branches: list[Branch]


class GenError(Exception):
    """The diagram cannot be generated (for example a loop through junctions)."""
    pass


class FsmGenerator:
    """Generates one module from an FsmView.

    How it works:
      1. __init__ decides, for each signal the machine drives, which always block assigns it:
         'out' (combinational output block) or 'clk' (clocked block). Clocked outputs are assigned
         through an internal copy named <signal><clocked_affix> (default _cld), registered outputs
         through <signal><registered_affix> (default _r).
      2. build() turns the transitions leaving every state into a decision tree
         (Chain / Case / Branch / Leaf), following junctions.
      3. render_ns() writes the next-state block from the trees; render_act() writes the
         actions of the tree that belong to one block ('out' or 'clk').
      4. generate() / machine() assemble header, ports, declarations, the three always blocks
         and the concurrent statements, in the order and layout the legacy tool uses.
    Warnings (unreachable states, unknown links, ...) are collected in self.warnings.
    """
    def __init__(self, view: FsmView, language: str | None = None):
        """Index the signals of `view` and decide the target block of each driven signal.
        `language` overrides view.language ('systemverilog' or 'verilog').
        """
        self.v = view
        self.sv = (language or view.language) == 'systemverilog'
        self.warnings: list[str] = []
        self.sig = {s.name: s for s in view.signals}
        ca, ra = view.clocked_affix, view.registered_affix
        self.clocked_out = [s for s in view.signals if s.mode == 'output' and s.scheme == 'clocked']
        self.registered_out = [s for s in view.signals if s.mode == 'output' and s.scheme == 'registered']
        self.block_of: dict[str, str] = {}
        for s in view.signals:
            if s.mode not in ('output', 'local', 'inout'):
                continue
            if s.scheme == 'comb':
                self.block_of[s.name] = 'out'
            elif s.scheme == 'clocked':
                self.block_of[s.name + ca if s.mode == 'output' else s.name] = 'clk'
            elif s.scheme == 'registered':
                self.block_of[s.name + ra] = 'out'

    # -- helpers ---------------------------------------------------------
    def block(self, stmt: str) -> str:
        """'out' or 'clk': the always block a statement belongs to. Signals with a scheme go to the
        block of their scheme; otherwise the operator decides (<= clocked, = combinational).
        """
        target, op = assignment_target(stmt)
        if target in self.block_of:
            return self.block_of[target]
        return 'clk' if op == '<=' else 'out'

    def only(self, stmts: list[str], blk: str) -> list[str]:
        """The statements that go to block blk ('out' or 'clk'). A BLANK line is kept when the
        statements on both sides of it go to that block."""
        out = []
        for k, s in enumerate(stmts):
            if s == BLANK:
                nxt = next((x for x in stmts[k + 1:] if x != BLANK), None)
                if out and out[-1] != BLANK and nxt is not None and self.block(nxt) == blk:
                    out.append(s)
            elif self.block(s) == blk and _code(s):
                # a comment-only action (no code at all) is not written, as the legacy tool
                out.append(s)
        return out

    def kw(self, verilog: str, sv: str) -> str:
        """Pick the Verilog or the SystemVerilog spelling of a keyword."""
        return sv if self.sv else verilog

    def _known_signals(self) -> set[str]:
        """Every signal name a block can read: ports and locals, the clocked / registered
        internal copies of outputs, and the state registers of every machine."""
        v = self.v
        names = {s.name for s in v.signals}
        names |= {s.name + v.clocked_affix for s in self.clocked_out}
        names |= {s.name + v.registered_affix for s in self.registered_out}
        multi = len(v.machines) > 1
        for m in v.machines:
            prefix = f'{m.name}_' if multi else ''
            names |= {prefix + m.current_state_name, prefix + m.next_state_name}
        return names

    _ASSIGNED_RE = re.compile(r'([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?<![<>!=])=(?!=)')
    _IDENT_RE = re.compile(r"(?<![\w$'`.])[A-Za-z_]\w*")

    def comb_head(self, body: list[str]) -> list[str]:
        """The first line(s) of a combinational always block whose statements are `body`.

        SystemVerilog: always_comb. Verilog: "always @ *" when Options > Verilog > Style >
        "Allow implicit event expression (@*)" is set (IMPLICIT_EVENT); otherwise, as the legacy tool
        generates by default, an explicit sensitivity list: every signal the block reads (a
        declared signal that appears in it and that the block does not assign), in alphabetical
        order, one per line:
            always @(
              a,
              b
            )
        """
        if self.sv:
            return ['always_comb']
        if IMPLICIT_EVENT:
            return ['always @ *']
        code = '\n'.join(body)
        code = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', ' ', code, flags=re.S)
        # read = named anywhere but as the target of an assignment: `tx = tx;` reads tx, and
        # The legacy tool lists it (checked with the legacy tool); the index of a target
        # (`a[i] = ...`) is read too
        rhs = self._ASSIGNED_RE.sub(lambda mo: ' ' * len(mo.group(1)) + mo.group(0)[len(mo.group(1)):], code)
        read = sorted(set(self._IDENT_RE.findall(rhs)) & self._known_signals())
        if not read:
            return ['always @ *']               # nothing read: no list to write
        return ['always @('] + [f'{IND}{n}, ' for n in read[:-1]] + [f'{IND}{read[-1]}', ')']

    # -- tree building ----------------------------------------------------
    def _target_state(self, m: Machine, node_id: str) -> State | None:
        """The state a transition really ends in: the state itself, or the target of a link
        (a warning when the link names an unknown state). None for junctions and points.
        """
        node = m.node(node_id)
        if isinstance(node, State):
            return node
        if node is not None and hasattr(node, 'target'):
            st = m.state_by_name(node.target)
            if st is None:
                self.warnings.append(f'Link to unknown state "{node.target}"')
            return st
        return None

    def build(self, m: Machine, src: State, node_id: str, seen: frozenset = frozenset()) -> Chain:
        """Decision tree of the transitions leaving `node_id` (a state, or a junction reached from
        state `src`). `seen` holds the junctions already on this path, to detect loops.
        """
        if node_id in seen:
            raise GenError(f'Loop through junctions at {node_id}')
        seen = seen | {node_id}
        node = m.node(node_id)
        is_case = getattr(node, 'kind', '') == 'case'
        branches = []
        for t in m.outgoing(node_id):
            body = self.edge_body(m, src, t, seen)
            pre = split_statements(t.actions) if not isinstance(body, Leaf) else []
            branches.append(Branch(t.cond.strip() or None, pre, body))
        # put unconditional branches last; keep only the first one
        cond = [b for b in branches if b.cond is not None]
        other = [b for b in branches if b.cond is None]
        if len(other) > 1:
            self.warnings.append(f'{src.name}: more than one unconditional transition, extra ones ignored')
        if other and branches and branches[-1].cond is not None:
            # The legacy tool refuses to generate such a machine ("This transition does not have a condition
            # but is not the lowest priority."); HDL Studio puts the unconditional one last
            self.warnings.append(f'{src.name}: a transition without condition is not the lowest priority '
                                 '(the legacy tool refuses to generate this)')
        branches = cond + other[:1]
        if not other:
            branches.append(Branch(None, [], Leaf(None)))
        if is_case:
            return Case(node.expr, branches)  # type: ignore[return-value]
        return Chain(branches)

    def edge_body(self, m: Machine, src: State, t, seen):
        """What follows transition t: a sub-tree when it goes into a junction, else a Leaf with the
        actions to run (exit of src, entry of the destination, then the transition's own actions).
        """
        dst_node = m.node(t.dst)
        if getattr(dst_node, 'kind', None) in ('if', 'case'):
            return self.build(m, src, t.dst, seen)
        st = self._target_state(m, t.dst)
        if st is None:
            self.warnings.append(f'{src.name}: transition {t.id} has no destination state')
            return Leaf(None)
        acts = split_statements(src.exit_actions) + split_statements(st.entry_actions) + split_statements(t.actions)
        return Leaf(st.name, acts)

    # -- rendering ----------------------------------------------------------
    @staticmethod
    def _indent(lines: list[str], level: int) -> list[str]:
        """Indent every line (and every sub-line of a multi-line entry) by `level` steps of IND.
        BLANK markers become indentation-only lines, as the legacy tool writes the user's empty lines.
        """
        out = []
        for l in lines:
            for sub in l.split('\n'):
                if sub == BLANK:
                    out.append(IND * level)     # the user's empty line: indentation only
                else:
                    # a generated empty line stays empty; an indentation-only line (a user's
                    # empty line indented by an inner block) gets this level too
                    out.append(IND * level + sub if sub else '')
        return out

    def render_ns(self, body, ns: str, src: str) -> list[str]:
        """Lines of the next-state logic for one tree: `<ns> = <state>;` assignments inside the
        if-chains / case statements of the diagram. `src` is the current state (the "stay" target).
        """
        if isinstance(body, Leaf):
            return [f'{ns} = {body.dest or src};']
        if isinstance(body, Case):
            lines = [f'case ({body.expr}) ']
            for b in body.branches:
                lines.append(f'{b.cond if b.cond is not None else "default"} : ')
                lines += self._indent(self.render_ns(b.body, ns, src), 1)
            lines.append('endcase')
            return lines
        brs = body.branches
        if len(brs) == 1 and brs[0].cond is None:
            return self.render_ns(brs[0].body, ns, src)
        lines = []
        for i, b in enumerate(brs):
            head = 'if' if i == 0 else 'else if'
            head = f'{head} ({b.cond})' if b.cond is not None else 'else'
            inner = self.render_ns(b.body, ns, src)
            if b.cond is None and i > 0 and isinstance(b.body, Chain) and inner and inner[0].startswith('if '):
                # the else branch leads to another decision: the legacy tool chains it as "else if (...)"
                lines += ['else ' + inner[0]] + inner[1:]
                continue
            wrap = isinstance(b.body, Chain) and i > 0
            if wrap:
                lines += [head + ' begin'] + self._indent(inner, 1) + ['end']
            else:
                lines += [head] + self._indent(inner, 1)
        return lines

    def render_act(self, body, blk: str) -> list[str] | None:
        """Lines for one block ('out' or 'clk'); None when nothing is assigned."""
        if isinstance(body, Leaf):
            stmts = self.only(body.actions, blk)
            return stmts or None
        rendered = []
        for b in body.branches:
            inner = self.render_act(b.body, blk)
            pre = self.only(b.pre, blk)
            if pre:
                inner = pre + (inner or [])
            rendered.append((b, inner))
        if all(r is None for _, r in rendered):
            return None
        if isinstance(body, Case):
            lines = [f'case ({body.expr}) ']
            for b, inner in rendered:
                label = b.cond if b.cond is not None else 'default'
                lines += self._item(f'{label} :', inner, 0)
            lines.append('endcase')
            return lines
        while rendered and rendered[-1][1] is None:
            rendered.pop()
        if len(rendered) == 1 and rendered[0][0].cond is None:
            return rendered[0][1]
        if (len(rendered) == 2 and rendered[0][1] is None and rendered[1][0].cond is None):
            # "if (c) <nothing> else <acts>"  ->  "if (!(c)) <acts>"; bare for one one-line statement
            inner = rendered[1][1]
            return self._stmt(f'if (!({rendered[0][0].cond}))', inner, single_ok=self._is_single_line(inner))
        lines = []
        for i, (b, inner) in enumerate(rendered):
            head = 'if' if i == 0 else 'else if'
            head = f'{head} ({b.cond})' if b.cond is not None else 'else'
            if b.cond is None and i > 0 and rendered[i - 1][0].cond is not None:
                head = 'else'
            last = i == len(rendered) - 1
            if (head == 'else' and isinstance(b.body, Chain) and not self.only(b.pre, blk)
                    and inner and inner[0].startswith('if ')):
                # the else branch leads to another decision: the legacy tool chains it as "else if (...)"
                lines += ['else ' + inner[0]] + inner[1:]
                continue
            if isinstance(b.body, Leaf):
                # The branch body is the user's action text: the legacy tool writes it bare only when it is
                # one single-line statement; an if/case/several lines go inside begin ... end.
                single_ok = self._is_single_line(inner or [])
            else:
                # The body comes from a junction (a nested decision of the diagram). Observed in
                # legacy output, the inner "if" is written bare when
                #   - it is the last branch and the inner if ends with its own else, or has only
                #     one-line statements (no begin ... end inside);
                #   - it is the first branch and the inner if ends with its own else;
                # and inside begin ... end otherwise.
                ends_else = self._ends_with_else(inner)
                # "simple": the inner if has one-line statements only, or several branches;
                # what gets begin ... end is a lone "if (c) begin ... end" (one branch, no else)
                top = [l for l in '\n'.join(inner or []).split('\n') if l and not l.startswith(' ')]
                branches = sum(1 for l in top if l.startswith(('if', 'else')))
                simple = branches > 1 or not any(l.rstrip().endswith('begin') for l in top)
                single_ok = (not self._is_if(inner) or (last and (ends_else or simple))
                             or (i == 0 and ends_else))
            lines += self._stmt(head, inner, single_ok=single_ok)
        return lines

    @staticmethod
    def _is_if(lines: list[str] | None) -> bool:
        """True when the lines start with an if statement."""
        return bool(lines) and lines[0].lstrip().startswith('if')

    @staticmethod
    def _ends_with_else(lines: list[str] | None) -> bool:
        """True for an if chain whose last branch is a plain else (no else can bind to it)."""
        if not lines or not lines[0].startswith('if'):
            return False
        top = [l for l in '\n'.join(lines).split('\n') if l and not l.startswith(' ')]
        if top[0].startswith('if (!(') and not any(l.startswith('else') for l in top):
            return True     # "if (!(c)) acts" stands for "if (c) <nothing> else acts": complete
        return any(l.rstrip() in ('else', 'else begin') for l in top)

    def _stmt(self, head: str, inner: list[str] | None, single_ok: bool) -> list[str]:
        """`head` followed by its body: bare (indented on the next line) when `single_ok` and the body
        is one line or one if/case construct, else wrapped in begin ... end.
        """
        if inner and single_ok and (self._is_single_line(inner) or self._is_single_construct(inner)):
            return [head] + self._indent(inner, 1)
        return [head.rstrip() + ' begin'] + self._indent(inner or [], 1) + ['end']

    @staticmethod
    def _is_single_line(lines: list[str]) -> bool:
        """True for exactly one statement on one line."""
        return len(lines) == 1 and '\n' not in lines[0]

    @staticmethod
    def _is_single_construct(lines: list[str]) -> bool:
        """True when the lines form one statement: a case...endcase or an if/else chain."""
        if not lines:
            return False
        if lines[0].startswith('case') and lines[-1] == 'endcase':
            return True
        if not lines[0].startswith('if'):
            return False
        top = [l for l in '\n'.join(lines).split('\n') if l and not l.startswith(' ')]
        # a second top-level "if" (not preceded by "else") starts another statement
        return (all(l.startswith(('if', 'else', 'end')) for l in top) and not top[-1].startswith('endcase')
                and not any(l.startswith('if') for l in top[1:]))

    def _item(self, label: str, inner: list[str] | None, level: int, always_block: bool = False) -> list[str]:
        """A case item `label` with its body: bare when the body is one statement, else begin ... end
        (always begin ... end when `always_block`, as the legacy tool writes the state items).
        """
        if inner and not always_block and (self._is_single_line(inner) or self._is_single_construct(inner)):
            return [label + ' '] + self._indent(inner, level + 1)
        return [label + ' begin'] + self._indent(inner or [], level + 1) + [IND * level + 'end']

    # -- declarations ---------------------------------------------------------
    def _procedural(self) -> set[str]:
        """Signals assigned inside always blocks (FSM actions or user procedural code)."""
        if not hasattr(self, '_proc'):
            v = self.v
            proc = set(self.block_of)
            proc |= {s.name for s in v.signals if s.mode in ('output', 'local', 'inout') and s.scheme != 'none'}
            for m in v.machines:
                for t in m.transitions:
                    proc |= {assignment_target(x)[0] for x in split_statements(t.actions)}
                for st in m.states:
                    for txt in (st.entry_actions, st.in_actions, st.exit_actions):
                        proc |= {assignment_target(x)[0] for x in split_statements(txt)}
            user = '\n'.join((v.concurrent_statements, v.state_register_statements, v.global_pre_actions,
                              v.global_post_actions))
            proc |= drivers(user)[1]
            self._proc = proc - {None}
        return self._proc

    def _type(self, s: Signal, in_port: bool) -> str:
        """Declared type of a signal: SystemVerilog logic / wire by the procedural rule; Verilog wire
        for input ports, reg for signals the machine assigns, else the type typed in the table.
        """
        if self.sv:
            return sv_net_type(s.name, self._procedural())
        if in_port and s.mode in ('input', 'inout'):
            return 'wire'
        if s.scheme in ('comb', 'clocked', 'registered') or s.mode == 'local':
            return 'reg'
        return s.type or 'wire'

    def _port_lines(self) -> list[str]:
        """The ANSI port list: inputs, then inouts, then outputs, each group by name (as the legacy tool)."""
        order = {'input': 0, 'inout': 1, 'output': 2}
        ports = sorted((s for s in self.v.signals if s.mode in order), key=lambda s: (order[s.mode], s.name))
        return port_lines([(s.mode, self._type(s, True) + (' signed' if s.signed else ''), s.bounds, s.name,
                            s.comment) for s in ports])

    def _decl_lines(self, sigs: list[tuple[str, str, str]]) -> list[str]:
        """sigs: (type+bounds, name, comment) aligned into declarations."""
        if not sigs:
            return []
        w = max(len(t) for t, _, _ in sigs) + 1
        wn = max(len(n) for _, n, _ in sigs) + 2
        out = []
        for t, n, c in sigs:
            line = f'{t:<{w}}{n};'
            if c:
                line = f'{line:<{w + wn}}// {c}'
            out.append(line)
        return out

    def _sig_type(self, s: Signal, name: str | None = None) -> str:
        """Type and bounds of an internal declaration ('reg [7:0]' / 'logic [7:0]')."""
        base = sv_net_type(name or s.name, self._procedural()) if self.sv else 'reg'
        return f'{base} {s.bounds}'.strip()

    # -- whole module -----------------------------------------------------------
    def generate(self) -> str:
        """The whole module text (header, parameters, ports, declarations, every machine, clocked output
        assignments, concurrent statements, endmodule and end-module directives).
        """
        v = self.v
        lines: list[str] = []
        hdr = v.header or (f'// Module {v.library}.{v.unit}.{v.view}\n'
                           f'// Generated by {APP_NAME} {__version__} - '
                           f'{"SystemVerilog" if self.sv else "Verilog"}')
        lines += hdr.rstrip('\n').split('\n')
        if v.pre_module_directives.strip():
            lines += v.pre_module_directives.rstrip('\n').split('\n')
        if v.parameters:
            lines.append(f'module {v.unit} #(')
            w = max(len(p.name) for p in v.parameters)
            for i, p in enumerate(v.parameters):
                sep = ',' if i < len(v.parameters) - 1 else ''
                lines.append(f'{IND}parameter {p.name:<{w}} = {p.value}{sep}')
            lines.append(')')
            lines.append('( ')
        else:
            lines.append(f'module {v.unit} ( ')
        lines.append(f'{IND}// Port Declarations')
        lines += self._port_lines()
        lines.append(');')
        lines.append('')
        if v.post_module_directives.strip():
            lines += v.post_module_directives.rstrip('\n').split('\n')
        lines.append('// Internal Declarations')
        lines.append('')
        pre_reg = [(self._sig_type(s, s.name + v.clocked_affix), s.name + v.clocked_affix, '') for s in sorted(self.clocked_out, key=lambda s: s.name)]
        pre_reg += [(self._sig_type(s, s.name + v.registered_affix), s.name + v.registered_affix, '') for s in sorted(self.registered_out, key=lambda s: s.name)]
        if pre_reg:
            lines.append('')
            lines.append('// Declare any pre-registered internal signals')
            lines += self._decl_lines(pre_reg)
        locals_ = sorted((s for s in v.signals if s.mode == 'local'), key=lambda s: s.name)
        if locals_:
            lines.append('')
            lines.append('// Module Declarations')
            lines += self._decl_lines([(self._sig_type(s), s.name, s.comment) for s in locals_])
        multi = len(v.machines) > 1
        for m in v.machines:
            lines += self.machine(m, prefix=f'{m.name}_' if multi else '')
        lines.append('')
        if self.clocked_out or v.concurrent_statements.strip():
            # The legacy tool leaves this comment out when there are no concurrent statements
            lines.append('// Concurrent Statements')
        if self.clocked_out:
            lines.append('// Clocked output assignments')
            assigns = [f'{s.name} = {s.name}{v.clocked_affix};' for s in sorted(self.clocked_out, key=lambda s: s.name)]
            lines += self.comb_head(assigns)
            lines.append('begin : clocked_output_proc')
            lines += [IND + a for a in assigns]
            lines.append('end')
        if v.concurrent_statements.strip():
            lines += v.concurrent_statements.rstrip('\n').split('\n')
        lines.append(f'endmodule // {v.unit}')
        if v.end_module_directives.strip():             # after the endmodule keyword (legacy user manual)
            lines += v.end_module_directives.rstrip('\n').split('\n')
        lines.append('')
        if self.sv:
            self.check_single_driver(v)
        return '\n'.join(lines)

    def check_single_driver(self, v: FsmView) -> None:
        """SystemVerilog only: warn about signals assigned both with "=" and "<=" (they would be driven
        by always_comb and always_ff at the same time, which is illegal).
        """
        targets_out, targets_clk = set(), set()
        for m in v.machines:
            for t in m.transitions:
                for s in split_statements(t.actions):
                    (targets_out if self.block(s) == 'out' else targets_clk).add(assignment_target(s)[0])
            for st in m.states:
                for txt in (st.entry_actions, st.in_actions, st.exit_actions):
                    for s in split_statements(txt):
                        (targets_out if self.block(s) == 'out' else targets_clk).add(assignment_target(s)[0])
        both = sorted(n for n in targets_out & targets_clk if n)
        for n in both:
            self.warnings.append(f'SystemVerilog: "{n}" is assigned in both always_comb and always_ff '
                                 f'(mixed "=" and "<="); fix the actions or the signal scheme')

    def machine(self, m: Machine, prefix: str) -> list[str]:
        """Lines of one state machine: state encoding declarations, next-state block, output block and
        clocked block (reset values, state register, enable, interrupts, recovery state).
        `prefix` is '<machine name>_' when the view holds several machines, so their state variables
        do not clash.
        """
        v = self.v
        cs, ns = prefix + m.current_state_name, prefix + m.next_state_name
        names = [s.name for s in m.states]
        if not names:
            self.warnings.append(f'Machine {m.name} has no states')
            return []
        width, codes = encode(names, m.encoding, {s.name: s.encoding for s in m.states})
        rng = f'[{width - 1}:0]'
        decl = m.state_decl if (self.sv or m.state_decl != 'enum') else 'parameter'
        if m.state_decl == 'enum' and not self.sv:
            self.warnings.append('State declaration "enum" needs SystemVerilog; using parameter for Verilog')
        lines = ['', '// State encoding']
        w = max(len(n) for n in names)
        if decl == 'enum':
            tname = f'{m.name}_state_t'
            lines.append(f'typedef enum logic {rng} {{')
            for i, n in enumerate(names):
                lines.append(f'{IND}{n:<{w}} = {codes[n]}' + (',' if i < len(names) - 1 else ''))
            lines.append(f'}} {tname};')
            lines.append('')
            lines.append(f'{tname} {cs}, {ns};')
        else:
            kw = decl if not (self.sv and decl == 'localparam') else f'localparam logic {rng}'
            lines.append(f'{kw} ')
            for i, n in enumerate(names):
                lines.append(f'{IND * 5}{n:<{w}} = {codes[n]}' + (',' if i < len(names) - 1 else ';'))
            lines.append('')
            lines.append(f'{"logic" if self.sv else "reg"} {rng} {cs}, {ns};')

        trees = {st.name: self.build(m, st, st.id) for st in m.states}
        interrupts = []
        for p in m.points_of('interrupt'):
            for t in m.outgoing(p.id):
                dst = self._target_state(m, t.dst)
                if dst is not None and t.cond.strip():
                    interrupts.append((t.cond.strip(), dst.name, split_statements(t.actions)))
        recovery = None
        rp = m.point('recovery')
        if rp is not None:
            out = m.outgoing(rp.id)
            if out:
                dst = self._target_state(m, out[0].dst)
                recovery = (dst.name if dst else None, split_statements(out[0].actions))
        reset_dest = None
        rst = m.point('reset')
        if rst is not None and m.outgoing(rst.id):
            d = self._target_state(m, m.outgoing(rst.id)[0].dst)
            reset_dest = d.name if d else None

        # ---- next state block
        title = f'machine {m.name}'
        body = [f'case ({cs}) ']
        for st in m.states:
            inner = self.render_ns(trees[st.name], ns, st.name)
            body += self._item(f'{IND}{st.name}:', inner, 1, always_block=True)
        if recovery and recovery[0]:
            body.append(f'{IND}default: ')
            body.append(f'{IND * 2}{ns} = {recovery[0]};')
        else:
            # no recovery state: the legacy tool writes no default branch, two empty lines in its place
            body += ['', '']
        body.append('endcase')
        body = self._wrap_interrupts(interrupts, body, lambda acts, dst: [f'{ns} = {dst};'])
        lines += ['', '//' + '-' * 65, f'// Next State Block for {title}', '//' + '-' * 65]
        lines += self.comb_head(body) + ['begin : ' + prefix + 'next_state_block_proc']
        lines += self._indent(body, 1)
        lines.append('end // Next State Block')

        # ---- output block
        # default values: outputs first, then the internal (local) signals under their own
        # comment, as the legacy tool writes them
        defaults = sorted((s for s in v.signals if s.mode == 'output' and s.scheme == 'comb' and s.default),
                          key=lambda s: s.name)
        defaults_r = sorted((s for s in self.registered_out if s.default), key=lambda s: s.name)
        defaults_i = sorted((s for s in v.signals if s.mode == 'local' and s.scheme == 'comb' and s.default),
                            key=lambda s: s.name)
        out_lines = []
        if defaults or defaults_r:
            out_lines.append('// Default Assignment')
            out_lines += [f'{s.name} = {s.default};' for s in defaults]
            out_lines += [f'{s.name}{v.registered_affix} = {s.default};' for s in defaults_r]
        if defaults_i:
            out_lines.append('// Default Assignment To Internals')
            out_lines += [f'{s.name} = {s.default};' for s in defaults_i]
        n_def = len(out_lines)                  # the default assignment lines written above
        case_out = self._action_case(m, cs, trees, recovery, 'out')
        pre_out = self.only(split_statements(v.global_pre_actions), 'out')
        if pre_out:
            # The legacy tool: a comment line above the global pre actions, an empty line after
            # them when the action case follows, no empty line after the default assignments
            out_lines += ['// Global Actions'] + pre_out + ([''] if case_out else [])
        # as in the clocked block: the actions (and the interrupts around them) only when some
        # statement goes to the output block
        if case_out or any(self.only(acts, 'out') for _, _, acts in interrupts):
            out_lines += self._wrap_interrupts(interrupts, case_out, lambda acts, dst: self.only(acts, 'out'),
                                               action_block=True)
        out_lines += self.only(split_statements(v.global_post_actions), 'out')
        if n_def and len(out_lines) > n_def and out_lines[n_def] not in ('', '// Global Actions'):
            out_lines.insert(n_def, '')         # The legacy tool: an empty line after the default assignments
        if out_lines:                           # The legacy tool leaves out an output block with nothing in it
            lines += ['', '//' + '-' * 65, f'// Output Block for {title}', '//' + '-' * 65]
            lines += self.comb_head(out_lines) + ['begin : ' + prefix + 'output_block_proc']
            lines += self._indent(out_lines, 1)
            lines.append('end // Output Block')

        # ---- clocked block
        clk = next((s for s in v.signals if s.category == 'clock'), None)
        rst_sig = next((s for s in v.signals if s.category == 'reset'), None)
        if clk is None:
            self.warnings.append('No clock signal: set Category = clock in the Signals table')
            clk_expr = 'posedge clk'
        else:
            clk_expr = clk.expression or f'posedge {clk.name}'
        sens = [clk_expr]
        rst_cond = None
        if rst_sig is not None:
            rst_cond = rst_sig.expression or f'!{rst_sig.name}'
            neg = rst_cond.lstrip().startswith(('!', '~'))
            sens.append(f'{"negedge" if neg else "posedge"} {rst_sig.name}')
        sep = ' or ' if self.sv else ', '
        if self.sv:
            lines += ['', '//' + '-' * 65, f'// Clocked Block for {title}', '//' + '-' * 65,
                      f'always_ff @({sep.join(sens)})']
        else:
            lines += ['', '//' + '-' * 65, f'// Clocked Block for {title}', '//' + '-' * 65,
                      'always @(', ', \n'.join(f'{IND}{s}' for s in sens) + '\n) ']
        lines.append('begin : ' + prefix + 'clocked_block_proc')
        run = []
        if v.state_register_statements.strip():
            run += split_statements(v.state_register_statements)
        else:
            run.append(f'{cs} <= {ns};')
        run += [f'{s.name} <= {s.name}{v.registered_affix};' for s in sorted(self.registered_out, key=lambda s: s.name)]
        # clocked outputs with a default value: the legacy tool sets their internal (_cld) signal to it at
        # the start of every clock (checked with the legacy tool)
        cld_defaults = sorted((s for s in self.clocked_out if s.default), key=lambda s: s.name)
        if cld_defaults:
            run += ['// Default Assignment To Internals'] + \
                [f'{s.name}{v.clocked_affix} <= {s.default};' for s in cld_defaults]
        pre_clk = self.only(split_statements(v.global_pre_actions), 'clk')
        if pre_clk:
            run += ['// Global Internal Actions'] + pre_clk     # The legacy tool's comment line above them
        case_clk = self._action_case(m, cs, trees, recovery, 'clk')
        # The legacy tool writes the clocked actions (and the interrupts around them) only when some
        # statement goes to the clocked block
        if case_clk or any(self.only(acts, 'clk') for _, _, acts in interrupts):
            if not interrupts:
                run.append('')
            run += self._wrap_interrupts(interrupts, case_clk, lambda acts, dst: self.only(acts, 'clk'),
                                         action_block=True)
        run += self.only(split_statements(v.global_post_actions), 'clk')
        enable = next((s for s in v.signals if s.category == 'enable'), None)
        if enable is not None:
            # a machine with an enable signal only runs while it is set (as the legacy tool writes it)
            run = [f'if ({enable.expression or enable.name}) begin'] + self._indent(run, 1) + ['end']
        if rst_cond is not None:
            values = [f'{s.name}{v.clocked_affix} <= {s.reset};' for s in sorted(self.clocked_out, key=lambda s: s.name) if s.reset]
            values += [f'{s.name} <= {s.reset};' for s in sorted(self.registered_out, key=lambda s: s.name) if s.reset]
            values += [f'{s.name} <= {s.reset};' for s in sorted(v.signals, key=lambda s: s.name)
                       if s.mode == 'local' and s.scheme == 'clocked' and s.reset]
            # the "// Reset Values" comment only when there are reset values (as the legacy tool)
            resets = [f'{cs} <= {reset_dest or names[0]};'] + (['// Reset Values'] + values if values else [])
            if reset_dest is None:
                self.warnings.append('No reset point: reset goes to the first state')
            blk = [f'if ({rst_cond}) begin'] + self._indent(resets, 1) + ['end', 'else ', 'begin'] + \
                self._indent(run, 1) + ['end']
        else:
            blk = run
        lines += self._indent(blk, 1)
        lines.append('end // Clocked Block')
        return lines

    def _action_case(self, m: Machine, cs: str, trees, recovery, blk: str) -> list[str]:
        """The "Combined Actions" case statement of block `blk` ('out' or 'clk'): for every state its
        in-actions and the actions of its transitions that go to this block. Returns [] when the
        block has nothing to do (the legacy tool then leaves the case out).
        """
        # The comment above the action case. With next-state clocking the legacy tool writes no comment in
        # the output block (an indentation-only line) and a different one in the clocked block.
        title = '// Combined Actions'
        if m.next_state_clocking:
            title = BLANK if blk == 'out' else '// Transition Actions for internal signals only'
        lines = [title, f'case ({cs}) ']
        empty = []
        for st in m.states:
            inner = self.only(split_statements(st.in_actions), blk)
            r = self.render_act(trees[st.name], blk)
            if r:
                inner += r
            if inner:
                lines += self._item(f'{IND}{st.name}:', inner, 1, always_block=True)
            else:
                empty.append(st.name)
        rec = self.only(recovery[1], blk) if recovery else []
        if empty and len(lines) > 2 and (rec or recovery is None):
            # The legacy tool lists the states without actions together, with an empty begin ... end: when
            # the recovery branch has actions here (they must not fall into it), and when the
            # machine has no recovery point at all (checked against legacy output)
            lines.append(IND + (',\n' + IND).join(empty) + ': begin')
            lines.append(IND + 'end')
        # The legacy tool always writes the default branch as begin ... end, even for one statement
        lines += self._item(f'{IND}default:', rec, 1, always_block=True) if rec else []
        lines.append('endcase')
        if len(lines) == 3 and not rec:
            return []
        return lines

    def _wrap_interrupts(self, interrupts, body: list[str], action_of, action_block: bool = False) -> list[str]:
        """Put `body` inside the interrupt checks: `if (int0) ... else if (int1) ... else begin body end`.
        `action_of(acts, dst)` gives the statements of one interrupt (the next-state assignment or its
        actions); `action_block` selects the layout of the output / clocked blocks.
        """
        if not interrupts:
            return body
        out = []
        for i, (cond, dst, acts) in enumerate(interrupts):
            head = 'if' if i == 0 else 'else if'
            inner = action_of(acts, dst)
            out += self._stmt(f'{head} ({cond}) ' if action_block else f'{head} ({cond})', inner,
                              single_ok=action_block)
        if action_block:
            out = ['', '// Interrupts'] + out
        out += ['else begin'] + ([''] if action_block else []) + self._indent(body, 1) + ['end']
        return out


def generate(view: FsmView, language: str | None = None) -> tuple[str, list[str]]:
    """Generate the module of an FsmView. Hierarchical states are flattened first (the view itself is
    not changed). Returns (HDL text, warnings).
    """
    from .hierarchy import flatten
    if any(s.hier for m in view.machines for s in m.states):
        # hierarchical states: generate from the machines with their paths resolved
        import copy
        view = copy.copy(view)
        view.machines = [flatten(m) for m in view.machines]
    g = FsmGenerator(view, language)
    text = g.generate()
    return text, g.warnings

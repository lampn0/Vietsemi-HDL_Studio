"""Data model for a state machine view (one design unit view with one or
more concurrent machines). Saved as JSON; graphics positions are kept
next to the logic so the diagram reopens as it was drawn."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

MODES = ('input', 'output', 'inout', 'local')
SCHEMES = ('comb', 'registered', 'clocked', 'none')
CATEGORIES = ('data', 'clock', 'reset', 'enable')
LANGUAGES = ('systemverilog', 'verilog')
STATE_DECLS = ('parameter', 'localparam', 'enum')
ENCODINGS = ('sequential', 'gray', 'onehot', 'johnson', 'manual')
POINT_KINDS = ('reset', 'clock', 'interrupt', 'recovery', 'enable', 'entry', 'exit')


@dataclass
class Signal:
    """A port or internal signal of a state machine view (one row of the Signals Table).

    mode is one of MODES; inputs and outputs become module ports, 'local' signals are internal.
    For outputs / locals, scheme says how the FSM drives it: 'comb' (combinational, assigned in the
    output block with `default`), 'registered' / 'clocked' (a register, with `reset` value), or
    'none' (driven elsewhere, e.g. by a concurrent statement).
    """
    name: str
    mode: str = 'input'              # MODES
    type: str = 'wire'
    bounds: str = ''                 # e.g. "[7:0]"
    signed: bool = False
    group: str = ''
    category: str = 'data'           # CATEGORIES
    expression: str = ''             # clock/reset/enable expression, e.g. "posedge clk"
    scheme: str = 'none'             # SCHEMES, outputs/locals only
    default: str = ''
    reset: str = ''
    comment: str = ''
    value: str = ''                  # initial value of a net declaration: wire x = <value>;
    array: str = ''                  # unpacked dimension, e.g. [0:3]
    delay: str = ''
    expansion: str = ''              # Verilog net expansion: '' | scalared | vectored
    strength: str = ''               # trireg charge strength: '' | small | medium | large
    sync: bool = False               # reset: synchronous (tested in the clocked block, not in its sensitivity)
    detail: str = ''                 # clock / reset / enable written by hand: 'specify' (or 'gated' clock)
    @property
    def is_driven(self) -> bool:
        """True when the state machine itself assigns this signal (an output or local with a scheme)."""
        return self.mode in ('output', 'local') and self.scheme != 'none'


# The Category column of the Signals Table, as the legacy tool lists it, and the code its files keep
# for each (the codes 1, 2, 8, 9, 12, 13, 14 and 15 are read from legacy files and the HDL the
# legacy tool generated from them; the others follow the same order).
CATEGORY_LABELS = ['Clock (Falling)', 'Clock (Gated)', 'Clock (Rising)', 'Clock (Specify)', 'Data',
                   'Enable (High)', 'Enable (Low)', 'Enable (Specify)', 'Reset (Async High)', 'Reset (Async Low)',
                   'Reset (Async Specify)', 'Reset (Sync High)', 'Reset (Sync Low)', 'Reset (Sync Specify)']
CATEGORY_CODES = {'Clock (Rising)': 1, 'Clock (Falling)': 2, 'Clock (Gated)': 3, 'Clock (Specify)': 4,
                  'Reset (Async Low)': 8, 'Reset (Async High)': 9, 'Reset (Async Specify)': 10,
                  'Reset (Sync Low)': 11, 'Reset (Sync High)': 12, 'Reset (Sync Specify)': 13,
                  'Enable (Low)': 14, 'Enable (High)': 15, 'Enable (Specify)': 16}


def _active_low(expr: str) -> bool:
    """Whether a reset / enable expression is active low ("!rst", "~rst", "rst = '0'", "rst == 0")."""
    e = expr.replace(' ', '')
    return e.startswith(('!', '~', 'not')) or e.endswith(("='0'", '==0', "==1'b0"))


def category_label(s: 'Signal') -> str:
    """The Category of a signal as the legacy Signals Table shows it: Data, Clock (Rising), Reset (Sync
    Low), ..."""
    expr = (s.expression or '').strip()
    if s.category == 'clock':
        if s.detail in ('gated', 'specify'):
            return f'Clock ({s.detail.capitalize()})'
        return 'Clock (Falling)' if expr.startswith('negedge') or expr.replace(' ', '').endswith("='0'")             else 'Clock (Rising)'
    if s.category == 'reset':
        mode = 'Sync' if s.sync else 'Async'
        level = 'Specify' if s.detail == 'specify' else 'Low' if _active_low(expr) else 'High'
        return f'Reset ({mode} {level})'
    if s.category == 'enable':
        return 'Enable (Specify)' if s.detail == 'specify' else             'Enable (Low)' if _active_low(expr) else 'Enable (High)'
    return 'Data'


def set_category_label(s: 'Signal', label: str, keep_expression: bool = False) -> None:
    """Give a signal the Category `label` (one of CATEGORY_LABELS): its category, sync / detail and
    the matching expression ("posedge clk", "!rst_n", ...). A Specify category keeps an expression
    of the same category (it is written by hand); `keep_expression` keeps it in any case (a file
    read back)."""
    t = label.lower()
    was = s.category
    s.sync, s.detail = False, ''
    if t.startswith('clock'):
        s.category = 'clock'
        if 'gated' in t or 'specify' in t:
            s.detail = 'gated' if 'gated' in t else 'specify'
            expr = s.expression if was == 'clock' and s.expression else f'posedge {s.name}'
        else:
            expr = f'{"negedge" if "falling" in t else "posedge"} {s.name}'
    elif t.startswith(('reset', 'enable')):
        s.category = 'reset' if t.startswith('reset') else 'enable'
        s.sync = 'sync' in t and 'async' not in t
        if 'specify' in t:
            s.detail = 'specify'
            expr = s.expression if was == s.category and s.expression else s.name
        else:
            expr = ('!' if 'low' in t else '') + s.name
    else:
        s.category, expr = 'data', ''
    if not keep_expression:
        s.expression = expr


@dataclass
class Parameter:
    """A module parameter of the view (`parameter NAME = value`)."""
    name: str
    value: str = ''
    type: str = ''
    group: str = ''
    comment: str = ''


@dataclass
class State:
    """A state of the diagram: its name, position (scene units, centre of the circle) and the
    entry / in / exit actions the legacy tool shows in the state's action box.
    """
    id: str
    name: str
    x: float = 0.0
    y: float = 0.0
    entry_actions: str = ''          # run on every transition into the state
    in_actions: str = ''             # run every clock cycle while in the state
    exit_actions: str = ''           # run on every transition out of the state
    encoding: str = ''               # manual encoding value
    actions_x: float | None = None   # top-left of the action box on the diagram (None = automatic)
    actions_y: float | None = None
    radius: float | None = None      # circle radius saved by the legacy tool (None = HDL Studio's default)
    is_wait: bool = False            # a wait state (the legacy tool: circle in an octagon)
    wait: str = ''                   # its wait text, e.g. "wait 2"
    hier: bool = False               # a hierarchical state (legacy CompositeState): its states are inside
    # geometry read from a legacy file, drawn as it is (scene units, offsets from the action
    # block's top-left): act_size [w, h], tline / bline (y of the lines between the entry,
    # state and exit actions; None = hidden), entry / in / exit [x, y] of each text
    orig: dict = field(default_factory=dict)
    parent: str = ''                 # id of the hierarchical state this one is inside ('' = top level)


@dataclass
class Junction:
    """A decision point between transitions: 'if' (conditions on the outgoing transitions) or 'case'
    (`expr` is the case expression, the outgoing conditions are its items).
    """
    id: str
    kind: str = 'if'                 # 'if' | 'case'
    expr: str = ''                   # case expression
    symbol: str = ''                 # text drawn in the diamond (the legacy tool: "&" when new, "if" ...)
    parent: str = ''                 # id of the hierarchical state it is inside ('' = top level)
    x: float = 0.0
    y: float = 0.0
    # geometry read from a legacy file (scene units, relative to the node's centre): 'shape'
    # [x0, y0, x1, y1] and its texts by key, each [x0, y0, x1, y1, justify, baseline]
    orig: dict = field(default_factory=dict)


@dataclass
class Link:
    """A link to another state by name (the legacy tool "Link"): a transition into it goes to the target state."""
    id: str
    target: str = ''                 # state name
    x: float = 0.0
    y: float = 0.0
    parent: str = ''                 # id of the hierarchical state it is inside ('' = top level)
    # geometry read from a legacy file (scene units, relative to the node's centre): 'shape'
    # [x0, y0, x1, y1] and its texts by key, each [x0, y0, x1, y1, justify, baseline]
    orig: dict = field(default_factory=dict)


@dataclass
class Point:
    """A special node: reset / clock / interrupt / recovery / enable point of the machine, or the
    entry / exit point of a hierarchical state.
    """
    id: str
    kind: str                        # POINT_KINDS
    x: float = 0.0
    y: float = 0.0
    parent: str = ''                 # entry / exit points: the hierarchical state they belong to
    # geometry read from a legacy file (scene units, relative to the node's centre): 'shape'
    # [x0, y0, x1, y1] and its texts by key, each [x0, y0, x1, y1, justify, baseline]
    orig: dict = field(default_factory=dict)


@dataclass
class Transition:
    """An arrow from node `src` to node `dst` (ids of states, junctions, links or points), with its
    condition, actions, priority among the transitions leaving `src`, and its drawing (bend points,
    attach angles, position of the condition/action box).
    """
    id: str
    src: str                         # node id
    dst: str                         # node id
    cond: str = ''                   # empty = unconditional / "others"
    actions: str = ''
    priority: int = 1
    points: list[list[float]] = field(default_factory=list)  # bend points between the two nodes
    start_angle: float | None = None  # where the line leaves / enters the node outline (radians)
    end_angle: float | None = None
    label_x: float | None = None      # top-left of the condition/action box (None = automatic)
    label_y: float | None = None
    prio_at: float | None = None      # where the priority number sits, as a fraction of the line length
    # geometry read from a legacy file, drawn as it is (scene units, offsets from the box's
    # top-left): box_size [w, h], cond / acts [x, y] of the texts, line (y of the line between
    # them, None = hidden), prio_shown (the priority circle visible)
    orig: dict = field(default_factory=dict)


@dataclass
class Comment:
    """Free comment text on a state diagram (Add > Comment Text); (x, y) is its top-left corner."""
    id: str
    text: str = ''
    x: float = 0.0
    y: float = 0.0


@dataclass
class Panel:
    """A named rectangle of a diagram (Add > Panel): an area to view (View > View Panel) or print on
    its own; (x, y) is its top-left corner. Used by state and block diagrams."""
    id: str
    name: str = 'Panel0'
    x: float = 0.0
    y: float = 0.0
    w: float = 600.0
    h: float = 400.0


@dataclass
class Machine:
    """One concurrent state machine of a view: its nodes and transitions, the names of the
    current / next state variables and the state encoding.
    """
    name: str = 'fsm'
    states: list[State] = field(default_factory=list)
    junctions: list[Junction] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    points: list[Point] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    panels: list[Panel] = field(default_factory=list)
    current_state_name: str = 'current_state'
    next_state_name: str = 'next_state'
    encoding: str = 'sequential'     # ENCODINGS
    state_decl: str = 'parameter'    # STATE_DECLS
    # Legacy generation property "nextStateClocking" (SmGenChar of the state machine): the legacy tool then
    # labels the clocked actions "Transition Actions for internal signals only"
    next_state_clocking: bool = False
    # visible area when the legacy tool last saved the diagram (scene units x0, y0, x1, y1): the editor
    # opens there, as the legacy tool does, when it has no view of its own for the diagram
    view_area: list[float] | None = None

    # -- lookup helpers -------------------------------------------------
    def node(self, node_id: str) -> Any:
        """Return the state, junction, link or point with this id (None if there is none)."""
        for coll in (self.states, self.junctions, self.links, self.points):
            for n in coll:
                if n.id == node_id:
                    return n
        return None

    def state_by_name(self, name: str) -> State | None:
        """Return the state called `name`, or None."""
        return next((s for s in self.states if s.name == name), None)

    def outgoing(self, node_id: str) -> list[Transition]:
        """Transitions leaving node `node_id`, highest priority (lowest number) first."""
        return sorted((t for t in self.transitions if t.src == node_id), key=lambda t: t.priority)

    def point(self, kind: str) -> Point | None:
        """The first point of this kind ('reset', 'clock', ...), or None."""
        return next((p for p in self.points if p.kind == kind), None)

    def points_of(self, kind: str) -> list[Point]:
        """All points of this kind."""
        return [p for p in self.points if p.kind == kind]

    def new_id(self, prefix: str) -> str:
        """A new id `<prefix><n>` (lowest n >= 1) not used by any node or transition of the machine."""
        used = {n.id for coll in (self.states, self.junctions, self.links, self.points, self.transitions,
                                  self.comments, self.panels) for n in coll}
        i = 1
        while f'{prefix}{i}' in used:
            i += 1
        return f'{prefix}{i}'


@dataclass
class FsmView:
    """A state machine view of a design unit (the legacy tool "fsm" view): ports and signals, parameters, one
    or more machines, the declaration blocks (directives, concurrent statements, global actions)
    and the layout data needed to redraw the diagram as it was.

    Saved as JSON (`<view>.fsm.json`, see to_json) or read from / written to a legacy .sm file by
    formats.import_sm / export_sm.
    """
    library: str = 'work'
    unit: str = 'my_fsm'
    view: str = 'fsm'
    language: str = 'systemverilog'  # LANGUAGES
    signals: list[Signal] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    machines: list[Machine] = field(default_factory=lambda: [Machine()])
    pre_module_directives: str = ''
    post_module_directives: str = ''
    end_module_directives: str = ''
    concurrent_statements: str = ''
    state_register_statements: str = ''
    global_pre_actions: str = ''
    global_post_actions: str = ''
    registered_affix: str = '_r'
    clocked_affix: str = '_cld'
    # name of a new state, from the diagram's default-state template ('' = HDL Studio's S<n>)
    default_state_name: str = ''
    # text of a new junction, from the diagram's default-junction template (the legacy tool: "&")
    default_junction_symbol: str = ''
    # where the declaration blocks are drawn on the diagram (scene units, top-left of each title):
    # global, concurrent, module, status, statereg, compdir; missing = HDL Studio's default layout
    decl_pos: dict = field(default_factory=dict)
    # the declaration blocks hidden on the diagram (the legacy tool: their title text has isHidden 1)
    decl_hidden: list = field(default_factory=list)
    # layout of the Signals Table / Parameters Table pages: column order and widths, frozen columns,
    # row order, cell formats (formats.sheet; {} = the legacy tool's layout of a new diagram)
    signals_sheet: dict = field(default_factory=dict)
    params_sheet: dict = field(default_factory=dict)
    header: str = ''

    def signal(self, name: str) -> Signal | None:
        """Return the signal called `name`, or None."""
        return next((s for s in self.signals if s.name == name), None)

    # -- persistence ----------------------------------------------------
    def to_json(self) -> str:
        """The whole view as JSON text (format tag 'hdlstudio-fsm', version 1)."""
        return json.dumps({'format': 'hdlstudio-fsm', 'version': 1, 'view': asdict(self)}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> 'FsmView':
        """Build a view from the text written by to_json (unknown keys are ignored)."""
        data = json.loads(text)
        return _build(cls, data['view'])

    def save(self, path: str) -> None:
        """Write the view as JSON to `path` (UTF-8)."""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> 'FsmView':
        """Read a view saved by save()."""
        with open(path, encoding='utf-8') as f:
            return cls.from_json(f.read())


_LIST_TYPES = {
    'signals': Signal, 'parameters': Parameter, 'machines': Machine, 'states': State,
    'junctions': Junction, 'links': Link, 'points': Point, 'transitions': Transition, 'comments': Comment,
    'panels': Panel,
}


def _build(cls, data: dict) -> Any:
    """Rebuild dataclass `cls` from the dict asdict() made of it, recursing into the typed lists of
    _LIST_TYPES. Keys that `cls` no longer has are dropped, so old files still load after a field
    is removed; missing keys take the field defaults.
    """
    names = {f.name for f in fields(cls)}
    kwargs = {}
    for k, v in data.items():
        if k not in names:
            continue
        # Transition.points is a plain list of [x, y]; Machine.points holds Point objects
        if k in _LIST_TYPES and not (cls is Transition and k == 'points'):
            v = [_build(_LIST_TYPES[k], item) for item in v]
        kwargs[k] = v
    return cls(**kwargs)

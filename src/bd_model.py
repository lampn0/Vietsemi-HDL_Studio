"""Data model of a block diagram view (the legacy tool "struct" view): component instances, embedded
blocks, port I/Os, wires (net segments), generate frames, comments and junction dots.

All coordinates are scene units (the legacy file units divided by the import scale, see
formats.import_bd). A net is not an object of its own: it is the set of wires with the same
`net` name plus the Signal of that name in BlockDiagram.signals (its type and bounds).

Saved as JSON (`struct.bd.json`) with to_json / load, or imported from a legacy .bd file.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from model import Panel, Parameter, Signal


NAME_LINE_H = 12.0      # spacing of the library / component / instance name lines of an instance


@dataclass
class BdPin:
    """A port on a component instance and the net connected to it."""
    name: str
    mode: str = 'input'
    net: str = ''              # empty = unconnected
    order: int = 0             # declaration order on the symbol
    x: float = 0.0             # scene position of the pin
    y: float = 0.0
    side: str = 'left'         # left | right | top | bottom
    bounds: str = ''           # e.g. [7:0], used when a new net is created from this pin
    clock: bool = False        # clock input: drawn with an edge triangle inside the body
    arrow: str = ''            # where the port triangle points (right/left/up/down); '' = by mode and side
    slice: str = ''            # part of the net connected, e.g. "[3:0]" (a sliced wire); '' = whole net


@dataclass
class BdInstance:
    """A component instance: which library.unit it instantiates, its instance name, parameter
    overrides, its pins (and the nets on them) and how it is drawn (box, texts, colours).
    """
    id: str
    name: str
    library: str
    unit: str
    params: list[Parameter] = field(default_factory=list)   # overrides only
    pins: list[BdPin] = field(default_factory=list)
    show_params: bool = False   # draw parameter overrides on the diagram
    show_library: bool = False
    source: str = ''            # HDL file the component was added from (when it is not in the project)
    x: float = 0.0
    y: float = 0.0
    w: float = 120.0
    h: float = 80.0
    show_instance: bool = True  # instance name visible
    # top-left of the name text (library, component, instance lines) relative to the body;
    # None: centred at the top of the body
    text_pos: list[float] | None = None
    # text visibility of the pins (Text Visibility page)
    text_name: bool = True
    text_type: bool = False
    text_type_name: bool = False
    text_signed: bool = False
    text_value: bool = False
    selectable_text: bool = True
    # port map frame: explicit mapping of unconnected ports, e.g. ".a(1'b0), .b(x[3])"
    portmap_frame: bool = False
    portmap_text: str = ''
    attributes: str = ''        # Verilog comments written before the instance
    # appearance
    fg: str = '#00e600'
    bg: str = '#ffffff'
    line_color: str = '#007800'
    fill_style: str = 'solid'
    line_style: str = 'solid'
    line_width: int = 1
    shape: str = 'rectangle'


@dataclass
class BdEmbedded:
    """An embedded block: HDL text written straight into the diagram (the legacy tool "Embedded Block"); the
    generator copies `text` into the module body.
    """
    id: str
    name: str
    number: int = 1
    text: str = ''
    x: float = 0.0
    y: float = 0.0
    w: float = 200.0
    h: float = 120.0
    # The block's Text view: a white box [x, y, w, h] relative to the block's top-left. A
    # legacy block has it inside the yellow frame; a new block gets it when the user picks
    # "Text" in Create Embedded View, at the block's bottom-right corner as in the legacy tool. None: no
    # view yet (an empty yellow block, generating nothing).
    text_box: list[float] | None = None
    show_name: bool = True      # "eb1" label above the block


@dataclass
class BdComment:
    """Free comment text; the boxes of the title block share a group and move together."""
    id: str
    text: str = ''
    x: float = 0.0
    y: float = 0.0
    w: float = 160.0
    h: float = 14.0
    fill: str = ''              # box colour, '' for none
    color: str = '#000080'      # text colour
    group: str = ''


@dataclass
class BdJunction:
    """Dot where nets of the same name meet."""
    id: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class BdPortIo:
    """A port of the module drawn on the diagram (input / output / inout arrow); its name is the
    name of the net connected to it.
    """
    id: str
    name: str
    mode: str = 'input'
    x: float = 0.0
    y: float = 0.0
    show_text: bool = True      # port name shown on the diagram
    text_type: bool = False     # type constraint (bounds) shown after the name
    text_type_name: bool = False
    text_signed: bool = False
    text_value: bool = False
    fg: str = '#000082'
    bg: str = '#ffffff'
    line_color: str = '#000000'
    fill_style: str = 'solid'
    line_style: str = 'solid'
    line_width: int = 1


@dataclass
class BdWire:
    """One drawn net segment chain (polyline `points`). Both ends may be attached to a pin, a port
    I/O or an embedded block (see `start` / `end`); the net it belongs to is `net`.
    """
    id: str
    net: str
    points: list[list[float]] = field(default_factory=list)
    start: str = ''            # what each end is attached to: "pin:<inst id>:<pin>", "pio:<id>", "emb:<id>"
    end: str = ''
    show_text: bool = True     # net name shown on the diagram
    label: list[float] | None = None   # name text position, relative to the first point
    label_vertical: bool = False       # name runs upward along a vertical segment (legacy "ro 270")
    slice: str = ''            # the part of the net it carries, e.g. "[15]" (ripped from a bus); '' = all

    @property
    def text(self) -> str:
        """The name shown on the diagram: the net and the slice it carries."""
        return self.net + self.slice


@dataclass
class BdFrame:
    """Generate frame. FOR: spec is the range "[lb:rb]" (instances inside become instance
    arrays); IF: spec is the condition, either "`ifdef MACRO" / "`ifndef MACRO" or a
    generate-if expression; ELSE: the alternative of the IF frame with the same name.
    Objects whose centre lies inside the frame belong to it."""
    id: str
    kind: str = 'for'           # for | if | else
    name: str = 'g0'
    spec: str = '[7:0]'
    number: int = 1
    x: float = 0.0
    y: float = 0.0
    w: float = 300.0
    h: float = 200.0
    show_label: bool = True     # title text visible on the diagram
    show_number: bool = True    # sequence number box visible

    @property
    def title(self) -> str:
        """Text drawn in the frame's title box: "name: spec"."""
        return f'{self.name}: {self.spec}' if self.spec else self.name

    @property
    def label(self) -> str:
        """How the frame appears in the design hierarchy."""
        return f'{self.kind.upper()} : {self.name}'

    def contains(self, x: float, y: float) -> bool:
        """True when the scene point (x, y) is inside the frame rectangle (edges included)."""
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h

    def range(self) -> tuple[str, str]:
        """(left, right) bounds of a FOR frame, from "[left:right]"."""
        inner = self.spec.strip().lstrip('[').rstrip(']')
        depth, cut = 0, -1
        for i, c in enumerate(inner):          # the ':' not inside brackets or parentheses
            depth += c in '([{'
            depth -= c in ')]}'
            if c == ':' and depth == 0:
                cut = i
        if cut < 0:
            return inner.strip(), '0'
        return inner[:cut].strip(), inner[cut + 1:].strip()


@dataclass
class BlockDiagram:
    """A whole block diagram view: module ports and internal nets (signals), parameters, every
    drawn object and the declaration / directive texts written into the generated module.
    """
    library: str = 'work'
    unit: str = 'top'
    view: str = 'struct'
    language: str = 'systemverilog'
    signals: list[Signal] = field(default_factory=list)       # ports + internal nets
    parameters: list[Parameter] = field(default_factory=list)
    instances: list[BdInstance] = field(default_factory=list)
    embedded: list[BdEmbedded] = field(default_factory=list)
    port_ios: list[BdPortIo] = field(default_factory=list)
    wires: list[BdWire] = field(default_factory=list)
    frames: list[BdFrame] = field(default_factory=list)
    comments: list[BdComment] = field(default_factory=list)
    panels: list[Panel] = field(default_factory=list)
    junctions: list[BdJunction] = field(default_factory=list)
    # Change Style: net name -> 'bus' | 'signal' when drawn other than its bounds suggest
    net_styles: dict[str, str] = field(default_factory=dict)
    pre_module_directives: str = ''
    post_module_directives: str = ''
    end_module_directives: str = ''
    # user text of the diagram's Declarations block ("Pre User:" / "Post User:")
    pre_user_declarations: str = ''
    post_user_declarations: str = ''
    # visible area when the diagram was last saved by the legacy tool (scene units: x0, y0, x1, y1); the
    # editor opens there, as the legacy tool does, when it has no view of its own for the diagram
    view_area: list[float] | None = None
    header: str = ''

    def frame_path(self, x: float, y: float) -> list[BdFrame]:
        """Frames around a point, outermost first."""
        inside = [f for f in self.frames if f.contains(x, y)]
        return sorted(inside, key=lambda f: -(f.w * f.h))

    def frame_of(self, obj) -> BdFrame | None:
        """Innermost frame holding an instance or embedded block (by its centre)."""
        path = self.frame_path(obj.x + obj.w / 2, obj.y + obj.h / 2)
        return path[-1] if path else None

    def to_json(self) -> str:
        """The whole diagram as JSON text (format tag 'hdlstudio-bd', version 1)."""
        return json.dumps({'format': 'hdlstudio-bd', 'version': 1, 'view': asdict(self)}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> 'BlockDiagram':
        """Build a diagram from the text written by to_json (unknown keys are ignored)."""
        return _build(cls, json.loads(text)['view'])

    def save(self, path: str) -> None:
        """Write the diagram as JSON to `path` (UTF-8)."""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> 'BlockDiagram':
        """Read a diagram saved by save()."""
        with open(path, encoding='utf-8') as f:
            return cls.from_json(f.read())


_LISTS = {'signals': Signal, 'parameters': Parameter, 'instances': BdInstance, 'embedded': BdEmbedded,
          'port_ios': BdPortIo, 'wires': BdWire, 'params': Parameter, 'pins': BdPin, 'frames': BdFrame,
          'comments': BdComment, 'junctions': BdJunction, 'panels': Panel}


def _build(cls, data: dict) -> Any:
    """Rebuild dataclass `cls` from its asdict() form, recursing into the typed lists of _LISTS;
    keys the class no longer has are dropped so older files still load.
    """
    names = {f.name for f in fields(cls)}
    kw = {}
    for k, v in data.items():
        if k not in names:
            continue
        if k in _LISTS:
            v = [_build(_LISTS[k], x) for x in v]
        kw[k] = v
    return cls(**kw)

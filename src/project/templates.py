"""Starting content for new design units."""
from __future__ import annotations

import re

from model import FsmView, Machine, Point, Signal, State, Transition


def _is_clock(name: str) -> bool:
    """True for a port name that looks like a clock (clk..., clock..., ..._clk)."""
    return bool(re.fullmatch(r'(clk|clock)\w*|\w*_(clk|clock)', name, re.I))


def _is_reset(name: str) -> bool:
    """True for a port name that looks like a reset (rst..., reset..., ..._rst, ..._rst_n)."""
    return bool(re.fullmatch(r'(rst|reset)\w*|\w*_(rst|reset)(_n)?', name, re.I))


def new_fsm(library: str, unit: str, view: str, ports: list[tuple[str, str, str]], language: str,
            state_decl: str, encoding: str) -> FsmView:
    """The state diagram of a new design unit (File > New Design Content > State Machine), as the legacy tool
    starts one: the ports typed in the dialog (`ports` = (mode, bounds, name)), the first
    clock-like input as clock, the first reset-like input as asynchronous active-low reset,
    outputs combinational with default 0, one state ST_IDLE and the clock / reset / recovery
    points.
    """
    signals = []
    clock_done = reset_done = False
    for mode, bounds, name in ports:
        s = Signal(name, mode, 'wire' if mode == 'input' else 'reg', bounds)
        if mode == 'input' and not clock_done and _is_clock(name):
            s.category, s.expression, clock_done = 'clock', f'posedge {name}', True
        elif mode == 'input' and not reset_done and _is_reset(name):
            # As in a new legacy state diagram, the reset is asynchronous and active low
            # ("Reset (Async Low)", condition !rst), whatever its name
            s.category, s.expression, reset_done = 'reset', f'!{name}', True
        elif mode == 'output':
            s.scheme, s.default = 'comb', "'0" if bounds else "1'b0"
        signals.append(s)
    # the concurrent state machine is named "csm", as legacy names it in a new state diagram
    m = Machine(name='csm', encoding=encoding, state_decl=state_decl)
    m.states = [State('s1', 'ST_IDLE', 0, 0)]
    m.points = [Point('p1', 'clock', -220, -100), Point('p2', 'reset', -220, -50), Point('p3', 'recovery', -220, 80)]
    m.transitions = [Transition('t1', 'p2', 's1'), Transition('t2', 'p3', 's1')]
    return FsmView(library=library, unit=unit, view=view, language=language, signals=signals, machines=[m])


def _lines(text: str) -> list[str]:
    """Text block as lines, [] for blank text."""
    return text.rstrip('\n').split('\n') if text.strip() else []


def new_module(unit: str, ports: list[tuple[str, str, str]], language: str, header: str,
               pre: str = '', post: str = '', end: str = '') -> str:
    """Text view of a new module; pre/post/end are the Default Directives of Verilog Options."""
    sv = language == 'systemverilog'
    lines = _lines(header) + _lines(pre)
    lines.append(f'module {unit} (')
    rows = []
    for mode, bounds, name in ports:
        typ = 'logic' if sv else ('wire' if mode != 'output' else 'reg')
        rows.append(f'  {mode:<7}{typ:<6}{(bounds + " ") if bounds else ""}{name}')
    lines.append(',\n'.join(rows))
    lines.append(');')
    lines.append('')
    lines += _lines(post)
    lines.append('  // TODO: implementation')
    lines.append('')
    lines.append(f'endmodule // {unit}')
    lines += _lines(end)
    lines.append('')
    return '\n'.join(lines)

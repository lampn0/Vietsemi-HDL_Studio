"""Formatting shared by the generators."""
from __future__ import annotations

import re

IND = '  '

# Options > Verilog > Style, as the legacy tool applies them when it generates (set_style): the indent
# width ("Tab Width (spaces)"), "Instance Parameters Mapping" (Named / Positional) and "Allow
# implicit event expression (@*)". The defaults are those of the server's legacy settings
# HDL Studio was matched against; the legacy tool out of the box uses 3 / Positional.
STYLE = {'tab_width': 2, 'param_mapping': 'Named', 'implicit_event': False}


def set_style(tab_width: int | None = None, param_mapping: str | None = None,
              implicit_event: bool | None = None) -> None:
    """Change the generation style. The generators hold the indent in a module constant
    (IND, imported by name): it is set in each of them."""
    global IND
    if tab_width is not None:
        STYLE['tab_width'] = max(1, int(tab_width))
    if param_mapping is not None:
        STYLE['param_mapping'] = 'Positional' if str(param_mapping).lower().startswith('pos') else 'Named'
    if implicit_event is not None:
        STYLE['implicit_event'] = bool(implicit_event)
    IND = ' ' * STYLE['tab_width']
    from . import bd_codegen, fsm_codegen
    bd_codegen.IND = fsm_codegen.IND = IND
    fsm_codegen.IMPLICIT_EVENT = STYLE['implicit_event']


def port_lines(rows: list[tuple[str, str, str, str, str]]) -> list[str]:
    """ANSI port list in the legacy layout.

    rows: (mode, type, bounds, name, comment). Columns: mode (8), type (8),
    bounds (longest + 2), "name, " and an aligned end-of-line comment.
    """
    if not rows:
        return []
    wb = max(len(r[2]) for r in rows) + 2
    wn = max(len(r[3]) for r in rows) + 3
    out = []
    for i, (mode, typ, bounds, name, comment) in enumerate(rows):
        sep = ', ' if i < len(rows) - 1 else ''
        line = f'{IND}{mode:<8}{typ:<8}{bounds:<{wb}}{name}{sep}'
        if comment:
            line = f'{line:<{len(IND) + 16 + wb + wn}}// {comment}'
        out.append(line)
    return out


_CONT_RE = re.compile(r'\bassign\s+(\{[^}]*\}|[A-Za-z_]\w*)')
# an assignment at the start of a statement: after ; begin else ) or a case label
_PROC_RE = re.compile(r'(?:^|;|\bbegin\b|\belse\b|\)|(?<!:):(?!:))\s*([A-Za-z_]\w*)(?:\s*\[[^\]]*\])*\s*(?:<=|=)(?!=)',
                      re.M)
_DECL_START = re.compile(r'^\s*(assign|wire|logic|reg|tri|parameter|localparam|genvar|integer|input|output|inout)\b')


def drivers(text: str) -> tuple[set[str], set[str]]:
    """Signals driven by continuous `assign` and by procedural code in a block of HDL."""
    code = re.sub(r'//[^\n]*|/\*.*?\*/', ' ', text, flags=re.S)
    cont: set[str] = set()
    for m in _CONT_RE.finditer(code):
        cont.update(re.findall(r'[A-Za-z_]\w*', m.group(1)) if m.group(1).startswith('{') else [m.group(1)])
    proc: set[str] = set()
    for line_start, line in _statements(code):
        if _DECL_START.match(line):
            continue
        for m in _PROC_RE.finditer(line):
            proc.add(m.group(1))
    return cont, proc - {'for', 'if', 'case'}


def _statements(code: str):
    """Yield (offset, text) per ';'-terminated chunk so declarations can be skipped."""
    pos = 0
    for part in re.split(r'(?<=;)', code):
        yield pos, part
        pos += len(part)


def sv_net_type(name: str, procedural: set[str]) -> str:
    """SystemVerilog rule: assigned in procedural code -> logic, otherwise wire."""
    return 'logic' if name in procedural else 'wire'


def text_lines(text: str) -> list[str]:
    """User text block as lines, without leading/trailing empty lines."""
    return text.strip('\n').split('\n') if text.strip() else []

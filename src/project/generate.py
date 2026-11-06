"""Load graphical views and generate their HDL into the library's HDL folder.

A small record (`<graphics folder>/<unit>/.hdlstudio_gen.json`) keeps the hash of every file
this tool wrote. If a target file no longer matches that hash (or was not
written by this tool), it was edited by hand and is only overwritten when
the caller passes force=True.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

from bd_model import BlockDiagram
from codegen.bd_codegen import generate_bd
from codegen.fsm_codegen import generate as generate_fsm
from formats.import_bd import import_bd
from formats.import_sm import import_sm
from model import FsmView
from .project import DesignUnit, Library, View

RECORD = '.hdlstudio_gen.json'


def load_view(lib: Library, unit: DesignUnit, view: View):
    """Return the FsmView / BlockDiagram for a graphical view."""
    if view.kind == 'fsm':
        return import_sm(view.path, lib.name, unit.name) if view.legacy else FsmView.load(view.path)
    if view.kind == 'bd':
        return import_bd(view.path, lib.name, unit.name) if view.legacy else BlockDiagram.load(view.path)
    raise ValueError(f'{view.label} views cannot be opened yet')


def native_path(lib: Library, unit: str, view_name: str, kind: str) -> str:
    """Path of a view saved in HDL Studio's own format: <graphics folder>/<unit>/<view>.<kind>.json."""
    return os.path.join(lib.unit_dir(unit), f'{view_name}.{kind}.json')


# extension of generated files by language (Options > Verilog > File: Generated Verilog / System Verilog)
GENERATED_EXT = {'verilog': 'v', 'systemverilog': 'sv'}


def target_path(lib: Library, unit: str, language: str, rule: str = '%(unit).%(ext)', lower: bool = True,
                view: str = '') -> str:
    """Generated HDL file of a unit. The rule may use %(unit), %(view) and %(ext); legacy names a
    generated file %(unit)_%(view).%(ext), e.g. uart_tx_fsm.v."""
    ext = GENERATED_EXT['systemverilog' if language == 'systemverilog' else 'verilog']
    name = rule.replace('%(unit)', unit).replace('%(view)', view).replace('%(ext)', ext)
    if lower:
        name = name.lower()
    return os.path.join(lib.main_hdl_dir, name)


def _sha(text: str) -> str:
    """SHA-256 of a text (hex), used to recognise files this tool wrote."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _read_record(unit_dir: str) -> dict:
    """The generation record of a unit folder ({file name: sha256}); {} if missing or unreadable."""
    try:
        with open(os.path.join(unit_dir, RECORD), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_record(unit_dir: str, rec: dict) -> None:
    """Write the generation record of a unit folder."""
    os.makedirs(unit_dir, exist_ok=True)
    with open(os.path.join(unit_dir, RECORD), 'w', encoding='utf-8') as f:
        json.dump(rec, f, indent=1)


@dataclass
class GenResult:
    """Outcome of generating one unit: the file, a status (written / unchanged / conflict / error),
    a message for the Log and the generator's warnings.
    """
    unit: str
    path: str = ''
    status: str = 'error'          # written | unchanged | conflict | error
    message: str = ''
    warnings: list[str] = field(default_factory=list)


def generate_text(model) -> tuple[str, list[str]]:
    """Generate the HDL text of a model (FsmView or BlockDiagram). Returns (text, warnings)."""
    if isinstance(model, FsmView):
        return generate_fsm(model)
    return generate_bd(model)


def generate_unit(lib: Library, unit: DesignUnit, view: View | None = None, model=None,
                  force: bool = False, rule: str = '%(unit).%(ext)', lower: bool = True,
                  header: str | None = None) -> GenResult:
    """Generate the HDL file of one design unit into its library's HDL folder.

    `view` defaults to the unit's graphical view; `model` may be given when the editor already
    has the (possibly unsaved) diagram in memory. The file is written only when its content
    changes, and an existing file that this tool did not write last (hash in the generation
    record differs) is reported as a 'conflict' and left alone unless `force` is set. `rule` /
    `lower` name the file (Options > Verilog), `header` replaces the model's header for this run.
    """
    res = GenResult(unit.name)
    view = view or unit.graphic_view()
    if view is None and model is None:
        res.message = 'no graphical view to generate from'
        return res
    if not lib.writable:
        res.message = f'library {lib.name} is {lib.type} (read-only)'
        return res
    if not lib.main_hdl_dir:
        res.message = f'library {lib.name} has no HDL directory'
        return res
    try:
        model = model if model is not None else load_view(lib, unit, view)
        saved_header = model.header
        if header is not None:
            model.header = header
        try:
            text, res.warnings = generate_text(model)
        finally:
            model.header = saved_header
    except Exception as e:
        res.message = f'generation failed: {e}'
        return res
    path = target_path(lib, unit.name, model.language, rule, lower, getattr(model, 'view', ''))
    res.path = path
    udir = lib.unit_dir(unit.name)
    rec = _read_record(udir)
    if os.path.exists(path):
        with open(path, encoding='utf-8', errors='replace') as f:
            current = f.read()
        if current == text:
            res.status = 'unchanged'
            rec[os.path.basename(path)] = _sha(text)
            _write_record(udir, rec)
            return res
        if rec.get(os.path.basename(path)) != _sha(current) and not force:
            res.status = 'conflict'
            res.message = (f'{os.path.basename(path)} was changed outside this tool '
                           f'(or generated by another tool); not overwritten')
            return res
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(tmp, path)
    rec[os.path.basename(path)] = _sha(text)
    _write_record(udir, rec)
    res.status = 'written'
    other = target_path(lib, unit.name, 'verilog' if model.language == 'systemverilog' else 'systemverilog',
                        rule, lower, getattr(model, 'view', ''))
    if os.path.exists(other):
        res.warnings.append(f'{os.path.basename(other)} (other language) still exists in the HDL folder')
    return res


def generate_library(lib: Library, force: bool = False, **kw) -> list[GenResult]:
    """Generate every unit of a library that has a graphical view (scanning the library first)."""
    if not lib.scanned:
        lib.scan()
    return [generate_unit(lib, u, force=force, **kw) for u in lib.units.values() if u.graphic_view()]

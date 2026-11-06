"""Project, libraries and design units - what the Design Manager shows.

    Project      one .hdp file (plus the shared .hdp it names): its libraries, default library,
                 design root and the parse cache of HDL files
    Library      a logical name mapped to HDL folders (source files, [hdl] section) and one
                 graphics folder ([hds] section: hds/<unit>/<view>.<ext>); type regular,
                 protected (read-only) or downstream
    DesignUnit   a unit of a library, found in its HDL files and/or its graphics folder,
                 with every view
    View         one view of a unit: state diagram (.sm / .fsm.json), block diagram
                 (.bd / .bd.json), symbol (.sb), HDL text, or a kind not supported yet

Libraries are scanned lazily (Library.scan) the first time they are browsed, and HDL files
are re-parsed only when their modification time changes (Project.cache).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable
from formats.names import META_DIR, PROJECT_DIR_VAR, SETTINGS_SECTION

from hdl.parser import HDL_EXTENSIONS, HEADER_EXTENSIONS, HdlFile, HdlUnit, parse_file

_ALLOWED: tuple[str, ...] = ()        # Options > Verilog > File: Allowed Extensions (empty: built-in list)


def set_allowed_extensions(text: str) -> None:
    """Set the HDL file extensions a library scan accepts, from the space separated list of
    Options > Verilog > File ("v sv vlg"); an empty list restores the built-in one.
    """
    global _ALLOWED
    _ALLOWED = tuple('.' + e.lstrip('.').lower() for e in text.split() if e.strip('.'))


def hdl_extensions() -> tuple[str, ...]:
    """The HDL extensions a library scan accepts now (with the leading dot)."""
    return _ALLOWED or HDL_EXTENSIONS
from .hdp import HdpFile, expand_path, read_hdp, type_from_hdp, type_to_hdp, write_hdp

VIEW_KINDS = {
    '.fsm.json': ('fsm', 'State Machine'),
    '.bd.json': ('bd', 'Block Diagram'),
    '.sm': ('fsm', 'State Machine'),
    '.bd': ('bd', 'Block Diagram'),
    '.sb': ('symbol', 'Symbol'),
    '.tt': ('other', 'Truth Table'),
    '.fc': ('other', 'Flow Chart'),
    '.ibd': ('other', 'IBD'),
    '.asm': ('other', 'ASM Chart'),
}
GRAPHIC_KINDS = ('fsm', 'bd')
DEFAULT_VIEWS_FILE = '.hdlstudio_default_views.json'    # in a library's graphics folder: unit -> "view|kind"


@dataclass
class View:
    """One view of a design unit and the file holding it. `legacy` is True for a view read from an
    legacy file (.sm / .bd / .sb) rather than from HDL Studio's own .json.
    """
    name: str
    kind: str                 # fsm | bd | symbol | text | other
    label: str                # "State Machine", "Block Diagram", "Module", ...
    path: str
    language: str = ''
    legacy: bool = False      # read from a legacy .sm/.bd file (saved as .json by this tool)

    @property
    def mtime(self) -> float:
        """Modification time of the view's file (0 when it does not exist)."""
        return os.path.getmtime(self.path) if os.path.exists(self.path) else 0.0


@dataclass
class DesignUnit:
    """A design unit: its views, the HDL description found in the library's HDL files (if any) and
    the parse errors of that file.
    """
    name: str
    library: 'Library'
    views: list[View] = field(default_factory=list)
    hdl: HdlUnit | None = None
    file_errors: list[str] = field(default_factory=list)

    @property
    def type(self) -> str:
        """The Type column of the Design Units pane: Component (it has a symbol or a diagram), else
        Module / Package / Interface by what the HDL text declares.
        """
        if any(v.kind in ('symbol',) + GRAPHIC_KINDS for v in self.views):
            return 'Component'
        return {'package': 'Package', 'interface': 'Interface'}.get(self.hdl.kind if self.hdl else '', 'Module')

    @property
    def language(self) -> str:
        """Language of the unit: of its HDL file, else of its graphical view."""
        if self.hdl:
            return self.hdl.language
        g = self.graphic_view()
        return g.language if g else ''

    def graphic_view(self) -> View | None:
        """The state diagram or block diagram of the unit, or None."""
        return next((v for v in self.views if v.kind in GRAPHIC_KINDS), None)

    def text_view(self) -> View | None:
        """The HDL text view of the unit, or None."""
        return next((v for v in self.views if v.kind == 'text'), None)

    def default_view(self) -> View | None:
        """The view chosen with Set Default View, else the graphical view, else the HDL text."""
        chosen = self.library.default_views.get(self.name)
        if chosen:
            v = next((v for v in self.views if f'{v.name}|{v.kind}' == chosen), None)
            if v is not None:
                return v
        return self.graphic_view() or self.text_view() or \
            next((v for v in self.views if v.kind != 'symbol'), self.views[0] if self.views else None)

    def is_default(self, view: View) -> bool:
        """True when `view` is the unit's default view (shown in bold in the Design Manager)."""
        d = self.default_view()
        return d is not None and d.name == view.name and d.kind == view.kind

    @property
    def mtime(self) -> float:
        """Latest modification time of any of the unit's views."""
        return max((v.mtime for v in self.views), default=0.0)


@dataclass
class Library:
    """A library of the project. `errors` lists problems found while opening it (unset variable,
    missing folder) that the Design Manager shows in red. `units` and `files` are filled by scan().
    """
    name: str
    hdl_dirs: list[str] = field(default_factory=list)
    meta_dir: str = ''
    type: str = 'regular'                 # regular | protected | downstream
    include_dirs: list[str] = field(default_factory=list)
    inclusion: str = 'all'
    origin: str = 'user'                  # user | shared
    errors: list[str] = field(default_factory=list)
    units: dict[str, DesignUnit] = field(default_factory=dict)
    files: dict[str, HdlFile] = field(default_factory=dict)
    scanned: bool = False
    default_views: dict[str, str] = field(default_factory=dict)

    def _default_views_path(self) -> str:
        """The file of the library's Set Default View choices ('' when the library has no graphics folder)."""
        return os.path.join(self.meta_dir, DEFAULT_VIEWS_FILE) if self.meta_dir else ''

    def load_default_views(self) -> None:
        """Read the Set Default View choices of the library ({} if there are none)."""
        try:
            with open(self._default_views_path(), encoding='utf-8') as f:
                data = json.load(f)
            self.default_views = {k: v for k, v in data.items() if isinstance(v, str)}
        except (OSError, ValueError, AttributeError):
            self.default_views = {}

    def set_default_view(self, unit: str, view: View) -> None:
        """Remember the view opened by default for a design unit (Set Default View)."""
        if not self.writable:
            raise PermissionError(f'library {self.name} is {self.type}')
        if not self.meta_dir:
            raise OSError(f'library {self.name} has no graphics folder')
        self.default_views[unit] = f'{view.name}|{view.kind}'
        os.makedirs(self.meta_dir, exist_ok=True)
        with open(self._default_views_path(), 'w', encoding='utf-8') as f:
            json.dump(self.default_views, f, indent=1, sort_keys=True)

    @property
    def writable(self) -> bool:
        """Only regular libraries can be edited; protected and downstream ones are read-only."""
        return self.type == 'regular'

    @property
    def main_hdl_dir(self) -> str:
        """The first HDL folder: where generated files are written."""
        return self.hdl_dirs[0] if self.hdl_dirs else ''

    def hdl_files(self) -> list[str]:
        """Every HDL source and header file of the library's HDL folders, sorted. A library in
        mode 'all' ([library_files_inclusion]) includes every file under its HDL folders, sub-folders
        too (e.g. hdl/dti_crc/dti_crc.sv), as the legacy tool does; hidden folders (.svn, .git) are
        skipped. Other modes read the HDL folders themselves only.
        """
        exts = hdl_extensions() + HEADER_EXTENSIONS
        out = []
        for d in self.hdl_dirs:
            if not os.path.isdir(d):
                continue
            if self.inclusion != 'all':
                out += [os.path.join(d, f) for f in sorted(os.listdir(d))
                        if f.lower().endswith(exts) and os.path.isfile(os.path.join(d, f))]
                continue
            for root, dirs, files in os.walk(d):
                dirs[:] = sorted(x for x in dirs if not x.startswith('.'))
                out += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(exts)]
        return out

    def owns(self, path: str) -> bool:
        """True when `path` lies under one of the library's HDL folders (at any depth)."""
        p = os.path.normcase(os.path.abspath(path))
        for d in self.hdl_dirs:
            d = os.path.normcase(os.path.abspath(d))
            if p.startswith(d.rstrip(os.sep) + os.sep):
                return True
        return False

    def relative_name(self, path: str) -> str:
        """`path` relative to the HDL folder holding it (dti_crc/dti_crc.sv), or its file name."""
        for d in self.hdl_dirs:
            try:
                rel = os.path.relpath(path, d)
            except ValueError:                  # another drive
                continue
            if not rel.startswith('..'):
                return rel.replace(os.sep, '/')
        return os.path.basename(path)

    def unparsed_count(self) -> int:
        """Number of HDL files with parse errors (shown in the library's status)."""
        return sum(1 for f in self.files.values() if f.errors)

    def scan(self, cache: dict[str, HdlFile] | None = None,
             progress: 'Callable[[str, int, int], None] | None' = None) -> None:
        """(Re)build the design unit list from disk. `progress(library, done, total)` is called
        before each HDL file and once at the end (the Design Manager shows it in its status bar).
        """
        cache = {} if cache is None else cache
        self.units = {}
        self.files = {}
        sources = [p for p in self.hdl_files() if not p.lower().endswith(HEADER_EXTENSIONS)]
        for i, path in enumerate(sources):
            if progress:
                progress(self.name, i, len(sources))
            mtime = os.path.getmtime(path)
            parsed = cache.get(path)
            if parsed is None or parsed.mtime != mtime:
                parsed = parse_file(path, self.include_dirs)
                cache[path] = parsed
            self.files[path] = parsed
            for u in parsed.units:
                du = self.units.setdefault(u.name, DesignUnit(u.name, self))
                du.hdl = u
                du.file_errors = parsed.errors
                # the Type column shows what the text describes, as in the legacy Design Explorer
                du.views.append(View(os.path.splitext(os.path.basename(path))[0], 'text',
                                     (u.kind or 'module').capitalize(), path, u.language))
        if self.meta_dir and os.path.isdir(self.meta_dir):
            for unit in sorted(os.listdir(self.meta_dir)):
                udir = os.path.join(self.meta_dir, unit)
                if unit.startswith('.') or not os.path.isdir(udir):
                    continue
                views = _graphic_views(udir)
                if not views:
                    continue
                du = self.units.setdefault(unit, DesignUnit(unit, self))
                du.views = views + du.views
        self.load_default_views()
        self.scanned = True
        if progress:
            progress(self.name, len(sources), len(sources))

    def unit_dir(self, unit: str) -> str:
        """The graphics folder of a unit: <graphics folder>/<unit>."""
        return os.path.join(self.meta_dir, unit)


def _graphic_views(udir: str) -> list[View]:
    """The views found in a unit's graphics folder. When both a legacy file and HDL Studio's .json
    exist for one view, the rules in the loop below decide which one is the view.
    """
    found: dict[tuple[str, str], View] = {}
    for f in sorted(os.listdir(udir)):
        p = os.path.join(udir, f)
        if not os.path.isfile(p) or f.endswith('.lck'):
            continue
        for ext, (kind, label) in VIEW_KINDS.items():
            if f.endswith(ext):
                name = f[:-len(ext)]
                key = (name, kind)
                legacy = not ext.endswith('.json')
                # a view with both a legacy file and this tool's .json: a state diagram is
                # saved back to its .sm (both tools edit the same file), so the one saved
                # last is the view; for other kinds the tool's own .json wins
                if key not in found:
                    found[key] = View(name, kind, label, p, '', legacy)
                elif kind == 'fsm' and found[key].legacy != legacy:
                    if os.path.getmtime(p) > os.path.getmtime(found[key].path):
                        found[key] = View(name, kind, label, p, '', legacy)
                elif found[key].legacy and not legacy:
                    found[key] = View(name, kind, label, p, '', legacy)
                break
    order = {'fsm': 0, 'bd': 0, 'other': 1, 'symbol': 2}
    return sorted(found.values(), key=lambda v: (order.get(v.kind, 3), v.name))


@dataclass
class Project:
    """An open project. `hdp` is the user project file; libraries of the shared project file
    ([shared] others = ...) are appended, unless a user library has the same name.
    """
    path: str
    hdp: HdpFile
    libraries: list[Library] = field(default_factory=list)
    shared_path: str = ''
    default_library: str = ''
    design_root: str = ''
    errors: list[str] = field(default_factory=list)
    cache: dict[str, HdlFile] = field(default_factory=dict)
    # progress(library, done, total) while a library is scanned; set by the Design Manager
    progress: 'Callable[[str, int, int], None] | None' = field(default=None, repr=False, compare=False)

    @property
    def dir(self) -> str:
        """Folder of the .hdp file ($HDS_PROJECT_DIR)."""
        return os.path.dirname(os.path.abspath(self.path))

    @property
    def name(self) -> str:
        """Project name: the .hdp file name without extension."""
        return os.path.splitext(os.path.basename(self.path))[0]

    def library(self, name: str) -> Library | None:
        """The library called `name`, or None."""
        return next((l for l in self.libraries if l.name == name), None)

    def find_unit(self, name: str, prefer: Library | None = None) -> DesignUnit | None:
        """Find a design unit by name, in `prefer` first, then in every library (scanning them as
        needed). None when no library has it.
        """
        libs = ([prefer] if prefer else []) + [l for l in self.libraries if l is not prefer]
        for lib in libs:
            if not lib.scanned:
                lib.scan(self.cache, self.progress)
            if name in lib.units:
                return lib.units[name]
        return None

    # -- editing (writes the user .hdp) -------------------------------------------
    def add_library(self, name: str, root: str, lib_type: str = 'regular') -> Library:
        """Add a regular-style library rooted at `root` (folders <root>/hdl and the graphics folder are created)
        and write it to the .hdp with paths relative to $HDS_PROJECT_DIR.
        """
        rel = os.path.relpath(root, self.dir).replace('\\', '/')
        base = f'${PROJECT_DIR_VAR}' if rel == '.' else f'${PROJECT_DIR_VAR}/{rel}'
        self.hdp.entries += [('hdl', name, f'{base}/hdl'), (META_DIR, name, f'{base}/{META_DIR}'),
                             ('library_type', name, type_to_hdp(lib_type)),
                             ('library_files_inclusion', name, 'all')]
        write_hdp(self.hdp)
        for sub in ('hdl', META_DIR):
            os.makedirs(os.path.join(root, sub), exist_ok=True)
        lib = Library(name, [os.path.join(root, 'hdl')], os.path.join(root, META_DIR), lib_type)
        self.libraries.append(lib)
        return lib

    def design_root_unit(self) -> 'DesignUnit | None':
        """Design unit named by design_root, e.g. "lib.unit(unit)unit/struct.bd" or "lib.unit"."""
        m = re.match(r'\s*([\w$]+)\s*[.\s]\s*([\w$]+)', self.design_root)
        if m is None:
            return self.find_unit(self.design_root.strip()) if self.design_root.strip() else None
        return self.find_unit(m.group(2), prefer=self.library(m.group(1)))

    def set_design_root(self, unit: 'DesignUnit') -> None:
        """Write design_root in the legacy form lib.unit(unit)unit/<view file>."""
        v = unit.default_view()
        tail = f'{unit.name}/{os.path.basename(v.path)}' if v is not None and v.kind != 'text' else ''
        value = f'{unit.library.name}.{unit.name}({unit.name}){tail}'
        self.hdp.entries = [e for e in self.hdp.entries if not (e[0] == SETTINGS_SECTION and e[1] == 'design_root')]
        self.hdp.entries.append((SETTINGS_SECTION, 'design_root', value))
        write_hdp(self.hdp)
        self.design_root = value

    def unset_design_root(self) -> None:
        """Remove design_root from the .hdp (the project has no design root afterwards)."""
        self.hdp.entries = [e for e in self.hdp.entries if not (e[0] == SETTINGS_SECTION and e[1] == 'design_root')]
        write_hdp(self.hdp)
        self.design_root = ''

    def set_library_type(self, lib: Library, lib_type: str) -> None:
        """Write [library_type] of `lib` (regular | protected | downstream) to the .hdp."""
        self.hdp.entries = [e for e in self.hdp.entries if not (e[0] == 'library_type' and e[1] == lib.name)]
        self.hdp.entries.append(('library_type', lib.name, type_to_hdp(lib_type)))
        write_hdp(self.hdp)
        lib.type = lib_type

    def soft_path(self, path: str) -> str:
        """`path` written with $<project dir variable> when it lies in the project folder, the
        form the .hdp uses (the "soft" path); else `path` itself."""
        rel = os.path.relpath(os.path.abspath(path), self.dir) if os.path.splitdrive(
            os.path.abspath(path))[0].lower() == os.path.splitdrive(self.dir)[0].lower() else '..'
        if rel.startswith('..'):
            return path
        return f'${PROJECT_DIR_VAR}' + ('' if rel == '.' else '/' + rel.replace(os.sep, '/'))

    def set_default_library(self, name: str) -> None:
        """Write [hds_settings] default_library to the .hdp."""
        self.hdp.entries = [e for e in self.hdp.entries if not (e[0] == SETTINGS_SECTION and e[1] == 'default_library')]
        self.hdp.entries.append((SETTINGS_SECTION, 'default_library', name))
        write_hdp(self.hdp)
        self.default_library = name


def unit_ports(du: DesignUnit) -> list[tuple[str, str, str]]:
    """(name, mode, bounds) of a design unit's interface, from its HDL or its graphical view."""
    import re
    if du.hdl is not None and du.hdl.ports:
        out = []
        for p in du.hdl.ports:
            m = re.search(r'(\[[^\]]*\])', p.type)
            out.append((p.name, p.direction, m.group(1) if m else ''))
        return out
    g = du.graphic_view()
    if g is not None:
        from .generate import load_view
        try:
            model = load_view(du.library, du, g)
        except Exception:
            return []
        return [(s.name, s.mode, s.bounds) for s in model.signals if s.mode in ('input', 'output', 'inout')]
    return []


def _libraries_from(hdp: HdpFile, origin: str) -> tuple[list[Library], list[str]]:
    """The libraries of one .hdp file and the problems found (unset variables, missing folders).
    `origin` is 'user' or 'shared'.
    """
    pdir = os.path.dirname(os.path.abspath(hdp.path))
    errors = []
    libs = []
    names = []
    for sec in ('hdl', META_DIR, 'library_type'):
        for k in hdp.keys(sec):
            if k not in names:
                names.append(k)
    for name in names:
        lib = Library(name, origin=origin)
        for raw in hdp.values('hdl', name):
            p, missing = expand_path(raw, pdir)
            if missing:
                lib.errors.append(f'{name}: variable(s) {", ".join("$" + m for m in missing)} not set in "{raw}"')
            elif not os.path.isdir(p):
                lib.errors.append(f'{name}: HDL directory not found: {p}')
            lib.hdl_dirs.append(p)
        raw = hdp.first(META_DIR, name)
        if raw:
            p, missing = expand_path(raw, pdir)
            if missing:
                lib.errors.append(f'{name}: variable(s) {", ".join("$" + m for m in missing)} not set in "{raw}"')
            lib.meta_dir = p
        lib.type = type_from_hdp(hdp.first('library_type', name, 'regular'))
        for raw in hdp.values('includes_search_path', name):
            p, missing = expand_path(raw, pdir)
            if not missing:
                lib.include_dirs.append(p)
        lib.inclusion = hdp.first('library_files_inclusion', name, 'all')
        errors += lib.errors
        libs.append(lib)
    return libs, errors


def open_project(path: str) -> Project:
    """Open a .hdp project: its libraries (not scanned yet), settings and the shared project."""
    hdp = read_hdp(path)
    proj = Project(path, hdp)
    proj.libraries, proj.errors = _libraries_from(hdp, 'user')
    proj.default_library = hdp.first(SETTINGS_SECTION, 'default_library')
    proj.design_root = hdp.first(SETTINGS_SECTION, 'design_root')
    shared_raw = hdp.first('shared', 'others')
    if shared_raw:
        sp, missing = expand_path(shared_raw, proj.dir)
        if missing:
            proj.errors.append(f'Shared project: variable(s) {", ".join("$" + m for m in missing)} not set')
        elif os.path.exists(sp):
            proj.shared_path = sp
            shared_libs, errs = _libraries_from(read_hdp(sp), 'shared')
            proj.errors += errs
            user_names = {l.name for l in proj.libraries}
            proj.libraries += [l for l in shared_libs if l.name not in user_names]
        else:
            proj.errors.append(f'Shared project file not found: {sp}')
    return proj


def create_project(path: str, default_library: str) -> Project:
    """Create a new project file with one default library (File > New Project) and open it."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    hdp = HdpFile(path, [(SETTINGS_SECTION, 'default_library', default_library), (SETTINGS_SECTION, 'version', '2')])
    write_hdp(hdp)
    proj = open_project(path)
    proj.add_library(default_library, os.path.join(proj.dir, default_library))
    return open_project(path)

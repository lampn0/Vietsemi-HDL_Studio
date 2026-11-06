"""Link between an editor window and the project: where the view is saved,
the edit lock, and generation with overwrite confirmation."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QMessageBox

from prefs import expand_header
from project import lock
from bd_model import BlockDiagram
from model import FsmView
from formats.names import SETTINGS_SECTION
from project.generate import generate_unit, load_view, native_path, target_path
from project.project import DesignUnit, Library, Project, View


class EditorContext:
    """Everything an editor window needs to know about the project it edits in: the project,
    library, unit and view, whether the view is read-only (and why), and the lock files it holds.
    Created by the Design Manager when it opens a view; the editors call acquire() before
    editing, save() / generate() for File > Save and Generate, and release() when they close.
    """
    def __init__(self, manager, project: Project, lib: Library, unit: DesignUnit, view: View):
        """`manager` is the DesignManager (log, preferences, generation reports)."""
        self.manager = manager
        self.project = project
        self.lib = lib
        self.unit = unit
        self.view = view
        self.readonly = False
        self.readonly_reason = ''
        self.locked: list[str] = []

    @property
    def project_name(self) -> str:
        """Name of the project (for the header template)."""
        return self.project.name

    # -- locking ------------------------------------------------------------------
    def acquire(self, parent) -> bool:
        """Lock the view (legacy file and our .json). False = user cancelled."""
        if not self.lib.writable:
            self.readonly, self.readonly_reason = True, f'library {self.lib.name} is {self.lib.type}'
            return True
        if not os.access(self.view.path, os.W_OK) or not os.access(os.path.dirname(self.view.path), os.W_OK):
            self.readonly, self.readonly_reason = True, 'no write permission'
            return True
        targets = [self.view.path]
        jp = native_path(self.lib, self.unit.name, self.view.name, self.view.kind)
        if jp != self.view.path:
            targets.append(jp)
        for t in targets:
            info = lock.read_lock(t)
            if info is None or lock.is_mine(info):
                continue
            stale = lock.is_stale(info)
            if stale and info.user == lock.me().user:
                # Left by this user on this host by a run that no longer exists (a crash, a
                # killed tool): nobody holds it, take it over without asking.
                self.manager.log(f'{os.path.basename(t)}: stale lock of {info.describe()} taken over')
                continue
            box = QMessageBox(parent)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle('View is locked')
            box.setText(f'{os.path.basename(t)} is locked by {info.describe()}.'
                        + ('\nThat process is no longer running (stale lock).' if stale else ''))
            ro = box.addButton('Open read-only', QMessageBox.AcceptRole)
            reset = box.addButton('Reset lock and edit', QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is ro:
                self.readonly, self.readonly_reason = True, f'locked by {info.describe()}'
                return True
            if box.clickedButton() is not reset:
                return False
        for t in targets:
            ok, _ = lock.acquire(t, force=True)
            if ok:
                self.locked.append(t)
        return True

    def release(self) -> None:
        """Remove the locks this editor holds and tell the Design Manager the editor closed."""
        for t in self.locked:
            lock.release(t)
        self.locked = []
        self.manager.editor_closed(self)

    # -- saving / generating --------------------------------------------------------
    def save(self, model, parent, geometry=None) -> bool:
        """Save the view. A state diagram read from a legacy .sm is written back to that .sm
        (so the legacy tool and this tool keep editing the same file); `geometry` gives the lines as
        drawn (FsmScene.sm_geometry). Other views are saved as this tool's .json."""
        if self.readonly:
            QMessageBox.information(parent, 'Read-only', f'Cannot save: {self.readonly_reason}.')
            return False
        if self.view.legacy and self.view.kind == 'fsm' and self.view.path.endswith('.sm'):
            return self._save_sm(model, parent, geometry)
        path = native_path(self.lib, self.unit.name, self.view.name, self.view.kind)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if self.manager.prefs.create_backup and os.path.exists(path):
            import shutil
            shutil.copy2(path, path + '.bak')       # Main Settings > Save > Create backup file
        model.save(path)
        if path not in self.locked:
            lock.acquire(path, force=True)
            self.locked.append(path)
        self.manager.log(f'Saved {path}')
        self.manager.view_saved(self)
        return True

    def _save_sm(self, model, parent, geometry) -> bool:
        """Write the state diagram back into its legacy .sm file (formats.export_sm) and report in the
        Log, and in a message box, what could not be written.
        """
        from formats.export_sm import export_sm
        path = self.view.path
        if self.manager.prefs.create_backup and os.path.exists(path):
            import shutil
            shutil.copy2(path, path + '.bak')       # Main Settings > Save > Create backup file
        warn = export_sm(model, path, path, geometry)
        self.manager.log(f'Saved {path}')
        for w in warn:
            self.manager.log(f'  not saved: {w}')
        if warn:
            QMessageBox.warning(parent, 'Saved with omissions',
                                'Saved to the .sm file, but these changes could not be written yet:\n\n'
                                + '\n'.join(warn[:15]) + ('\n...' if len(warn) > 15 else ''))
        self.manager.view_saved(self)
        return True

    def generate(self, model, parent) -> None:
        """Generate this view's HDL (from the model in memory, saved or not)."""
        if self.readonly:
            QMessageBox.information(parent, 'Read-only', f'Cannot generate: {self.readonly_reason}.')
            return
        self.manager.generate_model(self.lib, self.unit, model, parent)

    def generate_hierarchy(self, model, parent, scope: str) -> None:
        """Generate down the hierarchy. scope: 'blocks' (children in the same
        library), 'components' (every child with a graphical view) or 'root'
        (like 'components', starting from the project's design root)."""
        if self.readonly and scope != 'root':
            QMessageBox.information(parent, 'Read-only', f'Cannot generate: {self.readonly_reason}.')
            return
        start = (self.lib, self.unit, model)
        if scope == 'root':
            root = self.project.design_root_unit()
            if root is None:
                QMessageBox.information(parent, 'Generate', 'No design root is set for this project '
                                        f'(design_root in the [{SETTINGS_SECTION}] section of the .hdp file).')
                return
            start = (root.library, root, model if root is self.unit else None)
        order, seen = [], set()

        def walk(lib, du, m):
            """Collect (library, unit, model) of `du` and, for a block diagram, of the units it
            instantiates (depth first, each unit once).
            """
            if (lib.name, du.name) in seen:
                return
            seen.add((lib.name, du.name))
            order.append((lib, du, m))
            if m is None and du.graphic_view() is not None:
                try:
                    m = load_view(lib, du, du.graphic_view())
                except Exception as e:        # reported by the generation itself
                    self.manager.log(f'{du.name}: cannot read view: {e}')
                    return
            if not isinstance(m, BlockDiagram):
                return
            for inst in m.instances:
                if scope == 'blocks' and inst.library and inst.library != lib.name:
                    continue
                child = self.project.find_unit(inst.unit, prefer=self.project.library(inst.library))
                if child is not None and child.graphic_view() is not None:
                    walk(child.library, child, None)

        walk(*start)
        for lib, du, m in order:
            if lib.writable:
                generate_with_prompt(self.manager, lib, du, m, parent)
            else:
                self.manager.log(f'{du.name}: skipped, library {lib.name} is {lib.type}')

    def open_generated(self, model) -> None:
        """Open the generated HDL file of the view in the text editor."""
        prefs = self.manager.prefs
        path = target_path(self.lib, self.unit.name, model.language, prefs.generated_name_rule,
                           prefs.generated_lowercase, getattr(model, 'view', ''))
        self.manager.open_text_file(path)

    def header_for(self, model) -> str:
        """The header text to put on top of this view's generated file."""
        return generation_header(self.manager.prefs, self.lib.name, self.unit.name,
                                 getattr(model, 'view', self.view.name), self.project.name, model)


def generation_header(prefs, library: str, unit: str, view: str, project_name: str, model) -> str:
    """Header of the view type (Verilog Options > Headers), then the generation properties if asked."""
    view_type = ('Block Diagram' if isinstance(model, BlockDiagram) else
                 'State Diagram' if isinstance(model, FsmView) else '')
    header = expand_header(prefs.header_for(view_type), library, unit, view, project_name)
    if not prefs.gen_properties or model is None:
        return header
    lang = 'SystemVerilog' if model.language == 'systemverilog' else 'Verilog'
    lines = ['// Generation properties:', f'//   Language : {lang}', f'//   View     : {library}.{unit}.{view}']
    if prefs.gen_signal_status and isinstance(model, FsmView):
        lines.append('//   Signal status:')
        lines += [f'//     {s.name:<20} {s.mode:<7} {s.scheme}' for s in model.signals]
    return header.rstrip('\n') + '\n' + '\n'.join(lines)


def generate_with_prompt(manager, lib: Library, unit: DesignUnit, model, parent, view: View | None = None) -> None:
    """Generate one unit; ask before overwriting a file changed outside the tool."""
    prefs = manager.prefs
    if model is None:
        v = view or unit.graphic_view()
        try:
            model = load_view(lib, unit, v) if v is not None else None
        except Exception:
            model = None                            # generate_unit reports the error
    header = generation_header(prefs, lib.name, unit.name,
                               getattr(model, 'view', '') if model is not None else (view.name if view else ''),
                               manager.project.name if manager.project else '', model)
    kw = dict(rule=prefs.generated_name_rule, lower=prefs.generated_lowercase, header=header)
    res = generate_unit(lib, unit, view=view, model=model, **kw)
    if res.status == 'conflict':
        r = QMessageBox.question(parent, 'Overwrite HDL file?',
                                 f'{res.message}.\n\nOverwrite {res.path} with newly generated code?',
                                 QMessageBox.Yes | QMessageBox.No)
        if r == QMessageBox.Yes:
            res = generate_unit(lib, unit, view=view, model=model, force=True, **kw)
    manager.report_generation(res)

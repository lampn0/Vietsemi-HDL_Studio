"""Options > Main... : the legacy Main Settings dialog (General, Text, Diagrams, Tables,
Checks, Save, User Variables). Settings HDL Studio uses are live; the others are shown
as in the legacy tool but greyed, so the layout matches."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from prefs import Prefs
from formats.names import TEAM_VER_VAR

NOT_USED = 'Not used by HDL Studio yet'


def _off(*widgets):
    """Disable widgets that show a legacy setting HDL Studio does not use yet (with a tool tip saying so)."""
    for w in widgets:
        w.setEnabled(False)
        w.setToolTip(NOT_USED)


def _path_row(text: str, owner) -> tuple[QHBoxLayout, QLineEdit, QPushButton]:
    """A line edit with a Browse... button for a folder; returns (layout, edit, button)."""
    row = QHBoxLayout()
    edit = QLineEdit(text)
    browse = QPushButton('Browse...')
    browse.clicked.connect(lambda: (lambda d: d and edit.setText(d))(QFileDialog.getExistingDirectory(owner, 'Browse', edit.text())))
    row.addWidget(edit, 1); row.addWidget(browse)
    return row, edit, browse


class MainSettingsDialog(QDialog):
    """Options > Main... dialog (see the module docstring). `applied` tells the caller that
    settings were written (OK or Apply), so it can refresh what depends on them.
    """
    def __init__(self, prefs: Prefs, parent=None):
        """Build the seven tabs from the current `prefs`. Each "# ---- <tab>" block below builds one
        tab; widgets kept as attributes (self.xxx) are the live ones read back by apply().
        """
        super().__init__(parent)
        self.setWindowTitle('Main Settings')
        self.prefs = p = prefs
        tabs = QTabWidget()

        # ---- General
        w = QWidget(); v = QVBoxLayout(w)
        self.downcase = QCheckBox('Automatically downcase Design Unit and View names when entered')
        self.downcase.setChecked(p.downcase_names)
        v.addWidget(self.downcase)
        row = QHBoxLayout()
        box = QGroupBox('Toolbar Buttons'); b = QVBoxLayout(box)
        self.remain = QRadioButton('Remain active'); self.once = QRadioButton('Activate once only')
        (self.remain if p.toolbar_remain_active else self.once).setChecked(True)
        b.addWidget(self.remain); b.addWidget(self.once)
        row.addWidget(box)
        box = QGroupBox('Filename display'); b = QVBoxLayout(box)
        logical = QRadioButton('Show as logical name (e.g. MY_File)'); actual = QRadioButton('Show actual filename (e.g. @m@y_@file)')
        logical.setChecked(True); _off(logical, actual)
        b.addWidget(logical); b.addWidget(actual)
        row.addWidget(box)
        v.addLayout(row)
        box = QGroupBox('Team Preferences'); b = QVBoxLayout(box)
        b.addWidget(QLabel('Single User Mode'))
        r = QHBoxLayout(); team = QPushButton('Switch to Team Mode'); admin = QCheckBox('Team Administrator mode')
        _off(team, admin); r.addWidget(team); r.addWidget(admin); r.addStretch(1); b.addLayout(r)
        v.addWidget(box)
        box = QGroupBox('Temp Directory'); r, self.temp, tb = _path_row(p.temp_dir, self); box.setLayout(r)
        _off(self.temp, tb); v.addWidget(box)
        box = QGroupBox('Remote Simulation Directory Location'); r, remote, rb = _path_row(f'${TEAM_VER_VAR}/remote', self)
        box.setLayout(r); _off(remote, rb); v.addWidget(box)
        box = QGroupBox('Project Property File'); r, prop, pb = _path_row('', self); box.setLayout(r)
        _off(prop, pb); v.addWidget(box)
        row = QHBoxLayout()
        box = QGroupBox('Default Language for New Views'); f = QFormLayout(box)
        self.graphic_lang = QComboBox(); self.graphic_lang.addItem('Verilog 2005', 'verilog')
        self.graphic_lang.addItem('SystemVerilog', 'systemverilog')
        self.graphic_lang.setCurrentIndex(max(0, self.graphic_lang.findData(p.default_language)))
        vhdl = QComboBox(); vhdl.addItem('VHDL 2008'); _off(vhdl)
        self.text_lang = QComboBox(); self.text_lang.addItem('Verilog 2005', 'verilog')
        self.text_lang.addItem('SystemVerilog', 'systemverilog')
        self.text_lang.setCurrentIndex(max(0, self.text_lang.findData(p.text_language)))
        f.addRow('Graphical Views:', self.graphic_lang); f.addRow('Text Views VHDL:', vhdl)
        f.addRow('Text Views Verilog:', self.text_lang)
        row.addWidget(box)
        box = QGroupBox('Units'); f = QFormLayout(box)
        units = QComboBox(); units.addItems(['Inches', 'Millimeters']); _off(units)
        f.addRow('Units for printing:', units)
        row.addWidget(box, 0, Qt.AlignTop)
        v.addLayout(row)
        self.restore = QCheckBox('Reopen the last project and its windows at start-up')
        self.restore.setChecked(p.restore_session)
        v.addWidget(self.restore); v.addStretch(1)
        tabs.addTab(w, 'General')

        # ---- Text
        w = QWidget(); v = QVBoxLayout(w)
        box = QGroupBox('Text Editor Commands'); g = QGridLayout(box)
        self.editor = QComboBox(); self.editor.addItems(['HDL Studio editor', 'External command'])
        self.editor.setCurrentIndex(1 if p.use_external_editor else 0)
        self.editor_cmd = QLineEdit(p.external_editor)
        self.editor_cmd.setToolTip('{file} and {line} are replaced, e.g. gvim +{line} {file}')
        self.editor.currentIndexChanged.connect(lambda i: self.editor_cmd.setEnabled(i == 1))
        self.editor_cmd.setEnabled(p.use_external_editor)
        g.addWidget(QLabel('Editor:'), 0, 0, 1, 2)
        g.addWidget(self.editor, 1, 0); g.addWidget(self.editor_cmd, 1, 1)
        g.addWidget(QLabel('Text file extensions'), 2, 0)
        self.extensions = QLineEdit(p.text_extensions); g.addWidget(self.extensions, 2, 1)
        g.addWidget(QLabel('HDL Viewer (Used to display text read-only):'), 3, 0, 1, 2)
        viewer = QComboBox(); viewer.addItem('HDL Studio editor'); g.addWidget(viewer, 4, 0, 1, 2)
        v.addWidget(box)
        box = QGroupBox('Printing'); b = QVBoxLayout(box)
        b.addWidget(QLabel('Text File Print Command:'))
        pr = QComboBox(); pr.addItem('Enscript'); _off(pr); b.addWidget(pr)
        v.addWidget(box); v.addStretch(1)
        tabs.addTab(w, 'Text')

        # ---- Diagrams
        w = QWidget(); v = QVBoxLayout(w)
        box = QGroupBox('Font Settings'); g = QGridLayout(box)
        font = QLineEdit('courier Normal 10 point'); fset = QPushButton('Set...')
        scal = QCheckBox('Use scalable fonts'); close = QCheckBox('Use closest matched fonts')
        vis, sel = QSpinBox(), QSpinBox()
        for s in (vis, sel):
            s.setValue(3)
        g.addWidget(QLabel('Font:'), 0, 0); g.addWidget(font, 0, 1, 1, 2); g.addWidget(fset, 0, 3)
        g.addWidget(scal, 1, 1); g.addWidget(close, 1, 2)
        g.addWidget(QLabel('Text less than'), 2, 0); g.addWidget(vis, 2, 1); g.addWidget(QLabel('pixels high is not visible.'), 2, 2)
        g.addWidget(QLabel('Text less than'), 3, 0); g.addWidget(sel, 3, 1); g.addWidget(QLabel('pixels high is not selectable.'), 3, 2)
        _off(font, fset, scal, close, vis, sel)
        v.addWidget(box)
        box = QGroupBox('Title Blocks'); b = QVBoxLayout(box)
        b.addWidget(QLabel('Template file:'))
        r, tmpl, tbb = _path_row(f'${TEAM_VER_VAR}/title_block.tmpl', self); b.addLayout(r)
        add_tb = QCheckBox('Add Title Blocks in new diagrams'); b.addWidget(add_tb)
        _off(tmpl, tbb, add_tb)
        v.addWidget(box)
        anchors = QCheckBox('Show Anchors for associated objects'); strokes = QCheckBox('Enable Strokes')
        _off(anchors, strokes); v.addWidget(anchors); v.addWidget(strokes); v.addStretch(1)
        tabs.addTab(w, 'Diagrams')

        # ---- Tables
        w = QWidget(); v = QVBoxLayout(w)
        auto = QCheckBox('Enable AutoComplete for cell values (in IBD/Tabular IO)'); _off(auto)
        v.addWidget(auto); v.addStretch(1)
        tabs.addTab(w, 'Tables')

        # ---- Checks
        w = QWidget(); v = QVBoxLayout(w)
        box = QGroupBox('Semantic Checks'); b = QVBoxLayout(box)
        b.addWidget(QLabel('These checks are performed during HDL Generation or parsing. You can choose if you want '
                           'to perform base-level checks and then specify required check and message options.'))
        perform = QCheckBox('Perform Checks'); b.addWidget(perform)
        opts = QGroupBox('Check Options'); g = QGridLayout(opts)
        strict, synth, dep, strict_b = (QCheckBox('Strict checking'), QCheckBox('Common synthesis checks'),
                                        QCheckBox('Dependency checks'), QPushButton('Strict Options...'))
        g.addWidget(strict, 0, 0); g.addWidget(strict_b, 0, 1); g.addWidget(synth, 1, 0); g.addWidget(dep, 2, 0)
        b.addWidget(opts)
        msg = QGroupBox('Message Options'); g = QGridLayout(msg)
        warn, verb, limit = QCheckBox('Show warning messages'), QCheckBox('Show verbose messages'), QLineEdit('5')
        g.addWidget(warn, 0, 0); g.addWidget(QLabel('Same message limit:'), 0, 1); g.addWidget(limit, 0, 2)
        g.addWidget(verb, 1, 0)
        b.addWidget(msg)
        v.addWidget(box)
        box = QGroupBox('External IP Checks'); b = QVBoxLayout(box); ipc = QCheckBox('Check interface'); b.addWidget(ipc)
        v.addWidget(box)
        box = QGroupBox('Reconcile Interface Options'); b = QVBoxLayout(box)
        case, order = QCheckBox('Enforce consistent case'), QCheckBox('Enforce consistent port ordering')
        b.addWidget(case); b.addWidget(order); v.addWidget(box)
        box = QGroupBox('Gate Level Limits'); f = QFormLayout(box)
        il, sl = QLineEdit('1000'), QLineEdit('1000')
        f.addRow('Instance limit:', il); f.addRow('Signal limit:', sl); v.addWidget(box)
        _off(perform, strict, synth, dep, strict_b, warn, verb, limit, ipc, case, order, il, sl)
        v.addStretch(1)
        tabs.addTab(w, 'Checks')

        # ---- Save
        w = QWidget(); v = QVBoxLayout(w)
        box = QGroupBox('File Recovery'); g = QGridLayout(box)
        self.recovery = QCheckBox('Automatically save recovery file'); self.recovery.setChecked(p.autosave_enabled)
        self.every = QSpinBox(); self.every.setRange(1, 120); self.every.setValue(p.autosave_minutes)
        self.recovery.toggled.connect(self.every.setEnabled); self.every.setEnabled(p.autosave_enabled)
        self.backup = QCheckBox('Create backup file'); self.backup.setChecked(p.create_backup)
        self.backup.setToolTip('Keep the previous version as <file>.bak when a view is saved')
        g.addWidget(self.recovery, 0, 0, 1, 3)
        g.addWidget(QLabel('Save every:'), 1, 0); g.addWidget(self.every, 1, 1); g.addWidget(QLabel('minutes'), 1, 2)
        g.addWidget(self.backup, 2, 0, 1, 3)
        v.addWidget(box)
        box = QGroupBox('Symbol/Interface Updating'); b = QVBoxLayout(box)
        u1, u2 = QCheckBox('Update against default view on open'), QCheckBox('Update when default view is saved')
        b.addWidget(u1); b.addWidget(u2); v.addWidget(box)
        box = QGroupBox('View Updating'); b = QVBoxLayout(box)
        b.addWidget(QLabel('Updates occur when saving the symbol/interface.\nGraphical views are also updated when loaded.'))
        u3, u4, u5 = QCheckBox('Update HDL'), QCheckBox('Update graphics'), \
            QCheckBox('Preserve Verilog types for multiple view design units')
        for c in (u3, u4, u5):
            b.addWidget(c)
        v.addWidget(box)
        _off(u1, u2, u3, u4, u5)
        v.addStretch(1)
        tabs.addTab(w, 'Save')

        # ---- User Variables
        w = QWidget(); v = QVBoxLayout(w)
        self.vars = QTableWidget(0, 2); self.vars.setHorizontalHeaderLabels(['Name', 'Value'])
        self.vars.horizontalHeader().setStretchLastSection(True)
        for name, value in sorted(p.user_variables.items()):
            self._var_row(name, value)
        self._var_row('', '')
        self.vars.itemChanged.connect(self._grow)
        v.addWidget(self.vars)
        tabs.addTab(w, 'User Variables')

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
                              | QDialogButtonBox.Help)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        bb.button(QDialogButtonBox.Help).setEnabled(False)
        self.applied = False
        lay = QVBoxLayout(self); lay.addWidget(tabs); lay.addWidget(bb)
        self.tabs = tabs
        self.resize(640, 760)

    def _var_row(self, name: str, value: str):
        """Append one Name / Value row to the User Variables table."""
        r = self.vars.rowCount()
        self.vars.insertRow(r)
        self.vars.setItem(r, 0, QTableWidgetItem(name)); self.vars.setItem(r, 1, QTableWidgetItem(value))

    def _grow(self, item):
        """Keep one empty row at the end of the User Variables table, for typing a new variable."""
        last = self.vars.rowCount() - 1
        if item.row() == last and item.text().strip():
            self.vars.blockSignals(True); self._var_row('', ''); self.vars.blockSignals(False)

    def apply(self):
        """Copy the live widgets into the preferences and save them (Apply button, and OK)."""
        p = self.prefs
        p.downcase_names = self.downcase.isChecked()
        p.restore_session = self.restore.isChecked()
        p.toolbar_remain_active = self.remain.isChecked()
        p.default_language = self.graphic_lang.currentData()
        p.text_language = self.text_lang.currentData()
        p.use_external_editor = self.editor.currentIndex() == 1
        p.external_editor = self.editor_cmd.text().strip() or p.external_editor
        p.text_extensions = self.extensions.text().strip()
        p.autosave_enabled = self.recovery.isChecked()
        p.autosave_minutes = self.every.value()
        p.create_backup = self.backup.isChecked()
        p.user_variables = {self.vars.item(r, 0).text().strip(): (self.vars.item(r, 1).text() if self.vars.item(r, 1) else '')
                            for r in range(self.vars.rowCount())
                            if self.vars.item(r, 0) and self.vars.item(r, 0).text().strip()}
        p.save()
        self.applied = True

    def _ok(self):
        """OK: apply, then close."""
        self.apply()
        self.accept()

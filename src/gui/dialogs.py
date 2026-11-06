"""New project / library / design unit dialogs and Preferences."""
from __future__ import annotations

import os
import re

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from model import ENCODINGS, LANGUAGES, STATE_DECLS
from prefs import Prefs
from formats.names import META_DIR

IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*$')
LANG_LABEL = {'systemverilog': 'SystemVerilog', 'verilog': 'Verilog 2005'}


def _dir_row(edit: QLineEdit, parent, title: str) -> QWidget:
    """A line edit with a Browse... button that picks a folder into it."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(edit)
    b = QPushButton('Browse...')
    b.clicked.connect(lambda: edit.setText(QFileDialog.getExistingDirectory(parent, title, edit.text()) or edit.text()))
    lay.addWidget(b)
    return w


class _Base(QDialog):
    """Common frame of the dialogs: a form, a red error line and OK / Cancel. OK runs validate();
    the dialog closes only when it returns '' (otherwise the message is shown).
    """
    def __init__(self, title: str, parent=None):
        """Build the empty form; subclasses add their rows to self.form."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.form = QFormLayout()
        self.error = QLabel()
        self.error.setStyleSheet('color: #c00000')
        lay = QVBoxLayout(self)
        lay.addLayout(self.form)
        lay.addWidget(self.error)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.setMinimumWidth(520)

    def validate(self) -> str:
        """Error message for the current input, '' when it is acceptable (subclasses)."""
        return ''

    def _ok(self):
        """OK pressed: accept the dialog unless validate() reports a problem."""
        msg = self.validate()
        if msg:
            self.error.setText(msg)
            return
        self.accept()


class NewProjectDialog(_Base):
    """File > New Project: project name, parent folder and default library."""
    def __init__(self, parent=None, start_dir: str = ''):
        """Build the form; the library name follows the project name until edited."""
        super().__init__('Create New Project', parent)
        self.name = QLineEdit()
        self.folder = QLineEdit(start_dir or os.path.expanduser('~'))
        self.lib = QLineEdit()
        self.name.textEdited.connect(lambda t: self.lib.setText(t.lower()))
        self.form.addRow('Project name', self.name)
        self.form.addRow('Location (parent folder)', _dir_row(self.folder, self, 'Project location'))
        self.form.addRow('Default library', self.lib)
        self.form.addRow(QLabel('<small>Creates &lt;location&gt;/&lt;name&gt;/&lt;name&gt;.hdp and the default '
                                f'library folders &lt;library&gt;/hdl and &lt;library&gt;/{META_DIR}.</small>'))

    @property
    def hdp_path(self) -> str:
        """The .hdp file that will be created: <location>/<name>/<name>.hdp."""
        n = self.name.text().strip()
        return os.path.join(self.folder.text().strip(), n, f'{n}.hdp')

    def validate(self):
        """Names must be identifiers, the folder must exist and the project must not exist yet."""
        if not IDENT.match(self.name.text().strip()):
            return 'Project name must be an identifier (letters, digits, _).'
        if not IDENT.match(self.lib.text().strip()):
            return 'Library name must be an identifier.'
        if not os.path.isdir(self.folder.text().strip()):
            return 'Location folder does not exist.'
        if os.path.exists(self.hdp_path):
            return f'{self.hdp_path} already exists.'
        return ''


class NewLibraryDialog(_Base):
    """File > New Library: name, folder (default <project>/libs/<name>) and type."""
    def __init__(self, project_dir: str, parent=None):
        """Build the form for a project in `project_dir`."""
        super().__init__('New Library', parent)
        self.project_dir = project_dir
        self.name = QLineEdit()
        self.folder = QLineEdit()
        self.name.textEdited.connect(lambda t: self.folder.setText(os.path.join(project_dir, 'libs', t)))
        self.type = QComboBox(); self.type.addItems(['regular', 'protected'])
        self.form.addRow('Library name', self.name)
        self.form.addRow('Library folder', _dir_row(self.folder, self, 'Library folder'))
        self.form.addRow('Type', self.type)
        self.form.addRow(QLabel(f'<small>HDL files go to &lt;folder&gt;/hdl, graphics to &lt;folder&gt;/{META_DIR}. '
                                'The mapping is added to the project .hdp file.</small>'))

    def validate(self):
        """The name must be an identifier and a folder must be chosen."""
        if not IDENT.match(self.name.text().strip()):
            return 'Library name must be an identifier.'
        if not self.folder.text().strip():
            return 'Choose a folder.'
        return ''


class NewUnitDialog(_Base):
    """File > New Design Content: library, kind (state machine, block diagram, Verilog /
    SystemVerilog text module), unit and view names, language and the port list.
    """
    KINDS = [('fsm', 'State Machine (graphical)'), ('sv', 'SystemVerilog module (text)'),
             ('v', 'Verilog module (text)'), ('bd', 'Block Diagram (graphical)')]

    def __init__(self, libraries: list[str], current: str, prefs: Prefs, parent=None):
        """Build the form; `libraries` are offered, `current` is preselected, `prefs` gives the default
        language.
        """
        super().__init__('New Design Content', parent)
        self.lib = QComboBox(); self.lib.addItems(libraries)
        if current in libraries:
            self.lib.setCurrentText(current)
        self.kind = QComboBox()
        for k, label in self.KINDS:
            self.kind.addItem(label, k)
        self.unit = QLineEdit()
        self.view = QLineEdit('fsm')
        # language of a graphical view, as the legacy wizard asks it (Verilog 2005 / SystemVerilog)
        self.language = QComboBox()
        for lang in LANGUAGES:
            self.language.addItem(LANG_LABEL[lang], lang)
        self.language.setCurrentIndex(max(0, LANGUAGES.index(prefs.default_language)
                                          if prefs.default_language in LANGUAGES else 0))
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.ports = QPlainTextEdit()
        self.ports.setPlaceholderText('One port per line, e.g.\ninput clk\ninput rst_n\ninput [7:0] data_in\n'
                                      'output [7:0] data_out')
        self.ports.setPlainText('input clk\ninput rst_n')
        self.ports.setMaximumHeight(130)
        self.form.addRow('Library', self.lib)
        self.form.addRow('Content type', self.kind)
        self.form.addRow('Design unit name', self.unit)
        self.form.addRow('View name', self.view)
        self.form.addRow('Language', self.language)
        self.form.addRow('Ports', self.ports)
        self.form.addRow(QLabel('<small>For a state machine, the first input named like a clock gets '
                                'Category = clock and one named like a reset gets Category = reset.</small>'))

    def _kind_changed(self):
        """Default view name for the chosen kind (fsm / struct); text modules have no view name."""
        k = self.kind.currentData()
        self.view.setText({'fsm': 'fsm', 'bd': 'struct'}.get(k, ''))
        self.view.setEnabled(k in ('fsm', 'bd'))

    def parsed_ports(self) -> list[tuple[str, str, str]]:
        """The port lines as (mode, bounds, name), e.g. "input [7:0] data" -> ('input', '[7:0]', 'data')."""
        out = []
        for line in self.ports.toPlainText().splitlines():
            m = re.match(r'\s*(input|output|inout)\s*(\[[^\]]*\])?\s*([A-Za-z_]\w*)\s*$', line)
            if m:
                out.append((m.group(1), m.group(2) or '', m.group(3)))
        return out

    def validate(self):
        """The unit name must be an identifier and every non-empty port line must be readable."""
        if not IDENT.match(self.unit.text().strip()):
            return 'Design unit name must be an identifier.'
        bad = [l for l in self.ports.toPlainText().splitlines()
               if l.strip() and not re.match(r'\s*(input|output|inout)\s*(\[[^\]]*\])?\s*[A-Za-z_]\w*\s*$', l)]
        if bad:
            return f'Cannot read port line: "{bad[0].strip()}"'
        return ''


class PreferencesDialog(_Base):
    """Options > Preferences: defaults for new views, generated file naming, header template,
    external editor and session restore.
    """
    def __init__(self, prefs: Prefs, parent=None):
        """Build the form from the current `prefs`."""
        super().__init__('Preferences', parent)
        self.prefs = prefs
        self.lang = QComboBox(); [self.lang.addItem(LANG_LABEL[l], l) for l in LANGUAGES]
        self.lang.setCurrentIndex(LANGUAGES.index(prefs.default_language))
        self.decl = QComboBox(); self.decl.addItems(STATE_DECLS); self.decl.setCurrentText(prefs.default_state_decl)
        self.enc = QComboBox(); self.enc.addItems(ENCODINGS); self.enc.setCurrentText(prefs.default_encoding)
        self.rule = QLineEdit(prefs.generated_name_rule)
        self.lower = QCheckBox('Always lower case'); self.lower.setChecked(prefs.generated_lowercase)
        self.header = QPlainTextEdit(prefs.header_template)
        self.header.setMinimumHeight(140)
        self.ext = QCheckBox('Open HDL text in an external editor'); self.ext.setChecked(prefs.use_external_editor)
        self.ext_cmd = QLineEdit(prefs.external_editor)
        self.restore = QCheckBox('Reopen the last project and its windows at start-up')
        self.restore.setChecked(prefs.restore_session)
        self.form.addRow('', self.restore)
        self.form.addRow('Default language for new views', self.lang)
        self.form.addRow('Default state declaration', self.decl)
        self.form.addRow('Default state encoding', self.enc)
        self.form.addRow('Generated file name rule', self.rule)
        self.form.addRow('', self.lower)
        self.form.addRow('Header template', self.header)
        self.form.addRow(QLabel('<small>Variables: %(library) %(unit) %(view) %(project_name) %(user) %(date) '
                                '%(time) %(year)</small>'))
        self.form.addRow('', self.ext)
        self.form.addRow('External editor command', self.ext_cmd)
        self.form.addRow(QLabel('<small>{file} and {line} are replaced, e.g. <tt>gvim +{line} {file}</tt> or '
                                '<tt>emacs +{line} {file}</tt></small>'))
        self.setMinimumWidth(640)

    def validate(self):
        """The file name rule must contain %(unit)."""
        if '%(unit)' not in self.rule.text():
            return 'The file name rule must contain %(unit).'
        return ''

    def apply(self):
        """Copy the form into the preferences and save them."""
        p = self.prefs
        p.default_language = self.lang.currentData()
        p.default_state_decl = self.decl.currentText()
        p.default_encoding = self.enc.currentText()
        p.generated_name_rule = self.rule.text().strip()
        p.generated_lowercase = self.lower.isChecked()
        p.header_template = self.header.toPlainText()
        p.use_external_editor = self.ext.isChecked()
        p.external_editor = self.ext_cmd.text().strip()
        p.restore_session = self.restore.isChecked()
        p.save()

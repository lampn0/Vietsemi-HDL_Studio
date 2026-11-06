"""Toolbars of the diagram editors, laid out as in the legacy tool: Standard, the editor's tools
(State Diagram Tools / Block Diagram Tools), HDL Tools and Tasks, with the legacy buttons in the
legacy order. Each entry refers to an action the editor already has (by key); missing ones are
shown disabled. Entries given as a list become a button with a drop-down menu (first = default).
Icons are editor_icons' 16x16 pictures, greyed when a button is disabled.
"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu, QToolBar, QToolButton

from .command_names import COMMANDS
from .editor_icons import editor_icon


def _standard(expression_builder: bool) -> list:
    """The Standard toolbar (the state diagram one has Expression Builder, the block diagram one not)."""
    return ([[('new', 'New')], ('back', 'Back'), ('forward', 'Forward'), ('open_up', 'Open Up'),
             ('save', 'Save'), ('print', 'Print'),
             [('document', 'Document & Visualize Design'), ('document_hier', 'Hierarchy Through Components'),
              ('document_root', 'Through Design Root')], '|',
             ('cut', 'Cut'), ('copy', 'Copy'), ('paste', 'Paste'), '|', ('undo', 'Undo'), ('redo', 'Redo'), '|',
             ('find', 'Find'), '|', ('object_props', 'Object Properties'), '|']
            + ([('expression_builder', 'Expression Builder'), '|'] if expression_builder else [])
            + [('zoom_in', 'Zoom In'), ('zoom_out', 'Zoom Out'), ('view_area', 'View Area'), ('fit', 'View All')])


_SELECT = [('select', 'Select'), ('select_text', 'Select Text'), ('select_shape', 'Select Shape')]
_HDL_TOOLS = [('generate_open', 'View Generated HDL'), ('drc', 'Run Design Rule Checks')]


def task_keys(flow: str, through_blocks: bool) -> list[str]:
    """Keys of the Run ... commands of a task flow ('check', 'generate', ...): Run Single, [Run Through
    Blocks, Run Through Components,] Run Through Components from the Design Root."""
    return [flow] + ([flow + '_blocks', flow + '_components'] if through_blocks else []) + [flow + '_root']


def _tasks(through_blocks: bool) -> list:
    """The Tasks toolbar: the flows of the Tasks menu, each a button with its Run ... drop-down."""
    def flow(key, text):
        return [(k, text) for k in task_keys(key, through_blocks)]
    return [flow('check', 'Check'), ('registers', 'Registers'), flow('generate', 'Generate'),
            flow('simulate', 'Simulate'), flow('synthesize', 'Synthesize')]


# [(toolbar title, entries)]: '|' is a separator, (key, text) a button, a list a drop-down button
FSM_TOOLBARS = [
    ('Standard', _standard(True)),
    ('State Diagram Tools', [
        _SELECT, ('comment', 'Text'), ('pan', 'Panning'), '|',
        ('clock', 'Add Clock'), ('reset', 'Add Reset'), ('recovery', 'Add Recovery State Point'),
        ('enable', 'Add Enable'), '|',
        ('state', 'Add State'), ('transition', 'Add Transition'), ('interrupt', 'Add Interrupt Point'),
        ('link', 'Add Link'), [('junction_if', 'Add Junction'), ('junction_case', 'Add Junction (CASE)')], '|',
        ('hier_state', 'Add Hierarchical State'), ('wait_state', 'Add Wait State'), '|', ('panel', 'Add Panel')]),
    ('HDL Tools', _HDL_TOOLS),
    ('Tasks', _tasks(False)),
]

BD_TOOLBARS = [
    ('Standard', _standard(False)),
    ('Block Diagram Tools', [
        _SELECT, ('comment', 'Text'), ('pan', 'Panning'), '|',
        [('highlight', 'Highlight Net'), ('highlight_hier', 'Highlight Net (in hierarchy)')],
        ('clear_highlight', 'Clear Net Highlighting'), '|',
        ('block', 'Add Block'), ('component', 'Add Component'), ('moduleware', 'Add ModuleWare'), '|',
        ('external_ip', 'Add External IP'), ('embedded', 'Add Embedded Block'),
        [('frame', 'Add Frame'), ('frame_if', 'Add Frame (IF)'), ('frame_else', 'Add Frame (ELSE)')], '|',
        [('wire', 'Add Signal'), ('wire_port', 'Add Signal with a Port')],
        [('bus', 'Add Bus'), ('bus_port', 'Add Bus with a Port'), ('bus_ripper', 'Add Bus with a Ripper')],
        [('bundle', 'Add Bundle'), ('bundle_ripper', 'Add Bundle with a Ripper')], '|',
        [('port_in', 'Add Port In'), ('port_out', 'Add Port Out'), ('port_inout', 'Add Port InOut'),
         ('port_buffer', 'Add Port Buffer'), ('port_master', 'Add Port Master'), ('port_slave', 'Add Port Slave')],
        ('global_connector', 'Add Global Connector'), '|',
        ('panel', 'Add Panel'), ('edit_ibd', 'Edit as IBD'), ('visualize_ibd', 'Visualize as IBD')]),
    ('HDL Tools', _HDL_TOOLS),
    ('Tasks', _tasks(True)),
]

# Shortcuts and mnemonic keys of the legacy editors (Graphical Editors User Manual,
# "Diagram View Editing", "State Diagram" and "Block Diagram" command tables).
COMMON_KEYS = {
    'save': ['Ctrl+S'], 'print': ['Ctrl+P'], 'open_up': ['Ctrl+Shift+O'], 'cut': ['Ctrl+X'], 'copy': ['Ctrl+C'],
    'paste': ['Ctrl+V'], 'delete': ['Del', 'Backspace'], 'select_all': ['Ctrl+A'], 'undo': ['Ctrl+Z'],
    'redo': ['Ctrl+Y'], 'find': ['Ctrl+F'], 'replace': ['Ctrl+H'], 'object_props': ['Alt+Return'],
    'edit_text': ['F2'], 'zoom_in': ['Shift+Up', 'Ctrl++'], 'zoom_out': ['Shift+Down', 'Ctrl+-'],
    'view_area': ['Shift+Home'], 'fit': ['Home'], 'select': ['Esc'], 'generate_open': ['Ctrl+G'],
    'generate': ['Shift+G'],
}
FSM_KEYS = {
    **COMMON_KEYS, 'state': ['F3', 'S'], 'hier_state': ['Shift+F2', 'H'], 'interrupt': ['I'],
    'link': ['F4', 'L'], 'junction_if': ['J'], 'transition': ['F7', 'T'],
    'wait_state': ['Ctrl+F3', 'W'],          # as the legacy tool shows it in Add (F8 is Input Port there)
    'add_input_port': ['F8'], 'add_output_port': ['F9'], 'add_inout_port': ['F11'], 'add_machine': ['Ctrl+F2'],
}
BD_KEYS = {
    **COMMON_KEYS, 'block': ['Ctrl+F3', 'B'], 'component': ['F3', 'C'], 'embedded': ['F4', 'E'],
    'wire': ['F7', 'S'], 'bus': ['Shift+F7', 'U'], 'bundle': ['Ctrl+F7', 'N'], 'port_in': ['F8', 'I'],
    # Port Out / Port InOut keys as the legacy tool shows them in its Add menu; Global Connector has
    # no function key there (F5 is View > Refresh)
    'port_out': ['Shift+F8', 'O'], 'port_inout': ['F9', 'T'], 'port_buffer': ['F'],
    'global_connector': ['G'], 'frame': ['F6'], 'frame_if': ['Shift+F6'], 'frame_else': ['Alt+F6'],
    'add_stubs': ['Ctrl+F10'], 'add_stubs_ports': ['Shift+F10'], 'disconnect': ['Shift+Alt+C'],
    'open_down': ['Ctrl+D'],
}

# menu labels that must tell drop-down entries apart
_LABELS = {'junction_if': 'Junction (&IF)', 'junction_case': 'Junction (&CASE)',
           'highlight': 'Highlight Net (in &diagram)', 'highlight_hier': 'Highlight Net (in &hierarchy)',
           'clear_highlight': 'Clear Net &Highlighting'}


def apply_names(actions: dict[str, QAction], keys: dict[str, list[str]]) -> None:
    """Give every action its legacy menu label, tooltip, status-bar text and shortcuts."""
    for key, a in actions.items():
        menu, tip, desc = COMMANDS.get(key, ('', '', ''))
        label = _LABELS.get(key) or menu or tip
        if label:
            a.setText(label)
        if key in keys:
            a.setShortcuts([QKeySequence(k) for k in keys[key]])
        tip = tip or label.replace('&', '').replace('...', '')
        shortcut = ', '.join(QKeySequence(k).toString(QKeySequence.NativeText) for k in keys.get(key, []))
        if a.isEnabled():
            a.setToolTip(f'{tip} ({shortcut})' if shortcut else tip)
        if desc:
            a.setStatusTip(desc)



def _action(win: QMainWindow, actions: dict[str, QAction], key: str, text: str) -> QAction:
    """The action for toolbar entry `key`, created disabled ("not available in this version") when
    the editor has none; gives it its icon.
    """
    a = actions.get(key)
    if a is None:
        a = QAction(text, win)
        a.setEnabled(False)
        a.setToolTip(text)
        a.setStatusTip(f'{text}: not available in this version')
        actions[key] = a
    a.setIcon(editor_icon(key))
    if not a.toolTip() or a.toolTip() == a.text():
        a.setToolTip(text)
    return a


def build_toolbars(win: QMainWindow, actions: dict[str, QAction], spec: list,
                   keys: dict[str, list[str]] | None = None) -> list[QToolBar]:
    """Build the toolbars of an editor window from `spec` (FSM_TOOLBARS / BD_TOOLBARS): '|' is a
    separator, a (key, text) tuple a button, a list a button with a drop-down menu (a one-entry
    list: a button with a drop-down arrow, as New). Then give every action its legacy name, tool tip
    and shortcuts (apply_names). Returns the toolbars, in order.
    """
    bars = []
    for title, entries in spec:
        tb = QToolBar(title, win)
        tb.setObjectName('tb_' + title.lower().replace(' ', '_'))
        tb.setIconSize(QSize(16, 16))
        win.addToolBar(tb)
        bars.append(tb)
        for entry in entries:
            if entry == '|':
                tb.addSeparator()
            elif isinstance(entry, list):
                items = [_action(win, actions, k, t) for k, t in entry]
                btn = QToolButton()
                menu = items[0].menu() if len(items) == 1 and items[0].menu() else QMenu(btn)
                if menu.parent() is btn:
                    for a in items:
                        menu.addAction(a)
                btn.setMenu(menu)
                btn.setPopupMode(QToolButton.MenuButtonPopup)
                btn.setDefaultAction(items[0])
                if items[0].isCheckable():
                    # a tool button shows the last tool picked from its menu, as in the legacy tool
                    menu.triggered.connect(lambda a, b=btn: a.isCheckable() and b.setDefaultAction(a))
                tb.addWidget(btn)
            else:
                tb.addAction(_action(win, actions, *entry))
    apply_names(actions, keys or COMMON_KEYS)
    return bars


def fill_toolbars_menu(win: QMainWindow, menu: QMenu) -> None:
    """Fill View > Toolbars as the legacy tool lists it: Tooltips (tool tips on the toolbar buttons),
    one entry per toolbar in alphabetical order (the legacy toolbars this version does not have
    greyed), then Settings... ."""
    menu.clear()
    tips = menu.addAction('Tooltips')
    tips.setCheckable(True)
    tips.setChecked(getattr(win, 'toolbar_tooltips', True))
    tips.toggled.connect(lambda on: setattr(win, 'toolbar_tooltips', on))
    entries: dict[str, QAction | None] = {tb.windowTitle(): tb.toggleViewAction() for tb in win.findChildren(QToolBar)}
    for name in ('Appearance', 'Arrange Object', 'Comment Graphics', 'Format Text'):
        entries.setdefault(name, None)
    for name in sorted(entries):
        a = entries[name]
        if a is None:
            menu.addAction(name).setEnabled(False)
        else:
            a.setText(name)
            menu.addAction(a)
    menu.addSeparator()
    menu.addAction('Settings...').setEnabled(False)

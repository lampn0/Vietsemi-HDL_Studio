"""The state diagram editor window (MainWindow).

Layout, as in the legacy tool: the diagram canvas (diagram.FsmScene / FsmGraphicsView) in the
middle, one page at a time (State Diagram, Signals Table, Parameters Table: the tab bar is
hidden, pages are reached from the Structure Navigator and the menus), the Diagram Browser
(Structure Navigator + Content) on the right, and HDL Studio's own Properties / Messages docks,
hidden at start.

Data flow:
  - the window owns the FsmView (`self.view`) and the machine shown (`self.machine`);
  - FsmScene edits that model directly and emits `changed_model`; model_changed() then marks
    the window dirty, records an undo step (undo.SnapshotUndo) and schedules regenerate(),
    which regenerates the HDL text (shown in the hidden code pane and used for warnings);
  - saving goes through the EditorContext when the window was opened from the Design Manager
    (locks, write-back to the legacy tool .sm), or straight to a file when standalone.
"""
from __future__ import annotations

from version import APP_NAME
from .branding import install_app_icon, show_about
import os

from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QDockWidget, QGraphicsItem, QFileDialog, QInputDialog, QLabel,
                               QListWidget, QMainWindow, QMessageBox,
                               QSplitter, QTableWidget, QTabWidget, QToolBar,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from codegen.fsm_codegen import generate
from examples import traffic_light
from formats.import_sm import import_sm
from formats.names import META_DIR
from model import ENCODINGS, LANGUAGES, STATE_DECLS, FsmView, State, Transition
from .code_view import CodeView
from .diagram import FsmGraphicsView, FsmScene, _BoxItem, apply_select_filter
from .icons import icon
from . import editor_common as EC
from .menus import arrange_menus, fsm_menus, table_menus
from .toolbars import FSM_KEYS, FSM_TOOLBARS, build_toolbars, fill_toolbars_menu
from .panels import PanelCommands
from .props import PropertiesPanel
from .tables import ParametersTable, SignalsTable
from .undo import SnapshotUndo, load_view_state, save_view_state

MONO = QFont('Courier New', 9)
LANG_LABEL = {'systemverilog': 'SystemVerilog', 'verilog': 'Verilog 2005'}


class MainWindow(QMainWindow, PanelCommands):
    """State machine editor. Standalone (files chosen by the user) or opened
    from the Design Manager with an EditorContext (library/unit/view)."""

    def __init__(self, view: FsmView | None = None, context=None):
        """Build the window. `view` is the FsmView to edit (the traffic light example when None);
        `context` is the EditorContext given by the Design Manager (None = standalone editor).
        """
        super().__init__()
        install_app_icon()                  # Vietsemi mark (also when run on its own)
        self.context = context
        self.view: FsmView = view or traffic_light()
        self.machine = self.view.machines[0]
        self.path: str | None = None
        self.dirty = False

        self.scene = FsmScene(self)
        self.canvas = FsmGraphicsView(self.scene)
        self.signals_tab = SignalsTable()
        self.params_tab = ParametersTable()
        self.code = CodeView()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.canvas, 'State Diagram')
        self.tabs.addTab(self.signals_tab, 'Signals Table')
        self.tabs.addTab(self.params_tab, 'Parameters Table')
        # as in the legacy tool one page at a time, reached from the Structure Navigator and the menus
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(lambda _i: (self.update_title(), self._sync_nav()))
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tabs)
        code_box = QWidget(); cl = QVBoxLayout(code_box); cl.setContentsMargins(0, 0, 0, 0)
        self.code_title = QLabel()
        cl.addWidget(self.code_title); cl.addWidget(self.code)
        split.addWidget(code_box)
        split.setSizes([900, 600])
        code_box.hide()                 # The legacy tool has no HDL pane in the diagram window (HDL > View Generated HDL)
        self.code_pane = code_box
        self.setCentralWidget(split)

        self.props = PropertiesPanel()
        dock = QDockWidget('Properties', self); dock.setWidget(self.props)
        dock.setObjectName('props')
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        # Diagram Browser on the right with the Structure Navigator, as in the legacy tool
        # Content (under the navigator, as in the legacy tool): the objects of the machine by kind
        from .diagram_browser import DiagramBrowser
        self.browser = DiagramBrowser(['Name', 'Concurrent Machine'])
        self.nav, self.content = self.browser.navigator, self.browser.content
        self.content.itemClicked.connect(self._content_clicked)
        nav_dock = QDockWidget('Diagram Browser', self); nav_dock.setWidget(self.browser)
        nav_dock.setTitleBarWidget(QWidget())       # the browser draws its own vertical tab
        nav_dock.setObjectName('nav')
        self.addDockWidget(Qt.RightDockWidgetArea, nav_dock)
        self.nav_dock, self.props_dock = nav_dock, dock
        self.log = QListWidget(); self.log.setFont(MONO)
        log_dock = QDockWidget('Messages', self); log_dock.setWidget(self.log)
        log_dock.setObjectName('log')
        self.addDockWidget(Qt.BottomDockWidgetArea, log_dock)
        self.log_dock = log_dock
        self.resizeDocks([log_dock], [110], Qt.Vertical)
        self.resizeDocks([dock, nav_dock], [330, 300], Qt.Horizontal)
        # HDL Studio's own panels: kept, hidden at start so the window looks like the legacy tool
        dock.hide()
        log_dock.hide()

        self.undo_stack = SnapshotUndo(lambda: self.view.to_json(), self._restore_snapshot, self)
        self._build_actions()
        self.undo_stack.changed.connect(self._update_undo_actions)
        for text, widget in (('Signals Table', self.signals_tab), ('Parameters Table', self.params_tab)):
            a = QAction(text, self)
            a.triggered.connect(lambda checked=False, w=widget: self.tabs.setCurrentWidget(w))
            self.addAction(a)
        about = QAction(f'About {APP_NAME}', self)
        about.triggered.connect(lambda: show_about(self, 'State machine editor'))
        self.addAction(about)
        self._build_menu_commands()
        self._build_toolbars()
        self._diagram_menus = lambda: fsm_menus(standalone=self.context is None, machines=self._fill_open_machine,
                                                delete_machine=self._fill_delete_machine,
                                                toolbars=lambda m: fill_toolbars_menu(self, m),
                                                windows=lambda m: EC.fill_windows_menu(self, m))
        arrange_menus(self, self._diagram_menus())
        # the Signals / Parameters Table pages: their own menus and toolbars (table_page.py)
        from .table_page import TablePages, fill_machine_tables
        self.table_pages = TablePages(
            self, 'fsm', {'signals': self.signals_tab, 'parameters': self.params_tab}, self.canvas,
            self._diagram_menus,
            lambda: table_menus(True, standalone=self.context is None, toolbars=lambda m: fill_toolbars_menu(self, m),
                                windows=lambda m: EC.fill_windows_menu(self, m),
                                machines=lambda m: fill_machine_tables(self, m)),
            FSM_KEYS)
        self.statusBar().addWidget(QLabel('Ready'))      # as the legacy tool when no message is shown
        self.regen_timer = QTimer(self); self.regen_timer.setSingleShot(True); self.regen_timer.setInterval(250)
        self.regen_timer.timeout.connect(self.regenerate)

        self.scene.changed_model.connect(self.model_changed)
        self.scene.selectionChanged.connect(self.on_selection)
        self.scene.selectionChanged.connect(self.update_menu_states)
        QApplication.clipboard().dataChanged.connect(self.update_menu_states)
        self.scene.edit_requested.connect(self.edit_object)
        self.scene.message.connect(lambda m: self.statusBar().showMessage(m, 5000))
        self.scene.condition_edit_requested.connect(self.edit_condition_inline)
        self.scene.rename_requested.connect(self.rename_state_inline)
        self.scene.text_edit_requested.connect(self.edit_text_inline)
        self.scene.popup_requested.connect(self.show_popup)
        self.scene.comment_add_requested.connect(self.add_comment)
        self.scene.open_down_requested.connect(lambda st: self.show_level(st.id))
        self.scene.panel_add_requested.connect(self.add_panel)
        self.scene.comment_edit_requested.connect(self.edit_comment)
        # a double-click on a declaration block: the page where its text is edited
        self.scene.decl_edit_requested.connect(
            lambda key: self.tabs.setCurrentWidget(self.signals_tab) if key == 'status' else self.edit_decl_block(key))
        self.props.changed.connect(self.on_prop_changed)
        self.signals_tab.changed.connect(self.on_table_changed)
        self.params_tab.changed.connect(self.model_changed)
        self.nav.itemClicked.connect(self.on_nav)

        self.resize(1600, 950)
        self.load_view(self.view, None)
        if self.context is not None and self.context.readonly:
            for mode, a in self.mode_actions.items():
                a.setEnabled(mode == 'select')
            self.props.setEnabled(False)
            for t in (self.signals_tab, self.params_tab):
                t.set_readonly(True)
            self.scene.readonly = True
            self.statusBar().showMessage('Read-only: ' + self.context.readonly_reason)

    # -- actions --------------------------------------------------------------------
    def _build_actions(self):
        """The actions of the editor: file commands (different standalone / in a project), edit, view
        and zoom commands, one checkable action per tool (Select, Add State, ...), the toolbar
        (toolbars.build_toolbar) and the generation toolbar (language, state declaration, encoding).
        """
        mb = self.menuBar()
        fm = mb.addMenu('&File')
        self.act_open_generated = None
        if self.context is None:
            self._act(fm, '&New', self.new_file, QKeySequence.New)
            self._act(fm, '&Open...', self.open_file, QKeySequence.Open)
            self._act(fm, '&Import state machine (.sm)...', self.import_file)
            fm.addSeparator()
            self.act_save = self._act(fm, '&Save', self.save_file, QKeySequence.Save, 'save')
            self._act(fm, 'Save &As...', self.save_as)
            self.act_generate = self._act(fm, '&Generate (export HDL)...', self.export_hdl, 'Shift+G', 'generate')
            fm.addSeparator()
            self._act(fm, 'E&xit', self.close)
        else:
            self.act_save = self._act(fm, '&Save', self.save_file, QKeySequence.Save, 'save')
            self.act_generate = self._act(fm, '&Generate HDL', self.generate_hdl, 'Shift+G', 'generate')
            self._act(fm, 'Save and Generate', lambda: (self.save_file(), self.generate_hdl()), 'Ctrl+Shift+G')
            self.act_open_generated = self._act(fm, 'Open generated HDL',
                                                lambda: self.context.open_generated(self.view), 'Ctrl+G',
                                                'generate_open')
            fm.addSeparator()
            self._act(fm, '&Close', self.close, QKeySequence.Close)
        em = mb.addMenu('&Edit')
        self.act_undo = self._act(em, '&Undo', self.undo_stack.undo, QKeySequence.Undo, 'undo')
        self.act_redo = self._act(em, '&Redo', self.undo_stack.redo, ['Ctrl+Y', 'Ctrl+Shift+Z'], 'redo')
        em.addSeparator()
        act_del = self._act(em, '&Delete', self.scene.delete_selected, None, 'delete')
        self.act_edit_text = self._act(em, 'Edit Selected &Text', lambda: self.edit_selection(focus_text=True))
        vm = mb.addMenu('&View')
        act_fit = self._act(vm, 'View All', self.canvas.fit, None, 'fit')
        act_zin = self._act(vm, 'Zoom in', lambda: self.canvas.zoom(1.2), None, 'zoom_in')
        act_zout = self._act(vm, 'Zoom out', lambda: self.canvas.zoom(1 / 1.2), None, 'zoom_out')
        act_zlast = self._act(vm, 'Zoom Last', self.canvas.zoom_last)
        act_area = self._act(vm, 'View Area', self.view_area)
        act_all = self._act(em, 'Select All', self.select_all)

        group = QActionGroup(self); group.setExclusive(True)
        self.mode_actions = {}
        for mode, text in [('select', 'Select'), ('select_text', 'Select Text'), ('select_shape', 'Select Shapes'),
                           ('pan', 'Panning'), ('state', 'Add State'), ('transition', 'Add Transition'),
                           ('junction_if', 'Add IF Junction'), ('junction_case', 'Add CASE Junction'),
                           ('link', 'Add Link'), ('interrupt', 'Add Interrupt Point'),
                           ('recovery', 'Add Recovery State Point'), ('reset', 'Add Reset Point'),
                           ('clock', 'Add Clock Point'), ('enable', 'Add Enable'), ('wait_state', 'Add Wait State'),
                           ('hier_state', 'Add Hierarchical State'), ('comment', 'Comment Text'),
                           ('panel', 'Add Panel')]:
            a = QAction(icon(mode), text, self); a.setCheckable(True)
            a.triggered.connect(lambda checked, m=mode: self.set_mode(m))
            group.addAction(a)
            self.mode_actions[mode] = a
        self.mode_actions['select'].setChecked(True)
        act_props = QAction('Object Properties', self); act_props.triggered.connect(self.edit_selection)
        act_drc = QAction('Run Design Rule Checks', self); act_drc.triggered.connect(self.run_checks)
        self.toolbar_actions = {
            'save': self.act_save, 'undo': self.act_undo, 'redo': self.act_redo, 'object_props': act_props,
            'zoom_in': act_zin, 'zoom_out': act_zout, 'zoom_last': act_zlast, 'view_area': act_area,
            'fit': act_fit, 'drc': act_drc, 'generate': self.act_generate, 'delete': act_del,
            'select_all': act_all, 'edit_text': self.act_edit_text,
            **{k: v for k, v in self.mode_actions.items()},
        }
        if self.act_open_generated is not None:
            self.toolbar_actions['generate_open'] = self.act_open_generated
            self.toolbar_actions['generate_root'] = QAction('Generate through design root', self)
            self.toolbar_actions['generate_root'].triggered.connect(
                lambda: self.context.generate_hierarchy(self.view, self, 'root'))
        self.canvas.end_command.connect(lambda: self.set_mode('select'))
        self.canvas.tool_done.connect(lambda: self.set_mode(self._mode_before_area))
        self.canvas.nudged.connect(self.scene.changed_model.emit)
        self._mode_before_area = 'select'
        self._once = False
        self.select_filter = 'any'
        self.addAction(act_del)


    def _build_toolbars(self):
        """The legacy toolbars (Standard, State Diagram Tools, HDL Tools, Tasks: toolbars.FSM_TOOLBARS),
        then HDL Studio's own Generation toolbar (language, state declaration, encoding)."""
        self.toolbars = build_toolbars(self, self.toolbar_actions, FSM_TOOLBARS, FSM_KEYS)
        EC.install_tooltip_filter(self, self.toolbars)
        gt = QToolBar('Generation', self); gt.setObjectName('gen')
        self.addToolBar(gt)
        self.tb_lang = QComboBox(); [self.tb_lang.addItem(LANG_LABEL[l], l) for l in LANGUAGES]
        self.tb_lang.setToolTip('Target language')
        gt.addWidget(self.tb_lang)
        self.tb_decl = QComboBox(); self.tb_decl.addItems(STATE_DECLS)
        self.tb_decl.setToolTip('State declaration: parameter / localparam / enum')
        gt.addWidget(self.tb_decl)
        self.tb_enc = QComboBox(); self.tb_enc.addItems(ENCODINGS)
        self.tb_enc.setToolTip('State encoding')
        gt.addWidget(self.tb_enc)
        for cb in (self.tb_lang, self.tb_decl, self.tb_enc):
            cb.currentIndexChanged.connect(self.on_toolbar_option)

    def _act(self, menu, text, slot, key=None, icon_name: str | None = None):
        """key may be one shortcut or a list (first one is shown in menus)."""
        a = QAction(text, self)
        if icon_name:
            a.setIcon(icon(icon_name))
        if key:
            keys = [QKeySequence(k) for k in (key if isinstance(key, (list, tuple)) else [key])]
            a.setShortcuts(keys)
            a.setToolTip(f'{text.replace("&", "")}  ({", ".join(k.toString() for k in keys)})')
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def view_area(self):
        """View Area: drag a rectangle on the diagram to view that area."""
        if self.canvas.tool != 'area':
            self._mode_before_area = self.scene.mode if self.canvas.tool != 'pan' else 'pan'
        self.scene.set_mode('select')
        self.canvas.set_tool('area')
        self.statusBar().showMessage('Drag a rectangle around the area to view (Esc cancels)', 4000)

    def select_all(self):
        """Edit > Select All: select every selectable item of the diagram."""
        for it in self.scene.items():
            if it.flags() & QGraphicsItem.ItemIsSelectable:
                it.setSelected(True)

    def _is_text(self, item) -> bool:
        """True for the text items of the diagram (used by Select Text / Select Shapes)."""
        from .diagram import CommentTextItem
        return isinstance(item, (_BoxItem, CommentTextItem))

    def run_checks(self):
        """Design rule check: generator warnings plus a syntax check of the generated HDL."""
        from hdl.parser import check_text
        text, warnings = generate(self.view)
        self.log.clear()
        for w in warnings:
            self.log.addItem(f'warning: {w}')
        ext = 'sv' if self.view.language == 'systemverilog' else 'v'
        diags = [d for d in check_text(text, f'{self.view.unit}.{ext}') if d[1] == 'error']
        for line, _, msg in diags:
            self.log.addItem(f'error: generated HDL line {line}: {msg}')
        self.log.addItem(f'Design rule check: {len(diags)} error(s), {len(warnings)} warning(s)')

    def _build_menu_commands(self):
        """Commands of the legacy menu bar that the toolbar does not have (File, Edit, View, Diagram,
        Tasks, Add, Options, Window, Help), added to toolbar_actions under the keys fsm_menus() names.
        Commands without a slot are greyed (no counterpart in this version)."""
        from PySide6.QtWidgets import QMenu
        mgr = self.context.manager if self.context is not None else None
        ro = self.scene.readonly

        def act(key, text, slot=None, shortcut='', checkable=False, checked=False):
            """Create the action `key` in toolbar_actions: a check box action (`checkable`, slot gets the
            state) or a plain one; without a slot it is disabled.
            """
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                self.addAction(a)                # the shortcut works without opening the menu
            if checkable:
                a.setCheckable(True); a.setChecked(checked)
                if slot is not None:
                    a.toggled.connect(slot)
            elif slot is not None:
                a.triggered.connect(slot)
            if slot is None:
                a.setEnabled(False)
                a.setProperty('available', False)
            self.toolbar_actions[key] = a
            return a

        def edit(fn):
            """A slot for an editing command: none in a read-only diagram."""
            return None if ro else fn
        hist = EC.History.of(mgr if mgr is not None else self)
        # File
        new_content = act('new_content', 'Design Content...', mgr.new_unit if mgr else self.new_file)
        new_tb = act('new_testbench', 'Test Bench...')
        a_new = act('new', 'New', mgr.new_unit if mgr else self.new_file)
        menu = QMenu(self)
        menu.addAction(new_content); menu.addAction(new_tb)
        a_new.setMenu(menu)
        act('open_up', 'Open Up', self.open_up)
        act('open_down', 'Down', self.open_down)
        act('back', 'Back', lambda: hist.go(-1))
        act('forward', 'Forward', lambda: hist.go(1))
        act('save_as', 'Save As...', self.save_as if self.context is None else None)
        act('page_setup', 'Page Setup...', (lambda: mgr.page_setup(self)) if mgr else None)
        act('print', 'Print...', lambda: EC.print_diagram(self, self.scene))
        act('print_window', 'Print Window...', lambda: EC.print_diagram(self, self.scene, self.canvas))
        act('document', 'Single Level', lambda: EC.document_single_level(
            self, self.scene, self.view.unit, f'{self.view.library}/{self.view.unit}/{self.view.view}',
            generate(self.view)[0], self._dir()))
        act('close_window', 'Close Window', self.close)
        act('exit', 'Exit', QApplication.instance().closeAllWindows)
        # Edit
        act('cut', 'Cut', edit(self.cut))
        act('copy', 'Copy', self.copy)
        act('paste', 'Paste', edit(self.paste))
        act('paste_system', 'Paste from system clipboard', edit(self.paste_system))
        act('find', 'Find...', lambda: self.find_replace(False))
        act('replace', 'Replace...', lambda: self.find_replace(True))
        for key, text, how in (('align_left', 'Align Left', 'left'), ('align_center', 'Align Center', 'center'),
                               ('align_right', 'Align Right', 'right'), ('align_top', 'Align Top', 'top'),
                               ('align_middle', 'Align Middle', 'middle'),
                               ('align_bottom', 'Align Bottom', 'bottom')):
            act(key, text, edit(lambda checked=False, h=how: self._moved(EC.align(self._ordered_selection(), h))))
        act('distribute_h', 'Distribute Horizontally',
            edit(lambda: self._moved(EC.distribute(self.scene.selectedItems(), True))))
        act('distribute_v', 'Distribute Vertically',
            edit(lambda: self._moved(EC.distribute(self.scene.selectedItems(), False))))
        act('expression_builder', 'Expression Builder', self.expression_builder)
        # View
        act('refresh', 'Refresh', self._refresh_view, 'F5')
        act('grid', 'Grid', lambda on: (setattr(self.canvas, 'show_grid', on), self.canvas.viewport().update()),
            checkable=True, checked=getattr(self.canvas, 'show_grid', True))
        act('snap_grid', 'Snap to Grid', self._set_snap, checkable=True, checked=True)
        act('status_bar', 'Status Bar', lambda on: self.statusBar().setVisible(on), checkable=True, checked=True)
        self.object_tips = True
        act('object_tips', 'Object Tips', lambda on: setattr(self, 'object_tips', on), checkable=True, checked=True)
        self.canvas.viewport().installEventFilter(self)
        a = act('diagram_browser', 'Diagram Browser', lambda on: self.nav_dock.setVisible(on),
                checkable=True, checked=True)
        self.nav_dock.visibilityChanged.connect(a.setChecked)
        act('signals_table', 'Signals Table', lambda: self.tabs.setCurrentWidget(self.signals_tab))
        self.build_panel_actions(act, ro)
        # Diagram
        act('copy_picture', 'Copy Picture', self.copy_picture)
        act('compiler_directives', 'Compiler Directives...', self.compiler_directives)
        act('reverse_direction', 'Reverse Direction', edit(self.reverse_direction))
        act('rename_machine', 'Rename Concurrent Machine...', edit(self.rename_machine))
        for key, text, kind in (('change_state', 'State', 'state'), ('change_junction', 'Junction', 'junction'),
                                ('change_link', 'Link', 'link')):
            act(key, text, edit(lambda checked=False, k=kind: self.change_to(k)))
        act('sm_props', 'State Machine Properties...', self.machine_properties)
        # Tasks: the checks of the diagram are the Check flow here
        act('check', 'Run Single', self.run_checks)
        # Add
        for key, text, mode in (('add_input_port', 'Input Port', 'input'), ('add_output_port', 'Output Port', 'output'),
                                ('add_inout_port', 'InOut Port', 'inout'), ('add_local_signal', 'Local Signal', 'local')):
            act(key, text, edit(lambda checked=False, m=mode: self.add_signal(m)))
        act('add_machine', 'Concurrent State Machine', edit(self.add_machine))
        # Options / Window / Help
        act('main_settings', 'Main...', (lambda: mgr.main_settings(self)) if mgr else None)
        act('verilog_options', 'Verilog...', (lambda: mgr.verilog_options(self)) if mgr else None)
        act('log_window', 'Log Window', lambda: (self.log_dock.show(), self.log_dock.raise_()))
        act('design_manager', 'Design Manager',
            (lambda: (mgr.show(), mgr.raise_(), mgr.activateWindow())) if mgr else None)
        act('component_browser', 'Component Browser',
            getattr(mgr, 'show_component_browser', None) if mgr else None)
        act('shortcuts_help', 'Keyboard Shortcuts', (lambda: mgr._show_shortcuts(self)) if mgr else self._show_shortcuts)
        act('help_manuals', 'Help and Manuals', EC.open_user_guide, 'F1')
        act('regex_help', 'Regular Expressions', lambda: EC.show_regex_help(self))
        # F2 (edit the selected text) is in no legacy menu: keep its shortcut on the window
        self.addAction(self.act_edit_text)
        self._history = hist
        hist.visited(self)

    def edit_object(self, obj):
        """Double-click on an object. As in the legacy tool, a state, a transition (or its priority circle),
        a junction, a link, the clock or the reset point opens "SM Object Properties" on the page of
        that object (read-only diagram: shown, nothing applied); other points (interrupt, recovery,
        enable): HDL Studio's Properties panel (shown when hidden)."""
        from model import Junction, Link, Point, State, Transition
        if isinstance(obj, (State, Transition, Junction, Link)) or                 (isinstance(obj, Point) and obj.kind in ('clock', 'reset')):
            from .sm_props_dialog import SmObjectPropertiesDialog
            dlg = SmObjectPropertiesDialog(self.machine, [obj], self, view=self.view,
                                           readonly=self.scene.readonly)
            # Apply shows the change at once (diagram, tables, generated code), as OK does
            dlg.applied_changes.connect(self._props_applied)
            dlg.exec()
            return
        self.props.show_object(obj, self.machine)
        self.props_dock.show()
        self.props_dock.raise_()

    def _props_applied(self):
        """SM Object Properties applied: redraw the diagram and record the change (one undo step)."""
        self.scene.load(self.view, self.machine)
        self.scene.changed_model.emit()
        self.signals_tab.set_rows(self.view.signals, self.view.signals_sheet)   # clock / reset may change

    # -- clipboard ------------------------------------------------------------------------
    CLIP_MIME = 'application/x-hdlstudio-fsm'

    def _selected_nodes(self) -> list:
        """Model objects of the selected states, junctions, links and points (selection order)."""
        from .diagram import NodeItem
        return [it.obj for it in self._ordered_selection() if isinstance(it, NodeItem)]

    def copy(self):
        """Edit > Copy: the selected nodes and the transitions between them, to the clipboard (as data
        another state diagram window can paste, and as text for other programs)."""
        import json
        from dataclasses import asdict
        from PySide6.QtCore import QMimeData
        from model import Junction, Link, Point
        nodes = self._selected_nodes()
        if not nodes:
            return
        ids = {n.id for n in nodes}
        kinds = {State: 'state', Junction: 'junction', Link: 'link', Point: 'point'}
        data = {'nodes': [dict(asdict(n), _kind=kinds[type(n)]) for n in nodes if type(n) in kinds],
                'transitions': [asdict(t) for t in self.machine.transitions if t.src in ids and t.dst in ids]}
        for d in data['nodes'] + data['transitions']:
            d.pop('orig', None)
        mime = QMimeData()
        mime.setData(self.CLIP_MIME, json.dumps(data).encode())
        mime.setText('\n'.join(n.name for n in nodes if isinstance(n, State)))
        QApplication.clipboard().setMimeData(mime)
        self.statusBar().showMessage(f'Copied {len(data["nodes"])} object(s)', 3000)

    def cut(self):
        """Edit > Cut: copy, then delete the selection."""
        if self._selected_nodes():
            self.copy()
            self.scene.delete_selected()

    def can_paste(self) -> bool:
        """True when the clipboard holds state diagram objects."""
        md = QApplication.clipboard().mimeData()
        return md is not None and md.hasFormat(self.CLIP_MIME)

    def paste(self):
        """Edit > Paste: the copied objects, with new ids, offset from where they were (or under the
        mouse), states renamed when the name is taken; they are selected afterwards."""
        import json
        from model import Junction, Link, Point
        from .diagram import GRID
        if not self.can_paste() or self.machine is None:
            return
        data = json.loads(bytes(QApplication.clipboard().mimeData().data(self.CLIP_MIME)).decode())
        m = self.machine
        cls = {'state': State, 'junction': Junction, 'link': Link, 'point': Point}
        coll = {'state': m.states, 'junction': m.junctions, 'link': m.links, 'point': m.points}
        names = {s.name for s in m.states}
        new_ids: dict[str, str] = {}
        off = 2 * GRID
        added = []
        for d in data.get('nodes', []):
            kind = d.pop('_kind')
            if kind == 'point' and d.get('kind') in ('reset', 'clock', 'recovery', 'enable') and m.point(d['kind']):
                continue                        # one of each per machine
            obj = cls[kind](**{k: v for k, v in d.items() if k in cls[kind].__dataclass_fields__})
            old = obj.id
            obj.id = m.new_id({'state': 's', 'junction': 'j', 'link': 'l', 'point': 'p'}[kind])
            new_ids[old] = obj.id
            obj.x += off; obj.y += off
            obj.parent = ''
            if isinstance(obj, State):
                if obj.actions_x is not None:
                    obj.actions_x += off; obj.actions_y += off
                base, k = obj.name, 0
                while obj.name in names:
                    k += 1
                    obj.name = f'{base}_{k}'
                names.add(obj.name)
            coll[kind].append(obj)
            added.append(obj.id)
        for d in data.get('transitions', []):
            if d['src'] in new_ids and d['dst'] in new_ids:
                t = Transition(**{k: v for k, v in d.items() if k in Transition.__dataclass_fields__})
                t.id, t.src, t.dst = m.new_id('t'), new_ids[d['src']], new_ids[d['dst']]
                t.points = [[x + off, y + off] for x, y in t.points]
                if t.label_x is not None:
                    t.label_x += off; t.label_y += off
                m.transitions.append(t)
        self.scene.load(self.view, self.machine)
        for oid in added:
            it = self.scene.item_for(oid)
            if it is not None:
                it.setSelected(True)
        self.build_nav()
        self.scene.changed_model.emit()

    # -- selection helpers ------------------------------------------------------------------
    def _track_selection(self):
        """Keep the selected items in the order the user selected them (Align lines up on the first)."""
        sel = self.scene.selectedItems()
        order = [i for i in getattr(self, '_sel_order', []) if i in sel]
        order += [i for i in sel if i not in order]
        self._sel_order = order

    def _ordered_selection(self) -> list:
        self._track_selection()
        return list(self._sel_order)

    def _moved(self, moved: bool):
        """After Align / Distribute: one undo step when something moved."""
        if moved:
            self.scene.refresh_all()
            self.scene.changed_model.emit()

    def update_menu_states(self):
        """Grey what has nothing to act on, as the legacy tool: Cut / Copy / Delete without a selection,
        Paste without copied objects, Align with fewer than two objects, Reverse Direction without a
        transition, Back / Forward at the ends of the window history, the Add commands of points
        a machine has already (one clock, reset, recovery point and enable each)."""
        from .diagram import NodeItem, TransitionItem
        ro = self.scene.readonly
        sel = self.scene.selectedItems()
        acts = self.toolbar_actions
        EC.update_edit_states(acts, [i for i in self._ordered_selection() if isinstance(i, (NodeItem, TransitionItem))],
                              self.can_paste(), ro)
        acts['copy'].setEnabled(bool(self._selected_nodes()))
        acts['cut'].setEnabled(bool(self._selected_nodes()) and not ro)
        self.update_panel_states(ro)
        acts['paste_system'].setEnabled(not ro and bool(QApplication.clipboard().text().strip()))
        acts['reverse_direction'].setEnabled(not ro and any(isinstance(i, TransitionItem) for i in sel))
        nodes = [o for o in self._selected_nodes() if type(o).__name__ in ('State', 'Junction', 'Link')]
        for key, cls in (('change_state', 'State'), ('change_junction', 'Junction'), ('change_link', 'Link')):
            acts[key].setEnabled(not ro and any(type(o).__name__ != cls for o in nodes))
        acts['open_down'].setEnabled(any(isinstance(getattr(i, 'obj', None), State) and i.obj.hier for i in sel))
        acts['open_up'].setEnabled(bool(self.scene.level) or self.context is not None)
        hist = getattr(self, '_history', None)
        if hist is not None:
            acts['back'].setEnabled(hist.can_go(-1))
            acts['forward'].setEnabled(hist.can_go(1))
        m = self.machine
        for kind in ('clock', 'reset', 'recovery', 'enable'):
            a = self.mode_actions.get(kind)
            if a is not None and not ro:
                a.setEnabled(m is None or m.point(kind) is None or a.isChecked())

    def changeEvent(self, e):
        """Activating the window records it in the Back / Forward history."""
        if e.type() == QEvent.ActivationChange and self.isActiveWindow() and getattr(self, '_history', None):
            self._history.visited(self)
            self.update_menu_states()
        super().changeEvent(e)

    def eventFilter(self, obj, e):
        """View > Object Tips off: no tool tips over the diagram."""
        if obj is self.canvas.viewport() and e.type() == QEvent.ToolTip and not getattr(self, 'object_tips', True):
            return True
        return super().eventFilter(obj, e)

    # -- Edit / View / Diagram commands --------------------------------------------------
    def find_replace(self, replace: bool):
        """Edit > Find... / Replace...: the legacy Find and Replace dialog (find_dialog.py) over the
        texts of the diagram, by the legacy tool's object kinds: state names and actions, transition
        conditions and actions, comment texts, declaration blocks, State Machine Properties names
        and the columns of the Signals Table. Find Next opens a text in place with the match
        selected; one dialog per window, kept between uses."""
        from .find_dialog import FSM_KINDS, FindReplaceDialog
        dlg = getattr(self, '_find_dialog', None)
        if dlg is None:
            dlg = FindReplaceDialog(self, self._find_fields, self._find_done, FSM_KINDS, self._diagram_name(),
                                    replace, self.scene.readonly)
            self._find_dialog = dlg
        dlg.diagram = self._diagram_name()
        dlg.open_tab(replace)

    def _diagram_name(self) -> str:
        v = self.view
        return f'{v.library}/{v.unit}/{v.view} [{self.machine.name if self.machine else ""}]'

    def _find_done(self):
        """After a replacement: draw the diagram again, one undo step."""
        self.scene.load(self.view, self.machine)
        self.signals_tab.set_rows(self.view.signals, self.view.signals_sheet)
        self.build_nav()
        self.update_title()
        self.scene.changed_model.emit()

    def _find_fields(self) -> list:
        """The texts Find and Replace searches, as find_dialog.TextField records."""
        from .diagram import DeclBlockItem
        from .find_dialog import TextField
        m, v, sc = self.machine, self.view, self.scene
        if m is None:
            return []

        def attr(obj, name):
            return (lambda: getattr(obj, name) or ''), (lambda val: setattr(obj, name, val))

        def on_diagram(obj_id, level=''):
            """A function selecting a node / transition (at its level of the diagram) and showing it."""
            def run(add=False):
                self.tabs.setCurrentWidget(self.canvas)
                if level != sc.level:
                    self.show_level(level)
                it = sc.item_for(obj_id) or sc.trans_items.get(obj_id)
                if it is not None:
                    if not add:
                        sc.clearSelection()
                    it.setSelected(True)
                    self.canvas.centerOn(it)
            return run

        def in_place(select, item_of, field):
            """Show a text: its object selected, then the text opened in place with the match selected
            (field None: the name of a state)."""
            def run(span):
                EC.mark_text(None, None)
                select(False)
                item = item_of()
                if item is None:
                    return
                if sc.readonly:
                    EC.mark_text(item, span) if hasattr(item, 'find_span') else None
                    return
                self.activateWindow()
                if field is None:
                    self.rename_state_inline(item, span)
                else:
                    self.edit_text_inline(item, field, span)
            return run

        def marked(select, item_of):
            """Show a text without an in-place editor (a comment text): selected, the match marked."""
            def run(span):
                select(False)
                EC.mark_text(item_of(), span)
            return run

        def only_select(select):
            return lambda span: select(False)

        out = []

        def rename(state):
            def run(new):
                for lk in m.links:                  # links to the state follow its name
                    if lk.target == state.name:
                        lk.target = new
                state.name = new
            return run
        for st in m.states:
            sel = on_diagram(st.id, st.parent)
            out.append(TextField('State name', f'State name of {st.name}', lambda st=st: st.name, rename(st),
                                 in_place(sel, lambda st=st: sc.item_for(st.id), None), sel))
            for a, label in (('entry_actions', 'On-Entry actions for State'), ('in_actions', 'Actions for State'),
                             ('exit_actions', 'On-Exit actions for State')):
                if getattr(st, a):
                    g, w = attr(st, a)
                    out.append(TextField('State actions', f'{label} {st.name}', g, w,
                                         in_place(sel, lambda st=st: sc.action_boxes.get(st.id), a), sel))
        for t in m.transitions:
            src, dst = m.node(t.src), m.node(t.dst)
            name = f'{getattr(src, "name", t.src)} -> {getattr(dst, "name", getattr(dst, "target", t.dst))}'
            sel = on_diagram(t.id, getattr(src, 'parent', ''))
            label = (lambda t=t: getattr(sc.trans_items.get(t.id), 'label', None))
            for a, kind, what in (('cond', 'Transition conditions', 'Condition'),
                                  ('actions', 'Transition actions', 'Actions')):
                if getattr(t, a):
                    g, w = attr(t, a)
                    out.append(TextField(kind, f'{what} of Transition {name}', g, w, in_place(sel, label, a), sel))
        for lk in m.links:
            sel = on_diagram(lk.id, lk.parent)
            g, w = attr(lk, 'target')
            out.append(TextField('State name', f'Link to {lk.target}', g, w,
                                 in_place(sel, lambda lk=lk: sc.item_for(lk.id), 'target'), sel))
        for j in m.junctions:
            if j.expr:
                sel = on_diagram(j.id, j.parent)
                g, w = attr(j, 'expr')
                out.append(TextField('Transition conditions', 'CASE junction expression', g, w,
                                     in_place(sel, lambda j=j: sc.item_for(j.id), 'expr'), sel))
        for c in m.comments:
            sel = on_diagram(c.id)
            g, w = attr(c, 'text')
            out.append(TextField('Comment text', 'Comment text', g, w,
                                 marked(sel, lambda c=c: sc.item_for(c.id)), sel))

        def block(key):
            return lambda: next((i for i in sc.items() if isinstance(i, DeclBlockItem) and i.key == key), None)

        def block_select(key):
            def run(add=False):
                if sc.level:
                    self.show_level('')
                self.tabs.setCurrentWidget(self.canvas)
                it = block(key)()
                if it is not None:
                    if not add:
                        sc.clearSelection()
                    it.setSelected(True)
                    self.canvas.centerOn(it)
            return run
        for kind, key, a, name in (
                ('Compiler Directives', 'compdir', 'pre_module_directives', 'Pre-module directives'),
                ('Compiler Directives', 'compdir', 'post_module_directives', 'Post-module directives'),
                ('Compiler Directives', 'compdir', 'end_module_directives', 'End-module directives'),
                ('Process Declaration Block', 'concurrent', 'concurrent_statements', 'Concurrent Statements'),
                ('Process Declaration Block', 'statereg', 'state_register_statements',
                 'State Register Statements'),
                ('Process Declaration Block', 'global', 'global_pre_actions', 'Global Pre Actions'),
                ('Process Declaration Block', 'global', 'global_post_actions', 'Global Post Actions')):
            if getattr(v, a):
                g, w = attr(v, a)
                sel = block_select(key)
                out.append(TextField(kind, name, g, w, in_place(sel, block(key), a), sel))
        for a, name in (('name', 'Machine name'), ('current_state_name', 'Current state variable'),
                        ('next_state_name', 'Next state variable')):
            g, w = attr(m, a)
            out.append(TextField('State machine properties', name, g, w,
                                 lambda span: self.machine_properties(), None))

        def cell(sig, a):
            def run(span=None):
                self.tabs.setCurrentWidget(self.signals_tab)
                tbl = self.signals_tab.table
                r, c = self.signals_tab.row_of(sig), self.signals_tab.column_of(a)
                if r >= 0 and c >= 0:
                    tbl.setCurrentCell(r, c)
                    tbl.scrollToItem(tbl.item(r, c))
            return run
        for sig in v.signals:
            for a, kind in (('name', 'Signals Name Column'), ('mode', 'Signals Mode Column'),
                            ('type', 'Signals Type Column'), ('bounds', 'Signals Bounds Column'),
                            ('category', 'Signals Category Column'), ('expression', 'Signals Expression Column'),
                            ('scheme', 'Signals Scheme Column'), ('default', 'Signals Default Column'),
                            ('reset', 'Signals Reset Column'), ('comment', 'Signals Comment Column'),
                            ('group', 'Group Column/Row'), ('value', 'Signals Initial Column'),
                            ('delay', 'Signals Delay Column')):
                if not getattr(sig, a, ''):
                    continue
                g, w = attr(sig, a)
                writable = a not in ('mode', 'category', 'scheme')       # choices, not free text
                out.append(TextField(kind, f'{kind} ({sig.name})', g, w if writable else None, cell(sig, a), None))
        return out

    def expression_builder(self):
        """Edit > Expression Builder: build a condition from the signals and operators of the diagram
        and put it on the selected transition (or copy it)."""
        from .expression_builder import ExpressionBuilder
        sel = [i.obj for i in self.scene.selectedItems() if isinstance(getattr(i, 'obj', None), Transition)]
        t = sel[0] if len(sel) == 1 else None
        dlg = ExpressionBuilder(self, [s.name for s in self.view.signals], t.cond if t else '',
                                target='transition condition' if t else '')
        if dlg.exec() and t is not None and not self.scene.readonly and dlg.text() != t.cond:
            t.cond = dlg.text()
            self.scene.refresh_transitions_from(t.src)
            self.scene.changed_model.emit()

    def _refresh_view(self):
        """View > Refresh: draw the diagram again from the model."""
        st = self.canvas.state()
        self.scene.load(self.view, self.machine)
        self.canvas.restore(st)

    def _set_snap(self, on: bool):
        """View > Snap to Grid: objects land on the grid when placed or moved (or anywhere)."""
        from . import diagram
        diagram.SNAP_ON[0] = on

    def copy_picture(self):
        """Diagram > Copy Picture: the selection (or the diagram) as a picture on the clipboard."""
        EC.copy_picture(self.scene)
        self.statusBar().showMessage('Picture copied to the clipboard', 3000)

    def reverse_direction(self):
        """Diagram > Reverse Direction: the selected transitions go the other way."""
        from .diagram import TransitionItem
        items = [i for i in self.scene.selectedItems() if isinstance(i, TransitionItem)]
        for it in items:
            it.reverse()
        if items:
            self.scene.changed_model.emit()

    def rename_machine(self):
        """Diagram > Rename Concurrent Machine...: a new name for the machine shown."""
        name, ok = QInputDialog.getText(self, 'Rename Concurrent Machine', 'Machine name:', text=self.machine.name)
        name = name.strip()
        if not ok or not name or name == self.machine.name:
            return
        if any(m.name == name for m in self.view.machines):
            QMessageBox.warning(self, 'Rename Concurrent Machine', f'A machine called {name} exists already.')
            return
        self.machine.name = name
        self.build_nav()
        self.update_title()
        self.model_changed()

    def _fill_open_machine(self, menu):
        """Diagram > Open Machine: one entry per concurrent machine; the one shown is checked."""
        menu.clear()
        for m in self.view.machines:
            a = menu.addAction(m.name)
            a.setCheckable(True)
            a.setChecked(m is self.machine)
            a.triggered.connect(lambda checked=False, x=m: self.show_machine(x))

    def _fill_delete_machine(self, menu):
        """Diagram > Delete Machine: one entry per concurrent machine (the last one cannot go)."""
        menu.clear()
        for m in self.view.machines:
            a = menu.addAction(m.name)
            a.setEnabled(len(self.view.machines) > 1 and not self.scene.readonly)
            a.triggered.connect(lambda checked=False, x=m: self.delete_machine(x))

    def show_machine(self, m):
        """Show concurrent machine `m` in the diagram."""
        if m is self.machine:
            return
        self.machine = m
        self.scene.level = ''
        self.scene.load(self.view, m)
        apply_select_filter(self.scene, getattr(self, 'select_filter', 'any'), self._is_text)
        self.sync_toolbar()
        self.build_nav()
        self.update_title()
        self.canvas.fit()

    def delete_machine(self, m):
        """Diagram > Delete Machine > name: remove that concurrent machine (after asking)."""
        if len(self.view.machines) < 2:
            return
        if QMessageBox.question(self, 'Delete Machine', f'Delete the state machine {m.name} and all its states?') \
                != QMessageBox.Yes:
            return
        self.view.machines.remove(m)
        if m is self.machine:
            self.machine = None
            self.show_machine(self.view.machines[0])
        self.build_nav()
        self.model_changed()

    def add_machine(self):
        """Add > Concurrent State Machine: a new, empty machine in the same module, shown at once."""
        from model import Machine
        names = {m.name for m in self.view.machines}
        k = len(self.view.machines)
        while f'csm{k}' in names:
            k += 1
        cur = self.machine
        m = Machine(name=f'csm{k}', current_state_name=f'csm{k}_current_state',
                    next_state_name=f'csm{k}_next_state', encoding=cur.encoding if cur else 'sequential',
                    state_decl=cur.state_decl if cur else 'parameter')
        self.view.machines.append(m)
        self.show_machine(m)
        self.model_changed()

    def add_signal(self, mode: str):
        """Add > Input Port / Output Port / InOut Port / Local Signal: a new row of the Signals Table
        (shown, with the new name ready to edit)."""
        from model import Signal
        names = {s.name for s in self.view.signals}
        base = {'input': 'in', 'output': 'out', 'inout': 'io', 'local': 'sig'}[mode]
        k = 0
        while f'{base}{k}' in names:
            k += 1
        sig = Signal(name=f'{base}{k}', mode=mode, type='logic' if self.view.language == 'systemverilog' else 'wire')
        self.view.signals.append(sig)
        self.signals_tab.set_rows(self.view.signals, self.view.signals_sheet)
        self.tabs.setCurrentWidget(self.signals_tab)
        self.signals_tab.edit_cell(sig, 'name')          # the new name is ready to type over
        self.model_changed()

    def change_to(self, kind: str):
        """Diagram > Change To > State / Junction / Link: the selected nodes become that kind of node, at
        the same place and with the same transitions (a link cannot start a transition: a node with
        transitions leaving it does not become a link)."""
        from model import Junction, Link
        m = self.machine
        changed = 0
        for old in self._selected_nodes():
            if type(old).__name__ == kind.capitalize() or not isinstance(old, (State, Junction, Link)):
                continue
            if kind == 'link' and m.outgoing(old.id):
                self.statusBar().showMessage(f'{getattr(old, "name", "junction")}: transitions leave it, '
                                             'it cannot become a link', 5000)
                continue
            common = dict(id=old.id, x=old.x, y=old.y, parent=old.parent)
            if kind == 'state':
                base = old.target if isinstance(old, Link) and old.target not in ('', 'Link') else                     self.scene._unique_state_name()
                name, k = base, 0
                while m.state_by_name(name) is not None:
                    k += 1
                    name = f'{base}_{k}'
                new = State(name=name, **common)
            elif kind == 'junction':
                new = Junction(symbol=getattr(self.view, 'default_junction_symbol', ''), **common)
            else:
                new = Link(target=getattr(old, 'name', 'Link'), **common)
            for coll in (m.states, m.junctions, m.links):
                if old in coll:
                    coll.remove(old)
            {'state': m.states, 'junction': m.junctions, 'link': m.links}[kind].append(new)
            changed += 1
        if changed:
            self.scene.load(self.view, m)
            self.build_nav()
            self.scene.changed_model.emit()

    # -- panels (panels.PanelCommands) ---------------------------------------------------
    def panels_model(self) -> list:
        return self.machine.panels if self.machine is not None else []

    def panel_new_id(self) -> str:
        return self.machine.new_id('pn')

    def panels_reload(self):
        self.scene.level = ''                   # panels are on the top level
        st = self.canvas.state()
        self.scene.load(self.view, self.machine)
        self.canvas.restore(st)

    def panels_changed(self):
        self.scene.changed_model.emit()

    # -- hierarchical states ------------------------------------------------------------
    def open_down(self):
        """File > Open > Down: show the inside of the selected hierarchical state."""
        st = next((i.obj for i in self.scene.selectedItems() if isinstance(getattr(i, 'obj', None), State)
                   and i.obj.hier), None)
        if st is not None:
            self.show_level(st.id)

    def open_up(self):
        """Open Up: from inside a hierarchical state, the level that holds it; from the top level, the
        diagram that instantiates this design unit (Design Manager)."""
        if self.scene.level:
            st = next((s for s in self.machine.states if s.id == self.scene.level), None)
            self.show_level(st.parent if st is not None else '')
        elif self.context is not None:
            EC.open_up(self)

    def show_level(self, level: str):
        """Show the inside of hierarchical state `level` ('' = the top level of the machine). A
        hierarchical state shown for the first time gets its entry and exit points, as the legacy
        tool draws them in a new hierarchical diagram."""
        from model import Point
        m = self.machine
        if level and not any(p.parent == level for p in m.points if p.kind in ('entry', 'exit'))                 and not self.scene.readonly:
            m.points.append(Point(m.new_id('p'), 'entry', 0.0, 0.0, parent=level))
            m.points.append(Point(m.new_id('p'), 'exit', 400.0, 0.0, parent=level))
            self.undo_stack.note_change()
        self.scene.level = level
        self.scene.load(self.view, m)
        apply_select_filter(self.scene, getattr(self, 'select_filter', 'any'), self._is_text)
        self.update_title()
        self.update_menu_states()
        self.canvas.fit()

    def level_path(self) -> str:
        """Names of the hierarchical states down to the level shown ('' at the top level)."""
        names, lv = [], self.scene.level
        by_id = {s.id: s for s in self.machine.states} if self.machine else {}
        while lv and lv in by_id:
            names.append(by_id[lv].name)
            lv = by_id[lv].parent
        return '/'.join(reversed(names))

    def add_comment(self, pos):
        """Add > Comment Text: a click on the diagram; the text is typed in a dialog (empty: nothing)."""
        from model import Comment
        text, ok = QInputDialog.getMultiLineText(self, 'Comment Text', 'Text:')
        if not ok or not text.strip() or self.machine is None:
            return
        c = Comment(self.machine.new_id('c'), text.rstrip(), pos.x(), pos.y())
        self.machine.comments.append(c)
        self.scene.load(self.view, self.machine)
        it = self.scene.item_for(c.id)
        if it is not None:
            self.scene.clearSelection(); it.setSelected(True)
        self.scene.changed_model.emit()

    def paste_system(self):
        """Edit > Paste Special > Paste from system clipboard: the text on the system clipboard as a
        comment text in the middle of the window."""
        from model import Comment
        text = QApplication.clipboard().text().rstrip()
        if not text or self.machine is None:
            return
        from .diagram import snap_point
        pos = snap_point(self.canvas.mapToScene(self.canvas.viewport().rect().center()))
        c = Comment(self.machine.new_id('c'), text, pos.x(), pos.y())
        self.machine.comments.append(c)
        self.scene.level = ''                   # comment texts are on the top level
        self.scene.load(self.view, self.machine)
        it = self.scene.item_for(c.id)
        if it is not None:
            self.scene.clearSelection(); it.setSelected(True)
        self.scene.changed_model.emit()

    def edit_comment(self, c):
        """A double-click on a comment text: edit it (emptied: the comment goes)."""
        text, ok = QInputDialog.getMultiLineText(self, 'Comment Text', 'Text:', c.text)
        if not ok or text == c.text:
            return
        if text.strip():
            c.text = text.rstrip()
        else:
            self.machine.comments.remove(c)
        self.scene.load(self.view, self.machine)
        self.scene.changed_model.emit()

    def _show_shortcuts(self):
        """Help > Keyboard Shortcuts (stand-alone window)."""
        from .shortcuts_dialog import show_shortcuts
        show_shortcuts(self)

    # -- popup menus ---------------------------------------------------------------------
    def show_popup(self, item, screen_pos):
        """The right-click menus of the legacy state diagram, entry for entry as the legacy tool shows
        them on gc_control_fsm. Transitions have their own
        (TransitionItem). Entries HDL Studio has no command for yet are disabled.

            diagram   Signals Table, Open Up | Undo, Redo | Paste | View Area, Zoom In, Zoom Out,
                      Zoom Last | View Page, Print Page... | Object Visibility... |
                      Update Where Used... | State Machine Properties...
            state     Cut, Copy, Paste, Paste Special >, Delete | Appearance..., Change Shape...,
                      Show Text, Re-level >, Object Properties...
            junction  Cut, Copy, Paste, Paste Special >, Delete | Appearance..., Object Properties...
            link, clock / reset / enable point
                      Rotate > | Cut ... Delete | Appearance..., Object Properties...
            interrupt point   the same without Object Properties...
            recovery point    Cut ... Delete | Appearance..., Hide
            text      Copy, Paste, Paste Special > | Appearance..., Hide Text, Send to Editor,
                      Finish Edit, Finish All Edits | Object Properties...
        """
        from PySide6.QtWidgets import QMenu
        from .diagram import DeclBlockItem, JunctionItem, LinkItem, PointItem, StateItem
        ro = self.scene.readonly
        acts = self.toolbar_actions
        if item is not None and getattr(item, 'obj', None) is not None and not item.isSelected():
            # the commands act on the selection: the object clicked becomes it, as in the legacy tool
            self.scene.clearSelection()
            item.setSelected(True)
        m = QMenu(self)

        def add(text, slot=None, shortcut='', enabled=True):
            """Add an entry (disabled without a slot or when `enabled` is False) with its shortcut shown."""
            a = m.addAction(text)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                a.setShortcutVisibleInContextMenu(True)
            a.setEnabled(bool(slot) and enabled)
            if slot:
                a.triggered.connect(slot)
            return a

        def sub(text, entries):
            """Add a sub-menu whose entries are all disabled (commands not available yet)."""
            sm = m.addMenu(text)
            for e in entries:
                sm.addAction(e).setEnabled(False)

        def edit_part(cut=True):
            """The Cut / Copy / Paste / Paste Special / Delete / Appearance part of an object menu."""
            if cut:
                add('Cut', self.cut, 'Ctrl+X', not ro)
                add('Copy', self.copy, 'Ctrl+C')
            add('Paste', self.paste, 'Ctrl+V', not ro and self.can_paste())
            sub('Paste Special', ['Paste from system clipboard'])
            add('Delete', self.scene.delete_selected, 'Del', not ro)
            m.addSeparator()
            add('Appearance...')

        def props():
            """The Object Properties... entry of an object menu."""
            add('Object Properties...', lambda: self.edit_object(item.obj), 'Alt+Return')

        if item is None:
            up = acts.get('open_up')
            add('Signals Table', lambda: self.tabs.setCurrentWidget(self.signals_tab))
            add('Open Up', up.trigger if up is not None and up.isEnabled() else None, 'Ctrl+Shift+O')
            m.addSeparator()
            add('Undo', self.undo_stack.undo, 'Ctrl+Z', self.act_undo.isEnabled())
            add('Redo', self.undo_stack.redo, 'Ctrl+Y', self.act_redo.isEnabled())
            m.addSeparator()
            add('Paste', self.paste, 'Ctrl+V', not ro and self.can_paste())
            m.addSeparator()
            add('View Area', self.view_area, 'Shift+Home')
            add('Zoom In', lambda: self.canvas.zoom(1.2), 'Shift+Up')
            add('Zoom Out', lambda: self.canvas.zoom(1 / 1.2), 'Shift+Down')
            add('Zoom Last', self.canvas.zoom_last)
            m.addSeparator()
            add('View Page')
            add('Print Page...')
            m.addSeparator()
            add('Object Visibility...')
            m.addSeparator()
            add('Update Where Used...')
            add('State Machine Properties...', self.machine_properties)
        elif isinstance(item, StateItem):
            edit_part()
            add('Change Shape...')
            add('Show Text')
            sub('Re-level', ['Add hierarchy', 'Remove hierarchy'])
            if item.obj.hier:
                add('Open Down', lambda: self.show_level(item.obj.id))
            props()
        elif isinstance(item, JunctionItem):
            edit_part()
            props()
        elif isinstance(item, (LinkItem, PointItem)):
            kind = getattr(item.obj, 'kind', 'link')
            if kind != 'recovery':
                sub('Rotate', ['90', '180', '270'])
                m.addSeparator()
            edit_part()
            if kind == 'recovery':
                add('Hide')
            elif kind != 'interrupt':
                props()
        else:
            # a text: transition condition / actions, state actions, declaration block
            # Copy: the box's text (its sections one after the other) to the system clipboard
            secs = item.sections() if hasattr(item, 'sections') else []
            text = '\n'.join(line for _tag, lines in secs for line in lines)
            add('Copy', (lambda: QApplication.clipboard().setText(text)) if text else None, 'Ctrl+C')
            add('Paste', shortcut='Ctrl+V')
            sub('Paste Special', ['Paste from system clipboard'])
            m.addSeparator()
            add('Appearance...')
            add('Hide Text')
            add('Send to Editor')
            add('Finish Edit')
            add('Finish All Edits')
            m.addSeparator()
            if isinstance(item, DeclBlockItem):
                add('Object Properties...', lambda: self.edit_decl_block(item.key), 'Alt+Return')
            elif getattr(item, 'obj', None) is not None:
                props()
        m.exec(screen_pos)

    # -- machine-level dialogs ----------------------------------------------------------
    def _machine_dialog_done(self, dlg):
        """After a machine-level dialog: draw the diagram again (texts, hidden blocks) and
        record one undo step when something was applied."""
        if dlg.applied:
            self.scene.load(self.view, self.machine)
            self.sync_toolbar()
            self.scene.changed_model.emit()

    def machine_properties(self, page: str = 'generation'):
        """Diagram > State Machine Properties... (also the diagram popup menu): the legacy dialog,
        opened on `page` (a key of sm_machine_dialog.PAGES)."""
        from .sm_machine_dialog import StateMachinePropertiesDialog
        if self.machine is None:
            return
        dlg = StateMachinePropertiesDialog(self.view, self.machine, self, page=page if isinstance(page, str)
                                           else 'generation', readonly=self.scene.readonly)
        if dlg.exec() or dlg.applied:
            self._machine_dialog_done(dlg)

    def compiler_directives(self):
        """Diagram > Compiler Directives...: the Verilog Compiler Directives dialog."""
        from .sm_machine_dialog import CompilerDirectivesDialog
        dlg = CompilerDirectivesDialog(self.view, self, readonly=self.scene.readonly)
        dlg.exec()
        self._machine_dialog_done(dlg)

    def edit_decl_block(self, key: str):
        """A double-click on a declaration block, or its entry in the Structure Navigator: the
        dialog page where its text is edited."""
        if key == 'compdir':
            self.compiler_directives()
        else:
            self.machine_properties({'concurrent': 'statements', 'statereg': 'statements', 'global': 'statements',
                                     'module': 'declarations'}.get(key, 'generation'))

    def edit_text_inline(self, item, field: str, select: tuple[int, int] | None = None):
        """Edit one text of the diagram in place, in a box over it, as the legacy tool does on a
        double-click: a transition's condition / actions, a state's entry / state / exit actions,
        a link's target, a CASE junction's expression, a clock / enable expression, a text of
        the declaration blocks. Leaving the box (or Ctrl+Enter, Enter for one line) keeps the
        text; Esc drops the edit. `select` (start, end) is selected in the box (Find Next)."""
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit
        from .diagram import DeclBlockItem, JunctionItem, LinkItem, PointItem
        view, sc = self.view, self.scene
        if isinstance(item, DeclBlockItem):
            target, attr = view, field
        elif isinstance(item, PointItem):
            target = next((s for s in view.signals if s.category == item.obj.kind), None)
            attr = 'expression'
            if target is None:
                return
        else:
            target, attr = item.obj, field
        multiline = not isinstance(item, (LinkItem, JunctionItem, PointItem)) and attr != 'cond'
        old = getattr(target, attr)
        r = item.mapToScene(item.boundingRect()).boundingRect()
        vp = self.canvas.viewport()
        ed = QPlainTextEdit(vp) if multiline else QLineEdit(vp)
        ed.setFont(QFont('Arial', 9))
        if multiline:
            ed.setPlainText(old)
            ed.setLineWrapMode(QPlainTextEdit.NoWrap)
        else:
            ed.setText(old)
            ed.selectAll()
        tl = self.canvas.mapFromScene(r.topLeft())
        br = self.canvas.mapFromScene(r.bottomRight())
        ed.setGeometry(tl.x(), tl.y(), max(160, br.x() - tl.x() + 40),
                       max(26, br.y() - tl.y() + (40 if multiline else 4)))
        ed.setStyleSheet('border: 1px solid #0080c0; background: white;')
        EC.select_span(ed, select)
        ed.show(); ed.setFocus()
        done = []

        def finish(keep: bool):
            """Close the edit box; with `keep`, write the new text into the model and redraw. Runs once."""
            if done:
                return
            done.append(1)
            try:
                new = ed.toPlainText() if multiline else ed.text().strip()
            except RuntimeError:                # the box went with its window (closing, quitting)
                return
            ed.deleteLater()
            if keep and new != old:
                setattr(target, attr, new)
                sc.load(view, self.machine)
                sc.changed_model.emit()
                self.signals_tab.set_rows(view.signals, view.signals_sheet)

        class _Focus(QObject):
            """Event filter of the edit box: focus out keeps the text, Esc drops it, Enter (Ctrl+Enter in a
            multi-line box) keeps it.
            """
            def eventFilter(self, obj, ev):
                """Qt callback for the edit box's events (see the class docstring)."""
                if ev.type() == QEvent.FocusOut:
                    finish(True)
                elif ev.type() == QEvent.KeyPress:
                    if ev.key() == Qt.Key_Escape:
                        finish(False)
                        return True
                    if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and (
                            not multiline or ev.modifiers() & Qt.ControlModifier):
                        finish(True)
                        return True
                return False
        ed._filter = _Focus(ed)
        ed.installEventFilter(ed._filter)

    def rename_state_inline(self, item, select: tuple[int, int] | None = None):
        """Edit a state name in place, in a box over the name (the legacy tool: a double-click on the name).
        Enter or leaving the box renames the state, links to it follow; Esc keeps the old name.
        An empty name or the name of another state is refused. `select` (start, end) is selected
        instead of the whole name (Find Next)."""
        from PySide6.QtWidgets import QLineEdit
        s = item.obj
        vp = self.canvas.viewport()
        ed = QLineEdit(vp)
        ed.setText(s.name); ed.selectAll()
        EC.select_span(ed, select)
        ed.setMinimumWidth(80); ed.adjustSize()
        p = self.canvas.mapFromScene(item.mapToScene(item.name_rect().center()))
        ed.move(p.x() - ed.width() // 2, p.y() - ed.height() // 2)
        ed.show(); ed.setFocus()
        done = []

        def finish(keep: bool):
            """Close the name box; with `keep`, rename the state (and the links to it) when the name is free."""
            if done:
                return
            done.append(1)
            new, old = ed.text().strip(), s.name
            ed.deleteLater()
            if not keep or not new or new == old:
                return
            if any(o.name == new for o in self.machine.states if o is not s):
                self.statusBar().showMessage(f'A state named {new} already exists', 5000)
                return
            item.prepareGeometryChange()            # the circle grows with the name
            s.name = new
            for lk in self.machine.links:
                if lk.target == old:
                    lk.target = new
            self.scene.load(self.view, self.machine)
            self.scene.changed_model.emit()

        ed.returnPressed.connect(lambda: finish(True))
        ed.editingFinished.connect(lambda: finish(True))
        esc = QAction(ed); esc.setShortcut(QKeySequence('Esc')); esc.setShortcutContext(Qt.WidgetShortcut)
        esc.triggered.connect(lambda: finish(False))
        ed.addAction(esc)

    def edit_condition_inline(self, t):
        """Type the condition of a new transition in place, in a box at the middle of the
        transition, as the legacy tool opens one when a transition is drawn. Enter or leaving the
        box keeps the text; Esc leaves the condition empty."""
        from PySide6.QtWidgets import QLineEdit
        it = self.scene.trans_items.get(t.id)
        if it is None:
            return
        path = it.path()
        mid = it.mapToScene(path.pointAtPercent(0.5)) if path.length() > 0 else it.scenePos()
        vp = self.canvas.viewport()
        ed = QLineEdit(vp)
        ed.setPlaceholderText('value')                  # the hint the legacy tool shows in its box
        ed.setText(t.cond)
        ed.setMinimumWidth(120)
        ed.adjustSize()
        p = self.canvas.mapFromScene(mid)
        ed.move(p.x() - ed.width() // 2, p.y() - ed.height() // 2)
        ed.show(); ed.setFocus()
        done = []

        def finish(keep: bool):
            """Close the condition box; with `keep`, store the condition and redraw the transitions."""
            if done:
                return
            done.append(1)
            if keep and ed.text().strip() != t.cond:
                t.cond = ed.text().strip()
                self.scene.refresh_transitions_from(t.src)
                self.scene.changed_model.emit()
            ed.deleteLater()

        ed.returnPressed.connect(lambda: finish(True))
        ed.editingFinished.connect(lambda: finish(True))
        esc = QAction(ed); esc.setShortcut(QKeySequence('Esc')); esc.setShortcutContext(Qt.WidgetShortcut)
        esc.triggered.connect(lambda: finish(False))
        ed.addAction(esc)

    def edit_selection(self, focus_text: bool = False):
        """Alt+Enter / F2: show the selected object in the Properties panel."""
        sel = self.scene.selectedItems()
        obj = getattr(sel[0], 'obj', None) if sel else None
        if obj is None:
            return
        self.props.show_object(obj, self.machine)
        self.props.parentWidget().show()
        self.props.parentWidget().raise_()
        if focus_text:
            self.props.focus_main_field()

    def set_mode(self, mode):
        """Select/Panning tools and the Add commands. Add commands repeat until
        Esc or the right button (Main Settings > Toolbar Buttons: Remain active); Ctrl while
        choosing one toggles that for the command."""
        page = self.tabs.currentWidget()
        if mode == 'select' and hasattr(getattr(page, 'table', None), 'unselect'):
            page.table.unselect()           # Esc on a table page: no cell selected, the page stays
            return
        from prefs import Prefs
        ctrl = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        self._once = mode not in ('select', 'select_text', 'select_shape', 'pan') and \
            ctrl == Prefs.load().toolbar_remain_active
        self.canvas.set_tool('')
        if mode in ('select', 'select_text', 'select_shape'):
            self.select_filter = {'select': 'any', 'select_text': 'text', 'select_shape': 'shape'}[mode]
        self.scene.set_mode('select' if mode in ('select_text', 'select_shape', 'pan') else mode)
        apply_select_filter(self.scene, self.select_filter if mode != 'pan' else 'any', self._is_text)
        if mode == 'pan':
            self.canvas.set_tool('pan')
        self.mode_actions[mode].setChecked(True)
        self.tabs.setCurrentWidget(self.canvas)
        hints = {'state': 'Click on the canvas to add a state',
                 'transition': 'Click the source, then the destination',
                 'link': 'Click to place a link, then pick the target state',
                 'pan': 'Drag to move the diagram (Esc returns to Select)'}
        self.statusBar().showMessage(hints.get(mode, ''), 4000)

    def keyPressEvent(self, e):
        """Esc goes back to the Select tool."""
        if e.key() == Qt.Key_Escape:
            self.set_mode('select')
        super().keyPressEvent(e)

    # -- loading --------------------------------------------------------------------
    def load_view(self, view: FsmView, path: str | None):
        """Show `view` (read from `path`, None when not from a file): fill the scene, tables and
        navigator, regenerate, start a new undo history and restore the saved zoom / position.
        """
        self.view, self.path = view, path
        self.machine = view.machines[0] if view.machines else None
        self.scene.level = ''
        self.scene.load(view, self.machine)
        apply_select_filter(self.scene, getattr(self, 'select_filter', 'any'), self._is_text)
        self.signals_tab.set_rows(view.signals, view.signals_sheet)
        self.params_tab.set_rows(view.parameters, view.params_sheet)
        self.props.show_object(None)
        self.sync_toolbar()
        self.build_nav()
        self.dirty = False
        self.update_title()
        self.regenerate()
        self.undo_stack.reset()
        QTimer.singleShot(0, self._restore_view_position)

    # -- view position, undo ----------------------------------------------------------
    def _view_key(self) -> str:
        """Key under which the zoom / scroll of this diagram is remembered (its file path)."""
        if self.context is not None:
            return getattr(self.context, 'key', '') or self.context.view.path
        return self.path or ''

    def _restore_view_position(self):
        """Open where the user left the diagram: HDL Studio's own saved view first, then the view
        area the legacy tool saved for the machine (at the legacy tool's 100%, which is a zoom of 75/72 here, from its
        top-left corner), else the whole diagram."""
        if self.canvas.restore(load_view_state(self._view_key())):
            return
        va = self.machine.view_area if self.machine is not None else None
        if va:
            k = 75 / 72
            self.canvas.resetTransform()
            self.canvas.scale(k, k)
            vp = self.canvas.viewport()
            self.canvas.centerOn(va[0] + vp.width() / (2 * k), va[1] + vp.height() / (2 * k))
            return
        self.canvas.fit()

    def _save_view_position(self):
        """Remember the zoom / scroll of this diagram (on close)."""
        save_view_state(self._view_key(), self.canvas.state())

    def _restore_snapshot(self, text: str):
        """Put back an undo snapshot without moving the user's view."""
        st = self.canvas.state()
        view = FsmView.from_json(text)
        idx = self.view.machines.index(self.machine) if self.machine in self.view.machines else 0
        self.view = view
        self.machine = view.machines[min(idx, len(view.machines) - 1)]
        self.scene.load(view, self.machine)
        apply_select_filter(self.scene, getattr(self, 'select_filter', 'any'), self._is_text)
        self.signals_tab.set_rows(view.signals, view.signals_sheet)
        self.params_tab.set_rows(view.parameters, view.params_sheet)
        self.props.show_object(None)
        self.sync_toolbar()
        self.build_nav()
        self.canvas.restore(st)
        # back on the saved state (e.g. undo of every edit since the last save): no '*'
        self.dirty = not self.undo_stack.is_clean(text)
        self.update_title()
        self.regen_timer.start()

    def _update_undo_actions(self):
        """Enable Undo / Redo according to the history."""
        self.act_undo.setEnabled(self.undo_stack.can_undo())
        self.act_redo.setEnabled(self.undo_stack.can_redo())

    def sync_toolbar(self):
        """Show the view's language, state declaration and encoding in the generation toolbar
        (without triggering on_toolbar_option).
        """
        for cb in (self.tb_lang, self.tb_decl, self.tb_enc):
            cb.blockSignals(True)
        self.tb_lang.setCurrentIndex(LANGUAGES.index(self.view.language))
        self.tb_decl.setCurrentText(self.machine.state_decl)
        self.tb_enc.setCurrentText(self.machine.encoding)
        for cb in (self.tb_lang, self.tb_decl, self.tb_enc):
            cb.blockSignals(False)

    def on_toolbar_option(self, *args):
        """A generation toolbar choice changed: store it in the model."""
        self.view.language = self.tb_lang.currentData()
        self.machine.state_decl = self.tb_decl.currentText()
        self.machine.encoding = self.tb_enc.currentText()
        self.model_changed()

    def build_nav(self):
        """Fill the Structure Navigator as the legacy tool does: the two tables, the design unit
        (a click shows the diagram) with its Declarations/Statements (Compiler Directives, Module
        Declarations, Concurrent Statements, Signal Status) and its Concurrent Machines (their
        states under them)."""
        from .diagram_browser import nav_icon
        self.nav.clear()
        v = self.view

        def node(parent, text, key, icon_name=None):
            it = QTreeWidgetItem(parent, [text])
            it.setData(0, Qt.UserRole, key)
            if icon_name:
                it.setIcon(0, nav_icon(icon_name))
            return it
        node(self.nav, 'Signals Table', 'signals', 'signals')
        node(self.nav, 'Parameters Table', 'params', 'params')
        unit = node(self.nav, v.unit, 'diagram', 'unit')
        decl = node(unit, 'Declarations/Statements', 'diagram')
        for t, k, ic in (('Compiler Directives', 'compdir', 'compdir'), ('Module Declarations', 'module', 'decl'),
                         ('Concurrent Statements', 'concurrent', 'concurrent'), ('Signal Status', 'statereg', 'decl')):
            node(decl, t, f'props:{k}', ic)
        machines = node(unit, 'Concurrent Machines', 'diagram', 'unit')
        for m in v.machines:
            it = node(machines, m.name, 'diagram', 'machine')
            for s in m.states:
                node(it, s.name, ('state', s.id))
        self.build_content()
        for k in range(self.nav.topLevelItemCount()):        # The legacy tool shows the top entries in bold
            it = self.nav.topLevelItem(k)
            f = it.font(0); f.setBold(True); it.setFont(0, f)
        self.nav.expandToDepth(1)
        self._sync_nav()

    def _sync_nav(self):
        """The navigator entry of the page shown: the design unit for the diagram, none for a table;
        the Content pane lists objects for the diagram only."""
        if not hasattr(self, 'browser'):
            return
        on_diagram = self.tabs.currentWidget() is self.canvas
        self.nav.blockSignals(True)
        self.nav.setCurrentItem(self.nav.topLevelItem(2) if on_diagram else None)
        if not on_diagram:
            self.nav.clearSelection()
        self.nav.blockSignals(False)
        self.browser.show_content(on_diagram)
        if on_diagram:
            self.build_content()
        else:
            self.content.clear()

    def on_nav(self, item, col):
        """A click in the Structure Navigator: show that page, open that block's dialog, or select and
        centre that state.
        """
        key = item.data(0, Qt.UserRole)
        if key == 'signals':
            self.tabs.setCurrentWidget(self.signals_tab)
        elif key == 'params':
            self.tabs.setCurrentWidget(self.params_tab)
        elif isinstance(key, str) and key.startswith('props'):
            self.edit_decl_block(key[6:] or 'machine')
        elif key == 'diagram':
            self.tabs.setCurrentWidget(self.canvas)
        elif isinstance(key, tuple):
            self.tabs.setCurrentWidget(self.canvas)
            st = next((s for s in self.machine.states if s.id == key[1]), None)
            if st is not None and st.parent != self.scene.level:
                self.show_level(st.parent)          # a state inside a hierarchical state: go there
            it = self.scene.item_for(key[1])
            if it:
                self.scene.clearSelection(); it.setSelected(True)
                self.canvas.centerOn(it)

    # -- change handling ------------------------------------------------------------
    def build_content(self):
        """The Content pane: one group per kind of object of the machine, "(Items: n)", with
        the objects under it (name, machine), as the legacy tool lists them. Only kinds present are shown."""
        if not hasattr(self, 'content'):
            return
        self.content.clear()
        m = self.machine
        if m is None or self.tabs.currentWidget() is not self.canvas:    # empty on the table pages
            return
        # the kinds the legacy tool lists there (junctions, links, recovery and interrupt points are
        # not listed; the legacy tool also lists comment texts, which HDL Studio's state diagrams do not have)
        groups = [('state', [(s.name, s.id) for s in m.states])]
        for kind in ('clock', 'reset', 'enable'):
            groups.append((kind, [(p.kind, p.id) for p in m.points if p.kind == kind]))
        for kind, objs in groups:
            if not objs:
                continue
            top = QTreeWidgetItem(self.content, [f'(Items: {len(objs)})', ''])
            top.setIcon(0, icon(kind))
            for name, oid in objs:
                QTreeWidgetItem(top, [name, m.name]).setData(0, Qt.UserRole, oid)

    def _content_clicked(self, item, _col):
        """A click in the Content pane: select and centre that object."""
        oid = item.data(0, Qt.UserRole)
        if oid:
            it = self.scene.item_for(oid)
            if it is not None:
                self.tabs.setCurrentWidget(self.canvas)
                self.scene.clearSelection(); it.setSelected(True)
                self.canvas.centerOn(it)

    def model_changed(self):
        """Called after every edit of the model: dirty flag and title, Content pane, delayed
        regeneration, undo step. An Add command used "once" goes back to Select here.
        """
        if self._once and self.scene.mode != 'select' and self.scene._pending_src is None:
            self._once = False
            QTimer.singleShot(0, lambda: self.set_mode('select'))
        self.dirty = True
        self.update_title()
        self.build_content()
        self.regen_timer.start()
        self.undo_stack.note_change()
        self._update_undo_actions()

    def on_selection(self):
        """Show the single selected object in the Properties panel."""
        sel = self.scene.selectedItems()
        obj = sel[0].obj if len(sel) == 1 and hasattr(sel[0], 'obj') else None
        self.props.show_object(obj, self.machine)

    def on_prop_changed(self, obj):
        """The Properties panel edited `obj`: redraw it (and the navigator for a state rename)."""
        if isinstance(obj, State):
            self.scene.refresh_node(obj)
            self.build_nav()
        elif isinstance(obj, Transition):
            self.scene.refresh_transitions_from(obj.src)
        else:
            self.scene.refresh_node(obj)
        self.model_changed()

    def on_table_changed(self):
        """The Signals Table changed: redraw everything (names and texts may show signals)."""
        self.scene.refresh_all()
        self.model_changed()

    def regenerate(self):
        """Generate the HDL in memory and show it with the generator's warnings (never raises)."""
        self.log.clear()
        try:
            text, warnings = generate(self.view)
        except Exception as e:  # show generator problems instead of crashing the editor
            text, warnings = f'// Generation failed: {e}', [f'ERROR: {e}']
        self.code.set_code(text)
        ext = 'sv' if self.view.language == 'systemverilog' else 'v'
        self.code_title.setText(f'<b>Generated HDL</b> — {self.view.unit}.{ext} '
                                f'({LANG_LABEL[self.view.language]}, {self.machine.state_decl}, '
                                f'{self.machine.encoding}) — {text.count(chr(10))} lines')
        for w in warnings:
            self.log.addItem(w)
        if not warnings:
            self.log.addItem('Generation OK - no warnings')

    def update_title(self):
        """Window title as the legacy tool writes it (project, library/unit/view, machine, '*', read-only)."""
        v = self.view
        star = ' *' if self.dirty else ''
        if self.context is not None:
            # The legacy tool: "Project p: lib/unit/view [machine] (Read-only) (State Diagram)"; the '*' is
            # put after the names as in the block diagram title
            ro = ' (Read-only)' if self.context.readonly else ''
            lv = self.level_path() if hasattr(self, 'scene') else ''
            self.setWindowTitle(f'Project {self.context.project_name}: {v.library}/{v.unit}/{v.view} '
                                f'[{self.machine.name}{"/" + lv if lv else ""}]{star}{ro} (State Diagram)')
            return
        name = os.path.basename(self.path) if self.path else 'untitled'
        lv = self.level_path() if hasattr(self, 'scene') else ''
        self.setWindowTitle(f'{APP_NAME} — {v.library}/{v.unit}/{v.view} '
                            f'[{self.machine.name}{"/" + lv if lv else ""}] (State Diagram) — {name}{star}')

    def generate_hdl(self):
        """Tasks > Generate: generate this view through the project (in a project only)."""
        if self.context is not None:
            self.context.generate(self.view, self)

    # -- file operations ------------------------------------------------------------
    def _confirm_discard(self) -> bool:
        """Before losing unsaved changes: ask Save / Discard / Cancel. True when it is fine to go on."""
        if not self.dirty:
            return True
        r = QMessageBox.question(self, 'Unsaved changes',
                                 f'{self.view.unit}/{self.view.view} has been modified.\nSave the changes?',
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Save:
            self.save_file()
            return not self.dirty          # false if saving failed or was cancelled
        return r == QMessageBox.Discard

    def new_file(self):
        """File > New (standalone): start again from the example machine."""
        if self._confirm_discard():
            self.load_view(traffic_light(), None)

    def open_file(self):
        """File > Open... (standalone): open a .fsm.json file."""
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Open state machine', self._dir(),
                                              'State machine (*.fsm.json *.json)')
        if path:
            self._remember(path)
            self.load_view(FsmView.load(path), path)

    def import_file(self):
        """File > Import (standalone): open a legacy .sm file."""
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Import state machine', self._dir(),
                                              'State machine (*.sm)')
        if path:
            self._remember(path)
            self.open_path(path)

    def open_path(self, path: str):
        """Open a .sm (legacy) or .fsm.json file. A .sm outside a <library>/hds/<unit>/ folder asks for the
        library and unit names.
        """
        if path.endswith('.sm'):
            parts = os.path.normpath(os.path.abspath(path)).split(os.sep)
            unit = lib = None
            if not (len(parts) > 3 and parts[-3] == META_DIR):
                # loose file, not in <library>/hds/<unit>/: ask for the names
                text, ok = QInputDialog.getText(self, 'Import', 'Library.unit for this state machine:',
                                                text='work.' + os.path.splitext(parts[-1])[0])
                if not ok:
                    return
                lib, _, unit = text.strip().rpartition('.')
                lib = lib or 'work'
            view = import_sm(path, library=lib, unit=unit)
            self.load_view(view, path)          # saved back to the same .sm (the legacy tool reads it too)
            self.statusBar().showMessage(f'Opened {path}', 5000)
        else:
            self.load_view(FsmView.load(path), path)

    def save_file(self):
        """File > Save: through the project (EditorContext.save) or, standalone, to the file the view
        came from (.sm written back with export_sm, else JSON). Clears the dirty flag.
        """
        if self.context is not None:
            if self.context.save(self.view, self, geometry=self.scene.sm_geometry):
                if self.context.view.legacy and self.context.view.path.endswith('.sm'):
                    self._reload_scene()
                self.dirty = False
                self.undo_stack.mark_clean()    # undo back to here shows no '*'
                self.update_title()
            return
        if not self.path:
            return self.save_as()
        if self.path.endswith('.sm'):
            # a legacy state diagram opened as a file: written back to it (the legacy tool reads it too)
            from formats.export_sm import export_sm
            warn = export_sm(self.view, self.path, self.path, self.scene.sm_geometry)
            if warn:
                QMessageBox.warning(self, 'Saved with omissions',
                                    'Saved to the .sm file, but these changes could not be written yet:\n\n'
                                    + '\n'.join(warn[:15]))
            self._reload_scene()
        else:
            self.view.save(self.path)
        self.dirty = False
        self.undo_stack.mark_clean()
        self.update_title()
        self.statusBar().showMessage(f'Saved {self.path}', 4000)

    def _reload_scene(self):
        """After saving to a legacy .sm: the objects added in HDL Studio now have the ids of their
        labels in the file (formats.export_sm), so the scene is built again on them; the view
        stays where it is."""
        gv = self.scene.views()[0] if self.scene.views() else None
        center = gv.mapToScene(gv.viewport().rect().center()) if gv is not None else None
        self.scene.load(self.view, self.machine)
        if gv is not None:
            gv.centerOn(center)

    def save_as(self):
        """File > Save As... (standalone): save as a new .fsm.json file."""
        path, _ = QFileDialog.getSaveFileName(self, 'Save state machine',
                                              os.path.join(self._dir(), f'{self.view.unit}.fsm.json'),
                                              'State machine (*.fsm.json)')
        if path:
            self.path = path
            self._remember(path)
            self.save_file()

    def export_hdl(self):
        """Standalone Generate: write the generated HDL to a file chosen by the user."""
        ext = 'sv' if self.view.language == 'systemverilog' else 'v'
        path, _ = QFileDialog.getSaveFileName(self, 'Export HDL', os.path.join(self._dir(), f'{self.view.unit}.{ext}'),
                                              'Verilog/SystemVerilog (*.v *.sv)')
        if path:
            text, _ = generate(self.view)
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
            self.statusBar().showMessage(f'Wrote {path}', 5000)

    def _dir(self) -> str:
        """Folder the file dialogs start in (the last one used)."""
        return QSettings('Vietsemi', 'HDL Studio').value('lastDir', os.getcwd())

    def _remember(self, path: str):
        """Remember the folder of `path` for the next file dialog."""
        QSettings('Vietsemi', 'HDL Studio').setValue('lastDir', os.path.dirname(path))

    def closeEvent(self, e):
        """Close only after unsaved changes were saved or discarded; then remember the view position
        and release the locks.
        """
        if self._confirm_discard():
            self._save_view_position()
            if self.context is not None:
                self.context.release()
            e.accept()
        else:
            e.ignore()

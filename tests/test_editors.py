"""Tests for the menus, toolbars and commands of the diagram editors (state diagram and block
diagram), on a copy of the uart example. They run without a display (Qt "offscreen" platform)
and answer the dialogs the commands open themselves.

    python -m unittest tests.test_editors
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp(prefix='hdlstudio_test_home_')
os.environ['HDLSTUDIO_HOME'] = _HOME             # never the user's own configuration

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QDesktopServices  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from bd_model import BlockDiagram  # noqa: E402
from codegen.fsm_codegen import generate  # noqa: E402
from gui import editor_common as EC  # noqa: E402
from gui.bd_editor import CommentItem, InstanceItem  # noqa: E402
from gui.design_manager import DesignManager  # noqa: E402
from gui.diagram import CommentTextItem, StateItem, TransitionItem  # noqa: E402
from gui.editor_icons import editor_icon  # noqa: E402
from gui.menus import bd_menus, fsm_menus  # noqa: E402
from gui.toolbars import BD_TOOLBARS, FSM_TOOLBARS  # noqa: E402
from model import FsmView  # noqa: E402

EXAMPLE = os.path.join(ROOT, 'examples', 'uart_studio')


def _answers(text='typed text', item_index=0):
    """Answer the dialogs the commands open: Yes to questions, `text` to text boxes, the first entry
    of a choice; file dialogs and the system viewer are not opened."""
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: (text, True))
    QInputDialog.getText = staticmethod(lambda *a, **k: (text, True))
    QInputDialog.getItem = staticmethod(lambda p, t, l, items, *a, **k: (items[item_index], True))
    QDesktopServices.openUrl = staticmethod(lambda *a: True)


def _keys(spec) -> list[str]:
    """The keys of every button of a toolbar spec (drop-down entries included)."""
    out = []
    for _title, entries in spec:
        for e in entries:
            if isinstance(e, list):
                out += [k for k, _ in e]
            elif isinstance(e, tuple):
                out.append(e[0])
    return out


def _walk(menu: QMenu, path=()) -> dict:
    """{'Menu>Sub>Entry': action} of a menu and its sub-menus (dynamic sub-menus filled first)."""
    menu.aboutToShow.emit()
    out = {}
    for a in menu.actions():
        if a.isSeparator():
            continue
        p = path + (a.text().replace('&', ''),)
        out['>'.join(p)] = a
        if a.menu() is not None:
            out.update(_walk(a.menu(), p))
    return out


class _EditorCase(unittest.TestCase):
    """A Design Manager on a fresh copy of the uart example; open(unit) opens an editor."""

    def setUp(self):
        _answers()
        self.dir = tempfile.mkdtemp(prefix='hdlstudio_test_')
        shutil.copytree(EXAMPLE, os.path.join(self.dir, 'uart'))
        self.dm = DesignManager()
        self.dm.load_project(os.path.join(self.dir, 'uart', 'uart.hdp'))
        self.lib = self.dm.project.libraries[0]

    def tearDown(self):
        for w in list(self.dm.editors.values()):
            w.dirty = False
            w.close()
        self.dm.close()
        APP.processEvents()
        shutil.rmtree(self.dir, ignore_errors=True)

    def open(self, unit: str, kind: str):
        du = self.lib.units[unit]
        view = next(v for v in du.views if kind in v.kind)
        self.dm.open_view(du, view)
        w = next(x for x in self.dm.editors.values() if f'/{unit}/' in x.windowTitle())
        w.show()
        APP.processEvents()
        return w

    def menu_entries(self, w) -> dict:
        out = {}
        for a in w.menuBar().actions():
            out.update(_walk(a.menu(), (a.text().replace('&', ''),)))
        return out


class TestLayout(unittest.TestCase):
    """Toolbar and menu layout of both editors, as the legacy editors show them."""

    def test_toolbar_titles_and_order(self):
        self.assertEqual([t for t, _ in FSM_TOOLBARS], ['Standard', 'State Diagram Tools', 'HDL Tools', 'Tasks'])
        self.assertEqual([t for t, _ in BD_TOOLBARS], ['Standard', 'Block Diagram Tools', 'HDL Tools', 'Tasks'])
        fsm = _keys(FSM_TOOLBARS)
        # the legacy State Diagram Tools order
        order = ['select', 'comment', 'pan', 'clock', 'reset', 'recovery', 'enable', 'state', 'transition',
                 'interrupt', 'link', 'junction_if', 'hier_state', 'wait_state', 'panel']
        self.assertEqual([k for k in fsm if k in order], order)
        self.assertIn('expression_builder', fsm)
        self.assertNotIn('expression_builder', _keys(BD_TOOLBARS))
        self.assertIn('edit_ibd', _keys(BD_TOOLBARS))

    def test_every_toolbar_icon_is_drawn(self):
        for key in set(_keys(FSM_TOOLBARS) + _keys(BD_TOOLBARS)):
            ic = editor_icon(key)
            self.assertFalse(ic.isNull(), key)
            img = ic.pixmap(16, 16).toImage()
            painted = any(img.pixelColor(x, y).alpha() for x in range(16) for y in range(16))
            self.assertTrue(painted, f'icon {key} is empty')

    def test_menu_titles(self):
        self.assertEqual([t.replace('&', '') for t, _ in fsm_menus()],
                         ['File', 'Edit', 'View', 'HDL', 'Diagram', 'Tasks', 'Add', 'Simulate', 'Animation',
                          'Options', 'Window', 'Help'])
        self.assertEqual([t.replace('&', '') for t, _ in bd_menus()],
                         ['File', 'Edit', 'View', 'HDL', 'Diagram', 'Tasks', 'Simulate', 'Add', 'Options',
                          'Window', 'Help'])

    def test_no_legacy_product_names(self):
        text = json.dumps([fsm_menus(), bd_menus(), FSM_TOOLBARS, BD_TOOLBARS], default=str)
        for name in ('DesignChecker', 'ModelSim', 'Precision', 'SVAssistant', 'Register Assistant', 'HDS'):
            self.assertNotIn(name, text)


class TestStateDiagram(_EditorCase):
    """State diagram editor commands on uart_tx."""

    def setUp(self):
        super().setUp()
        self.w = self.open('uart_tx', 'fsm')
        self.A = self.w.toolbar_actions

    def states(self):
        return sorted((i for i in self.w.scene.items() if isinstance(i, StateItem)), key=lambda i: i.obj.name)

    def test_menus_have_the_legacy_entries(self):
        e = self.menu_entries(self.w)
        for path in ('File>Open>Open Up', 'File>Document And Visualize>Single Level', 'Edit>Replace...',
                     'Edit>Align>Align Left', 'Edit>Expression Builder', 'View>Snap to Grid',
                     'View>Toolbars>Tooltips', 'View>Toolbars>State Diagram Tools', 'Diagram>Open Machine>csm',
                     'Diagram>Change To>Junction', 'Diagram>Panels>Delete Panel', 'Tasks>Check Flow>Run Single',
                     'Add>Concurrent State Machine', 'Add>Comment Text', 'Add>Panel'):
            self.assertIn(path, e)
        self.assertEqual(e['Add>Input Port'].shortcut().toString(), 'F8')
        self.assertEqual(e['Add>Concurrent State Machine'].shortcut().toString(), 'Ctrl+F2')

    def test_buttons_follow_the_selection(self):
        self.w.update_menu_states()
        for key in ('cut', 'copy', 'paste', 'align_left', 'reverse_direction'):
            self.assertFalse(self.A[key].isEnabled(), key)
        self.assertFalse(self.A['clock'].isEnabled())          # the machine has its clock
        a, b = self.states()[:2]
        a.setSelected(True); b.setSelected(True)
        self.w.update_menu_states()
        for key in ('cut', 'copy', 'align_left', 'change_junction'):
            self.assertTrue(self.A[key].isEnabled(), key)
        self.assertFalse(self.A['distribute_h'].isEnabled())   # three objects needed

    def test_copy_paste_and_align(self):
        a, b = self.states()[:2]
        b.obj.y += 40; b.setPos(b.obj.x, b.obj.y)
        a.setSelected(True); b.setSelected(True)
        self.A['align_top'].trigger()
        self.assertEqual(a.obj.y, b.obj.y)
        self.A['copy'].trigger()
        self.w.update_menu_states()
        self.assertTrue(self.A['paste'].isEnabled())
        n = len(self.w.machine.states)
        self.A['paste'].trigger()
        names = [s.name for s in self.w.machine.states]
        self.assertEqual(len(names), n + 2)
        self.assertEqual(len(set(names)), len(names))           # pasted states were renamed

    def test_find_replace_renames_links_too(self):
        m = self.w.machine
        from model import Link
        target = m.states[1].name
        m.links.append(Link(m.new_id('l'), target, 0, 0))
        self.w.find_replace(True)
        dlg = self.w._find_dialog
        dlg.find.setCurrentText(target); dlg.word.setChecked(True); dlg.case.setChecked(True)
        dlg.repl.setCurrentText('RENAMED')
        dlg.replace_all()
        dlg.close()
        self.assertIn('RENAMED', [s.name for s in m.states])
        self.assertEqual(m.links[-1].target, 'RENAMED')

    def test_reverse_direction_and_change_to(self):
        t = next(i for i in self.w.scene.items() if isinstance(i, TransitionItem))
        src, dst = t.obj.src, t.obj.dst
        t.setSelected(True)
        self.A['reverse_direction'].trigger()
        self.assertEqual((t.obj.src, t.obj.dst), (dst, src))
        self.w.scene.clearSelection()
        st = self.states()[0]
        sid = st.obj.id
        n = len([x for x in self.w.machine.transitions if sid in (x.src, x.dst)])
        st.setSelected(True)
        self.A['change_junction'].trigger()
        self.assertTrue(any(j.id == sid for j in self.w.machine.junctions))
        self.assertEqual(n, len([x for x in self.w.machine.transitions if sid in (x.src, x.dst)]))

    def test_machines_and_signals(self):
        self.A['add_machine'].trigger()
        self.assertEqual(len(self.w.view.machines), 2)
        self.assertIs(self.w.machine, self.w.view.machines[1])
        menu = QMenu(); self.w._fill_open_machine(menu)
        self.assertEqual([a.text() for a in menu.actions()], [m.name for m in self.w.view.machines])
        self.w.delete_machine(self.w.machine)
        self.assertEqual(len(self.w.view.machines), 1)
        n = len(self.w.view.signals)
        self.A['add_input_port'].trigger(); self.A['add_output_port'].trigger()
        self.assertEqual([s.mode for s in self.w.view.signals[n:]], ['input', 'output'])

    def test_hierarchical_state(self):
        from model import State
        m = self.w.machine
        h = State(m.new_id('s'), 'H1', 600, 600, hier=True)
        m.states.append(h)
        self.w.scene.load(self.w.view, m)
        self.w.show_level(h.id)
        self.assertEqual(self.w.scene.level, h.id)
        self.assertIn('/H1]', self.w.windowTitle())
        self.assertEqual(sorted(p.kind for p in m.points if p.parent == h.id), ['entry', 'exit'])
        self.A['open_up'].trigger()
        self.assertEqual(self.w.scene.level, '')
        generate(self.w.view)                                   # still generates

    def test_comment_text_and_panel_are_saved(self):
        _answers('a note')
        self.w.add_comment(QPointF(20, 20))
        self.assertTrue(any(isinstance(i, CommentTextItem) for i in self.w.scene.items()))
        self.w.add_panel(QPointF(0, 0))
        view = FsmView.from_json(self.w.view.to_json())
        self.assertEqual([c.text for c in view.machines[0].comments], ['a note'])
        self.assertEqual([p.name for p in view.machines[0].panels], ['Panel0'])
        self.w.scene.clearSelection()
        self.w.panel_items()[0].setSelected(True)
        self.w.scene.delete_selected()
        self.assertEqual(self.w.machine.panels, [])

    def test_paste_from_system_clipboard(self):
        QApplication.clipboard().setText('from the clipboard')
        self.w.update_menu_states()
        self.assertTrue(self.A['paste_system'].isEnabled())
        self.A['paste_system'].trigger()
        self.assertEqual(self.w.machine.comments[-1].text, 'from the clipboard')

    def test_document_single_level(self):
        out = os.path.join(self.dir, 'doc')
        os.makedirs(out)
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: out)
        self.A['document'].trigger()
        self.assertTrue(os.path.isfile(os.path.join(out, 'uart_tx.png')))
        with open(os.path.join(out, 'uart_tx.html'), encoding='utf-8') as f:
            self.assertIn('module uart_tx', f.read())


class TestBlockDiagram(_EditorCase):
    """Block diagram editor commands on uart_top."""

    def setUp(self):
        super().setUp()
        self.w = self.open('uart_top', 'bd')
        self.A = self.w.toolbar_actions

    def test_menus_have_the_legacy_entries(self):
        e = self.menu_entries(self.w)
        for path in ('Diagram>Edit as IBD', 'Diagram>Autoroute>Connect By Name', 'Edit>Find...',
                     'View>Toolbars>Block Diagram Tools', 'View>View Panel', 'Add>Comment Text'):
            self.assertIn(path, e)

    def test_align_and_undo(self):
        insts = sorted((i for i in self.w.scene.items() if isinstance(i, InstanceItem)), key=lambda i: i.obj.name)
        a, b = insts[:2]
        a.setSelected(True); b.setSelected(True)
        self.w.update_menu_states()
        self.assertTrue(self.A['align_left'].isEnabled())
        x_b = b.obj.x
        self.A['align_left'].trigger()
        moved = next(i for i in self.w.bd.instances if i.name == b.obj.name)
        self.assertEqual(moved.x, a.obj.x)
        self.w.undo_stack.flush()
        self.A['undo'].trigger()
        self.assertEqual(next(i for i in self.w.bd.instances if i.name == b.obj.name).x, x_b)

    def test_comment_text(self):
        _answers('note\nline 2')
        self.w.set_mode('comment')
        self.w.place_at(QPointF(100, 100))
        c = [c for c in self.w.bd.comments if not c.group]
        self.assertEqual([x.text for x in c], ['note\nline 2'])
        self.assertTrue(any(isinstance(i, CommentItem) and i.obj is c[0] for i in self.w.scene.items()))

    def test_connectivity_rows(self):
        rows = {r[0]: r for r in self.w.connectivity_rows()}
        self.assertIn('clk', rows)
        self.assertIn('port clk (input)', rows['clk'][2])
        self.assertIn('u_tx.clk', rows['clk'][3])

    def test_connect_by_name(self):
        u = next(i for i in self.w.bd.instances if i.unit == 'uart_tx')
        self.w.disconnect(u)
        self.assertTrue(self.w._free_pins(u))
        self.w.connect_by_name()
        self.assertEqual(self.w._free_pins(u), [])

    def test_find_lists_nets_and_instances(self):
        self.w.find_replace(False)
        dlg = self.w._find_dialog
        dlg.find.setCurrentText('tx'); dlg.find_all()
        found = [dlg.results.item(k, 1).text() for k in range(dlg.results.rowCount())]
        dlg.close()
        self.assertIn('Instance u_tx (uart_tx)', found)
        self.assertIn('Signal tx_data', found)

    def test_panel_saved(self):
        self.w.add_panel(QPointF(0, 0))
        bd = BlockDiagram.from_json(self.w.bd.to_json())
        self.assertEqual([p.name for p in bd.panels], ['Panel0'])

    def test_open_down_then_open_up(self):
        tx = next(i.obj for i in self.w.scene.items() if isinstance(i, InstanceItem) and i.obj.unit == 'uart_tx')
        self.w.open_instance(tx)
        child = next(x for x in self.dm.editors.values() if '/uart_tx/' in x.windowTitle())
        EC.open_up(child)
        hist = EC.History.of(self.dm)
        self.assertIn(self.w, hist.windows)
        self.assertIn(child, hist.windows)


class TestFindDialog(_EditorCase):
    """The legacy Find and Replace dialog (find_dialog.py) on uart_tx."""

    def setUp(self):
        super().setUp()
        self.w = self.open('uart_tx', 'fsm')
        self.w.find_replace(False)
        self.d = self.w._find_dialog

    def visible_buttons(self):
        d = self.d
        return [b.text() for b in (d.b_next, d.b_replace, d.b_close, d.b_more, d.b_all, d.b_select,
                                   d.b_repl_all, d.b_help) if b.isVisible()]

    def test_layout_as_the_legacy_dialog(self):
        d = self.d
        self.assertEqual(d.windowTitle(), 'Find and Replace - uart_lib/uart_tx/fsm [csm]')
        self.assertEqual([d.tabs.tabText(k) for k in range(d.tabs.count())], ['Find', 'Replace'])
        self.assertEqual(self.visible_buttons(), ['Find Next', 'Close', 'More >>'])
        d.set_more(True)
        self.assertEqual(self.visible_buttons(), ['Find Next', 'Close', '<< Less', 'Find All', 'Select All', 'Help'])
        self.assertEqual([d.depth.itemText(k) for k in range(d.depth.count())],
                         ['Current', 'Hierarchically', 'Through Components'])
        self.assertTrue(d.related.isVisible())
        d.tabs.setCurrentIndex(1)
        self.assertEqual(self.visible_buttons(),
                         ['Find Next', 'Replace', 'Close', '<< Less', 'Find All', 'Replace All', 'Help'])
        self.assertFalse(d.related.isVisible())
        self.assertTrue(d.repl.isVisible())
        self.assertFalse(d.clear_btn.isEnabled())
        d.kinds.item(0).setSelected(True)
        self.assertTrue(d.clear_btn.isEnabled())
        d.clear_btn.click()
        self.assertEqual(d.kinds.selectedItems(), [])
        self.assertFalse(d.syntax_btn.isEnabled())
        d.regex.setChecked(True)
        self.assertTrue(d.syntax_btn.isEnabled())

    def test_find_next_opens_the_text_with_the_match_selected(self):
        from PySide6.QtWidgets import QPlainTextEdit
        d = self.d
        d.find.setCurrentText('bit_cnt')
        self.assertTrue(d.find_next())
        boxes = [e for e in self.w.canvas.viewport().findChildren(QPlainTextEdit) if e.isVisible()]
        self.assertEqual([b.textCursor().selectedText() for b in boxes], ['bit_cnt'])
        self.assertIn('bit_cnt', [d.find.itemText(k) for k in range(d.find.count())])     # history

    def test_find_next_stops_at_the_end_unless_wrap(self):
        d = self.d
        d.find.setCurrentText('bit_cnt')
        n = len(d.matches()[1])
        for _ in range(n):
            self.assertTrue(d.find_next())
        self.assertFalse(d.find_next())
        d.wrap.setChecked(True)
        self.assertTrue(d.find_next())

    def test_find_all_and_constraints(self):
        d = self.d
        d.find.setCurrentText('bit_cnt')
        d.find_all()
        names = [d.results.item(r, 1).text() for r in range(d.results.rowCount())]
        self.assertIn('Signals Name Column (bit_cnt)', names)
        self.assertEqual(d.results.item(0, 2).text(), 'Available for Edit')
        d.kinds.findItems('Transition conditions', Qt.MatchExactly)[0].setSelected(True)
        d.find_all()
        names = [d.results.item(r, 1).text() for r in range(d.results.rowCount())]
        self.assertTrue(names and all(n.startswith('Condition of Transition') for n in names))

    def test_replace_one_then_all(self):
        d = self.d
        d.tabs.setCurrentIndex(1)
        d.find.setCurrentText('bit_cnt')
        d.case.setChecked(True); d.word.setChecked(True)
        d.repl.setCurrentText('bitcount')
        total = len(d.matches()[1])
        d.find_next()
        d.replace_one()
        self.assertEqual(len(d.matches()[1]), total - 1)
        self.assertEqual(d.replace_all(), total - 1)
        self.assertEqual(d.matches()[1], [])
        self.assertIn('bitcount', [s.name for s in self.w.view.signals])

    def test_regular_expression_groups(self):
        d = self.d
        d.find.setCurrentText(r'(\w+)_cnt'); d.regex.setChecked(True); d.case.setChecked(True)
        d.repl.setCurrentText(r'\1_count')
        self.assertGreater(d.replace_all(), 0)
        self.assertIn('bit_count', [s.name for s in self.w.view.signals])

    def test_block_diagram_kinds(self):
        from gui.find_dialog import BD_KINDS
        b = self.open('uart_top', 'bd')
        b.find_replace(True)
        d = b._find_dialog
        self.assertEqual(d.windowTitle(), 'Find and Replace - uart_lib/uart_top/struct')
        self.assertEqual([d.kinds.item(k).text() for k in range(d.kinds.count())], BD_KINDS)
        self.assertEqual(d.tabs.currentIndex(), 1)
        d.find.setCurrentText('tx_data'); d.case.setChecked(True); d.word.setChecked(True)
        d.repl.setCurrentText('tx_byte')
        d.kinds.findItems('Signal Name', Qt.MatchExactly)[0].setSelected(True)
        self.assertEqual(d.replace_all(), 1)                    # the net, renamed everywhere
        self.assertTrue(all(w.net != 'tx_data' for w in b.bd.wires))
        self.assertIn('tx_byte', {p.net for i in b.bd.instances for p in i.pins})


class TestFindHighlight(_EditorCase):
    """Find Next shows the match selected (blue) in place, comment texts marked; End of search."""

    def setUp(self):
        super().setUp()
        self.messages = []
        QMessageBox.information = staticmethod(lambda p, t, m, *a, **k: self.messages.append(m) or QMessageBox.Ok)

    def boxes(self, w):
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit
        vp = w.canvas.viewport()
        return [e for e in vp.findChildren(QLineEdit) + vp.findChildren(QPlainTextEdit) if e.isVisible()]

    def test_state_name_opens_with_the_match_selected_in_blue(self):
        from PySide6.QtGui import QPalette
        w = self.open('uart_tx', 'fsm')
        w.find_replace(False)
        d = w._find_dialog
        d.find.setCurrentText('DAT'); d.case.setChecked(True)
        self.assertTrue(d.find_next())
        boxes = self.boxes(w)
        self.assertEqual([b.selectedText() for b in boxes], ['DAT'])
        pal = boxes[0].palette()
        self.assertEqual(pal.color(QPalette.Inactive, QPalette.Highlight).name(), '#0078d7')

    def test_comment_text_is_marked(self):
        _answers('look at DATA')
        w = self.open('uart_tx', 'fsm')
        w.add_comment(QPointF(0, -200))
        w.find_replace(False)
        d = w._find_dialog
        d.find.setCurrentText('look'); d.case.setChecked(True)
        d.find_next()
        marked = [i for i in w.scene.items() if isinstance(i, CommentTextItem)]
        self.assertEqual(marked[0].find_span, (0, 4))

    def test_end_of_search_message(self):
        w = self.open('uart_tx', 'fsm')
        w.find_replace(False)
        d = w._find_dialog
        d.find.setCurrentText('bit_cnt')
        n = len(d.matches()[1])
        for _ in range(n):
            d.find_next()
        self.assertEqual(self.messages, [])
        self.assertFalse(d.find_next())
        self.assertEqual(self.messages, ["End of search. Hit 'Find Next' to start again."])
        self.assertTrue(d.find_next())                         # starts again from the first match
        d.find.setCurrentText('no_such_text')
        d.find_next()
        self.assertEqual(self.messages[-1], 'Search completed. Nothing was found.')

    def test_block_diagram_instance_opens_in_place(self):
        b = self.open('uart_top', 'bd')
        b.find_replace(False)
        d = b._find_dialog
        d.find.setCurrentText('u_r'); d.case.setChecked(True)
        d.find_next()
        APP.processEvents()
        self.assertEqual([x.selectedText() for x in self.boxes(b)], ['u_r'])


class TestTables(_EditorCase):
    """Signals Table and Parameters Table pages as the legacy spreadsheet."""

    def setUp(self):
        super().setUp()
        self.w = self.open('uart_rx', 'fsm')
        self.st = self.w.signals_tab
        self.t = self.st.table

    def sig(self, name):
        return next(s for s in self.w.view.signals if s.name == name)

    def cell(self, name, attr):
        return self.t.item(self.st.row_of(self.sig(name)), self.st.column_of(attr))

    def test_columns_of_a_new_diagram(self):
        from gui.tables import HEADERS
        self.assertEqual([HEADERS[a] for a in self.st.columns],
                         ['Group', 'Name', 'Mode', 'Type', 'Signed', 'Bounds', 'Delay', 'Value', 'Category',
                          'Assign In', 'Expression', 'Scheme', 'Default', 'Reset', 'Comment'])
        self.assertEqual(self.w.params_tab.columns, ['group', 'name', 'value', 'comment'])
        self.assertEqual([self.t.columnWidth(k) for k in range(4)], [50, 70, 50, 80])   # the legacy defaults
        self.assertEqual(self.t.fixed(), 3)                     # Group, Name, Mode frozen
        b = self.open('uart_top', 'bd')
        self.assertEqual(b.signals_tab.columns,
                         ['group', 'name', 'mode', 'type', 'signed', 'bounds', 'delay', 'value', 'comment'])
        self.assertEqual(b.params_tab.columns, ['group', 'name', 'value', 'comment'])
        self.assertEqual(self.t.rowCount(), len(self.w.view.signals) + 1)       # the empty last row

    def test_texts_and_grey_cells(self):
        self.assertEqual(self.cell('clk', 'category').text(), 'Clock (Rising)')
        self.assertEqual(self.cell('rst', 'category').text(), 'Reset (Async Low)')
        self.assertEqual(self.cell('rx_data', 'assign').text(), '<auto>')
        self.assertEqual(self.cell('shift_reg', 'scheme').text(), 'Clocked')

        def editable(it):
            return bool(it.flags() & Qt.ItemIsEditable)
        self.assertFalse(editable(self.cell('clk', 'scheme')))              # inputs have no scheme
        self.assertFalse(editable(self.cell('clk', 'assign')))              # nor Assign In
        self.assertTrue(editable(self.cell('rx_data', 'assign')))           # outputs have <auto> / <none>
        self.assertTrue(editable(self.cell('clk', 'expression')))           # a clock has its expression
        self.assertFalse(editable(self.cell('rx', 'expression')))           # a data input has none
        self.assertFalse(editable(self.cell('rx_data', 'category')))        # outputs have no category
        self.assertFalse(editable(self.cell('rx_data', 'reset')))           # combinational: no reset
        self.assertTrue(editable(self.cell('shift_reg', 'reset')))          # clocked: a reset value

    def test_assign_none(self):
        s = self.sig('rx_data')
        self.t.write(self.st.row_of(s), self.st.column_of('assign'), '<none>')
        self.assertEqual(s.scheme, 'none')
        self.assertEqual(self.cell('rx_data', 'scheme').text(), 'N/A')
        self.assertFalse(bool(self.cell('rx_data', 'default').flags() & Qt.ItemIsEditable))

    def test_typing_in_the_last_row_adds_a_signal(self):
        n = len(self.w.view.signals)
        self.t.write(n, self.st.column_of('name'), 'new_in')
        self.assertEqual(self.w.view.signals[-1].name, 'new_in')
        self.assertEqual((self.w.view.signals[-1].mode, self.w.view.signals[-1].type), ('input', 'wire'))
        self.assertEqual(self.t.rowCount(), n + 2)
        self.assertEqual(self.w.view.signals_sheet['order'][-1], 'new_in')     # its place in the layout
        self.t.write(self.st.row_of(self.sig('clk')), self.st.column_of('name'), 'rst')   # a name taken
        self.assertIsNotNone(self.sig('clk'))

    def test_category_sets_the_expression(self):
        n = len(self.w.view.signals)
        self.t.write(n, self.st.column_of('name'), 'en')
        s = self.sig('en')
        self.t.write(self.st.row_of(s), self.st.column_of('category'), 'Enable (Low)')
        self.assertEqual((s.category, s.expression), ('enable', '!en'))
        self.t.write(self.st.row_of(s), self.st.column_of('name'), 'en2')       # the expression follows the name
        self.assertEqual(s.expression, '!en2')
        self.t.write(self.st.row_of(s), self.st.column_of('mode'), 'output')
        self.assertEqual((s.category, s.scheme), ('data', 'comb'))

    def test_delete_rows_sort_and_filter(self):
        from PySide6.QtTest import QTest
        n = len(self.w.view.signals)
        self.t.setFocus()
        self.t.selectRow(0)
        QTest.keyClick(self.t, Qt.Key_Delete)
        self.assertEqual(len(self.w.view.signals), n - 1)
        self.t.setCurrentCell(0, self.st.column_of('name'))
        self.st.sort()
        names = [s.name for s in self.st.display_rows()]
        self.assertEqual(names, sorted(names, key=str.lower))
        self.t.set_filter(self.st.column_of('mode'), 'local')
        rows = self.st.display_rows()
        shown = {rows[r].mode for r in range(len(rows)) if not self.t.isRowHidden(r)}
        self.assertEqual(shown, {'local'})
        self.st.clear_filters()
        self.assertFalse(any(self.t.isRowHidden(r) for r in range(self.t.rowCount())))

    def test_appearance_and_column_width_are_kept_in_the_layout(self):
        self.t.setCurrentCell(self.st.row_of(self.sig('clk')), self.st.column_of('name'))
        self.st.set_format(bg='#ff0000', bold=None, align='left')
        fmt = self.w.view.signals_sheet['cells']['clk|name']
        self.assertEqual((fmt['bg'], fmt['bold'], fmt['align']), ('#ff0000', True, 'left'))
        self.t.setColumnWidth(self.st.column_of('comment'), 222)
        self.assertIn(['comment', 222], self.w.view.signals_sheet['columns'])

    def test_page_menus_and_toolbars(self):
        from PySide6.QtWidgets import QToolBar
        w = self.w
        w.tabs.setCurrentWidget(self.st)
        titles = [a.text().replace('&', '') for a in w.menuBar().actions()]
        self.assertEqual(titles, ['File', 'Edit', 'View', 'HDL', 'Table', 'Tasks', 'Add', 'Options', 'Window', 'Help'])
        shown = {t.windowTitle() for t in w.findChildren(QToolBar) if not t.isHidden()}
        self.assertTrue({'Standard', 'SM Signals Tools', 'Appearance', 'HDL Tools', 'Tasks'} <= shown)
        self.assertNotIn('State Diagram Tools', shown)
        w.toolbar_actions['toggle_tables'].trigger()
        self.assertIs(w.tabs.currentWidget(), w.params_tab)
        w.toolbar_actions['show_diagram'].trigger()
        titles = [a.text().replace('&', '') for a in w.menuBar().actions()]
        self.assertIn('Diagram', titles)
        shown = {t.windowTitle() for t in w.findChildren(QToolBar) if not t.isHidden()}
        self.assertIn('State Diagram Tools', shown)
        self.assertNotIn('Appearance', shown)

    def test_parameters(self):
        p = self.w.params_tab
        p.table.write(len(self.w.view.parameters), p.column_of('name'), 'WIDTH')
        prm = self.w.view.parameters[-1]
        p.table.write(p.row_of(prm), p.column_of('value'), '8')
        self.assertEqual((prm.name, prm.value), ('WIDTH', '8'))


@unittest.skipUnless(os.path.isfile(os.path.join(os.environ.get('HDLSTUDIO_SAMPLES', 'D:/workspace'), 'fsm.sm')),
                     'no legacy state diagram sample (HDLSTUDIO_SAMPLES)')
class TestSheetLayout(unittest.TestCase):
    """The table layout read from a legacy .sm (formats.sheet)."""

    def test_read_sheets(self):
        from formats.sexpr import parse_file
        from formats.sheet import read_sheets
        sig, prm = read_sheets(parse_file(os.path.join(os.environ.get('HDLSTUDIO_SAMPLES', 'D:/workspace'),
                                                       'fsm.sm')))
        self.assertEqual(sig['columns'][0][0], '#ref')
        self.assertIn('name', [a for a, _ in sig['columns']])
        self.assertEqual(sig['fixed_row'], 2)
        self.assertEqual(sig['va']['header']['bg'], '#c0c0c0')
        self.assertEqual(prm['columns'][-1][0], 'comment')


class TestEditorCommon(unittest.TestCase):
    """Window history used by Back / Forward."""

    def test_history(self):
        from PySide6.QtWidgets import QMainWindow
        a, b, c = QMainWindow(), QMainWindow(), QMainWindow()
        for w in (a, b, c):
            w.show()
        h = EC.History()
        for w in (a, b, c):
            h.visited(w)
        self.assertTrue(h.can_go(-1))
        self.assertFalse(h.can_go(1))
        h.go(-1)
        self.assertIs(h.windows[h.pos], b)
        self.assertTrue(h.can_go(1))
        h.visited(a)                         # a new visit drops the forward part
        self.assertFalse(h.can_go(1))
        for w in (a, b, c):
            w.close()


if __name__ == '__main__':
    unittest.main()

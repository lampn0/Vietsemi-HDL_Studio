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

from PySide6.QtCore import QPointF  # noqa: E402
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
        dlg.find.setText(target); dlg.word.setChecked(True); dlg.case.setChecked(True)
        dlg.repl.setText('RENAMED')
        dlg.replace(only_current=False)
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
        dlg.find.setText('tx'); dlg.find_all()
        found = [dlg.results.item(k).text() for k in range(dlg.results.count())]
        dlg.close()
        self.assertTrue(any(t.startswith('Instance u_tx') for t in found))
        self.assertTrue(any(t.startswith('Net tx_data') for t in found))

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

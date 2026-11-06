"""Tests for projects, libraries, locks, generation and block diagrams."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from codegen.bd_codegen import generate_bd  # noqa: E402
from formats.import_bd import import_bd  # noqa: E402
from project import lock  # noqa: E402
from project.generate import generate_unit, native_path  # noqa: E402
from project.hdp import read_hdp  # noqa: E402
from project.project import create_project, open_project  # noqa: E402
from project.templates import new_fsm  # noqa: E402

SAMPLES = os.environ.get('HDLSTUDIO_SAMPLES', 'D:/workspace')
BD = os.path.join(SAMPLES, 'struct.bd')
BD_GOLDEN = os.path.join(SAMPLES, 'pc_global_controller.v')


class TestProject(unittest.TestCase):
    """Projects, libraries and generation in a temporary folder."""
    def setUp(self):
        """A fresh temporary folder for each test."""
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove the temporary folder."""
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_create_scan_generate(self):
        """Create a project and a state machine unit, scan the library, generate, and check that a
        hand-edited generated file is reported as a conflict instead of being overwritten.
        """
        hdp = os.path.join(self.dir, 'demo', 'demo.hdp')
        proj = create_project(hdp, 'lib_a')
        lib = proj.library('lib_a')
        self.assertTrue(os.path.isdir(lib.main_hdl_dir) and os.path.isdir(lib.meta_dir))
        raw = read_hdp(hdp)
        self.assertEqual(raw.first('hdl', 'lib_a'), '$HDS_PROJECT_DIR/lib_a/hdl')
        self.assertEqual(raw.first('hds_settings', 'default_library'), 'lib_a')

        fsm = new_fsm('lib_a', 'ctrl', 'fsm', [('input', '', 'clk'), ('input', '', 'rst_n'), ('output', '', 'done')],
                      'systemverilog', 'enum', 'gray')
        path = native_path(lib, 'ctrl', 'fsm', 'fsm')
        os.makedirs(os.path.dirname(path))
        fsm.save(path)
        with open(os.path.join(lib.main_hdl_dir, 'top.sv'), 'w') as f:
            f.write('module top(input clk, input rst_n, output done);\n  ctrl u1(.clk(clk), .rst_n(rst_n), .done(done));\nendmodule\n')
        lib.scan()
        self.assertEqual(lib.units['ctrl'].type, 'Component')
        self.assertEqual(lib.units['top'].type, 'Module')
        self.assertEqual([(i.module, i.name) for i in lib.units['top'].hdl.instances], [('ctrl', 'u1')])

        res = generate_unit(lib, lib.units['ctrl'])
        self.assertEqual(res.status, 'written', res.message)
        self.assertTrue(res.path.endswith('ctrl.sv'))
        self.assertEqual(generate_unit(lib, lib.units['ctrl']).status, 'unchanged')
        with open(res.path, 'a') as f:
            f.write('// hand edit\n')
        self.assertEqual(generate_unit(lib, lib.units['ctrl']).status, 'conflict')
        self.assertEqual(generate_unit(lib, lib.units['ctrl'], force=True).status, 'written')

    def test_hdp_paths_and_shared(self):
        """.hdp reading: repeated keys, $HDS_PROJECT_DIR, an unset variable reported as an error, the
        shared project's libraries and the protected library type.
        """
        os.makedirs(os.path.join(self.dir, 'team'))
        with open(os.path.join(self.dir, 'team', 'shared.hdp'), 'w') as f:
            f.write('[hdl]\nstdlib = $HDS_PROJECT_DIR/std\n[library_type]\nstdlib = standard\n')
        with open(os.path.join(self.dir, 'p.hdp'), 'w') as f:
            f.write('[hdl]\na = $HDS_PROJECT_DIR/a/hdl\na = $HDS_PROJECT_DIR/a/extra\nb = $NOT_SET_VAR/b\n'
                    '[library_type]\na = regular\n[shared]\nothers = $HDS_PROJECT_DIR/team/shared.hdp\n')
        p = open_project(os.path.join(self.dir, 'p.hdp'))
        a = p.library('a')
        self.assertEqual(len(a.hdl_dirs), 2)
        self.assertTrue(any('NOT_SET_VAR' in e for e in p.library('b').errors))
        self.assertEqual(p.library('stdlib').type, 'protected')
        self.assertEqual(p.library('stdlib').origin, 'shared')


class TestLock(unittest.TestCase):
    """Edit locks."""
    def test_lock_round_trip(self):
        """Acquire / read / release a lock; a lock held by another process is refused unless forced."""
        with tempfile.TemporaryDirectory() as d:
            view = os.path.join(d, 'fsm.sm')
            open(view, 'w').close()
            ok, holder = lock.acquire(view)
            self.assertTrue(ok)
            info = lock.read_lock(view)
            self.assertTrue(lock.is_mine(info))
            with open(lock.lock_path(view)) as f:
                self.assertEqual(f.readline().strip(), 'EDIT_LOCK')
            lock.release(view)
            self.assertIsNone(lock.read_lock(view))
            with open(lock.lock_path(view), 'w') as f:
                f.write('EDIT_LOCK\nsomeone\ngrp\nother-host\n123\n10/30/26-11:00:51.105832\n')
            ok, holder = lock.acquire(view)
            self.assertFalse(ok)
            self.assertEqual(holder.user, 'someone')


@unittest.skipUnless(os.path.exists(BD) and os.path.exists(BD_GOLDEN), 'legacy samples not found')
class TestBlockDiagramGolden(unittest.TestCase):
    """pc_global_controller read from the legacy tool .bd generates exactly what the old tool generated."""
    def test_body_matches_legacy_tool(self):
        """Four instances, no warnings, body from "// Internal Declarations" identical to the golden file."""
        bd = import_bd(BD, 'protocol_controller', 'pc_global_controller')
        self.assertEqual(len(bd.instances), 4)
        text, warnings = generate_bd(bd, 'verilog')
        self.assertEqual(warnings, [])
        with open(BD_GOLDEN, encoding='utf-8') as f:
            golden = f.read()
        cut = '// Internal Declarations'
        self.assertEqual(text[text.index(cut):], golden[golden.index(cut):])


if __name__ == '__main__':
    unittest.main()


class TestSvRuleAndWires(unittest.TestCase):
    """The SystemVerilog logic / wire rule and the wire geometry helpers of the editor."""
    def test_drivers(self):
        """drivers() tells continuous assignments from procedural ones (comparisons are not assignments)."""
        from codegen.common import drivers
        cont, proc = drivers("assign a = b;\nwire w = 0;\nalways @(posedge clk) if (x <= y) q <= d;\n"
                             "always @* begin z = 1; end")
        self.assertEqual(cont, {'a'})
        self.assertEqual(proc, {'q', 'z'})

    @unittest.skipUnless(os.path.exists(BD), 'legacy samples not found')
    def test_sv_logic_vs_wire(self):
        """In SystemVerilog, signals assigned in procedural code are declared logic, the others wire."""
        bd = import_bd(BD, 'protocol_controller', 'pc_global_controller')
        text, _ = generate_bd(bd, 'systemverilog')
        decl = {}
        for line in text.split('\n'):
            code = line.split('//')[0].split()
            if code and code[0] in ('input', 'output'):
                decl[code[-1].rstrip(',;')] = code[1]
        self.assertEqual(decl['t_rfc_done'], 'logic')      # assigned in an always block
        self.assertEqual(decl['dram_odt_gc'], 'wire')      # assigned with assign
        self.assertEqual(decl['clk'], 'wire')              # input

    def test_wire_end_stays_orthogonal(self):
        """_shift_end keeps the end segment of a net horizontal / vertical when its end moves."""
        from bd_model import BdWire
        from gui.bd_editor import _shift_end
        w = BdWire('w', 'n', [[0, 0], [50, 0], [50, 40], [100, 40]])
        _shift_end(w, 'start', 0, 20)
        self.assertEqual(w.points[:2], [[0, 20], [50, 20]])
        w2 = BdWire('w', 'n', [[0, 0], [100, 0]])
        _shift_end(w2, 'end', 0, 30)
        for a, b in zip(w2.points, w2.points[1:]):
            self.assertTrue(a[0] == b[0] or a[1] == b[1])

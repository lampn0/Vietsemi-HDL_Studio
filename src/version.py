"""Version and product identity of Vietsemi HDL Studio, and a map of src/.

src/ is the top level of the application: bin/ puts it on sys.path, so its modules and
packages are imported by their own names (`from model import FsmView`, `from gui.bd_editor
import BdEditorWindow`). From the bottom layer up:

    model.py, bd_model.py   in-memory data model of a state diagram (FsmView) and of a block
                            diagram (BlockDiagram), with their JSON persistence (.fsm.json / .bd.json)
    formats/                readers and writers of the legacy graphics formats (.sm, .bd, .sb):
                            S-expression parser (sexpr), importers, exporters, and the names
                            the legacy project format fixes (names.py)
    hdl/                    Verilog / SystemVerilog parser (pyslang: ports, parameters, instances)
    codegen/                HDL generation from the data model (FSM and block diagram), with
                            the exact text layout of the legacy tool's output
    project/                .hdp projects, libraries, design units, locks, generation records
    homes.py                the configuration folders: ~/hdl_studio/user and team, one folder per release
    prefs.py, session.py    user preferences and the saved working session (in the user folder)
    gui/                    the Qt (PySide6) user interface: Design Manager, editors, dialogs

The launchers in bin/ put src/ on sys.path and start gui.design_manager.DesignManager
(or gui.main_window.MainWindow for the stand-alone FSM editor).
"""

# Version YYYY.MM.NNN: the release (year and month) and a three-digit revision of that release.
# The full number is used in generated file headers and release archive names.
__version__ = '2026.12.001'
# The release alone (YYYY.MM): what the About box and the splash screen show, and the name of
# the configuration folder of the release (~/hdl_studio/user/vYYYY.MM, see homes.py).
RELEASE = '.'.join(__version__.split('.')[:2])

# Product identity. Every user-visible name of the tool comes from here.
VENDOR = 'Vietsemi Technology Co., Ltd.'
VENDOR_URL = 'https://vietsemi.org'
APP_NAME = 'Vietsemi HDL Studio'   # full product name: About boxes, window titles, generated headers
APP_SHORT = 'HDL Studio'           # short form for menus and messages
APP_ID = 'vietsemi-hdl-studio'     # technical id; earlier builds kept settings in ~/.config/<APP_ID>


def about_text(part: str = '') -> str:
    """Text of the Help > About box; `part` names the window it is shown from (e.g. 'Block diagram editor')."""
    head = f'{APP_NAME} {RELEASE}' + (f' - {part}' if part else '')
    return '\n'.join((
        head,
        'RTL design and verification (testbench, RAL) for Verilog / SystemVerilog.',
        '',
        f'(c) {VENDOR} - {VENDOR_URL}'))

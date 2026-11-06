"""Rebuild a window's menu bar in the legacy tool's order from the actions it
already has. Entries that do not exist yet appear disabled, so the layout
matches even where the feature is not implemented."""
from __future__ import annotations

from typing import Callable

from version import APP_NAME
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu

from .command_names import COMMANDS


def _key(text: str) -> str:
    """Normalised action text used to match menu entries to actions ("&Save As..." -> "save as")."""
    return text.replace('&', '').replace('...', '').strip().lower()


def arrange_menus(win: QMainWindow, spec: list[tuple[str, list]]) -> None:
    """spec: [(menu title, [item | '-' | (submenu title, [...]) | (submenu title, fill)])]. An item is
    '@key' for a command of the window's toolbar_actions (shown under its legacy name), '@key=Label'
    the same with the label of the greyed placeholder shown while the window has no such command,
    '!text' for a disabled placeholder, or the text of another action the window has (a disabled
    placeholder when there is none). A sub-menu given with a function `fill(menu)` is filled by it
    each time it opens (lists that change: machines, windows, toolbars).
    """
    actions: dict[str, QAction] = {}
    for a in win.findChildren(QAction):
        # actions owned by the old menus die with them when the menu bar is cleared below
        if a.text() and not a.isSeparator() and not isinstance(a.parent(), QMenu):
            actions.setdefault(_key(a.text()), a)
    commands = getattr(win, 'toolbar_actions', {})
    mb = win.menuBar()
    mb.clear()

    def placeholder(label: str) -> QAction:
        a = QAction(label, win)
        a.setEnabled(False)
        a.setToolTip('Not available in this version')
        return a

    def fill(menu: QMenu, items: list):
        """Add the entries of `items` to `menu` (recursing into sub-menus)."""
        for it in items:
            if it == '-':
                menu.addSeparator()
            elif callable(it):
                # a section of `menu` filled by it(menu-like) each time the menu opens
                held: list[QAction] = []

                def refresh(m=menu, f=it, held=held):
                    for a in held:
                        m.removeAction(a)
                    held.clear()
                    tmp = QMenu()
                    f(tmp)
                    for a in tmp.actions():
                        a.setParent(m)
                        m.addAction(a)
                        held.append(a)
                menu.aboutToShow.connect(refresh)
            elif isinstance(it, tuple) and callable(it[1]):
                sub = menu.addMenu(it[0])
                sub.aboutToShow.connect(lambda m=sub, f=it[1]: f(m))
                it[1](sub)                       # filled once now, so the entry is not empty
            elif isinstance(it, tuple):
                fill(menu.addMenu(it[0]), it[1])
            elif it.startswith('!'):
                # '!text': a placeholder only, even when another action has the same name
                # (e.g. Diagram > Panels > Print... is not the diagram's Print...)
                menu.addAction(placeholder(it[1:]))
            elif it.startswith('@'):
                key, _, label = it[1:].partition('=')
                a = commands.get(key)
                if a is None:
                    a = placeholder(label or COMMANDS.get(key, ('', key, ''))[0].replace('&', '') or key)
                menu.addAction(a)
            else:
                menu.addAction(actions.get(_key(it)) or placeholder(it))

    for title, items in spec:
        menu = mb.addMenu(title)
        fill(menu, items)
        # entries that act on the selection are enabled when their menu opens
        if hasattr(win, 'update_menu_states'):
            menu.aboutToShow.connect(win.update_menu_states)


def _greyed(*labels: str) -> list[str]:
    """Placeholders of a sub-menu that is greyed as a whole in this version."""
    return ['!' + t for t in labels]


def _file(fsm: bool, own: list) -> list:
    """File menu of the diagram editors (the state diagram one has Open > Down and Save As)."""
    return [('&New', ['@new_content=Design Content...', '@new_testbench=Test Bench...']),
            ('&Open', ['@open_up', '@open_interface=Interface'] + (['@open_down'] if fsm else [])),
            '@save'] + (['@save_as'] if fsm else []) + [
            '@save_title_block=Save Title Block', '-', '@refresh_boundaries=Refresh Page Boundaries', '-',
            '@page_setup', '@print_window=Print Window...', '@print', '-',
            ('Document And Visualize', ['@document', '@document_hier', '@document_root'])] + own + [
            '-', '@close_window', '@exit']


def _edit(fsm: bool) -> list:
    """Edit menu of the diagram editors."""
    return ['@undo', '@redo', '-', '@cut', '@copy', '@paste',
            ('Paste Special', ['@paste_system=Paste from system clipboard']), '@delete', '-', '@select_all', '-',
            '@find', '@replace', '-', '@appearance=Appearance...',
            ('Align', ['@align_left=Align Left', '@align_center=Align Center', '@align_right=Align Right',
                       '@align_top=Align Top', '@align_middle=Align Middle', '@align_bottom=Align Bottom', '-',
                       '@distribute_h=Distribute Horizontally', '@distribute_v=Distribute Vertically']),
            ('Group', ['@group=Group', '@ungroup=UnGroup']),
            ('Rotate', ['@rotate_90=90', '@rotate_180=180', '@rotate_270=270']),
            ('Flip', ['@flip_v=Vertical', '@flip_h=Horizontal']), '-'] \
        + (['@expression_builder'] if fsm else []) + ['@object_props']


def _view(fsm: bool, toolbars: Callable) -> list:
    """View menu of the diagram editors; `toolbars` fills View > Toolbars."""
    return ['@fit', '@view_area', '@refresh', '@view_panel=View Panel', '@zoom_in', '@zoom_out', '@zoom_last',
            '-', '@grid'] + (['@snap_grid=Snap to Grid'] if fsm else []) + [
            '-', ('&Toolbars', toolbars), '@status_bar', '@object_tips=Object Tips', '@diagram_browser',
            '@signals_table'] + ([] if fsm else ['-', '@page_break=Page Break Preview'])


def _text_menu(rotate: bool) -> tuple:
    """Diagram > Text."""
    return ('Text', ['@text_show=Show Text', '@text_hide=Hide Text']
            + ([('Rotate Text', ['@text_rotate_90=90', '@text_rotate_180=180', '@text_rotate_270=270'])]
               if rotate else [])
            + ['@send_to_editor=Send to Editor', '@finish_edit=Finish Edit', '@finish_all_edits=Finish All Edits',
               ('Allow Visual Change', ['@visual_change_yes=Yes', '@visual_change_no=No'])])


_COMMENT_GRAPHICS_SHOW = ('Comment Graphics', ['@comment_graphics_hide=Hide', '@comment_graphics_show=Show All'])
_PANELS = ('Panels', ['@panel_delete=Delete Panel', '@panel_show=Show Panel', '@panel_print=Print...',
                      '@panels_protect=Protect All Panels', '@panel_props=Object Properties'])


def _tasks(through_blocks: bool) -> list:
    """Tasks menu: the flows (Check, Generate, Simulate, Synthesize), each with its Run ... entries."""
    from .toolbars import task_keys

    def flow(title, key, settings=False):
        return (title, ['@' + k for k in task_keys(key, through_blocks)]
                + (['@generate_settings=Settings...'] if settings else []) + [f'@{key}_enable=Enable'])
    return ['@generate_always=Set Generate Always', '@compile_always=Set Compile Always',
            '@generate_all=Generate All (One Shot)', '@compile_all=Compile All (One Shot)', '-',
            flow('Check Flow', 'check'), flow('&Generate', 'generate', True), flow('Simulate Flow', 'simulate'),
            flow('Synthesize Flow', 'synthesize')]


def _add_comment_graphics() -> list:
    """Add > Comment Text, Panel, Comment Graphics, Title Block (common to both editors)."""
    return ['@comment=Comment Text', '@panel',
            ('Comment Graphics', ['@cg_line=Line', '@cg_polyline=Polyline', '@cg_polygon=Polygon', '@cg_arc=Arc',
                                  '@cg_rectangle=Rectangle', '@cg_ellipse=Ellipse', '@cg_circle=Circle',
                                  '@cg_bitmap=Bitmap...']),
            '@title_block=Title Block']


def _simulate(fsm: bool) -> list:
    """Simulate menu: shown as in the legacy tool, greyed (no simulator in this version)."""
    run = ['!Run Single', '!Run Through Blocks', '!Run Through Components', '!Run Through Components from Design Root']
    items = [('Start Simulation', run),
             ('Run', _greyed('For Time', 'Forever', 'Continue', 'To Next Event')),
             ('Step', _greyed('Over Line', 'Into Line', *(['Over Object'] if fsm else []))),
             ('Environment', _greyed(*([] if fsm else ['Selected']), 'Diagram', 'Top', 'Report')),
             ('Breakpoints', _greyed('Add', 'Delete', 'Delete All', 'Enable', 'Enable All', 'Disable',
                                     'Disable All', 'Report'))]
    if fsm:
        items += [('Display', _greyed('Add State Variable To Wave Window', 'Delete State Variable From Wave Window',
                                      'Add State Variable To List Window', 'Delete State Variable From List Window',
                                      'Track Cursor', 'Highlight Object'))]
    else:
        items += [('Probes', _greyed('Add', 'Delete', 'Delete All', 'Track Cursor', 'Probe Properties')),
                  ('Display', _greyed('Add Wave', 'Delete Wave', 'Add List', 'Delete List', 'Add Log', 'Delete Log',
                                      'Highlight Object'))]
    items += [('View', _greyed('Source', 'Structure', 'Variables', 'Signals', 'List', 'Process', 'Wave', 'Dataflow',
                               'All'))]
    items += ([] if fsm else ['!Signal Info', '!Choose Instance...']) + ['!Restart Simulator',
                                                                         '!Debug Detective Enabled']
    return items


_ANIMATION = _greyed('Move By States', 'Move By Events', 'Move By Clocks', 'Goto Next State', 'Goto Previous State',
                     'Goto Time', 'Goto Start', 'Goto Latest', 'Cause', 'Data Capture', 'Global Capture On',
                     'Global Capture Off', 'Show Animation', 'Choose Instance...', 'Activity Trails...',
                     'Clear Captured Events', 'Link Diagrams')

_OPTIONS = ['@main_settings', '@verilog_options', '@diagram_prefs=Diagram Preferences...',
            ('Master Preferences', ['@master_apply_new=Apply to New Objects',
                                    '@master_apply_all=Apply to New and Existing Objects',
                                    '@master_update=Update from Diagram'])]


def _window(windows: Callable | None) -> list:
    """Window menu: the tool windows, then one entry per open window (`windows` fills them)."""
    items = ['@same_window=Use Same Window', '-', '@log_window', '@task_log=Task Log Window', '@design_manager',
             '@component_browser=Component Browser']
    return items + (['-', windows] if windows else [])


_HELP = ['@help_manuals=Help and Manuals', '@shortcuts_help', '@regex_help=Regular Expressions', '-',
         'About ' + APP_NAME]


def fsm_menus(standalone: bool = False, machines: Callable | None = None, delete_machine: Callable | None = None,
              toolbars: Callable | None = None, windows: Callable | None = None) -> list:
    """The state diagram editor menus, entry for entry as the legacy tool shows them (read from the
    running tool); VHDL-only entries and third-party tool names are left out. Outside a project
    (standalone) the File menu also has HDL Studio's own New / Open / Import commands. The functions
    fill the sub-menus that change: Diagram > Open Machine / Delete Machine, View > Toolbars and the
    open windows.
    """
    own = ['-', 'New', 'Open...', 'Import state machine (.sm)...'] if standalone else []
    none = (lambda m: None)
    return [
        ('&File', _file(True, own)),
        ('&Edit', _edit(True)),
        ('&View', _view(True, toolbars or none)),
        ('&HDL', ['@generate_open', '@black_box=Black box for Synthesis']),
        ('&Diagram', ['@copy_picture=Copy Picture', '!Package References...', '@compiler_directives', '-',
                      '@reverse_direction=Reverse Direction',
                      ('Change To', ['@change_state=State', '!Hierarchical State', '@change_junction=Junction',
                                     '!Interrupt Point', '!Entry Point', '@change_link=Link', '!Exit Point']),
                      _text_menu(False), _COMMENT_GRAPHICS_SHOW, _PANELS, '-',
                      ('Open Machine', machines or none), ('Delete Machine', delete_machine or none),
                      ('Re-level', ['!Add hierarchy', '!Remove hierarchy']),
                      '@rename_machine=Rename Concurrent Machine...', '@sm_props']),
        ('&Tasks', _tasks(False)),
        ('&Add', ['@add_input_port=Input Port', '@add_output_port=Output Port', '@add_inout_port=InOut Port',
                  '@add_local_signal=Local Signal', '@add_machine=Concurrent State Machine', '-',
                  '@clock', '@reset', '@recovery', '@enable', '-', '@state', '@transition', '@interrupt',
                  '@link', '@junction_if', '@junction_case', '@hier_state', '@wait_state', '-']
                 + _add_comment_graphics()),
        ('&Simulate', _simulate(True)),          # the legacy tool puts Add before Simulate in this window
        ('A&nimation', _ANIMATION),
        ('&Options', _OPTIONS),
        ('&Window', _window(windows)),
        ('&Help', _HELP),
    ]


FSM_MENUS = fsm_menus()

_ON_OFF = ['On', 'Off']


def bd_menus(toolbars: Callable | None = None, windows: Callable | None = None) -> list:
    """The block diagram editor menus, entry for entry as the legacy tool shows them (read from the
    running tool). VHDL-only entries and third-party tool names are left out. Entries HDL Studio
    cannot do yet are greyed at their legacy place."""
    none = (lambda m: None)
    return [
        ('&File', _file(False, [])),
        ('&Edit', _edit(False)),
        ('&View', _view(False, toolbars or none)),
        ('&HDL', ['@generate_open', '@black_box=Black box for Synthesis']),
        ('&Diagram', [
            '@copy_picture=Copy Picture', '!Package References...', '@compiler_directives', '-',
            ('Ports', [('Change Mode', ['@port_mode_in', '@port_mode_out', '@port_mode_inout']),
                       ('Clock', ['@port_clock_on=On', '@port_clock_off=Off']),
                       ('Not', ['@port_not_on=On', '@port_not_off=Off']),
                       ('Ordering', ['@port_order_auto=Automatic', '@port_order_manual=Manual']),
                       ('Attributes', ['@port_attr_show=Show', '@port_attr_hide=Hide', '@port_attr_edit=Edit...']),
                       ('Comments', ['@port_comment_show=Show', '@port_comment_hide=Hide',
                                     '@port_comment_edit=Edit...']),
                       '@equidistant']),
            ('Signals', [('Ordering', ['@net_order_auto=Automatic', '@net_order_manual=Manual']),
                         ('Comments', ['@net_comment_show=Show', '@net_comment_hide=Hide', '@net_comment']),
                         ('Attributes', ['@net_attr_show=Show', '@net_attr_hide=Hide', '@net_attr_edit=Edit...']),
                         ('Highlight Net', ['@net_highlight', '@highlight_hier=Hierarchical...',
                                            '@net_clear_highlight']),
                         ('Insert Net', ['!Single Level Up...', '!Single Level Down...', '!Hierarchical...']),
                         ('Remove Net', ['!Single Level Up...', '!Single Level Down...', '!Hierarchical...']),
                         ('Scope For Changes', ['@scope_joined=Joined Wires in this diagram',
                                                '@scope_diagram=Entire Net in diagram',
                                                '@scope_hierarchy=Entire Net in hierarchy']),
                         '@net_change_style', '@net_add_port_io']),
            _text_menu(True), _COMMENT_GRAPHICS_SHOW, _PANELS,
            '-', '@connect', '@disconnect', '@add_stubs', '@add_stubs_ports',
            '@auto_instance_names=Automatic Instance Names',
            ('Port Map Frame', ['@portmap_enable', '@portmap_disable', '@portmap_edit']),
            ('Shape', ['!Editing Shape', '!Autowhisker', '!Autoshapes...']),
            ('Autoroute', ['@autoconnect=Autoconnect', '@autobundle=Autobundle', '@connect_by_name=Connect By Name',
                           '@autoroute=Autoroute', '@autoroute_options=Autoroute Options...']),
            '@layout_diagram=Layout Diagram', '@layout_options=Layout/Routing Options...', '-',
            ('Update', ['@update_interface', '!Interface and Graphics', '!From Symbol', '!Graphics To Symbol']),
            ('Re-level', ['!Remove Hierarchy...', '!Add Hierarchy...']), '-', '@check_design',
            '@check_options=Design Checking Options...', '-', '@edit_ibd', '@visualize_ibd']),
        ('&Tasks', _tasks(True)),
        ('&Simulate', _simulate(False)),
        ('&Add', ['@block', '@component', '@moduleware', '@external_ip', '@embedded',
                  ('&Frame', ['@frame', '@frame_if', '@frame_else']), '@wire', '@bus', '@bundle',
                  '@global_connector', '@port_in', '@port_out', '@port_inout'] + _add_comment_graphics()),
        ('&Options', _OPTIONS),
        ('&Window', _window(windows)),
        ('&Help', _HELP),
    ]


BD_MENUS = bd_menus()

DM_MENUS = [
    ('&File', ['New &Project', '&Open Project', 'Recent Projects', '-', 'New &Library', '&New Design Content',
               'Open HDL &File', '-', '&Close Project', 'E&xit']),
    ('&Edit', ['Cut', 'Copy', 'Paste', 'Delete', '-', 'Select All', 'Find']),
    ('&View', ['&Refresh', 'Re&load (re-read every file)', 'Explore &Library']),
    ('&HDL', ['View generated / source &HDL', '&Generate selected']),
    ('&Tasks', ['&Generate selected', 'Generate whole &library']),
    ('&Tools', ['DesignPad', 'Component Browser', 'Find']),
    ('&Options', ['&Preferences']),
    ('&Window', ['Log']),
    ('&Help', ['&About']),
]

"""Toolbars of the Design Manager, laid out as in the legacy Design Explorer.

Four toolbars (Standard, Design Manager, HDL, Tasks) with the legacy buttons in the legacy
order, tool tips and status-bar texts. A button is enabled only for the selections it acts on
(STATES), as in the legacy tool: e.g. Explore Library lights up when a library is selected on
the Project page, Object Properties when a design unit is selected. Buttons for flows HDL
Studio does not have stay greyed.

Selection kinds (DesignManager.selection_kind()):
    none      Project page, nothing selected      lib       Project page, a library selected
    explorer  a library tab, nothing selected     unit      a design unit or one of its views
    file      a file of the Files pane            hier      a row of the Design Hierarchy pane
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QToolBar, QToolButton

from .dm_icons import dm_icon

if TYPE_CHECKING:
    from .design_manager import DesignManager

ALL = frozenset({'none', 'lib', 'explorer', 'unit', 'file', 'hier'})
NEVER = frozenset()


@dataclass
class Button:
    """One toolbar button: icon name (dm_icons 'tb_<icon>'), tool tip, status-bar text, the
    selection kinds it is enabled for and the slot it runs (None: greyed always); `menu` is the
    name of the drop-down menu of a split button ('new', 'generate')."""
    icon: str
    tip: str
    status: str
    states: frozenset = NEVER
    slot: str = ''
    menu: str = ''


def _s(*kinds: str) -> frozenset:
    return frozenset(kinds)


# toolbar title -> buttons; '-' is a separator
TOOLBARS: list[tuple[str, list]] = [
    ('Standard', [
        Button('new', 'New', 'Creates a new design content', ALL, 'new_unit', menu='new'),
        Button('open', 'Open', 'Open', _s('unit', 'file', 'hier'), 'open_selected'),
        '-',
        Button('print', 'Print', 'Print'),
        Button('document', 'Document And Visualize Design', 'Document And Visualize'),
        '-',
        Button('cut', 'Cut', 'Cut'),
        Button('copy', 'Copy', 'Copy', _s('none', 'lib', 'unit', 'file', 'hier'), 'copy_selection'),
        Button('paste', 'Paste', 'Paste'),
        Button('delete', 'Delete', 'Delete'),
        '-',
        Button('properties', 'Object Properties', 'Object Properties', _s('unit'), 'selected_properties'),
    ]),
    ('Design Manager', [
        Button('hierarchy', 'Toggle Hierarchy', 'Toggle Hierarchy', _s('unit', 'file'), 'toggle_selected_hierarchy'),
        Button('cross_highlight', 'Cross-Highlight', 'Cross-Highlight'),
        Button('explore', 'Explore Library', 'Explore Library', _s('lib'), 'explore_selected'),
        '-',
        Button('explorer_view', 'Change Explorer View', 'Change Explorer View',
               _s('explorer', 'unit', 'file', 'hier'), 'toggle_explorer_view'),
        Button('viewpoint', 'Viewpoint Manager', 'Hide or show the Viewpoint Manager'),
        Button('find', 'Find', 'Find'),
        Button('components', 'Show Component Browser', 'Show Component Browser Window'),
        Button('designpad', 'DesignPad', 'Open the HDL text of the selected design unit', ALL,
               'open_selected_hdl'),
        '-',
        Button('refresh', 'Refresh', 'Check and update project files, libraries...', ALL, 'refresh_project'),
    ]),
    ('HDL', [
        Button('convert', 'Convert HDL to Graphics', 'Convert HDL declarations to graphics'),
        Button('visualize', 'Visualize the specified declaration as a graphical view',
               'Visualize the specified declaration as a graphical view'),
        Button('view_hdl', 'View Generated HDL', 'View Generated HDL code',
               _s('none', 'lib', 'explorer', 'unit', 'hier'), 'open_selected_hdl'),
    ]),
    ('Tasks', [
        Button('tasks', 'Show/Hide Tasks and Templates Window', 'Show/Hide Tasks and Templates Window'),
        '-',
        Button('check', 'Check', 'Check the selected design units', ALL, 'check_selected'),
        Button('registers', 'Registers', 'Register file generation'),
        Button('generate', 'Generate', 'Generate HDL for the selected design units', ALL, 'generate_selected',
               menu='generate'),
        Button('simulate', 'Simulate', 'Simulation flow'),
        Button('synthesize', 'Synthesize', 'Synthesis flow'),
    ]),
]


class DmToolbars:
    """The toolbars of a Design Manager and the enabling of their buttons."""

    def __init__(self, dm: 'DesignManager', menus: dict[str, QMenu]):
        """Build the toolbars into `dm`; `menus` are the drop-down menus of the split buttons."""
        self.dm = dm
        self.bars: list[QToolBar] = []
        self._actions: list[tuple[QAction, Button]] = []
        for title, buttons in TOOLBARS:
            bar = QToolBar(title, dm)
            bar.setObjectName('tb_' + title.lower().replace(' ', '_'))
            bar.setIconSize(QSize(16, 16))
            for b in buttons:
                if b == '-':
                    bar.addSeparator()
                    continue
                a = QAction(dm_icon('tb_' + b.icon), b.tip, dm)
                a.setStatusTip(b.status)
                slot = getattr(dm, b.slot) if b.slot else None
                if slot is not None:
                    a.triggered.connect(lambda checked=False, f=slot: f())
                bar.addAction(a)
                if b.menu and b.menu in menus:
                    a.setMenu(menus[b.menu])
                    btn = bar.widgetForAction(a)
                    if isinstance(btn, QToolButton):
                        btn.setPopupMode(QToolButton.MenuButtonPopup)
                self._actions.append((a, b))
            dm.addToolBar(bar)
            self.bars.append(bar)
        self.update('none')

    def update(self, kind: str) -> None:
        """Enable the buttons that act on a selection of `kind` (see the module docstring)."""
        for a, b in self._actions:
            a.setEnabled(bool(b.slot) and kind in b.states)

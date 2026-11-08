"""Qt user interface (PySide6).

Windows:
    design_manager.py   the Design Manager (project tree, libraries, design units, files,
                        hierarchy) - the main window of the application
    main_window.py      the state diagram editor window (canvas from diagram.py)
    bd_editor.py        the block diagram editor window (canvas, items, commands)
    text_editor.py      the HDL text editor (line numbers, find, syntax check)

Shared pieces: menus.py / toolbars.py / command_names.py (legacy menus, toolbars, command names,
shortcuts and tool tips of the editors), editor_common.py (commands both diagram editors share:
print, Copy Picture, Align, Back / Forward, Open Up), find_dialog.py (Find and Replace),
expression_builder.py,
context.py (popup menus), explorer_menus.py (Design Explorer right-click menus), dm_toolbar.py
(Design Manager toolbars), text_selection.py (selection drawn behind the text only), undo.py,
icons.py / dm_icons.py / editor_icons.py (icons drawn in code),
branding.py (Vietsemi logo: window icon, About boxes, splash picture), status.py (start-up splash
screen and status bar progress), shortcuts_dialog.py (Help > Keyboard Shortcuts),
dialogs and property panels (dialogs.py, bd_dialogs.py, sm_props_dialog.py,
sm_machine_dialog.py, dm_options.py, main_settings.py, props.py, tables.py).
"""

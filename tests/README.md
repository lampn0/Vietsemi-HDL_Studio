# Tests

Run everything from the repository root (the folder holding `src/` and `tests/`).
The test scripts put `src/` on the Python path themselves.

| Kind | Command | What it checks | Needs |
|---|---|---|---|
| Unit tests | `python -m unittest discover -s tests` | projects, libraries, locks, FSM and block diagram generation; the editors' menus, toolbars and commands (`test_editors.py`) | nothing (the golden checks are skipped without the `HDLSTUDIO_SAMPLES` files; `test_editors.py` runs Qt without a display) |
| GUI tests | `python tests/gui/run_all.py` | the real application through the Design Manager and the editors, driven with real mouse and keyboard input | a display, the real project |

## Editor tests (`tests/test_editors.py`)

The state diagram and block diagram editors opened by a Design Manager on a temporary copy of
`examples/uart_studio`, with Qt's `offscreen` platform (no window appears, the mouse is not
used) and a temporary configuration folder. The dialogs the commands open are answered by the
test. They check:

| Class | Covers |
|---|---|
| `TestLayout` | Toolbar titles and button order (Standard, State / Block Diagram Tools, HDL Tools, Tasks), every toolbar icon drawn, menu titles in the legacy order, no legacy product names |
| `TestStateDiagram` | Legacy menu entries and shortcuts (F8, Ctrl+F2), buttons enabled by the selection, Copy / Paste and Align, Find / Replace (links follow a renamed state), Reverse Direction, Change To, concurrent machines and signals, hierarchical states (Open Down / Open Up), comment texts and panels saved in the JSON, Paste from system clipboard, Document And Visualize |
| `TestBlockDiagram` | Legacy menu entries, Align and Undo, Comment Text, the connectivity table (IBD), Connect By Name, Find, panels saved in the JSON, Open Down then Open Up |
| `TestEditorCommon` | The Back / Forward window history |

```
python -m unittest tests.test_editors -v
```

## GUI tests (`tests/gui/`)

Each `gui_*.py` file opens the application with visible windows, works on it with mouse clicks,
drags and key presses, and prints one `PASS` or `FAIL` line per check. **Leave the mouse and
keyboard alone while they run** (about 3 minutes for all of them).

```
python tests/gui/run_all.py                    # all GUI tests, with a summary
python tests/gui/run_all.py bd_suite session    # only the files whose name contains one of these
python tests/gui/gui_bd_suite.py                # one file on its own
```

`_env.py` gives every test a temporary copy of part of a real project (the `dynamo_core`
block diagram and the whole `protocol_controller` library) and its own configuration folder, so
a test never writes into the real project or into your preferences. Screenshots go to
`tests/gui/out/` (not in git).

A test never waits for a person: a dialog left open more than 20 seconds (a lock question, an
error box) is closed and reported as a `FAIL` line, and `run_all.py` stops a test after 5 minutes.
Lock files a test leaves (some tests simulate a crash) stay in its temporary copy, which
`run_all.py` deletes.

| Variable | Default | Meaning |
|---|---|---|
| `HDLSTUDIO_TEST_SRC` | `D:\workspace\src` | the real project folder copied from (only read) |
| `HDLSTUDIO_TEST_OUT` | `tests/gui/out` | where screenshots go |
| `HDLSTUDIO_TEST_TMP` | a new temporary folder | where the project copy and config go (`run_all.py` makes and deletes one per test) |
| `HDLSTUDIO_UART_SM` | none (the test is skipped) | a legacy `uart_tx` state diagram (`fsm.sm`, states START and DATA) that `gui_fsm_transitions.py` reads |
| `HDLSTUDIO_SAMPLES` | `D:/workspace` | folder of `fsm.sm`, `struct.bd` and their golden `.v` files for the unit tests (`test_fsm.py`, `test_project.py`) |

| File | Covers |
|---|---|
| `gui_bd_suite.py` | Block diagram editing as in the legacy tool: nets and buses (default names `sig0`/`dbus0`, two-click drawing, joining a net, name placement, Change Style, in-place edit, undo, "with a Port"), ports (preview, auto-connection by the port's wire end, unnamed free ports, Change Mode, inout), components (preview, placement, nets from component ports, moving), embedded blocks (Create Embedded View, Text view move/resize, input/output by net direction, Change Mode), save/reload and generated HDL |
| `gui_bd_add_items.py` | Port preview and attach, new embedded block and its Text view, a net to the block |
| `gui_bd_component_name.py` | Component name lines: select, drag, double-click edit; undo clears the title `*` |
| `gui_bd_name_text.py` | The same on the legacy `dynamo_core` diagram, outside the Design Manager |
| `gui_bd_inline_edit.py` | In-place edit of nets and ports (`name : type[bounds]`), dragging a net name |
| `gui_bd_embedded_nets.py` | Dragging nets attached to an embedded block (the block stays) |
| `gui_bd_embedded_drag.py` | Sliding a net end along an embedded block edge |
| `gui_bd_comp_to_comp.py` | A net between two components |
| `gui_bd_connect.py` | Ports follow components, connection by dragging, popup menus |
| `gui_bd_net_ops.py` | Moving components and nets, Alt+drag of a segment, in-place rename |
| `gui_bd_pin_drag.py`, `gui_bd_pin_move.py`, `gui_bd_pin_net_drag.py` | Moving component ports and their nets |
| `gui_bd_grid.py`, `gui_bd_handles.py` | Grid snapping, handle sizes |
| `gui_bd_frames.py`, `gui_bd_frame_props.py` | Generate frames |
| `gui_bd_component_props.py`, `gui_bd_params.py` | Component popup menus, Object Properties, parameters |
| `gui_bd_route_modes.py` | PortIO drag routing modes |
| `gui_canvas_ops.py` | Zoom, pan, view area and other canvas operations of both editors |
| `gui_editor_toolbars.py` | The legacy toolbars of both editors with real clicks and keys: the four toolbars, Cut / Copy greyed without a selection, Add State from its button, Ctrl+C / Ctrl+V, Edit > Align, Ctrl+F, Add Panel and Comment Text from the toolbar, View > Toolbars |
| `gui_dm_menu_states.py` | Design Manager menus: which entries are enabled for each selection |
| `gui_dm_units.py` | Design unit list, default views, double-click on a unit name |
| `gui_dm_hierarchy.py` | Design Hierarchy pane (two runs: the hierarchy kept by the session) |
| `gui_dm_session.py` | Session restore and crash recovery (three runs) |
| `gui_dm_verilog_options.py` | Options > Verilog dialog and its effect |
| `gui_fsm_transitions.py` | State diagram transitions: boxes, route points, leaders, declaration blocks |
| `gui_fsm_machine_props.py [fsm.sm]` | State diagram popup menus (real right clicks) against the legacy tool's, State Machine Properties and Compiler Directives dialogs, their changes saved to the `.sm` (on a copy of gc_control_fsm) |
| `gui_fsm_save_sm.py [fsm.sm] [--keep]` | Editor save back to the legacy `.sm`: a state dragged by the mouse, a condition changed, File > Save, the file read again (on a copy unless `--keep`). Without a path: `gc_control_fsm` of the real project |

Tools that compare HDL Studio with the legacy tool itself (driving its window, batch generation,
round trips through its files) are kept outside this repository.

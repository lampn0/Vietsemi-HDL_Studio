# HDS 2021.1 behaviour, as observed on the real tool

Read with `tests/hds_gui/hds.py` on the sample project `D:/workspace/hds_reference` (Windows,
HDS 2021.1). Screenshots of each check are in `tests/hds_gui/out/` (not in git). "Done" means
HDL Studio now does the same.

## Both editors

| What | HDS | HDL Studio |
|---|---|---|
| Menus | see `bd_menus_hds.txt`, `fsm_menus_hds.txt` (BD: ... Tasks, Simulate, Add ...; FSM: ... Tasks, Add, Simulate, Animation ...) | done (VHDL / simulation / third-party entries left out) |
| Window | canvas, Diagram Browser on the right (Structure Navigator, Content pane), status bar "Ready", no tabs | done (Content pane not yet) |
| Title | `Project p: lib/unit/view * (Block Diagram)`, `... [csm] (Read-only) (State Diagram)`, `(Signals for struct)` on the table page | done |
| Opening | at the `viewArea` saved in the file, HDS 100% = 72 units / pixel (HDL Studio zoom 75/72) | done |
| Canvas | white, grid dots one pixel (103,103,103), Grid on | done |
| Fonts | diagram fonts "courier" drawn with the user's default font, Arial (Windows) | done |
| Undo | Edit > Undo shows the command: `Undo (AddBdConnectorCmd)`; switching to the Signals Table page is itself an undo step and marks the diagram modified | not done (on purpose: page switches are not edits in HDL Studio) |
| Add commands | stay active after a placement (F7, F8, F4, F3 in FSM, ...) until Esc; Esc also cancels a net being drawn | done |

## Block diagram

| What | HDS | HDL Studio |
|---|---|---|
| Add Signal / Bus | a click in open space adds a right-angle corner (after a horizontal segment the net turns vertical first), a double-click ends it there; a click on an object (port, net end, net) ends it at once and connects it | done |
| New net | selected; name `sig<n>` / `dbus<n>` (`wire [15:0]`), baseline 200 above the first segment, text 2000 after the start (right), 3000 before it (left); vertical: read upward, 200 left of the net, 2000 below / 3000 above | done |
| Signal started on a bus | dialog "Rip Element From Bus" (Specify Element); the wire carries that element (`sl "[15]"`), its name shows `bus[15]` | done (the component port on it gets the element) |
| Net name | a click on the name selects the name only: box with corner handles and a red line to the start of the net | done |
| Add Port | outline preview, the cursor on the tip of the port's stub; the port is placed without a name, selected (corner handles, keeps its colour) | done |
| Add Embedded Block | outline preview 8000 x 10000 units, cursor at the bottom-left corner; the new block is yellow, shows its name and number, a "?" icon (no view yet), selected | done (the "no view" mark is HDL Studio's own drawing) |
| Add Component (F3) | opens the floating Component Browser (library tree, hint "To instance a component, drag onto a diagram, or use Copy and Paste"); a drop puts the body's bottom-left corner at the cursor; instance name = unit, then unit1, unit2 ...; the instance is selected | done (`src/gui/component_browser.py`: F3 opens it, drag a unit onto the diagram) |
| New component layout | body size and port places from the unit's symbol (`symbol.sb`), ports on the body edges; name lines at the top of the body, starting 1800 units left of its middle; a selected component keeps its outline and gets corner handles | done (`symbol_geometry` in `import_bd.py`; without a symbol, HDL Studio's own layout) |
| Component pin names | text starts 1000 units past the pin triangle, baseline 300 below the pin line | done |
| Double-click on a component body | opens the component (its HDL / view) | already so |

## State diagram

| What | HDS | HDL Studio |
|---|---|---|
| Add State | outline circle centred on the cursor; the new state is selected; name from the diagram's `defaultState` template ("ST_"), then "ST_1", "ST_2" ... | done |
| Add Junction | outline diamond centred on the cursor; the new junction shows "&", selected | done (the symbol comes from the diagram's `defaultJunction` template; existing junctions keep theirs, e.g. "if") |
| Add Link (F4) | outline link with its stub tip on the cursor; no question asked, the link shows "Link", selected | done |
| Add Transition | a thin solid line from the source state to the cursor; on the target: the transition is selected and a box opens at its middle to type the condition (hint "value") | done |
| Double-click on a state name | edits the name in place | done (links follow the new name) |
| Double-click elsewhere on a state / on a transition | dialog "SM Object Properties - States / - Transitions": category list on the left (Clock, Resets, Enable, States, Transitions, Junctions, Links, Text, Requirement Reference, User Properties); States page: Number of selected states, Name, State Type (Simple State), Shape..., Outgoing transitions Style IF / CASE + Settings..., Implicit loopback, tabs Entry / State / Exit Actions with Visible and "Perform entry actions via implicit loopback"; Transitions page: Number of selected transitions, IF Condition (Visible), Priority spin box (Visible), Actions (Visible); buttons OK, Cancel, Apply, Help | done (`src/gui/sm_props_dialog.py`; fields HDL Studio does not keep yet are shown disabled) |

## State diagram: transitions and declaration blocks (second pass)

| What | HDS 2021.1 | HDL Studio |
|---|---|---|
| Transition text | white box, blue border (0,128,192); condition centred, a line, actions left in dark blue; selected: red border with corner handles and a red line to the transition | done |
| Lines from text boxes | only while the box is selected (red) | done (were grey dashed lines always) |
| State actions | plain text next to the state, no box | done |
| Selected transition | stays black, square handles on both ends and on route points; comes above the states | done |
| Drag on the line | nothing | done (HDL Studio added a bend point) |
| Route points | right-click: Add Route / Remove Route / Remove All Routes / Reverse Direction, Cut, Copy, Paste, Delete, Appearance..., Show Text, Object Properties...; the line is a smooth curve (spline) through them, the ends turn towards them | done (Cut / Copy / Paste / Appearance / Show Text not in the menu) |
| End handle dropped on another state | the transition is reconnected there, straight, text in the middle | done |
| Declaration blocks | at the top of the diagram: Global Actions (Pre / Post Actions), Concurrent Statements, Module Declarations (Pre / Post Decls), Signal Status (SIGNAL MODE DEFAULT RESET SCHEME COMMENT), State Register Statements, Compiler Directives (Pre- / Post- / End-module directives); titles bold, user text blue | done (`DeclBlockItem`; places read from the .sm, movable; double-click opens the page that edits the text) |

## State diagram objects (third pass, all icons of the Add menu)

Checked on a scratch diagram made in HDS (`D:/workspace/uart_hds/uart_lib/hds/uart_txshapesshapes`),
sizes read from its .sm, side by side in `tests/hds_gui/out/cmp_fsm_shapes.png` (HDS above, HDL Studio below).

| Object | HDS 2021.1 | HDL Studio |
|---|---|---|
| State | cyan circle, radius 3000 (as saved), outline (0,128,192) width 2, name Arial 10 bold | done (radius read from the file) |
| Wait state | the circle in an octagon, "wait 2" above the name | done |
| Hierarchical state | blue triple circle (117,156,255), navy outline; its states, entry and exit points are in its own diagram | done (drawn at the top level; code generation follows the paths through it, `codegen/hierarchy.py`) |
| Junction | lilac diamond 3300, symbol in Arial 10 bold: "&" (AND, new), "if", "case"; CASE shows "CASE: expr" below; style AND / IF / CASE in its properties | done |
| Link | yellow arrow 2250 x 1000, stub on its back, target name in Arial 8 bold on the right | done |
| Clock / reset / enable | yellow arrow with a symbol in it, the signal name on the left (Arial 8); clock / enable: the expression in a box at the tip | done |
| Interrupt point | red arrow with a yellow flash and a stub | done |
| Recovery state point | red circle (radius 900) with a black X | done |
| State actions | state actions alone: plain text; with entry / exit actions: one light blue cell per kind, entry and exit marked with a tick | done |
| Text colours | all black | done |
| Editing | a double-click on a text edits it in place (state name, condition, actions, entry / state / exit actions, link name, CASE expression, clock / enable expression, declaration block texts) | done |

## State diagram: machine dialogs and popup menus (fourth pass, gc_control_fsm, 2026-11-04)

Read on `protocol_controller/gc_control_fsm` in the user's project (HDS 2021.1); screenshots
`tests/hds_gui/out/smp_*.png`, `compdir.png`, `pop_*.png`; HDL Studio's in `tests/gui/out/machine_props/`.

| What | HDS 2021.1 | HDL Studio |
|---|---|---|
| State Machine Properties | one dialog (not a page): tree State Machine > Generation (> Advanced), Encoding, Statement Blocks, Declaration Blocks (> Pre/Post User Declarations), Internal Signals; OK / Cancel / Apply / Help; title "State Machine Properties - Encoding (dram_control_fsm)" (no machine name on State Machine and the declaration pages) | done (`src/gui/sm_machine_dialog.py`); editable: state signal names, encoding style / manual codes, statement block texts and Visible, Module Declarations Visible, registered / clocked affix; the rest shown disabled |
| Encoding page | Scheme Specified / Auto, Pragma, Style Sequential / 1-Hot / 2-Hot / Gray / Johnson / Manual, table "State Name / <style>", first row "23 states / 5 bits", codes as bits | done (2-Hot disabled) |
| Compiler Directives... | separate dialog "Verilog Compiler Directives": Visible, Pre- / Post- / End-Module Directives, OK / Cancel / Help | done |
| Saved in the .sm | csName / nsName in SmGenChar, stateSignalName in the header, signalSuffix / clockSuffix in the model, declaration texts (MLText st), hidden blocks (isHidden on every text of the block) | done (`export_sm._write_machine_props`, `_write_decl_blocks`); the encoding style is not written yet |
| Popup: open space | Signals Table, Open Up / Undo, Redo / Paste / View Area, Zoom In, Zoom Out, Zoom Last / View Page, Print Page... / Object Visibility... / Update Where Used..., State Machine Properties... | done |
| Popup: state | Cut, Copy, Paste, Paste Special >, Delete / Appearance..., Change Shape..., Show Text, Re-level >, Object Properties... | done (Delete, Object Properties work) |
| Popup: junction | Cut ... Delete / Appearance..., Object Properties... | done |
| Popup: link (and clock / reset / enable) | Rotate > / Cut ... Delete / Appearance..., Object Properties... | done |
| Popup: interrupt point | Rotate > / Cut ... Delete / Appearance... | done |
| Popup: recovery point | Cut ... Delete / Appearance..., Hide | done |
| Popup: text | Copy, Paste, Paste Special > / Appearance..., Hide Text, Send to Editor, Finish Edit, Finish All Edits / Object Properties... | done (Copy puts the text on the clipboard) |
| Popup: transition | ... Reverse Direction / Cut, Copy, Paste, Paste Special >, Delete / Appearance..., Show Text, Object Properties... | done |
| Cut / Copy / Paste of objects | yes | not yet |


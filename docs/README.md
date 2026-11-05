# Vietsemi HDL Studio documentation

| Document | Read it for |
|---|---|
| [user-guide.md](user-guide.md) | using the tool: projects, libraries, editors, generation, sessions, locks |
| [architecture.md](architecture.md) | how the code is organised and how data flows (start here to change the code) |
| [development.md](development.md) | set-up, repository layout, coding conventions, tests, packaging |
| [qt-guide.md](qt-guide.md) | Qt 6 / PySide6 as this code uses it: concepts, components by group with their functions and signals, the patterns of `src/gui/` (Vietnamese) |
| [roadmap.md](roadmap.md) | what works today and what is not done yet |
| [requirements.md](requirements.md) | the requirements specification (Vietnamese), with requirement ids |
| [hds-file-format.md](hds-file-format.md) | the HDS file formats: `.hdp`, folders, `.sm`, `.bd`, `.sb`, `.lck` (Vietnamese) |
| [codegen-reference.md](codegen-reference.md) | the HDL HDS generates and the rules HDL Studio follows, Verilog and SystemVerilog (Vietnamese) |
| [hds-observations.md](hds-observations.md) | HDS 2021.1 behaviour observed on the real tool (menus, gestures, dialogs) |
| [hds-graphical-editors-review.md](hds-graphical-editors-review.md) | HDL Studio checked chapter by chapter against the HDS Graphical Editors User Manual (Vietnamese) |
| [hds-batch-tcl.md](hds-batch-tcl.md) | running HDS in batch (Tcl) and driving its window from test scripts |
| [uart-compare.md](uart-compare.md) | the UART example built with HDS and with HDL Studio: what differed and what was fixed |
| [../tests/README.md](../tests/README.md) | every test, what it checks and what it needs |

Pictures used by these documents are in `resources/images/` (screenshots) and
`resources/drawings/` (diagrams, plain SVG that can be edited by hand).

The tool was called "Dolphin HDS" during the prototype. That name survives only in the
format tags of its own diagram files (`"format": "dolphin-hds-fsm"` / `"dolphin-hds-bd"`),
kept so existing `.fsm.json` / `.bd.json` files stay readable, and in some test file names.

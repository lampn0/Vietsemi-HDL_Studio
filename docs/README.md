# Vietsemi HDL Studio documentation

| Document | Read it for |
|---|---|
| [user-guide.md](user-guide.md) | using the tool: projects, libraries, editors, generation, sessions, locks |
| [architecture.md](architecture.md) | how the code is organised and how data flows (start here to change the code) |
| [development.md](development.md) | set-up, repository layout, coding conventions, tests, packaging |
| [qt-guide.md](qt-guide.md) | Qt 6 / PySide6 as this code uses it: concepts, components by group with their functions and signals, the patterns of `src/gui/` (Vietnamese) |
| [roadmap.md](roadmap.md) | what works today and what is not done yet |
| [requirements.md](requirements.md) | the requirements specification (Vietnamese), with requirement ids |
| [codegen-reference.md](codegen-reference.md) | the HDL the legacy tool generates and the rules HDL Studio follows, Verilog and SystemVerilog (Vietnamese) |
| [formats/sm-sb-bd-reference.html](formats/sm-sb-bd-reference.html) | the syntax of the legacy `.sm` / `.sb` / `.bd` files: every object type and key, their meaning, what HDL Studio reads / writes (HTML, Vietnamese; open it in a browser) |
| [../tests/README.md](../tests/README.md) | every test, what it checks and what it needs |

Pictures used by these documents are in `resources/images/` (screenshots) and
`resources/drawings/` (diagrams, plain SVG that can be edited by hand).

The syntax of the legacy files HDL Studio reads and writes is in `formats/`. The page is generated
by `resources/scripts/format_ref.py` (see its last topic) and is updated together with the import /
export code. Other notes on the legacy tool (its behaviour, the scripts that drive it to compare
with HDL Studio) are kept outside this repository.

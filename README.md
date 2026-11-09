# Vietsemi HDL Studio

**Vietsemi HDL Studio** is the RTL design and verification tool of [Vietsemi](https://vietsemi.org),
the front-end companion of **V-Layout**. It is a design manager and graphical HDL editor for
**Verilog and SystemVerilog** that works on existing projects in the legacy project format
(`.hdp` project files, `.sm` state diagrams, `.bd` block diagrams, `.sb` symbols). It opens
these projects, browses their libraries and design units, edits state diagrams and block
diagrams, edits HDL text, and generates the same Verilog / SystemVerilog that the legacy tool
generates from the same diagrams.

Written in Python with PySide6 (Qt 6); runs on Windows and CentOS Stream 9.
Version 2026.12 (revision 001; `src/version.py`, which also holds the product name used everywhere in the tool).
Settings live in `~/hdl_studio`: `user/` (per user) and `team/` (shared by a team), each with one
folder per release (`v2026.12/`). Settings of earlier builds in `~/.config/vietsemi-hdl-studio` are
copied there on first start.

![Design Manager](resources/images/screenshots/design_manager.png)

## What it does

| | |
|---|---|
| **Projects** | Open / create `.hdp` projects, with shared team projects, regular and protected libraries, environment variables in paths. |
| **Design Manager** | Libraries in tabs: Design Units (with views and default view), Files (parse errors in red), Design Hierarchy (generate frames, missing units). Session restore and crash recovery. |
| **State diagram editor** | States, transitions, junctions, links, clock / reset / recovery / enable / interrupt points, hierarchical and wait states, concurrent machines, comment texts, panels, declaration blocks, dialogs and popup menus; menus and toolbars as the legacy editor (cut / copy / paste, find / replace, align, Expression Builder, Change To). Reads and **writes back the `.sm`**, so the legacy tool and HDL Studio edit the same file. |
| **Block diagram editor** | Components (Component Browser), nets and buses, port I/Os, embedded HDL blocks, FOR / IF / ELSE generate frames, comment texts, panels, routing, Connect By Name, connectivity table (IBD), dialogs and popup menus; menus and toolbars as the legacy editor. Reads the `.bd`. |
| **HDL text editor** | Line numbers, find / replace, syntax check with slang. |
| **Generation** | Verilog-2005 / SystemVerilog, identical to the legacy tool's output; through blocks, components or the design root; hand-edited files are never overwritten without asking. |

What is not done yet is listed in [docs/roadmap.md](docs/roadmap.md).

## Quick start

```
pip install -r requirements.txt
python bin/hdlstudio.py                               # Design Manager (reopens the last session)
python bin/hdlstudio.py examples/uart_studio/uart.hdp # open the example project
```

On CentOS Stream 9 install the Qt xcb libraries first (see
[docs/development.md](docs/development.md)), then use `python3` or `bin/hdlstudio.sh`.
On Windows `bin\hdlstudio.bat` starts the tool without a console window.
Set the environment variables your projects use in their paths before starting the tool.

The [user guide](docs/user-guide.md) explains the daily work: projects, libraries, the
editors, generation, sessions and locks.

## Repository layout

```
hdl-studio/
├── bin/            launchers: hdlstudio.py (Design Manager), fsm_editor.py, .bat / .sh wrappers
├── src/            the application code (on sys.path: modules imported by their own names)
│   ├── model.py, bd_model.py    data model of state diagrams and block diagrams
│   ├── formats/                 legacy file formats: .sm / .bd / .sb readers and writers
│   ├── hdl/                     Verilog / SystemVerilog parser (pyslang)
│   ├── codegen/                 HDL generators (state machine, block diagram)
│   ├── project/                 .hdp projects, libraries, generation, locks, templates
│   ├── homes.py                 configuration folders (~/hdl_studio)
│   ├── prefs.py, session.py     preferences, session, autosave
│   ├── version.py               version number
│   └── gui/                     Qt user interface: Design Manager, editors, dialogs
├── libs/           HDL libraries shipped with the tool
├── resources/      images/ (screenshots), drawings/ (doc diagrams), scripts/ (doc checks)
├── scripts/        build, packaging and release (scripts/README.md)
├── examples/       example project (a UART built with HDL Studio)
├── tests/          unit tests and GUI tests (tests/README.md)
├── docs/           requirements, architecture, file formats, guides (docs/README.md)
├── requirements.txt
└── LICENSE
```

## Documentation

* [docs/README.md](docs/README.md) - index of all documents
* [docs/architecture.md](docs/architecture.md) - how the code is organised; read before changing it
* [docs/development.md](docs/development.md) - set-up, conventions, tests, packaging
* [docs/user-guide.md](docs/user-guide.md) - using the tool
* [docs/requirements.md](docs/requirements.md) - requirements specification
* [tests/README.md](tests/README.md) - the tests and what they need

Every module, class and function of `src/` carries an English docstring; the module
docstrings are the best entry point into each part of the code.

## Tests

```
python -m unittest discover -s tests       # unit tests, including golden HDL comparisons
python tests/gui/run_all.py                 # GUI tests: real windows, mouse and keyboard
```

## Building a release

```
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1     # Windows: dist/HDLStudio-<version>-windows-x64.zip
bash scripts/build_linux.sh                                       # Linux:   dist/HDLStudio-<version>-linux-x64.tar.gz
```

Add `-Release` / `--release` to publish the archives as the GitHub release `v<version>`.
See [scripts/README.md](scripts/README.md).

## License

GNU General Public License v3.0 - see [LICENSE](LICENSE). (c) Vietsemi.


# resources

Files that are not source code.

| Folder | Holds |
|---|---|
| `images/screenshots/` | screenshots of HDL Studio used by the README and the docs |
| `drawings/` | diagrams of the documentation, as plain SVG (edit them by hand or in Inkscape) |
| `scripts/` | `check_docs.py` (docstrings and doc links check); `format_ref.py`, `format_notes.py` and `format_ref.html` build [docs/formats/sm-sb-bd-reference.html](../docs/formats/sm-sb-bd-reference.html). Build, packaging and release scripts are in [`../scripts/`](../scripts/README.md) |

Icons of the application are drawn in code (`src/gui/icons.py`, `dm_icons.py`), so there
are no icon files to ship. Do not copy another tool's bitmaps here.

"""User preferences, stored as JSON in ~/hdl_studio/user/<release>/user_prefs.json (see homes.py)."""
from __future__ import annotations

import getpass
import json
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime

DEFAULT_HEADER = """//-----------------------------------------------------------------------------
//    Module %(library).%(unit).%(view)
//    Project: %(project_name)
//    Author: %(user)
//    Date: %(time) - %(date)
//-----------------------------------------------------------------------------"""


@dataclass
class Prefs:
    """All user preferences (Options > Preferences, Options > Main, Options > Verilog, Page Setup)
    and the list of recent projects. One JSON file per user; fields missing from the file take the
    defaults below, so new preferences can be added without breaking existing files.
    """
    default_language: str = 'systemverilog'
    default_state_decl: str = 'parameter'
    default_encoding: str = 'sequential'
    generated_name_rule: str = '%(unit).%(ext)'
    generated_lowercase: bool = True
    header_template: str = DEFAULT_HEADER
    use_external_editor: bool = False
    external_editor: str = 'gvim +{line} {file}'
    recent_projects: list[str] = field(default_factory=list)
    restore_session: bool = True     # reopen the last project and its windows at start-up
    # Options > Main... (Main Settings)
    downcase_names: bool = False                 # General: downcase design unit / view names when entered
    toolbar_remain_active: bool = True           # General: Add commands repeat (else they act once)
    temp_dir: str = '/tmp'
    text_language: str = 'systemverilog'         # General: default language of new text views
    text_extensions: str = 'txt ini tcl dcs edn edf edif'
    autosave_enabled: bool = True                # Save: automatically save recovery file
    autosave_minutes: int = 1                    # Save: every N minutes
    create_backup: bool = False                  # Save: keep <file>.bak when a view is saved
    user_variables: dict[str, str] = field(default_factory=dict)
    # Options > Verilog... (Verilog Options > File)
    verilog_extensions: str = 'v vlg verilog vo sv svh'
    source_ext: str = 'v'                        # Source Verilog (default)
    generated_ext: str = 'v'                     # Generated Verilog
    sv_ext: str = 'sv'                           # System Verilog (default), source and generated
    source_rule: str = '%(module_name).%(ext)'
    source_case: str = 'Preserve case'
    search_path: str = ''
    verilog_style: dict = field(default_factory=dict)    # Style tab; tab_width is used by generation
    view_headers: dict = field(default_factory=dict)     # Headers tab: view type -> template
    gen_properties: bool = False                 # Headers: generation properties after the header
    gen_signal_status: bool = False              # Headers: signal status of state machines
    pre_module: str = ''                         # Default Directives, copied into new views
    post_module: str = ''
    end_module: str = ''
    package_refs: str = ''                       # Default Packages, copied into new SystemVerilog views
    pragma: dict = field(default_factory=dict)   # Style > Pragma Setup: keyword, directive, sm_state_vector
    # File > Page Setup...
    page_setup: dict = field(default_factory=dict)

    @staticmethod
    def path() -> str:
        """Location of the preference file: user_prefs.json in the per-user release folder
        (~/hdl_studio/user/v2026.12/ by default, $HDLSTUDIO_HOME / $HDLSTUDIO_USER_HOME move it; tests set them).
        """
        import homes
        return os.path.join(homes.user_dir(), homes.USER_PREFS)

    @classmethod
    def load(cls) -> 'Prefs':
        """Read the preferences; defaults when the file is missing or unreadable. Unknown keys (from
        another version of the tool) are ignored.
        """
        try:
            with open(cls.path(), encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return cls()
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def save(self) -> None:
        """Write the preferences to path() (creates the folder)."""
        os.makedirs(os.path.dirname(self.path()), exist_ok=True)
        with open(self.path(), 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2)

    def header_for(self, view_type: str) -> str:
        """Header template of a view type of Verilog Options > Headers (Block Diagram, State Diagram...)."""
        return self.view_headers.get(view_type) or self.header_template

    def add_recent(self, path: str) -> None:
        """Put `path` first in File > Recent Projects (at most 10 entries) and save."""
        path = os.path.abspath(path)
        self.recent_projects = [path] + [p for p in self.recent_projects if p != path][:9]
        self.save()


def expand_header(template: str, library: str, unit: str, view: str, project_name: str) -> str:
    """Fill the %(name) placeholders of a header template (library, unit, view, project_name,
    user, date, time, year and the graphical_source_* variants the legacy tool offers) and return the text.
    """
    now = datetime.now()
    values = {
        'library': library, 'unit': unit, 'view': view, 'project_name': project_name,
        'user': getpass.getuser(), 'graphical_source_author': getpass.getuser(),
        'date': now.strftime('%m/%d/%y'), 'graphical_source_date': now.strftime('%m/%d/%y'),
        'time': now.strftime('%H:%M:%S'), 'graphical_source_time': now.strftime('%H:%M:%S'),
        'year': now.strftime('%Y'),
    }
    out = template
    for k, v in values.items():
        out = out.replace(f'%({k})', v)
    return out

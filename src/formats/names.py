"""Names fixed by the legacy project format.

They are written in users' files (sections of the .hdp file, path variables, the name of a
library's graphics folder), so they must stay exactly as the legacy tool spells them, or
existing projects would no longer open. This module is the one place in the code that spells
them; everything else uses these constants.
"""
from __future__ import annotations

META_DIR = 'hds'                     # graphics folder of a library (<lib>/hds/<unit>/<view>.<ext>),
                                     # and the .hdp section that maps each library to it
SETTINGS_SECTION = 'hds_settings'    # .hdp section: default_library, design_root, version
PROJECT_DIR_VAR = 'HDS_PROJECT_DIR'  # path variable: the folder that holds the .hdp file
TEAM_VER_VAR = 'HDS_TEAM_VER'        # path variable: the team's shared settings folder

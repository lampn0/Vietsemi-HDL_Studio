"""The configuration folders of HDL Studio, laid out like those of the legacy tool.

Everything lives under one folder in the home directory, ~/hdl_studio ($HDLSTUDIO_HOME):

    ~/hdl_studio/
        user/                       per-user settings ($HDLSTUDIO_USER_HOME)
            v2026.12/               one folder per release (user_dir())
                user_prefs.json     Options dialogs, recent projects (prefs.py)
                session.json        open project and windows (session.py)
                autosave/           unsaved editor contents (session.py)
                templates/          the user's templates for new files
                tasks/              the user's tasks
                *cache*             parse caches of the Design Manager
            logs/                   log files (logs_dir())
        team/                       settings shared by a team ($HDLSTUDIO_TEAM_HOME)
            shared.hdp              libraries every project of the team sees
            v2026.12/               one folder per release (team_dir())

The release folder is named after the year and month of the version (v2026.12 for 2026.12.NNN).
When it does not exist yet, the newest older one is copied, so preferences survive an upgrade. The settings of
the earlier layout (~/.config/vietsemi-hdl-studio) are copied once into the user folder.
"""
from __future__ import annotations

import os
import re
import shutil

ROOT_NAME = 'hdl_studio'                  # folder in the home directory
USER_PREFS = 'user_prefs.json'
TEAM_PREFS = 'team_prefs.json'
SHARED_PROJECT = 'shared.hdp'


def version_dir_name() -> str:
    """Name of the release folder: 'v' + version.RELEASE (e.g. 'v2026.12')."""
    from version import RELEASE
    return 'v' + RELEASE


def root() -> str:
    """The top folder: $HDLSTUDIO_HOME, else ~/hdl_studio."""
    return os.environ.get('HDLSTUDIO_HOME') or os.path.join(os.path.expanduser('~'), ROOT_NAME)


def user_home() -> str:
    """The per-user folder: $HDLSTUDIO_USER_HOME, else <root>/user."""
    return os.environ.get('HDLSTUDIO_USER_HOME') or os.path.join(root(), 'user')


def team_home() -> str:
    """The team folder: $HDLSTUDIO_TEAM_HOME, else <root>/team."""
    return os.environ.get('HDLSTUDIO_TEAM_HOME') or os.path.join(root(), 'team')


def _version_key(name: str) -> tuple[int, ...] | None:
    """(major, minor) of a release folder name 'vX.Y', None for other names."""
    m = re.fullmatch(r'v(\d+)\.(\d+)', name)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _release_dir(home: str) -> str:
    """<home>/v<major.minor>; created on first use by copying the newest older release folder
    of the same home, if there is one.
    """
    name = version_dir_name()
    path = os.path.join(home, name)
    if os.path.isdir(path):
        return path
    mine = _version_key(name)
    older = []
    if os.path.isdir(home):
        for entry in os.listdir(home):
            key = _version_key(entry)
            if key is not None and key < mine and os.path.isdir(os.path.join(home, entry)):
                older.append((key, entry))
    if older:
        shutil.copytree(os.path.join(home, max(older)[1]), path)
    return path


def _legacy_config() -> str:
    """Folder used by earlier builds of HDL Studio: $XDG_CONFIG_HOME or ~/.config, then the app id."""
    from version import APP_ID
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, APP_ID)


def _import_old_layout(dest: str) -> None:
    """Copy prefs.json (as user_prefs.json) and session.json of the earlier layout into `dest`,
    once: only when `dest` has no preference file yet.
    """
    old = _legacy_config()
    if os.path.exists(os.path.join(dest, USER_PREFS)) or not os.path.isdir(old):
        return
    os.makedirs(dest, exist_ok=True)
    for src, dst in (('prefs.json', USER_PREFS), ('session.json', 'session.json')):
        p = os.path.join(old, src)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(dest, dst))


def user_dir() -> str:
    """The per-user release folder (preferences, session, autosave, caches). Not created here:
    writers create it when they first save.
    """
    path = _release_dir(user_home())
    if not os.environ.get('HDLSTUDIO_HOME') and not os.environ.get('HDLSTUDIO_USER_HOME'):
        _import_old_layout(path)
    return path


def team_dir() -> str:
    """The team release folder (team preferences)."""
    return _release_dir(team_home())


def logs_dir() -> str:
    """Folder of the log files: <user home>/logs."""
    return os.path.join(user_home(), 'logs')


def shared_project() -> str:
    """Path of the team's shared project file (<team home>/shared.hdp); it may not exist."""
    return os.path.join(team_home(), SHARED_PROJECT)

"""Snapshot-based undo / redo for the diagram editors, and the per-view zoom / scroll memory.

SnapshotUndo does not record individual edit commands: the editor gives it a `snapshot()`
function (the whole model as a JSON string) and a `restore(snapshot)` function. After each edit
the editor calls note_change(); a short timer then takes one snapshot, so a burst of edits (a
drag, typing in a field) becomes a single undo step. Undo restores the previous snapshot. This
is simple and always consistent, at the cost of memory (limited to `limit` steps).

save_view_state / load_view_state keep the zoom and scroll position of each view in QSettings,
so a diagram reopens where the user left it.
"""
from __future__ import annotations

import json

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication


class SnapshotUndo(QObject):
    """Undo / redo history of one editor (see the module docstring). Emits `changed` whenever the
    history moves, so the editor can update its Undo / Redo actions and its title '*'.
    """
    changed = Signal()

    def __init__(self, snapshot, restore, parent=None, delay_ms: int = 400, limit: int = 200):
        """`snapshot()` returns the model as a string, `restore(s)` puts a snapshot back into the editor.
        `delay_ms` is how long edits are merged into one step; `limit` the number of steps kept.
        """
        super().__init__(parent)
        self._snapshot, self._restore = snapshot, restore
        self._undo: list[str] = []
        self._redo: list[str] = []
        # the name of the command of each step (the legacy popup shows "Undo (Cut)"), parallel to
        # _undo / _redo; `pending_label` names the edit not recorded yet
        self._undo_labels: list[str] = []
        self._redo_labels: list[str] = []
        self.pending_label = ''
        self._limit = limit
        self._restoring = False
        # The snapshot that matches the file on disk (taken when the view is opened and after
        # each save). Undo / redo landing on it means "no unsaved changes", so the editor can
        # drop its '*'. None: no snapshot matches the disk (e.g. recovered unsaved changes).
        self.clean: str | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._on_timer)

    def reset(self):
        """Start a fresh history from the model as it is now, which is taken as saved."""
        self._timer.stop()
        self._undo, self._redo = [self._snapshot()], []
        self._undo_labels, self._redo_labels, self.pending_label = [''], [], ''
        self.clean = self._undo[0]
        self.changed.emit()

    def mark_clean(self):
        """The model was just saved: its current state is the one on disk."""
        self.flush()
        self.clean = self._undo[-1] if self._undo else self._snapshot()

    def is_clean(self, snap: str) -> bool:
        """Whether a snapshot (e.g. the one undo just restored) equals the saved state."""
        return self.clean is not None and snap == self.clean

    def note_change(self):
        """Call after every model edit; consecutive edits are merged into one step."""
        if not self._restoring:
            self._timer.start()

    def _on_timer(self):
        """The merge delay has passed: take the snapshot (unless a mouse button is still down)."""
        # never record the model in the middle of a mouse drag: wait for the release, so one
        # drag is always one undo step even when the machine is slow
        if QGuiApplication.mouseButtons() != Qt.NoButton:
            self._timer.start()
            return
        self._take()

    def _take(self):
        """Append the current model to the history, unless it did not change; clears the redo list."""
        snap = self._snapshot()
        if self._undo and snap == self._undo[-1]:
            return
        self._undo.append(snap)
        self._undo_labels.append(self.pending_label)
        self.pending_label = ''
        del self._undo[:-self._limit]
        del self._undo_labels[:-self._limit]
        self._redo.clear()
        self._redo_labels.clear()
        self.changed.emit()

    def flush(self):
        """Take the pending snapshot now (before undo, redo or save)."""
        if self._timer.isActive():
            self._timer.stop()
            self._take()

    def undo(self):
        """Go back one step."""
        self.flush()
        if len(self._undo) < 2:
            return
        self._redo.append(self._undo.pop())
        self._redo_labels.append(self._undo_labels.pop() if self._undo_labels else '')
        self._apply(self._undo[-1])

    def redo(self):
        """Go forward one step."""
        self.flush()
        if not self._redo:
            return
        snap = self._redo.pop()
        self._undo.append(snap)
        self._undo_labels.append(self._redo_labels.pop() if self._redo_labels else '')
        self._apply(snap)

    def _apply(self, snap: str):
        """Restore a snapshot without recording the restore itself as a new change."""
        self._restoring = True
        try:
            self._restore(snap)
        finally:
            self._restoring = False
        self.changed.emit()

    def can_undo(self) -> bool:
        """True when there is a step to undo (or edits waiting to become one)."""
        return len(self._undo) > 1 or self._timer.isActive()

    def undo_label(self) -> str:
        """Name of the command the next Undo takes back ('' when unknown)."""
        if self._timer.isActive():
            return self.pending_label
        return self._undo_labels[-1] if len(self._undo) > 1 and self._undo_labels else ''

    def redo_label(self) -> str:
        """Name of the command the next Redo does again ('' when unknown)."""
        return self._redo_labels[-1] if self._redo and self._redo_labels else ''

    def can_redo(self) -> bool:
        """True when there is an undone step to redo."""
        return bool(self._redo)


_SETTINGS = ('Vietsemi', 'HDL Studio')


def save_view_state(key: str, state: dict) -> None:
    """Remember the view state (zoom, scroll position, ...) of the diagram file `key`."""
    if key:
        QSettings(*_SETTINGS).setValue('viewstate/' + key.replace('\\', '/'), json.dumps(state))


def load_view_state(key: str) -> dict | None:
    """The view state saved for `key`, or None."""
    if not key:
        return None
    raw = QSettings(*_SETTINGS).value('viewstate/' + key.replace('\\', '/'))
    try:
        return json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None

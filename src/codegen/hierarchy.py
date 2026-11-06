"""Hierarchical states for code generation.

A hierarchical state (legacy CompositeState) only groups states: it is not a state of the
machine. The legacy tool follows the paths through it:
  - a transition into the hierarchical state continues from the entry point inside it,
    so  X --c/a--> H  +  ENTRY --e/b--> Y  becomes  X --(c) & (e) / a b--> Y;
  - a transition into an exit point continues along the transitions leaving its
    hierarchical state:  Z --z/a--> EXIT  +  H --w/b--> W  becomes  Z --(z) & (w) / a b--> W.
The first transition of each path keeps its id, priority and geometry.
"""
from __future__ import annotations

import copy

from model import Machine, Transition


def _join(a: str, b: str, sep: str) -> str:
    """Join the non-blank strings among a and b with sep."""
    return sep.join(x for x in (a, b) if x.strip())


def flatten(m: Machine) -> Machine:
    """A copy of the machine without hierarchical states: their transitions resolved into
    plain transitions between the states inside (the machine itself is not changed)."""
    hier = {s.id for s in m.states if s.hier}
    if not hier:
        return m
    entries: dict[str, list[str]] = {}
    exit_owner: dict[str, str] = {}
    for p in m.points:
        if p.kind == 'entry' and p.parent:
            entries.setdefault(p.parent, []).append(p.id)
        elif p.kind == 'exit' and p.parent:
            exit_owner[p.id] = p.parent
    out_of: dict[str, list[Transition]] = {}
    for t in m.transitions:
        out_of.setdefault(t.src, []).append(t)
    plumbing = hier | set(exit_owner) | {e for es in entries.values() for e in es}

    def follow(t: Transition, src: str, dst: str, cond: str, acts: str, depth: int = 0) -> list[Transition]:
        """Follow one path from transition `t`: `cond` / `acts` are what has been collected so far.
        If `dst` is a hierarchical state, continue with the transitions leaving its entry points;
        if it is an exit point, continue with the transitions leaving its hierarchical state;
        otherwise the path ends at a real node and one plain transition src -> dst is returned.
        Conditions are ANDed (each in parentheses when both are non-empty), actions concatenated.
        """
        if depth > 16:                       # a cycle of hierarchical states: give up on it
            return []
        if dst in entries:
            nxt = [r for e in entries[dst] for r in out_of.get(e, [])]
        elif dst in exit_owner:
            nxt = out_of.get(exit_owner[dst], [])
        else:
            u = copy.copy(t)
            u.src, u.dst, u.cond, u.actions = src, dst, cond, acts
            return [u]
        res = []
        for r in nxt:
            both = cond and r.cond
            c = _join(f'({cond})' if both else cond, f'({r.cond})' if both else r.cond, ' & ')
            res += follow(t, src, r.dst, c, _join(acts, r.actions, '\n'), depth + 1)
        return res

    flat = []
    for t in m.transitions:
        if t.src in plumbing:
            continue                         # reached through the paths that lead into it
        flat += follow(t, t.src, t.dst, t.cond, t.actions)
    out = copy.copy(m)
    out.states = [s for s in m.states if not s.hier]
    out.points = [p for p in m.points if p.kind not in ('entry', 'exit')]
    out.transitions = flat
    return out

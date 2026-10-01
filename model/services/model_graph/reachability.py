"""BFS reachability within a bounded number of hops, over an adjacency map."""

from __future__ import annotations

from collections import deque


def reachable_within(roots, adjacency, depth):
    """Nodes within ``depth`` hops of ``roots`` (unlimited when ``depth`` is None)."""
    seen = set(roots)
    frontier = deque((root, 0) for root in roots)
    while frontier:
        current, distance = frontier.popleft()
        if depth is not None and distance >= depth:
            continue
        for neighbour in adjacency.get(current, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                frontier.append((neighbour, distance + 1))
    return seen

"""
One place that assembles an exploration: effective dataset -> sanitised query
-> projection. Views call ``explore`` and then ask the pieces for a payload,
search results or details, so they all agree on the same dataset and query.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dataset import EffectiveDataset
from .loader import load_effective_dataset
from .projection import Projection, project
from .query import ExplorerQuery


@dataclass(frozen=True)
class Exploration:
    dataset: EffectiveDataset
    query: ExplorerQuery
    dropped: list
    projection: Projection


def explore(model, proposal, params) -> Exploration:
    """``proposal`` is the user's active proposal (or None: canonical state only)."""
    dataset = load_effective_dataset(model, proposal)
    query, dropped = ExplorerQuery.from_params(params, dataset)
    return Exploration(dataset=dataset, query=query, dropped=dropped, projection=project(dataset, query))

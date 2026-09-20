"""
Golden cases that keep the Python Explorer logic and its JavaScript port in step.

Each case is a hand-built dataset plus a list of Explorer states and search
queries. This module runs the *Python* implementation (query sanitising,
projection, graph compilation, search, details) and records the results; the
JS test (publication/jstests/parity.test.js) feeds the same dataset and states
to the JS engine and requires identical output.

The committed fixture is ``publication/jstests/fixtures/parity.json``. When the
Python behaviour changes on purpose, regenerate it with

    WEAVE_UPDATE_PARITY=1 python manage.py test publication.tests.test_parity
"""

from __future__ import annotations

from types import SimpleNamespace

from model.services.appearance import AppearanceService
from model.services.model_graph.compiler import compile_model_graph
from model.services.model_graph.dataset import EffectiveDataset
from model.services.model_graph.details import object_details, relationship_details
from model.services.model_graph.projection import project
from model.services.model_graph.query import ExplorerQuery
from model.services.model_graph.search import search_objects
from model.services.model_graph.tests.builders import (
    APP,
    MEMBER_OF,
    OPS,
    PERSON,
    TEAM,
    USES,
    obj,
    object_type,
    rel,
    relationship_type,
    rule,
    sample_dataset,
    spec,
    uid,
)
from publication.services.bundle import build_dataset_block
from publication.services.config import PublicationScope
from publication.services.scoping import apply_scope

MODEL = SimpleNamespace(name="Parity", appearance={}, revision=1)


# ------------------------------------------------------------------------------------
# Datasets
# ------------------------------------------------------------------------------------


def unicode_dataset() -> EffectiveDataset:
    """Names, text and values chosen to expose folding, ordering and formatting differences."""
    thing_attributes = [
        spec("note", "text"),
        spec("score", "number"),
        spec("joined", "date"),
        spec("seen", "datetime"),
        spec("vip", "boolean"),
        spec("tier", "choice", ["Gold", "Silver", "STRASSE"]),
    ]
    names = [
        "Émile",
        "émile",
        "Straße",
        "STRASSE",
        "strasse",
        "İstanbul",
        "Ωmega",
        "ΟΣ",
        "ος",
        "\U0001F600 Emoji",
        "～ Fullwidth",
        "Zed",
        "zed",
        "Alice",
        "Alice",
        "  padded name  ",
        "Ünï Cödé",
        "ǅ",
        "ﬁne",
        "Tab\tname",
    ]
    values = [
        {"note": "Straße note", "score": 1.5, "joined": "2020-03-01", "seen": "2021-05-01T10:00:00Z", "vip": True, "tier": "Gold"},
        {"note": "émile likes CAFÉ", "score": 0.1, "joined": "2019-12-31", "seen": "2021-05-01T23:59:59", "vip": False, "tier": "Silver"},
        {"note": "STRASSE", "score": 100, "joined": "2021-01-01", "tier": "STRASSE"},
        {"score": -3, "joined": "2020-12-31", "seen": "2020-12-31T12:00:00"},
        {"note": "ﬁne print", "score": 30.0},
        {"note": "İ dotted", "vip": True},
        {"note": "ΟΣ ends in sigma", "score": 7},
        {"note": "\U0001F600 in a note", "tier": "Gold"},
        {},
        {"note": "   ", "score": None},
        {"note": "tie one", "score": 5},
        {"note": "tie two", "score": 5},
    ]
    objects = [
        obj(
            1000 + i,
            PERSON if i % 3 else TEAM,
            name,
            values[i % len(values)] if i % 3 else {},
            description="Beschreibung ß" if i % 5 == 0 else "",
        )
        for i, name in enumerate(names)
    ]
    person_ids = [1000 + i for i in range(len(names)) if i % 3]
    team_ids = [1000 + i for i in range(len(names)) if not i % 3]
    relationships = [
        rel(2000 + i, MEMBER_OF, person_ids[i % len(person_ids)], team_ids[i % len(team_ids)], {"since": "2020-01-0%d" % (1 + i % 9)})
        for i in range(10)
    ]
    relationships.append(rel(2100, USES, team_ids[0], team_ids[0]))  # a self-loop
    relationships.append(rel(2101, USES, team_ids[0], team_ids[1]))
    relationships.append(rel(2102, USES, team_ids[0], team_ids[1]))  # parallel edge

    return EffectiveDataset(
        object_types=[
            object_type(PERSON, "Person", thing_attributes),
            object_type(TEAM, "Team", [spec("region", "text")]),
        ],
        relationship_types=[
            relationship_type(MEMBER_OF, "Member of", [rule(PERSON, TEAM, subject=(0, 1), obj=(1, None))], [spec("since", "date")]),
            relationship_type(USES, "Uses", [rule(TEAM, TEAM)]),
        ],
        objects=objects,
        relationships=relationships,
    )


def dense_dataset() -> EffectiveDataset:
    """Enough connectivity and name/degree ties to exercise truncation ranking."""
    objects = [obj(3000 + i, APP if i % 4 else TEAM, f"Node {i % 7}", {"status": "Live"} if i % 4 else {}) for i in range(36)]
    relationships = []
    number = 4000
    for i in range(36):
        for step in (1, 5):
            j = (i * step + 3) % 36
            if i != j:
                relationships.append(rel(number, USES, 3000 + i, 3000 + j))
                number += 1
    return EffectiveDataset(
        object_types=[object_type(TEAM, "Team"), object_type(APP, "Application", [spec("status", "choice", ["Live", "Retired"])])],
        relationship_types=[relationship_type(USES, "Uses", [rule(TEAM, APP)])],
        objects=objects,
        relationships=relationships,
    )


def _published(dataset: EffectiveDataset) -> EffectiveDataset:
    """The dataset as Publishing would embed it (canonical, attributes cleaned)."""
    return apply_scope(dataset, PublicationScope())


# ------------------------------------------------------------------------------------
# States and queries
# ------------------------------------------------------------------------------------


def _filter(type_number, key, op, value):
    return {"type_id": uid(type_number), "key": key, "op": op, "value": value}


def sample_states():
    return [
        {},
        {"limit": 3},
        {"hiddenObjectTypes": [uid(TEAM)]},
        {"hiddenRelationshipTypes": [uid(MEMBER_OF)]},
        {"hiddenObjectTypes": [uid(TEAM)], "include": [uid(OPS)]},
        {"attributeFilters": [_filter(APP, "status", "in", ["live"])]},
        {"attributeFilters": [_filter(APP, "critical", "in", ["true"])]},
        {"attributeFilters": [_filter(APP, "owner", "contains", "CAR")]},
        {"attributeFilters": [_filter(APP, "users", "range", {"min": 100, "max": 5000})]},
        {"attributeFilters": [_filter(APP, "users", "range", {"min": "41", "max": None})]},
        {"attributeFilters": [_filter(APP, "launched", "range", {"min": "2016-01-01", "max": "2021-03-01"})]},
        {"attributeFilters": [_filter(PERSON, "email", "contains", "two"), _filter(APP, "status", "in", ["Retired"])]},
        {"hiddenObjectTypes": [uid(999), "not-a-uuid", uid(APP).upper()], "include": [uid(12345), "{" + uid(OPS) + "}"]},
        {
            "attributeFilters": [
                _filter(APP, "nope", "in", ["x"]),
                _filter(APP, "status", "range", {"min": 1}),
                _filter(APP, "status", "in", []),
                _filter(APP, "owner", "contains", "  "),
                _filter(APP, "users", "range", {"min": "abc"}),
                _filter(APP, "users", "range", {"min": None, "max": ""}),
                "junk",
                _filter(APP, "status", "in", ["Live"]),
                _filter(APP, "status", "in", ["Live"]),
            ]
        },
        {"limit": 0},
        {"limit": "2"},
        {"limit": "many"},
        {"hiddenRelationshipTypes": [uid(USES)], "limit": 2, "include": [uid(999)]},
    ]


def unicode_states():
    person, team = PERSON, TEAM
    return [
        {},
        {"limit": 5},
        {"limit": 5, "include": [uid(1000 + 19), uid(1000 + 10)]},
        {"hiddenObjectTypes": [uid(team)]},
        {"hiddenRelationshipTypes": [uid(USES)]},
        {"attributeFilters": [_filter(person, "tier", "in", ["strasse"])]},
        {"attributeFilters": [_filter(person, "tier", "in", ["Gold", "silver"])]},
        {"attributeFilters": [_filter(person, "vip", "in", ["true"])]},
        {"attributeFilters": [_filter(person, "vip", "in", ["false", "TRUE"])]},
        {"attributeFilters": [_filter(person, "note", "contains", "STRASSE")]},
        {"attributeFilters": [_filter(person, "note", "contains", "straße")]},
        {"attributeFilters": [_filter(person, "note", "contains", "ΟΣ")]},
        {"attributeFilters": [_filter(person, "note", "contains", "café")]},
        {"attributeFilters": [_filter(person, "score", "range", {"min": 0, "max": 10})]},
        {"attributeFilters": [_filter(person, "score", "range", {"min": None, "max": 1.5})]},
        {"attributeFilters": [_filter(person, "score", "range", {"min": "5", "max": "5"})]},
        {"attributeFilters": [_filter(person, "joined", "range", {"min": "2020-01-01", "max": "2020-12-31"})]},
        {"attributeFilters": [_filter(person, "seen", "range", {"min": "2021-05-01", "max": "2021-05-01"})]},
        {"attributeFilters": [_filter(person, "seen", "range", {"min": None, "max": "2021-05-01T10:00:00Z"})]},
        {"attributeFilters": [_filter(team, "region", "contains", "x")]},
    ]


def dense_states():
    return [
        {},
        {"limit": 5},
        {"limit": 8, "include": [uid(3030), uid(3031)]},
        {"limit": 10, "hiddenObjectTypes": [uid(TEAM)]},
        {"limit": 4, "attributeFilters": [_filter(APP, "status", "in", ["Live"])]},
    ]


SAMPLE_QUERIES = ["alice", "  ALICE   two ", "ops", "carol", "1200", "2021", "web", "live", "example.com", "zzz", "", "  "]
UNICODE_QUERIES = [
    "straße",
    "STRASSE",
    "strasse",
    "émile",
    "EMILE",
    "ΟΣ",
    "ος",
    "ωmega",
    "istanbul",
    "\U0001F600",
    "ﬁne",
    "fine",
    "zed",
    "alice",
    "tie",
    "beschreibung",
    "ß",
    "gold",
    "  padded   name ",
    "1.5",
    "e",
    "i",
]
DENSE_QUERIES = ["node", "node 3", "live", "4"]


# ------------------------------------------------------------------------------------
# Running the Python implementation
# ------------------------------------------------------------------------------------


def _dropped(entries):
    # The id of a dropped filter is a Python-formatted JSON dump; only kind and reason are contractual.
    return [{"kind": e["kind"], "reason": e["reason"]} for e in entries]


def _run_state(dataset, state, queries, with_details):
    query, dropped = ExplorerQuery.from_state(state, dataset)
    projection = project(dataset, query)

    step = {
        "state": state,
        "graph": {
            "payload": compile_model_graph(MODEL, dataset, projection).to_dict(),
            "summary": projection.summary.to_dict(),
            "state": query.to_state(),
            "dropped": _dropped(dropped),
        },
    }
    if queries:
        step["search"] = [
            {"q": q, "result": {**search_objects(dataset, q, projection=projection).to_dict(), "state": query.to_state()}}
            for q in queries
        ]
    if with_details:
        step["details"] = {
            "objects": {oid: object_details(dataset, oid, projection) for oid in dataset.objects},
            "relationships": {rid: relationship_details(dataset, rid, projection) for rid in dataset.relationships},
        }
    return step


def build_case(name, dataset, states, queries, details_states=(0,)):
    dataset = _published(dataset)
    empty = project(dataset, ExplorerQuery())
    template = {**compile_model_graph(MODEL, dataset, empty).to_dict(), "nodes": [], "edges": []}
    resolver = AppearanceService.resolver(MODEL)

    steps = []
    for index, state in enumerate(states):
        steps.append(_run_state(dataset, state, queries if index in details_states else [], index in details_states))
    return {
        "name": name,
        "dataset": build_dataset_block(dataset, resolver),
        "template": template,
        "canvasBackground": resolver.theme.canvas_background,
        "steps": steps,
    }


def build_fixture() -> dict:
    return {
        "version": 1,
        "cases": [
            build_case("sample", sample_dataset(), sample_states(), SAMPLE_QUERIES, details_states=(0, 2, 12)),
            build_case("unicode", unicode_dataset(), unicode_states(), UNICODE_QUERIES, details_states=(0, 3)),
            build_case("dense", dense_dataset(), dense_states(), DENSE_QUERIES, details_states=(0, 1)),
        ],
    }

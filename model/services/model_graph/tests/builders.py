"""Hand-built effective datasets for the pure (no database) model_graph tests."""

import uuid

from model.services.model_graph.dataset import (
    AttributeSpec,
    CardinalityRule,
    EffectiveAttributeDefinition,
    EffectiveDataset,
    EffectiveObject,
    EffectiveObjectType,
    EffectiveRelationship,
    EffectiveRelationshipType,
    EffectiveRelationshipTypeRule,
)


def uid(number: int) -> str:
    return str(uuid.UUID(int=number))


def spec(key, data_type="text", choices=(), name=None):
    return AttributeSpec(key=key, name=name or key.replace("_", " ").title(), data_type=data_type, choices=tuple(choices))


def object_type(number, name, attributes=(), proposed=False):
    return EffectiveObjectType(
        id=uid(number), key=name.lower(), name=name, is_proposed=proposed, attributes=tuple(attributes)
    )


def relationship_type(number, name, rules=(), attributes=(), proposed=False):
    return EffectiveRelationshipType(
        id=uid(number),
        key=name.lower().replace(" ", "_"),
        name=name,
        is_proposed=proposed,
        attributes=tuple(attributes),
        rules=tuple(rules),
    )


def rule(subject_type, object_type_, subject=(0, None), obj=(0, None)):
    return CardinalityRule(uid(subject_type), uid(object_type_), subject[0], subject[1], obj[0], obj[1])


def obj(number, type_number, name, attributes=None, proposed=False, created=False, description="", key=None):
    return EffectiveObject(
        id=uid(number),
        type_id=uid(type_number),
        name=name,
        key=key if key is not None else name.lower().replace(" ", "_"),
        description=description,
        attributes=attributes or {},
        is_proposed=proposed,
        is_created=created,
    )


def attribute_definition(number, key, name, data_type, *, parent_type, parent_number):
    return EffectiveAttributeDefinition(
        id=uid(number),
        key=key,
        name=name,
        data_type=data_type,
        parent_type=parent_type,
        parent_id=uid(parent_number),
    )


def relationship_type_rule(number, relationship_type_number, subject_type_number, object_type_number, **cardinality):
    cardinality.setdefault("subject_minimum", 0)
    cardinality.setdefault("subject_maximum", None)
    cardinality.setdefault("object_minimum", 0)
    cardinality.setdefault("object_maximum", None)
    return EffectiveRelationshipTypeRule(
        id=uid(number),
        relationship_type_id=uid(relationship_type_number),
        subject_type_id=uid(subject_type_number),
        object_type_id=uid(object_type_number),
        **cardinality,
    )


def rel(number, type_number, source_number, target_number, attributes=None, proposed=False, created=False):
    return EffectiveRelationship(
        id=uid(number),
        type_id=uid(type_number),
        source_id=uid(source_number),
        target_id=uid(target_number),
        attributes=attributes or {},
        is_proposed=proposed,
        is_created=created,
    )


# Ids used by ``sample_dataset``.
PERSON, TEAM, APP = 1, 2, 3
MEMBER_OF, USES = 11, 12
ALICE, BOB, ALICE_TWO, OPS, WEB, BILLING, LONER = 101, 102, 103, 201, 301, 302, 401


def sample_dataset() -> EffectiveDataset:
    """
    People, teams and applications.

        Alice --member_of--> Ops        Ops --uses--> Web
        Bob   --member_of--> Ops        Ops --uses--> Billing
        Alice(2) (a namesake, no links) Loner (an isolated Team-less App)
    """
    app_attributes = [
        spec("status", "choice", ["Live", "Retired"]),
        spec("owner", "text"),
        spec("users", "number"),
        spec("launched", "date"),
        spec("critical", "boolean"),
    ]
    return EffectiveDataset(
        object_types=[
            object_type(PERSON, "Person", [spec("email", "text")]),
            object_type(TEAM, "Team"),
            object_type(APP, "Application", app_attributes),
        ],
        relationship_types=[
            relationship_type(MEMBER_OF, "Member of", [rule(PERSON, TEAM)], [spec("since", "date")]),
            relationship_type(USES, "Uses", [rule(TEAM, APP, subject=(1, None), obj=(0, 1))]),
        ],
        objects=[
            obj(ALICE, PERSON, "Alice", {"email": "alice@example.com"}),
            obj(BOB, PERSON, "Bob"),
            obj(ALICE_TWO, PERSON, "Alice", {"email": "alice.two@example.com"}, key="alice_two"),
            obj(OPS, TEAM, "Ops"),
            obj(
                WEB,
                APP,
                "Web Portal",
                {"status": "Live", "owner": "Carol", "users": 1200, "launched": "2021-03-01", "critical": True},
            ),
            obj(
                BILLING,
                APP,
                "Billing",
                {"status": "Retired", "owner": "Dave", "users": 40, "launched": "2015-06-10", "critical": False},
            ),
            obj(LONER, APP, "Loner", {"status": "Live"}),
        ],
        relationships=[
            rel(1001, MEMBER_OF, ALICE, OPS, {"since": "2022-01-01"}),
            rel(1002, MEMBER_OF, BOB, OPS),
            rel(1003, USES, OPS, WEB),
            rel(1004, USES, OPS, BILLING),
        ],
    )

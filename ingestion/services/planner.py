"""
Entry point for planning an import: source table + target + mapping in,
`ImportPlan` out. Read-only: it queries canonical tables and writes nothing.
"""

from ingestion.services.mapping import ImportMapping
from ingestion.services.object_planner import plan_object_import
from ingestion.services.plan import ImportPlan
from ingestion.services.relationship_planner import plan_relationship_import
from ingestion.services.targets import OBJECT, RELATIONSHIP, object_type_specs, resolve_target


def build_plan(model, table, mapping_payload) -> ImportPlan:
    """
    Resolve the target named in the (untrusted) payload inside `model`,
    validate the mapping against it and the table, and plan the import.

    Raises TargetError / MappingError for a target or mapping that cannot be
    used; row-level problems come back on the plan as blocking `problems`.
    """

    declared = mapping_payload.get("target") if isinstance(mapping_payload, dict) else None
    declared = declared if isinstance(declared, dict) else {}

    target = resolve_target(model, declared.get("kind"), declared.get("type_id"))

    endpoint_types = object_type_specs(model) if target.kind == RELATIONSHIP else None

    mapping = ImportMapping.from_json(
        mapping_payload,
        target,
        column_count=table.column_count,
        endpoint_types=endpoint_types,
    )

    if target.kind == OBJECT:
        return plan_object_import(model, table, target, mapping)

    return plan_relationship_import(model, table, target, mapping, endpoint_types)

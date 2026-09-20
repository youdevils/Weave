"""
Addressing of field-level changes.

Object/Relationship attribute values live inside a single `attributes` JSON
blob rather than as top-level model fields, so a field-level UPDATE addresses
them with a dot-namespaced path ("attributes.<key>") instead of a bare field
name. Shared by the record editors, the proposal pipeline and Data Import.
"""

ATTRIBUTE_FIELD_PREFIX = "attributes."


def attribute_field_name(key):
    return f"{ATTRIBUTE_FIELD_PREFIX}{key}"

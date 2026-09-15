from django.db.models import Q

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.relationship import Relationship
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.validation.cardinality import validate_cardinality
from model.services.validation.objects import validate_object
from model.services.validation.relationships import validate_relationship
from model.services.validation.result import ValidationIssue, ValidationResult
from model.services.validation.structural import (
    validate_attribute_definition,
    validate_relationship_type_rule,
)


def validate_model(model: Model) -> ValidationResult:
    """
    Validate the complete current state of a Model: every active
    Object and Relationship against their type's attribute
    definitions, every AttributeDefinition/RelationshipTypeRule
    against its own structural invariants, and cardinality across the
    whole model.

    Called against canonical DB state that already reflects a
    proposal's changes (applied but not yet committed), so this
    validates the effective model a proposal would produce, using the
    existing validators unmodified.
    """

    issues: list[ValidationIssue] = []

    for definition in AttributeDefinition.objects.filter(
        Q(object_type__model=model) | Q(relationship_type__model=model),
        is_active=True,
    ):
        issues.extend(validate_attribute_definition(definition).issues)

    for rule in RelationshipTypeRule.objects.filter(
        relationship_type__model=model,
    ):
        issues.extend(validate_relationship_type_rule(rule).issues)

    for obj in Object.objects.filter(model=model, is_active=True):
        issues.extend(validate_object(obj).issues)

    for relationship in Relationship.objects.filter(model=model, is_active=True):
        issues.extend(validate_relationship(relationship).issues)

    issues.extend(validate_cardinality(model).issues)

    return ValidationResult(issues=issues)

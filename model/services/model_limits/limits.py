"""
Enforces the acting user's Plan model-count limit on Model creation.

A "Model limit" is purely a count of currently-existing Models in the
user's own Workspace -- there is no archive/retire concept on Model itself
(see model.models.model.Model), so deleting a Model always frees a slot.
"""

from account.services.entitlement import user_model_limit


class ModelLimitReached(Exception):
    """The acting user already owns the maximum number of Models their plan allows."""


def ensure_can_create_model(user, workspace) -> None:
    limit = user_model_limit(user)
    if workspace.models.count() >= limit:
        raise ModelLimitReached(
            f"Your {user.get_plan_display()} plan allows up to {limit} models. "
            "Delete an existing model before creating another."
        )

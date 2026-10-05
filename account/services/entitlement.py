"""
The single place that turns a user's Plan into allow/deny decisions and
numeric limits.

Feature code asks "can this user do X" / "how many Y can this user have"
through the functions below -- it never compares account.plan against a
Plan constant directly. See account.models.CustomUser.Plan for the
persisted field this reads, and _PLAN_ENTITLEMENTS below for what each plan
actually grants.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from account.models import CustomUser


@dataclass(frozen=True)
class Entitlements:
    model_limit: int
    publication_enabled: bool
    assisted_enabled: bool
    assisted_token_limit: int | None  # None = unlimited


# assisted_token_limit for COLLABORATOR is a placeholder here -- entitlements_for()
# overrides it with the live settings.ASSISTED_TOKEN_LIMIT_COLLABORATOR on every
# call, rather than baking it in at module-import time, so it stays overridable
# via @override_settings in tests and via a real settings change in production.
_PLAN_ENTITLEMENTS: dict[str, Entitlements] = {
    CustomUser.Plan.LEARNER: Entitlements(
        model_limit=2,
        publication_enabled=False,
        assisted_enabled=False,
        assisted_token_limit=None,
    ),
    CustomUser.Plan.COMMUNICATOR: Entitlements(
        model_limit=10,
        publication_enabled=True,
        assisted_enabled=False,
        assisted_token_limit=None,
    ),
    CustomUser.Plan.COLLABORATOR: Entitlements(
        model_limit=20,
        publication_enabled=True,
        assisted_enabled=True,
        assisted_token_limit=None,
    ),
}


def entitlements_for(user) -> Entitlements:
    ent = _PLAN_ENTITLEMENTS[user.plan]
    if user.plan == CustomUser.Plan.COLLABORATOR:
        ent = replace(ent, assisted_token_limit=settings.ASSISTED_TOKEN_LIMIT_COLLABORATOR)
    return ent


def user_model_limit(user) -> int:
    return entitlements_for(user).model_limit


def user_can_publish(user) -> bool:
    return entitlements_for(user).publication_enabled


def user_can_run_assisted(user) -> bool:
    ent = entitlements_for(user)
    if not ent.assisted_enabled:
        return False
    if ent.assisted_token_limit is None:
        return True
    return _assisted_tokens_used_this_period(user) < ent.assisted_token_limit


def _assisted_tokens_used_this_period(user) -> int:
    # Local import: avoids a module-level account -> assisted dependency,
    # the reverse of assisted's own module-level account -> entitlement
    # import (assisted/services/lifecycle.py, assisted/services/execution.py).
    from assisted.models import AssistedTask

    now = timezone.now()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = AssistedTask.objects.filter(
        creator=user,
        created_at__gte=period_start,
    ).aggregate(total=Sum("tokens_used"))["total"]
    return total or 0

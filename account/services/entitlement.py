"""
The single place that turns a user's Assisted entitlement into an
allow/deny decision.

Deliberately trivial today (a one-field lookup) so that future
billing/plan logic can change how the entitlement is derived without
touching any of Assisted's call sites -- see account.models.CustomUser
.assisted_tier for the persisted field this reads.
"""

from __future__ import annotations

from account.models import CustomUser


def user_can_run_assisted(user) -> bool:
    return user.assisted_tier == CustomUser.AssistedTier.ENHANCED

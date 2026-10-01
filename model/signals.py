"""
Domain lifecycle signals for Proposal's own state transitions -- not a
generic pub/sub bus. Each fires exactly once, at the exact moment a
Proposal transitions (committed on successful submission, abandoned when
the user declines it), synchronously inside the sender's own transaction --
see the send sites in model/services/proposal/{submission,proposal}.py.

model owns both signals and both transition points; it only ever emits,
never imports ai or assisted. assisted (assisted/signals.py) is the one
consumer today.
"""

import django.dispatch

# kwargs: proposal_id (uuid), model_id (uuid).
proposal_committed = django.dispatch.Signal()
proposal_abandoned = django.dispatch.Signal()

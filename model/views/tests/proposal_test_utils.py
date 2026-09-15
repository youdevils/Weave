"""
Shared test helper for simulating "this proposal is the active one"
in the session, without requiring a full HTTP round-trip through the
proposal review page (which is what sets it as a side effect of a
real GET in production).
"""

from model.views.active_proposal import SESSION_KEY


def activate_proposal(client, model_id, proposal):
    session = client.session
    active = session.get(SESSION_KEY, {})
    active[str(model_id)] = str(proposal.id)
    session[SESSION_KEY] = active
    session.save()

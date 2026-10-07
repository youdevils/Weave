"""
Identity (C4): which canonical Object, if any, an evidence entity cluster is.

OnyxJar binds a cluster to an existing Object only as a lexical
transformation of the cluster's own claim -- exactly one Object of the mapped
type whose key, name or alias is identical after normalisation
(SemanticModelIndex.match_objects) -- and records it `basis: lexical` for
Verification. Several exact matches, or near matches (one name's words
contained in the other's), are `ambiguous`: an Adjudication question whose
options are those Objects plus "new". No match at all means `new`. A retired
match means `reactivate`. Generic entities have no identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings

from ai.services.reconcile import questions as q
from ai.services.reconcile.ledger import IDENTITY, Ledger
from ai.services.reconcile.normalise import ClusterResult
from ai.services.semantic.index import SemanticModelIndex, normalize_name


@dataclass
class Identity:
    cluster_id: str
    outcome: str  # existing | reactivate | new | ambiguous | none | unresolved_ambiguity
    object_id: str | None = None
    basis: str = ""
    options: list = field(default_factory=list)  # Object keys (+ "new")
    decision_id: str = ""

    @property
    def resolved(self) -> bool:
        return self.outcome in ("existing", "reactivate", "new")


def _near_matches(index: SemanticModelIndex, type_id, names) -> list:
    wanted = [set(n.split()) for n in names if n]
    found = []
    for obj in index.objects_of_type(type_id):
        words = set(normalize_name(obj.name).split())
        if words and any(w and (w <= words or words <= w) for w in wanted):
            found.append(obj)
    return found


def resolve_identities(clusters: ClusterResult, types: dict, *, index: SemanticModelIndex, pins: dict, ledger: Ledger) -> dict[str, Identity]:
    result = {}
    for cid, cluster in clusters.clusters.items():
        mapping = types[cid]
        pin_key = q.key("identity", cid)
        inputs = [*cluster.member_eids, mapping.decision_id, *q.pin_inputs(pin_key, pins)]
        identity = Identity(cid, "none")

        if cluster.specificity == "generic" or mapping.outcome != "mapped":
            identity.outcome = "none"
        else:
            exact = index.match_objects(mapping.type_id, cluster.name, cluster.aliases)
            exact_ids = {m.object.id for m in exact}
            near = [o for o in _near_matches(index, mapping.type_id, cluster.names()) if o.id not in exact_ids]
            candidates = [*(m.object for m in exact), *near][: settings.AI_MAPPING_MAX_OPTIONS]
            pin = pins.get(pin_key)
            if pin is not None:
                chosen = next((o for o in candidates if o.key == pin.option_id), None)
                if chosen is not None:
                    identity = Identity(cid, "existing" if chosen.is_active else "reactivate", chosen.id, "adjudicated")
                elif pin.option_id == q.NEW:
                    identity = Identity(cid, "new", basis="adjudicated")
                else:
                    identity = Identity(cid, "unresolved_ambiguity", basis=pin.basis, options=[o.key for o in candidates] + [q.NEW])
            elif len(exact) == 1 and not near:
                obj = exact[0].object
                identity = Identity(cid, "existing" if obj.is_active else "reactivate", obj.id, "lexical")
            elif candidates:
                identity = Identity(cid, "ambiguous", options=[o.key for o in candidates] + [q.NEW])
            else:
                identity = Identity(cid, "new", basis="deterministic")

        identity.decision_id = f"ident:{cid}"
        obj = index.objects.get(identity.object_id) if identity.object_id else None
        ledger.structural(
            identity.decision_id, step=IDENTITY, basis=identity.basis or "deterministic", subject_ids=[cid], inputs=inputs,
            outcome=identity.outcome, options=[{"option_id": o} for o in identity.options],
            source={"name": cluster.name, "aliases": cluster.aliases},
            mapping={"object_key": obj.key, "object_name": obj.name, "active": obj.is_active} if obj else None,
            flags=["lexical_identity"] if identity.basis == "lexical" else (["unresolved_ambiguity"] if identity.outcome == "unresolved_ambiguity" else []),
            question_key=pin_key,
        )
        result[cid] = identity
    return result

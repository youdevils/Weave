"""
The rugby reconciliation scenario -- the real E2E case that exposed the
CandidateSet architecture's failure modes -- as a reusable fixture.

Ontology: Tournament -has_stage-> Stage -has_match-> Match -has_team-> Team
(x2 minimum), Match -played_at-> Venue, Tournament -sponsors-> Sponsor
(optional). Venue defines a numeric `capacity` attribute, and nothing for a
location or primary use -- the flyer states both.

The pre-existing 2027 Championship is given a complete, already-valid chain
(validate_model runs model-wide on every staged attempt, so a bare
Tournament would fail has_stage's minimum regardless of intent). A
pre-existing, unconnected Sponsor is never mentioned by the evidence and must
never be touched.

The flyer's "Forsyth Barr Stadium | ... | Pool matches" says the venue hosts
pool matches without identifying which -- extracted as a `generic` Match, it
is the canonical `intermediate_unidentified` case (never compiled).
"""

from pathlib import Path

from ai.tests.support import (
    AIServiceTestCase,
    anchor,
    assertion,
    entity,
    extraction,
    fact,
    frame,
    target,
)

FLYER_TEXT = (Path(__file__).parent / "fixtures" / "rugby_flyer.txt").read_text(encoding="utf-8")
FLYER_ASSETS = [{"name": "flyer.txt", "content": FLYER_TEXT, "mime_type": "text/plain"}]
INTENT = (
    "Add the venues and stages listed in the flyer to the 2027 Championship, and create any "
    "relationships that should be associated as well."
)


class RugbyFixture(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model(name="Rugby", purpose="Track rugby tournaments.", scope="Tournaments.", exclusions="")
        self.tournament_type = self.make_object_type(self.model, key="tournament")
        self.stage_type = self.make_object_type(self.model, key="stage")
        self.match_type = self.make_object_type(self.model, key="match")
        self.team_type = self.make_object_type(self.model, key="team")
        self.venue_type = self.make_object_type(self.model, key="venue")
        self.sponsor_type = self.make_object_type(self.model, key="sponsor")

        self.has_stage = self.make_relationship_type(self.model, key="has_stage")
        self.has_match = self.make_relationship_type(self.model, key="has_match")
        self.has_team = self.make_relationship_type(self.model, key="has_team")
        self.played_at = self.make_relationship_type(self.model, key="played_at")
        self.sponsors = self.make_relationship_type(self.model, key="sponsors")

        self.make_attribute_definition(object_type=self.venue_type, key="capacity", data_type="number")

        self.make_rule(self.has_stage, self.tournament_type, self.stage_type, object_minimum=1)
        self.make_rule(self.has_match, self.stage_type, self.match_type, object_minimum=1)
        self.make_rule(self.has_team, self.match_type, self.team_type, object_minimum=2)
        self.make_rule(self.played_at, self.match_type, self.venue_type, object_minimum=1)
        self.make_rule(self.sponsors, self.tournament_type, self.sponsor_type)

        self.tournament = self.make_object(self.model, self.tournament_type, name="2027 Championship", key="championship_2027")
        stage = self.make_object(self.model, self.stage_type, name="Qualifying Stage", key="qualifying_stage")
        match = self.make_object(self.model, self.match_type, name="Qualifier Match", key="qualifier_match")
        team_a = self.make_object(self.model, self.team_type, name="Qualifier Team A", key="qualifier_team_a")
        team_b = self.make_object(self.model, self.team_type, name="Qualifier Team B", key="qualifier_team_b")
        venue = self.make_object(self.model, self.venue_type, name="Qualifier Venue", key="qualifier_venue")
        self.make_relationship(self.model, self.has_stage, self.tournament, stage)
        self.make_relationship(self.model, self.has_match, stage, match)
        self.make_relationship(self.model, self.has_team, match, team_a)
        self.make_relationship(self.model, self.has_team, match, team_b)
        self.make_relationship(self.model, self.played_at, match, venue)

        self.sponsor = self.make_object(self.model, self.sponsor_type, name="Acme Corp", key="acme_corp")

    # -- Extraction output (claims) ---------------------------------------------

    def flyer_frame(self, **kwargs):
        return frame(
            [target("T1", "venues", "venues"), target("T2", "stages", "stages")],
            [anchor("N1", "2027 Championship", "the 2027 Championship", hint="tournament")],
            include_related=True, include_related_excerpt="create any relationships that should be associated",
            restated="Add the flyer's venues and stages to the 2027 Championship, with their relationships.",
            **kwargs,
        )

    def flyer_items(self, *, include_fiji=True, include_forsyth_barr=True, hints=True):
        hint = (lambda key: key) if hints else (lambda key: None)
        items = [
            entity("E1", "2027 Championship", "championship", hint=hint("tournament"), excerpt="2027 Championship", source_id="intent"),
            entity("E2", "Pool Stage", "stage", hint=hint("stage"), excerpt="Pool Stage"),
            entity("E3", "Match 1", "match", hint=hint("match"), excerpt="Match 1: New Zealand v Fiji"),
            entity("E4", "New Zealand", "team", hint=hint("team"), excerpt="New Zealand v Fiji"),
            entity("E6", "Eden Park", "venue", hint=hint("venue"), excerpt="Eden Park | Auckland"),
            # The intent links the flyer's stages to the 2027 Championship; the
            # flyer names this stage -- a structural claim citing both.
            assertion("A1", "E1", "includes stage", "E2", hint=hint("has_stage"), support="structural",
                      spans=[("stages listed in the flyer to the 2027 Championship", "intent"), ("Pool Stage", "S1")]),
            assertion("A2", "E2", "includes", "E3", hint=hint("has_match"), excerpt="Pool Stage"),
            assertion("A3", "E3", "is played by", "E4", hint=hint("has_team"), excerpt="Match 1: New Zealand v Fiji"),
            assertion("A5", "E3", "played at", "E6", hint=hint("played_at"), excerpt="played at Eden Park"),
            fact("F1", "E6", "City", "Auckland", excerpt="Eden Park | Auckland"),
            fact("F2", "E6", "Capacity", "50000", excerpt="Eden Park capacity: 50000"),
            fact("F3", "E6", "Use", "Opening match and final", excerpt="Opening match and final"),
        ]
        if include_fiji:
            items += [
                entity("E5", "Fiji", "team", hint=hint("team"), excerpt="New Zealand v Fiji"),
                assertion("A4", "E3", "is played by", "E5", hint=hint("has_team"), excerpt="Match 1: New Zealand v Fiji"),
            ]
        if include_forsyth_barr:
            items += [
                entity("E7", "Forsyth Barr Stadium", "venue", hint=hint("venue"), excerpt="Forsyth Barr Stadium | Dunedin"),
                entity("E8", "Pool matches", "match", hint=hint("match"), specificity="generic", excerpt="Pool matches"),
                assertion("A6", "E7", "hosts", "E8", hint=hint("played_at"), orientation="converse", excerpt="Forsyth Barr Stadium | Dunedin | Pool matches"),
                fact("F4", "E7", "City", "Dunedin", excerpt="Forsyth Barr Stadium | Dunedin"),
            ]
        return items

    def flyer_extraction(self, **kwargs):
        return extraction(self.flyer_frame(), *self.flyer_items(**kwargs))

    # -- ChangeSet v3 (resolver / staging tests) --------------------------------

    def tournament_ref(self):
        return {"kind": "existing", "type_key": "tournament", "key": "championship_2027"}

    def chain_actions(self, *, include_fiji=True, include_forsyth_barr=True, eden_park=None):
        """
        The full evidenced ChangeSet. `eden_park` overrides how Eden Park is
        represented (default: created new, with capacity).
        """

        new = lambda t: {"kind": "new", "token": t}  # noqa: E731
        evidence = lambda excerpt: [{"source_id": "S1", "excerpt": excerpt}]  # noqa: E731
        actions = [
            {"kind": "create_object", "action_id": "a1", "token": "stage", "type": {"kind": "existing", "key": "stage"},
             "name": "Pool Stage", "provenance": evidence("Pool Stage")},
            {"kind": "create_relationship", "action_id": "a2", "relationship_type": {"kind": "existing", "key": "has_stage"},
             "subject": self.tournament_ref(), "object": new("stage"), "provenance": evidence("Pool Stage")},
            {"kind": "create_object", "action_id": "a3", "token": "match", "type": {"kind": "existing", "key": "match"},
             "name": "New Zealand v Fiji", "provenance": evidence("Match 1: New Zealand v Fiji")},
            {"kind": "create_relationship", "action_id": "a4", "relationship_type": {"kind": "existing", "key": "has_match"},
             "subject": new("stage"), "object": new("match")},
            {"kind": "create_object", "action_id": "a5", "token": "nz", "type": {"kind": "existing", "key": "team"},
             "name": "New Zealand"},
            {"kind": "create_relationship", "action_id": "a7", "relationship_type": {"kind": "existing", "key": "has_team"},
             "subject": new("match"), "object": new("nz")},
        ]
        if include_fiji:
            actions += [
                {"kind": "create_object", "action_id": "a6", "token": "fiji", "type": {"kind": "existing", "key": "team"},
                 "name": "Fiji"},
                {"kind": "create_relationship", "action_id": "a8", "relationship_type": {"kind": "existing", "key": "has_team"},
                 "subject": new("match"), "object": new("fiji")},
            ]
        if eden_park is None:
            actions.append(
                {"kind": "create_object", "action_id": "a9", "token": "eden", "type": {"kind": "existing", "key": "venue"},
                 "name": "Eden Park", "attributes": [{"key": "capacity", "number_value": 50000}],
                 "provenance": evidence("Eden Park | Auckland") + evidence("Eden Park capacity: 50000")}
            )
            venue_ref = new("eden")
        else:
            extra, venue_ref = eden_park
            actions += extra
        actions.append(
            {"kind": "create_relationship", "action_id": "a10", "relationship_type": {"kind": "existing", "key": "played_at"},
             "subject": new("match"), "object": venue_ref}
        )
        if include_forsyth_barr:
            actions.append(
                {"kind": "create_object", "action_id": "a11", "token": "fb", "type": {"kind": "existing", "key": "venue"},
                 "name": "Forsyth Barr Stadium"}
            )
        return actions

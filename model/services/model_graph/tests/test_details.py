from django.test import SimpleTestCase

from model.services.model_graph.details import object_details, relationship_details
from model.services.model_graph.facets import build_facets
from model.services.model_graph.projection import project
from model.services.model_graph.query import ExplorerQuery

from .builders import ALICE, APP, BILLING, LONER, MEMBER_OF, OPS, TEAM, USES, WEB, sample_dataset, uid


def projection_for(dataset, **params):
    query, _ = ExplorerQuery.from_params(params, dataset)
    return project(dataset, query)


class ObjectDetailsTests(SimpleTestCase):

    def setUp(self):
        self.dataset = sample_dataset()

    def test_core_fields(self):
        details = object_details(self.dataset, uid(WEB))

        self.assertEqual(details["kind"], "object")
        self.assertEqual(details["name"], "Web Portal")
        self.assertEqual(details["type"]["name"], "Application")
        self.assertIsNone(details["inView"])  # no projection supplied

    def test_attributes_follow_definition_order_and_include_empty_ones(self):
        details = object_details(self.dataset, uid(LONER))  # only status populated

        keys = [a["key"] for a in details["attributes"]]
        self.assertEqual(keys, ["status", "owner", "users", "launched", "critical"])
        by_key = {a["key"]: a for a in details["attributes"]}
        self.assertEqual(by_key["status"]["display"], "Live")
        self.assertIsNone(by_key["owner"]["display"])  # missing optional attribute

    def test_boolean_display(self):
        by_key = {a["key"]: a for a in object_details(self.dataset, uid(WEB))["attributes"]}
        billing = {a["key"]: a for a in object_details(self.dataset, uid(BILLING))["attributes"]}

        self.assertEqual(by_key["critical"]["display"], "Yes")
        self.assertEqual(billing["critical"]["display"], "No")

    def test_url_attribute_keeps_its_datatype_and_stays_distinct_from_text(self):
        from model.services.model_graph.dataset import EffectiveDataset

        from .builders import obj, object_type, rel, relationship_type, spec

        link = "https://example.com/docs"
        dataset = EffectiveDataset(
            object_types=[object_type(1, "Doc", [spec("website", "url"), spec("notes", "text")])],
            relationship_types=[relationship_type(2, "Cites", attributes=[spec("source", "url")])],
            objects=[
                obj(10, 1, "A", {"website": link, "notes": link}),
                obj(11, 1, "B"),
            ],
            relationships=[rel(20, 2, 10, 11, {"source": link})],
        )

        by_key = {a["key"]: a for a in object_details(dataset, uid(10))["attributes"]}
        self.assertEqual((by_key["website"]["dataType"], by_key["website"]["value"], by_key["website"]["display"]), ("url", link, link))
        self.assertEqual(by_key["notes"]["dataType"], "text")

        (source,) = relationship_details(dataset, uid(20))["attributes"]
        self.assertEqual((source["dataType"], source["value"]), ("url", link))

        (inline,) = object_details(dataset, uid(10))["relationships"][0]["items"][0]["attributes"]
        self.assertEqual(inline["dataType"], "url")

    def test_relationships_are_grouped_by_type_with_direction(self):
        details = object_details(self.dataset, uid(OPS))

        groups = {g["type"]["name"]: g["items"] for g in details["relationships"]}
        self.assertEqual(set(groups), {"Member of", "Uses"})
        self.assertTrue(all(i["direction"] == "incoming" for i in groups["Member of"]))
        self.assertTrue(all(i["direction"] == "outgoing" for i in groups["Uses"]))
        self.assertEqual([i["counterpart"]["name"] for i in groups["Uses"]], ["Billing", "Web Portal"])
        self.assertEqual(details["connectionCount"], 4)

    def test_counterparts_carry_enough_to_navigate(self):
        item = object_details(self.dataset, uid(ALICE))["relationships"][0]["items"][0]

        self.assertEqual(item["counterpart"]["id"], uid(OPS))
        self.assertEqual(item["counterpart"]["typeName"], "Team")
        self.assertEqual(item["relationshipId"], uid(1001))

    def test_relationship_attributes_are_included_when_populated(self):
        item = object_details(self.dataset, uid(ALICE))["relationships"][0]["items"][0]

        self.assertEqual([(a["label"], a["display"]) for a in item["attributes"]], [("Since", "2022-01-01")])

    def test_object_with_no_relationships(self):
        details = object_details(self.dataset, uid(LONER))

        self.assertEqual(details["relationships"], [])
        self.assertEqual(details["connectionCount"], 0)
        self.assertEqual(details["hiddenConnectionIds"], [])

    def test_unknown_id_returns_none(self):
        self.assertIsNone(object_details(self.dataset, uid(999999)))
        self.assertIsNone(object_details(self.dataset, "garbage"))

    def test_hidden_connections_are_reported_when_filters_hide_counterparts(self):
        projection = projection_for(self.dataset, hide_objects=[uid(APP)])

        details = object_details(self.dataset, uid(OPS), projection)

        self.assertEqual(sorted(details["hiddenConnectionIds"]), sorted([uid(WEB), uid(BILLING)]))
        uses = next(g for g in details["relationships"] if g["type"]["name"] == "Uses")
        self.assertTrue(all(i["counterpart"]["inView"] is False for i in uses["items"]))
        self.assertTrue(all(i["inView"] is False for i in uses["items"]))

    def test_nothing_hidden_when_everything_is_in_view(self):
        details = object_details(self.dataset, uid(OPS), projection_for(self.dataset))

        self.assertEqual(details["hiddenConnectionIds"], [])
        self.assertIs(details["inView"], True)

    def test_hidden_relationship_type_is_not_a_hidden_connection(self):
        # Both endpoints stay visible; only the edge is hidden.
        projection = projection_for(self.dataset, hide_relationships=[uid(USES)])
        details = object_details(self.dataset, uid(OPS), projection)

        self.assertEqual(details["hiddenConnectionIds"], [])
        uses = next(g for g in details["relationships"] if g["type"]["name"] == "Uses")
        self.assertTrue(all(i["inView"] is False and i["counterpart"]["inView"] is True for i in uses["items"]))

    def test_selected_object_hidden_by_filters_is_flagged(self):
        details = object_details(self.dataset, uid(OPS), projection_for(self.dataset, hide_objects=[uid(TEAM)]))

        self.assertIs(details["inView"], False)


class RelationshipDetailsTests(SimpleTestCase):

    def setUp(self):
        self.dataset = sample_dataset()

    def test_endpoints_type_and_direction(self):
        details = relationship_details(self.dataset, uid(1003))  # Ops uses Web

        self.assertEqual(details["kind"], "relationship")
        self.assertEqual(details["type"]["name"], "Uses")
        self.assertEqual(details["source"]["name"], "Ops")
        self.assertEqual(details["target"]["name"], "Web Portal")

    def test_attributes(self):
        details = relationship_details(self.dataset, uid(1001))

        self.assertEqual([(a["key"], a["display"]) for a in details["attributes"]], [("since", "2022-01-01")])

    def test_cardinality_context(self):
        details = relationship_details(self.dataset, uid(1003))

        self.assertEqual(
            details["cardinality"],
            {"subject": {"minimum": 1, "maximum": None}, "object": {"minimum": 0, "maximum": 1}},
        )

    def test_unknown_id_returns_none(self):
        self.assertIsNone(relationship_details(self.dataset, uid(999999)))

    def test_in_view_reflects_the_projection(self):
        hidden = projection_for(self.dataset, hide_relationships=[uid(USES)])
        shown = projection_for(self.dataset)

        self.assertIs(relationship_details(self.dataset, uid(1003), hidden)["inView"], False)
        self.assertIs(relationship_details(self.dataset, uid(1003), shown)["inView"], True)
        self.assertIs(relationship_details(self.dataset, uid(1003), shown)["source"]["inView"], True)


class FacetTests(SimpleTestCase):

    def setUp(self):
        self.facets = build_facets(sample_dataset())

    def test_object_types_with_counts_in_dataset_order(self):
        self.assertEqual(
            [(t["name"], t["count"]) for t in self.facets["objectTypes"]],
            [("Person", 3), ("Team", 1), ("Application", 3)],
        )

    def test_relationship_types_with_counts(self):
        self.assertEqual(
            [(t["name"], t["count"]) for t in self.facets["relationshipTypes"]], [("Member of", 2), ("Uses", 2)]
        )

    def test_choice_attribute_values_are_counted_including_zero(self):
        application = next(t for t in self.facets["objectTypes"] if t["name"] == "Application")
        status = next(a for a in application["attributes"] if a["key"] == "status")

        self.assertEqual(status["op"], "in")
        self.assertEqual(status["values"], [{"value": "Live", "count": 2}, {"value": "Retired", "count": 1}])

    def test_boolean_attribute_offers_yes_and_no(self):
        application = next(t for t in self.facets["objectTypes"] if t["name"] == "Application")
        critical = next(a for a in application["attributes"] if a["key"] == "critical")

        self.assertEqual([(v["value"], v["count"]) for v in critical["values"]], [("true", 1), ("false", 1)])

    def test_free_form_attributes_carry_their_operator_only(self):
        application = next(t for t in self.facets["objectTypes"] if t["name"] == "Application")
        ops = {a["key"]: a["op"] for a in application["attributes"]}

        self.assertEqual(ops, {"status": "in", "owner": "contains", "users": "range", "launched": "range", "critical": "in"})

    def test_swatches_are_absent_without_an_appearance_resolver(self):
        self.assertTrue(all(t["swatch"] is None for t in self.facets["objectTypes"]))

    def test_swatches_come_from_the_resolved_appearance(self):
        from model.services.appearance import AppearanceResolver
        from model.services.appearance import schema

        document = schema.sanitise_document(
            {"object_types": {uid(APP): {"shape": "star", "background": "#112233"}}}
        )

        facets = build_facets(sample_dataset(), AppearanceResolver(document))

        application = next(t for t in facets["objectTypes"] if t["name"] == "Application")
        person = next(t for t in facets["objectTypes"] if t["name"] == "Person")
        self.assertEqual((application["swatch"]["shape"], application["swatch"]["background"]), ("star", "#112233"))
        self.assertEqual(person["swatch"]["shape"], "box")
        self.assertEqual(facets["relationshipTypes"][0]["swatch"], {"colour": "#495057", "lineStyle": "solid"})

    def object_swatch(self, type_layer, name="Application"):
        from model.services.appearance import AppearanceResolver, schema

        document = schema.sanitise_document({"object_types": {uid(APP): type_layer}})
        facets = build_facets(sample_dataset(), AppearanceResolver(document))
        return next(t for t in facets["objectTypes"] if t["name"] == name)["swatch"]

    def test_swatch_carries_the_configured_shape_and_no_icon_by_default(self):
        swatch = self.object_swatch({"shape": "hexagon", "background": "#112233", "border": "#445566"})

        self.assertEqual(
            swatch,
            {"background": "#112233", "border": "#445566", "shape": "hexagon", "icon": None, "image": None},
        )

    def test_every_curated_shape_reaches_the_swatch(self):
        from model.services.appearance.schema import SHAPES

        for shape, _label in SHAPES:
            self.assertEqual(self.object_swatch({"shape": shape})["shape"], shape)

    def test_swatch_icon_image_is_exactly_what_the_graph_node_uses(self):
        from model.services.appearance import AppearanceResolver, schema
        from model.services.appearance.viewer_adapter import node_style

        document = schema.sanitise_document({"object_types": {uid(APP): {"icon": "database", "border": "#AA0000"}}})
        resolver = AppearanceResolver(document)

        swatch = next(
            t for t in build_facets(sample_dataset(), resolver)["objectTypes"] if t["name"] == "Application"
        )["swatch"]

        node = node_style(resolver.object_type(uid(APP)))
        self.assertEqual(swatch["icon"], "database")
        self.assertEqual(swatch["image"], node.image)
        self.assertIn("%23AA0000", swatch["image"])  # glyph is drawn in the border colour

    def test_types_without_an_icon_have_no_image_even_when_others_do(self):
        self.assertIsNone(self.object_swatch({"icon": "person"}, name="Person")["image"])
        self.assertIsNotNone(self.object_swatch({"icon": "person"})["image"])

    def test_relationship_swatch_is_unchanged(self):
        from model.services.appearance import AppearanceResolver, schema

        document = schema.sanitise_document({"relationship_types": {uid(USES): {"colour": "#c92a2a", "line_style": "dotted"}}})

        facets = build_facets(sample_dataset(), AppearanceResolver(document))

        uses = next(t for t in facets["relationshipTypes"] if t["name"] == "Uses")
        self.assertEqual(uses["swatch"], {"colour": "#C92A2A", "lineStyle": "dotted"})
        member_of = next(t for t in facets["relationshipTypes"] if t["name"] == "Member of")
        self.assertEqual(member_of["swatch"], {"colour": "#495057", "lineStyle": "solid"})

    def test_facets_ignore_filters(self):
        # Facets are built from the dataset alone, so a hidden type keeps its entry.
        self.assertEqual(len(self.facets["objectTypes"]), 3)

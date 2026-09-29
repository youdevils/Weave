"""New Zealand Farm Operations model template.

A complete, populated showcase model for a fictional Waikato dairy farm.
The model is deliberately operational rather than project-centric: it connects
land, pasture, livestock, feed, farm infrastructure, equipment, people,
seasonal activities, observations, animal health, environmental management,
production and operational risks into a single model of farm operations.

The model is intentionally fictional. It uses recognisable New Zealand dairy
operating concepts without attempting to represent any real farm, supplier,
processor or current regulatory threshold.

The template is declarative. Template instantiation services are responsible
for turning the definition into database records.

Sample object keys are template-local references used to create the sample
relationships. They are not persisted as Object fields.
"""

from __future__ import annotations


def _attr(key, name, data_type, description, sort_order, *, choices=None):
    config = {"choices": choices} if choices is not None else {}
    return {
        "key": key,
        "name": name,
        "data_type": data_type,
        "description": description,
        "required": False,
        "nullable": True,
        "default_value": None,
        "sort_order": sort_order,
        "config": config,
    }


def _otype(key, name, description, sort_order, attributes=()):
    return {
        "key": key,
        "name": name,
        "description": description,
        "sort_order": sort_order,
        "attributes": list(attributes),
    }


def _rule(subject_type, object_type, subject_minimum, subject_maximum,
          object_minimum, object_maximum):
    """Define cardinality in natural subject/object terms.

    The model validator stores the cardinalities from the opposite endpoint
    perspective: subject_* describe how many subjects an object may have,
    while object_* describe how many objects a subject may have.
    """
    return {
        "subject_type": subject_type,
        "object_type": object_type,
        "subject_minimum": object_minimum,
        "subject_maximum": object_maximum,
        "object_minimum": subject_minimum,
        "object_maximum": subject_maximum,
    }


def _rtype(key, name, description, sort_order, rules):
    return {
        "key": key,
        "name": name,
        "description": description,
        "sort_order": sort_order,
        "rules": rules,
        "attributes": [],
    }


def _obj(key, type_, name, description, attributes=None):
    return {
        "key": key,
        "type": type_,
        "name": name,
        "description": description,
        "attributes": attributes or {},
    }


def _rel(type_, subject, object_):
    return {"type": type_, "subject": subject, "object": object_}


STATUS = ["Planned", "In progress", "Established", "At risk", "Complete"]
CRITICALITY = ["Low", "Medium", "High", "Critical"]
RISK_STATUS = ["Open", "Monitored", "Mitigated", "Closed"]


NEW_ZEALAND_FARM_OPERATIONS_TEMPLATE = {
    "key": "new_zealand_farm_operations",
    "name": "Kauri Ridge Dairy — New Zealand Farm Operations",
    "description": (
        "A fictional Waikato dairy farm modelled as an interconnected operating system. "
        "The model connects land, pasture, livestock, feed, farm infrastructure, equipment, "
        "people, seasonal activities, animal health, environmental management, production and "
        "operational risk to show how the farm works as a whole."
    ),

    "object_types": [
        _otype(
            "farm", "Farm",
            "A defined dairy farming operation responsible for managing land, livestock, resources, "
            "people and production as a working farm business.", 10,
            [
                _attr("region", "Region", "text", "The New Zealand region in which the farm operates.", 10),
                _attr("farming_system", "Farming system", "choice", "The broad production system used by the farm.", 20,
                      choices=["Pasture-based seasonal dairy"]),
                _attr("calving_pattern", "Calving pattern", "choice", "The seasonal calving pattern used by the farm.", 30,
                      choices=["Spring calving"]),
                _attr("herd_scale", "Herd scale", "text", "Approximate milking herd size used to describe the farm scale.", 40),
                _attr("purpose", "Purpose", "text", "The operating purpose of the farm as a working business.", 50),
            ],
        ),
        _otype(
            "paddock", "Paddock",
            "A managed area of farm land used for grazing, pasture management or other farm activity.", 20,
            [
                _attr("area", "Area", "text", "Approximate paddock area.", 10),
                _attr("soil_type", "Soil type", "choice", "The dominant soil profile used for operational planning.", 20,
                      choices=["Allophanic", "Mellow yellow-brown loam", "Peaty loam"]),
                _attr("use_status", "Use status", "choice", "The current operational use of the paddock.", 30,
                      choices=["Grazing", "Recovery", "Silage", "Maintenance"]),
                _attr("drainage", "Drainage", "choice", "The broad drainage condition relevant to farm operations.", 40,
                      choices=["Well drained", "Moderate", "Wet prone"]),
            ],
        ),
        _otype(
            "waterway", "Waterway",
            "A natural or managed water feature on or adjacent to the farm that is relevant to water management and environmental care.", 30,
            [
                _attr("waterway_type", "Waterway type", "choice", "The broad type of water feature.", 10,
                      choices=["Stream", "Drain", "Wetland"]),
                _attr("sensitivity", "Sensitivity", "choice", "The operational sensitivity of the waterway to farm activity.", 20,
                      choices=["Low", "Moderate", "High"]),
                _attr("status", "Status", "choice", "The current condition used for farm management attention.", 30,
                      choices=["Healthy", "Monitored", "Needs attention"]),
            ],
        ),
        _otype(
            "pasture", "Pasture",
            "A pasture resource supporting grazing and feed production within a farm area.", 40,
            [
                _attr("pasture_type", "Pasture type", "choice", "The dominant pasture composition or use.", 10,
                      choices=["Perennial ryegrass-clover", "High-performing mixed pasture", "Summer crop", "Silage pasture"]),
                _attr("cover_status", "Cover status", "choice", "The current pasture cover position.", 20,
                      choices=["Below target", "On target", "Above target"]),
                _attr("quality", "Quality", "choice", "A broad operating assessment of pasture quality.", 30,
                      choices=["Good", "Acceptable", "Poor"]),
                _attr("purpose", "Purpose", "text", "The role the pasture plays in the farm feed system.", 40),
            ],
        ),
        _otype(
            "herd", "Herd",
            "A managed livestock population treated as a coherent operating unit within the farm.", 50,
            [
                _attr("herd_type", "Herd type", "choice", "The broad role of the herd.", 10,
                      choices=["Milking herd", "Replacement herd"]),
                _attr("size", "Size", "text", "Approximate population size represented by the herd object.", 20),
                _attr("production_stage", "Production stage", "choice", "The current stage of the herd in the seasonal cycle.", 30,
                      choices=["Pre-calving", "Calving", "Peak lactation", "Mid lactation", "Replacement rearing", "Dry-off preparation"]),
                _attr("condition", "Condition", 'text', "A broad operating assessment of herd condition.", 40),
            ],
        ),
        _otype(
            "animal_group", "Animal Group",
            "A meaningful subgroup of livestock managed together for a specific stage, treatment or purpose.", 60,
            [
                _attr("group_type", "Group type", "choice", "The role of the animal group.", 10,
                      choices=["First-calvers", "Spring-calving cows", "Rising two-year-olds", "Calves"]),
                _attr("size", "Size", "text", "Approximate group size.", 20),
                _attr("management_focus", "Management focus", "text", "The specific management focus for this group.", 30),
            ],
        ),
        _otype(
            "feed_resource", "Feed Resource",
            "A feed source managed to help meet livestock nutritional demand across the seasonal production cycle.", 70,
            [
                _attr("feed_type", "Feed type", "choice", "The broad type of feed resource.", 10,
                      choices=["Pasture", "Silage", "PKE", "Maize silage"]),
                _attr("availability", "Availability", "choice", "The current availability of the feed resource.", 20,
                      choices=["Abundant", "Adequate", "Tight", "Unavailable"]),
                _attr("purpose", "Purpose", 'text', "How the feed resource is used operationally.", 30),
            ],
        ),
        _otype(
            "farm_facility", "Farm Facility",
            "A fixed farm location or structure required to carry out livestock, production or support activities.", 80,
            [
                _attr("facility_type", "Facility type", "choice", "The broad kind of farm facility.", 10,
                      choices=["Farm dairy", "Stock yards", "Implement shed", "Calf rearing area", "Feed pad"]),
                _attr("condition", "Condition", 'choice', "The current physical or operating condition of the facility.", 20,
                      choices=["Good", "Serviceable", "Needs work"]),
                _attr("purpose", "Purpose", 'text', "The role of the facility in farm operations.", 30),
            ],
        ),
        _otype(
            "farm_equipment", "Farm Equipment",
            "A mobile or fixed item of equipment used to perform, support or maintain farm operations.", 90,
            [
                _attr("equipment_type", "Equipment type", "choice", "The broad equipment category.", 10,
                      choices=["Tractor", "Milking equipment", "Feed wagon", "Water pump", "Effluent equipment", "Utility vehicle"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current operating lifecycle state.", 20,
                      choices=["Current", "Needs maintenance", "Replacement planned"]),
                _attr("criticality", "Criticality", 'choice', "The importance of the equipment to continued farm operations.", 30,
                      choices=CRITICALITY),
                _attr("purpose", "Purpose", 'text', "The primary operating role of the equipment.", 40),
            ],
        ),
        _otype(
            "water_system", "Water System",
            "The infrastructure used to source, store, distribute or monitor water required for farm operations.", 100,
            [
                _attr("source_type", "Source type", "choice", "The main water source.", 10,
                      choices=["Bore", "Rainwater", "Surface water", "Mixed"]),
                _attr("status", "Status", 'choice', "The current operating condition of the water system.", 20,
                      choices=["Normal", "Restricted", "Needs attention"]),
                _attr("purpose", "Purpose", 'text', "The farm activities and livestock needs supported by the water system.", 30),
            ],
        ),
        _otype(
            "effluent_system", "Effluent System",
            "The infrastructure and storage arrangement used to collect, store and apply dairy effluent.", 110,
            [
                _attr("system_type", "System type", "choice", "The broad effluent system arrangement.", 10,
                      choices=["Pond and irrigation", "Storage and low-rate application"]),
                _attr("status", "Status", 'choice', "The current operating state of the effluent system.", 20,
                      choices=["Normal", "Storage constrained", "Needs maintenance"]),
                _attr("capacity", "Capacity", 'text', "The storage capacity available to support operational planning.", 30),
            ],
        ),
        _otype(
            "farm_activity", "Farm Activity",
            "A defined operational activity performed as part of running the farm and producing milk while maintaining land, livestock and infrastructure.", 120,
            [
                _attr("activity_type", "Activity type", "choice", "The broad class of farm activity.", 10,
                      choices=["Grazing", "Milking", "Feeding", "Animal health", "Breeding", "Pasture management", "Fertiliser", "Effluent", "Maintenance", "Monitoring", "Water management"]),
                _attr("status", "Status", 'choice', "The current operating state of the activity.", 20,
                      choices=STATUS),
                _attr("timing", "Timing", 'text', "The seasonal timing or operating window for the activity.", 30),
                _attr("purpose", "Purpose", 'text', "The operational purpose of the activity.", 40),
                _attr("risk_level", "Risk level", 'choice', "The current operational risk associated with carrying out the activity.", 50,
                      choices=CRITICALITY),
            ],
        ),
        _otype(
            "farm_input", "Farm Input",
            "A consumable or purchased input used to support livestock, pasture, infrastructure or farm operations.", 130,
            [
                _attr("input_type", "Input type", "choice", "The broad kind of farm input.", 10,
                      choices=["Fertiliser", "Fuel", "Animal health", "Supplementary feed", "Seed"]),
                _attr("availability", "Availability", 'choice', "The current operational availability of the input.", 20,
                      choices=["Available", "Low", "On order"]),
                _attr("purpose", "Purpose", "text", "The operational role of the input.", 30),
            ],
        ),
        _otype(
            "person", "Person",
            "An individual with a defined responsibility in operating or supporting the farm.", 140,
            [
                _attr("role", "Role", 'text', "The primary role played by the person.", 10),
                _attr("employment_type", "Employment type", 'choice', "The broad relationship to the farm.", 20,
                      choices=["Employee", "Owner", "Contractor", "Professional adviser"]),
                _attr("responsibility", "Responsibility", 'text', "The principal responsibility of the person in the model.", 30),
            ],
        ),
        _otype(
            "team", "Team",
            "A small group accountable for a coherent area of farm work or operational support.", 150,
            [
                _attr("team_type", "Team type", 'choice', "The broad operating role of the team.", 10,
                      choices=["Farm team", "Contract service team", "Advisory team"]),
                _attr("purpose", "Purpose", "text", "The team's primary operational purpose.", 20),
            ],
        ),
        _otype(
            "service_provider", "Service Provider",
            "An external organisation or specialist service supporting the farm operation.", 160,
            [
                _attr("service_type", "Service type", 'choice', "The broad type of service provided.", 10,
                      choices=["Milk processor", "Veterinary", "Farm supplies", "Engineering", "Rural support"]),
                _attr("relationship_status", "Relationship status", 'choice', "The current relationship to the farm.", 20,
                      choices=["Current", "Preferred", "Ad hoc"]),
                _attr("purpose", "Purpose", "text", "The role the service provider plays in farm operations.", 30),
            ],
        ),
        _otype(
            "weather_condition", "Weather Condition",
            "A material weather condition affecting the timing, safety or effectiveness of farm operations.", 170,
            [
                _attr("condition_type", "Condition type", 'choice', "The broad type of weather condition.", 10,
                      choices=["Wet period", "Dry period", "Heavy rain", "Frost", "Heat"]),
                _attr("severity", "Severity", 'choice', "The operational severity of the condition.", 20,
                      choices=["Low", "Moderate", "High"]),
                _attr("period", "Period", 'text', "The time period in which the condition is relevant.", 30),
            ],
        ),
        _otype(
            "observation", "Farm Observation",
            "A recorded observation or measurement used to understand farm conditions and support an operating decision.", 180,
            [
                _attr("observation_type", "Observation type", 'choice', "The broad category of observation.", 10,
                      choices=["Pasture cover", "Animal condition", "Water quality", "Soil condition", "Equipment condition", "Milk production", "Effluent storage"]),
                _attr("status", "Status", 'choice', "The operating interpretation of the observation.", 20,
                      choices=["Normal", "Watch", "Action required"]),
                _attr("finding", "Finding", 'text', "The recorded finding or interpretation.", 30),
            ],
        ),
        _otype(
            "animal_health_event", "Animal Health Event",
            "A defined animal health occurrence requiring monitoring, treatment, prevention or follow-up.", 190,
            [
                _attr("event_type", "Event type", 'choice', "The broad type of animal health event.", 10,
                      choices=["Lameness", "Mastitis", "Calf illness", "BVD monitoring", "Condition concern"]),
                _attr("status", "Status", 'choice', "The current status of the event.", 20,
                      choices=["Open", "Under treatment", "Monitoring", "Resolved"]),
                _attr("response", "Response", 'text', "The management response being used.", 30),
            ],
        ),
        _otype(
            "maintenance_event", "Maintenance Event",
            "A defined repair, service or inspection event required to keep farm infrastructure or equipment reliable.", 200,
            [
                _attr("maintenance_type", "Maintenance type", 'choice', "The broad type of maintenance event.", 10,
                      choices=["Planned service", "Repair", "Inspection", "Calibration"]),
                _attr("status", "Status", 'choice', "The current state of the maintenance event.", 20,
                      choices=["Planned", "Open", "In progress", "Complete"]),
                _attr("priority", "Priority", 'choice', "The operational priority of the maintenance work.", 30,
                      choices=CRITICALITY),
                _attr("response", "Response", 'text', "The planned or completed response.", 40),
            ],
        ),
        _otype(
            "environmental_plan", "Environmental Management Plan",
            "A farm-level operating plan describing how environmental risks and obligations are managed through normal farm activity.", 210,
            [
                _attr("plan_type", "Plan type", 'choice', "The main environmental focus of the plan.", 10,
                      choices=["Freshwater and waterways", "Effluent management", "Nutrient management"]),
                _attr("status", "Status", 'choice', "The current operating status of the plan.", 20,
                      choices=["Current", "Under review", "Action required"]),
                _attr("focus", "Focus", 'text', "The main operational focus of the plan.", 30),
            ],
        ),
        _otype(
            "production_output", "Production Output",
            "A measurable output of farm operations that represents production, collection or another meaningful operating result.", 220,
            [
                _attr("output_type", "Output type", 'choice', "The broad kind of production output.", 10,
                      choices=["Milk", "Milksolids", "Replacement stock", "Pasture conserved"]),
                _attr("status", "Status", 'choice', "The operating status of the output.", 20,
                      choices=["On target", "Below target", "Above target", "At risk"]),
                _attr("period", "Period", 'text', "The production period represented by the output.", 30),
                _attr("quality", "Quality", 'text', "The relevant quality assessment for the output.", 40),
            ],
        ),
        _otype(
            "operational_risk", "Operational Risk",
            "A condition or event that could disrupt farm operations, production, animal welfare, infrastructure or environmental performance.", 230,
            [
                _attr("category", "Category", 'choice', "The broad category of operational risk.", 10,
                      choices=["Production", "Animal health", "Weather", "Infrastructure", "Environmental", "Supply"]),
                _attr("status", "Status", 'choice', "The current management status of the risk.", 20,
                      choices=RISK_STATUS),
                _attr("severity", "Severity", 'choice', "The potential operational severity if the risk materialises.", 30,
                      choices=CRITICALITY),
                _attr("description", "Description", 'text', "The practical effect the risk could have on the farm.", 40),
            ],
        ),
        _otype(
            "business_outcome", "Business Outcome",
            "A meaningful result the farm seeks to achieve through effective day-to-day operation and management of the farm system.", 240,
            [
                _attr("outcome_type", "Outcome type", 'choice', "The broad type of farm outcome.", 10,
                      choices=["Production", "Animal welfare", "Environmental", "Business continuity", "Sustainability"]),
                _attr("status", "Status", 'choice', "The current position against the desired outcome.", 20,
                      choices=["On track", "Watch", "At risk"]),
                _attr("description", "Description", 'text', "The desired operating result.", 30),
            ],
        ),
        _otype(
            "information_record", "Information Record",
            "A meaningful record used to coordinate, evidence or understand farm operations.", 250,
            [
                _attr("record_type", "Record type", 'choice', "The broad type of information record.", 10,
                      choices=["Grazing plan", "Animal health record", "Milk report", "Maintenance record", "Environmental record", "Supplier record", "Farm measurement"]),
                _attr("sensitivity", "Sensitivity", 'choice', "The general sensitivity of the information.", 20,
                      choices=["Public", "Internal", "Confidential"]),
                _attr("purpose", "Purpose", "text", "The operational role of the record.", 30),
            ],
        ),
    ],

    "relationship_types": [
        _rtype("has_paddock", "Has paddock", "Indicates that a paddock forms part of a farm's managed land area.", 10, [
            _rule("farm", "paddock", 1, None, 1, 1),
        ]),
        _rtype("has_waterway", "Has waterway", "Indicates that a waterway forms part of or is managed as part of the farm environment.", 20, [
            _rule("farm", "waterway", 1, None, 1, 1),
        ]),
        _rtype("has_pasture", "Has pasture", "Indicates that a pasture resource is associated with a managed paddock.", 30, [
            _rule("paddock", "pasture", 1, 1, 1, 1),
        ]),
        _rtype("has_herd", "Has herd", "Indicates that a herd is managed as part of the farm operation.", 40, [
            _rule("farm", "herd", 1, None, 1, 1),
        ]),
        _rtype("has_group", "Has group", "Indicates that an animal group belongs to a managed herd.", 50, [
            _rule("herd", "animal_group", 1, None, 1, 1),
        ]),
        _rtype("has_feed_resource", "Has feed resource", "Indicates that a feed resource is part of the farm feed system.", 60, [
            _rule("farm", "feed_resource", 1, None, 1, 1),
        ]),
        _rtype("has_facility", "Has facility", "Indicates that a farm facility forms part of the farm's physical operating estate.", 70, [
            _rule("farm", "farm_facility", 1, None, 1, 1),
        ]),
        _rtype("has_equipment", "Has equipment", "Indicates that equipment is part of the farm's operating asset base.", 80, [
            _rule("farm", "farm_equipment", 1, None, 1, 1),
        ]),
        _rtype("has_water_system", "Has water system", "Indicates that a water system supports the farm's water needs.", 90, [
            _rule("farm", "water_system", 1, None, 1, 1),
        ]),
        _rtype("has_effluent_system", "Has effluent system", "Indicates that an effluent system forms part of the farm's environmental infrastructure.", 100, [
            _rule("farm", "effluent_system", 1, 1, 1, 1),
        ]),
        _rtype("has_activity", "Has activity", "Indicates that a farm activity forms part of the farm operating model.", 110, [
            _rule("farm", "farm_activity", 1, None, 1, 1),
        ]),
        _rtype("has_input", "Has input", "Indicates that an input is managed as part of the farm operation.", 120, [
            _rule("farm", "farm_input", 1, None, 1, 1),
        ]),
        _rtype("has_person", "Has person", "Indicates that a person is part of the farm's operating workforce or professional support network.", 130, [
            _rule("farm", "person", 1, None, 1, 1),
        ]),
        _rtype("has_team", "Has team", "Indicates that a team contributes to farm operations.", 140, [
            _rule("farm", "team", 1, None, 1, 1),
        ]),
        _rtype("uses_service_provider", "Uses service provider", "Indicates that a farm uses an external service provider in support of its operation.", 150, [
            _rule("farm", "service_provider", 0, None, 0, None),
        ]),
        _rtype("has_weather_condition", "Has weather condition", "Indicates that a material weather condition is relevant to the farm's current operating context.", 160, [
            _rule("farm", "weather_condition", 1, None, 1, 1),
        ]),
        _rtype("has_observation", "Has observation", "Indicates that a farm observation forms part of the farm's operating evidence.", 170, [
            _rule("farm", "observation", 1, None, 1, 1),
        ]),
        _rtype("has_animal_health_event", "Has animal health event", "Indicates that an animal health event is part of the farm's health management record.", 180, [
            _rule("farm", "animal_health_event", 1, None, 1, 1),
        ]),
        _rtype("has_maintenance_event", "Has maintenance event", "Indicates that a maintenance event is managed within the farm operation.", 190, [
            _rule("farm", "maintenance_event", 1, None, 1, 1),
        ]),
        _rtype("has_environmental_plan", "Has environmental plan", "Indicates that an environmental management plan governs part of farm operations.", 200, [
            _rule("farm", "environmental_plan", 1, 1, 1, 1),
        ]),
        _rtype("has_output", "Has output", "Indicates that a production output is part of the farm's operating results.", 210, [
            _rule("farm", "production_output", 1, None, 1, 1),
        ]),
        _rtype("has_risk", "Has risk", "Indicates that an operational risk is relevant to the farm.", 220, [
            _rule("farm", "operational_risk", 1, None, 1, 1),
        ]),
        _rtype("has_outcome", "Has outcome", "Indicates that a business outcome is a desired result for the farm.", 230, [
            _rule("farm", "business_outcome", 1, None, 1, 1),
        ]),
        _rtype("has_record", "Has record", "Indicates that an information record supports farm operations.", 240, [
            _rule("farm", "information_record", 1, None, 1, 1),
        ]),
        _rtype("managed_by", "Managed by", "Indicates that a farm activity or operational asset is managed by a responsible person or team.", 250, [
            _rule("farm_activity", "person", 1, 1, 0, None),
            _rule("farm_activity", "team", 0, 1, 0, None),
            _rule("farm_facility", "team", 0, 1, 0, None),
            _rule("farm_equipment", "team", 0, 1, 0, None),
            _rule("farm_input", "person", 0, 1, 0, None),
            _rule("environmental_plan", "person", 1, 1, 0, None),
        ]),
        _rtype("member_of", "Member of", "Indicates that a person belongs to or works within a farm team.", 260, [
            _rule("person", "team", 0, 1, 0, None),
        ]),
        _rtype("performed_by", "Performed by", "Indicates the person or team carrying out a farm activity.", 270, [
            _rule("farm_activity", "team", 0, 1, 0, None),
            _rule("farm_activity", "service_provider", 0, 1, 0, None),
        ]),
        _rtype("takes_place_at", "Takes place at", "Indicates the paddock or facility in which an activity occurs.", 280, [
            _rule("farm_activity", "paddock", 0, 1, 0, None),
            _rule("farm_activity", "farm_facility", 0, 1, 0, None),
        ]),
        _rtype("involves_herd", "Involves herd", "Indicates that an activity directly concerns a managed herd or animal group.", 290, [
            _rule("farm_activity", "herd", 0, 1, 0, None),
            _rule("farm_activity", "animal_group", 0, 1, 0, None),
        ]),
        _rtype("uses_equipment", "Uses equipment", "Indicates that an activity relies on equipment to be performed.", 300, [
            _rule("farm_activity", "farm_equipment", 0, None, 0, None),
        ]),
        _rtype("uses_input", "Uses input", "Indicates that an activity consumes or applies a farm input.", 310, [
            _rule("farm_activity", "farm_input", 0, None, 0, None),
            _rule("farm_activity", "feed_resource", 0, None, 0, None),
        ]),
        _rtype("affected_by", "Affected by", "Indicates that a farm activity is affected by a weather or operating condition.", 320, [
            _rule("farm_activity", "weather_condition", 0, None, 0, None),
            _rule("farm_activity", "observation", 0, None, 0, None),
        ]),
        _rtype("produces", "Produces", "Indicates that an activity contributes to a production output.", 330, [
            _rule("farm_activity", "production_output", 0, None, 0, None),
        ]),
        _rtype("creates_record", "Creates record", "Indicates that an activity creates or updates an information record.", 340, [
            _rule("farm_activity", "information_record", 0, None, 0, None),
            _rule("animal_health_event", "information_record", 0, None, 0, None),
            _rule("maintenance_event", "information_record", 0, None, 0, None),
        ]),
        _rtype("observes", "Observes", "Indicates that an observation describes a paddock, pasture, herd, equipment or environmental asset.", 350, [
            _rule("observation", "paddock", 0, None, 0, 1),
            _rule("observation", "pasture", 0, None, 0, 1),
            _rule("observation", "herd", 0, None, 0, 1),
            _rule("observation", "animal_group", 0, None, 0, 1),
            _rule("observation", "farm_equipment", 0, None, 0, 1),
            _rule("observation", "waterway", 0, None, 0, 1),
            _rule("observation", "effluent_system", 0, None, 0, 1),
        ]),
        _rtype("taken_by", "Taken by", "Indicates who recorded a farm observation.", 360, [
            _rule("observation", "person", 1, 1, 0, None),
        ]),
        _rtype("affects", "Affects", "Indicates that an animal health event concerns a herd or animal group.", 370, [
            _rule("animal_health_event", "herd", 0, None, 0, 1),
            _rule("animal_health_event", "animal_group", 0, None, 0, 1),
        ]),
        _rtype("treated_by", "Treated by", "Indicates that an animal health event is managed by a veterinary or specialist service provider.", 380, [
            _rule("animal_health_event", "service_provider", 0, 1, 0, None),
        ]),
        _rtype("applies_to", "Applies to", "Indicates that maintenance work applies to equipment or a facility.", 390, [
            _rule("maintenance_event", "farm_equipment", 0, None, 0, 1),
            _rule("maintenance_event", "farm_facility", 0, None, 0, 1),
        ]),
        _rtype("serviced_by", "Serviced by", "Indicates which service provider completes or supports maintenance work.", 400, [
            _rule("maintenance_event", "service_provider", 0, 1, 0, None),
        ]),
        _rtype("governs", "Governs", "Indicates that an environmental plan governs a farm area, activity or environmental system.", 410, [
            _rule("environmental_plan", "paddock", 0, None, 0, None),
            _rule("environmental_plan", "waterway", 0, None, 0, None),
            _rule("environmental_plan", "farm_activity", 0, None, 0, None),
            _rule("environmental_plan", "effluent_system", 0, 1, 0, None),
        ]),
        _rtype("mitigates", "Mitigates", "Indicates that a farm activity or management practice is used to reduce an operational risk.", 420, [
            _rule("farm_activity", "operational_risk", 0, None, 0, None),
        ]),
        _rtype("impacts", "Impacts", "Indicates that an operational risk could affect a farm activity, asset, production output or business outcome.", 430, [
            _rule("operational_risk", "farm_activity", 0, None, 0, None),
            _rule("operational_risk", "farm_equipment", 0, None, 0, None),
            _rule("operational_risk", "production_output", 0, None, 0, None),
            _rule("operational_risk", "business_outcome", 0, None, 0, None),
        ]),
        _rtype("supports", "Supports", "Indicates that a process, asset, resource or output contributes to a desired farm business outcome.", 440, [
            _rule("production_output", "business_outcome", 0, None, 0, None),
            _rule("farm_activity", "business_outcome", 0, None, 0, None),
        ]),
        _rtype("supplied_by", "Supplied by", "Indicates that a feed resource or farm input is supplied by an external provider.", 450, [
            _rule("feed_resource", "service_provider", 0, 1, 0, None),
            _rule("farm_input", "service_provider", 0, 1, 0, None),
        ]),
        _rtype("depends_on", "Depends on", "Indicates that one farm asset, activity or output relies on another operating dependency.", 460, [
            _rule("farm_activity", "farm_equipment", 0, None, 0, None),
            _rule("farm_activity", "water_system", 0, 1, 0, None),
            _rule("farm_activity", "effluent_system", 0, 1, 0, None),
            _rule("production_output", "farm_activity", 0, None, 0, None),
        ]),
        _rtype("associated_with", "Associated with", "Indicates that an information record provides evidence for a farm asset, activity, output or event.", 470, [
            _rule("information_record", "farm_activity", 0, None, 0, None),
            _rule("information_record", "production_output", 0, None, 0, None),
            _rule("information_record", "operational_risk", 0, None, 0, None),
            _rule("information_record", "animal_health_event", 0, None, 0, None),
            _rule("information_record", "maintenance_event", 0, None, 0, None),
        ]),
        _rtype("collected_by", "Collected by", "Indicates that a production output is collected or received by an external processor or service provider.", 480, [
            _rule("production_output", "service_provider", 0, 1, 0, None),
        ]),
    ],

    "objects": [
        # Farm
        _obj(
            "kauri_ridge_dairy", "farm", "Kauri Ridge Dairy",
            "A fictional 600-cow pasture-based dairy farm in the Waikato. The farm operates a seasonal spring-calving system, manages a mixed set of pastoral and supporting land areas, and supplies milk through an external processor.",
            {"region": "Waikato", "farming_system": "Pasture-based seasonal dairy", "calving_pattern": "Spring calving", "herd_scale": "Approximately 600 milking cows", "purpose": "Produce milk sustainably while maintaining a healthy herd, productive land base, reliable infrastructure and a viable farm business."},
        ),

        # Paddocks
        _obj("north_pasture", "paddock", "North Pasture", "A 32-hectare paddock used heavily during the spring pasture growth flush.", {"area": "32 ha", "soil_type": "Mellow yellow-brown loam", "use_status": "Grazing", "drainage": "Well drained"}),
        _obj("home_block", "paddock", "Home Block", "A 24-hectare paddock group close to the farm dairy used for flexible grazing and access during busy milking periods.", {"area": "24 ha", "soil_type": "Allophanic", "use_status": "Grazing", "drainage": "Well drained"}),
        _obj("east_flat", "paddock", "East Flat", "A 28-hectare lower-lying area with strong pasture potential but increased wet-weather traffic sensitivity.", {"area": "28 ha", "soil_type": "Peaty loam", "use_status": "Recovery", "drainage": "Wet prone"}),
        _obj("river_margin", "paddock", "River Margin", "A 16-hectare lower-intensity area adjoining a stream margin and managed with environmental sensitivity.", {"area": "16 ha", "soil_type": "Peaty loam", "use_status": "Grazing", "drainage": "Wet prone"}),
        _obj("silage_paddock", "paddock", "Longacre Silage Paddock", "A 14-hectare paddock held for silage production when seasonal pasture growth and farm feed planning require conserved feed.", {"area": "14 ha", "soil_type": "Allophanic", "use_status": "Silage", "drainage": "Moderate"}),

        # Waterways
        _obj("kahikatea_stream", "waterway", "Kahikatea Stream", "A small stream crossing the lower part of the farm and forming a sensitive environmental boundary.", {"waterway_type": "Stream", "sensitivity": "High", "status": "Healthy"}),
        _obj("north_drain", "waterway", "North Drain", "A managed drainage channel collecting runoff from the northern part of the property.", {"waterway_type": "Drain", "sensitivity": "Moderate", "status": "Monitored"}),

        # Pasture
        _obj("north_pasture_sward", "pasture", "North Pasture Sward", "A perennial ryegrass-clover sward carrying strong spring growth on the northern block.", {"pasture_type": "Perennial ryegrass-clover", "cover_status": "Above target", "quality": "Good", "purpose": "Primary spring grazing supply for the milking herd."}),
        _obj("home_block_sward", "pasture", "Home Block Sward", "A high-performing mixed pasture close to the farm dairy and suited to regular grazing rotations.", {"pasture_type": "High-performing mixed pasture", "cover_status": "On target", "quality": "Good", "purpose": "Provide reliable grazing near the farm dairy and support flexible herd movements."}),
        _obj("east_flat_sward", "pasture", "East Flat Sward", "A moisture-sensitive pasture area managed conservatively during wet conditions.", {"pasture_type": "Perennial ryegrass-clover", "cover_status": "On target", "quality": "Acceptable", "purpose": "Provide grazing while protecting the paddock from pugging and soil damage."}),
        _obj("river_margin_sward", "pasture", "River Margin Pasture", "Lower-intensity pasture adjoining the stream margin.", {"pasture_type": "Perennial ryegrass-clover", "cover_status": "On target", "quality": "Acceptable", "purpose": "Provide controlled grazing while maintaining the environmental margin."}),
        _obj("longacre_silage_sward", "pasture", "Longacre Silage Sward", "A strong pasture stand reserved for a planned silage cut.", {"pasture_type": "Silage pasture", "cover_status": "Above target", "quality": "Good", "purpose": "Build conserved feed reserves for periods when pasture supply is constrained."}),

        # Herds and animal groups
        _obj("milking_herd", "herd", "Milking Herd", "The main approximately 600-cow spring-calving herd producing milk through the seasonal production system.", {"herd_type": "Milking herd", "size": "600 cows", "production_stage": "Peak lactation", "condition": "Good, with close monitoring of first-calvers"}),
        _obj("replacement_herd", "herd", "Replacement Herd", "Young stock retained to maintain the future milking herd and support the farm's longer-term operating continuity.", {"herd_type": "Replacement herd", "size": "145 animals", "production_stage": "Replacement rearing", "condition": "Good"}),
        _obj("spring_calvers", "animal_group", "Spring-Calving Cows", "The main group of cows calving into the current spring production season.", {"group_type": "Spring-calving cows", "size": "480 cows", "management_focus": "Transition from calving through peak milk production while maintaining body condition."}),
        _obj("first_calvers", "animal_group", "First-Calvers", "Young cows entering their first full lactation and requiring close condition and feed monitoring.", {"group_type": "First-calvers", "size": "120 cows", "management_focus": "Protect condition and maintain steady production through early lactation."}),
        _obj("rising_two_year_olds", "animal_group", "Rising Two-Year-Olds", "Replacement heifers approaching entry to the milking herd.", {"group_type": "Rising two-year-olds", "size": "75 animals", "management_focus": "Maintain target liveweight and readiness for joining."}),

        # Feed resources
        _obj("spring_pasture_feed", "feed_resource", "Spring Pasture Feed", "The principal spring feed source produced directly from the farm pasture platform.", {"feed_type": "Pasture", "availability": "Abundant", "purpose": "Provide the base diet for the milking herd during the spring growth flush."}),
        _obj("grass_silage", "feed_resource", "Grass Silage", "Conserved pasture harvested from the Longacre paddock for use when daily pasture supply is tight.", {"feed_type": "Silage", "availability": "Adequate", "purpose": "Buffer short-term pasture deficits without materially changing the farm's pasture-based system."}),
        _obj("maize_silage", "feed_resource", "Maize Silage", "Purchased supplementary feed used selectively for higher-demand groups and periods of tight pasture supply.", {"feed_type": "Maize silage", "availability": "Adequate", "purpose": "Provide energy-dense supplementary feed when pasture allocation is constrained."}),

        # Facilities
        _obj("farm_dairy", "farm_facility", "Kauri Ridge Farm Dairy", "The central milking facility where the herd is milked twice daily during the main season.", {"facility_type": "Farm dairy", "condition": "Good", "purpose": "Receive the herd, operate milking equipment and transfer milk into the farm's collection system."}),
        _obj("stock_yards", "farm_facility", "Main Stock Yards", "Handling yards used for animal drafting, health work, weighing and other livestock management activities.", {"facility_type": "Stock yards", "condition": "Serviceable", "purpose": "Provide a controlled environment for livestock handling and animal health work."}),
        _obj("implement_shed", "farm_facility", "Implement Shed", "Covered storage and maintenance area for tractors, implements and farm equipment.", {"facility_type": "Implement shed", "condition": "Good", "purpose": "Protect equipment and provide a controlled location for maintenance work."}),

        # Equipment
        _obj("main_tractor", "farm_equipment", "Main Farm Tractor", "The primary tractor used for feed movement, pasture work, fertiliser and general farm tasks.", {"equipment_type": "Tractor", "lifecycle_status": "Current", "criticality": "High", "purpose": "Provide mobile power for core farm support activities."}),
        _obj("milking_system", "farm_equipment", "Rotary Milking System", "The rotary milking plant supporting twice-daily milking and milk transfer at the farm dairy.", {"equipment_type": "Milking equipment", "lifecycle_status": "Current", "criticality": "Critical", "purpose": "Milk the herd consistently and transfer milk into the farm collection system."}),
        _obj("feed_wagon", "farm_equipment", "Feed Wagon", "The wagon used to deliver supplementary feed to livestock when pasture allocation requires support.", {"equipment_type": "Feed wagon", "lifecycle_status": "Current", "criticality": "Medium", "purpose": "Distribute supplementary feed accurately to the required animal groups."}),
        _obj("water_pump", "farm_equipment", "Main Water Pump", "The primary pump supporting stock water distribution across the farm.", {"equipment_type": "Water pump", "lifecycle_status": "Needs maintenance", "criticality": "High", "purpose": "Maintain reliable water delivery to livestock and operational facilities."}),
        _obj("utility_vehicle", "farm_equipment", "Farm Utility Vehicle", "A utility vehicle used for daily stock checks, paddock inspection and moving between operating areas.", {"equipment_type": "Utility vehicle", "lifecycle_status": "Current", "criticality": "Medium", "purpose": "Provide rapid access between the farm dairy, paddocks and livestock areas."}),
        _obj("effluent_irrigator", "farm_equipment", "Effluent Irrigator", "Low-rate effluent application equipment used to return nutrients to suitable land under appropriate conditions.", {"equipment_type": "Effluent equipment", "lifecycle_status": "Current", "criticality": "High", "purpose": "Apply stored effluent within the farm's environmental management controls."}),

        # Water / effluent systems
        _obj("bore_water_system", "water_system", "North Bore Water System", "The main bore, storage and distribution system supporting stock water and farm dairy supply.", {"source_type": "Bore", "status": "Normal", "purpose": "Provide dependable water for livestock, milking and farm operations."}),
        _obj("effluent_storage_system", "effluent_system", "Dairy Effluent Storage and Irrigation System", "The farm's storage and low-rate application arrangement for dairy effluent.", {"system_type": "Storage and low-rate application", "status": "Normal", "capacity": "Approximately 90 days under the current operating assumptions"}),

        # Activities
        _obj("morning_milking", "farm_activity", "Morning Milking", "Twice-daily milking performed at the farm dairy before the main daytime grazing rotation.", {"activity_type": "Milking", "status": "Established", "timing": "Daily, early morning", "purpose": "Collect saleable milk while maintaining a consistent milking routine.", "risk_level": "High"}),
        _obj("afternoon_milking", "farm_activity", "Afternoon Milking", "The second daily milking session completing the farm's main milking cycle.", {"activity_type": "Milking", "status": "Established", "timing": "Daily, afternoon", "purpose": "Maintain the seasonal milking routine and complete daily milk production.", "risk_level": "High"}),
        _obj("morning_grazing", "farm_activity", "Morning Grazing Rotation", "Move the milking herd onto the next allocated paddock after morning milking.", {"activity_type": "Grazing", "status": "Established", "timing": "Daily, after morning milking", "purpose": "Allocate pasture to the herd while maintaining target residuals and rotation length.", "risk_level": "Medium"}),
        _obj("supplementary_feeding", "farm_activity", "Supplementary Feeding", "Provide conserved or purchased feed when pasture allocation is insufficient for the required herd demand.", {"activity_type": "Feeding", "status": "In progress", "timing": "As required during tight pasture periods", "purpose": "Protect production and animal condition when pasture supply is temporarily constrained.", "risk_level": "Medium"}),
        _obj("spring_calving", "farm_activity", "Spring Calving Management", "Monitor calving cows, provide support where required and move cows into the milking herd after calving.", {"activity_type": "Breeding", "status": "In progress", "timing": "Spring calving period", "purpose": "Bring cows through calving safely and into the seasonal milk production cycle.", "risk_level": "High"}),
        _obj("animal_health_round", "farm_activity", "Animal Health Round", "Routine livestock observation and treatment activity covering body condition, lameness, mastitis indicators and other health concerns.", {"activity_type": "Animal health", "status": "Established", "timing": "Daily observation with planned weekly review", "purpose": "Detect and respond to animal health issues before they materially affect welfare or production.", "risk_level": "High"}),
        _obj("pasture_walk", "farm_activity", "Weekly Pasture Walk", "Walk farm paddocks to assess pasture cover, rotation position and likely feed supply for the coming period.", {"activity_type": "Monitoring", "status": "Established", "timing": "Weekly", "purpose": "Maintain an evidence-based view of pasture supply and adjust grazing allocation.", "risk_level": "Medium"}),
        _obj("silage_harvest", "farm_activity", "Grass Silage Harvest", "Harvest surplus pasture from the designated silage paddock to maintain a feed reserve for periods of tight pasture supply.", {"activity_type": "Pasture management", "status": "Planned", "timing": "Spring, when pasture growth exceeds grazing demand", "purpose": "Convert surplus spring pasture into a conserved feed reserve.", "risk_level": "Medium"}),
        _obj("fertiliser_application", "farm_activity", "Targeted Fertiliser Application", "Apply planned nutrients to selected paddocks in line with pasture demand, soil conditions and the farm nutrient management approach.", {"activity_type": "Fertiliser", "status": "In progress", "timing": "Seasonal and condition dependent", "purpose": "Maintain pasture productivity without unnecessary nutrient loss.", "risk_level": "High"}),
        _obj("effluent_application", "farm_activity", "Effluent Application", "Apply stored dairy effluent to suitable paddocks when soil moisture, storage and operating conditions allow.", {"activity_type": "Effluent", "status": "Established", "timing": "When soil and weather conditions are suitable", "purpose": "Manage effluent responsibly while returning nutrients to the land.", "risk_level": "High"}),
        _obj("pump_maintenance", "farm_activity", "Main Water Pump Maintenance", "Complete planned service work on the main water pump after repeated early-season pressure fluctuations.", {"activity_type": "Maintenance", "status": "In progress", "timing": "Current maintenance window", "purpose": "Restore reliable stock water delivery and reduce the risk of an avoidable farm-wide water interruption.", "risk_level": "High"}),

        # Inputs
        _obj("nitrogen_fertiliser", "farm_input", "Nitrogen Fertiliser", "Purchased nitrogen fertiliser used selectively to support pasture growth where nutrient planning identifies a need.", {"input_type": "Fertiliser", "availability": "Available", "purpose": "Support pasture growth where justified by seasonal demand and farm nutrient planning."}),
        _obj("diesel", "farm_input", "Diesel", "Fuel used for tractors, feed movement and other mobile farm equipment.", {"input_type": "Fuel", "availability": "Available", "purpose": "Provide fuel for mobile farm operations."}),
        _obj("veterinary_inputs", "farm_input", "Veterinary Inputs", "Medicines and animal health products held for approved livestock treatment and prevention activities.", {"input_type": "Animal health", "availability": "Available", "purpose": "Enable timely veterinary and farm-led animal health responses."}),
        _obj("supplementary_feed_input", "farm_input", "Purchased Supplementary Feed", "Purchased feed used when pasture supply or animal demand requires additional nutritional support.", {"input_type": "Supplementary feed", "availability": "Available", "purpose": "Buffer pasture deficits for priority animal groups."}),

        # People
        _obj("farm_manager", "person", "Mara Te Rangi", "Farm manager responsible for daily operating decisions, people coordination, pasture allocation and farm performance.", {"role": "Farm Manager", "employment_type": "Employee", "responsibility": "Coordinate the farm operating system and make daily decisions across livestock, pasture, people and infrastructure."}),
        _obj("farm_owner", "person", "Wiremu Carter", "Farm owner overseeing the longer-term direction and viability of the farm business.", {"role": "Farm Owner", "employment_type": "Owner", "responsibility": "Own the farm business and oversee longer-term investment, production and operating sustainability."}),

        # Teams
        _obj("core_farm_team", "team", "Core Farm Team", "The on-farm team responsible for routine livestock, pasture and daily farm operations.", {"team_type": "Farm team", "purpose": "Run the daily farm operation safely and consistently."}),

        # Service providers
        _obj("waikato_vets", "service_provider", "Waikato Rural Vets", "The farm's veterinary service supporting herd health, diagnosis, treatment and preventive programmes.", {"service_type": "Veterinary", "relationship_status": "Current", "purpose": "Provide veterinary support for animal health events and herd health planning."}),
        _obj("southern_farm_supplies", "service_provider", "Southern Rural Supplies", "A fictional rural supplier providing fertiliser, farm inputs and selected consumables.", {"service_type": "Farm supplies", "relationship_status": "Preferred", "purpose": "Supply agricultural inputs and support seasonal procurement."}),
        _obj("waikato_milk_co", "service_provider", "Waikato Milk Co-op", "A fictional dairy processor collecting milk from Kauri Ridge Dairy and providing milk quality and collection information.", {"service_type": "Milk processor", "relationship_status": "Current", "purpose": "Collect farm milk and provide processor-side production information and feedback."}),
        _obj("waikato_agri_engineering", "service_provider", "Waikato Agri Engineering", "A fictional rural engineering service supporting farm equipment servicing, pump repairs and calibration work.", {"service_type": "Engineering", "relationship_status": "Current", "purpose": "Provide specialist engineering support for critical farm equipment and infrastructure."}),

        # Weather
        _obj("late_spring_rain", "weather_condition", "Late Spring Rain", "A wet-weather period that improves pasture growth but increases soil traffic and effluent application constraints.", {"condition_type": "Wet period", "severity": "Moderate", "period": "Current spring fortnight"}),
        _obj("short_heat_period", "weather_condition", "Short Early Summer Heat", "A short run of warm conditions expected to increase water demand and reduce daily pasture growth.", {"condition_type": "Heat", "severity": "Moderate", "period": "Early summer forecast"}),

        # Observations
        _obj("north_pasture_observation", "observation", "North Pasture Cover Observation", "Weekly pasture assessment showing the North Pasture carrying above-target cover ahead of the next grazing rotation.", {"observation_type": "Pasture cover", "status": "Normal", "finding": "Cover is above the current target and can carry the next planned milking-herd allocation without supplementary feed."}),
        _obj("first_calver_condition_observation", "observation", "First-Calver Condition Observation", "Routine condition assessment showing a subset of first-calvers require close monitoring through peak lactation.", {"observation_type": "Animal condition", "status": "Watch", "finding": "Most first-calvers are on target, but a small group is showing greater-than-expected condition loss."}),
        _obj("water_quality_observation", "observation", "Kahikatea Stream Water Observation", "Routine visual and field observation of the stream margin after the recent wet period.", {"observation_type": "Water quality", "status": "Normal", "finding": "No visible deterioration; stream margin remains stable after recent rainfall."}),
        _obj("pump_condition_observation", "observation", "Main Water Pump Condition Observation", "Inspection record showing pressure instability and evidence that planned pump maintenance should be brought forward.", {"observation_type": "Equipment condition", "status": "Action required", "finding": "Pressure fluctuations indicate the pump needs service before the expected warm-weather increase in demand."}),
        _obj("spring_milk_observation", "observation", "Spring Milk Production Observation", "Current farm production observation showing healthy seasonal production with some first-calver variation.", {"observation_type": "Milk production", "status": "Normal", "finding": "Whole-herd production is on seasonal expectation; first-calver performance is the main area requiring attention."}),

        # Animal health events
        _obj("first_calver_mastitis_event", "animal_health_event", "First-Calver Mastitis Cluster", "A small cluster of mastitis cases identified early in the spring season within the first-calver group.", {"event_type": "Mastitis", "status": "Monitoring", "response": "Treat affected animals under the farm veterinary programme, review milking hygiene and monitor recurrence."}),
        _obj("mob_lameness_event", "animal_health_event", "Lameness Watchlist", "A small number of cows requiring follow-up after increased walking distance during wet paddock conditions.", {"event_type": "Lameness", "status": "Monitoring", "response": "Draft affected animals for inspection, manage treatment and reduce unnecessary walking pressure where practical."}),

        # Maintenance events
        _obj("water_pump_service", "maintenance_event", "Main Water Pump Service", "Planned service and repair work to stabilise water pressure before the warmer period increases farm water demand.", {"maintenance_type": "Planned service", "status": "In progress", "priority": "High", "response": "Inspect seals and pressure controls, replace worn components and confirm delivery pressure under load."}),
        _obj("milking_system_calibration", "maintenance_event", "Milking System Calibration", "Scheduled calibration of milk meters and associated monitoring equipment ahead of the peak production period.", {"maintenance_type": "Calibration", "status": "Planned", "priority": "High", "response": "Calibrate meters, verify readings and record the results before the next production review."}),

        # Environmental plan
        _obj("freshwater_effluent_plan", "environmental_plan", "Freshwater & Effluent Management Plan", "The farm-level plan linking waterway protection, effluent storage and application, soil conditions and normal farm practices.", {"plan_type": "Freshwater and waterways", "status": "Current", "focus": "Prevent avoidable nutrient and effluent losses while maintaining practical farm operations."}),

        # Production outputs
        _obj("daily_milk_output", "production_output", "Daily Milk Production", "Daily bulk milk production collected from the farm dairy during the spring peak.", {"output_type": "Milk", "status": "On target", "period": "Current production week", "quality": "Within expected collection parameters"}),
        _obj("spring_milksolids", "production_output", "Spring Milksolids Production", "Season-to-date milksolids contribution used to monitor production performance.", {"output_type": "Milksolids", "status": "On target", "period": "Current spring season", "quality": "Tracking to seasonal expectation"}),
        _obj("grass_silage_reserve", "production_output", "Grass Silage Reserve", "Conserved pasture held as a strategic feed reserve for periods when pasture supply falls short of demand.", {"output_type": "Pasture conserved", "status": "On target", "period": "Current season", "quality": "Good quality conserved feed"}),

        # Risks
        _obj("wet_weather_ground_damage", "operational_risk", "Wet Weather Ground Damage", "Extended wet conditions could cause pugging, pasture damage and reduced access to moisture-sensitive paddocks.", {"category": "Weather", "status": "Monitored", "severity": "High", "description": "Ground damage could reduce available grazing area and increase pressure on supplementary feed."}),
        _obj("water_supply_interruption", "operational_risk", "Stock Water Supply Interruption", "Failure of the main water pump could interrupt reliable stock water supply and create animal welfare and production risk.", {"category": "Infrastructure", "status": "Mitigated", "severity": "High", "description": "A pump fault during a warm period could rapidly become a farm-wide operational issue."}),
        _obj("first_calver_condition_decline", "operational_risk", "First-Calver Condition Decline", "Condition loss in first-calvers could reduce reproductive performance and future herd productivity if not addressed early.", {"category": "Animal health", "status": "Monitored", "severity": "Medium", "description": "The group requires close feed and animal-health monitoring through peak lactation."}),

        # Outcomes
        _obj("reliable_milk_supply", "business_outcome", "Reliable Seasonal Milk Production", "The farm maintains a dependable seasonal milk flow without avoidable disruption from preventable operational failures.", {"outcome_type": "Production", "status": "On track", "description": "Milk production remains broadly on seasonal expectation while operational risks are actively managed."}),
        _obj("healthy_herd", "business_outcome", "Healthy Productive Herd", "The herd maintains good health, welfare and condition throughout the seasonal production cycle.", {"outcome_type": "Animal welfare", "status": "Watch", "description": "Overall herd health is strong, with specific attention required for mastitis and first-calver condition."}),
        _obj("protected_waterways", "business_outcome", "Protected Farm Waterways", "Farm activities are managed so that waterways remain in good condition while the farm continues to operate productively.", {"outcome_type": "Environmental", "status": "On track", "description": "The farm monitors waterway condition and manages effluent and land activities around sensitive areas."}),
        _obj("resilient_farm_operation", "business_outcome", "Resilient Farm Operation", "The farm can continue operating through normal seasonal variability, equipment issues and changing environmental conditions without disproportionate disruption.", {"outcome_type": "Business continuity", "status": "On track", "description": "Operational resilience is supported by planned maintenance, feed reserves, monitoring and clear farm routines."}),

        # Information records
        _obj("spring_grazing_plan", "information_record", "Spring Grazing Plan", "Current grazing allocation and rotation plan used to manage pasture supply and herd demand through the spring period.", {"record_type": "Grazing plan", "sensitivity": "Internal", "purpose": "Coordinate grazing decisions across paddocks, pasture cover and herd demand."}),
        _obj("herd_health_record", "information_record", "Herd Health Record", "Current herd-health record summarising treatment, monitoring and follow-up activity.", {"record_type": "Animal health record", "sensitivity": "Confidential", "purpose": "Provide an evidence trail for animal health decisions and follow-up."}),
        _obj("weekly_milk_report", "information_record", "Weekly Milk Production Report", "Weekly production report summarising milk and milksolids performance for farm review.", {"record_type": "Milk report", "sensitivity": "Confidential", "purpose": "Compare actual production with seasonal expectation and identify emerging variation."}),
        _obj("maintenance_register", "information_record", "Farm Maintenance Register", "Current record of planned and reactive maintenance affecting critical farm equipment and infrastructure.", {"record_type": "Maintenance record", "sensitivity": "Internal", "purpose": "Coordinate maintenance and provide evidence of work completed on critical equipment."}),
    ],

    "relationships": [
        # Farm structure
        _rel("has_paddock", "kauri_ridge_dairy", "north_pasture"),
        _rel("has_paddock", "kauri_ridge_dairy", "home_block"),
        _rel("has_paddock", "kauri_ridge_dairy", "east_flat"),
        _rel("has_paddock", "kauri_ridge_dairy", "river_margin"),
        _rel("has_paddock", "kauri_ridge_dairy", "silage_paddock"),
        _rel("has_waterway", "kauri_ridge_dairy", "kahikatea_stream"),
        _rel("has_waterway", "kauri_ridge_dairy", "north_drain"),
        _rel("has_pasture", "north_pasture", "north_pasture_sward"),
        _rel("has_pasture", "home_block", "home_block_sward"),
        _rel("has_pasture", "east_flat", "east_flat_sward"),
        _rel("has_pasture", "river_margin", "river_margin_sward"),
        _rel("has_pasture", "silage_paddock", "longacre_silage_sward"),
        _rel("has_herd", "kauri_ridge_dairy", "milking_herd"),
        _rel("has_herd", "kauri_ridge_dairy", "replacement_herd"),
        _rel("has_group", "milking_herd", "spring_calvers"),
        _rel("has_group", "milking_herd", "first_calvers"),
        _rel("has_group", "replacement_herd", "rising_two_year_olds"),
        _rel("has_feed_resource", "kauri_ridge_dairy", "spring_pasture_feed"),
        _rel("has_feed_resource", "kauri_ridge_dairy", "grass_silage"),
        _rel("has_feed_resource", "kauri_ridge_dairy", "maize_silage"),
        _rel("has_facility", "kauri_ridge_dairy", "farm_dairy"),
        _rel("has_facility", "kauri_ridge_dairy", "stock_yards"),
        _rel("has_facility", "kauri_ridge_dairy", "implement_shed"),
                _rel("has_equipment", "kauri_ridge_dairy", "main_tractor"),
        _rel("has_equipment", "kauri_ridge_dairy", "milking_system"),
        _rel("has_equipment", "kauri_ridge_dairy", "feed_wagon"),
        _rel("has_equipment", "kauri_ridge_dairy", "water_pump"),
        _rel("has_equipment", "kauri_ridge_dairy", "utility_vehicle"),
        _rel("has_equipment", "kauri_ridge_dairy", "effluent_irrigator"),
        _rel("has_water_system", "kauri_ridge_dairy", "bore_water_system"),
        _rel("has_effluent_system", "kauri_ridge_dairy", "effluent_storage_system"),

        # Activities and operational structure
        _rel("has_activity", "kauri_ridge_dairy", "morning_milking"),
        _rel("has_activity", "kauri_ridge_dairy", "afternoon_milking"),
        _rel("has_activity", "kauri_ridge_dairy", "morning_grazing"),
        _rel("has_activity", "kauri_ridge_dairy", "supplementary_feeding"),
        _rel("has_activity", "kauri_ridge_dairy", "spring_calving"),
        _rel("has_activity", "kauri_ridge_dairy", "animal_health_round"),
        _rel("has_activity", "kauri_ridge_dairy", "pasture_walk"),
        _rel("has_activity", "kauri_ridge_dairy", "silage_harvest"),
        _rel("has_activity", "kauri_ridge_dairy", "fertiliser_application"),
        _rel("has_activity", "kauri_ridge_dairy", "effluent_application"),
        _rel("has_activity", "kauri_ridge_dairy", "pump_maintenance"),
        _rel("has_input", "kauri_ridge_dairy", "nitrogen_fertiliser"),
        _rel("has_input", "kauri_ridge_dairy", "veterinary_inputs"),
        _rel("has_input", "kauri_ridge_dairy", "supplementary_feed_input"),
        _rel("has_input", "kauri_ridge_dairy", "diesel"),
        _rel("has_person", "kauri_ridge_dairy", "farm_manager"),
        _rel("has_person", "kauri_ridge_dairy", "farm_owner"),
                _rel("has_team", "kauri_ridge_dairy", "core_farm_team"),
        _rel("uses_service_provider", "kauri_ridge_dairy", "waikato_vets"),
        _rel("uses_service_provider", "kauri_ridge_dairy", "southern_farm_supplies"),
        _rel("uses_service_provider", "kauri_ridge_dairy", "waikato_milk_co"),
        _rel("uses_service_provider", "kauri_ridge_dairy", "waikato_agri_engineering"),
        _rel("has_weather_condition", "kauri_ridge_dairy", "late_spring_rain"),
        _rel("has_weather_condition", "kauri_ridge_dairy", "short_heat_period"),
        _rel("has_observation", "kauri_ridge_dairy", "north_pasture_observation"),
        _rel("has_observation", "kauri_ridge_dairy", "first_calver_condition_observation"),
        _rel("has_observation", "kauri_ridge_dairy", "water_quality_observation"),
        _rel("has_observation", "kauri_ridge_dairy", "pump_condition_observation"),
        _rel("has_observation", "kauri_ridge_dairy", "spring_milk_observation"),
        _rel("has_animal_health_event", "kauri_ridge_dairy", "first_calver_mastitis_event"),
        _rel("has_animal_health_event", "kauri_ridge_dairy", "mob_lameness_event"),
        _rel("has_maintenance_event", "kauri_ridge_dairy", "water_pump_service"),
        _rel("has_maintenance_event", "kauri_ridge_dairy", "milking_system_calibration"),
        _rel("has_environmental_plan", "kauri_ridge_dairy", "freshwater_effluent_plan"),
        _rel("has_output", "kauri_ridge_dairy", "daily_milk_output"),
        _rel("has_output", "kauri_ridge_dairy", "spring_milksolids"),
        _rel("has_output", "kauri_ridge_dairy", "grass_silage_reserve"),
        _rel("has_risk", "kauri_ridge_dairy", "wet_weather_ground_damage"),
        _rel("has_risk", "kauri_ridge_dairy", "water_supply_interruption"),
        _rel("has_risk", "kauri_ridge_dairy", "first_calver_condition_decline"),
        _rel("has_outcome", "kauri_ridge_dairy", "reliable_milk_supply"),
        _rel("has_outcome", "kauri_ridge_dairy", "healthy_herd"),
        _rel("has_outcome", "kauri_ridge_dairy", "protected_waterways"),
        _rel("has_outcome", "kauri_ridge_dairy", "resilient_farm_operation"),
        _rel("has_record", "kauri_ridge_dairy", "spring_grazing_plan"),
        _rel("has_record", "kauri_ridge_dairy", "herd_health_record"),
        _rel("has_record", "kauri_ridge_dairy", "weekly_milk_report"),
        _rel("has_record", "kauri_ridge_dairy", "maintenance_register"),

        # People and teams
        _rel("member_of", "farm_manager", "core_farm_team"),

        # Activity ownership / performance
        _rel("managed_by", "morning_milking", "farm_manager"),
        _rel("managed_by", "afternoon_milking", "farm_manager"),
        _rel("managed_by", "morning_grazing", "farm_manager"),
        _rel("managed_by", "supplementary_feeding", "farm_manager"),
        _rel("managed_by", "spring_calving", "farm_manager"),
        _rel("managed_by", "animal_health_round", "farm_manager"),
        _rel("managed_by", "pasture_walk", "farm_manager"),
        _rel("managed_by", "silage_harvest", "farm_manager"),
        _rel("managed_by", "fertiliser_application", "farm_manager"),
        _rel("managed_by", "effluent_application", "farm_manager"),
        _rel("managed_by", "pump_maintenance", "farm_manager"),
        _rel("managed_by", "freshwater_effluent_plan", "farm_manager"),

        _rel("performed_by", "morning_milking", "core_farm_team"),
        _rel("performed_by", "afternoon_milking", "core_farm_team"),
        _rel("performed_by", "morning_grazing", "core_farm_team"),
        _rel("performed_by", "supplementary_feeding", "core_farm_team"),
        _rel("performed_by", "spring_calving", "core_farm_team"),
        _rel("performed_by", "animal_health_round", "core_farm_team"),
        _rel("performed_by", "pasture_walk", "core_farm_team"),
        _rel("performed_by", "silage_harvest", "core_farm_team"),
        _rel("performed_by", "fertiliser_application", "core_farm_team"),
        _rel("performed_by", "effluent_application", "core_farm_team"),

        # Activity locations and livestock
        _rel("takes_place_at", "morning_milking", "farm_dairy"),
        _rel("takes_place_at", "afternoon_milking", "farm_dairy"),
        _rel("takes_place_at", "morning_grazing", "north_pasture"),
        _rel("takes_place_at", "spring_calving", "stock_yards"),
        _rel("takes_place_at", "animal_health_round", "stock_yards"),
        _rel("takes_place_at", "pasture_walk", "north_pasture"),
        _rel("takes_place_at", "silage_harvest", "silage_paddock"),
        _rel("takes_place_at", "fertiliser_application", "east_flat"),
        _rel("takes_place_at", "effluent_application", "river_margin"),

        _rel("involves_herd", "morning_milking", "milking_herd"),
        _rel("involves_herd", "afternoon_milking", "milking_herd"),
        _rel("involves_herd", "morning_grazing", "milking_herd"),
        _rel("involves_herd", "supplementary_feeding", "first_calvers"),
        _rel("involves_herd", "spring_calving", "spring_calvers"),
        _rel("involves_herd", "animal_health_round", "milking_herd"),
        _rel("involves_herd", "animal_health_round", "first_calvers"),

        # Equipment / inputs / conditions
        _rel("uses_equipment", "morning_milking", "milking_system"),
        _rel("uses_equipment", "afternoon_milking", "milking_system"),
        _rel("uses_equipment", "supplementary_feeding", "feed_wagon"),
        _rel("uses_equipment", "effluent_application", "effluent_irrigator"),
        _rel("uses_equipment", "pump_maintenance", "water_pump"),
        _rel("uses_equipment", "morning_grazing", "utility_vehicle"),
        _rel("uses_equipment", "silage_harvest", "main_tractor"),
        _rel("uses_input", "supplementary_feeding", "supplementary_feed_input"),
        _rel("uses_input", "supplementary_feeding", "grass_silage"),
        _rel("uses_input", "supplementary_feeding", "maize_silage"),
        _rel("uses_input", "fertiliser_application", "nitrogen_fertiliser"),
        _rel("uses_input", "fertiliser_application", "diesel"),
        _rel("uses_input", "animal_health_round", "veterinary_inputs"),
        _rel("affected_by", "morning_grazing", "late_spring_rain"),
        _rel("affected_by", "supplementary_feeding", "north_pasture_observation"),
        _rel("affected_by", "fertiliser_application", "late_spring_rain"),
        _rel("affected_by", "effluent_application", "late_spring_rain"),
        _rel("depends_on", "effluent_application", "effluent_storage_system"),
        _rel("depends_on", "morning_milking", "milking_system"),
        _rel("depends_on", "afternoon_milking", "milking_system"),

        # Activity outputs
        _rel("produces", "morning_milking", "daily_milk_output"),
        _rel("produces", "afternoon_milking", "daily_milk_output"),
        _rel("produces", "morning_milking", "spring_milksolids"),
        _rel("produces", "afternoon_milking", "spring_milksolids"),
        _rel("produces", "silage_harvest", "grass_silage_reserve"),
        _rel("depends_on", "daily_milk_output", "morning_milking"),
        _rel("depends_on", "daily_milk_output", "afternoon_milking"),
        _rel("depends_on", "spring_milksolids", "morning_milking"),
        _rel("depends_on", "spring_milksolids", "afternoon_milking"),
        _rel("collected_by", "daily_milk_output", "waikato_milk_co"),
        _rel("collected_by", "spring_milksolids", "waikato_milk_co"),

        # Inputs and suppliers
        _rel("supplied_by", "supplementary_feed_input", "southern_farm_supplies"),
        _rel("supplied_by", "nitrogen_fertiliser", "southern_farm_supplies"),
        _rel("supplied_by", "veterinary_inputs", "waikato_vets"),
                        _rel("supplied_by", "maize_silage", "southern_farm_supplies"),

        # Observations
        _rel("observes", "north_pasture_observation", "north_pasture"),
        _rel("observes", "north_pasture_observation", "north_pasture_sward"),
        _rel("observes", "first_calver_condition_observation", "first_calvers"),
        _rel("observes", "water_quality_observation", "kahikatea_stream"),
        _rel("observes", "pump_condition_observation", "water_pump"),
        _rel("observes", "spring_milk_observation", "milking_herd"),
        _rel("taken_by", "north_pasture_observation", "farm_manager"),
        _rel("taken_by", "first_calver_condition_observation", "farm_manager"),
        _rel("taken_by", "water_quality_observation", "farm_manager"),
        _rel("taken_by", "pump_condition_observation", "farm_manager"),
        _rel("taken_by", "spring_milk_observation", "farm_manager"),

        # Animal health
        _rel("affects", "first_calver_mastitis_event", "first_calvers"),
        _rel("affects", "mob_lameness_event", "milking_herd"),
        _rel("treated_by", "first_calver_mastitis_event", "waikato_vets"),
        _rel("treated_by", "mob_lameness_event", "waikato_vets"),

        # Maintenance
        _rel("applies_to", "water_pump_service", "water_pump"),
        _rel("applies_to", "milking_system_calibration", "milking_system"),
        _rel("serviced_by", "water_pump_service", "waikato_agri_engineering"),
        _rel("serviced_by", "milking_system_calibration", "waikato_agri_engineering"),
        _rel("creates_record", "water_pump_service", "maintenance_register"),
        _rel("creates_record", "milking_system_calibration", "maintenance_register"),

        # Environmental plan
        _rel("governs", "freshwater_effluent_plan", "kahikatea_stream"),
        _rel("governs", "freshwater_effluent_plan", "north_drain"),
        _rel("governs", "freshwater_effluent_plan", "river_margin"),
        _rel("governs", "freshwater_effluent_plan", "fertiliser_application"),
        _rel("governs", "freshwater_effluent_plan", "effluent_application"),
        _rel("governs", "freshwater_effluent_plan", "effluent_storage_system"),
        _rel("mitigates", "effluent_application", "wet_weather_ground_damage"),
        _rel("mitigates", "fertiliser_application", "wet_weather_ground_damage"),
        _rel("mitigates", "pasture_walk", "first_calver_condition_decline"),
        _rel("mitigates", "pump_maintenance", "water_supply_interruption"),
        _rel("mitigates", "supplementary_feeding", "first_calver_condition_decline"),

        # Risks
        _rel("impacts", "wet_weather_ground_damage", "morning_grazing"),
        _rel("impacts", "wet_weather_ground_damage", "reliable_milk_supply"),
        _rel("impacts", "water_supply_interruption", "morning_milking"),
        _rel("impacts", "water_supply_interruption", "daily_milk_output"),
        _rel("impacts", "first_calver_condition_decline", "supplementary_feeding"),
        _rel("impacts", "first_calver_condition_decline", "spring_milksolids"),

        # Outcomes
        _rel("supports", "daily_milk_output", "reliable_milk_supply"),
        _rel("supports", "animal_health_round", "healthy_herd"),
        _rel("supports", "fertiliser_application", "protected_waterways"),
        _rel("supports", "pump_maintenance", "resilient_farm_operation"),
        _rel("supports", "effluent_application", "protected_waterways"),
        _rel("supports", "fertiliser_application", "protected_waterways"),

        # Records / evidence
        _rel("creates_record", "pasture_walk", "spring_grazing_plan"),
        _rel("creates_record", "animal_health_round", "herd_health_record"),
        _rel("associated_with", "weekly_milk_report", "daily_milk_output"),
    ],

    "appearance": {
        "object_types": {
            "farm": {"shape": "hexagon", "icon": "farm", "background": "#E8F5E9"},
            "paddock": {"shape": "box", "icon": "field", "background": "#DCEFD8"},
            "waterway": {"shape": "ellipse", "icon": "water", "background": "#D0EBFF"},
            "pasture": {"shape": "box", "icon": "crop", "background": "#E7F5DC"},
            "herd": {"shape": "ellipse", "icon": "livestock", "background": "#FFF3BF"},
            "animal_group": {"shape": "ellipse", "icon": "livestock", "background": "#FFF9DB"},
            "feed_resource": {"shape": "box", "icon": "product", "background": "#FFE8CC"},
            "farm_facility": {"shape": "box", "icon": "barn", "background": "#FFD8A8"},
            "farm_equipment": {"shape": "box", "icon": "tractor", "background": "#FFE3E3"},
            "water_system": {"shape": "box", "icon": "water", "background": "#D3F9D8"},
            "effluent_system": {"shape": "box", "icon": "water", "background": "#C5F6FA"},
            "farm_activity": {"shape": "ellipse", "icon": "process", "background": "#D0EBFF"},
            "farm_input": {"shape": "box", "icon": "product", "background": "#FFF3BF"},
            "person": {"shape": "ellipse", "icon": "person", "background": "#F3D9FA"},
            "team": {"shape": "ellipse", "icon": "team", "background": "#A5D8FF"},
            "service_provider": {"shape": "box", "icon": "organisation", "background": "#E5DBFF"},
            "weather_condition": {"shape": "ellipse", "icon": "weather", "background": "#E7F5FF"},
            "observation": {"shape": "box", "icon": "chart", "background": "#F3F0FF"},
            "animal_health_event": {"shape": "diamond", "icon": "warning", "background": "#FFE3E3"},
            "maintenance_event": {"shape": "box", "icon": "task", "background": "#E9ECEF"},
            "environmental_plan": {"shape": "hexagon", "icon": "shield", "background": "#D3F9D8"},
            "production_output": {"shape": "star", "icon": "chart", "background": "#96F2D7"},
            "operational_risk": {"shape": "diamond", "icon": "warning", "background": "#FFE3E3"},
            "business_outcome": {"shape": "star", "icon": "target", "background": "#B2F2BB"},
            "information_record": {"shape": "box", "icon": "document", "background": "#F3D9FA"},
        },
        "relationship_types": {
            "has_paddock": {"colour": "#868E96"},
            "has_waterway": {"colour": "#1971C2"},
            "has_pasture": {"colour": "#2F9E44"},
            "has_herd": {"colour": "#FAB005"},
            "has_group": {"colour": "#E67700"},
            "has_feed_resource": {"colour": "#D9480F"},
            "has_facility": {"colour": "#C92A2A"},
            "has_equipment": {"colour": "#E03131"},
            "has_water_system": {"colour": "#1971C2"},
            "has_effluent_system": {"colour": "#0C8599"},
            "has_activity": {"colour": "#6741D9"},
            "has_input": {"colour": "#AE3EC9"},
            "has_person": {"colour": "#9C36B5"},
            "has_team": {"colour": "#1864AB"},
            "uses_service_provider": {"colour": "#495057"},
            "has_weather_condition": {"colour": "#74C0FC"},
            "has_observation": {"colour": "#845EF7"},
            "has_animal_health_event": {"colour": "#D6336C"},
            "has_maintenance_event": {"colour": "#495057"},
            "has_environmental_plan": {"colour": "#2B8A3E"},
            "has_output": {"colour": "#2F9E44"},
            "has_risk": {"colour": "#E03131"},
            "has_outcome": {"colour": "#2F9E44"},
            "has_record": {"colour": "#7950F2"},
            "managed_by": {"colour": "#1864AB"},
            "member_of": {"colour": "#495057"},
            "performed_by": {"colour": "#1971C2"},
            "takes_place_at": {"colour": "#868E96"},
            "involves_herd": {"colour": "#FAB005"},
            "uses_equipment": {"colour": "#E8590C"},
            "uses_input": {"colour": "#AE3EC9"},
            "affected_by": {"colour": "#F08C00"},
            "produces": {"colour": "#2F9E44"},
            "creates_record": {"colour": "#7950F2"},
            "observes": {"colour": "#845EF7"},
            "taken_by": {"colour": "#1864AB"},
            "affects": {"colour": "#E03131"},
            "treated_by": {"colour": "#D6336C"},
            "applies_to": {"colour": "#495057"},
            "serviced_by": {"colour": "#495057"},
            "governs": {"colour": "#2B8A3E"},
            "mitigates": {"colour": "#2F9E44"},
            "impacts": {"colour": "#E03131"},
            "supports": {"colour": "#12B886"},
            "supplied_by": {"colour": "#7950F2"},
            "depends_on": {"colour": "#E03131"},
            "associated_with": {"colour": "#7950F2"},
            "collected_by": {"colour": "#1971C2"},
        },
    },
}

# Convenient aliases for callers that use the naming convention of other templates.
FARM_OPERATIONS_TEMPLATE = NEW_ZEALAND_FARM_OPERATIONS_TEMPLATE

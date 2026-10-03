"""Business Operations model template.

A blank, reusable starting-point model for understanding how an organisation
actually operates. The template is deliberately broad rather than industry-
specific: it connects organisational structure, capabilities, processes,
activities, services, people, teams, applications, information, suppliers,
resources, governance, events, risks, decisions, measures and outcomes.

The template contains no sample objects or relationships. It is intended as a
meaningful semantic starting point that a user can extend for their own
organisation or problem domain.

The template is declarative. Template instantiation services are responsible
for turning the definition into database records.
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
    """Define cardinality in natural subject/object terms."""
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


BUSINESS_OPERATIONS_TEMPLATE = {
    "key": "business_operations",
    "name": "Business Operations",
    "description": (
        "A reusable starting point for modelling how an organisation actually works. "
        "The model connects organisational structure, capabilities, processes, activities, "
        "services, people, teams, applications, information, resources, suppliers, governance, "
        "risks, decisions, measures and outcomes so the operating model can be understood as a whole."
    ),

    "object_types": [
        _otype(
            "organisation", "Organisation",
            "The organisation or operating entity being modelled as a whole.", 10,
            [
                _attr("organisation_type", "Organisation type", "choice", "The broad kind of organisation being modelled.", 10,
                      choices=["Commercial business", "Public sector", "Not-for-profit", "Other"]),
                _attr("purpose", "Purpose", "text", "The organisation's primary purpose or reason for operating.", 20),
                _attr("operating_model", "Operating model", "text", "A concise description of how the organisation is structured to deliver its purpose.", 30),
                _attr("scope", "Scope", "text", "The organisational boundary represented by this model.", 40),
            ],
        ),
        _otype(
            "business_unit", "Business Unit",
            "A distinct part of the organisation with a defined area of responsibility or operating focus.", 20,
            [
                _attr("unit_type", "Unit type", "choice", "The broad kind of organisational unit.", 10,
                      choices=["Business unit", "Division", "Function", "Department", "Region", "Other"]),
                _attr("purpose", "Purpose", "text", "The primary purpose of the unit within the organisation.", 20),
                _attr("scope", "Scope", "text", "The area of the organisation or work covered by the unit.", 30),
            ],
        ),
        _otype(
            "capability", "Capability",
            "An organisational ability or area of competence required to achieve a meaningful business result.", 30,
            [
                _attr("capability_area", "Capability area", "text", "The domain or business area in which the capability exists.", 10),
                _attr("maturity", "Maturity", "choice", "The current maturity of the capability.", 20,
                      choices=["Emerging", "Developing", "Established", "Advanced"]),
                _attr("importance", "Importance", "choice", "The relative importance of the capability to the organisation.", 30,
                      choices=["Supporting", "Important", "Critical"]),
                _attr("purpose", "Purpose", "text", "What the capability enables the organisation to do.", 40),
            ],
        ),
        _otype(
            "process", "Process",
            "A repeatable body of work through which the organisation transforms inputs into services, outputs or outcomes.", 40,
            [
                _attr("process_type", "Process type", "choice", "The broad nature of the process.", 10,
                      choices=["Core", "Supporting", "Management", "Control"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current state of the process.", 20,
                      choices=["Planned", "Current", "Under review", "Retiring"]),
                _attr("frequency", "Frequency", "text", "How often the process normally runs.", 30),
                _attr("purpose", "Purpose", "text", "The business purpose the process serves.", 40),
                _attr("criticality", "Criticality", "choice", "The impact of process failure or interruption.", 50,
                      choices=["Low", "Medium", "High", "Critical"]),
            ],
        ),
        _otype(
            "operational_activity", "Operational Activity",
            "A defined piece of work performed within or alongside a process to achieve an immediate operational result.", 50,
            [
                _attr("activity_type", "Activity type", "choice", "The broad kind of operational activity.", 10,
                      choices=["Manual", "Automated", "Review", "Approval", "Interaction", "Handover", "Other"]),
                _attr("status", "Status", "choice", "The current operating status of the activity.", 20,
                      choices=["Planned", "Current", "Under review", "Retiring"]),
                _attr("frequency", "Frequency", "text", "How often the activity is normally performed.", 30),
                _attr("purpose", "Purpose", "text", "The immediate purpose of the activity.", 40),
            ],
        ),
        _otype(
            "service", "Service",
            "A service provided to a customer, user or another part of the organisation as a meaningful unit of value or support.", 60,
            [
                _attr("service_type", "Service type", "choice", "The broad type of service.", 10,
                      choices=["Customer", "Internal", "Platform", "Shared", "Other"]),
                _attr("audience", "Audience", "text", "The primary customer, user or recipient of the service.", 20),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the service.", 30,
                      choices=["Planned", "Current", "Under review", "Retiring"]),
                _attr("purpose", "Purpose", "text", "The value or support the service is intended to provide.", 40),
            ],
        ),
        _otype(
            "person", "Person",
            "An individual with a defined role, responsibility or involvement in the organisation's operating model.", 70,
            [
                _attr("role", "Role", "text", "The primary role played by the person in the model.", 10),
                _attr("employment_type", "Employment type", "choice", "The person's relationship to the organisation.", 20,
                      choices=["Employee", "Contractor", "Partner", "Customer", "Other"]),
                _attr("responsibility", "Responsibility", "text", "The principal responsibility relevant to the model.", 30),
            ],
        ),
        _otype(
            "team", "Team",
            "A group of people accountable for a coherent area of work, capability or operational responsibility.", 80,
            [
                _attr("team_type", "Team type", "choice", "The broad operating role of the team.", 10,
                      choices=["Operational", "Delivery", "Support", "Leadership", "Specialist", "Other"]),
                _attr("responsibility", "Responsibility", "text", "The main area of accountability held by the team.", 20),
                _attr("purpose", "Purpose", "text", "The team's primary operating purpose.", 30),
            ],
        ),
        _otype(
            "application", "Application",
            "A software application or digital system that supports, automates or enables business work.", 90,
            [
                _attr("application_type", "Application type", "choice", "The broad kind of application.", 10,
                      choices=["SaaS", "Internal", "Platform", "Custom", "Legacy", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the application.", 20,
                      choices=["Planned", "Current", "Under review", "Retiring"]),
                _attr("criticality", "Criticality", "choice", "The operational importance of the application.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("purpose", "Purpose", "text", "The business purpose the application supports.", 40),
            ],
        ),
        _otype(
            "information", "Information",
            "A meaningful set of information, record, data or document used to operate, coordinate or understand the business.", 100,
            [
                _attr("information_type", "Information type", "choice", "The broad kind of information represented.", 10,
                      choices=["Record", "Data", "Document", "Report", "Reference", "Other"]),
                _attr("sensitivity", "Sensitivity", "choice", "The general sensitivity of the information.", 20,
                      choices=["Public", "Internal", "Confidential", "Restricted"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current state of the information asset.", 30,
                      choices=["Current", "Under review", "Archived", "Retiring"]),
                _attr("purpose", "Purpose", "text", "How the information is used in the operating model.", 40),
            ],
        ),
        _otype(
            "supplier", "Supplier / Partner",
            "An external organisation that supplies products, services, capability or specialist support to the organisation.", 110,
            [
                _attr("supplier_type", "Supplier type", "choice", "The broad kind of external relationship.", 10,
                      choices=["Supplier", "Technology provider", "Professional service", "Partner", "Other"]),
                _attr("relationship_status", "Relationship status", "choice", "The current status of the external relationship.", 20,
                      choices=["Prospective", "Current", "Preferred", "Exiting"]),
                _attr("purpose", "Purpose", "text", "The role the supplier or partner plays in the operating model.", 30),
            ],
        ),
        _otype(
            "customer_group", "Customer Group",
            "A meaningful group of customers or users with a shared relationship to the organisation or its services.", 120,
            [
                _attr("group_type", "Group type", "choice", "The broad kind of customer or user group.", 10,
                      choices=["Consumer", "Business", "Internal user", "Community", "Other"]),
                _attr("needs", "Needs", "text", "The principal needs or expectations represented by the group.", 20),
                _attr("importance", "Importance", "choice", "The relative importance of the group to the organisation.", 30,
                      choices=["Supporting", "Important", "Strategic"]),
            ],
        ),
        _otype(
            "resource", "Operational Resource",
            "A physical, financial, technical or other resource required to perform or support business operations.", 130,
            [
                _attr("resource_type", "Resource type", "choice", "The broad kind of operational resource.", 10,
                      choices=["Physical", "Financial", "Technology", "Capacity", "External", "Other"]),
                _attr("availability", "Availability", "choice", "The current availability of the resource.", 20,
                      choices=["Available", "Constrained", "Unavailable", "Planned"]),
                _attr("criticality", "Criticality", "choice", "The operational importance of the resource.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("purpose", "Purpose", "text", "The role the resource plays in operations.", 40),
            ],
        ),
        _otype(
            "policy", "Policy / Standard",
            "A policy, standard, principle or rule that governs how the organisation or its work should operate.", 140,
            [
                _attr("policy_type", "Policy type", "choice", "The broad kind of governance artefact.", 10,
                      choices=["Policy", "Standard", "Principle", "Rule", "Procedure", "Other"]),
                _attr("status", "Status", "choice", "The current status of the policy or standard.", 20,
                      choices=["Draft", "Current", "Under review", "Retired"]),
                _attr("scope", "Scope", "text", "The business area or activity governed by the policy or standard.", 30),
                _attr("purpose", "Purpose", "text", "The behaviour or outcome the policy or standard is intended to govern.", 40),
            ],
        ),
        _otype(
            "decision", "Decision",
            "A material choice or determination that changes, directs or constrains how the organisation operates.", 150,
            [
                _attr("decision_type", "Decision type", "choice", "The broad nature of the decision.", 10,
                      choices=["Strategic", "Operational", "Investment", "Risk", "Design", "Other"]),
                _attr("status", "Status", "choice", "The current state of the decision.", 20,
                      choices=["Proposed", "Made", "Under review", "Reversed"]),
                _attr("decision_date", "Decision date", "text", "The date on which the decision was made or is expected to be made.", 30),
                _attr("rationale", "Rationale", "text", "The key reason or consideration behind the decision.", 40),
            ],
        ),
        _otype(
            "event", "Business Event",
            "A meaningful occurrence that triggers, changes or materially affects business activity or operating conditions.", 160,
            [
                _attr("event_type", "Event type", "choice", "The broad kind of business event.", 10,
                      choices=["Customer", "Operational", "Technology", "External", "Regulatory", "Other"]),
                _attr("status", "Status", "choice", "The current state of the event.", 20,
                      choices=["Expected", "Occurred", "Ongoing", "Resolved"]),
                _attr("timing", "Timing", "text", "When the event occurs or is expected to occur.", 30),
            ],
        ),
        _otype(
            "risk", "Operational Risk",
            "A condition or event that could prevent the organisation, process, service or capability from achieving its intended result.", 170,
            [
                _attr("category", "Category", "choice", "The broad category of the risk.", 10,
                      choices=["Operational", "Customer", "Technology", "People", "Financial", "Third party", "Regulatory", "Strategic"]),
                _attr("status", "Status", "choice", "The current management status of the risk.", 20,
                      choices=["Open", "Monitored", "Mitigated", "Accepted", "Closed"]),
                _attr("severity", "Severity", "choice", "The potential significance if the risk materialises.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("description", "Description", "text", "The practical effect the risk could have on the operating model.", 40),
            ],
        ),
        _otype(
            "outcome", "Business Outcome",
            "A meaningful result the organisation seeks to achieve through its capabilities, services and operations.", 180,
            [
                _attr("outcome_type", "Outcome type", "choice", "The broad type of outcome.", 10,
                      choices=["Customer", "Operational", "Financial", "People", "Strategic", "Other"]),
                _attr("status", "Status", "choice", "The current position against the desired outcome.", 20,
                      choices=["Planned", "On track", "Watch", "At risk", "Achieved"]),
                _attr("description", "Description", "text", "The result the organisation is trying to achieve.", 30),
            ],
        ),
        _otype(
            "measure", "Measure",
            "A defined measure used to understand performance, capacity, quality, cost, risk or progress.", 190,
            [
                _attr("measure_type", "Measure type", "choice", "The broad purpose of the measure.", 10,
                      choices=["Performance", "Quality", "Cost", "Capacity", "Customer", "Risk", "Progress"]),
                _attr("frequency", "Frequency", "text", "How often the measure is collected or reviewed.", 20),
                _attr("direction", "Direction", "choice", "The intended direction of improvement where meaningful.", 30,
                      choices=["Higher is better", "Lower is better", "Target range", "Informational"]),
                _attr("purpose", "Purpose", "text", "What decision, assessment or understanding the measure supports.", 40),
            ],
        ),
    ],

    "relationship_types": [
        _rtype("contains", "Contains", "Indicates that one organisational element contains or comprises another structural element.", 10, [
            _rule("organisation", "business_unit", 1, None, 0, None),
            _rule("business_unit", "team", 0, None, 0, 1),
        ]),
        _rtype("part_of", "Part of", "Indicates that an element forms part of a broader organisational, capability or service context.", 20, [
            _rule("capability", "business_unit", 0, 1, 0, None),
            _rule("process", "capability", 0, None, 0, None),
            _rule("operational_activity", "process", 1, 1, 0, None),
            _rule("team", "business_unit", 0, 1, 0, None),
        ]),
        _rtype("owned_by", "Owned by", "Indicates which organisational unit, team or person has ownership or accountability for an element.", 30, [
            _rule("capability", "business_unit", 0, 1, 0, None),
            _rule("process", "business_unit", 0, 1, 0, None),
            _rule("service", "team", 0, 1, 0, None),
            _rule("application", "team", 0, 1, 0, None),
            _rule("policy", "team", 0, 1, 0, None),
            _rule("risk", "person", 0, 1, 0, None),
            _rule("measure", "team", 0, 1, 0, None),
        ]),
        _rtype("supports", "Supports", "Indicates that a capability, application, resource or service enables another part of the operating model.", 40, [
            _rule("capability", "process", 0, None, 0, None),
            _rule("application", "process", 0, None, 0, None),
            _rule("resource", "process", 0, None, 0, None),
            _rule("service", "process", 0, None, 0, None),
        ]),
        _rtype("realised_by", "Realised by", "Indicates how an organisational capability is put into practice through processes, services or activities.", 50, [
            _rule("capability", "process", 0, None, 0, None),
            _rule("capability", "service", 0, None, 0, None),
        ]),
        _rtype("includes", "Includes", "Indicates that a process or service consists of one or more operational activities.", 60, [
            _rule("process", "operational_activity", 0, None, 1, 1),
            _rule("service", "operational_activity", 0, None, 0, None),
        ]),
        _rtype("performed_by", "Performed by", "Indicates the person or team responsible for carrying out an operational activity.", 70, [
            _rule("operational_activity", "person", 0, 1, 0, None),
            _rule("operational_activity", "team", 0, 1, 0, None),
        ]),
        _rtype("member_of", "Member of", "Indicates that a person belongs to or works within a team.", 80, [
            _rule("person", "team", 0, None, 0, None),
        ]),
        _rtype("uses", "Uses", "Indicates that an activity, process or service uses an application, information or operational resource.", 90, [
            _rule("operational_activity", "application", 0, None, 0, None),
            _rule("operational_activity", "information", 0, None, 0, None),
            _rule("operational_activity", "resource", 0, None, 0, None),
            _rule("process", "application", 0, None, 0, None),
            _rule("process", "information", 0, None, 0, None),
            _rule("process", "resource", 0, None, 0, None),
            _rule("service", "application", 0, None, 0, None),
        ]),
        _rtype("produces", "Produces", "Indicates that a process or activity produces a service, information or meaningful operating result.", 100, [
            _rule("process", "service", 0, None, 0, None),
            _rule("process", "information", 0, None, 0, None),
            _rule("operational_activity", "information", 0, None, 0, None),
            _rule("operational_activity", "service", 0, None, 0, None),
        ]),
        _rtype("serves", "Serves", "Indicates which customer or user group receives or relies on a service.", 110, [
            _rule("service", "customer_group", 0, None, 0, None),
        ]),
        _rtype("supplied_by", "Supplied by", "Indicates that a service, application or resource is provided by an external supplier or partner.", 120, [
            _rule("service", "supplier", 0, 1, 0, None),
            _rule("application", "supplier", 0, 1, 0, None),
            _rule("resource", "supplier", 0, 1, 0, None),
        ]),
        _rtype("governed_by", "Governed by", "Indicates that an element operates under a policy, standard, principle or rule.", 130, [
            _rule("capability", "policy", 0, None, 0, None),
            _rule("process", "policy", 0, None, 0, None),
            _rule("operational_activity", "policy", 0, None, 0, None),
            _rule("service", "policy", 0, None, 0, None),
            _rule("application", "policy", 0, None, 0, None),
        ]),
        _rtype("triggered_by", "Triggered by", "Indicates that an event starts or materially changes a process or operational activity.", 140, [
            _rule("process", "event", 0, None, 0, None),
            _rule("operational_activity", "event", 0, None, 0, None),
            _rule("decision", "event", 0, None, 0, None),
        ]),
        _rtype("depends_on", "Depends on", "Indicates that an element relies on another element for successful operation or delivery.", 150, [
            _rule("process", "process", 0, None, 0, None),
            _rule("service", "service", 0, None, 0, None),
            _rule("service", "application", 0, None, 0, None),
            _rule("application", "application", 0, None, 0, None),
            _rule("process", "resource", 0, None, 0, None),
        ]),
        _rtype("measured_by", "Measured by", "Indicates which measures are used to understand performance, quality, capacity, risk or progress.", 160, [
            _rule("capability", "measure", 0, None, 0, None),
            _rule("process", "measure", 0, None, 0, None),
            _rule("service", "measure", 0, None, 0, None),
            _rule("outcome", "measure", 0, None, 0, None),
            _rule("application", "measure", 0, None, 0, None),
        ]),
        _rtype("evidenced_by", "Evidenced by", "Indicates that information provides evidence or context for an element in the operating model.", 170, [
            _rule("process", "information", 0, None, 0, None),
            _rule("capability", "information", 0, None, 0, None),
            _rule("outcome", "information", 0, None, 0, None),
            _rule("risk", "information", 0, None, 0, None),
            _rule("decision", "information", 0, None, 0, None),
        ]),
        _rtype("impacts", "Impacts", "Indicates that a risk could negatively affect an element of the operating model or desired outcome.", 180, [
            _rule("risk", "capability", 0, None, 0, None),
            _rule("risk", "process", 0, None, 0, None),
            _rule("risk", "service", 0, None, 0, None),
            _rule("risk", "application", 0, None, 0, None),
            _rule("risk", "outcome", 0, None, 0, None),
        ]),
        _rtype("mitigates", "Mitigates", "Indicates that a process or operational activity is intended to reduce or manage a risk.", 190, [
            _rule("process", "risk", 0, None, 0, None),
            _rule("operational_activity", "risk", 0, None, 0, None),
            _rule("service", "risk", 0, None, 0, None),
        ]),
        _rtype("affects", "Affects", "Indicates that a business event materially changes an operating element or condition.", 200, [
            _rule("event", "capability", 0, None, 0, None),
            _rule("event", "process", 0, None, 0, None),
            _rule("event", "service", 0, None, 0, None),
            _rule("event", "resource", 0, None, 0, None),
        ]),
        _rtype("made_by", "Made by", "Indicates which person or team makes or owns a decision.", 210, [
            _rule("decision", "person", 0, 1, 0, None),
            _rule("decision", "team", 0, 1, 0, None),
        ]),
        _rtype("addresses", "Addresses", "Indicates that a decision is intended to address a risk, issue or desired outcome.", 220, [
            _rule("decision", "risk", 0, None, 0, None),
            _rule("decision", "outcome", 0, None, 0, None),
        ]),
        _rtype("leads_to", "Leads to", "Indicates that a decision changes, initiates or directs a process, activity or outcome.", 230, [
            _rule("decision", "process", 0, None, 0, None),
            _rule("decision", "operational_activity", 0, None, 0, None),
            _rule("decision", "outcome", 0, None, 0, None),
        ]),
        _rtype("supports_outcome", "Supports outcome", "Indicates that a capability, process, service or activity contributes to a desired business outcome.", 240, [
            _rule("capability", "outcome", 0, None, 0, None),
            _rule("process", "outcome", 0, None, 0, None),
            _rule("service", "outcome", 0, None, 0, None),
            _rule("operational_activity", "outcome", 0, None, 0, None),
        ]),
        _rtype("responsible_for", "Responsible for", "Indicates that a person or team has operational responsibility for an element.", 250, [
            _rule("person", "process", 0, None, 0, None),
            _rule("person", "capability", 0, None, 0, None),
            _rule("team", "process", 0, None, 0, None),
            _rule("team", "capability", 0, None, 0, None),
            _rule("team", "service", 0, None, 0, None),
            _rule("team", "application", 0, None, 0, None),
        ]),
    ],

    # Deliberately no sample data: this is a genuine starting-point template.
    "objects": [],
    "relationships": [],

    "appearance": {
        "object_types": {
            "organisation": {"shape": "hexagon", "icon": "building", "background": "#EEF1F4", "border": "#6B7280", "font_colour": "#25313C", "font_weight": "bold"},
            "business_unit": {"shape": "box", "icon": "folder", "background": "#F3F0FF", "border": "#7950F2", "font_colour": "#342E52"},
            "capability": {"shape": "box", "icon": "cube", "background": "#EDE9FE", "border": "#7C5CFC", "font_colour": "#342A56", "font_weight": "bold"},
            "process": {"shape": "ellipse", "icon": "process", "background": "#E7F5FF", "border": "#4C8FBF", "font_colour": "#24465E"},
            "operational_activity": {"shape": "box", "icon": "task", "background": "#EEF4FB", "border": "#6B8FB4", "font_colour": "#2E4358"},
            "service": {"shape": "box", "icon": "product", "background": "#E8F5E9", "border": "#4F9564", "font_colour": "#284C32"},
            "person": {"shape": "ellipse", "icon": "person", "background": "#F7ECFA", "border": "#A85CC2", "font_colour": "#4E315A"},
            "team": {"shape": "ellipse", "icon": "team", "background": "#E8F1FB", "border": "#5681AD", "font_colour": "#29445F"},
            "application": {"shape": "box", "icon": "application", "background": "#EAF0FF", "border": "#637BC2", "font_colour": "#303F67"},
            "information": {"shape": "box", "icon": "document", "background": "#FFF8E1", "border": "#B58B34", "font_colour": "#5D491D"},
            "supplier": {"shape": "box", "icon": "store", "background": "#FFF0E1", "border": "#C88345", "font_colour": "#5D3D25"},
            "customer_group": {"shape": "ellipse", "icon": "team", "background": "#FDECEF", "border": "#C76B7F", "font_colour": "#5A303A"},
            "resource": {"shape": "box", "icon": "server", "background": "#EEF2F4", "border": "#71808B", "font_colour": "#34414A"},
            "policy": {"shape": "hexagon", "icon": "shield", "background": "#EAF6EE", "border": "#4E8D63", "font_colour": "#294B34"},
            "decision": {"shape": "diamond", "icon": "decision", "background": "#FFF2E2", "border": "#C47A2C", "font_colour": "#5C3B1B", "font_weight": "bold"},
            "event": {"shape": "ellipse", "icon": "event", "background": "#EAF5FC", "border": "#4C90B9", "font_colour": "#29485A"},
            "risk": {"shape": "diamond", "icon": "warning", "background": "#FBEAEA", "border": "#C65B5B", "font_colour": "#5E2C2C", "font_weight": "bold"},
            "outcome": {"shape": "star", "icon": "target", "background": "#E8F7F3", "border": "#429B87", "font_colour": "#245047", "font_weight": "bold"},
            "measure": {"shape": "box", "icon": "chart", "background": "#F2EEFF", "border": "#8063B8", "font_colour": "#40345F"},
        },
        "relationship_types": {
            "contains": {"colour": "#6C757D", "width": 1.5, "line_style": "solid"},
            "part_of": {"colour": "#868E96", "width": 1.5, "line_style": "solid"},
            "owned_by": {"colour": "#495057", "width": 1.5, "line_style": "solid"},
            "supports": {"colour": "#2F7D62", "width": 1.7, "line_style": "solid"},
            "realised_by": {"colour": "#5F3DC4", "width": 1.7, "line_style": "solid"},
            "includes": {"colour": "#4C78A8", "width": 1.5, "line_style": "solid"},
            "performed_by": {"colour": "#3E6C99", "width": 1.5, "line_style": "solid"},
            "member_of": {"colour": "#868E96", "width": 1.4, "line_style": "solid"},
            "uses": {"colour": "#6C5AA8", "width": 1.5, "line_style": "solid"},
            "produces": {"colour": "#27815B", "width": 1.6, "line_style": "solid"},
            "serves": {"colour": "#B04F6B", "width": 1.5, "line_style": "solid"},
            "supplied_by": {"colour": "#A56835", "width": 1.5, "line_style": "dashed"},
            "governed_by": {"colour": "#3F7953", "width": 1.6, "line_style": "dashed"},
            "triggered_by": {"colour": "#3D7EA6", "width": 1.5, "line_style": "dashed"},
            "depends_on": {"colour": "#A54B4B", "width": 1.6, "line_style": "dashed"},
            "measured_by": {"colour": "#72549A", "width": 1.5, "line_style": "dotted"},
            "evidenced_by": {"colour": "#72549A", "width": 1.5, "line_style": "dotted"},
            "impacts": {"colour": "#B43F3F", "width": 1.6, "line_style": "dashed"},
            "mitigates": {"colour": "#34855D", "width": 1.6, "line_style": "dashed"},
            "affects": {"colour": "#B56A2F", "width": 1.5, "line_style": "dashed"},
            "made_by": {"colour": "#7B5A30", "width": 1.5, "line_style": "solid"},
            "addresses": {"colour": "#9A4F4F", "width": 1.5, "line_style": "dashed"},
            "leads_to": {"colour": "#7658A8", "width": 1.6, "line_style": "solid"},
            "supports_outcome": {"colour": "#24806A", "width": 1.7, "line_style": "solid"},
            "responsible_for": {"colour": "#355F87", "width": 1.5, "line_style": "solid"},
        },
    },
}

# Convenient alias for callers that use the naming convention of other templates.
BUSINESS_OPERATIONS = BUSINESS_OPERATIONS_TEMPLATE

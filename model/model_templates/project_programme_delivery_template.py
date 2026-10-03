"""Project / Programme Delivery model template.

A blank, reusable starting-point model for understanding delivery work as a
connected system. The template is deliberately delivery-focused rather than a
simple task tracker: it connects programmes and projects to outcomes, scope,
workstreams, deliverables, requirements, tasks, milestones, people, teams,
stakeholders, suppliers, dependencies, decisions, risks, issues, change,
evidence, measures and funding.

The template contains no sample objects or relationships. It is intended as a
genuine starting point that a delivery team can extend for a project, programme
or change initiative of its own.

The template is declarative. Template instantiation services are responsible for
turning the definition into database records.
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


PROJECT_PROGRAMME_DELIVERY_TEMPLATE = {
    "key": "project_programme_delivery",
    "name": "Project / Programme Delivery",
    "description": (
        "A reusable starting point for modelling delivery work as a connected system. "
        "The model links programmes and projects to intended outcomes, scope, workstreams, "
        "deliverables, requirements, tasks, milestones, people, teams, stakeholders, suppliers, "
        "dependencies, decisions, risks, issues, change, evidence, measures and funding."
    ),

    "object_types": [
        _otype(
            "programme", "Programme",
            "A coordinated body of related projects and change work managed together to achieve a broader outcome or set of outcomes.", 10,
            [
                _attr("programme_type", "Programme type", "choice", "The broad nature of the programme.", 10,
                      choices=["Transformation", "Business change", "Technology", "Regulatory", "Operational", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the programme.", 20,
                      choices=["Proposed", "Active", "Paused", "Closing", "Closed"]),
                _attr("priority", "Priority", "choice", "The relative delivery priority of the programme.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("purpose", "Purpose", "text", "Why the programme exists and the change it is intended to coordinate.", 40),
            ],
        ),
        _otype(
            "project", "Project",
            "A defined delivery initiative with a clear purpose, scope, timeframe and accountable ownership.", 20,
            [
                _attr("project_type", "Project type", "choice", "The broad kind of project.", 10,
                      choices=["Business change", "Technology", "Product", "Regulatory", "Process improvement", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the project.", 20,
                      choices=["Proposed", "Initiating", "Delivery", "Transition", "Closing", "Closed"]),
                _attr("priority", "Priority", "choice", "The relative delivery priority of the project.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("start_date", "Start date", "date", "Planned or actual project start date.", 40),
                _attr("target_end_date", "Target end date", "date", "Planned target completion date.", 50),
                _attr("purpose", "Purpose", "text", "Why the project exists and what change it is intended to deliver.", 60),
            ],
        ),
        _otype(
            "outcome", "Outcome",
            "A meaningful business or customer result that the delivery effort exists to achieve or materially improve.", 30,
            [
                _attr("outcome_type", "Outcome type", "choice", "The broad kind of intended outcome.", 10,
                      choices=["Customer", "Business", "Operational", "Financial", "Risk", "Regulatory", "Technology", "Other"]),
                _attr("status", "Status", "choice", "The current position against the intended outcome.", 20,
                      choices=["Proposed", "On track", "Watch", "At risk", "Achieved"]),
                _attr("description", "Description", "text", "The measurable or observable result the delivery effort seeks to achieve.", 30),
            ],
        ),
        _otype(
            "scope_item", "Scope Item",
            "A defined area of change or responsibility that establishes what the project or programme will address.", 40,
            [
                _attr("scope_type", "Scope type", "choice", "The broad kind of scope item.", 10,
                      choices=["Business area", "Capability", "Process", "Product", "Technology", "Data", "Other"]),
                _attr("status", "Status", "choice", "The current position of the scope item.", 20,
                      choices=["Candidate", "In scope", "Deferred", "Out of scope", "Complete"]),
                _attr("description", "Description", "text", "What is included, changed or explicitly bounded by the scope item.", 30),
            ],
        ),
        _otype(
            "workstream", "Workstream",
            "A coherent stream of delivery activity grouped around a common area of change, responsibility or expertise.", 50,
            [
                _attr("workstream_type", "Workstream type", "choice", "The broad nature of the workstream.", 10,
                      choices=["Business", "Technology", "Data", "Change", "Testing", "Transition", "Other"]),
                _attr("status", "Status", "choice", "The current state of the workstream.", 20,
                      choices=["Planned", "Active", "At risk", "Complete", "Paused"]),
                _attr("purpose", "Purpose", "text", "What the workstream is responsible for delivering.", 30),
            ],
        ),
        _otype(
            "deliverable", "Deliverable",
            "A defined product, capability, change, document or other tangible result that the delivery effort is expected to produce.", 60,
            [
                _attr("deliverable_type", "Deliverable type", "choice", "The broad kind of deliverable.", 10,
                      choices=["Product", "Capability", "Process", "System", "Document", "Release", "Training", "Other"]),
                _attr("status", "Status", "choice", "The current state of the deliverable.", 20,
                      choices=["Planned", "In progress", "Ready for review", "Accepted", "Deferred", "Cancelled"]),
                _attr("quality_status", "Quality status", "choice", "The current confidence in the deliverable meeting expectations.", 30,
                      choices=["Not assessed", "On track", "Needs attention", "Accepted"]),
                _attr("acceptance_criteria", "Acceptance criteria", "text", "The main conditions that must be met for acceptance.", 40),
            ],
        ),
        _otype(
            "requirement", "Requirement",
            "A defined need, condition or capability that the delivery effort must satisfy.", 70,
            [
                _attr("requirement_type", "Requirement type", "choice", "The broad kind of requirement.", 10,
                      choices=["Business", "Functional", "Non-functional", "Data", "Regulatory", "Technical", "Other"]),
                _attr("priority", "Priority", "choice", "The relative priority of the requirement.", 20,
                      choices=["Must", "Should", "Could", "Deferred"]),
                _attr("status", "Status", "choice", "The current state of the requirement.", 30,
                      choices=["Proposed", "Approved", "In delivery", "Satisfied", "Rejected"]),
                _attr("description", "Description", "text", "The need or condition that the requirement represents.", 40),
            ],
        ),
        _otype(
            "task", "Task",
            "A unit of work that contributes to a deliverable, workstream or other delivery result.", 80,
            [
                _attr("status", "Status", "choice", "The current state of the task.", 10,
                      choices=["Not started", "In progress", "Blocked", "Complete", "Cancelled"]),
                _attr("priority", "Priority", "choice", "The relative priority of the task.", 20,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("start_date", "Start date", "date", "Planned or actual task start date.", 30),
                _attr("due_date", "Due date", "date", "Target task completion date.", 40),
                _attr("description", "Description", "text", "The work to be performed and the intended result.", 50),
            ],
        ),
        _otype(
            "milestone", "Milestone",
            "A significant point in delivery that marks a decision, handoff, achievement or planned checkpoint.", 90,
            [
                _attr("milestone_type", "Milestone type", "choice", "The broad kind of milestone.", 10,
                      choices=["Decision", "Delivery", "Approval", "Transition", "Review", "Go-live", "Other"]),
                _attr("status", "Status", "choice", "The current position of the milestone.", 20,
                      choices=["Planned", "At risk", "Achieved", "Missed", "Cancelled"]),
                _attr("target_date", "Target date", "date", "Planned milestone date.", 30),
            ],
        ),
        _otype(
            "person", "Person",
            "An individual who owns, performs, approves, contributes to or is affected by delivery work.", 100,
            [
                _attr("role", "Role", "text", "The person's role in the delivery context.", 10),
                _attr("responsibility", "Responsibility", "text", "The person's principal delivery responsibility.", 20),
            ],
        ),
        _otype(
            "team", "Team",
            "A group accountable for a coherent area of delivery work, governance or specialist support.", 110,
            [
                _attr("team_type", "Team type", "choice", "The broad role of the team.", 10,
                      choices=["Delivery", "Business", "Technology", "Change", "Governance", "Supplier", "Other"]),
                _attr("responsibility", "Responsibility", "text", "The team's principal delivery responsibility.", 20),
            ],
        ),
        _otype(
            "stakeholder", "Stakeholder",
            "A person, group or organisational party with a material interest in, influence over or exposure to delivery outcomes.", 120,
            [
                _attr("stakeholder_type", "Stakeholder type", "choice", "The broad kind of stakeholder.", 10,
                      choices=["Customer", "Executive", "Business owner", "Regulator", "Partner", "Supplier", "Community", "Other"]),
                _attr("interest", "Interest", "text", "What the stakeholder cares about or needs from the delivery effort.", 20),
                _attr("influence", "Influence", "choice", "The stakeholder's ability to affect delivery decisions or outcomes.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
            ],
        ),
        _otype(
            "supplier", "Supplier",
            "An external organisation that provides products, services, expertise or delivery capacity to the project or programme.", 130,
            [
                _attr("supplier_type", "Supplier type", "choice", "The broad role of the supplier.", 10,
                      choices=["Technology", "Professional services", "Product", "Delivery partner", "Other"]),
                _attr("relationship_status", "Relationship status", "choice", "The current commercial or operating relationship.", 20,
                      choices=["Prospective", "Current", "Preferred", "Exiting"]),
                _attr("purpose", "Purpose", "text", "The role the supplier plays in delivery.", 30),
            ],
        ),
        _otype(
            "dependency", "Dependency",
            "A reliance on another project, workstream, decision, supplier, capability, system or external condition for delivery to proceed.", 140,
            [
                _attr("dependency_type", "Dependency type", "choice", "The broad kind of dependency.", 10,
                      choices=["Project", "Workstream", "Supplier", "Decision", "Technology", "Business", "External", "Other"]),
                _attr("status", "Status", "choice", "The current state of the dependency.", 20,
                      choices=["Identified", "Active", "At risk", "Resolved"]),
                _attr("description", "Description", "text", "What the delivery effort relies on and what happens if it is unavailable.", 30),
            ],
        ),
        _otype(
            "decision", "Decision",
            "A material delivery choice that determines direction, scope, sequencing, design or treatment of an issue.", 150,
            [
                _attr("decision_type", "Decision type", "choice", "The broad kind of delivery decision.", 10,
                      choices=["Scope", "Design", "Priority", "Funding", "Sequence", "Exception", "Other"]),
                _attr("status", "Status", "choice", "The current state of the decision.", 20,
                      choices=["Open", "Under review", "Decided", "Revisited", "Closed"]),
                _attr("decision_date", "Decision date", "date", "Date the decision was or is expected to be made.", 30),
                _attr("rationale", "Rationale", "text", "The principal reasoning or evidence supporting the decision.", 40),
            ],
        ),
        _otype(
            "risk", "Risk",
            "A potential event or condition that could affect delivery scope, time, cost, quality, outcomes or stakeholder confidence.", 160,
            [
                _attr("category", "Category", "choice", "The broad category of the delivery risk.", 10,
                      choices=["Scope", "Schedule", "Cost", "Quality", "Technology", "People", "Supplier", "External", "Other"]),
                _attr("status", "Status", "choice", "The current management state of the risk.", 20,
                      choices=["Open", "Monitored", "Mitigated", "Accepted", "Closed"]),
                _attr("severity", "Severity", "choice", "The potential impact if the risk materialises.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("description", "Description", "text", "The practical effect the risk could have on delivery.", 40),
            ],
        ),
        _otype(
            "issue", "Issue",
            "A known problem, exception or condition that is already affecting or may directly impede delivery.", 170,
            [
                _attr("category", "Category", "choice", "The broad category of the issue.", 10,
                      choices=["Scope", "Schedule", "Cost", "Quality", "Technology", "People", "Supplier", "Other"]),
                _attr("status", "Status", "choice", "The current management state of the issue.", 20,
                      choices=["Open", "Being resolved", "Escalated", "Resolved", "Closed"]),
                _attr("severity", "Severity", "choice", "The current impact or urgency of the issue.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("description", "Description", "text", "What is happening and why it matters to delivery.", 40),
            ],
        ),
        _otype(
            "change_request", "Change Request",
            "A proposed change to agreed scope, requirements, deliverables, sequencing or another controlled part of the delivery baseline.", 180,
            [
                _attr("change_type", "Change type", "choice", "The broad kind of requested change.", 10,
                      choices=["Scope", "Requirement", "Schedule", "Budget", "Design", "Resource", "Other"]),
                _attr("status", "Status", "choice", "The current state of the change request.", 20,
                      choices=["Proposed", "Under assessment", "Approved", "Rejected", "Implemented", "Withdrawn"]),
                _attr("impact", "Impact", "choice", "The expected delivery impact of the change.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("description", "Description", "text", "What is being proposed and why the change is needed.", 40),
            ],
        ),
        _otype(
            "document", "Delivery Document",
            "A plan, decision record, status report, design, business case or other information artifact used to govern or evidence delivery.", 190,
            [
                _attr("document_type", "Document type", "choice", "The broad kind of delivery document.", 10,
                      choices=["Business case", "Plan", "Status report", "Decision record", "Design", "Requirement", "Contract", "Other"]),
                _attr("status", "Status", "choice", "The current status of the document.", 20,
                      choices=["Draft", "Current", "Under review", "Superseded", "Archived"]),
                _attr("purpose", "Purpose", "text", "What the document is used to support, communicate or evidence.", 30),
            ],
        ),
        _otype(
            "measure", "Delivery Measure",
            "A metric, indicator or measure used to understand delivery progress, health, quality, value or outcome performance.", 200,
            [
                _attr("measure_type", "Measure type", "choice", "The broad purpose of the measure.", 10,
                      choices=["Progress", "Schedule", "Cost", "Quality", "Value", "Outcome", "Risk", "Other"]),
                _attr("status", "Status", "choice", "The current interpretation of the measure.", 20,
                      choices=["On target", "Watch", "At risk", "Off target"]),
                _attr("definition", "Definition", "text", "What is measured and how the measure should be interpreted.", 30),
            ],
        ),
        _otype(
            "budget", "Budget / Funding", 
            "A defined allocation of funding or financial capacity associated with delivery work.", 210,
            [
                _attr("funding_type", "Funding type", "choice", "The broad kind of funding represented.", 10,
                      choices=["Capital", "Operating", "Programme", "Project", "Supplier", "Other"]),
                _attr("status", "Status", "choice", "The current state of the funding allocation.", 20,
                      choices=["Proposed", "Approved", "Committed", "Under review", "Closed"]),
                _attr("amount", "Amount", "text", "The amount or financial envelope represented by the budget or funding item.", 30),
                _attr("purpose", "Purpose", "text", "What the funding is intended to support.", 40),
            ],
        ),
    ],

    "relationship_types": [
        _rtype("contains_project", "Contains project", "Indicates that a project forms part of a programme.", 10, [
            _rule("programme", "project", 0, None, 0, 1),
        ]),
        _rtype("seeks_outcome", "Seeks outcome", "Indicates that a programme or project exists to achieve an intended outcome.", 20, [
            _rule("programme", "outcome", 0, None, 0, None),
            _rule("project", "outcome", 0, None, 0, None),
        ]),
        _rtype("defines_scope", "Defines scope", "Indicates that a programme or project establishes an area of delivery scope.", 30, [
            _rule("programme", "scope_item", 0, None, 0, None),
            _rule("project", "scope_item", 0, None, 0, None),
        ]),
        _rtype("contains_workstream", "Contains workstream", "Indicates that a programme or project contains a coherent workstream.", 40, [
            _rule("programme", "workstream", 0, None, 0, None),
            _rule("project", "workstream", 0, None, 0, None),
        ]),
        _rtype("delivers", "Delivers", "Indicates that a project or workstream is responsible for a deliverable.", 50, [
            _rule("project", "deliverable", 0, None, 0, None),
            _rule("workstream", "deliverable", 0, None, 0, None),
        ]),
        _rtype("satisfies", "Satisfies", "Indicates that a deliverable is intended to satisfy a requirement.", 60, [
            _rule("deliverable", "requirement", 0, None, 0, None),
        ]),
        _rtype("breaks_down_to", "Breaks down to", "Indicates that a workstream or deliverable is decomposed into tasks or that scope is refined into workstreams.", 70, [
            _rule("workstream", "task", 0, None, 0, None),
            _rule("deliverable", "task", 0, None, 0, None),
            _rule("scope_item", "workstream", 0, None, 0, None),
        ]),
        _rtype("assigned_to", "Assigned to", "Indicates who is responsible for carrying out a task or workstream.", 80, [
            _rule("task", "person", 0, 1, 0, None),
            _rule("task", "team", 0, 1, 0, None),
            _rule("workstream", "person", 0, 1, 0, None),
            _rule("workstream", "team", 0, 1, 0, None),
        ]),
        _rtype("has_milestone", "Has milestone", "Indicates that a programme, project or workstream is measured or governed through a milestone.", 90, [
            _rule("programme", "milestone", 0, None, 0, None),
            _rule("project", "milestone", 0, None, 0, None),
            _rule("workstream", "milestone", 0, None, 0, None),
        ]),
        _rtype("owned_by", "Owned by", "Indicates the person or team accountable for a programme, project, deliverable or outcome.", 100, [
            _rule("programme", "person", 0, 1, 0, None),
            _rule("programme", "team", 0, 1, 0, None),
            _rule("project", "person", 0, 1, 0, None),
            _rule("project", "team", 0, 1, 0, None),
            _rule("deliverable", "person", 0, 1, 0, None),
            _rule("deliverable", "team", 0, 1, 0, None),
            _rule("outcome", "person", 0, 1, 0, None),
            _rule("outcome", "team", 0, 1, 0, None),
        ]),
        _rtype("involves", "Involves", "Indicates that a stakeholder or supplier has a material role in the delivery effort.", 110, [
            _rule("programme", "stakeholder", 0, None, 0, None),
            _rule("project", "stakeholder", 0, None, 0, None),
            _rule("programme", "supplier", 0, None, 0, None),
            _rule("project", "supplier", 0, None, 0, None),
        ]),
        _rtype("depends_on", "Depends on", "Indicates that delivery relies on another dependency being available or resolved.", 120, [
            _rule("programme", "dependency", 0, None, 0, None),
            _rule("project", "dependency", 0, None, 0, None),
            _rule("workstream", "dependency", 0, None, 0, None),
            _rule("task", "dependency", 0, None, 0, None),
        ]),
        _rtype("blocks", "Blocks", "Indicates that an issue or dependency is preventing delivery from progressing as intended.", 130, [
            _rule("issue", "task", 0, None, 0, None),
            _rule("issue", "deliverable", 0, None, 0, None),
            _rule("dependency", "task", 0, None, 0, None),
            _rule("dependency", "deliverable", 0, None, 0, None),
        ]),
        _rtype("decides", "Decides", "Indicates that a decision determines the direction or treatment of a project, scope item, issue or change request.", 140, [
            _rule("decision", "project", 0, None, 0, None),
            _rule("decision", "scope_item", 0, None, 0, None),
            _rule("decision", "issue", 0, None, 0, None),
            _rule("decision", "change_request", 0, None, 0, None),
        ]),
        _rtype("affects", "Affects", "Indicates that a risk or issue may affect a delivery element or intended outcome.", 150, [
            _rule("risk", "project", 0, None, 0, None),
            _rule("risk", "workstream", 0, None, 0, None),
            _rule("risk", "deliverable", 0, None, 0, None),
            _rule("risk", "outcome", 0, None, 0, None),
            _rule("issue", "project", 0, None, 0, None),
            _rule("issue", "workstream", 0, None, 0, None),
            _rule("issue", "deliverable", 0, None, 0, None),
            _rule("issue", "outcome", 0, None, 0, None),
        ]),
        _rtype("mitigated_by", "Mitigated by", "Indicates that a risk is actively treated through a task, decision, change request or other delivery action.", 160, [
            _rule("risk", "task", 0, None, 0, None),
            _rule("risk", "decision", 0, None, 0, None),
            _rule("risk", "change_request", 0, None, 0, None),
        ]),
        _rtype("changes", "Changes", "Indicates that a change request proposes or causes a change to an agreed delivery element.", 170, [
            _rule("change_request", "scope_item", 0, None, 0, None),
            _rule("change_request", "requirement", 0, None, 0, None),
            _rule("change_request", "deliverable", 0, None, 0, None),
            _rule("change_request", "project", 0, 1, 0, None),
        ]),
        _rtype("evidenced_by", "Evidenced by", "Indicates that a delivery element, decision or outcome is supported or recorded by a document.", 180, [
            _rule("project", "document", 0, None, 0, None),
            _rule("decision", "document", 0, None, 0, None),
            _rule("deliverable", "document", 0, None, 0, None),
            _rule("outcome", "document", 0, None, 0, None),
            _rule("risk", "document", 0, None, 0, None),
        ]),
        _rtype("measured_by", "Measured by", "Indicates which measures are used to understand delivery progress, health, value or outcomes.", 190, [
            _rule("programme", "measure", 0, None, 0, None),
            _rule("project", "measure", 0, None, 0, None),
            _rule("workstream", "measure", 0, None, 0, None),
            _rule("outcome", "measure", 0, None, 0, None),
        ]),
        _rtype("funded_by", "Funded by", "Indicates the funding allocation supporting a programme, project or defined delivery work.", 200, [
            _rule("programme", "budget", 0, None, 0, None),
            _rule("project", "budget", 0, None, 0, None),
            _rule("workstream", "budget", 0, None, 0, None),
        ]),
        _rtype("precedes", "Precedes", "Indicates a delivery sequencing relationship where one item must occur before another.", 210, [
            _rule("task", "task", 0, None, 0, None),
            _rule("milestone", "milestone", 0, None, 0, None),
            _rule("workstream", "workstream", 0, None, 0, None),
        ]),
    ],

    # Deliberately no sample data: this is a genuine starting-point template.
    "objects": [],
    "relationships": [],

    "appearance": {
        "object_types": {
            "programme": {"shape": "hexagon", "icon": "building", "background": "#F0EBFA", "border": "#8064B4", "font_colour": "#493A61", "font_weight": "bold"},
            "project": {"shape": "hexagon", "icon": "flag", "background": "#EAF0FF", "border": "#637BC2", "font_colour": "#303F67", "font_weight": "bold"},
            "outcome": {"shape": "star", "icon": "target", "background": "#E8F7F3", "border": "#429B87", "font_colour": "#245047", "font_weight": "bold"},
            "scope_item": {"shape": "box", "icon": "cube", "background": "#F3EFFB", "border": "#8A75B7", "font_colour": "#4A3E62"},
            "workstream": {"shape": "ellipse", "icon": "process", "background": "#E9F6F4", "border": "#4D968A", "font_colour": "#294E49", "font_weight": "bold"},
            "deliverable": {"shape": "box", "icon": "product", "background": "#EEF3FF", "border": "#6E84C7", "font_colour": "#344368"},
            "requirement": {"shape": "box", "icon": "document", "background": "#FFF8E5", "border": "#B58E35", "font_colour": "#5E4A20"},
            "task": {"shape": "box", "icon": "task", "background": "#EEF5FB", "border": "#668EAE", "font_colour": "#304858"},
            "milestone": {"shape": "ellipse", "icon": "calendar", "background": "#FFF4DF", "border": "#B98A35", "font_colour": "#5B471F", "font_weight": "bold"},
            "person": {"shape": "ellipse", "icon": "person", "background": "#F8ECFA", "border": "#A85CC2", "font_colour": "#4E315A"},
            "team": {"shape": "ellipse", "icon": "team", "background": "#E9F0FB", "border": "#5A80AD", "font_colour": "#2D465F"},
            "stakeholder": {"shape": "ellipse", "icon": "person", "background": "#F3EEF8", "border": "#9075A8", "font_colour": "#4A3E52"},
            "supplier": {"shape": "box", "icon": "store", "background": "#FFF1E1", "border": "#C88345", "font_colour": "#5D3D25"},
            "dependency": {"shape": "ellipse", "icon": "network", "background": "#EEF2F6", "border": "#718397", "font_colour": "#3C4B59"},
            "decision": {"shape": "diamond", "icon": "decision", "background": "#FFF4DD", "border": "#B68632", "font_colour": "#58441E", "font_weight": "bold"},
            "risk": {"shape": "diamond", "icon": "warning", "background": "#FBEAEA", "border": "#C65B5B", "font_colour": "#5E2C2C", "font_weight": "bold"},
            "issue": {"shape": "diamond", "icon": "warning", "background": "#FFF0E5", "border": "#C77A42", "font_colour": "#5B3924", "font_weight": "bold"},
            "change_request": {"shape": "box", "icon": "event", "background": "#F2EEFF", "border": "#8063B8", "font_colour": "#40345F"},
            "document": {"shape": "box", "icon": "document", "background": "#F7F1FB", "border": "#9173A6", "font_colour": "#4A3C55"},
            "measure": {"shape": "box", "icon": "chart", "background": "#F2EEFF", "border": "#8063B8", "font_colour": "#40345F"},
            "budget": {"shape": "box", "icon": "money", "background": "#EDF7EF", "border": "#5B9669", "font_colour": "#2F5036"},
        },
        "relationship_types": {
            "contains_project": {"colour": "#66558F", "width": 1.7, "line_style": "solid"},
            "seeks_outcome": {"colour": "#24806A", "width": 1.7, "line_style": "solid"},
            "defines_scope": {"colour": "#77639D", "width": 1.5, "line_style": "solid"},
            "contains_workstream": {"colour": "#3E8179", "width": 1.6, "line_style": "solid"},
            "delivers": {"colour": "#3F699A", "width": 1.7, "line_style": "solid"},
            "satisfies": {"colour": "#9A7930", "width": 1.5, "line_style": "solid"},
            "breaks_down_to": {"colour": "#607487", "width": 1.5, "line_style": "solid"},
            "assigned_to": {"colour": "#355F87", "width": 1.5, "line_style": "dashed"},
            "has_milestone": {"colour": "#A77A2E", "width": 1.6, "line_style": "dashed"},
            "owned_by": {"colour": "#5E4A7D", "width": 1.5, "line_style": "solid"},
            "involves": {"colour": "#8A5B32", "width": 1.5, "line_style": "dashed"},
            "depends_on": {"colour": "#697787", "width": 1.6, "line_style": "dashed"},
            "blocks": {"colour": "#B44A3C", "width": 1.7, "line_style": "solid"},
            "decides": {"colour": "#A77729", "width": 1.6, "line_style": "solid"},
            "affects": {"colour": "#B43F3F", "width": 1.6, "line_style": "dashed"},
            "mitigated_by": {"colour": "#3F7E61", "width": 1.5, "line_style": "dashed"},
            "changes": {"colour": "#72549A", "width": 1.6, "line_style": "dashed"},
            "evidenced_by": {"colour": "#795D91", "width": 1.5, "line_style": "dotted"},
            "measured_by": {"colour": "#72549A", "width": 1.5, "line_style": "dotted"},
            "funded_by": {"colour": "#4F8057", "width": 1.5, "line_style": "dashed"},
            "precedes": {"colour": "#6A7684", "width": 1.7, "line_style": "solid"},
        },
    },
}

# Convenient alias for callers that use the shorter naming convention.
PROJECT_DELIVERY_TEMPLATE = PROJECT_PROGRAMME_DELIVERY_TEMPLATE

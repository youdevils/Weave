"""Process Context model template.

A blank, reusable starting-point model for understanding a process in its real
operating context. The template is deliberately process-centred rather than a
simple flowchart: it connects triggers, process steps, people, teams,
customers, applications, information, inputs, outputs, policies, decisions,
dependencies, measures, risks and outcomes.

The template contains no sample objects or relationships. It is intended as a
meaningful semantic starting point that a user can extend for their own process
or operating problem.

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


PROCESS_CONTEXT_TEMPLATE = {
    "key": "process_context",
    "name": "Process Context",
    "description": (
        "A reusable starting point for understanding a process in its real operating context. "
        "The model connects process steps, triggers, actors, customers, applications, information, "
        "inputs, outputs, policies, decisions, dependencies, risks, measures and outcomes so the "
        "process can be understood as part of the wider system around it."
    ),

    "object_types": [
        _otype(
            "process", "Process",
            "The end-to-end body of work being understood, including its purpose, boundary and operating context.", 10,
            [
                _attr("process_type", "Process type", "choice", "The broad nature of the process.", 10,
                      choices=["Customer-facing", "Operational", "Supporting", "Management", "Control"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the process.", 20,
                      choices=["Planned", "Current", "Under review", "Retiring"]),
                _attr("frequency", "Frequency", "text", "How often the process normally runs or is initiated.", 30),
                _attr("purpose", "Purpose", "text", "The business purpose the process exists to fulfil.", 40),
                _attr("boundary", "Boundary", "text", "What is explicitly inside and outside the process boundary.", 50),
            ],
        ),
        _otype(
            "process_step", "Process Step",
            "A meaningful unit of work within a process that has a distinct action, responsibility or result.", 20,
            [
                _attr("step_type", "Step type", "choice", "The broad kind of process step.", 10,
                      choices=["Activity", "Review", "Decision", "Approval", "Handover", "Communication", "Wait", "Other"]),
                _attr("purpose", "Purpose", "text", "The immediate purpose of the step within the process.", 20),
                _attr("status", "Status", "choice", "The current state of the step.", 30,
                      choices=["Current", "Planned", "Under review", "Retiring"]),
                _attr("timing", "Timing", "text", "Timing, service expectation or operating window for the step.", 40),
            ],
        ),
        _otype(
            "event", "Trigger / Event",
            "A meaningful occurrence that starts, interrupts, resumes or materially changes the process.", 30,
            [
                _attr("event_type", "Event type", "choice", "The broad kind of trigger or event.", 10,
                      choices=["Customer", "Business", "Operational", "System", "External", "Regulatory", "Time-based"]),
                _attr("timing", "Timing", "text", "When the event occurs or is expected to occur.", 20),
                _attr("description", "Description", "text", "What happens and why it matters to the process.", 30),
            ],
        ),
        _otype(
            "person", "Person",
            "An individual who performs, owns, approves, provides input to or is affected by process work.", 40,
            [
                _attr("role", "Role", "text", "The person's role in relation to the process.", 10),
                _attr("responsibility", "Responsibility", "text", "The person's principal responsibility within the process context.", 20),
            ],
        ),
        _otype(
            "team", "Team",
            "A group accountable for performing, supporting, governing or receiving work within the process.", 50,
            [
                _attr("team_type", "Team type", "choice", "The broad operating role of the team.", 10,
                      choices=["Operational", "Support", "Specialist", "Approval", "External", "Other"]),
                _attr("responsibility", "Responsibility", "text", "The team's main responsibility in the process.", 20),
                _attr("handoff_role", "Handoff role", "text", "The part the team plays when work is passed to or from it.", 30),
            ],
        ),
        _otype(
            "customer_group", "Customer / User Group",
            "A meaningful group of customers, users or recipients whose needs or interactions are part of the process context.", 60,
            [
                _attr("group_type", "Group type", "choice", "The broad kind of customer or user group.", 10,
                      choices=["Consumer", "Business", "Employee", "Partner", "Community", "Other"]),
                _attr("needs", "Needs", "text", "The principal needs or expectations represented by the group.", 20),
                _attr("interaction", "Interaction", "text", "How the group interacts with or experiences the process.", 30),
            ],
        ),
        _otype(
            "application", "Application",
            "A software application or digital system used by the process or affected by its outputs.", 70,
            [
                _attr("application_type", "Application type", "choice", "The broad kind of application.", 10,
                      choices=["SaaS", "Internal", "Platform", "Custom", "Legacy", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the application.", 20,
                      choices=["Planned", "Current", "Under review", "Retiring"]),
                _attr("criticality", "Criticality", "choice", "The operational importance of the application to the process.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("purpose", "Purpose", "text", "How the application supports the process.", 40),
            ],
        ),
        _otype(
            "information", "Information / Document",
            "A document, data set, record, instruction or other information used or produced by the process.", 80,
            [
                _attr("information_type", "Information type", "choice", "The broad kind of information represented.", 10,
                      choices=["Data", "Document", "Record", "Report", "Instruction", "Reference", "Other"]),
                _attr("sensitivity", "Sensitivity", "choice", "The general sensitivity of the information.", 20,
                      choices=["Public", "Internal", "Confidential", "Restricted"]),
                _attr("purpose", "Purpose", "text", "How the information is used within the process.", 30),
                _attr("source", "Source", "text", "Where the information originates or is maintained.", 40),
            ],
        ),
        _otype(
            "input", "Input / Resource",
            "A resource, item, information package, capacity or external input required to perform the process.", 90,
            [
                _attr("input_type", "Input type", "choice", "The broad kind of process input.", 10,
                      choices=["Information", "Material", "Capacity", "Funding", "Service", "Approval", "Other"]),
                _attr("availability", "Availability", "choice", "The current availability of the input or resource.", 20,
                      choices=["Available", "Constrained", "Unavailable", "Planned"]),
                _attr("criticality", "Criticality", "choice", "The importance of the input to successful process execution.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
            ],
        ),
        _otype(
            "output", "Output / Result",
            "A concrete output, handoff, record, service result or other result produced by the process.", 100,
            [
                _attr("output_type", "Output type", "choice", "The broad kind of process output.", 10,
                      choices=["Service", "Decision", "Information", "Record", "Product", "Handoff", "Other"]),
                _attr("quality", "Quality", "choice", "The expected or observed quality position of the output.", 20,
                      choices=["Unknown", "Acceptable", "Good", "Poor"]),
                _attr("purpose", "Purpose", "text", "What the output is used for or enables next.", 30),
            ],
        ),
        _otype(
            "policy", "Policy / Rule",
            "A policy, standard, rule, obligation or procedural constraint that governs how the process should operate.", 110,
            [
                _attr("policy_type", "Policy type", "choice", "The broad kind of governing requirement.", 10,
                      choices=["Policy", "Standard", "Rule", "Procedure", "Obligation", "Principle", "Other"]),
                _attr("status", "Status", "choice", "The current status of the policy or rule.", 20,
                      choices=["Draft", "Current", "Under review", "Retired"]),
                _attr("scope", "Scope", "text", "The part of the process or circumstance governed by the policy or rule.", 30),
                _attr("purpose", "Purpose", "text", "The behaviour, control or outcome the rule is intended to produce.", 40),
            ],
        ),
        _otype(
            "decision", "Decision Point",
            "A material choice within or around the process that determines what happens next or which path is taken.", 120,
            [
                _attr("decision_type", "Decision type", "choice", "The broad kind of process decision.", 10,
                      choices=["Business rule", "Approval", "Assessment", "Routing", "Exception", "Prioritisation", "Other"]),
                _attr("status", "Status", "choice", "The current state of the decision point.", 20,
                      choices=["Defined", "Under review", "Changed", "Retired"]),
                _attr("criteria", "Criteria", "text", "The information or conditions used to make the decision.", 30),
                _attr("purpose", "Purpose", "text", "What the decision is intended to determine.", 40),
            ],
        ),
        _otype(
            "dependency", "Dependency",
            "An external or adjacent service, process, capability or condition on which successful process execution relies.", 130,
            [
                _attr("dependency_type", "Dependency type", "choice", "The broad kind of dependency.", 10,
                      choices=["Process", "Service", "System", "Team", "Supplier", "External", "Resource", "Other"]),
                _attr("criticality", "Criticality", "choice", "The consequence to the process if the dependency is unavailable.", 20,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("description", "Description", "text", "How the process depends on this element.", 30),
            ],
        ),
        _otype(
            "supplier", "Supplier / Partner",
            "An external organisation or partner that provides something the process relies on or interacts with.", 140,
            [
                _attr("supplier_type", "Supplier type", "choice", "The broad kind of external relationship.", 10,
                      choices=["Supplier", "Technology provider", "Service provider", "Partner", "Regulator", "Other"]),
                _attr("relationship_status", "Relationship status", "choice", "The current state of the relationship.", 20,
                      choices=["Prospective", "Current", "Preferred", "Exiting"]),
                _attr("purpose", "Purpose", "text", "The role the external party plays in the process.", 30),
            ],
        ),
        _otype(
            "risk", "Process Risk / Exception",
            "A risk, failure condition or exception that can disrupt the process or alter its expected result.", 150,
            [
                _attr("risk_type", "Risk type", "choice", "The broad category of process risk or exception.", 10,
                      choices=["Operational", "Customer", "Technology", "People", "Information", "Third party", "Regulatory", "Other"]),
                _attr("status", "Status", "choice", "The current management status of the risk or exception.", 20,
                      choices=["Open", "Monitored", "Mitigated", "Accepted", "Closed"]),
                _attr("severity", "Severity", "choice", "The potential significance if the condition occurs.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("description", "Description", "text", "The practical effect on the process if the condition occurs.", 40),
            ],
        ),
        _otype(
            "measure", "Process Measure",
            "A measure used to understand process performance, quality, timeliness, capacity or customer experience.", 160,
            [
                _attr("measure_type", "Measure type", "choice", "The broad purpose of the measure.", 10,
                      choices=["Time", "Volume", "Quality", "Cost", "Capacity", "Customer", "Risk", "Outcome"]),
                _attr("frequency", "Frequency", "text", "How often the measure is collected or reviewed.", 20),
                _attr("direction", "Direction", "choice", "The intended direction of improvement where meaningful.", 30,
                      choices=["Higher is better", "Lower is better", "Target range", "Informational"]),
                _attr("purpose", "Purpose", "text", "What the measure is intended to tell the process owner or user.", 40),
            ],
        ),
        _otype(
            "outcome", "Process Outcome",
            "A meaningful business, customer or operational result that the process exists to achieve or support.", 170,
            [
                _attr("outcome_type", "Outcome type", "choice", "The broad kind of outcome.", 10,
                      choices=["Customer", "Operational", "Financial", "Compliance", "Service", "Strategic", "Other"]),
                _attr("status", "Status", "choice", "The current position against the intended outcome.", 20,
                      choices=["Planned", "On track", "Watch", "At risk", "Achieved"]),
                _attr("description", "Description", "text", "The result the process is intended to help achieve.", 30),
            ],
        ),
    ],

    "relationship_types": [
        _rtype("includes", "Includes", "Indicates that a process consists of one or more meaningful process steps.", 10, [
            _rule("process", "process_step", 1, None, 1, 1),
        ]),
        _rtype("precedes", "Precedes", "Indicates the expected sequence between process steps without reducing the model to a simple flowchart.", 20, [
            _rule("process_step", "process_step", 0, None, 0, None),
        ]),
        _rtype("triggered_by", "Triggered by", "Indicates that an event starts, resumes or materially changes a process or process step.", 30, [
            _rule("process", "event", 0, None, 0, None),
            _rule("process_step", "event", 0, None, 0, None),
        ]),
        _rtype("performed_by", "Performed by", "Indicates the person or team carrying out a process or process step.", 40, [
            _rule("process", "person", 0, None, 0, 1),
            _rule("process", "team", 0, None, 0, 1),
            _rule("process_step", "person", 0, None, 0, None),
            _rule("process_step", "team", 0, None, 0, None),
        ]),
        _rtype("serves", "Serves", "Indicates which customer or user group receives, participates in or depends on the process outcome.", 50, [
            _rule("process", "customer_group", 0, None, 0, None),
        ]),
        _rtype("uses", "Uses", "Indicates that a process or process step relies on an application, information or input/resource.", 60, [
            _rule("process", "application", 0, None, 0, None),
            _rule("process", "information", 0, None, 0, None),
            _rule("process", "input", 0, None, 0, None),
            _rule("process_step", "application", 0, None, 0, None),
            _rule("process_step", "information", 0, None, 0, None),
            _rule("process_step", "input", 0, None, 0, None),
        ]),
        _rtype("produces", "Produces", "Indicates that a process or process step creates an output, result or information product.", 70, [
            _rule("process", "output", 0, None, 0, None),
            _rule("process", "information", 0, None, 0, None),
            _rule("process_step", "output", 0, None, 0, None),
            _rule("process_step", "information", 0, None, 0, None),
        ]),
        _rtype("handoffs_to", "Hands off to", "Indicates that work, responsibility or a result is passed from one person or team to another.", 80, [
            _rule("process_step", "person", 0, None, 0, None),
            _rule("process_step", "team", 0, None, 0, None),
        ]),
        _rtype("governed_by", "Governed by", "Indicates that a process or step operates under a policy, standard, rule or obligation.", 90, [
            _rule("process", "policy", 0, None, 0, None),
            _rule("process_step", "policy", 0, None, 0, None),
            _rule("decision", "policy", 0, None, 0, None),
        ]),
        _rtype("decides", "Decides", "Indicates that a decision point determines a path, approval or treatment within the process.", 100, [
            _rule("process_step", "decision", 0, None, 0, 1),
            _rule("process", "decision", 0, None, 0, None),
        ]),
        _rtype("depends_on", "Depends on", "Indicates that the process or one of its steps relies on an adjacent process, service or condition.", 110, [
            _rule("process", "dependency", 0, None, 0, None),
            _rule("process_step", "dependency", 0, None, 0, None),
        ]),
        _rtype("supplied_by", "Supplied by", "Indicates that an input, application or dependency is provided by an external supplier or partner.", 120, [
            _rule("input", "supplier", 0, 1, 0, None),
            _rule("application", "supplier", 0, 1, 0, None),
            _rule("dependency", "supplier", 0, 1, 0, None),
        ]),
        _rtype("impacts", "Impacts", "Indicates that a risk or exception could adversely affect a process, step, output or outcome.", 130, [
            _rule("risk", "process", 0, None, 0, None),
            _rule("risk", "process_step", 0, None, 0, None),
            _rule("risk", "output", 0, None, 0, None),
            _rule("risk", "outcome", 0, None, 0, None),
        ]),
        _rtype("mitigated_by", "Mitigated by", "Indicates that a process step, decision or control activity reduces or manages a process risk or exception.", 140, [
            _rule("process_step", "risk", 0, None, 0, None),
            _rule("decision", "risk", 0, None, 0, None),
            _rule("process", "risk", 0, None, 0, None),
        ]),
        _rtype("measured_by", "Measured by", "Indicates which measures are used to assess process performance or effectiveness.", 150, [
            _rule("process", "measure", 0, None, 0, None),
            _rule("process_step", "measure", 0, None, 0, None),
            _rule("output", "measure", 0, None, 0, None),
            _rule("outcome", "measure", 0, None, 0, None),
        ]),
        _rtype("evidenced_by", "Evidenced by", "Indicates that information or records provide evidence about how the process operates or performs.", 160, [
            _rule("process", "information", 0, None, 0, None),
            _rule("process_step", "information", 0, None, 0, None),
            _rule("decision", "information", 0, None, 0, None),
            _rule("risk", "information", 0, None, 0, None),
            _rule("outcome", "information", 0, None, 0, None),
        ]),
        _rtype("supports_outcome", "Supports outcome", "Indicates that the process or one of its outputs contributes to an intended outcome.", 170, [
            _rule("process", "outcome", 0, None, 0, None),
            _rule("output", "outcome", 0, None, 0, None),
            _rule("process_step", "outcome", 0, None, 0, None),
        ]),
        _rtype("interacts_with", "Interacts with", "Indicates a meaningful interaction between the process and a customer, user, supplier or external party.", 180, [
            _rule("process", "customer_group", 0, None, 0, None),
            _rule("process", "supplier", 0, None, 0, None),
            _rule("process_step", "customer_group", 0, None, 0, None),
            _rule("process_step", "supplier", 0, None, 0, None),
        ]),
    ],

    # Deliberately no sample data: this is a genuine starting-point template.
    "objects": [],
    "relationships": [],

    "appearance": {
        "object_types": {
            "process": {"shape": "ellipse", "icon": "process", "background": "#E7F5FF", "border": "#3D7EA6", "font_colour": "#24465E", "font_weight": "bold"},
            "process_step": {"shape": "box", "icon": "task", "background": "#EEF4FB", "border": "#6687A6", "font_colour": "#2E4358"},
            "event": {"shape": "ellipse", "icon": "event", "background": "#EAF5FC", "border": "#4C90B9", "font_colour": "#29485A"},
            "person": {"shape": "ellipse", "icon": "person", "background": "#F7ECFA", "border": "#A85CC2", "font_colour": "#4E315A"},
            "team": {"shape": "ellipse", "icon": "team", "background": "#E8F1FB", "border": "#5681AD", "font_colour": "#29445F"},
            "customer_group": {"shape": "ellipse", "icon": "person", "background": "#FDECEF", "border": "#C76B7F", "font_colour": "#5A303A"},
            "application": {"shape": "box", "icon": "application", "background": "#EAF0FF", "border": "#637BC2", "font_colour": "#303F67"},
            "information": {"shape": "box", "icon": "document", "background": "#FFF8E1", "border": "#B58B34", "font_colour": "#5D491D"},
            "input": {"shape": "box", "icon": "cube", "background": "#F0F2F4", "border": "#7A8792", "font_colour": "#34414A"},
            "output": {"shape": "box", "icon": "product", "background": "#E8F5E9", "border": "#4F9564", "font_colour": "#284C32", "font_weight": "bold"},
            "policy": {"shape": "hexagon", "icon": "shield", "background": "#EAF6EE", "border": "#4E8D63", "font_colour": "#294B34"},
            "decision": {"shape": "diamond", "icon": "decision", "background": "#FFF2E2", "border": "#C47A2C", "font_colour": "#5C3B1B", "font_weight": "bold"},
            "dependency": {"shape": "box", "icon": "network", "background": "#F1F3F5", "border": "#73808C", "font_colour": "#36414A"},
            "supplier": {"shape": "box", "icon": "store", "background": "#FFF0E1", "border": "#C88345", "font_colour": "#5D3D25"},
            "risk": {"shape": "diamond", "icon": "warning", "background": "#FBEAEA", "border": "#C65B5B", "font_colour": "#5E2C2C", "font_weight": "bold"},
            "measure": {"shape": "box", "icon": "chart", "background": "#F2EEFF", "border": "#8063B8", "font_colour": "#40345F"},
            "outcome": {"shape": "star", "icon": "target", "background": "#E8F7F3", "border": "#429B87", "font_colour": "#245047", "font_weight": "bold"},
        },
        "relationship_types": {
            "includes": {"colour": "#4C78A8", "width": 1.7, "line_style": "solid"},
            "precedes": {"colour": "#3D7EA6", "width": 1.6, "line_style": "solid"},
            "triggered_by": {"colour": "#3D7EA6", "width": 1.5, "line_style": "dashed"},
            "performed_by": {"colour": "#355F87", "width": 1.5, "line_style": "solid"},
            "serves": {"colour": "#B04F6B", "width": 1.5, "line_style": "solid"},
            "uses": {"colour": "#6C5AA8", "width": 1.5, "line_style": "solid"},
            "produces": {"colour": "#27815B", "width": 1.6, "line_style": "solid"},
            "handoffs_to": {"colour": "#65727E", "width": 1.5, "line_style": "dashed"},
            "governed_by": {"colour": "#3F7953", "width": 1.6, "line_style": "dashed"},
            "decides": {"colour": "#A96E2B", "width": 1.6, "line_style": "solid"},
            "depends_on": {"colour": "#8B5050", "width": 1.6, "line_style": "dashed"},
            "supplied_by": {"colour": "#A56835", "width": 1.5, "line_style": "dashed"},
            "impacts": {"colour": "#B43F3F", "width": 1.6, "line_style": "dashed"},
            "mitigated_by": {"colour": "#34855D", "width": 1.6, "line_style": "dashed"},
            "measured_by": {"colour": "#72549A", "width": 1.5, "line_style": "dotted"},
            "evidenced_by": {"colour": "#72549A", "width": 1.5, "line_style": "dotted"},
            "supports_outcome": {"colour": "#24806A", "width": 1.7, "line_style": "solid"},
            "interacts_with": {"colour": "#9B5A7A", "width": 1.5, "line_style": "solid"},
        },
    },
}

# Convenient alias for callers that use the naming convention of other templates.
PROCESS_CONTEXT = PROCESS_CONTEXT_TEMPLATE

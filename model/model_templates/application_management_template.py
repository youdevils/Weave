"""Application Management model template.

A blank, reusable starting-point model for understanding an application estate
and the business and technical context around it. The template is deliberately
estate-focused rather than a generic enterprise architecture model: it connects
applications and components to capabilities, processes, services, information,
integrations, APIs, environments, platforms, people, teams, vendors, governance,
risks, planned change, measures and outcomes.

The template contains no sample objects or relationships. It is intended as a
meaningful semantic starting point that a user can extend for their own
application estate or technology problem.

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


APPLICATION_MANAGEMENT_TEMPLATE = {
    "key": "application_management",
    "name": "Application Management",
    "description": (
        "A reusable starting point for understanding an application estate and the context around it. "
        "The model connects applications and components to business capabilities, processes, services, "
        "information, integrations, APIs, environments, platforms, people, teams, vendors, governance, "
        "risks, planned change, measures and outcomes so the estate can be understood as a connected system."
    ),

    "object_types": [
        _otype(
            "application", "Application",
            "A software application or digital system that supports, automates or enables business or operational work.", 10,
            [
                _attr("application_type", "Application type", "choice", "The broad kind of application.", 10,
                      choices=["SaaS", "Internal", "Platform", "Custom", "Legacy", "Mobile", "Website", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the application.", 20,
                      choices=["Planned", "Current", "Under review", "Retiring", "Retired"]),
                _attr("criticality", "Criticality", "choice", "The operational importance of the application.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("support_status", "Support status", "choice", "The current level of support and active ownership for the application.", 40,
                      choices=["Supported", "Limited support", "Unsupported", "Unknown"]),
                _attr("purpose", "Purpose", "text", "The principal business or operational purpose the application serves.", 50),
            ],
        ),
        _otype(
            "application_component", "Application Component",
            "A meaningful internal component, module or bounded part of an application that can be managed or changed independently.", 20,
            [
                _attr("component_type", "Component type", "choice", "The broad kind of application component.", 10,
                      choices=["Module", "Service", "Database", "Job", "Extension", "Configuration", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the component.", 20,
                      choices=["Current", "Under change", "Retiring", "Retired"]),
                _attr("purpose", "Purpose", "text", "The role the component plays within the application.", 30),
            ],
        ),
        _otype(
            "business_capability", "Business Capability",
            "An organisational ability that an application, service or technology supports or enables.", 30,
            [
                _attr("maturity", "Maturity", "choice", "The current maturity of the capability.", 10,
                      choices=["Emerging", "Developing", "Established", "Advanced"]),
                _attr("importance", "Importance", "choice", "The relative importance of the capability to the organisation.", 20,
                      choices=["Supporting", "Important", "Strategic", "Critical"]),
                _attr("purpose", "Purpose", "text", "What the capability enables the organisation to do.", 30),
            ],
        ),
        _otype(
            "business_process", "Business Process",
            "A repeatable body of business work supported by one or more applications or services.", 40,
            [
                _attr("process_type", "Process type", "choice", "The broad type of business process.", 10,
                      choices=["Core", "Supporting", "Management", "Control"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the process.", 20,
                      choices=["Planned", "Current", "Under review", "Retiring"]),
                _attr("criticality", "Criticality", "choice", "The impact of application failure on the process.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("purpose", "Purpose", "text", "The business purpose of the process.", 40),
            ],
        ),
        _otype(
            "service", "Service",
            "A business or technology service provided to customers, users or other parts of the organisation.", 50,
            [
                _attr("service_type", "Service type", "choice", "The broad kind of service.", 10,
                      choices=["Business", "Customer", "Internal", "Platform", "Shared", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the service.", 20,
                      choices=["Planned", "Current", "Under review", "Retiring"]),
                _attr("criticality", "Criticality", "choice", "The operational importance of the service.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("purpose", "Purpose", "text", "The value or support the service provides.", 40),
            ],
        ),
        _otype(
            "information_asset", "Information Asset",
            "A meaningful data set, record, document or information domain that is created, stored or used by applications.", 60,
            [
                _attr("information_type", "Information type", "choice", "The broad kind of information asset.", 10,
                      choices=["Customer data", "Transactional data", "Reference data", "Document", "Report", "Record", "Other"]),
                _attr("sensitivity", "Sensitivity", "choice", "The general sensitivity of the information asset.", 20,
                      choices=["Public", "Internal", "Confidential", "Restricted"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the information asset.", 30,
                      choices=["Active", "Under review", "Archived", "Retired"]),
                _attr("purpose", "Purpose", "text", "The principal business use or value of the information asset.", 40),
            ],
        ),
        _otype(
            "integration", "Integration",
            "A defined exchange or connection that allows applications or services to interact and move information or events.", 70,
            [
                _attr("integration_type", "Integration type", "choice", "The broad pattern used for the integration.", 10,
                      choices=["API", "Event", "File", "Batch", "Message", "Other"]),
                _attr("status", "Status", "choice", "The current operating status of the integration.", 20,
                      choices=["Planned", "Current", "Under change", "Retiring", "Failed"]),
                _attr("frequency", "Frequency", "text", "How often information or events are exchanged.", 30),
                _attr("purpose", "Purpose", "text", "Why the integration exists and what it enables.", 40),
            ],
        ),
        _otype(
            "api_interface", "API Interface",
            "A defined application programming interface through which an application exposes or consumes functionality or information.", 80,
            [
                _attr("api_type", "API type", "choice", "The broad type of API interface.", 10,
                      choices=["REST", "SOAP", "GraphQL", "Internal", "Partner", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the API.", 20,
                      choices=["Planned", "Current", "Deprecated", "Retiring"]),
                _attr("version", "Version", "text", "The current published or supported API version.", 30),
                _attr("purpose", "Purpose", "text", "The functionality or information exposed through the API.", 40),
            ],
        ),
        _otype(
            "environment", "Environment",
            "A runtime environment in which an application or component is developed, tested or operated.", 90,
            [
                _attr("environment_type", "Environment type", "choice", "The role of the environment.", 10,
                      choices=["Development", "Test", "UAT", "Production", "Disaster recovery", "Other"]),
                _attr("location", "Location", "text", "Where the environment is hosted or materially located.", 20),
                _attr("status", "Status", "choice", "The current operating state of the environment.", 30,
                      choices=["Available", "Degraded", "Planned", "Retiring"]),
            ],
        ),
        _otype(
            "technology_platform", "Technology Platform",
            "A shared technology platform or infrastructure capability on which applications or components depend.", 100,
            [
                _attr("platform_type", "Platform type", "choice", "The broad type of technology platform.", 10,
                      choices=["Cloud", "Server", "Database", "Container", "Network", "Identity", "Other"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the platform.", 20,
                      choices=["Planned", "Current", "Under upgrade", "Retiring"]),
                _attr("criticality", "Criticality", "choice", "The operational importance of the platform.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("purpose", "Purpose", "text", "The technology capability or shared service the platform provides.", 40),
            ],
        ),
        _otype(
            "person", "Person",
            "An individual with a defined ownership, support, architecture, delivery or decision responsibility relating to the application estate.", 110,
            [
                _attr("role", "Role", "text", "The person's role relevant to the application estate.", 10),
                _attr("responsibility", "Responsibility", "text", "The principal responsibility held by the person.", 20),
            ],
        ),
        _otype(
            "team", "Team",
            "A group accountable for owning, supporting, developing, governing or using applications and related services.", 120,
            [
                _attr("team_type", "Team type", "choice", "The broad role of the team.", 10,
                      choices=["Product", "Engineering", "Support", "Architecture", "Security", "Operations", "Business", "Other"]),
                _attr("responsibility", "Responsibility", "text", "The team's main area of accountability.", 20),
                _attr("purpose", "Purpose", "text", "The team's primary role in the application estate.", 30),
            ],
        ),
        _otype(
            "vendor", "Vendor / Provider",
            "An external organisation providing an application, platform, service, support capability or technology dependency.", 130,
            [
                _attr("vendor_type", "Vendor type", "choice", "The broad type of external provider.", 10,
                      choices=["Software vendor", "Cloud provider", "Managed service", "Consultancy", "Support provider", "Other"]),
                _attr("relationship_status", "Relationship status", "choice", "The current relationship with the provider.", 20,
                      choices=["Current", "Preferred", "Under review", "Exiting"]),
                _attr("criticality", "Criticality", "choice", "The importance of the provider to continued operation.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
            ],
        ),
        _otype(
            "policy", "Policy / Standard",
            "A policy, standard, architectural rule or mandatory practice that governs an application or technology decision.", 140,
            [
                _attr("policy_type", "Policy type", "choice", "The broad kind of governing requirement.", 10,
                      choices=["Policy", "Standard", "Architecture principle", "Security requirement", "Data requirement", "Other"]),
                _attr("status", "Status", "choice", "The current status of the governing requirement.", 20,
                      choices=["Current", "Under review", "Proposed", "Retired"]),
                _attr("purpose", "Purpose", "text", "What the policy or standard is intended to control or achieve.", 30),
            ],
        ),
        _otype(
            "risk", "Application Risk",
            "A condition that could adversely affect an application's availability, security, integrity, supportability or business value.", 150,
            [
                _attr("category", "Category", "choice", "The broad category of application risk.", 10,
                      choices=["Availability", "Security", "Data", "Technology", "Vendor", "Support", "Architecture", "Other"]),
                _attr("status", "Status", "choice", "The current management status of the risk.", 20,
                      choices=["Open", "Monitored", "Mitigated", "Accepted", "Closed"]),
                _attr("severity", "Severity", "choice", "The potential severity if the risk materialises.", 30,
                      choices=["Low", "Medium", "High", "Critical"]),
                _attr("description", "Description", "text", "The practical effect the risk could have on the estate or supported business.", 40),
            ],
        ),
        _otype(
            "change_initiative", "Change Initiative",
            "A planned change, modernisation, replacement, migration or investment that materially affects one or more applications or their dependencies.", 160,
            [
                _attr("change_type", "Change type", "choice", "The broad kind of application change.", 10,
                      choices=["Enhancement", "Modernisation", "Migration", "Replacement", "Decommission", "Remediation", "Other"]),
                _attr("status", "Status", "choice", "The current status of the change initiative.", 20,
                      choices=["Proposed", "Planned", "In progress", "Complete", "Paused", "Cancelled"]),
                _attr("target_timing", "Target timing", "text", "The intended timing or delivery window for the change.", 30),
                _attr("purpose", "Purpose", "text", "The outcome or reason for undertaking the change.", 40),
            ],
        ),
        _otype(
            "measure", "Measure",
            "A metric or indicator used to understand application performance, reliability, cost, adoption or business value.", 170,
            [
                _attr("measure_type", "Measure type", "choice", "The broad category of the measure.", 10,
                      choices=["Availability", "Performance", "Cost", "Usage", "Quality", "Risk", "Value", "Other"]),
                _attr("frequency", "Frequency", "text", "How often the measure is collected or reviewed.", 20),
                _attr("target", "Target", "text", "The intended target, threshold or expected position.", 30),
                _attr("purpose", "Purpose", "text", "What decision or understanding the measure supports.", 40),
            ],
        ),
        _otype(
            "outcome", "Business Outcome",
            "A meaningful business result that the application estate, service or technology investment is intended to support.", 180,
            [
                _attr("outcome_type", "Outcome type", "choice", "The broad kind of outcome.", 10,
                      choices=["Customer", "Operational", "Financial", "Risk", "Strategic", "Other"]),
                _attr("status", "Status", "choice", "The current position against the intended outcome.", 20,
                      choices=["On track", "Watch", "At risk", "Achieved"]),
                _attr("description", "Description", "text", "The desired business result.", 30),
            ],
        ),
    ],

    "relationship_types": [
        _rtype("contains", "Contains", "Indicates that an application contains an independently meaningful component.", 10, [
            _rule("application", "application_component", 0, None, 0, None),
        ]),
        _rtype("supports_capability", "Supports capability", "Indicates that an application, service or process supports an organisational capability.", 20, [
            _rule("application", "business_capability", 0, None, 0, None),
            _rule("service", "business_capability", 0, None, 0, None),
            _rule("business_process", "business_capability", 0, None, 0, None),
        ]),
        _rtype("supports_process", "Supports process", "Indicates that an application or service supports execution of a business process.", 30, [
            _rule("application", "business_process", 0, None, 0, None),
            _rule("service", "business_process", 0, None, 0, None),
        ]),
        _rtype("provides_service", "Provides service", "Indicates that an application provides or enables a business or technology service.", 40, [
            _rule("application", "service", 0, None, 0, None),
            _rule("application_component", "service", 0, None, 0, None),
        ]),
        _rtype("uses_information", "Uses information", "Indicates that an application, process or service creates, reads or otherwise uses an information asset.", 50, [
            _rule("application", "information_asset", 0, None, 0, None),
            _rule("business_process", "information_asset", 0, None, 0, None),
            _rule("service", "information_asset", 0, None, 0, None),
        ]),
        _rtype("integrates_with", "Integrates with", "Indicates that an application or service exchanges information or events with another application or service.", 60, [
            _rule("application", "application", 0, None, 0, None),
            _rule("application", "service", 0, None, 0, None),
            _rule("service", "application", 0, None, 0, None),
        ]),
        _rtype("realised_by", "Realised by", "Indicates that an application integration is realised through one or more interfaces or technical components.", 70, [
            _rule("integration", "api_interface", 0, None, 0, None),
            _rule("integration", "application_component", 0, None, 0, None),
        ]),
        _rtype("connects", "Connects", "Indicates which applications or services participate in an integration.", 80, [
            _rule("integration", "application", 0, None, 0, None),
            _rule("integration", "service", 0, None, 0, None),
        ]),
        _rtype("exposes", "Exposes", "Indicates that an application or component exposes an API interface.", 90, [
            _rule("application", "api_interface", 0, None, 0, None),
            _rule("application_component", "api_interface", 0, None, 0, None),
        ]),
        _rtype("deployed_to", "Deployed to", "Indicates that an application or component is deployed into a particular runtime environment.", 100, [
            _rule("application", "environment", 0, None, 0, None),
            _rule("application_component", "environment", 0, None, 0, None),
        ]),
        _rtype("runs_on", "Runs on", "Indicates that an application, component or environment relies on a technology platform.", 110, [
            _rule("application", "technology_platform", 0, None, 0, None),
            _rule("application_component", "technology_platform", 0, None, 0, None),
            _rule("environment", "technology_platform", 0, None, 0, None),
        ]),
        _rtype("owned_by", "Owned by", "Indicates the person or team accountable for an application, service or technology asset.", 120, [
            _rule("application", "person", 0, 1, 0, None),
            _rule("application", "team", 0, 1, 0, None),
            _rule("service", "person", 0, 1, 0, None),
            _rule("service", "team", 0, 1, 0, None),
            _rule("technology_platform", "person", 0, 1, 0, None),
            _rule("technology_platform", "team", 0, 1, 0, None),
        ]),
        _rtype("provided_by", "Provided by", "Indicates that an application, service, platform or component is provided or supported by an external vendor.", 130, [
            _rule("application", "vendor", 0, 1, 0, None),
            _rule("service", "vendor", 0, 1, 0, None),
            _rule("technology_platform", "vendor", 0, 1, 0, None),
            _rule("application_component", "vendor", 0, 1, 0, None),
        ]),
        _rtype("governed_by", "Governed by", "Indicates that an application, interface, information asset, platform or change is governed by a policy or standard.", 140, [
            _rule("application", "policy", 0, None, 0, None),
            _rule("api_interface", "policy", 0, None, 0, None),
            _rule("information_asset", "policy", 0, None, 0, None),
            _rule("technology_platform", "policy", 0, None, 0, None),
            _rule("change_initiative", "policy", 0, None, 0, None),
        ]),
        _rtype("depends_on", "Depends on", "Indicates that an application, service, component or environment relies on another estate dependency.", 150, [
            _rule("application", "application", 0, None, 0, None),
            _rule("application", "technology_platform", 0, None, 0, None),
            _rule("application", "service", 0, None, 0, None),
            _rule("application_component", "application_component", 0, None, 0, None),
            _rule("service", "application", 0, None, 0, None),
            _rule("environment", "technology_platform", 0, None, 0, None),
        ]),
        _rtype("affected_by", "Affected by", "Indicates that an application, service or capability may be adversely affected by a risk.", 160, [
            _rule("application", "risk", 0, None, 0, None),
            _rule("service", "risk", 0, None, 0, None),
            _rule("business_process", "risk", 0, None, 0, None),
        ]),
        _rtype("addressed_by", "Addressed by", "Indicates that a risk is actively addressed by a change initiative or governing policy.", 170, [
            _rule("risk", "change_initiative", 0, None, 0, None),
            _rule("risk", "policy", 0, None, 0, None),
        ]),
        _rtype("planned_change", "Planned change", "Indicates that a planned change initiative materially affects an application, service or platform.", 180, [
            _rule("change_initiative", "application", 0, None, 0, None),
            _rule("change_initiative", "service", 0, None, 0, None),
            _rule("change_initiative", "technology_platform", 0, None, 0, None),
        ]),
        _rtype("measured_by", "Measured by", "Indicates which measures are used to understand application, service or capability performance and value.", 190, [
            _rule("application", "measure", 0, None, 0, None),
            _rule("service", "measure", 0, None, 0, None),
            _rule("business_capability", "measure", 0, None, 0, None),
        ]),
        _rtype("supports_outcome", "Supports outcome", "Indicates that an application, service, capability or process contributes to an intended business outcome.", 200, [
            _rule("application", "outcome", 0, None, 0, None),
            _rule("service", "outcome", 0, None, 0, None),
            _rule("business_capability", "outcome", 0, None, 0, None),
            _rule("business_process", "outcome", 0, None, 0, None),
        ]),
    ],

    # Deliberately no sample data: this is a genuine starting-point template.
    "objects": [],
    "relationships": [],

    "appearance": {
        "object_types": {
            "application": {"shape": "box", "icon": "application", "background": "#EAF0FF", "border": "#637BC2", "font_colour": "#303F67", "font_weight": "bold"},
            "application_component": {"shape": "box", "icon": "cube", "background": "#F0F3F8", "border": "#788AA3", "font_colour": "#354252"},
            "business_capability": {"shape": "hexagon", "icon": "cube", "background": "#F0EBFA", "border": "#8064B4", "font_colour": "#493A61", "font_weight": "bold"},
            "business_process": {"shape": "ellipse", "icon": "process", "background": "#E9F6F4", "border": "#4D968A", "font_colour": "#294E49"},
            "service": {"shape": "box", "icon": "product", "background": "#EAF7F0", "border": "#54926C", "font_colour": "#2E4E39", "font_weight": "bold"},
            "information_asset": {"shape": "box", "icon": "document", "background": "#FFF8E5", "border": "#B58E35", "font_colour": "#5E4A20"},
            "integration": {"shape": "ellipse", "icon": "network", "background": "#FFF0E4", "border": "#BE7A43", "font_colour": "#5D3E27"},
            "api_interface": {"shape": "box", "icon": "api", "background": "#F2EEFF", "border": "#8063B8", "font_colour": "#40345F"},
            "environment": {"shape": "ellipse", "icon": "cloud", "background": "#EAF5FF", "border": "#5C91BA", "font_colour": "#304B60"},
            "technology_platform": {"shape": "box", "icon": "server", "background": "#EEF1F3", "border": "#77838D", "font_colour": "#374149"},
            "person": {"shape": "ellipse", "icon": "person", "background": "#F8ECFA", "border": "#A85CC2", "font_colour": "#4E315A"},
            "team": {"shape": "ellipse", "icon": "team", "background": "#E9F0FB", "border": "#5A80AD", "font_colour": "#2D465F"},
            "vendor": {"shape": "box", "icon": "store", "background": "#FFF1E1", "border": "#C88345", "font_colour": "#5D3D25"},
            "policy": {"shape": "hexagon", "icon": "shield", "background": "#EAF6EE", "border": "#4E8D63", "font_colour": "#294B34"},
            "risk": {"shape": "diamond", "icon": "warning", "background": "#FBEAEA", "border": "#C65B5B", "font_colour": "#5E2C2C", "font_weight": "bold"},
            "change_initiative": {"shape": "box", "icon": "task", "background": "#FFF5DC", "border": "#B98A35", "font_colour": "#5B471F"},
            "measure": {"shape": "box", "icon": "chart", "background": "#F2EEFF", "border": "#8063B8", "font_colour": "#40345F"},
            "outcome": {"shape": "star", "icon": "target", "background": "#E8F7F3", "border": "#429B87", "font_colour": "#245047", "font_weight": "bold"},
        },
        "relationship_types": {
            "contains": {"colour": "#627486", "width": 1.6, "line_style": "solid"},
            "supports_capability": {"colour": "#6C5AA8", "width": 1.6, "line_style": "solid"},
            "supports_process": {"colour": "#3E8179", "width": 1.6, "line_style": "solid"},
            "provides_service": {"colour": "#39815B", "width": 1.7, "line_style": "solid"},
            "uses_information": {"colour": "#9A7930", "width": 1.5, "line_style": "dashed"},
            "integrates_with": {"colour": "#B56D38", "width": 1.7, "line_style": "solid"},
            "realised_by": {"colour": "#7A5BAF", "width": 1.5, "line_style": "dashed"},
            "connects": {"colour": "#B56D38", "width": 1.5, "line_style": "dashed"},
            "exposes": {"colour": "#72549A", "width": 1.5, "line_style": "solid"},
            "deployed_to": {"colour": "#4F7FA2", "width": 1.6, "line_style": "solid"},
            "runs_on": {"colour": "#65727E", "width": 1.5, "line_style": "dashed"},
            "owned_by": {"colour": "#355F87", "width": 1.5, "line_style": "solid"},
            "provided_by": {"colour": "#A56835", "width": 1.5, "line_style": "dashed"},
            "governed_by": {"colour": "#3F7953", "width": 1.5, "line_style": "dashed"},
            "depends_on": {"colour": "#8B5050", "width": 1.6, "line_style": "dashed"},
            "affected_by": {"colour": "#B43F3F", "width": 1.6, "line_style": "dashed"},
            "addressed_by": {"colour": "#3F7E61", "width": 1.5, "line_style": "dashed"},
            "planned_change": {"colour": "#A77A2E", "width": 1.6, "line_style": "dashed"},
            "measured_by": {"colour": "#72549A", "width": 1.5, "line_style": "dotted"},
            "supports_outcome": {"colour": "#24806A", "width": 1.7, "line_style": "solid"},
        },
    },
}

# Convenient alias for callers that use the naming convention of other templates.
APPLICATION_MANAGEMENT = APPLICATION_MANAGEMENT_TEMPLATE

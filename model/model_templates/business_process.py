"""
Business Process model template.

This template provides a complete, populated starting point for
understanding business processes, the activities within them, the
people and teams performing them, the applications supporting them,
and the capabilities, information, customers and outcomes connected
to the work.

The template is deliberately declarative.

It describes WHAT the model contains. Template instantiation services
are responsible for turning the definition into database records.

Sample object keys are template-local references used to create the
sample relationships. They are not persisted as Object fields.
"""

BUSINESS_PROCESS_TEMPLATE = {
    "key": "business_process",
    "name": "Business Process",
    "description": (
        "A model for understanding how business processes are performed "
        "by people and supported by applications, capabilities and "
        "information."
    ),
    # -----------------------------------------------------------------
    # Object types
    # -----------------------------------------------------------------
    "object_types": [
        # =============================================================
        # Business Process
        # =============================================================
        {
            "key": "business_process",
            "name": "Business Process",
            "description": (
                "A defined sequence of activities performed to achieve "
                "a business outcome."
            ),
            "sort_order": 10,
            "attributes": [
                {
                    "key": "owner",
                    "name": "Owner",
                    "data_type": "text",
                    "description": (
                        "The person or role accountable for the overall "
                        "performance and effectiveness of the process."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {},
                },
                {
                    "key": "purpose",
                    "name": "Purpose",
                    "data_type": "text",
                    "description": (
                        "The business purpose or outcome that the "
                        "process is intended to achieve."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 20,
                    "config": {},
                },
                {
                    "key": "process_type",
                    "name": "Process type",
                    "data_type": "choice",
                    "description": "The broad type of business process.",
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 30,
                    "config": {
                        "choices": [
                            "Core",
                            "Supporting",
                            "Management",
                        ],
                    },
                },
                {
                    "key": "criticality",
                    "name": "Criticality",
                    "data_type": "choice",
                    "description": (
                        "The importance of the process to the organisation."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 40,
                    "config": {
                        "choices": [
                            "Low",
                            "Medium",
                            "High",
                            "Critical",
                        ],
                    },
                },
                {
                    "key": "lifecycle_status",
                    "name": "Lifecycle status",
                    "data_type": "choice",
                    "description": ("The current lifecycle state of the process."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 50,
                    "config": {
                        "choices": [
                            "Current",
                            "Under review",
                            "Planned",
                            "Retired",
                        ],
                    },
                },
                {
                    "key": "customer_facing",
                    "name": "Customer facing",
                    "data_type": "boolean",
                    "description": (
                        "Whether the process directly contributes to "
                        "a customer-facing service."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 60,
                    "config": {},
                },
            ],
        },
        # =============================================================
        # Activity
        # =============================================================
        {
            "key": "activity",
            "name": "Activity",
            "description": (
                "A discrete unit of work performed as part of a " "business process."
            ),
            "sort_order": 20,
            "attributes": [
                {
                    "key": "purpose",
                    "name": "Purpose",
                    "data_type": "text",
                    "description": (
                        "The outcome or purpose of the work performed "
                        "by the activity."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {},
                },
                {
                    "key": "activity_type",
                    "name": "Activity type",
                    "data_type": "choice",
                    "description": (
                        "The broad type of work performed by the activity."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 20,
                    "config": {
                        "choices": [
                            "Manual",
                            "Automated",
                            "Decision",
                            "Interaction",
                        ],
                    },
                },
                {
                    "key": "automation_level",
                    "name": "Automation level",
                    "data_type": "choice",
                    "description": ("The degree to which the activity is automated."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 30,
                    "config": {
                        "choices": [
                            "Manual",
                            "Assisted",
                            "Highly automated",
                            "Fully automated",
                        ],
                    },
                },
                {
                    "key": "criticality",
                    "name": "Criticality",
                    "data_type": "choice",
                    "description": ("The importance of the activity to the process."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 40,
                    "config": {
                        "choices": [
                            "Low",
                            "Medium",
                            "High",
                            "Critical",
                        ],
                    },
                },
            ],
        },
        # =============================================================
        # Team
        # =============================================================
        {
            "key": "team",
            "name": "Team",
            "description": (
                "A group of people responsible for performing or "
                "supporting business activities."
            ),
            "sort_order": 30,
            "attributes": [
                {
                    "key": "purpose",
                    "name": "Purpose",
                    "data_type": "text",
                    "description": (
                        "The primary role or purpose of the team "
                        "within the organisation."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {},
                },
                {
                    "key": "team_type",
                    "name": "Team type",
                    "data_type": "choice",
                    "description": "The broad type of team.",
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 20,
                    "config": {
                        "choices": [
                            "Business",
                            "Technology",
                            "Operations",
                            "External",
                        ],
                    },
                },
            ],
        },
        # =============================================================
        # Business Unit
        # =============================================================
        {
            "key": "business_unit",
            "name": "Business Unit",
            "description": (
                "An organisational unit responsible for a set of "
                "business capabilities, processes or services."
            ),
            "sort_order": 40,
            "attributes": [
                {
                    "key": "purpose",
                    "name": "Purpose",
                    "data_type": "text",
                    "description": ("The primary purpose of the business unit."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {},
                },
            ],
        },
        # =============================================================
        # Application
        # =============================================================
        {
            "key": "application",
            "name": "Application",
            "description": (
                "A software application used to support or enable " "business activity."
            ),
            "sort_order": 50,
            "attributes": [
                {
                    "key": "vendor",
                    "name": "Vendor",
                    "data_type": "text",
                    "description": (
                        "The organisation responsible for providing " "the application."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {},
                },
                {
                    "key": "application_type",
                    "name": "Application type",
                    "data_type": "choice",
                    "description": ("The broad category of application."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 20,
                    "config": {
                        "choices": [
                            "Business application",
                            "Platform",
                            "Infrastructure",
                            "Integration",
                        ],
                    },
                },
                {
                    "key": "lifecycle_status",
                    "name": "Lifecycle status",
                    "data_type": "choice",
                    "description": ("The current lifecycle state of the application."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 30,
                    "config": {
                        "choices": [
                            "Current",
                            "Under review",
                            "Planned",
                            "Retired",
                        ],
                    },
                },
                {
                    "key": "criticality",
                    "name": "Criticality",
                    "data_type": "choice",
                    "description": (
                        "The importance of the application to business " "operations."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 40,
                    "config": {
                        "choices": [
                            "Low",
                            "Medium",
                            "High",
                            "Critical",
                        ],
                    },
                },
                {
                    "key": "purpose",
                    "name": "Purpose",
                    "data_type": "text",
                    "description": (
                        "The primary business or technical purpose "
                        "of the application."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 50,
                    "config": {},
                },
            ],
        },
        # =============================================================
        # Business Capability
        # =============================================================
        {
            "key": "business_capability",
            "name": "Business Capability",
            "description": (
                "An ability the organisation possesses or requires "
                "to achieve its objectives."
            ),
            "sort_order": 60,
            "attributes": [
                {
                    "key": "purpose",
                    "name": "Purpose",
                    "data_type": "text",
                    "description": (
                        "The purpose and business value of the capability."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {},
                },
                {
                    "key": "strategic_importance",
                    "name": "Strategic importance",
                    "data_type": "choice",
                    "description": ("The strategic importance of the capability."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 20,
                    "config": {
                        "choices": [
                            "Low",
                            "Medium",
                            "High",
                            "Critical",
                        ],
                    },
                },
            ],
        },
        # =============================================================
        # Business Outcome
        # =============================================================
        {
            "key": "business_outcome",
            "name": "Business Outcome",
            "description": (
                "A result or outcome that the organisation seeks to "
                "achieve through its business processes."
            ),
            "sort_order": 70,
            "attributes": [
                {
                    "key": "description",
                    "name": "Outcome description",
                    "data_type": "text",
                    "description": ("A description of the desired business outcome."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {},
                },
            ],
        },
        # =============================================================
        # Customer
        # =============================================================
        {
            "key": "customer",
            "name": "Customer",
            "description": (
                "A person or organisation that receives products, "
                "services or outcomes from the business."
            ),
            "sort_order": 80,
            "attributes": [
                {
                    "key": "customer_type",
                    "name": "Customer type",
                    "data_type": "choice",
                    "description": ("The broad type of customer."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {
                        "choices": [
                            "Individual",
                            "Small business",
                            "Corporate",
                            "Government",
                        ],
                    },
                },
            ],
        },
        # =============================================================
        # Information Object
        # =============================================================
        {
            "key": "information_object",
            "name": "Information Object",
            "description": (
                "A meaningful unit of business information created, "
                "used or maintained during business activity."
            ),
            "sort_order": 90,
            "attributes": [
                {
                    "key": "purpose",
                    "name": "Purpose",
                    "data_type": "text",
                    "description": (
                        "The purpose of the information within the " "business domain."
                    ),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 10,
                    "config": {},
                },
                {
                    "key": "sensitivity",
                    "name": "Sensitivity",
                    "data_type": "choice",
                    "description": ("The general sensitivity of the information."),
                    "required": False,
                    "nullable": True,
                    "default_value": None,
                    "sort_order": 20,
                    "config": {
                        "choices": [
                            "Public",
                            "Internal",
                            "Confidential",
                            "Restricted",
                        ],
                    },
                },
            ],
        },
    ],
    # -----------------------------------------------------------------
    # Relationship types
    # -----------------------------------------------------------------
    "relationship_types": [
        # =============================================================
        # Process contains activities
        # =============================================================
        {
            "key": "contains",
            "name": "Contains",
            "description": ("Indicates that a business process contains an activity."),
            "sort_order": 10,
            "rules": [
                {
                    "subject_type": "business_process",
                    "object_type": "activity",
                    "subject_minimum": 1,
                    "subject_maximum": 1,
                    "object_minimum": 1,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Activity performed by team
        # =============================================================
        {
            "key": "performed_by",
            "name": "Performed by",
            "description": ("Indicates that an activity is performed by a team."),
            "sort_order": 20,
            "rules": [
                {
                    "subject_type": "activity",
                    "object_type": "team",
                    "subject_minimum": 1,
                    "subject_maximum": None,
                    "object_minimum": 0,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Activity uses application
        # =============================================================
        {
            "key": "uses",
            "name": "Uses",
            "description": (
                "Indicates that an activity uses an application " "to perform its work."
            ),
            "sort_order": 30,
            "rules": [
                {
                    "subject_type": "activity",
                    "object_type": "application",
                    "subject_minimum": 0,
                    "subject_maximum": None,
                    "object_minimum": 0,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Application supports capability
        # =============================================================
        {
            "key": "supports",
            "name": "Supports",
            "description": (
                "Indicates that an application supports a business " "capability."
            ),
            "sort_order": 40,
            "rules": [
                {
                    "subject_type": "application",
                    "object_type": "business_capability",
                    "subject_minimum": 1,
                    "subject_maximum": None,
                    "object_minimum": 0,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Process delivers outcome
        # =============================================================
        {
            "key": "delivers",
            "name": "Delivers",
            "description": (
                "Indicates that a business process contributes to "
                "a business outcome."
            ),
            "sort_order": 50,
            "rules": [
                {
                    "subject_type": "business_process",
                    "object_type": "business_outcome",
                    "subject_minimum": 1,
                    "subject_maximum": None,
                    "object_minimum": 0,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Process serves customer
        # =============================================================
        {
            "key": "serves",
            "name": "Serves",
            "description": (
                "Indicates that a business process serves a customer "
                "or customer group."
            ),
            "sort_order": 60,
            "rules": [
                {
                    "subject_type": "business_process",
                    "object_type": "customer",
                    "subject_minimum": 0,
                    "subject_maximum": None,
                    "object_minimum": 0,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Process owned by team
        # =============================================================
        {
            "key": "owned_by",
            "name": "Owned by",
            "description": (
                "Indicates that a team is accountable for a " "business process."
            ),
            "sort_order": 70,
            "rules": [
                {
                    "subject_type": "business_process",
                    "object_type": "team",
                    "subject_minimum": 0,
                    "subject_maximum": None,
                    "object_minimum": 1,
                    "object_maximum": 1,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Team belongs to business unit
        # =============================================================
        {
            "key": "belongs_to",
            "name": "Belongs to",
            "description": ("Indicates that a team belongs to a business unit."),
            "sort_order": 80,
            "rules": [
                {
                    "subject_type": "team",
                    "object_type": "business_unit",
                    "subject_minimum": 1,
                    "subject_maximum": None,
                    "object_minimum": 1,
                    "object_maximum": 1,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Activity creates information
        # =============================================================
        {
            "key": "creates",
            "name": "Creates",
            "description": (
                "Indicates that an activity creates or produces "
                "an information object."
            ),
            "sort_order": 90,
            "rules": [
                {
                    "subject_type": "activity",
                    "object_type": "information_object",
                    "subject_minimum": 0,
                    "subject_maximum": None,
                    "object_minimum": 0,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Activity uses information
        # =============================================================
        {
            "key": "uses_information",
            "name": "Uses information",
            "description": ("Indicates that an activity uses an information object."),
            "sort_order": 100,
            "rules": [
                {
                    "subject_type": "activity",
                    "object_type": "information_object",
                    "subject_minimum": 0,
                    "subject_maximum": None,
                    "object_minimum": 0,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
        # =============================================================
        # Application depends on application
        # =============================================================
        {
            "key": "depends_on",
            "name": "Depends on",
            "description": (
                "Indicates that an application depends on another " "application."
            ),
            "sort_order": 110,
            "rules": [
                {
                    "subject_type": "application",
                    "object_type": "application",
                    "subject_minimum": 0,
                    "subject_maximum": None,
                    "object_minimum": 0,
                    "object_maximum": None,
                },
            ],
            "attributes": [],
        },
    ],
    # -----------------------------------------------------------------
    # Sample objects
    # -----------------------------------------------------------------
    "objects": [
        # =============================================================
        # Business Units
        # =============================================================
        {
            "key": "customer_operations",
            "type": "business_unit",
            "name": "Customer Operations",
            "description": (
                "The business unit responsible for customer-facing "
                "operations and service delivery."
            ),
            "attributes": {
                "purpose": ("Deliver consistent and effective customer service."),
            },
        },
        {
            "key": "insurance_operations",
            "type": "business_unit",
            "name": "Insurance Operations",
            "description": (
                "The business unit responsible for underwriting, "
                "policy administration and claims."
            ),
            "attributes": {
                "purpose": ("Manage the core insurance lifecycle."),
            },
        },
        {
            "key": "finance",
            "type": "business_unit",
            "name": "Finance",
            "description": ("The business unit responsible for financial operations."),
            "attributes": {
                "purpose": ("Manage financial transactions, controls and reporting."),
            },
        },
        {
            "key": "technology",
            "type": "business_unit",
            "name": "Technology",
            "description": (
                "The business unit responsible for technology platforms "
                "and application services."
            ),
            "attributes": {
                "purpose": (
                    "Provide and maintain technology capabilities "
                    "supporting the organisation."
                ),
            },
        },
        # =============================================================
        # Teams
        # =============================================================
        {
            "key": "sales",
            "type": "team",
            "name": "Sales",
            "description": (
                "Team responsible for customer acquisition and new business."
            ),
            "attributes": {
                "purpose": "Acquire and support new customers.",
                "team_type": "Business",
            },
        },
        {
            "key": "underwriting",
            "type": "team",
            "name": "Underwriting",
            "description": (
                "Team responsible for assessing risk and making "
                "underwriting decisions."
            ),
            "attributes": {
                "purpose": "Assess risk and determine appropriate cover.",
                "team_type": "Business",
            },
        },
        {
            "key": "customer_service",
            "type": "team",
            "name": "Customer Service",
            "description": (
                "Team responsible for assisting customers throughout "
                "the policy lifecycle."
            ),
            "attributes": {
                "purpose": "Support customers and resolve enquiries.",
                "team_type": "Business",
            },
        },
        {
            "key": "claims",
            "type": "team",
            "name": "Claims",
            "description": (
                "Team responsible for assessing and settling insurance claims."
            ),
            "attributes": {
                "purpose": "Assess and settle customer claims.",
                "team_type": "Business",
            },
        },
        {
            "key": "finance_operations",
            "type": "team",
            "name": "Finance Operations",
            "description": (
                "Team responsible for financial processing and reconciliation."
            ),
            "attributes": {
                "purpose": "Process and control financial transactions.",
                "team_type": "Operations",
            },
        },
        {
            "key": "technology_services",
            "type": "team",
            "name": "Technology Services",
            "description": (
                "Team responsible for technology platforms and application " "support."
            ),
            "attributes": {
                "purpose": "Operate and support technology services.",
                "team_type": "Technology",
            },
        },
        {
            "key": "data_analytics",
            "type": "team",
            "name": "Data & Analytics",
            "description": ("Team responsible for data, reporting and analytics."),
            "attributes": {
                "purpose": "Provide trusted information and analytical insight.",
                "team_type": "Technology",
            },
        },
        # =============================================================
        # Capabilities
        # =============================================================
        {
            "key": "customer_management",
            "type": "business_capability",
            "name": "Customer Management",
            "description": (
                "The ability to acquire, understand and support customers."
            ),
            "attributes": {
                "purpose": "Manage customer relationships and interactions.",
                "strategic_importance": "High",
            },
        },
        {
            "key": "underwriting_capability",
            "type": "business_capability",
            "name": "Underwriting",
            "description": (
                "The ability to assess insurance risk and determine cover."
            ),
            "attributes": {
                "purpose": "Assess risk and make underwriting decisions.",
                "strategic_importance": "Critical",
            },
        },
        {
            "key": "policy_administration",
            "type": "business_capability",
            "name": "Policy Administration",
            "description": (
                "The ability to create, maintain and manage insurance policies."
            ),
            "attributes": {
                "purpose": "Manage the insurance policy lifecycle.",
                "strategic_importance": "Critical",
            },
        },
        {
            "key": "claims_management",
            "type": "business_capability",
            "name": "Claims Management",
            "description": ("The ability to receive, assess and settle claims."),
            "attributes": {
                "purpose": "Manage claims from notification through settlement.",
                "strategic_importance": "Critical",
            },
        },
        {
            "key": "payments",
            "type": "business_capability",
            "name": "Payments",
            "description": ("The ability to collect and make financial payments."),
            "attributes": {
                "purpose": "Manage customer and business payments.",
                "strategic_importance": "High",
            },
        },
        {
            "key": "document_management",
            "type": "business_capability",
            "name": "Document Management",
            "description": (
                "The ability to create, store and retrieve business documents."
            ),
            "attributes": {
                "purpose": "Manage important business documentation.",
                "strategic_importance": "Medium",
            },
        },
        {
            "key": "reporting_analytics",
            "type": "business_capability",
            "name": "Reporting & Analytics",
            "description": (
                "The ability to turn business information into "
                "reporting and insight."
            ),
            "attributes": {
                "purpose": "Provide trusted reporting and analytical insight.",
                "strategic_importance": "High",
            },
        },
        # =============================================================
        # Customers
        # =============================================================
        {
            "key": "individual_customer",
            "type": "customer",
            "name": "Individual Customer",
            "description": ("A representative individual insurance customer."),
            "attributes": {
                "customer_type": "Individual",
            },
        },
        {
            "key": "small_business_customer",
            "type": "customer",
            "name": "Small Business Customer",
            "description": ("A representative small business insurance customer."),
            "attributes": {
                "customer_type": "Small business",
            },
        },
        {
            "key": "corporate_customer",
            "type": "customer",
            "name": "Corporate Customer",
            "description": ("A representative corporate insurance customer."),
            "attributes": {
                "customer_type": "Corporate",
            },
        },
        # =============================================================
        # Outcomes
        # =============================================================
        {
            "key": "customer_has_cover",
            "type": "business_outcome",
            "name": "Customer has appropriate cover",
            "description": (
                "The customer obtains insurance cover appropriate "
                "to their circumstances and risk."
            ),
            "attributes": {
                "description": ("Customers receive appropriate insurance protection."),
            },
        },
        {
            "key": "policy_issued",
            "type": "business_outcome",
            "name": "Policy issued",
            "description": ("A valid insurance policy has been successfully issued."),
            "attributes": {
                "description": (
                    "The customer has an active policy and associated documents."
                ),
            },
        },
        {
            "key": "claim_settled",
            "type": "business_outcome",
            "name": "Claim settled",
            "description": (
                "A valid claim has been assessed and settlement completed."
            ),
            "attributes": {
                "description": ("The customer's eligible claim has been resolved."),
            },
        },
        {
            "key": "premium_collected",
            "type": "business_outcome",
            "name": "Premium collected",
            "description": (
                "The organisation has successfully collected the "
                "required customer premium."
            ),
            "attributes": {
                "description": ("Expected premium revenue has been collected."),
            },
        },
        {
            "key": "customer_served",
            "type": "business_outcome",
            "name": "Customer served",
            "description": (
                "A customer enquiry or service need has been successfully " "resolved."
            ),
            "attributes": {
                "description": ("The customer's service need has been addressed."),
            },
        },
        # =============================================================
        # Applications
        # =============================================================
        {
            "key": "crm",
            "type": "application",
            "name": "Customer Relationship Management",
            "description": (
                "Application used to manage customer information and interactions."
            ),
            "attributes": {
                "vendor": "Example Software Co",
                "application_type": "Business application",
                "lifecycle_status": "Current",
                "criticality": "High",
                "purpose": ("Manage customer relationships and service interactions."),
            },
        },
        {
            "key": "policy_administration_system",
            "type": "application",
            "name": "Policy Administration System",
            "description": ("Core application used to manage insurance policies."),
            "attributes": {
                "vendor": "Example Insurance Systems",
                "application_type": "Business application",
                "lifecycle_status": "Current",
                "criticality": "Critical",
                "purpose": ("Create and maintain insurance policies."),
            },
        },
        {
            "key": "claims_management_system",
            "type": "application",
            "name": "Claims Management System",
            "description": (
                "Application used to manage claims from notification "
                "through settlement."
            ),
            "attributes": {
                "vendor": "Example Insurance Systems",
                "application_type": "Business application",
                "lifecycle_status": "Current",
                "criticality": "Critical",
                "purpose": ("Manage the end-to-end claims lifecycle."),
            },
        },
        {
            "key": "payment_gateway",
            "type": "application",
            "name": "Payment Gateway",
            "description": ("Service used to process customer payment transactions."),
            "attributes": {
                "vendor": "Example Payments",
                "application_type": "Integration",
                "lifecycle_status": "Current",
                "criticality": "High",
                "purpose": ("Process electronic customer payments."),
            },
        },
        {
            "key": "document_management_system",
            "type": "application",
            "name": "Document Management System",
            "description": (
                "Application used to create, store and retrieve documents."
            ),
            "attributes": {
                "vendor": "Example Content Systems",
                "application_type": "Business application",
                "lifecycle_status": "Current",
                "criticality": "High",
                "purpose": ("Manage customer and policy documentation."),
            },
        },
        {
            "key": "data_warehouse",
            "type": "application",
            "name": "Data Warehouse",
            "description": (
                "Central analytical data platform used for reporting " "and analysis."
            ),
            "attributes": {
                "vendor": "Example Data Platform",
                "application_type": "Platform",
                "lifecycle_status": "Current",
                "criticality": "High",
                "purpose": ("Provide trusted data for reporting and analytics."),
            },
        },
        {
            "key": "reporting_platform",
            "type": "application",
            "name": "Reporting Platform",
            "description": (
                "Application used to produce operational and management reports."
            ),
            "attributes": {
                "vendor": "Example Analytics",
                "application_type": "Business application",
                "lifecycle_status": "Current",
                "criticality": "Medium",
                "purpose": ("Deliver operational and management reporting."),
            },
        },
        # =============================================================
        # Information
        # =============================================================
        {
            "key": "customer_record",
            "type": "information_object",
            "name": "Customer Record",
            "description": (
                "Information describing a customer and their relationship "
                "with the organisation."
            ),
            "attributes": {
                "purpose": (
                    "Provide a trusted representation of customer information."
                ),
                "sensitivity": "Confidential",
            },
        },
        {
            "key": "quote",
            "type": "information_object",
            "name": "Quote",
            "description": ("Information representing an insurance quotation."),
            "attributes": {
                "purpose": "Record the proposed insurance cover and premium.",
                "sensitivity": "Confidential",
            },
        },
        {
            "key": "policy",
            "type": "information_object",
            "name": "Policy",
            "description": (
                "Information representing an active or historical " "insurance policy."
            ),
            "attributes": {
                "purpose": "Represent insurance cover and policy terms.",
                "sensitivity": "Confidential",
            },
        },
        {
            "key": "claim",
            "type": "information_object",
            "name": "Claim",
            "description": ("Information representing a customer's insurance claim."),
            "attributes": {
                "purpose": "Record the details and status of a claim.",
                "sensitivity": "Confidential",
            },
        },
        {
            "key": "claim_assessment",
            "type": "information_object",
            "name": "Claim Assessment",
            "description": (
                "Information documenting the assessment and decision "
                "associated with a claim."
            ),
            "attributes": {
                "purpose": ("Record the assessment supporting a claim decision."),
                "sensitivity": "Restricted",
            },
        },
        {
            "key": "payment",
            "type": "information_object",
            "name": "Payment",
            "description": (
                "Information representing a financial payment transaction."
            ),
            "attributes": {
                "purpose": "Record a customer or business payment.",
                "sensitivity": "Confidential",
            },
        },
        {
            "key": "policy_document",
            "type": "information_object",
            "name": "Policy Document",
            "description": ("A document containing the customer's policy information."),
            "attributes": {
                "purpose": "Provide customers with policy documentation.",
                "sensitivity": "Confidential",
            },
        },
        # =============================================================
        # Processes
        # =============================================================
        {
            "key": "quote_customer",
            "type": "business_process",
            "name": "Quote Customer",
            "description": (
                "Assess a customer's requirements and provide an "
                "appropriate insurance quotation."
            ),
            "attributes": {
                "owner": "Head of Sales",
                "purpose": ("Provide customers with an appropriate insurance quote."),
                "process_type": "Core",
                "criticality": "High",
                "lifecycle_status": "Current",
                "customer_facing": True,
            },
        },
        {
            "key": "underwrite_policy",
            "type": "business_process",
            "name": "Underwrite Policy",
            "description": (
                "Assess risk and determine whether proposed insurance "
                "cover should be accepted."
            ),
            "attributes": {
                "owner": "Chief Underwriting Officer",
                "purpose": (
                    "Make appropriate and commercially sound underwriting decisions."
                ),
                "process_type": "Core",
                "criticality": "Critical",
                "lifecycle_status": "Current",
                "customer_facing": False,
            },
        },
        {
            "key": "issue_policy",
            "type": "business_process",
            "name": "Issue Policy",
            "description": (
                "Create and issue an insurance policy following acceptance "
                "of the risk."
            ),
            "attributes": {
                "owner": "Policy Operations Manager",
                "purpose": ("Convert accepted insurance cover into an active policy."),
                "process_type": "Core",
                "criticality": "Critical",
                "lifecycle_status": "Current",
                "customer_facing": True,
            },
        },
        {
            "key": "manage_policy",
            "type": "business_process",
            "name": "Manage Policy",
            "description": (
                "Maintain policies and process changes throughout their lifecycle."
            ),
            "attributes": {
                "owner": "Policy Operations Manager",
                "purpose": ("Maintain accurate and effective customer policies."),
                "process_type": "Core",
                "criticality": "High",
                "lifecycle_status": "Current",
                "customer_facing": True,
            },
        },
        {
            "key": "handle_claim",
            "type": "business_process",
            "name": "Handle Claim",
            "description": ("Receive, assess and settle an insurance claim."),
            "attributes": {
                "owner": "Head of Claims",
                "purpose": ("Resolve valid customer claims fairly and efficiently."),
                "process_type": "Core",
                "criticality": "Critical",
                "lifecycle_status": "Current",
                "customer_facing": True,
            },
        },
        {
            "key": "collect_premium",
            "type": "business_process",
            "name": "Collect Premium",
            "description": ("Collect insurance premiums from customers."),
            "attributes": {
                "owner": "Finance Operations Manager",
                "purpose": ("Collect premiums accurately and efficiently."),
                "process_type": "Core",
                "criticality": "High",
                "lifecycle_status": "Current",
                "customer_facing": False,
            },
        },
        {
            "key": "manage_customer",
            "type": "business_process",
            "name": "Manage Customer",
            "description": (
                "Manage customer enquiries, service requests and "
                "relationship information."
            ),
            "attributes": {
                "owner": "Head of Customer Service",
                "purpose": ("Maintain effective customer relationships and service."),
                "process_type": "Core",
                "criticality": "High",
                "lifecycle_status": "Current",
                "customer_facing": True,
            },
        },
        {
            "key": "produce_management_reporting",
            "type": "business_process",
            "name": "Produce Management Reporting",
            "description": (
                "Produce trusted management information from operational data."
            ),
            "attributes": {
                "owner": "Head of Finance",
                "purpose": (
                    "Provide management with reliable information for decision making."
                ),
                "process_type": "Management",
                "criticality": "Medium",
                "lifecycle_status": "Current",
                "customer_facing": False,
            },
        },
        # =============================================================
        # Quote Customer activities
        # =============================================================
        {
            "key": "capture_customer_details",
            "type": "activity",
            "name": "Capture customer details",
            "description": (
                "Capture the customer's identity, contact and insurance requirements."
            ),
            "attributes": {
                "purpose": "Establish the information required to prepare a quote.",
                "activity_type": "Interaction",
                "automation_level": "Assisted",
                "criticality": "High",
            },
        },
        {
            "key": "assess_quote_risk",
            "type": "activity",
            "name": "Assess quote risk",
            "description": (
                "Assess the customer's risk information for quotation purposes."
            ),
            "attributes": {
                "purpose": "Determine the risk characteristics of the proposed cover.",
                "activity_type": "Decision",
                "automation_level": "Assisted",
                "criticality": "High",
            },
        },
        {
            "key": "calculate_premium",
            "type": "activity",
            "name": "Calculate premium",
            "description": (
                "Calculate the proposed premium for the customer's insurance cover."
            ),
            "attributes": {
                "purpose": "Determine an appropriate premium.",
                "activity_type": "Automated",
                "automation_level": "Fully automated",
                "criticality": "High",
            },
        },
        {
            "key": "review_quote",
            "type": "activity",
            "name": "Review quote",
            "description": (
                "Review the proposed quote before presenting it to the customer."
            ),
            "attributes": {
                "purpose": "Confirm the quote is appropriate and complete.",
                "activity_type": "Decision",
                "automation_level": "Manual",
                "criticality": "Medium",
            },
        },
        {
            "key": "present_quote",
            "type": "activity",
            "name": "Present quote",
            "description": ("Present the insurance quote to the customer."),
            "attributes": {
                "purpose": "Provide the customer with the proposed cover and premium.",
                "activity_type": "Interaction",
                "automation_level": "Assisted",
                "criticality": "Medium",
            },
        },
        # =============================================================
        # Underwrite Policy activities
        # =============================================================
        {
            "key": "validate_application",
            "type": "activity",
            "name": "Validate application",
            "description": (
                "Check that the insurance application contains the "
                "information required for underwriting."
            ),
            "attributes": {
                "purpose": "Confirm the application is complete and valid.",
                "activity_type": "Decision",
                "automation_level": "Assisted",
                "criticality": "High",
            },
        },
        {
            "key": "assess_underwriting_risk",
            "type": "activity",
            "name": "Assess underwriting risk",
            "description": (
                "Assess the risk associated with the proposed insurance cover."
            ),
            "attributes": {
                "purpose": "Determine the level and characteristics of risk.",
                "activity_type": "Decision",
                "automation_level": "Assisted",
                "criticality": "Critical",
            },
        },
        {
            "key": "refer_underwriting_decision",
            "type": "activity",
            "name": "Review underwriting referral",
            "description": (
                "Review risks that require additional underwriting consideration."
            ),
            "attributes": {
                "purpose": "Make decisions on risks outside standard rules.",
                "activity_type": "Decision",
                "automation_level": "Manual",
                "criticality": "High",
            },
        },
        {
            "key": "approve_cover",
            "type": "activity",
            "name": "Approve cover",
            "description": ("Approve the proposed insurance cover."),
            "attributes": {
                "purpose": "Make the final underwriting decision.",
                "activity_type": "Decision",
                "automation_level": "Manual",
                "criticality": "Critical",
            },
        },
        # =============================================================
        # Issue Policy activities
        # =============================================================
        {
            "key": "confirm_payment",
            "type": "activity",
            "name": "Confirm payment",
            "description": ("Confirm that the required payment has been received."),
            "attributes": {
                "purpose": "Confirm the financial condition for policy issue.",
                "activity_type": "Decision",
                "automation_level": "Highly automated",
                "criticality": "High",
            },
        },
        {
            "key": "create_policy",
            "type": "activity",
            "name": "Create policy",
            "description": ("Create the policy record following acceptance of cover."),
            "attributes": {
                "purpose": "Create an accurate policy record.",
                "activity_type": "Automated",
                "automation_level": "Fully automated",
                "criticality": "Critical",
            },
        },
        {
            "key": "generate_policy_documents",
            "type": "activity",
            "name": "Generate policy documents",
            "description": ("Generate the documentation associated with the policy."),
            "attributes": {
                "purpose": "Produce accurate policy documentation.",
                "activity_type": "Automated",
                "automation_level": "Fully automated",
                "criticality": "High",
            },
        },
        {
            "key": "notify_customer_policy_issued",
            "type": "activity",
            "name": "Notify customer of policy issue",
            "description": ("Notify the customer that their policy has been issued."),
            "attributes": {
                "purpose": "Confirm policy issue to the customer.",
                "activity_type": "Interaction",
                "automation_level": "Highly automated",
                "criticality": "Medium",
            },
        },
        # =============================================================
        # Manage Policy activities
        # =============================================================
        {
            "key": "receive_policy_change",
            "type": "activity",
            "name": "Receive policy change request",
            "description": ("Receive a request to change an existing policy."),
            "attributes": {
                "purpose": "Capture the customer's requested policy change.",
                "activity_type": "Interaction",
                "automation_level": "Assisted",
                "criticality": "Medium",
            },
        },
        {
            "key": "assess_policy_change",
            "type": "activity",
            "name": "Assess policy change",
            "description": (
                "Assess the impact and requirements of a requested policy change."
            ),
            "attributes": {
                "purpose": "Determine whether the requested change can be made.",
                "activity_type": "Decision",
                "automation_level": "Assisted",
                "criticality": "High",
            },
        },
        {
            "key": "update_policy",
            "type": "activity",
            "name": "Update policy",
            "description": ("Update the policy following approval of a change."),
            "attributes": {
                "purpose": "Maintain an accurate policy record.",
                "activity_type": "Automated",
                "automation_level": "Highly automated",
                "criticality": "High",
            },
        },
        # =============================================================
        # Claims activities
        # =============================================================
        {
            "key": "receive_claim",
            "type": "activity",
            "name": "Receive claim",
            "description": ("Receive and register a customer's insurance claim."),
            "attributes": {
                "purpose": "Capture the claim and begin the claims process.",
                "activity_type": "Interaction",
                "automation_level": "Assisted",
                "criticality": "Critical",
            },
        },
        {
            "key": "validate_claim",
            "type": "activity",
            "name": "Validate claim",
            "description": ("Validate the claim information and policy details."),
            "attributes": {
                "purpose": "Confirm that the claim can proceed to assessment.",
                "activity_type": "Decision",
                "automation_level": "Assisted",
                "criticality": "Critical",
            },
        },
        {
            "key": "assess_claim",
            "type": "activity",
            "name": "Assess claim",
            "description": (
                "Assess the circumstances, evidence and likely value of a claim."
            ),
            "attributes": {
                "purpose": "Determine the appropriate claim outcome.",
                "activity_type": "Decision",
                "automation_level": "Assisted",
                "criticality": "Critical",
            },
        },
        {
            "key": "determine_claim_settlement",
            "type": "activity",
            "name": "Determine claim settlement",
            "description": ("Determine the amount and terms of the claim settlement."),
            "attributes": {
                "purpose": "Determine the appropriate settlement.",
                "activity_type": "Decision",
                "automation_level": "Assisted",
                "criticality": "Critical",
            },
        },
        {
            "key": "authorise_claim_payment",
            "type": "activity",
            "name": "Authorise claim payment",
            "description": ("Authorise payment of an approved claim settlement."),
            "attributes": {
                "purpose": "Approve the financial settlement of the claim.",
                "activity_type": "Decision",
                "automation_level": "Manual",
                "criticality": "High",
            },
        },
        {
            "key": "notify_claim_outcome",
            "type": "activity",
            "name": "Notify customer of claim outcome",
            "description": ("Notify the customer of the claim assessment and outcome."),
            "attributes": {
                "purpose": "Communicate the claim outcome to the customer.",
                "activity_type": "Interaction",
                "automation_level": "Assisted",
                "criticality": "High",
            },
        },
        # =============================================================
        # Premium activities
        # =============================================================
        {
            "key": "calculate_premium_due",
            "type": "activity",
            "name": "Calculate premium due",
            "description": ("Determine the amount of premium due from the customer."),
            "attributes": {
                "purpose": "Determine the customer's premium obligation.",
                "activity_type": "Automated",
                "automation_level": "Fully automated",
                "criticality": "High",
            },
        },
        {
            "key": "request_customer_payment",
            "type": "activity",
            "name": "Request customer payment",
            "description": ("Request payment of the premium from the customer."),
            "attributes": {
                "purpose": "Initiate collection of the premium.",
                "activity_type": "Interaction",
                "automation_level": "Highly automated",
                "criticality": "High",
            },
        },
        {
            "key": "process_premium_payment",
            "type": "activity",
            "name": "Process premium payment",
            "description": ("Process the customer's premium payment."),
            "attributes": {
                "purpose": "Collect and record premium payment.",
                "activity_type": "Automated",
                "automation_level": "Fully automated",
                "criticality": "High",
            },
        },
        # =============================================================
        # Customer service activities
        # =============================================================
        {
            "key": "receive_customer_enquiry",
            "type": "activity",
            "name": "Receive customer enquiry",
            "description": (
                "Receive and classify a customer enquiry or service request."
            ),
            "attributes": {
                "purpose": "Understand the customer's service requirement.",
                "activity_type": "Interaction",
                "automation_level": "Assisted",
                "criticality": "Medium",
            },
        },
        {
            "key": "resolve_customer_enquiry",
            "type": "activity",
            "name": "Resolve customer enquiry",
            "description": ("Investigate and resolve the customer's enquiry."),
            "attributes": {
                "purpose": "Resolve the customer's service need.",
                "activity_type": "Interaction",
                "automation_level": "Assisted",
                "criticality": "High",
            },
        },
        # =============================================================
        # Reporting activities
        # =============================================================
        {
            "key": "extract_reporting_data",
            "type": "activity",
            "name": "Extract reporting data",
            "description": ("Extract trusted operational information for reporting."),
            "attributes": {
                "purpose": "Prepare data for management reporting.",
                "activity_type": "Automated",
                "automation_level": "Fully automated",
                "criticality": "Medium",
            },
        },
        {
            "key": "produce_management_report",
            "type": "activity",
            "name": "Produce management report",
            "description": ("Produce management reporting and analytical information."),
            "attributes": {
                "purpose": "Provide management with useful information.",
                "activity_type": "Automated",
                "automation_level": "Highly automated",
                "criticality": "Medium",
            },
        },
    ],
    # -----------------------------------------------------------------
    # Sample relationships
    # -----------------------------------------------------------------
    "relationships": [
        # =============================================================
        # Process -> Activity
        # =============================================================
        # Quote Customer
        {
            "type": "contains",
            "subject": "quote_customer",
            "object": "capture_customer_details",
        },
        {
            "type": "contains",
            "subject": "quote_customer",
            "object": "assess_quote_risk",
        },
        {
            "type": "contains",
            "subject": "quote_customer",
            "object": "calculate_premium",
        },
        {
            "type": "contains",
            "subject": "quote_customer",
            "object": "review_quote",
        },
        {
            "type": "contains",
            "subject": "quote_customer",
            "object": "present_quote",
        },
        # Underwrite Policy
        {
            "type": "contains",
            "subject": "underwrite_policy",
            "object": "validate_application",
        },
        {
            "type": "contains",
            "subject": "underwrite_policy",
            "object": "assess_underwriting_risk",
        },
        {
            "type": "contains",
            "subject": "underwrite_policy",
            "object": "refer_underwriting_decision",
        },
        {
            "type": "contains",
            "subject": "underwrite_policy",
            "object": "approve_cover",
        },
        # Issue Policy
        {
            "type": "contains",
            "subject": "issue_policy",
            "object": "confirm_payment",
        },
        {
            "type": "contains",
            "subject": "issue_policy",
            "object": "create_policy",
        },
        {
            "type": "contains",
            "subject": "issue_policy",
            "object": "generate_policy_documents",
        },
        {
            "type": "contains",
            "subject": "issue_policy",
            "object": "notify_customer_policy_issued",
        },
        # Manage Policy
        {
            "type": "contains",
            "subject": "manage_policy",
            "object": "receive_policy_change",
        },
        {
            "type": "contains",
            "subject": "manage_policy",
            "object": "assess_policy_change",
        },
        {
            "type": "contains",
            "subject": "manage_policy",
            "object": "update_policy",
        },
        # Handle Claim
        {
            "type": "contains",
            "subject": "handle_claim",
            "object": "receive_claim",
        },
        {
            "type": "contains",
            "subject": "handle_claim",
            "object": "validate_claim",
        },
        {
            "type": "contains",
            "subject": "handle_claim",
            "object": "assess_claim",
        },
        {
            "type": "contains",
            "subject": "handle_claim",
            "object": "determine_claim_settlement",
        },
        {
            "type": "contains",
            "subject": "handle_claim",
            "object": "authorise_claim_payment",
        },
        {
            "type": "contains",
            "subject": "handle_claim",
            "object": "notify_claim_outcome",
        },
        # Collect Premium
        {
            "type": "contains",
            "subject": "collect_premium",
            "object": "calculate_premium_due",
        },
        {
            "type": "contains",
            "subject": "collect_premium",
            "object": "request_customer_payment",
        },
        {
            "type": "contains",
            "subject": "collect_premium",
            "object": "process_premium_payment",
        },
        # Manage Customer
        {
            "type": "contains",
            "subject": "manage_customer",
            "object": "receive_customer_enquiry",
        },
        {
            "type": "contains",
            "subject": "manage_customer",
            "object": "resolve_customer_enquiry",
        },
        # Reporting
        {
            "type": "contains",
            "subject": "produce_management_reporting",
            "object": "extract_reporting_data",
        },
        {
            "type": "contains",
            "subject": "produce_management_reporting",
            "object": "produce_management_report",
        },
        # =============================================================
        # Activity -> Team
        # =============================================================
        {
            "type": "performed_by",
            "subject": "capture_customer_details",
            "object": "sales",
        },
        {
            "type": "performed_by",
            "subject": "assess_quote_risk",
            "object": "underwriting",
        },
        {
            "type": "performed_by",
            "subject": "calculate_premium",
            "object": "underwriting",
        },
        {
            "type": "performed_by",
            "subject": "review_quote",
            "object": "sales",
        },
        {
            "type": "performed_by",
            "subject": "present_quote",
            "object": "sales",
        },
        {
            "type": "performed_by",
            "subject": "validate_application",
            "object": "underwriting",
        },
        {
            "type": "performed_by",
            "subject": "assess_underwriting_risk",
            "object": "underwriting",
        },
        {
            "type": "performed_by",
            "subject": "refer_underwriting_decision",
            "object": "underwriting",
        },
        {
            "type": "performed_by",
            "subject": "approve_cover",
            "object": "underwriting",
        },
        {
            "type": "performed_by",
            "subject": "confirm_payment",
            "object": "finance_operations",
        },
        {
            "type": "performed_by",
            "subject": "create_policy",
            "object": "technology_services",
        },
        {
            "type": "performed_by",
            "subject": "generate_policy_documents",
            "object": "technology_services",
        },
        {
            "type": "performed_by",
            "subject": "notify_customer_policy_issued",
            "object": "customer_service",
        },
        {
            "type": "performed_by",
            "subject": "receive_policy_change",
            "object": "customer_service",
        },
        {
            "type": "performed_by",
            "subject": "assess_policy_change",
            "object": "underwriting",
        },
        {
            "type": "performed_by",
            "subject": "update_policy",
            "object": "technology_services",
        },
        {
            "type": "performed_by",
            "subject": "receive_claim",
            "object": "claims",
        },
        {
            "type": "performed_by",
            "subject": "validate_claim",
            "object": "claims",
        },
        {
            "type": "performed_by",
            "subject": "assess_claim",
            "object": "claims",
        },
        {
            "type": "performed_by",
            "subject": "determine_claim_settlement",
            "object": "claims",
        },
        {
            "type": "performed_by",
            "subject": "authorise_claim_payment",
            "object": "finance_operations",
        },
        {
            "type": "performed_by",
            "subject": "notify_claim_outcome",
            "object": "claims",
        },
        {
            "type": "performed_by",
            "subject": "calculate_premium_due",
            "object": "finance_operations",
        },
        {
            "type": "performed_by",
            "subject": "request_customer_payment",
            "object": "finance_operations",
        },
        {
            "type": "performed_by",
            "subject": "process_premium_payment",
            "object": "finance_operations",
        },
        {
            "type": "performed_by",
            "subject": "receive_customer_enquiry",
            "object": "customer_service",
        },
        {
            "type": "performed_by",
            "subject": "resolve_customer_enquiry",
            "object": "customer_service",
        },
        {
            "type": "performed_by",
            "subject": "extract_reporting_data",
            "object": "data_analytics",
        },
        {
            "type": "performed_by",
            "subject": "produce_management_report",
            "object": "data_analytics",
        },
        # =============================================================
        # Activity -> Application
        # =============================================================
        {
            "type": "uses",
            "subject": "capture_customer_details",
            "object": "crm",
        },
        {
            "type": "uses",
            "subject": "assess_quote_risk",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "calculate_premium",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "review_quote",
            "object": "crm",
        },
        {
            "type": "uses",
            "subject": "present_quote",
            "object": "crm",
        },
        {
            "type": "uses",
            "subject": "validate_application",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "assess_underwriting_risk",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "refer_underwriting_decision",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "approve_cover",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "confirm_payment",
            "object": "payment_gateway",
        },
        {
            "type": "uses",
            "subject": "create_policy",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "generate_policy_documents",
            "object": "document_management_system",
        },
        {
            "type": "uses",
            "subject": "notify_customer_policy_issued",
            "object": "crm",
        },
        {
            "type": "uses",
            "subject": "receive_policy_change",
            "object": "crm",
        },
        {
            "type": "uses",
            "subject": "assess_policy_change",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "update_policy",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "receive_claim",
            "object": "claims_management_system",
        },
        {
            "type": "uses",
            "subject": "validate_claim",
            "object": "claims_management_system",
        },
        {
            "type": "uses",
            "subject": "assess_claim",
            "object": "claims_management_system",
        },
        {
            "type": "uses",
            "subject": "determine_claim_settlement",
            "object": "claims_management_system",
        },
        {
            "type": "uses",
            "subject": "authorise_claim_payment",
            "object": "payment_gateway",
        },
        {
            "type": "uses",
            "subject": "notify_claim_outcome",
            "object": "claims_management_system",
        },
        {
            "type": "uses",
            "subject": "calculate_premium_due",
            "object": "policy_administration_system",
        },
        {
            "type": "uses",
            "subject": "request_customer_payment",
            "object": "payment_gateway",
        },
        {
            "type": "uses",
            "subject": "process_premium_payment",
            "object": "payment_gateway",
        },
        {
            "type": "uses",
            "subject": "receive_customer_enquiry",
            "object": "crm",
        },
        {
            "type": "uses",
            "subject": "resolve_customer_enquiry",
            "object": "crm",
        },
        {
            "type": "uses",
            "subject": "extract_reporting_data",
            "object": "data_warehouse",
        },
        {
            "type": "uses",
            "subject": "produce_management_report",
            "object": "reporting_platform",
        },
        # =============================================================
        # Application -> Capability
        # =============================================================
        {
            "type": "supports",
            "subject": "crm",
            "object": "customer_management",
        },
        {
            "type": "supports",
            "subject": "policy_administration_system",
            "object": "policy_administration",
        },
        {
            "type": "supports",
            "subject": "policy_administration_system",
            "object": "underwriting_capability",
        },
        {
            "type": "supports",
            "subject": "claims_management_system",
            "object": "claims_management",
        },
        {
            "type": "supports",
            "subject": "payment_gateway",
            "object": "payments",
        },
        {
            "type": "supports",
            "subject": "document_management_system",
            "object": "document_management",
        },
        {
            "type": "supports",
            "subject": "data_warehouse",
            "object": "reporting_analytics",
        },
        {
            "type": "supports",
            "subject": "reporting_platform",
            "object": "reporting_analytics",
        },
        # =============================================================
        # Process -> Outcome
        # =============================================================
        {
            "type": "delivers",
            "subject": "quote_customer",
            "object": "customer_has_cover",
        },
        {
            "type": "delivers",
            "subject": "underwrite_policy",
            "object": "customer_has_cover",
        },
        {
            "type": "delivers",
            "subject": "issue_policy",
            "object": "policy_issued",
        },
        {
            "type": "delivers",
            "subject": "handle_claim",
            "object": "claim_settled",
        },
        {
            "type": "delivers",
            "subject": "collect_premium",
            "object": "premium_collected",
        },
        {
            "type": "delivers",
            "subject": "manage_customer",
            "object": "customer_served",
        },
        # =============================================================
        # Process -> Customer
        # =============================================================
        {
            "type": "serves",
            "subject": "quote_customer",
            "object": "individual_customer",
        },
        {
            "type": "serves",
            "subject": "quote_customer",
            "object": "small_business_customer",
        },
        {
            "type": "serves",
            "subject": "quote_customer",
            "object": "corporate_customer",
        },
        {
            "type": "serves",
            "subject": "issue_policy",
            "object": "individual_customer",
        },
        {
            "type": "serves",
            "subject": "handle_claim",
            "object": "individual_customer",
        },
        {
            "type": "serves",
            "subject": "handle_claim",
            "object": "small_business_customer",
        },
        {
            "type": "serves",
            "subject": "manage_customer",
            "object": "individual_customer",
        },
        {
            "type": "serves",
            "subject": "manage_customer",
            "object": "small_business_customer",
        },
        {
            "type": "serves",
            "subject": "manage_customer",
            "object": "corporate_customer",
        },
        # =============================================================
        # Process -> Owner
        # =============================================================
        {
            "type": "owned_by",
            "subject": "quote_customer",
            "object": "sales",
        },
        {
            "type": "owned_by",
            "subject": "underwrite_policy",
            "object": "underwriting",
        },
        {
            "type": "owned_by",
            "subject": "issue_policy",
            "object": "customer_service",
        },
        {
            "type": "owned_by",
            "subject": "manage_policy",
            "object": "customer_service",
        },
        {
            "type": "owned_by",
            "subject": "handle_claim",
            "object": "claims",
        },
        {
            "type": "owned_by",
            "subject": "collect_premium",
            "object": "finance_operations",
        },
        {
            "type": "owned_by",
            "subject": "manage_customer",
            "object": "customer_service",
        },
        {
            "type": "owned_by",
            "subject": "produce_management_reporting",
            "object": "data_analytics",
        },
        # =============================================================
        # Team -> Business Unit
        # =============================================================
        {
            "type": "belongs_to",
            "subject": "sales",
            "object": "customer_operations",
        },
        {
            "type": "belongs_to",
            "subject": "customer_service",
            "object": "customer_operations",
        },
        {
            "type": "belongs_to",
            "subject": "underwriting",
            "object": "insurance_operations",
        },
        {
            "type": "belongs_to",
            "subject": "claims",
            "object": "insurance_operations",
        },
        {
            "type": "belongs_to",
            "subject": "finance_operations",
            "object": "finance",
        },
        {
            "type": "belongs_to",
            "subject": "technology_services",
            "object": "technology",
        },
        {
            "type": "belongs_to",
            "subject": "data_analytics",
            "object": "technology",
        },
        # =============================================================
        # Activity -> Information created
        # =============================================================
        {
            "type": "creates",
            "subject": "capture_customer_details",
            "object": "customer_record",
        },
        {
            "type": "creates",
            "subject": "review_quote",
            "object": "quote",
        },
        {
            "type": "creates",
            "subject": "create_policy",
            "object": "policy",
        },
        {
            "type": "creates",
            "subject": "generate_policy_documents",
            "object": "policy_document",
        },
        {
            "type": "creates",
            "subject": "receive_claim",
            "object": "claim",
        },
        {
            "type": "creates",
            "subject": "assess_claim",
            "object": "claim_assessment",
        },
        {
            "type": "creates",
            "subject": "process_premium_payment",
            "object": "payment",
        },
        # =============================================================
        # Activity -> Information used
        # =============================================================
        {
            "type": "uses_information",
            "subject": "assess_quote_risk",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "calculate_premium",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "review_quote",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "review_quote",
            "object": "quote",
        },
        {
            "type": "uses_information",
            "subject": "validate_application",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "assess_underwriting_risk",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "approve_cover",
            "object": "quote",
        },
        {
            "type": "uses_information",
            "subject": "confirm_payment",
            "object": "payment",
        },
        {
            "type": "uses_information",
            "subject": "create_policy",
            "object": "quote",
        },
        {
            "type": "uses_information",
            "subject": "create_policy",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "generate_policy_documents",
            "object": "policy",
        },
        {
            "type": "uses_information",
            "subject": "receive_policy_change",
            "object": "policy",
        },
        {
            "type": "uses_information",
            "subject": "assess_policy_change",
            "object": "policy",
        },
        {
            "type": "uses_information",
            "subject": "update_policy",
            "object": "policy",
        },
        {
            "type": "uses_information",
            "subject": "validate_claim",
            "object": "claim",
        },
        {
            "type": "uses_information",
            "subject": "validate_claim",
            "object": "policy",
        },
        {
            "type": "uses_information",
            "subject": "assess_claim",
            "object": "claim",
        },
        {
            "type": "uses_information",
            "subject": "assess_claim",
            "object": "policy",
        },
        {
            "type": "uses_information",
            "subject": "determine_claim_settlement",
            "object": "claim_assessment",
        },
        {
            "type": "uses_information",
            "subject": "authorise_claim_payment",
            "object": "claim_assessment",
        },
        {
            "type": "uses_information",
            "subject": "calculate_premium_due",
            "object": "policy",
        },
        {
            "type": "uses_information",
            "subject": "process_premium_payment",
            "object": "payment",
        },
        {
            "type": "uses_information",
            "subject": "receive_customer_enquiry",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "resolve_customer_enquiry",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "extract_reporting_data",
            "object": "customer_record",
        },
        {
            "type": "uses_information",
            "subject": "extract_reporting_data",
            "object": "policy",
        },
        {
            "type": "uses_information",
            "subject": "extract_reporting_data",
            "object": "claim",
        },
        {
            "type": "uses_information",
            "subject": "produce_management_report",
            "object": "customer_record",
        },
        # =============================================================
        # Application -> Application
        # =============================================================
        {
            "type": "depends_on",
            "subject": "claims_management_system",
            "object": "policy_administration_system",
        },
        {
            "type": "depends_on",
            "subject": "claims_management_system",
            "object": "document_management_system",
        },
        {
            "type": "depends_on",
            "subject": "policy_administration_system",
            "object": "document_management_system",
        },
        {
            "type": "depends_on",
            "subject": "reporting_platform",
            "object": "data_warehouse",
        },
    ],
}

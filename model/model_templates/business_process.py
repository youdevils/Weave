"""
Business Process model template.

This is a complete ontology definition for the Business Process
starting point.

The template is deliberately declarative. It describes WHAT the
ontology contains; template instantiation services are responsible
for turning this definition into database records.
"""

BUSINESS_PROCESS_TEMPLATE = {
    "key": "business_process",
    "name": "Business Process",
    "description": (
        "A model for understanding how business processes are performed "
        "by people and supported by applications."
    ),
    # -----------------------------------------------------------------
    # Object types
    # -----------------------------------------------------------------
    "object_types": [
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
                    "description": ("The broad type of business process."),
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
            ],
        },
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
            ],
        },
        {
            "key": "application",
            "name": "Application",
            "description": (
                "A software application used to support or enable " "business activity."
            ),
            "sort_order": 30,
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
                    "sort_order": 30,
                    "config": {},
                },
            ],
        },
        {
            "key": "team",
            "name": "Team",
            "description": (
                "A group of people responsible for performing or "
                "supporting business activities."
            ),
            "sort_order": 40,
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
                    "description": ("The broad type of team."),
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
    ],
    # -----------------------------------------------------------------
    # Relationship types
    # -----------------------------------------------------------------
    "relationship_types": [
        {
            "key": "contains",
            "name": "Contains",
            "description": ("Indicates that a business process contains an activity."),
            "sort_order": 10,
            "rules": [
                {
                    "subject_type": "business_process",
                    "object_type": "activity",
                    # A process contains one or more activities.
                    "subject_minimum": 1,
                    "subject_maximum": None,
                    "subject_required": True,
                    # An activity belongs to one process.
                    "object_minimum": 1,
                    "object_maximum": 1,
                    "object_required": True,
                },
            ],
            "attributes": [],
        },
        {
            "key": "uses",
            "name": "Uses",
            "description": (
                "Indicates that an activity uses an application " "to perform its work."
            ),
            "sort_order": 20,
            "rules": [
                {
                    "subject_type": "activity",
                    "object_type": "application",
                    # An activity may use zero or more applications.
                    "subject_minimum": 0,
                    "subject_maximum": None,
                    "subject_required": False,
                    # An application may support zero or more activities.
                    "object_minimum": 0,
                    "object_maximum": None,
                    "object_required": False,
                },
            ],
            "attributes": [],
        },
        {
            "key": "performed_by",
            "name": "Performed by",
            "description": ("Indicates that an activity is performed by a team."),
            "sort_order": 30,
            "rules": [
                {
                    "subject_type": "activity",
                    "object_type": "team",
                    # An activity may be performed by one or more teams.
                    "subject_minimum": 0,
                    "subject_maximum": None,
                    "subject_required": False,
                    # A team may perform zero or more activities.
                    "object_minimum": 0,
                    "object_maximum": None,
                    "object_required": False,
                },
            ],
            "attributes": [],
        },
    ],
}

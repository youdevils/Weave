"""Delivery Project model template.

A complete, populated showcase model for a medium-sized fictional New Zealand
retail EFTPOS modernisation project. The model deliberately connects delivery
objects to the operational domain they change so the graph can be explored as
project structure, impact map, dependency map, transition model and delivery
status view.

The template is deliberately declarative. Template instantiation services are
responsible for turning the definition into database records.

Sample object keys are template-local references used to create the sample
relationships. They are not persisted as Object fields.
"""


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


PICK_STATUS = ["Not started", "In progress", "At risk", "Complete"]
CRITICALITY = ["Low", "Medium", "High", "Critical"]

DELIVERY_PROJECT_TEMPLATE = {
    "key": "delivery_project",
    "name": "Delivery Project",
    "description": (
        "A model for understanding a delivery project together with the business "
        "processes, applications, teams, capabilities and outcomes that the project "
        "changes, enables or supports."
    ),

    "object_types": [
        _otype(
            "project", "Project",
            "A defined delivery effort established to make a material change to the organisation.", 10,
            [
                _attr("status", "Status", "choice", "The current delivery stage of the project.", 10,
                      choices=["Planned", "In delivery", "Pilot", "Rollout", "Complete"]),
                _attr("purpose", "Purpose", "text", "The business problem and intended outcome of the project.", 20),
                _attr("sponsor", "Sponsor", "text", "The senior business role accountable for sponsoring the project.", 30),
                _attr("criticality", "Criticality", "choice", "The operational importance of completing the project successfully.", 40,
                      choices=CRITICALITY),
            ],
        ),
        _otype(
            "workstream", "Workstream",
            "A coherent area of delivery work grouping related changes and delivery activity.", 20,
            [
                _attr("status", "Status", "choice", "The current delivery state of the workstream.", 10,
                      choices=PICK_STATUS),
                _attr("purpose", "Purpose", "text", "The outcome this workstream is responsible for delivering.", 20),
                _attr("lead", "Lead", "text", "The role responsible for coordinating the workstream.", 30),
                _attr("criticality", "Criticality", "choice", "The importance of the workstream to successful delivery.", 40,
                      choices=CRITICALITY),
            ],
        ),
        _otype(
            "change", "Change",
            "A defined change the project makes to technology, processes, operations or the customer experience.", 30,
            [
                _attr("status", "Status", "choice", "The current delivery state of the change.", 10,
                      choices=PICK_STATUS),
                _attr("change_type", "Change type", "choice", "The broad nature of the change.", 20,
                      choices=["Technology", "Process", "Operational", "Data", "Customer"]),
                _attr("business_value", "Business value", "text", "The practical business improvement expected when the change is operating successfully.", 30),
                _attr("target_state", "Target state", "text", "A description of what will be different after the change has been implemented.", 40),
            ],
        ),
        _otype(
            "deliverable", "Deliverable",
            "A tangible product, capability or piece of work required to implement a change.", 40,
            [
                _attr("status", "Status", "choice", "The current delivery state of the deliverable.", 10,
                      choices=PICK_STATUS),
                _attr("deliverable_type", "Deliverable type", "choice", "The broad type of deliverable.", 20,
                      choices=["Technology", "Integration", "Process", "Operational", "Documentation"]),
                _attr("purpose", "Purpose", "text", "The outcome the deliverable must provide.", 30),
                _attr("acceptance_criteria", "Acceptance criteria", "text", "The conditions that must be satisfied for the deliverable to be accepted as complete.", 40),
            ],
        ),
        _otype(
            "test", "Test",
            "A defined verification activity used to establish whether a delivery item works as intended and is ready to progress.", 50,
            [
                _attr("status", "Status", "choice", "The current execution state or result of the test.", 10,
                      choices=["Not started", "In progress", "Passed", "Failed"]),
                _attr("test_type", "Test type", "choice", "The broad type of verification being performed.", 20,
                      choices=["Integration", "Operational", "User acceptance", "Resilience", "Reconciliation"]),
                _attr("purpose", "Purpose", "text", "What the test is intended to prove.", 30),
            ],
        ),
        _otype(
            "release", "Release",
            "A controlled deployment of a delivery item into an environment or operational population.", 60,
            [
                _attr("status", "Status", "choice", "The current release state.", 10,
                      choices=["Planned", "Approved", "Deployed", "Verified", "Rolled back"]),
                _attr("purpose", "Purpose", "text", "What the release is intended to put into operation.", 20),
                _attr("environment", "Environment", "choice", "The operational context in which the release is deployed.", 30,
                      choices=["Test", "Pilot", "Production"]),
            ],
        ),
        _otype(
            "decision", "Decision",
            "A material project decision that establishes or constrains how a change will be delivered.", 70,
            [
                _attr("status", "Status", "choice", "The current status of the decision.", 10,
                      choices=["Proposed", "Approved", "Superseded"]),
                _attr("decision_type", "Decision type", "choice", "The broad type of decision.", 20,
                      choices=["Architecture", "Delivery", "Operational", "Scope", "Risk"]),
                _attr("rationale", "Rationale", "text", "The reasoning or evidence behind the decision.", 30),
            ],
        ),
        _otype(
            "business_process", "Business Process",
            "A defined sequence of work performed by people and systems to achieve a business outcome.", 80,
            [
                _attr("purpose", "Purpose", "text", "The business outcome the process exists to achieve.", 10),
                _attr("criticality", "Criticality", "choice", "The importance of the process to store operations.", 20,
                      choices=CRITICALITY),
                _attr("customer_facing", "Customer facing", "boolean", "Whether the process directly affects the customer experience.", 30),
            ],
        ),
        _otype(
            "application", "Application",
            "A software application or technical service that supports business activity or enables a delivery capability.", 90,
            [
                _attr("vendor", "Vendor", "text", "The organisation providing or maintaining the application.", 10),
                _attr("application_type", "Application type", "choice", "The broad category of application.", 20,
                      choices=["Business application", "Platform", "Integration", "Infrastructure"]),
                _attr("lifecycle_status", "Lifecycle status", "choice", "The current lifecycle position of the application.", 30,
                      choices=["Current", "Planned", "Retiring", "Retired"]),
                _attr("criticality", "Criticality", "choice", "The operational importance of the application.", 40,
                      choices=CRITICALITY),
                _attr("purpose", "Purpose", "text", "The primary business or technical purpose of the application.", 50),
            ],
        ),
        _otype(
            "team", "Team",
            "A group of people accountable for delivering, operating or supporting part of the business or technology landscape.", 100,
            [
                _attr("purpose", "Purpose", "text", "The team's primary responsibility in the organisation.", 10),
                _attr("team_type", "Team type", "choice", "The broad type of team.", 20,
                      choices=["Business", "Technology", "Operations", "External"]),
            ],
        ),
        _otype(
            "business_unit", "Business Unit",
            "An organisational unit accountable for a meaningful area of business operations or corporate support.", 110,
            [_attr("purpose", "Purpose", "text", "The primary purpose of the business unit.", 10)],
        ),
        _otype(
            "business_capability", "Business Capability",
            "An ability the organisation requires to operate its retail business and serve customers.", 120,
            [
                _attr("purpose", "Purpose", "text", "The business value of the capability.", 10),
                _attr("strategic_importance", "Strategic importance", "choice", "The importance of the capability to the organisation.", 20,
                      choices=CRITICALITY),
            ],
        ),
        _otype(
            "business_outcome", "Business Outcome",
            "A meaningful result the organisation expects to achieve through its processes or delivery changes.", 130,
            [_attr("description", "Outcome description", "text", "A detailed description of the desired business outcome.", 10)],
        ),
        _otype(
            "information_object", "Information Object",
            "A meaningful unit of information created, exchanged or maintained by a business process or application.", 140,
            [
                _attr("purpose", "Purpose", "text", "The role the information plays in the business or delivery context.", 10),
                _attr("sensitivity", "Sensitivity", "choice", "The general sensitivity of the information.", 20,
                      choices=["Public", "Internal", "Confidential", "Restricted"]),
            ],
        ),
        _otype(
            "store_cluster", "Store Cluster",
            "A defined group of retail stores treated as a common operational population for rollout and support.", 150,
            [
                _attr("store_type", "Store type", "choice", "The broad operating profile of the stores.", 10,
                      choices=["Metropolitan", "Regional", "High volume", "Mixed"]),
                _attr("rollout_status", "Rollout status", "choice", "The current EFTPOS rollout position for the store cluster.", 20,
                      choices=["Not started", "Pilot", "Rolling out", "Live"]),
            ],
        ),
    ],

    "relationship_types": [
        _rtype("contains", "Contains", "Indicates that a delivery object forms part of another delivery object.", 10, [
            _rule("project", "workstream", 1, None, 1, 1),
            _rule("workstream", "change", 1, None, 1, 1),
        ]),
        _rtype("has_deliverable", "Has deliverable", "Indicates that a change is implemented through one or more deliverables.", 20, [
            _rule("change", "deliverable", 1, None, 1, 1),
        ]),
        _rtype("has_test", "Has test", "Indicates that a change has one or more defined verification activities.", 30, [
            _rule("change", "test", 1, None, 1, 1),
        ]),
        _rtype("has_release", "Has release", "Indicates that a change is implemented through controlled releases.", 40, [
            _rule("change", "release", 0, None, 1, 1),
        ]),
        _rtype("applies_to", "Applies to", "Indicates that a project decision applies to one or more delivery changes.", 50, [
            _rule("decision", "change", 0, None, 0, None),
        ]),
        _rtype("made_by", "Made by", "Indicates the team responsible for making a project decision.", 60, [
            _rule("decision", "team", 1, 1, 0, None),
        ]),
        _rtype("owned_by", "Owned by", "Indicates the team accountable for a delivery object or operational asset.", 70, [
            _rule("project", "team", 1, 1, 0, None),
            _rule("workstream", "team", 1, 1, 0, None),
            _rule("change", "team", 1, 1, 0, None),
            _rule("deliverable", "team", 1, 1, 0, None),
            _rule("application", "team", 1, 1, 0, None),
            _rule("business_process", "team", 1, 1, 0, None),
        ]),
        _rtype("validates", "Validates", "Indicates that a test verifies a deliverable.", 80, [
            _rule("test", "deliverable", 1, 1, 1, None),
        ]),
        _rtype("executed_by", "Executed by", "Indicates the team responsible for executing a test.", 90, [
            _rule("test", "team", 1, 1, 0, None),
        ]),
        _rtype("deploys", "Deploys", "Indicates that a release deploys one or more applications.", 100, [
            _rule("release", "application", 1, None, 0, None),
        ]),
        _rtype("deployed_to", "Deployed to", "Indicates the store population receiving a release.", 110, [
            _rule("release", "store_cluster", 0, None, 0, None),
        ]),
        _rtype("approved_by", "Approved by", "Indicates the team providing operational approval for a release.", 120, [
            _rule("release", "team", 0, None, 0, None),
        ]),
        _rtype("rolls_out_to", "Rolls out to", "Indicates the store populations included in a delivery change rollout.", 125, [
            _rule("change", "store_cluster", 0, None, 0, None),
        ]),
        _rtype("affects", "Affects", "Indicates that a delivery change alters or materially impacts an existing domain element.", 130, [
            _rule("change", "business_process", 0, None, 0, None),
            _rule("change", "application", 0, None, 0, None),
            _rule("change", "team", 0, None, 0, None),
            _rule("change", "business_capability", 0, None, 0, None),
        ]),
        _rtype("delivers", "Delivers", "Indicates that a delivery change contributes directly to a business outcome.", 140, [
            _rule("change", "business_outcome", 0, None, 0, None),
        ]),
        _rtype("uses", "Uses", "Indicates the application currently used by a business process.", 150, [
            _rule("business_process", "application", 0, None, 0, None),
        ]),
        _rtype("will_use", "Will use", "Indicates the application intended to support a business process in the target state.", 160, [
            _rule("business_process", "application", 0, None, 0, None),
        ]),
        _rtype("replaces", "Replaces", "Indicates that one application is the intended replacement for another.", 170, [
            _rule("application", "application", 0, None, 0, 1),
        ]),
        _rtype("supports", "Supports", "Indicates that an application or business process supports a business capability.", 180, [
            _rule("application", "business_capability", 0, None, 0, None),
            _rule("business_process", "business_capability", 0, None, 0, None),
        ]),
        _rtype("depends_on", "Depends on", "Indicates that an application relies on another application or service.", 190, [
            _rule("application", "application", 0, None, 0, None),
        ]),
        _rtype("operated_by", "Operated by", "Indicates the team responsible for operating an application or service.", 200, [
            _rule("application", "team", 0, 1, 0, None),
        ]),
        _rtype("belongs_to", "Belongs to", "Indicates the business unit to which a team belongs.", 210, [
            _rule("team", "business_unit", 1, 1, 0, None),
        ]),
        _rtype("performed_by", "Performed by", "Indicates the team that performs a business process.", 220, [
            _rule("business_process", "team", 1, None, 0, None),
        ]),
        _rtype("delivers_process_outcome", "Delivers outcome", "Indicates that a business process contributes to a business outcome.", 230, [
            _rule("business_process", "business_outcome", 0, None, 0, None),
        ]),
        _rtype("creates_information", "Creates", "Indicates that a process or application creates an information object.", 240, [
            _rule("business_process", "information_object", 0, None, 0, None),
            _rule("application", "information_object", 0, None, 0, None),
        ]),
        _rtype("uses_information", "Uses information", "Indicates that a process or application consumes an information object.", 250, [
            _rule("business_process", "information_object", 0, None, 0, None),
            _rule("application", "information_object", 0, None, 0, None),
        ]),
    ],

    "objects": [
        # Project
        _obj(
            "eftpos_modernisation", "project", "Harbour Home Retail EFTPOS Modernisation",
            "A fictional medium-sized New Zealand retail technology project replacing an ageing in-store EFTPOS platform, integrating a new payment service with the existing RetailPOS application, and improving settlement reconciliation and device support across a 32-store network.",
            {"status": "Pilot", "purpose": "Modernise the store payment experience without replacing the core checkout application. The project is intended to improve terminal reliability, make device faults easier to detect, simplify settlement handling and establish a supportable EFTPOS platform for future store growth.", "sponsor": "Chief Operating Officer", "criticality": "Critical"},
        ),

        # Workstreams
        _obj("payment_platform", "workstream", "Payment Platform", "Build and configure the target EFTPOS service, retire the legacy terminal management capability and establish the technical foundation for store payments.", {"status": "Complete", "purpose": "Put the new payment platform and checkout integration into a technically ready state for live stores.", "lead": "Payments Technology Lead", "criticality": "Critical"}),
        _obj("store_rollout", "workstream", "Store Rollout & Readiness", "Prepare stores for the new terminals, coordinate installation waves and establish a repeatable approach to frontline readiness and cutover.", {"status": "In progress", "purpose": "Move from a successful technical build into controlled store deployment with minimal disruption to trading.", "lead": "Retail Change Lead", "criticality": "High"}),
        _obj("finance_reconciliation", "workstream", "Finance & Reconciliation", "Ensure the new payment flows produce settlement information that Finance Operations can reconcile to store trading and bank receipts without manual workarounds.", {"status": "At risk", "purpose": "Prove that the financial records produced by the new platform can be reconciled accurately within the existing daily close timetable.", "lead": "Finance Operations Lead", "criticality": "Critical"}),
        _obj("support_operations", "workstream", "Support & Operations", "Establish operational monitoring, support procedures and clear ownership for the new EFTPOS service once stores are live.", {"status": "In progress", "purpose": "Make the target service supportable from day one, including device monitoring, incident triage and operational ownership.", "lead": "Technology Services Manager", "criticality": "High"}),

        # Changes
        _obj("replace_eftpos_platform", "change", "Replace the legacy EFTPOS platform", "Replace the ageing EFTPOS terminal estate and its management service with HarbourPay while preserving the existing RetailPOS checkout experience for stores and customers.", {"status": "In progress", "change_type": "Technology", "business_value": "Reduce payment device failures, remove dependence on an unsupported legacy platform and establish a maintainable payment service for the next stage of store growth.", "target_state": "Stores use HarbourPay-managed terminals connected through the existing payment gateway, while the legacy EFTPOS Manager is retired."}),
        _obj("integrate_retailpos", "change", "Integrate HarbourPay with RetailPOS", "Modify the RetailPOS payment adapter so sales and refunds can be initiated through HarbourPay without changing the core checkout workflow used by store staff.", {"status": "Complete", "change_type": "Technology", "business_value": "Introduce the new payment platform without requiring stores to learn a different checkout process.", "target_state": "RetailPOS sends payment and refund requests to HarbourPay and receives the business-level outcomes expected by the checkout workflow."}),
        _obj("modernise_settlement", "change", "Modernise card settlement reconciliation", "Update the settlement mapping and reconciliation process so Finance Operations can reconcile HarbourPay transactions and settlement batches against store trading records.", {"status": "At risk", "change_type": "Process", "business_value": "Reduce manual investigation of settlement differences and give Finance Operations a consistent view of payment results across stores.", "target_state": "HarbourPay settlement batches are mapped into the existing reconciliation process with exceptions surfaced for investigation instead of spreadsheet-based investigation."}),
        _obj("introduce_device_monitoring", "change", "Introduce proactive device monitoring", "Introduce central monitoring for terminal connectivity, device health and common payment faults so Technology Services can detect issues before stores need to escalate every incident manually.", {"status": "In progress", "change_type": "Operational", "business_value": "Shorten the time between terminal failure and detection and give support teams a consistent operational view of the estate.", "target_state": "Technology Services can see terminal health and connectivity across live stores and identify common failure conditions without contacting each store first."}),
        _obj("rollout_store_capability", "change", "Establish the repeatable store rollout capability", "Create the operating procedures, training material, cutover steps and support model required to deploy the new EFTPOS service across stores in controlled waves.", {"status": "In progress", "change_type": "Operational", "business_value": "Make remaining store deployments predictable and reduce the operational risk associated with each installation wave.", "target_state": "A store can be prepared, cut over, supported and verified using a repeatable procedure owned by Retail Operations and Technology Services."}),

        # Deliverables
        _obj("harbourpay_platform_configured", "deliverable", "HarbourPay production platform configured", "Production configuration for HarbourPay, including merchant settings, terminal profiles, routing parameters and secure connectivity to the payment gateway.", {"status": "Complete", "deliverable_type": "Technology", "purpose": "Provide a production-ready target payment platform that can support store sales and refunds.", "acceptance_criteria": "Production configuration is approved, connectivity is verified and pilot terminal profiles can transact successfully."}),
        _obj("retailpos_payment_integration", "deliverable", "RetailPOS payment integration", "The updated RetailPOS payment adapter supporting sale, refund and payment-result handling through HarbourPay while preserving the existing checkout interaction used by store staff.", {"status": "Complete", "deliverable_type": "Integration", "purpose": "Connect the existing checkout application to the new payment platform without redesigning the checkout workflow.", "acceptance_criteria": "Sales and refunds complete successfully, payment failures are returned correctly and existing checkout controls behave as expected."}),
        _obj("pilot_terminal_estate", "deliverable", "Auckland pilot terminal estate deployed", "Twenty production terminals installed across four Auckland stores, configured against HarbourPay and verified for normal trading.", {"status": "In progress", "deliverable_type": "Technology", "purpose": "Prove the physical installation and operational rollout pattern before expanding to the rest of the store network.", "acceptance_criteria": "All pilot stores can complete sales and refunds, local staff have completed training and no critical installation issues remain."}),
        _obj("settlement_mapping", "deliverable", "HarbourPay settlement mapping and reconciliation rules", "Mapping rules that translate HarbourPay settlement batches into the existing finance reconciliation process, including handling for partial batches and settlement exceptions.", {"status": "At risk", "deliverable_type": "Process", "purpose": "Ensure payment settlements can be reconciled consistently without introducing manual spreadsheet work.", "acceptance_criteria": "A full trading day can be reconciled end to end and known exception scenarios are identified and routed for investigation."}),
        _obj("device_monitoring_dashboards", "deliverable", "Store payment device monitoring dashboards", "Operational dashboards showing terminal connectivity, device health and common fault conditions for Technology Services.", {"status": "In progress", "deliverable_type": "Operational", "purpose": "Give support teams a central view of payment device health across live stores.", "acceptance_criteria": "Support can identify offline or degraded terminals and trace the affected store without relying on a store call first."}),
        _obj("store_cutover_procedure", "deliverable", "Store cutover and rollback procedure", "A repeatable procedure covering store preparation, terminal swap, validation, rollback triggers and escalation steps for each rollout wave.", {"status": "Complete", "deliverable_type": "Operational", "purpose": "Provide a controlled and repeatable method for moving a store from the legacy terminal estate to HarbourPay.", "acceptance_criteria": "The procedure has been exercised in the pilot and can be followed without project-specific knowledge."}),
        _obj("store_training_package", "deliverable", "Store payment operations training package", "Short training material and quick-reference guidance covering normal payment, refund handling, terminal replacement and the first steps when a payment device becomes unavailable.", {"status": "Complete", "deliverable_type": "Documentation", "purpose": "Give store teams enough information to operate the new terminals and handle common issues confidently.", "acceptance_criteria": "Pilot store managers have completed the training and can follow documented sale, refund and failure procedures."}),

        # Tests
        _obj("sale_integration_test", "test", "Sale integration test", "End-to-end verification that a normal card sale started in RetailPOS is authorised through HarbourPay and the result is returned correctly to the checkout.", {"status": "Passed", "test_type": "Integration", "purpose": "Prove that the primary customer payment path works across RetailPOS, HarbourPay and the payment gateway."}),
        _obj("refund_integration_test", "test", "Refund integration test", "Verification that a store refund initiated through RetailPOS is processed by HarbourPay and produces the expected transaction result and downstream settlement record.", {"status": "Passed", "test_type": "Integration", "purpose": "Prove that refund processing continues to work through the new platform."}),
        _obj("settlement_reconciliation_test", "test", "Daily settlement reconciliation test", "A full-day reconciliation test matching store trading activity, HarbourPay settlement batches and expected finance records, including controlled settlement exceptions.", {"status": "In progress", "test_type": "Reconciliation", "purpose": "Establish whether Finance Operations can close a full trading day without material unexplained payment differences."}),
        _obj("terminal_failure_recovery_test", "test", "Terminal failure recovery test", "Verification that a terminal becoming unavailable is detected, escalated and recovered using the intended operational support process.", {"status": "Failed", "test_type": "Resilience", "purpose": "Prove that a common device failure can be detected and resolved without an extended interruption to store trading."}),
        _obj("pilot_store_acceptance_test", "test", "Pilot store acceptance test", "Store-level acceptance covering sales, refunds, device replacement, support escalation and day-end close procedures in the pilot stores.", {"status": "In progress", "test_type": "User acceptance", "purpose": "Confirm that the target solution works in the real store operating environment, not only in technical testing."}),
        _obj("harbourpay_configuration_verification", "test", "HarbourPay production configuration verification", "Verification that the production HarbourPay configuration matches the approved merchant, terminal, routing and connectivity settings and is ready for controlled store use.", {"status": "Passed", "test_type": "Operational", "purpose": "Establish that the configured production platform is complete, approved and safe to introduce into the pilot stores."}),
        _obj("store_cutover_rehearsal_test", "test", "Store cutover rehearsal", "A controlled rehearsal of the store cutover and rollback procedure using the pilot installation sequence, validation steps, escalation points and recovery triggers.", {"status": "Passed", "test_type": "Operational", "purpose": "Demonstrate that the rollout procedure can be followed consistently by store and support teams without relying on project-specific knowledge."}),
        _obj("store_training_readiness_test", "test", "Store training readiness assessment", "Assessment that pilot store managers understand normal payment, refund handling, terminal replacement and first-line recovery steps before their stores enter live service.", {"status": "Passed", "test_type": "User acceptance", "purpose": "Confirm that frontline teams can operate the new terminals and follow the documented response to common payment device problems."}),

        # Releases
        _obj("platform_foundation_release", "release", "Release 1.0 — HarbourPay platform foundation", "Initial production release establishing HarbourPay configuration, gateway connectivity and the supporting integration services required for the pilot.", {"status": "Verified", "purpose": "Put the technical foundation into production-ready condition before the store pilot begins.", "environment": "Production"}),
        _obj("pilot_stores_release", "release", "Release 1.1 — Auckland pilot stores", "Controlled deployment of the new EFTPOS platform to four Auckland pilot stores, including terminal installation, store validation and support readiness.", {"status": "Deployed", "purpose": "Validate the full operational solution in a small live store population before authorising wider rollout.", "environment": "Pilot"}),
        _obj("reconciliation_cutover_release", "release", "Release 1.2 — Settlement reconciliation cutover", "Production release enabling HarbourPay settlement mapping and reconciliation for the pilot population after parallel validation.", {"status": "Planned", "purpose": "Move the finance process from validation into supported production use.", "environment": "Production"}),

        # Decisions
        _obj("select_harbourpay", "decision", "Select HarbourPay as the target EFTPOS platform", "The project selected HarbourPay as the target store payment platform after comparing the required terminal management, monitoring and integration capabilities.", {"status": "Approved", "decision_type": "Architecture", "rationale": "The selected platform meets target operational requirements while allowing the existing RetailPOS checkout and payment gateway arrangements to remain substantially unchanged."}),
        _obj("retain_payment_gateway", "decision", "Retain the existing payment gateway", "The project will replace the in-store EFTPOS layer without replacing the existing external payment gateway.", {"status": "Approved", "decision_type": "Scope", "rationale": "Keeping the gateway reduces integration scope and avoids changing a stable external payment service that is not part of the problem being addressed."}),
        _obj("pilot_four_auckland_stores", "decision", "Pilot in four Auckland stores", "The first live rollout uses four metropolitan stores with different trading profiles so the project can validate both high-volume and standard store conditions.", {"status": "Approved", "decision_type": "Delivery", "rationale": "A small but representative pilot provides real operational evidence without exposing the full 32-store estate to an unproven cutover pattern."}),
        _obj("parallel_settlement_validation", "decision", "Run settlement formats in parallel during validation", "HarbourPay settlement information will be reconciled in parallel with the existing settlement process before the new mapping becomes the supported production path.", {"status": "Approved", "decision_type": "Risk", "rationale": "Parallel validation provides a direct comparison of the new and existing financial results before the project removes the legacy reconciliation path."}),

        # Business units
        _obj("retail_operations", "business_unit", "Retail Operations", "The business unit responsible for store performance, frontline operating standards and the day-to-day customer experience.", {"purpose": "Keep stores trading effectively while providing a consistent customer experience across the retail network."}),
        _obj("technology", "business_unit", "Technology", "The business unit responsible for application delivery, technology operations, security and support services.", {"purpose": "Provide reliable technology services that support store operations and the wider organisation."}),
        _obj("finance", "business_unit", "Finance", "The business unit responsible for financial control, transaction processing and management reporting.", {"purpose": "Maintain accurate financial records and effective financial controls across the retail business."}),

        # Teams
        _obj("store_operations_team", "team", "Store Operations", "Business team responsible for store procedures, frontline readiness and operating standards across the retail network.", {"purpose": "Keep store teams productive and provide consistent operating practices across the retail network.", "team_type": "Business"}),
        _obj("payments_product", "team", "Payments Product", "Product team accountable for the payment experience and the business requirements governing store payments and refunds.", {"purpose": "Own the customer and business outcomes associated with store payments.", "team_type": "Business"}),
        _obj("retail_technology", "team", "Retail Technology", "Technology team responsible for RetailPOS and the integrations that connect store technology to payment services.", {"purpose": "Deliver and maintain the applications and integrations used by stores.", "team_type": "Technology"}),
        _obj("finance_operations_team", "team", "Finance Operations", "Operations team responsible for daily transaction processing, settlement review and investigation of reconciliation exceptions.", {"purpose": "Ensure customer payment transactions are accurately captured, settled and reconciled.", "team_type": "Operations"}),
        _obj("technology_services", "team", "Technology Services", "Operational technology team responsible for monitoring, incident management and support of live store technology services.", {"purpose": "Detect and resolve technology incidents before they materially disrupt store operations.", "team_type": "Technology"}),
        _obj("service_desk", "team", "Service Desk", "Frontline support team receiving store technology incidents and coordinating escalation to specialist support teams.", {"purpose": "Provide the first point of contact for store technology support.", "team_type": "Operations"}),
        _obj("data_analytics", "team", "Data & Analytics", "Technology team responsible for analytical data flows, reporting and operational insight.", {"purpose": "Provide trusted data and reporting for operational and management decisions.", "team_type": "Technology"}),

        # Capabilities
        _obj("in_store_sales", "business_capability", "In-Store Sales", "The ability to complete retail sales at physical stores, from basket confirmation through payment and receipt.", {"purpose": "Convert customer purchases into completed store transactions.", "strategic_importance": "Critical"}),
        _obj("payments_capability", "business_capability", "Retail Payments", "The ability to accept and process electronic customer payments reliably across the store network.", {"purpose": "Provide a dependable payment mechanism that supports store trading.", "strategic_importance": "Critical"}),
        _obj("refund_management", "business_capability", "Refund Management", "The ability to return customer funds accurately when a purchase needs to be reversed or refunded.", {"purpose": "Process refunds accurately while preserving transaction traceability.", "strategic_importance": "High"}),
        _obj("financial_reconciliation", "business_capability", "Financial Reconciliation", "The ability to compare expected retail transactions with payment settlement results and investigate differences.", {"purpose": "Maintain confidence that retail payment activity agrees with financial settlement records.", "strategic_importance": "Critical"}),
        _obj("store_operations_capability", "business_capability", "Store Operations", "The ability to run stores safely and consistently through standard operating procedures, local support and store readiness.", {"purpose": "Keep stores productive while maintaining consistent operating standards.", "strategic_importance": "High"}),
        _obj("technology_operations", "business_capability", "Technology Operations", "The ability to monitor, support and recover technology services used in day-to-day retail operations.", {"purpose": "Maintain reliable technology services and minimise operational disruption.", "strategic_importance": "High"}),

        # Outcomes
        _obj("reliable_customer_payments", "business_outcome", "Customers can pay reliably in store", "Customers can complete normal card payments at checkout without avoidable terminal failures or unnecessary intervention by store staff.", {"description": "The payment experience remains familiar while the underlying technology becomes more reliable and supportable."}),
        _obj("accurate_refunds", "business_outcome", "Customer refunds are processed accurately", "Refunds initiated by store staff result in the correct transaction outcome and can be traced through payment and settlement records.", {"description": "Refund processing remains dependable through the transition to HarbourPay."}),
        _obj("settlements_reconciled", "business_outcome", "Card settlements are reconciled by next business day", "Finance Operations can reconcile card settlement activity to store trading records within the existing daily finance timetable.", {"description": "The new payment platform does not create a new manual finance workload."}),
        _obj("payment_incidents_detected_early", "business_outcome", "Payment incidents are detected early", "Technology Services can identify common terminal connectivity and device health problems before repeated store escalation becomes necessary.", {"description": "Operational monitoring provides an earlier signal of problems and a consistent starting point for support."}),
        _obj("supported_payment_service", "business_outcome", "Supported store payment service", "The store payment service has clear ownership, monitoring and support procedures across the live estate and no longer depends on project-specific knowledge to remain operational.", {"description": "The target service can be operated and supported as part of normal business-as-usual technology operations."}),

        # Store clusters
        _obj("auckland_metropolitan", "store_cluster", "Auckland Metropolitan Stores", "Twelve higher-volume metropolitan stores across Auckland. Four stores form the initial live pilot population for HarbourPay.", {"store_type": "High volume", "rollout_status": "Pilot"}),
        _obj("waikato_bop", "store_cluster", "Waikato & Bay of Plenty Stores", "Ten regional stores serving a mixed urban and provincial customer base. This population follows the Auckland pilot once the rollout pattern is proven.", {"store_type": "Regional", "rollout_status": "Not started"}),
        _obj("wellington_lower_north_island", "store_cluster", "Wellington & Lower North Island Stores", "Ten metropolitan and regional stores scheduled for later rollout waves after the payment and reconciliation model is proven.", {"store_type": "Mixed", "rollout_status": "Not started"}),

        # Applications
        _obj("retailpos", "application", "RetailPOS", "The store point-of-sale application used by staff to create sales, process refunds and complete the checkout workflow.", {"vendor": "Harbour Home Retail Technology", "application_type": "Business application", "lifecycle_status": "Current", "criticality": "Critical", "purpose": "Manage in-store sales and present the checkout experience used by store teams and customers."}),
        _obj("legacy_eftpos_manager", "application", "Legacy EFTPOS Manager", "The existing store payment management service controlling the legacy terminal estate. It has limited monitoring capability and is approaching the end of its supported lifecycle.", {"vendor": "Legacy Payments Ltd", "application_type": "Platform", "lifecycle_status": "Retiring", "criticality": "Critical", "purpose": "Manage the existing EFTPOS terminals and route store payment requests to the external payment gateway."}),
        _obj("harbourpay", "application", "HarbourPay EFTPOS Platform", "The target store payment platform providing terminal management, transaction routing, device configuration and operational telemetry for the next-generation EFTPOS estate.", {"vendor": "Harbour Payments", "application_type": "Platform", "lifecycle_status": "Planned", "criticality": "Critical", "purpose": "Provide a supported and observable EFTPOS service for stores while preserving the existing RetailPOS checkout workflow."}),
        _obj("payment_gateway", "application", "National Payment Gateway", "The external payment service that authorises card transactions and returns payment outcomes to the retail payment platform.", {"vendor": "National Payments Network", "application_type": "Integration", "lifecycle_status": "Current", "criticality": "Critical", "purpose": "Provide external card authorisation and payment processing services."}),
        _obj("settlement_reconciliation_service", "application", "Settlement Reconciliation Service", "The finance support application that compares retail transaction results with payment settlement batches and highlights differences for investigation.", {"vendor": "Harbour Home Retail Technology", "application_type": "Business application", "lifecycle_status": "Current", "criticality": "High", "purpose": "Support Finance Operations in reconciling payment settlements to expected store activity."}),
        _obj("store_operations_portal", "application", "Store Operations Portal", "A target operational interface for viewing store payment device status, initiating standard support actions and accessing store technology guidance.", {"vendor": "Harbour Home Retail Technology", "application_type": "Business application", "lifecycle_status": "Planned", "criticality": "High", "purpose": "Give store and support teams a consistent operational entry point for payment device issues."}),
        _obj("payment_analytics_warehouse", "application", "Payment Analytics Warehouse", "The analytical data service used to retain payment and settlement information for operational reporting and trend analysis.", {"vendor": "Harbour Home Retail Technology", "application_type": "Platform", "lifecycle_status": "Current", "criticality": "High", "purpose": "Provide trusted payment information for operational and management reporting."}),

        # Processes
        _obj("complete_in_store_sale", "business_process", "Complete In-Store Sale", "Take a customer purchase from basket confirmation through card payment authorisation, receipt and completion of the transaction.", {"purpose": "Complete a customer purchase accurately and with minimal friction at checkout.", "criticality": "Critical", "customer_facing": True}),
        _obj("process_store_refund", "business_process", "Process Store Refund", "Receive and validate a refund request, submit the required payment reversal and confirm the result to the customer.", {"purpose": "Return eligible customer funds accurately while keeping a clear transaction record.", "criticality": "High", "customer_facing": True}),
        _obj("close_trading_day", "business_process", "Close Trading Day", "Complete the store's end-of-day payment activities, including final transaction capture, settlement preparation and local close controls.", {"purpose": "Ensure the day's store payment activity is complete and ready for finance processing.", "criticality": "High", "customer_facing": False}),
        _obj("reconcile_card_settlements", "business_process", "Reconcile Card Settlements", "Compare expected card payment activity with settlement batches, identify discrepancies and resolve or escalate unexplained differences.", {"purpose": "Confirm that payment settlements agree with the retail transactions that generated them.", "criticality": "Critical", "customer_facing": False}),
        _obj("manage_store_payment_devices", "business_process", "Manage Store Payment Devices", "Monitor payment terminal health, respond to device failures, replace faulty equipment and keep the store payment estate operational.", {"purpose": "Maintain payment device availability without unnecessary disruption to store trading.", "criticality": "High", "customer_facing": False}),
        _obj("resolve_payment_exception", "business_process", "Resolve Payment Exception", "Investigate failed or unusual payment conditions, determine whether the issue is transactional, device-related or service-related, and restore normal processing.", {"purpose": "Restore payment processing and ensure exceptions are understood rather than silently remaining unresolved.", "criticality": "High", "customer_facing": False}),

        # Information
        _obj("payment_transaction", "information_object", "Payment Transaction", "A record of a customer payment attempt and its final outcome, including transaction identifiers required for traceability.", {"purpose": "Provide the canonical record used to trace a customer payment through checkout, authorisation and settlement.", "sensitivity": "Confidential"}),
        _obj("refund_request", "information_object", "Refund Request", "A record of a store-initiated request to return funds against a previously completed customer transaction.", {"purpose": "Capture the reason, amount and reference needed to process a refund.", "sensitivity": "Confidential"}),
        _obj("settlement_batch", "information_object", "Settlement Batch", "A grouped record of payment transactions submitted for settlement through the external payment network.", {"purpose": "Provide the settlement-side record used in daily reconciliation.", "sensitivity": "Confidential"}),
        _obj("reconciliation_exception", "information_object", "Reconciliation Exception", "A recorded difference between expected store payment activity and settlement results received for the same trading period.", {"purpose": "Capture the details and disposition of unexplained payment differences.", "sensitivity": "Restricted"}),
        _obj("device_configuration", "information_object", "Device Configuration", "The configuration information required to identify, provision and operate an EFTPOS terminal in a particular store.", {"purpose": "Define how an individual payment device is configured and connected.", "sensitivity": "Restricted"}),
    ],

    "relationships": [
        # Delivery structure
        _rel("contains", "eftpos_modernisation", "payment_platform"),
        _rel("contains", "eftpos_modernisation", "store_rollout"),
        _rel("contains", "eftpos_modernisation", "finance_reconciliation"),
        _rel("contains", "eftpos_modernisation", "support_operations"),
        _rel("contains", "payment_platform", "replace_eftpos_platform"),
        _rel("contains", "payment_platform", "integrate_retailpos"),
        _rel("contains", "finance_reconciliation", "modernise_settlement"),
        _rel("contains", "support_operations", "introduce_device_monitoring"),
        _rel("contains", "store_rollout", "rollout_store_capability"),

        # Changes -> deliverables
        _rel("has_deliverable", "replace_eftpos_platform", "harbourpay_platform_configured"),
        _rel("has_deliverable", "replace_eftpos_platform", "pilot_terminal_estate"),
        _rel("has_deliverable", "integrate_retailpos", "retailpos_payment_integration"),
        _rel("has_deliverable", "modernise_settlement", "settlement_mapping"),
        _rel("has_deliverable", "introduce_device_monitoring", "device_monitoring_dashboards"),
        _rel("has_deliverable", "rollout_store_capability", "store_cutover_procedure"),
        _rel("has_deliverable", "rollout_store_capability", "store_training_package"),

        # Changes -> tests -> deliverables
        _rel("has_test", "integrate_retailpos", "sale_integration_test"),
        _rel("has_test", "integrate_retailpos", "refund_integration_test"),
        _rel("has_test", "modernise_settlement", "settlement_reconciliation_test"),
        _rel("has_test", "introduce_device_monitoring", "terminal_failure_recovery_test"),
        _rel("has_test", "rollout_store_capability", "pilot_store_acceptance_test"),
        _rel("has_test", "replace_eftpos_platform", "harbourpay_configuration_verification"),
        _rel("has_test", "rollout_store_capability", "store_cutover_rehearsal_test"),
        _rel("has_test", "rollout_store_capability", "store_training_readiness_test"),
        _rel("validates", "sale_integration_test", "retailpos_payment_integration"),
        _rel("validates", "refund_integration_test", "retailpos_payment_integration"),
        _rel("validates", "settlement_reconciliation_test", "settlement_mapping"),
        _rel("validates", "terminal_failure_recovery_test", "device_monitoring_dashboards"),
        _rel("validates", "pilot_store_acceptance_test", "pilot_terminal_estate"),
        _rel("validates", "harbourpay_configuration_verification", "harbourpay_platform_configured"),
        _rel("validates", "store_cutover_rehearsal_test", "store_cutover_procedure"),
        _rel("validates", "store_training_readiness_test", "store_training_package"),
        _rel("executed_by", "sale_integration_test", "retail_technology"),
        _rel("executed_by", "refund_integration_test", "retail_technology"),
        _rel("executed_by", "settlement_reconciliation_test", "finance_operations_team"),
        _rel("executed_by", "terminal_failure_recovery_test", "technology_services"),
        _rel("executed_by", "pilot_store_acceptance_test", "store_operations_team"),
        _rel("executed_by", "harbourpay_configuration_verification", "retail_technology"),
        _rel("executed_by", "store_cutover_rehearsal_test", "store_operations_team"),
        _rel("executed_by", "store_training_readiness_test", "store_operations_team"),

        # Changes -> releases
        _rel("has_release", "replace_eftpos_platform", "platform_foundation_release"),
        _rel("has_release", "rollout_store_capability", "pilot_stores_release"),
        _rel("has_release", "modernise_settlement", "reconciliation_cutover_release"),
        _rel("deploys", "platform_foundation_release", "harbourpay"),
        _rel("deploys", "pilot_stores_release", "harbourpay"),
        _rel("deploys", "pilot_stores_release", "store_operations_portal"),
        _rel("deploys", "reconciliation_cutover_release", "settlement_reconciliation_service"),
        _rel("deployed_to", "pilot_stores_release", "auckland_metropolitan"),
        _rel("approved_by", "platform_foundation_release", "retail_technology"),
        _rel("approved_by", "pilot_stores_release", "store_operations_team"),
        _rel("approved_by", "reconciliation_cutover_release", "finance_operations_team"),

        # Delivery ownership
        _rel("owned_by", "eftpos_modernisation", "payments_product"),
        _rel("owned_by", "payment_platform", "retail_technology"),
        _rel("owned_by", "store_rollout", "store_operations_team"),
        _rel("owned_by", "finance_reconciliation", "finance_operations_team"),
        _rel("owned_by", "support_operations", "technology_services"),
        _rel("owned_by", "replace_eftpos_platform", "retail_technology"),
        _rel("owned_by", "integrate_retailpos", "retail_technology"),
        _rel("owned_by", "modernise_settlement", "finance_operations_team"),
        _rel("owned_by", "introduce_device_monitoring", "technology_services"),
        _rel("owned_by", "rollout_store_capability", "store_operations_team"),
        _rel("owned_by", "harbourpay_platform_configured", "retail_technology"),
        _rel("owned_by", "retailpos_payment_integration", "retail_technology"),
        _rel("owned_by", "pilot_terminal_estate", "store_operations_team"),
        _rel("owned_by", "settlement_mapping", "finance_operations_team"),
        _rel("owned_by", "device_monitoring_dashboards", "technology_services"),
        _rel("owned_by", "store_cutover_procedure", "store_operations_team"),
        _rel("owned_by", "store_training_package", "store_operations_team"),

        # Decisions
        _rel("applies_to", "select_harbourpay", "replace_eftpos_platform"),
        _rel("applies_to", "retain_payment_gateway", "replace_eftpos_platform"),
        _rel("applies_to", "pilot_four_auckland_stores", "rollout_store_capability"),
        _rel("applies_to", "parallel_settlement_validation", "modernise_settlement"),
        _rel("made_by", "select_harbourpay", "payments_product"),
        _rel("made_by", "retain_payment_gateway", "retail_technology"),
        _rel("made_by", "pilot_four_auckland_stores", "store_operations_team"),
        _rel("made_by", "parallel_settlement_validation", "finance_operations_team"),

        # Rollout scope
        _rel("rolls_out_to", "rollout_store_capability", "auckland_metropolitan"),
        _rel("rolls_out_to", "rollout_store_capability", "waikato_bop"),
        _rel("rolls_out_to", "rollout_store_capability", "wellington_lower_north_island"),

        # Change impact
        _rel("affects", "replace_eftpos_platform", "complete_in_store_sale"),
        _rel("affects", "replace_eftpos_platform", "process_store_refund"),
        _rel("affects", "replace_eftpos_platform", "manage_store_payment_devices"),
        _rel("affects", "replace_eftpos_platform", "legacy_eftpos_manager"),
        _rel("affects", "replace_eftpos_platform", "retail_technology"),
        _rel("affects", "replace_eftpos_platform", "payments_capability"),
        _rel("affects", "integrate_retailpos", "complete_in_store_sale"),
        _rel("affects", "integrate_retailpos", "process_store_refund"),
        _rel("affects", "integrate_retailpos", "retailpos"),
        _rel("affects", "modernise_settlement", "reconcile_card_settlements"),
        _rel("affects", "modernise_settlement", "close_trading_day"),
        _rel("affects", "modernise_settlement", "settlement_reconciliation_service"),
        _rel("affects", "modernise_settlement", "finance_operations_team"),
        _rel("affects", "modernise_settlement", "financial_reconciliation"),
        _rel("affects", "introduce_device_monitoring", "manage_store_payment_devices"),
        _rel("affects", "introduce_device_monitoring", "resolve_payment_exception"),
        _rel("affects", "introduce_device_monitoring", "technology_services"),
        _rel("affects", "introduce_device_monitoring", "technology_operations"),
        _rel("affects", "rollout_store_capability", "store_operations_team"),
        _rel("affects", "rollout_store_capability", "store_operations_capability"),

        # Change -> business outcomes
        _rel("delivers", "replace_eftpos_platform", "reliable_customer_payments"),
        _rel("delivers", "integrate_retailpos", "accurate_refunds"),
        _rel("delivers", "modernise_settlement", "settlements_reconciled"),
        _rel("delivers", "introduce_device_monitoring", "payment_incidents_detected_early"),
        _rel("delivers", "rollout_store_capability", "supported_payment_service"),

        # Current application relationships
        _rel("uses", "complete_in_store_sale", "retailpos"),
        _rel("uses", "complete_in_store_sale", "legacy_eftpos_manager"),
        _rel("uses", "process_store_refund", "retailpos"),
        _rel("uses", "process_store_refund", "legacy_eftpos_manager"),
        _rel("uses", "close_trading_day", "retailpos"),
        _rel("uses", "reconcile_card_settlements", "settlement_reconciliation_service"),
        _rel("uses", "manage_store_payment_devices", "legacy_eftpos_manager"),
        _rel("uses", "resolve_payment_exception", "legacy_eftpos_manager"),

        # Target application relationships
        _rel("will_use", "complete_in_store_sale", "harbourpay"),
        _rel("will_use", "process_store_refund", "harbourpay"),
        _rel("will_use", "manage_store_payment_devices", "harbourpay"),
        _rel("will_use", "resolve_payment_exception", "harbourpay"),
        _rel("will_use", "manage_store_payment_devices", "store_operations_portal"),
        _rel("will_use", "reconcile_card_settlements", "payment_analytics_warehouse"),
        _rel("replaces", "harbourpay", "legacy_eftpos_manager"),

        # Application dependencies and capability support
        _rel("depends_on", "retailpos", "legacy_eftpos_manager"),
        _rel("depends_on", "legacy_eftpos_manager", "payment_gateway"),
        _rel("depends_on", "harbourpay", "payment_gateway"),
        _rel("depends_on", "store_operations_portal", "harbourpay"),
        _rel("depends_on", "settlement_reconciliation_service", "payment_analytics_warehouse"),
        _rel("supports", "retailpos", "in_store_sales"),
        _rel("supports", "retailpos", "refund_management"),
        _rel("supports", "legacy_eftpos_manager", "payments_capability"),
        _rel("supports", "harbourpay", "payments_capability"),
        _rel("supports", "harbourpay", "technology_operations"),
        _rel("supports", "settlement_reconciliation_service", "financial_reconciliation"),
        _rel("supports", "store_operations_portal", "technology_operations"),

        # Application operations
        _rel("operated_by", "retailpos", "retail_technology"),
        _rel("operated_by", "legacy_eftpos_manager", "retail_technology"),
        _rel("operated_by", "harbourpay", "technology_services"),
        _rel("operated_by", "settlement_reconciliation_service", "finance_operations_team"),
        _rel("operated_by", "store_operations_portal", "technology_services"),
        _rel("operated_by", "payment_analytics_warehouse", "data_analytics"),

        # Business ownership of operational assets
        _rel("owned_by", "retailpos", "retail_technology"),
        _rel("owned_by", "legacy_eftpos_manager", "retail_technology"),
        _rel("owned_by", "harbourpay", "payments_product"),
        _rel("owned_by", "payment_gateway", "retail_technology"),
        _rel("owned_by", "settlement_reconciliation_service", "finance_operations_team"),
        _rel("owned_by", "store_operations_portal", "technology_services"),
        _rel("owned_by", "payment_analytics_warehouse", "data_analytics"),

        # Process ownership
        _rel("owned_by", "complete_in_store_sale", "store_operations_team"),
        _rel("owned_by", "process_store_refund", "store_operations_team"),
        _rel("owned_by", "close_trading_day", "store_operations_team"),
        _rel("owned_by", "reconcile_card_settlements", "finance_operations_team"),
        _rel("owned_by", "manage_store_payment_devices", "technology_services"),
        _rel("owned_by", "resolve_payment_exception", "technology_services"),

        # Organisation
        _rel("belongs_to", "store_operations_team", "retail_operations"),
        _rel("belongs_to", "payments_product", "retail_operations"),
        _rel("belongs_to", "retail_technology", "technology"),
        _rel("belongs_to", "technology_services", "technology"),
        _rel("belongs_to", "service_desk", "technology"),
        _rel("belongs_to", "data_analytics", "technology"),
        _rel("belongs_to", "finance_operations_team", "finance"),

        # Process -> Team
        _rel("performed_by", "complete_in_store_sale", "store_operations_team"),
        _rel("performed_by", "process_store_refund", "store_operations_team"),
        _rel("performed_by", "close_trading_day", "store_operations_team"),
        _rel("performed_by", "reconcile_card_settlements", "finance_operations_team"),
        _rel("performed_by", "manage_store_payment_devices", "technology_services"),
        _rel("performed_by", "resolve_payment_exception", "service_desk"),
        _rel("performed_by", "resolve_payment_exception", "technology_services"),

        # Process -> Capabilities
        _rel("supports", "complete_in_store_sale", "in_store_sales"),
        _rel("supports", "complete_in_store_sale", "payments_capability"),
        _rel("supports", "process_store_refund", "refund_management"),
        _rel("supports", "close_trading_day", "financial_reconciliation"),
        _rel("supports", "reconcile_card_settlements", "financial_reconciliation"),
        _rel("supports", "manage_store_payment_devices", "technology_operations"),
        _rel("supports", "resolve_payment_exception", "technology_operations"),

        # Process -> Outcomes
        _rel("delivers_process_outcome", "complete_in_store_sale", "reliable_customer_payments"),
        _rel("delivers_process_outcome", "process_store_refund", "accurate_refunds"),
        _rel("delivers_process_outcome", "reconcile_card_settlements", "settlements_reconciled"),
        _rel("delivers_process_outcome", "manage_store_payment_devices", "payment_incidents_detected_early"),

        # Process / Application -> Information
        _rel("creates_information", "complete_in_store_sale", "payment_transaction"),
        _rel("uses_information", "process_store_refund", "refund_request"),
        _rel("creates_information", "process_store_refund", "payment_transaction"),
        _rel("creates_information", "reconcile_card_settlements", "reconciliation_exception"),
        _rel("uses_information", "reconcile_card_settlements", "settlement_batch"),
        _rel("uses_information", "manage_store_payment_devices", "device_configuration"),
        _rel("creates_information", "resolve_payment_exception", "reconciliation_exception"),
        _rel("creates_information", "retailpos", "payment_transaction"),
        _rel("creates_information", "harbourpay", "payment_transaction"),
        _rel("uses_information", "harbourpay", "device_configuration"),
        _rel("creates_information", "settlement_reconciliation_service", "reconciliation_exception"),
        _rel("uses_information", "settlement_reconciliation_service", "settlement_batch"),
        _rel("uses_information", "payment_analytics_warehouse", "payment_transaction"),
        _rel("uses_information", "payment_analytics_warehouse", "settlement_batch"),
    ],
}

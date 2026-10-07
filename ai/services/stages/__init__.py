"""
The concrete workflow stages (Discovery, Planning, Verification) that
ai.services.operation_definitions composes into each operation's
WorkflowDefinition. Planning is shared by Create (alone) and Reconcile
(between Discovery and Verification); future Change/Assess compose subsets.
"""

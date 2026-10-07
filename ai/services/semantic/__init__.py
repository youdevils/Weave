"""
The canonical *semantic* representation of a Model for AI-facing use.

Everything an AI stage sees about canonical state is built here, from
SemanticModelIndex -- never from model.services.model_graph's Explorer
details/projection payloads or model.services.ontology_graph, which exist to
drive the viewer and carry viewer/projection identifiers (node/edge ids,
inView flags, display strings). Canonical UUIDs live only inside the index
itself, where OnyxJar uses them to resolve semantic references and translate
validation feedback; no AI-facing structure built from it ever carries one.
"""

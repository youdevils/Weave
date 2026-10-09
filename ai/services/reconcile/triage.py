"""
Gap triage and requirement states (Phase 4 of
.Documentation/reconcile-architecture-plan.md, sections 3.4 and 3.6).

Every requirement a blocked item misses ends in exactly ONE state, never a
generic "blocked":

    undecidable            structure / wording exists, but its meaning could
                           not be decided (an `undecidable` answer, a mapping
                           or Reading slot refused twice, an unresolved
                           ambiguity)
    insufficient_evidence  the meaning is decided and evidence exists, but it
                           does not meet the rule (too few distinct, identified,
                           viable counterparts)
    not_stated             the proposition was investigated over complete
                           coverage of its relevant evidence, and the source
                           does not state it
    unadjudicated          a decision it waits on was not reached (an open
                           question, an unresolved row exception)
    uninvestigated         its evidence was not investigated yet (a probe
                           not made, unread structure)

A Reading `none` is none of these: it is a semantic decision about a
structural element, and it never directly produces `not_stated`.

Readings mode routes each unmet requirement by its LEADS -- where layout or
prose says to look (ai.services.document.queries.leads), checked in order:

    0. a lead row with an unresolved anomaly  -> its grouped row_exception
       first; no terminal negative until it is resolved
    1. a lead in an element whose relevant slot is decided -> already
       expanded; the state follows from the evidence
    2. a lead in an unread / undecided element, or one whose relevant slot is
       `none` (or a section relation left out) -> a Reading question on THAT
       slot, once per slot (for `none`: a challenge stating the requirement)
    3. prose leads only -> a Gap Probe (prose packs)
    4. no lead with complete coverage -> not_stated, no AI call

So a probe never runs over a structural lead, and `not_stated` is never
recorded while a structural lead sits in an unread, undecided or
unreconsidered-`none` element. Claims mode keeps its routing (and its
not_stated contest); only the states are reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.services.document import queries
from ai.services.reconcile import questions as q
from ai.services.reconcile import readings as rd
from ai.services.sources import mentions, tokens

UNDECIDABLE, INSUFFICIENT, NOT_STATED = "undecidable", "insufficient_evidence", "not_stated"
UNADJUDICATED, UNINVESTIGATED = "unadjudicated", "uninvestigated"
STATES = (UNDECIDABLE, INSUFFICIENT, NOT_STATED, UNADJUDICATED, UNINVESTIGATED)

# Routes (readings mode).
TERMINAL, ANOMALY, QUESTION, UNREAD, PROBE = "terminal", "anomaly", "question", "unread", "probe"


@dataclass
class Triage:
    requirement_id: str
    route: str = TERMINAL
    # Structural leads: [{segment_id, table_id, slot_id, reason}]; prose lead segment ids.
    structural: list = field(default_factory=list)
    prose: list = field(default_factory=list)
    # Slot ids a question was raised (or is pending) for.
    slots: list = field(default_factory=list)


def _names(analysis, requirement) -> list[str]:
    cluster = analysis.clusters.clusters[requirement.cluster_id]
    return [cluster.name, *cluster.aliases]


def _labels(index, requirement) -> list[str]:
    counterpart = index.object_types[requirement.counterpart_type_id]
    return [counterpart.name, counterpart.key.replace("_", " ")]


def unmet(analysis) -> list:
    """Every requirement of a non-viable cluster that its viable counterparts
    do not meet."""

    scope = analysis.scope
    return [r for cid in sorted(scope.tentative - scope.viable) for r in scope.requirements.get(cid, []) if r.viable_count < r.minimum]


def _reconsidered(pins, slot_id) -> bool:
    return slot_id is not None and rd.slot_question_key(slot_id) in pins


def _slot_route(reading, slot_id, pins, *, absent_is_none=False):
    """-> (route, reason) for a lead whose meaning rests on `slot_id`."""

    slot = reading.slot(slot_id) if reading is not None else None
    if slot is None and not absent_is_none:
        return UNREAD, "no Reading of it"
    if slot is None or (slot.state == "decided" and slot.choice == rd.NONE):
        if _reconsidered(pins, slot_id):
            return TERMINAL, "none, reconsidered and upheld"
        return QUESTION, "challenge: the Reading decided none here"
    if slot.state == "undecidable":
        return QUESTION, "the Reading left it undecidable"
    if slot.state != "decided":
        return UNREAD, f"slot {slot.state}"
    return TERMINAL, "read"


def triage(analysis, state, *, bundle, index) -> dict:
    """Readings mode: the route of every unmet requirement (module docstring)."""

    document = bundle.document()
    readings = {r.element_id: r for r in analysis.readings}
    pins = state.pins
    anomalies = [a for a in analysis.anomalies if not a.resolved]
    scope_segments = state.prose_scope or set()
    result = {}
    for requirement in unmet(analysis):
        if requirement.pending_decision or requirement.ambiguous:
            continue  # a decision gap: answered, never probed (its state says why)
        names, labels = _names(analysis, requirement), _labels(index, requirement)
        triaged = Triage(requirement.requirement_id)
        routes = []
        # The rows the item itself was read from: an unresolved exception
        # there (e.g. its participants' cells) holds its requirements open.
        own_rows = {document.cells[e[2:].split("/p")[0]].row_id for e in analysis.clusters.clusters[requirement.cluster_id].member_eids
                    if e.startswith("x/") and e[2:].split("/p")[0] in document.cells}
        for anomaly in anomalies:
            if anomaly.row_id in own_rows:
                routes.append((ANOMALY, None, anomaly.row_id, f"an unresolved row exception ({anomaly.slot_id})"))
        # The reverse section lead: a cell the item was read from sits under a
        # heading a Section Reading identified as an entity of the
        # counterpart's kind (Pool A under the tournament's title) -- the
        # relationship rests on that heading's section_relation to the column.
        for eid in analysis.clusters.clusters[requirement.cluster_id].member_eids:
            cell = document.cells.get(eid[2:]) if eid.startswith("x/") else None
            if cell is None:
                continue
            table = document.tables[document.rows[cell.row_id].table_id]
            for heading_id in table.ancestor_ids:
                section = readings.get(heading_id)
                heading = section.slot(f"{section.reading_id}/heading_entity") if section is not None and section.status == "validated" else None
                if heading is None or heading.state != "decided":
                    continue
                heading_type = rd.resolve_type(index, heading.choice)
                if heading_type is None or heading_type.id != requirement.counterpart_type_id:
                    continue
                slot_id = f"{section.reading_id}/section_relation/{cell.column_id}"
                route, why = _slot_route(section, slot_id, pins, absent_is_none=True)
                routes.append((route, slot_id, cell.row_id, why))
        for lead in queries.leads(bundle, names, labels):
            row = document.rows.get(lead["segment_id"])
            if row is None:
                if lead["segment_id"] in scope_segments:
                    triaged.prose.append(lead["segment_id"])
                continue
            table = document.tables[row.table_id]
            reading = readings.get(table.table_id)
            if reading is None or reading.status != "validated":
                routes.append((UNREAD, None, row.row_id, "the table has no validated Reading"))
                continue
            if any(a.row_id == row.row_id for a in anomalies):
                routes.append((ANOMALY, None, row.row_id, "an unresolved row exception"))
                continue
            wanted = [tokens(n) for n in names]
            entity_columns = [c.column_id for c in row.cells if tokens(c.text) in wanted]
            if "column" in lead:
                counterpart = [c for c in table.columns if c.label == lead["column"]]
                for column in counterpart:
                    route, why = _slot_route(reading, f"{reading.reading_id}/role/{rd._short(column.column_id)}", pins)
                    if route != TERMINAL:
                        routes.append((route, f"{reading.reading_id}/role/{rd._short(column.column_id)}", row.row_id, why))
                        continue
                    for entity_column in entity_columns:
                        a, b = sorted([entity_column, column.column_id], key=lambda c: document.columns[c].ordinal)
                        slot_id = f"{reading.reading_id}/relation/{rd._short(a)}>{rd._short(b)}"
                        route, why = _slot_route(reading, slot_id, pins)
                        routes.append((route, slot_id, row.row_id, why))
            else:
                heading = next((h for h in table.ancestor_ids if bundle.segment(h).text == lead.get("under")), None)
                section = readings.get(heading)
                columns = [c for c in table.columns if c.column_id in {s.columns[0] for s in reading.slots
                           if s.kind == "role" and s.state == "decided" and rd.resolve_type(index, s.choice) is not None
                           and rd.resolve_type(index, s.choice).id == requirement.counterpart_type_id}]
                if section is None or section.status != "validated" or not columns:
                    routes.append((UNREAD, None, row.row_id, "no Reading relates the section to the kind"))
                    continue
                route, why = _slot_route(section, f"{section.reading_id}/heading_entity", pins)
                if route != TERMINAL:
                    routes.append((route, f"{section.reading_id}/heading_entity", row.row_id, why))
                    continue
                for column in columns:
                    slot_id = f"{section.reading_id}/section_relation/{column.column_id}"
                    route, why = _slot_route(section, slot_id, pins, absent_is_none=True)
                    routes.append((route, slot_id, row.row_id, why))
        for route, slot_id, row_id, why in routes:
            triaged.structural.append({"segment_id": row_id, "slot_id": slot_id, "route": route, "reason": why})
        # Prose naming the entity, beyond the labelled leads (a probe reads it).
        triaged.prose += [s.segment_id for s in bundle.segments()
                          if s.segment_id in scope_segments and s.segment_id not in triaged.prose and mentions(s.text, names)]
        open_routes = [r for r, *_ in routes if r != TERMINAL]
        if ANOMALY in open_routes:
            triaged.route = ANOMALY
        elif QUESTION in open_routes:
            triaged.route = QUESTION
        elif UNREAD in open_routes:
            triaged.route = UNREAD
        elif triaged.prose and requirement.evidenced < requirement.minimum:
            triaged.route = PROBE
        triaged.slots = sorted({slot for route, slot, *_ in routes if route == QUESTION and slot})
        result[requirement.requirement_id] = triaged
    return result


def challenge_questions(analysis, state, triaged: dict, *, index, document=None, bundle=None) -> list:
    """One Reading question per challenged slot (whatever number of
    requirements point at it): an undecidable slot is already asked by
    readings.questions; a `none` slot (or an omitted section relation) is
    challenged with the requirement and lead that contest it."""

    questions, seen = [], set()
    readings = {r.reading_id: r for r in analysis.readings}
    elements = getattr(state, "reading_elements", {}) or {}
    for requirement_id, item in sorted(triaged.items()):
        for slot_id in item.slots:
            key = rd.slot_question_key(slot_id)
            if key in seen or key in state.pins or key in state.asked:
                continue
            reading_id = "/".join(slot_id.split("/")[:2])
            reading = readings.get(reading_id)
            slot = reading.slot(slot_id) if reading else None
            if slot is not None and slot.state == "undecidable":
                continue  # readings.questions asks it
            seen.add(key)
            # Legal, labelled options for a relationship slot (endpoint types,
            # rules, orientation); a role slot keeps its type options.
            legal = rd.slot_options(slot_id, analysis.readings, index, document) if document is not None else None
            options = list(slot.options) if slot is not None else []
            if not options:
                template = next((s for e in elements.values() for s in e.slots if s.slot_id == slot_id), None)
                options = list(template.options) if template else [*rd.relation_options(index), rd.NONE, rd.UNDECIDABLE]
            leads = [lead for lead in item.structural if lead["slot_id"] == slot_id]
            requirement = next((r for r in unmet(analysis) if r.requirement_id == requirement_id), None)
            counterpart = index.object_types[requirement.counterpart_type_id] if requirement else None
            evidence = _challenge_evidence(slot_id, leads, counterpart, document, bundle)
            questions.append(q.Question(
                question_id=key, kind="reading_slot", subject_ids=[slot_id, *evidence],
                prompt=_challenge_prompt(slot_id, slot, document, analysis.readings, index),
                options=q.standard_options(legal if legal is not None else
                                           [q.QuestionOption(option_id=o, label=o) for o in options if o not in rd.RESERVED]),
            ))
    return questions


def _challenge_evidence(slot_id, leads, counterpart, document, bundle=None) -> list[str]:
    """The lead rows, every heading between the slot's heading and its table
    (the 'Teams' section under the title), and prose under the heading that
    mentions the counterpart's kind ('Eight national teams')."""

    found = [lead["segment_id"] for lead in leads]
    parsed = rd._parse_slot_id(slot_id)
    if parsed is not None and document is not None:
        element, kind, rest = parsed
        column = document.columns.get(rest) if kind == "section_relation" else None
        if column is not None:
            table = document.tables[column.table_id]
            found += [h for h in table.ancestor_ids if h != element]
            if counterpart is not None:
                section = document.sections.get(element)
                labels = [counterpart.name, counterpart.key.replace("_", " ")]
                prose = [s for s in (section.descendant_ids if section else ()) if document.classes.get(s) == "prose"]
                found += [s for s in prose if bundle is not None and mentions(bundle.segment(s).text, labels)][:3]
    return list(dict.fromkeys(found))


def _challenge_prompt(slot_id, slot, document, readings, index) -> str:
    """Neutral and accurate: what the Reading did (an omitted relation is not
    a 'none' decision), what the layout is, and the question -- never a nudge
    toward either answer."""

    parsed = rd._parse_slot_id(slot_id)
    if parsed is not None and parsed[1] == "section_relation" and document is not None:
        heading_id, column_id = parsed[0], parsed[2]
        column = document.columns.get(column_id)
        heading_reading = next((r for r in readings if r.element_id == heading_id), None)
        heading_slot = heading_reading.slot(f"{heading_reading.reading_id}/heading_entity") if heading_reading else None
        heading_type = rd.resolve_type(index, heading_slot.choice) if heading_slot and heading_slot.state == "decided" else None
        column_type = rd._role_type(readings, column_id, index)
        table = document.tables[column.table_id] if column else None
        between = [document.sections[h].heading for h in (table.ancestor_ids if table else ()) if h != heading_id and h in document.sections]
        done = ("decided that the layout states no relationship here" if slot is not None and slot.state == "decided"
                else "did not state any relationship here")
        return (f"Heading {heading_id} was read as a {heading_type.name if heading_type else 'entity'}. Table {column.table_id if column else ''}"
                f"{' (in section ' + ', '.join(repr(b) for b in between) + ')' if between else ''} sits under it, and its column "
                f"{column_id} was read as {column_type.name if column_type else 'entities'}. The Reading {done}. Considering the "
                "headings, the table and the text under the heading, which relationship -- if any -- does the document state "
                "between the heading's entity and each entity of that column?")
    done = f"decided '{slot.choice}'" if slot is not None and slot.state == "decided" else "left this open"
    return (f"The Reading {done} for {slot_id}. Given the layout shown and the rows cited, which option does the document "
            "actually state?")


def requirement_state(requirement, analysis, state, triaged=None) -> str:
    """The one negative state of an unmet requirement (module docstring)."""

    if requirement.pending_decision:
        statuses = {analysis.decision_status.get(aid, "open") for aid in requirement.pending_decision}
        return UNDECIDABLE if statuses <= {"undecidable", "rejected_answer"} else UNADJUDICATED
    if requirement.ambiguous:
        return UNDECIDABLE
    if triaged is not None:
        if triaged.route in (ANOMALY, QUESTION):
            return UNADJUDICATED
        if triaged.route == UNREAD:
            return UNINVESTIGATED
    if requirement.evidenced > 0:
        return INSUFFICIENT
    outcome = analysis.probe_outcomes.get(requirement.requirement_id)
    if triaged is not None and triaged.route == PROBE and requirement.requirement_id not in state.probed:
        return UNINVESTIGATED
    if triaged is None and outcome is None and requirement.requirement_id not in state.probed:
        return UNINVESTIGATED  # claims mode: never probed (the budget deferred it)
    if outcome in ("not_stated_contested", "found_unsupported") and requirement.requirement_id not in state.reprobed:
        return UNINVESTIGATED
    return NOT_STATED


def aggregate(states) -> str:
    """A blocked item's own state, from its own unmet requirements' states."""

    states = list(states)
    for wanted in (UNDECIDABLE, UNADJUDICATED, UNINVESTIGATED, INSUFFICIENT):
        if wanted in states:
            return wanted
    return NOT_STATED if states else ""

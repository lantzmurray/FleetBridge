# AWS Builder Center Post Drafts

These are unpublished drafts. Publication URLs and bonus eligibility remain
**UNKNOWN** until the organizer accepts the posts. Add a factual screenshot or
diagram only after checking it contains no account ID, runtime ARN, trace payload,
customer data, credential, or private link.

## Post 1 — The human problem

**Title:** A perfect repair can still leave the customer unable to work

A thin field-service ticket hides more than a device symptom. Before dispatch,
someone has to reconcile contract SLA, service history, site access,
ownership, replacement dependencies, and the evidence required to prove the
workflow is restored.

I built FieldBridge for that coordinator. It investigates a bounded synthetic
ticket and prepares one evidence-linked routing packet before a truck rolls. The
agent can inspect, route, recommend a schedule, and draft. It cannot execute
dispatch, order parts, contact a customer, change a production ticket, or close work.

The design is inspired by generalized field-service experience, but every
organization, ticket, identifier, policy, and result is synthetic.

**Suggested visual:** the thin-ticket versus decision-card screen.

## Post 2 — Why deterministic policy sits under the agent

**Title:** The model interprets; code keeps the promise

FieldBridge uses a Strands agent to decide which synthetic evidence to inspect
and to explain the result. It does not let the model choose the authoritative
SLA deadline, contracted team, internal route, required evidence, fulfillment path, closure
proof, or blocked actions.

Those decisions come from deterministic policy and schema validation. Unstated
facts remain unknown. Unsupported proposals are rejected. If model execution
fails, the result is labeled `DEGRADED_REVIEW_REQUIRED`; the application does not
pretend a live agent trace occurred.

That split made the product more useful, not less agentic: the model handles
interpretation while code owns commitments.

**Suggested visual:** the Strands/tools/deterministic-policy section of the
architecture diagram.

## Post 3 — Human approval is a product feature

**Title:** A review button should not secretly be an action button

In FieldBridge, “Approve draft” records that a person reviewed a synthetic
handoff. It does not trigger dispatch, parts ordering, customer outreach, ticket
updates, or closure.

The interface shows the SLA deadline, contracted team, internal route, missing
evidence, access constraint, restoration work, closure proof, and a sanitized tool timeline
before asking for a decision. Approve, request changes, and reject each append an
audit event.

The principle is simple: interrupt the coordinator only for evidence or authority
the agent cannot safely resolve, and make that stop point visible.

**Suggested visual:** the decision card and appended review event.

## Publication record

| Post | Builder Center URL | Published | Organizer credit verified |
| --- | --- | --- | --- |
| Human problem | UNKNOWN | UNKNOWN | UNKNOWN |
| Deterministic policy | UNKNOWN | UNKNOWN | UNKNOWN |
| Human approval | UNKNOWN | UNKNOWN | UNKNOWN |

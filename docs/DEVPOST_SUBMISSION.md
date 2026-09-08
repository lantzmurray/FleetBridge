# Devpost Submission Draft

All bracketed evidence fields remain **UNKNOWN** until verified. This is a draft,
not proof of submission or deployment.

## Project

**FieldBridge**

**Tagline:** A governed Strands agent that turns a thin field-service ticket into
the safest next human decision before a truck rolls.

**Track:** Professional Agents

## Inspiration

A technician can replace a device perfectly and still leave the customer unable
to work. In field service, the hidden work happens before dispatch: coordinators
must reconcile contract SLA, service history, site access, actual-user
evidence, replacement dependencies, and restoration steps from an incomplete
ticket. FieldBridge is inspired by generalized first-person field-service
experience. Every organization, policy, ticket, identifier, and result in the
project is original synthetic data.

## What it does

FieldBridge investigates one of two bounded synthetic tickets in the background.
It uses evidence-specific tools, applies deterministic policy, and returns one
decision card with the SLA deadline, contracted team, internal routing team, point
of contact, missing evidence, site-access constraint, fulfillment plan,
restoration steps, closure proof, and blocked actions. The coordinator can approve
the draft, prepare an information request, request internal changes, or reject it.
The information request is visibly marked as a draft and is never sent by the
agent. Every decision is appended to the audit timeline; it never executes
dispatch, orders parts, contacts a customer, changes a production ticket, or
closes work.

The flagship story begins with: “Urgent—replace the printer. Send someone today.”
FieldBridge discovers that the site requires a chaperone, the actual user and
serial evidence are missing, and a replacement requires network registration plus
managed-workflow restoration. The fax scenario follows a different evidence path
and routes to the dedicated platform owner without inventing a device serial.

## How we built it

- Python 3.12, FastAPI, and immutable typed records
- Strands Agents with narrow synthetic evidence tools
- Amazon Nova Lite through Amazon Bedrock, configured explicitly
- Deterministic policy validation as the authority beneath model output
- Amazon Bedrock AgentCore Runtime for the worker
- API Gateway/Lambda façade, AWS WAF controls, DynamoDB review ledger, Secrets
  Manager HMAC key, and CloudWatch observability
- Pytest, Ruff, coverage, `pip-audit`, release validation, and a 15-case product
  evaluation suite

## Responsible-agent design

The browser cannot submit free-form prompts, arbitrary tickets, or customer data.
The model cannot change policy or gain operational tools. Unsupported facts stay
unknown. If model execution fails, the system returns a deterministic packet
labeled `DEGRADED_REVIEW_REQUIRED` and does not fabricate a tool trace. Human
approval means only that a synthetic draft was reviewed.

## Challenges

The hard part was not generating prose. It was separating model interpretation
from authoritative policy, preserving unknown evidence, making tool use visible
without exposing chain-of-thought, and designing a useful human stop point before
any real-world action.

## Accomplishments

- A memorable before/after operator workflow instead of a feature tour
- Scenario-specific evidence paths and deterministic validation
- A strict synthetic-only public boundary with explicit blocked actions
- Review workflow, append-only events, and repeatable product evals
- Deployment-as-code with least-privilege roles and cost/abuse controls
- Editable draw.io architecture with AWS4 service icons plus a GitHub-rendered SVG preview

Do not add test totals, coverage, live-run counts, latency, impact metrics, or AWS
claims here until captured from the exact submitted revision.

## Potential impact and pilot measurement

FieldBridge targets a repeated coordination task rather than a one-time answer.
For every thin service ticket, a coordinator may need to reconcile contract,
history, access, routing, contact, restoration, and closure evidence before a
visit can be responsibly scheduled. The demonstrated product consolidates those
checks into one review point and makes missing evidence visible before a human
dispatch decision.

A controlled enterprise pilot would measure intake-to-review time, evidence gaps
caught before scheduling, routing corrections, SLA-risk detection, and repeat
visits caused by incomplete restoration handoffs. No time-saved, SLA-improvement,
or cost-reduction result is claimed before that pilot.

## What we learned

Agent safety is more than filtering output. It is deciding which facts a model may
interpret, which rules code must own, which tools should not exist, and what
evidence a human needs before authorizing the next step.

## What's next

After the synthetic demo, the next step would be an authenticated, tenant-isolated
pilot with explicit data governance and read-only connectors. Operational writes
would require a separate security and approval design; they are intentionally out
of scope here.

## Evidence fields

| Field | Value |
| --- | --- |
| Public GitHub repository | UNKNOWN |
| Live application | UNKNOWN |
| Public English demo video (`<5` minutes) | UNKNOWN |
| Git revision | UNKNOWN |
| Façade image digest | UNKNOWN |
| AgentCore image digest | UNKNOWN |
| AgentCore runtime ARN/revision | UNKNOWN |
| Local Bedrock model run | VERIFIED 2026-09-07 for both synthetic scenarios |
| AgentCore run and CloudWatch trace | UNKNOWN |
| 15-case `pass^3` evaluation report | UNKNOWN |
| Clean Python 3.12 CI result | UNKNOWN |
| AWS Builder ID field complete | UNKNOWN |

## Pre-existing tools and disclosure

FieldBridge uses the open-source Strands Agents SDK, FastAPI, Uvicorn, Pytest,
Ruff, and standard AWS services. The application-specific policy, synthetic
fixtures, workflow, interface, evaluation cases, architecture, and submission
materials are this project's work. Before submission, confirm the hackathon's
eligibility window and disclose any application-specific code that predates it;
that fact is currently **UNKNOWN**.

## Final submission checklist

- [ ] Repository is public under the submitter's account; MIT is visible in the
  repository About panel.
- [ ] README install/run steps pass from a clean clone.
- [ ] Architecture SVG renders and matches the deployed resources.
- [ ] Live URL, video, and every evidence field above are verified and public.
- [ ] Video is English, under five minutes, and shows the exact deployed revision.
- [ ] AWS Builder ID and every Devpost team/eligibility field are complete.
- [ ] No private invitation URL, AWS identifier that should remain private,
  customer data, credentials, unsupported metric, or employer claim is present.

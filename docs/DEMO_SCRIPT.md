# FieldBridge Four-Minute Demo

Use [PITCH_PRACTICE.md](PITCH_PRACTICE.md) as the presenter cue card. Speak from
its seven beats rather than reading this document word for word. The preferred
cut is UI-first: the product already provides the opening hook, day-work queue,
decision reveal, audit proof, and closing boundary. Add an architecture still
only after it matches a verified AgentCore deployment.

Record one continuous take from the exact revision that passes the deployment
runbook three times. Do not claim live Bedrock, AgentCore, or CloudWatch evidence
unless it is visible and verified. Never show credentials, account IDs, real
tickets, customer data, or chain-of-thought.

## Credential-free recording rehearsal

The repository includes a repeatable Playwright recorder for the talk-over
version of this demo. It uses the approved synthetic investigator and a visible
`Recorded local rehearsal` overlay; it is not evidence of a live Bedrock or
AgentCore run.

```bash
.venv/bin/python scripts/record_demo.py --serve --port 8081
.venv/bin/python scripts/record_demo.py --rehearse
.venv/bin/python scripts/record_demo.py
```

The recording and checkpoint screenshots are written to the ignored
`output/playwright/` directory. Use the generated WebM for voiceover only. For
the judged live version, replace this rehearsal with the exact deployed
revision and repeat the runbook's live verification gates.

## 0:00–0:25 — Hook

Show the thin ticket: “Urgent—replace the printer. Send someone today.”

> A technician can replace the device perfectly and still leave the customer
> unable to work. The hidden risk is the handoff before the truck rolls.

## 0:25–0:45 — Person and problem

> FieldBridge is for the coordinator who has to reconcile contract rules,
> service history, site access, ownership, replacement dependencies, and closure
> evidence from that one incomplete note.

Point to the explicit boundary: inspect, route, recommend, prepare, and record
review; never execute dispatch, order, contact, change a production ticket, or
close work.

Briefly show the queue views—Open, Prepared, Awaiting, and Closed—then open the
flagship row. The requester, account, assignment, current status, and SLA should
make the interface read as a day-work service desk before the AI feature appears.

## 0:45–1:30 — Background investigation

Select `replacement-pressure` and click **Run background sweep**. Show the
Strands/Bedrock status and the sanitized tool timeline. Explain that the agent
chooses evidence while deterministic code owns the SLA deadline, routing team,
requirements, and blocked actions. Do not narrate hidden reasoning.

## 1:30–2:25 — The money shot

Compare the thin note with the decision card:

- computed deadline
- contracted team, internal routing team, and point of contact
- chaperone requirement
- recommended scheduling window and escalation path
- missing actual-user and serial evidence
- replacement registration and managed-workflow restoration
- closure proof and blocked actions

> FieldBridge found the work around the replacement—the work that determines
> whether the user is actually restored.

## 2:25–3:00 — Human authority and audit

First show **Prepare information request** and its **Draft only · not sent**
boundary. Reset, rerun, apply the bounded evidence correction, then approve the
draft. Point to the append-only review event.

> Approval records my review. It does not dispatch anyone or touch a production
> system; a coordinator still decides whether an onsite technician is needed.

## 3:00–3:25 — Different case, different path

Reset, run `fax-routing`, and show the platform-routing evidence path. Point out
that FieldBridge routes to the enterprise fax owner and does not invent a printer
serial requirement.

## 3:25–4:00 — Proof and close

Show the exact Git revision, image digest, AgentCore runtime revision, Nova Lite
model ID, matching CloudWatch correlation/trace evidence, clean CI, architecture,
and the 15-case `pass^3` report—only if each is verified.

> FieldBridge is not AI running field service. It is AI preparing the safest
> next human decision before a weak ticket becomes a strong mistake.

If any proof item is unavailable, label it **UNKNOWN** on screen and omit the
corresponding claim. Do not substitute a deterministic/degraded run for live
model evidence.

# FieldBridge Finalist Readiness

Assessment date: 2026-09-07

## Judge verdict

FieldBridge is now a strong, coherent Professional Agents submission with a
credible enterprise workflow, genuine Strands tool use, deterministic safety,
and a professional operator experience. It is a competitive finalist candidate,
but it is not submission-ready until the public repository, deployed AgentCore
path, CI, and final narrated video are verified.

No one can prove a finalist outcome before judging. This score estimates the
quality of the current evidence against the five equally weighted official
criteria.

| Criterion | Current evidence | Score |
| --- | --- | ---: |
| Technical implementation | Two local model-backed Strands/Nova scenarios, distinct bounded tool paths, schemas, deterministic validation, API/workflow tests; AgentCore still unverified | 4.2/5 |
| Design | Queue-first service desk, selected-record workflow, HITL review, follow-up draft, audit timeline, visible boundary | 4.4/5 |
| Potential impact | Specific coordinator audience and recurring triage/SLA problem; pilot metrics defined, but no measured production outcome | 4.1/5 |
| Creativity and originality | Agent prepares the hidden work around field dispatch while code protects commitments and humans retain action authority | 4.4/5 |
| Presentation | Hook-led UI, concise pitch card, repeatable Playwright story; final narrated public video not yet recorded | 4.0/5 |
| **Estimated total** |  | **21.1/25** |

The optional Builder Center bonus is separate and remains unverified.

## Evidence that is already strong

- One memorable failure mode: a technically correct replacement can still fail
  to restore the user's workflow.
- A named professional audience with a recognizable day-work queue.
- The replacement case uses contract, history, access, fulfillment, safety, and
  validation tools.
- The fax case uses a different contract/routing path and does not invent a
  device serial requirement.
- Deterministic code owns SLA, routing, evidence requirements, restoration,
  closure proof, and blocked actions.
- Human review records a decision without executing dispatch, ordering, contact,
  ticket mutation, or closure.
- Synthetic-only public inputs and an explicit degraded mode prevent false live
  claims.

## Release gates before claiming finalist-ready

1. Publish the complete repository and make the MIT license visible in GitHub
   About. The supplied public `lantzmurray/FieldBridge` repository was empty at
   the time of this assessment.
2. Deploy the exact release revision to AgentCore and the public FastAPI façade;
   verify the immutable image digests, runtime revision, and public URL.
3. Pass the 15-case evaluation three consecutive times against that deployment
   and capture matching sanitized CloudWatch trace evidence.
4. Confirm the public repository CI passes on Python 3.12. Local verification is
   currently Python 3.14 and does not replace the CI result.
5. Record the final human-narrated UI demo from the deployed revision, keep it
   under five minutes, and upload it publicly to YouTube or Vimeo.
6. Complete the Devpost fields and AWS Builder ID. Publish Builder Center posts
   only with verified claims.

## Enterprise positioning

The product can credibly be described as ready for a controlled enterprise
pilot once deployment and access controls are verified. It should not yet be
described as production-ready because the public demonstration deliberately has
no real ticket connector, tenant authentication, customer data, or operational
writes.

Pilot success should measure:

- time from ticket intake to review-ready handoff;
- missing serial, user, and access evidence caught before scheduling;
- routing corrections before field dispatch;
- SLA-at-risk cases surfaced before the deadline;
- repeat visits attributable to incomplete replacement/restoration handoffs.

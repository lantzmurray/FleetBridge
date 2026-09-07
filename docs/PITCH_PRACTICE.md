# FieldBridge Pitch Practice Card

Use the application as the presentation. The first screen already works as the
opening slide, and the operating-boundary panel works as the close. Add a brief
architecture still only after AgentCore is deployed and the diagram matches the
verified resources.

These are speaking beats, not a script. Paraphrase them in your own voice.

## The seven beats to remember

1. **Hook:** A technician can replace the device perfectly and still leave the
   customer unable to work.
2. **Person:** A field-service coordinator inherits thin tickets and owns the
   coordination before anyone promises a visit.
3. **Hidden work:** Contract deadline, history, access, routing, contact,
   replacement dependencies, restoration, and closure evidence are scattered.
4. **Agent:** FieldBridge investigates the approved case in the background and
   prepares one evidence-linked decision card.
5. **Authority:** Strands chooses evidence; deterministic policy owns the SLA
   deadline and route; a human owns dispatch.
6. **Proof:** The replacement and fax cases use different tools and produce
   different routes without inventing missing evidence.
7. **Why it matters:** Less coordinator searching, fewer weak handoffs, and a
   better chance of restoring the user's workflow inside the contract SLA.

## Thirty-second pitch

- Field-service tickets often arrive as one thin sentence.
- The coordinator still has to reconcile several systems before deciding what
  should happen next.
- FieldBridge uses a Strands agent to gather the relevant synthetic evidence and
  prepares the route, SLA deadline, missing facts, and restoration work.
- Deterministic policy protects commitments, and a human still decides whether
  to dispatch onsite.
- The result is a faster, safer handoff—not another chatbot and not hidden
  automation.

## Four-minute UI-first run of show

### 0:00-0:25 — Hook and audience

On screen: top of the service desk and the thin replacement ticket.

- Perfect device replacement can still fail the user's actual workflow.
- This is for the coordinator or dispatch lead working the queue every day.
- The problem begins before the truck rolls.

### 0:25-0:55 — Make the day job recognizable

On screen: queue columns and SLA-sorted ticket rows.

- Tickets arrive with a summary, contact, client, device context, and due time,
  but important evidence is still missing.
- At scale, the operator filters the queue, selects one ticket, and works the
  full record below it.
- FieldBridge takes the case as far as evidence allows before interrupting.

### 0:55-1:30 — Run the investigation

On screen: click **Run background sweep**, then point to the tool timeline.

- The Strands agent selects bounded read-only tools for this case.
- Contract, history, site access, and fulfillment are separate evidence checks.
- The timeline is sanitized: tool, status, duration, and correlation only—no
  chain-of-thought.

### 1:30-2:20 — The money shot

On screen: thin ticket beside the prepared packet, then the decision card.

- The contract becomes a concrete SLA deadline.
- The chaperone, actual user, and serial gaps become visible before scheduling.
- Replacement is not a box swap: network registration and managed-workflow
  restoration are part of the handoff.
- Closure proof defines when the user is restored, not merely when hardware was
  installed.
- The contracted team, internal route, contact, and recommended schedule are in
  one place.

### 2:20-2:50 — Ask for what is missing

On screen: click **Prepare information request**.

- The system prepares a bounded follow-up instead of inventing an answer.
- It is visibly a draft and is never sent automatically.
- This is one human stop point: the coordinator owns customer contact.

### 2:50-3:20 — Human authority and audit

On screen: reset, rerun, apply approved synthetic evidence, approve the draft,
and point to the appended event.

- A bounded correction closes the evidence gap.
- Approval records review; it does not dispatch a technician or touch a
  production ticket.
- The append-only event shows who retained authority at the decision point.

### 3:20-3:40 — Prove it is an agent, not a macro

On screen: select the fax case and run it.

- This case chooses contract and routing tools, not the replacement tool chain.
- It routes to the enterprise fax team and does not invent a printer serial.

### 3:40-4:00 — Close on value and boundary

On screen: return to the operating boundary. If the deployed revision is
verified, briefly show its live badge and architecture still.

- FieldBridge can reduce the coordination burden in a controlled enterprise
  pilot today.
- Production use would add authenticated, read-only ticketing connectors,
  tenant isolation, and the customer's data-governance controls.
- Close: FieldBridge prepares the safest next human decision before a weak
  ticket becomes a strong mistake.

## Claims to use

- “Designed to reduce coordinator search and handoff time.”
- “Two live local Bedrock scenarios completed with different Strands tool
  paths.”
- “The deterministic layer owns SLA, routing, required evidence, and blocked
  actions.”
- “The public demo is synthetic-only and human-reviewed.”
- “This is ready for a controlled enterprise pilot after deployment and access
  controls are verified.”

## Claims to avoid until measured or deployed

- Do not say FieldBridge has already saved a specific number of hours.
- Do not claim a reduction in SLA misses, truck rolls, or support cost without a
  measured pilot.
- Do not call the current synthetic demo production-ready.
- Do not claim AgentCore, CloudWatch, DynamoDB, or a public application is live
  until the exact submitted revision is verified.
- Do not describe approval as dispatch.

## Practice method

1. Practice the seven beats without the screen until they take 45-60 seconds.
2. Rehearse once while clicking, aiming for 3:30-4:10 rather than exactly four
   minutes.
3. Watch once with the sound off. The UI should still communicate the story.
4. Record your narration separately if that makes delivery more natural, then
   align it to the Playwright capture.
5. Keep the final export under five minutes and leave several seconds of buffer.

## Likely judge questions

**Why use an agent instead of a rules engine?**

Thin narrative tickets require contextual evidence selection. Strands handles
that investigation; deterministic policy protects commitments such as the SLA,
route, and action boundary.

**Why does it not dispatch automatically?**

Dispatch changes cost, scheduling, access, and customer expectations. FieldBridge
prepares that decision and preserves human authority rather than hiding a risky
write action behind an approval button.

**What makes the impact credible without a production pilot?**

The demo shows the exact recurring coordination work it consolidates and the
failure modes it catches. Time savings and SLA improvement remain hypotheses to
measure in a controlled pilot, not invented results.

**What would an enterprise deployment add?**

Authenticated read-only connectors, tenant isolation, customer-approved data
retention, role-mapped review, monitoring, and a separate security review before
any operational write integration.

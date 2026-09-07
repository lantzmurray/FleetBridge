(function () {
  "use strict";

  let state = Object.freeze({
    scenarios: [],
    selectedId: "",
    run: null,
    events: [],
    filter: "all",
    runsByScenario: {},
    eventsByScenario: {},
  });

  const elements = {
    select: document.querySelector("#scenario-select"),
    list: document.querySelector("#scenario-list"),
    inboxCount: document.querySelector("#inbox-count"),
    deskTicketCount: document.querySelector("#desk-ticket-count"),
    queueRowCount: document.querySelector("#queue-row-count"),
    queueEmpty: document.querySelector("#queue-empty"),
    queueTabs: Array.from(document.querySelectorAll("[data-queue-filter]")),
    queueCounts: {
      all: document.querySelector("#queue-count-all"),
      open: document.querySelector("#queue-count-open"),
      prepared: document.querySelector("#queue-count-prepared"),
      awaiting: document.querySelector("#queue-count-awaiting"),
      closed: document.querySelector("#queue-count-closed"),
    },
    navCounts: {
      all: document.querySelector("#nav-my-queue-count"),
      awaiting: document.querySelector("#nav-awaiting-count"),
      prepared: document.querySelector("#nav-prepared-count"),
    },
    runButton: document.querySelector("#run-button"),
    resetButton: document.querySelector("#reset-button"),
    systemStatus: document.querySelector("#system-status"),
    caseTitle: document.querySelector("#case-title"),
    ticketAccount: document.querySelector("#ticket-account"),
    ticketRequester: document.querySelector("#ticket-requester"),
    ticketChannel: document.querySelector("#ticket-channel"),
    ticketStatus: document.querySelector("#ticket-status"),
    ticketRequesterDetail: document.querySelector("#ticket-requester-detail"),
    ticketAssignedTeam: document.querySelector("#ticket-assigned-team"),
    ticketSlaPreview: document.querySelector("#ticket-sla-preview"),
    sourceNote: document.querySelector("#source-note"),
    packetSummary: document.querySelector("#packet-summary"),
    modeBadge: document.querySelector("#mode-badge"),
    stateBadge: document.querySelector("#state-badge"),
    docketCount: document.querySelector("#docket-count"),
    decisionTitle: document.querySelector("#decision-title"),
    exceptionFlag: document.querySelector("#exception-flag"),
    deadline: document.querySelector("#deadline"),
    owner: document.querySelector("#owner"),
    routeTeam: document.querySelector("#route-team"),
    internalTeam: document.querySelector("#internal-team"),
    pointOfContact: document.querySelector("#point-of-contact"),
    scheduleRecommendation: document.querySelector("#schedule-recommendation"),
    escalationRecommendation: document.querySelector("#escalation-recommendation"),
    dispatchRecommendation: document.querySelector("#dispatch-recommendation"),
    accessConstraint: document.querySelector("#access-constraint"),
    fulfillment: document.querySelector("#fulfillment"),
    missingEvidence: document.querySelector("#missing-evidence"),
    restorationSteps: document.querySelector("#restoration-steps"),
    closureProof: document.querySelector("#closure-proof"),
    blockedActions: document.querySelector("#blocked-actions"),
    correlationId: document.querySelector("#correlation-id"),
    toolTimeline: document.querySelector("#tool-timeline"),
    auditTimeline: document.querySelector("#audit-timeline"),
    revisionLabel: document.querySelector("#revision-label"),
    reasonCode: document.querySelector("#reason-code"),
    correctionButton: document.querySelector("#correction-button"),
    requestInfoButton: document.querySelector("#request-info-button"),
    outreachDraft: document.querySelector("#outreach-draft"),
    outreachCopy: document.querySelector("#outreach-copy"),
    reviewActions: Array.from(document.querySelectorAll(".review-action")),
  };

  const INFORMATION_REQUEST = Object.freeze({
    decision: "request_changes",
    reason_code: "insufficient_evidence",
  });

  function updateState(changes) {
    state = Object.freeze({ ...state, ...changes });
  }

  function node(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  }

  function idempotencyKey() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return `fieldbridge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  async function request(path, options) {
    const response = await window.fetch(path, options);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "The demo service could not complete the request.");
    }
    return response.json();
  }

  function setStatus(message, kind) {
    elements.systemStatus.textContent = message;
    elements.systemStatus.dataset.kind = kind || "neutral";
  }

  function selectedScenario() {
    return state.scenarios.find((item) => item.id === state.selectedId);
  }

  function runFor(scenario) {
    return state.runsByScenario[scenario.id] || null;
  }

  function queueCategory(scenario) {
    const run = runFor(scenario);
    if (!run) return scenario.queue_status.toLowerCase();
    if (run.state === "PREPARED") return "prepared";
    if (["APPROVED_DRAFT", "REJECTED"].includes(run.state)) return "closed";
    if (["REVIEW_REQUIRED", "DEGRADED_REVIEW_REQUIRED", "CHANGES_REQUESTED"].includes(run.state)) {
      return "awaiting";
    }
    return "open";
  }

  function ticketStatusLabel(scenario) {
    const run = runFor(scenario);
    if (!run) return scenario.queue_status === "PREPARED" ? "Prepared" : "Open";
    const labels = {
      PREPARED: "Prepared",
      REVIEW_REQUIRED: "Awaiting coordinator",
      DEGRADED_REVIEW_REQUIRED: "Manual review",
      CHANGES_REQUESTED: "Awaiting requester",
      APPROVED_DRAFT: "Approved draft",
      REJECTED: "Rejected",
    };
    return labels[run.state] || "Open";
  }

  function queueCounts() {
    return state.scenarios.reduce(
      (counts, scenario) => {
        const category = queueCategory(scenario);
        return { ...counts, all: counts.all + 1, [category]: counts[category] + 1 };
      },
      { all: 0, open: 0, prepared: 0, awaiting: 0, closed: 0 },
    );
  }

  function renderScenarios() {
    elements.select.replaceChildren();
    elements.list.replaceChildren();
    const counts = queueCounts();
    elements.inboxCount.textContent = String(counts.all).padStart(2, "0");
    elements.deskTicketCount.textContent = String(counts.all).padStart(2, "0");
    Object.entries(elements.queueCounts).forEach(([name, element]) => {
      element.textContent = String(counts[name]);
    });
    elements.navCounts.all.textContent = String(counts.all).padStart(2, "0");
    elements.navCounts.awaiting.textContent = String(counts.awaiting).padStart(2, "0");
    elements.navCounts.prepared.textContent = String(counts.prepared).padStart(2, "0");

    state.scenarios.forEach((scenario) => {
      const option = node("option", `${scenario.ticket_id} · ${scenario.title}`);
      option.value = scenario.id;
      elements.select.append(option);
    });

    const visible = state.scenarios.filter(
      (scenario) => state.filter === "all" || queueCategory(scenario) === state.filter,
    );
    visible.forEach((scenario) => {
      const button = node("button", undefined, "scenario-card");
      button.type = "button";
      button.dataset.scenarioId = scenario.id;
      button.setAttribute("aria-pressed", String(scenario.id === state.selectedId));

      const summary = node("span", undefined, "queue-cell queue-summary");
      summary.append(node("strong", scenario.title));
      summary.append(node("small", scenario.summary));
      const ticket = node("span", undefined, "queue-cell queue-ticket");
      ticket.append(node("strong", scenario.ticket_id));
      const status = node("span", ticketStatusLabel(scenario), "queue-status");
      status.dataset.status = queueCategory(scenario);
      const cells = [
        [scenario.received_at, "time"],
        [summary, "summary"],
        [scenario.serial, "serial"],
        [scenario.application, "application"],
        [scenario.contact, "contact"],
        [scenario.client, "client"],
        [scenario.due, "due"],
        [ticket, "ticket"],
        [status, "status"],
      ];
      cells.forEach(([value, column]) => {
        const cell = typeof value === "string"
          ? node("span", value, `queue-cell queue-cell-${column}`)
          : value;
        cell.dataset.column = column;
        if (column === "summary") cell.classList.add("queue-cell-summary");
        if (column === "ticket") cell.classList.add("queue-cell-ticket");
        button.append(cell);
      });
      button.addEventListener("click", () => chooseScenario(scenario.id));
      elements.list.append(button);
    });

    elements.queueEmpty.hidden = visible.length !== 0;
    elements.queueRowCount.textContent = `${visible.length} ${visible.length === 1 ? "ticket" : "tickets"}`;
    elements.queueTabs.forEach((tab) => {
      const active = tab.dataset.queueFilter === state.filter;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-pressed", String(active));
    });
    elements.select.value = state.selectedId;
  }

  function renderTicketContext(scenario) {
    elements.caseTitle.textContent = `${scenario.ticket_id} · ${scenario.title}`;
    elements.ticketAccount.textContent = scenario.account;
    elements.ticketRequester.textContent = scenario.requester;
    elements.ticketChannel.textContent = scenario.channel;
    elements.ticketStatus.textContent = ticketStatusLabel(scenario);
    elements.ticketRequesterDetail.textContent = scenario.requester;
    elements.ticketAssignedTeam.textContent = scenario.assigned_team;
    elements.ticketSlaPreview.textContent = scenario.sla_preview;
  }

  function resetDecisionView() {
    const emptyFields = [
      elements.deadline,
      elements.owner,
      elements.routeTeam,
      elements.internalTeam,
      elements.pointOfContact,
      elements.scheduleRecommendation,
      elements.escalationRecommendation,
      elements.dispatchRecommendation,
      elements.accessConstraint,
      elements.fulfillment,
    ];
    emptyFields.forEach((field) => { field.textContent = "—"; });
    elements.modeBadge.textContent = "IDLE";
    elements.modeBadge.dataset.mode = "idle";
    elements.stateBadge.textContent = "CREATED";
    elements.decisionTitle.textContent = "Awaiting investigation";
    elements.exceptionFlag.textContent = "No run";
    elements.docketCount.textContent = "0 exceptions";
    elements.correlationId.textContent = "—";
    elements.revisionLabel.textContent = "Revision · local";
    renderList(elements.missingEvidence, ["Not evaluated"], false);
    renderList(elements.restorationSteps, ["Not evaluated"], true);
    renderList(elements.closureProof, ["Not evaluated"], false);
    renderList(elements.blockedActions, ["Dispatch, contact, ordering, ticket mutation, and closure remain blocked."], false);
    elements.reasonCode.disabled = true;
    elements.correctionButton.disabled = true;
    elements.requestInfoButton.disabled = true;
    elements.reviewActions.forEach((button) => { button.disabled = true; });
    elements.outreachDraft.hidden = true;
  }

  function chooseScenario(scenarioId) {
    const run = state.runsByScenario[scenarioId] || null;
    const events = state.eventsByScenario[scenarioId] || [];
    updateState({ selectedId: scenarioId, run, events });
    const scenario = selectedScenario();
    elements.select.value = scenarioId;
    renderTicketContext(scenario);
    elements.sourceNote.textContent = `“${scenario.summary}”`;
    elements.packetSummary.textContent = "Ready to investigate contract, routing, access, fulfillment, and closure dependencies.";
    elements.outreachDraft.hidden = true;
    if (run) {
      renderRun();
      renderEvents();
    } else {
      resetDecisionView();
    }
    renderScenarios();
    setStatus(`${scenario.ticket_id} selected. Run the bounded background sweep.`, "neutral");
  }

  function filterQueue(filter) {
    if (!Object.hasOwn(elements.queueCounts, filter)) return;
    updateState({ filter });
    renderScenarios();
  }

  function renderList(container, items, ordered) {
    container.replaceChildren();
    const values = items.length ? items : ["None identified"];
    values.forEach((value, index) => {
      const item = node("li");
      if (ordered) item.dataset.step = String(index + 1).padStart(2, "0");
      item.append(node("span", value));
      container.append(item);
    });
  }

  function renderRun() {
    const run = state.run;
    const decision = run.decision;
    const scenario = selectedScenario();
    renderTicketContext(scenario);
    elements.sourceNote.textContent = `“${run.source_note}”`;
    elements.packetSummary.textContent = `Route to ${decision.internal_team.replaceAll("_", " ")} for ${decision.contracted_team}. ${decision.missing_evidence.length} evidence gaps require review.`;
    elements.modeBadge.textContent = run.mode;
    elements.modeBadge.dataset.mode = run.mode.toLowerCase();
    elements.modeBadge.title = run.mode_label;
    elements.stateBadge.textContent = run.state.replaceAll("_", " ");
    const exceptionCount = decision.missing_evidence.length + decision.review_reasons.length;
    elements.docketCount.textContent = exceptionCount ? `${exceptionCount} exceptions` : "Routine · no exceptions";
    const reviewable = run.state === "PREPARED" || run.state === "REVIEW_REQUIRED";
    elements.decisionTitle.textContent = reviewable
      ? "Coordinator review required"
      : run.state === "DEGRADED_REVIEW_REQUIRED"
        ? "Manual review required · live agent unavailable"
        : "Review recorded";
    elements.exceptionFlag.textContent = exceptionCount ? "Review required" : "Ready to route";
    elements.deadline.textContent = decision.deadline;
    elements.owner.textContent = decision.owner.replaceAll("_", " ");
    elements.routeTeam.textContent = decision.contracted_team;
    elements.internalTeam.textContent = decision.internal_team.replaceAll("_", " ");
    elements.pointOfContact.textContent = decision.point_of_contact;
    elements.scheduleRecommendation.textContent = decision.schedule_recommendation;
    elements.escalationRecommendation.textContent = decision.escalation_recommendation;
    elements.dispatchRecommendation.textContent = decision.dispatch_recommendation;
    elements.accessConstraint.textContent = decision.access_constraint;
    elements.fulfillment.textContent = decision.fulfillment_plan;
    elements.correlationId.textContent = run.correlation_id;
    elements.revisionLabel.textContent = `Revision · ${run.deployment_revision} · ${run.model_id}`;
    renderList(elements.missingEvidence, decision.missing_evidence, false);
    renderList(elements.restorationSteps, decision.restoration_steps, true);
    renderList(elements.closureProof, decision.closure_proof, false);
    renderList(elements.blockedActions, decision.blocked_actions, false);
    elements.reasonCode.disabled = !reviewable;
    elements.correctionButton.disabled = !(
      reviewable && run.scenario_id === "replacement-pressure" && decision.missing_evidence.length > 0
    );
    elements.requestInfoButton.disabled = !(reviewable && decision.missing_evidence.length > 0);
    elements.reviewActions.forEach((button) => { button.disabled = !reviewable; });
    renderScenarios();
  }

  function renderEvents() {
    elements.toolTimeline.replaceChildren();
    elements.auditTimeline.replaceChildren();
    let toolCount = 0;
    state.events.forEach((event) => {
      if (event.type === "tool") {
        toolCount += 1;
        const trace = node("li");
        trace.append(node("span", undefined, "trace-dot"));
        const traceCopy = node("div");
        traceCopy.append(node("strong", event.label));
        traceCopy.append(node("small", `${event.status} · ${event.duration_ms} ms`));
        trace.append(traceCopy);
        elements.toolTimeline.append(trace);
      }

      const audit = node("li");
      audit.append(node("time", event.occurred_at));
      audit.append(node("strong", event.label));
      const auditLabels = {
        review: "Human review recorded",
        tool: "Sanitized tool event",
        workflow: "Immutable workflow event",
      };
      audit.append(node("span", auditLabels[event.type] || "Bounded event"));
      elements.auditTimeline.append(audit);
    });
    if (toolCount === 0) {
      const trace = node("li");
      trace.append(node("span", undefined, "trace-dot"));
      const traceCopy = node("div");
      traceCopy.append(node("strong", "No live tool trace"));
      traceCopy.append(node("small", "This run used the labeled deterministic fallback."));
      trace.append(traceCopy);
      elements.toolTimeline.append(trace);
    }
  }

  async function loadScenarios() {
    try {
      const payload = await request("/api/v1/scenarios");
      const firstId = payload.scenarios[0].id;
      updateState({ scenarios: payload.scenarios, selectedId: firstId });
      renderScenarios();
      chooseScenario(firstId);
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  async function runSweep() {
    elements.runButton.disabled = true;
    elements.runButton.setAttribute("aria-busy", "true");
    setStatus("Investigating approved evidence lanes…", "working");
    try {
      const run = await request("/api/v1/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey() },
        body: JSON.stringify({ scenario_id: state.selectedId }),
      });
      const payload = await request(`/api/v1/runs/${run.run_id}/events`);
      updateState({
        run,
        events: payload.events,
        runsByScenario: { ...state.runsByScenario, [state.selectedId]: run },
        eventsByScenario: { ...state.eventsByScenario, [state.selectedId]: payload.events },
      });
      renderRun();
      renderEvents();
      const liveCompleted = run.state === "PREPARED" || run.state === "REVIEW_REQUIRED";
      setStatus(
        liveCompleted
          ? "Sweep complete. Evidence-linked draft is ready for human review."
          : "Live agent unavailable. Deterministic findings are shown, but approval is disabled.",
        liveCompleted ? "success" : "warning",
      );
      elements.decisionTitle.focus({ preventScroll: true });
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      elements.runButton.disabled = false;
      elements.runButton.removeAttribute("aria-busy");
    }
  }

  async function submitReview(payload) {
    const run = await request(`/api/v1/runs/${state.run.run_id}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const eventsPayload = await request(`/api/v1/runs/${run.run_id}/events`);
    updateState({
      run,
      events: eventsPayload.events,
      runsByScenario: { ...state.runsByScenario, [state.selectedId]: run },
      eventsByScenario: { ...state.eventsByScenario, [state.selectedId]: eventsPayload.events },
    });
    renderRun();
    renderEvents();
  }

  async function reviewDraft(decision) {
    if (!state.run) return;
    elements.reviewActions.forEach((button) => { button.disabled = true; });
    try {
      await submitReview({ decision, reason_code: elements.reasonCode.value });
      setStatus("Review recorded. No operational action was executed.", "success");
    } catch (error) {
      elements.reviewActions.forEach((button) => { button.disabled = false; });
      setStatus(error.message, "error");
    }
  }

  async function prepareInformationRequest() {
    if (!state.run || elements.requestInfoButton.disabled) return;
    elements.requestInfoButton.disabled = true;
    try {
      const missingFields = state.run.decision.missing_evidence.map(
        (gap) => gap.split(" — ")[0],
      );
      await submitReview(INFORMATION_REQUEST);
      elements.outreachCopy.textContent = `Please confirm ${missingFields.join(" and ")} so we can validate the contracted route, schedule, point of contact, and whether onsite service is needed.`;
      elements.outreachDraft.hidden = false;
      elements.outreachDraft.scrollIntoView({ behavior: "smooth", block: "nearest" });
      setStatus("Information request prepared for human review. Nothing was sent.", "success");
    } catch (error) {
      elements.requestInfoButton.disabled = false;
      setStatus(error.message, "error");
    }
  }

  async function applyCorrection() {
    if (!state.run) return;
    elements.correctionButton.disabled = true;
    try {
      const run = await request(`/api/v1/runs/${state.run.run_id}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ correction_id: "serial_and_user_confirmed" }),
      });
      const payload = await request(`/api/v1/runs/${run.run_id}/events`);
      updateState({
        run,
        events: payload.events,
        runsByScenario: { ...state.runsByScenario, [state.selectedId]: run },
        eventsByScenario: { ...state.eventsByScenario, [state.selectedId]: payload.events },
      });
      renderRun();
      renderEvents();
      setStatus("Approved synthetic serial and user-role evidence added to the draft.", "success");
    } catch (error) {
      elements.correctionButton.disabled = false;
      setStatus(error.message, "error");
    }
  }

  async function resetDemo() {
    try {
      await request("/api/v1/demo/reset", { method: "POST" });
      window.location.reload();
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  elements.select.addEventListener("change", (event) => chooseScenario(event.target.value));
  elements.runButton.addEventListener("click", runSweep);
  elements.resetButton.addEventListener("click", resetDemo);
  elements.correctionButton.addEventListener("click", applyCorrection);
  elements.requestInfoButton.addEventListener("click", prepareInformationRequest);
  elements.queueTabs.forEach((tab) => {
    tab.addEventListener("click", () => filterQueue(tab.dataset.queueFilter));
  });
  const REVIEW_DECISIONS = ["approve", "request_changes", "reject"];
  elements.reviewActions.forEach((button) => {
    const decision = button.dataset.decision;
    if (!REVIEW_DECISIONS.includes(decision)) return;
    button.addEventListener("click", () => reviewDraft(decision));
  });
  loadScenarios();
})();

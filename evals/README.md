# FieldBridge Product Evals

The suite contains 15 deterministic checks against the public, synthetic-only
API. It tests the decision packet, unknown preservation, routing, action boundary,
input rejection, idempotency, and review transition. It does not grade hidden
reasoning or accept real tickets.

Start FieldBridge, then run:

```bash
python evals/run_evals.py --base-url http://127.0.0.1:8080
```

For the release stability gate, require all three attempts to pass:

```bash
python evals/run_evals.py \
  --base-url "$FIELD_BRIDGE_URL" \
  --attempts 3 \
  --output evals/results/deployed.json
```

`evals/results/` is intentionally ignored. Review the report, deployment
revision, AgentCore trace, and mode before publishing a summarized result. A
local deterministic or degraded run is not evidence of a successful Bedrock or
AgentCore invocation.

The idempotent-review case is mode-aware: a live run must accept the bounded
review, while a degraded run must reject it with a conflict because degraded
packets are not reviewable as live-agent output. Neither path is allowed to
claim a model trace.

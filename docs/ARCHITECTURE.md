# FieldBridge Architecture

![FieldBridge AWS architecture](architecture.svg)

The editable source is [`architecture.drawio`](architecture.drawio), authored
for diagrams.net/draw.io with AWS4 stencil icons. The SVG is a static preview
for GitHub and Devpost; open the draw.io file when reviewing or changing the
architecture.

[`architecture.mmd`](architecture.mmd) is retained as a compact flow reference,
but the draw.io file is the canonical diagram. It shows the submission
architecture, not proof that the AWS resources are currently live.
Deployment URL, AgentCore runtime ARN/revision, Bedrock run evidence, and
CloudWatch trace ID remain **UNKNOWN** until the verification gates in
[`DEPLOYMENT.md`](DEPLOYMENT.md) pass.

## Trust boundaries

- The browser can submit only an approved synthetic `scenario_id`; arbitrary
  ticket text and unexpected fields are rejected before model invocation.
- API Gateway and WAF provide edge throttling. The façade applies idempotency and
  daily quotas using an HMAC-derived source identifier; raw IP addresses are not
  intended for the ledger.
- The Lambda role can access only its ledger/secret and invoke the named
  FieldBridge runtime family.
- The AgentCore role can pull only the named ECR repository and invoke only the
  selected Nova Lite inference profile/foundation model, plus the telemetry
  actions required by AWS.
- DynamoDB records expire after 24 hours. TTL is eventual, so expired records may
  remain briefly after the expiry timestamp.
- The agent may prepare a contracted-team route, schedule recommendation, point
  of contact, and escalation path. Human approval records review only; there is
  no dispatch execution, ordering, customer-contact, production-ticket, or
  closure integration.

## Failure behavior

If Strands, Bedrock, or AgentCore fails, FieldBridge may return the deterministic
packet only when it is clearly labeled `DEGRADED_REVIEW_REQUIRED`. Degraded mode
does not fabricate tool events, a model identifier, or a CloudWatch trace. The
request correlation ID may remain visible for local diagnostics, but it is not
evidence of a live model run.

## Current evidence level

The repository can prove local behavior through tests and the evaluation suite.
The diagram becomes deployment evidence only after the exact image digest,
CloudFormation stack outputs, AgentCore revision, three consecutive live runs,
and corresponding CloudWatch traces have been captured and reviewed.

# AWS Deployment and Verification Runbook

Deployment status: **VERIFIED 2026-09-09** (stack `fieldbridge-demo`, region
`us-east-1`, account `860738048934`).

| Artifact | Verified value |
| --- | --- |
| Public API URL | `https://mh6bxtoj2m.execute-api.us-east-1.amazonaws.com/Prod/` |
| Git revision (runtime artifacts) | `f9bc5cc68824` |
| AgentCore runtime ARN | `arn:aws:bedrock-agentcore:us-east-1:860738048934:runtime/FieldBridgeAgent-Pk5MSF41ZM` |
| Agent image (ECR `fieldbridge-agent`) | digest `sha256:0db6ffe3001ccb67fbcf5225c97bb140c13b70dfff8991ae35b89c371108e6f2` |
| Façade image | digest `sha256:15650c712bd82366af8fdbc5dd8beb78fb193eb066d6cf7cd1cb232ed2a070c3` |
| Run ledger | DynamoDB `fieldbridge-demo-RunLedger-1B2FN4KK604HQ` (24h TTL) |
| Model | `us.amazon.nova-lite-v1:0` (live runs confirmed in run payloads and X-Ray traces) |
| Product evals | 15/15 passed in three consecutive attempts against the public URL |
| CI | Python 3.12 workflow green on the public repository |

Runtime artifacts were built from revision `f9bc5cc68824`; later commits are
documentation-only. Re-verify this table (and rebuild both images) before
claiming any later revision as the submitted one.

The submitted design uses an ARM64 FastAPI container in AgentCore Runtime and a
separate FastAPI façade in API Gateway/Lambda. The façade stores synthetic runs
and append-only review events in DynamoDB. The template creates no dispatch,
ordering, customer-contact, production-ticket, or closure permissions.

## Prerequisites

- AWS account and CLI credentials owned by the submitter
- Docker with `buildx`, AWS SAM CLI, and Python 3.12
- Bedrock access to `us.amazon.nova-lite-v1:0` in `us-east-1`
- Permission to create CloudFormation, ECR, Lambda, API Gateway, WAF, DynamoDB,
  Secrets Manager, IAM, AgentCore Runtime, CloudWatch, and X-Ray resources
- CloudWatch Transaction Search enabled once for AgentCore trace visibility

Current AWS references: [custom AgentCore FastAPI contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html),
[AgentCore runtime IAM](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html),
[AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html),
and [Nova Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html).

## 1. Verify locally before creating cloud resources

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python scripts/validate_release.py
.venv/bin/pytest -q
.venv/bin/coverage run -m pytest -q
.venv/bin/coverage report --fail-under=80
.venv/bin/ruff check .
.venv/bin/pip-audit
sam validate --lint --template-file deploy/template.yaml
docker build --platform linux/arm64 -t fieldbridge-facade:local .
docker build --platform linux/arm64 -f deploy/agentcore/Dockerfile -t fieldbridge-agent:local .
```

Run each image locally and verify `/health` on the façade and `/ping` on the
worker. `/invocations` accepts only `scenario_id` and optional `correlation_id`;
it must reject prompts, arbitrary tickets, and unexpected fields.

## 2. Publish an immutable AgentCore image

Use task-specific shell variables and an explicit region. Never put AWS keys in
this repository or build arguments.

```bash
FB_AWS_REGION=us-east-1
FB_AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
FB_REVISION="$(git rev-parse --short=12 HEAD)"
FB_AGENT_REPOSITORY=fieldbridge-agent
FB_AGENT_IMAGE="${FB_AWS_ACCOUNT_ID}.dkr.ecr.${FB_AWS_REGION}.amazonaws.com/${FB_AGENT_REPOSITORY}:${FB_REVISION}"

aws ecr describe-repositories \
  --region "$FB_AWS_REGION" \
  --repository-names "$FB_AGENT_REPOSITORY" >/dev/null 2>&1 || \
aws ecr create-repository \
  --region "$FB_AWS_REGION" \
  --repository-name "$FB_AGENT_REPOSITORY" \
  --image-scanning-configuration scanOnPush=true

aws ecr get-login-password --region "$FB_AWS_REGION" | \
  docker login --username AWS --password-stdin \
  "${FB_AWS_ACCOUNT_ID}.dkr.ecr.${FB_AWS_REGION}.amazonaws.com"

docker buildx build \
  --platform linux/arm64 \
  --file deploy/agentcore/Dockerfile \
  --tag "$FB_AGENT_IMAGE" \
  --push .
```

Record the pushed digest. Do not use `latest` for a judged release.

## 3. Build and deploy the SAM stack

```bash
sam build --template-file deploy/template.yaml
sam deploy --guided \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    DeployAgentCore=true \
    AgentImageUri="$FB_AGENT_IMAGE" \
    AgentImageRepositoryName="$FB_AGENT_REPOSITORY" \
    BedrockModelId=us.amazon.nova-lite-v1:0 \
    DeploymentRevision="$FB_REVISION"
```

Review the CloudFormation change set before approval. The supplied
`deploy/samconfig.toml.example` defaults to `DeployAgentCore=false`; copy it to an
untracked `samconfig.toml` only after replacing the revision. A façade-only stack
must display AgentCore status as `UNKNOWN` or degraded—it is not a live-agent
submission.

## 4. Verify the exact deployed revision

1. Capture the `PublicApiUrl`, `AgentCoreRuntimeArn`, stack ID, façade image
   digest, agent image digest, and Git revision.
2. Confirm `/health`, `/api/v1/boundary`, and `/api/v1/scenarios` expose no
   secrets and correctly identify synthetic-only mode.
3. Run the complete replacement workflow in a browser: reset the browser view, background sweep,
   decision card, correction, approval, and audit event.
4. Run `python evals/run_evals.py --base-url "$FIELD_BRIDGE_URL" --attempts 3`.
   All 15 cases must pass in all three consecutive attempts.
5. Confirm the flagship and fax cases used different expected tool paths and
   that the UI shows sanitized tool name, status, duration, and correlation ID.
6. In CloudWatch, confirm Transaction Search shows the corresponding AgentCore
   sessions/traces. Do not expose chain-of-thought or copy payloads into public
   material.
7. Confirm a forced model failure produces `DEGRADED_REVIEW_REQUIRED` with no
   fabricated trace and that no review action triggers an external operation.
8. Run IAM Access Analyzer, inspect WAF metrics, verify DynamoDB TTL is enabled,
   and confirm the roles have no operational-action permissions.

Only after those checks may `UNKNOWN` fields in the README and submission draft
be replaced with evidence-linked values. The final demo must use the same Git
revision and image digests verified here.

The reset control clears the in-memory local demo. In the shared AWS façade it
starts a fresh browser view but does not delete another judge's append-only
ledger records; those expire through the 24-hour TTL.

## Environment contract

| Variable | Component | Required behavior |
| --- | --- | --- |
| `BEDROCK_MODEL_ID` | Agent worker | Exactly `us.amazon.nova-lite-v1:0`; missing live configuration fails visibly. |
| `DEPLOYMENT_REVISION` | Both | Immutable Git revision; `UNKNOWN` is allowed only before verification. |
| `AGENTCORE_RUNTIME_ARN` | Façade | Runtime ARN from CloudFormation; `UNKNOWN` forces degraded/not-live labeling. |
| `RUN_LEDGER_TABLE` | Façade | DynamoDB table with `PK`/`SK` keys and `expires_at` TTL. |
| `SOURCE_HMAC_SECRET_ARN` | Façade | Secrets Manager ARN; never log the secret or raw source address. |

AWS SDK credentials use the normal runtime role chain. Static credentials,
tokens, customer data, and real tickets are forbidden in environment files.

## Rollback and teardown

CloudFormation updates are replacement-safe only after a smoke test. If a new
revision fails, redeploy the last verified image digest and Git revision. To
remove the demo, use `sam delete --stack-name fieldbridge-demo`; separately
remove ECR images only after confirming they are not the judged release record.

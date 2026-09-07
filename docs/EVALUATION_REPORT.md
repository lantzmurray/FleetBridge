# FieldBridge Evaluation Report

Evidence date: 2026-09-07

## Verified locally

- The replacement scenario completed a model-backed Strands run with Amazon
  Nova Lite through Bedrock.
- Its successful tool path was `load_case` → `contract_policy` →
  `service_history` → `site_access_policy` → `fulfillment_requirements` →
  `safety_boundary` → `validate_draft`.
- The fax scenario completed a different live path: `load_case` →
  `contract_policy` → `routing_policy` → `safety_boundary` → `validate_draft`.
- Deterministic validation returned the authoritative SLA deadline, route,
  evidence requirements, restoration sequence, and blocked actions.
- The fax case routed to `enterprise_fax_support` without creating a serial gap.
- Both live results kept dispatch, ordering, customer contact, ticket mutation,
  and closure blocked.

The live checks above used the submitter's configured AWS profile from the local
checkout. They prove local Strands-to-Bedrock model execution. They do not prove
an AgentCore deployment, public application, CloudWatch trace, or production
integration.

## Automated product evidence

The repository contains unit, integration, API, AWS-adapter, workflow, security
boundary, and Playwright browser tests plus 15 synthetic API evaluations. The
release gate requires:

- all tests passing;
- backend branch coverage of at least 80%;
- clean Ruff and dependency-audit results;
- valid release artifacts and deployment template;
- all 15 product evaluations passing in three consecutive attempts on the exact
  deployed revision;
- the flagship browser workflow passing three times before final recording.

Current local totals must be refreshed after the final release commit and must
not be presented as deployed evidence.

Current pre-release local result:

- 83 tests and 10 subtests passed;
- 89% backend branch coverage;
- 15 of 15 product evaluations passed in all three attempts (`pass^3`);
- Ruff and release-artifact validation passed;
- `pip-audit` reported no known dependency vulnerabilities.

The `pass^3` run used the explicitly labeled local degraded path to verify API,
policy, idempotency, and review behavior. It is not AgentCore or live-model
evidence.

## Still unverified

- AgentCore runtime and immutable image digest
- API Gateway/Lambda public URL
- DynamoDB TTL and append-only cloud ledger behavior
- CloudWatch/Transaction Search trace correlation
- Python 3.12 clean-clone CI on the public repository
- three consecutive live deployed evaluation runs
- measured enterprise time savings or SLA improvement

Status: **competitive local implementation; deployment evidence still required**.

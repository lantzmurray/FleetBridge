# Recording deployment — 2026-09-10

Public demo: https://mh6bxtoj2m.execute-api.us-east-1.amazonaws.com/Prod/

Always link and load the URL with the trailing slash. Without it the stage
prefix is dropped from the document base and static assets 403 at the WAF.

## UI v0.6.0 — Jira-style service desk (current)

The live façade now serves the redesigned issue workspace from revision
`edf37c355f2c` (commit `edf37c3`, `feat(web): Jira-style service desk issue
workspace (UI v0.6.0)`). The agent and backend remain at `f9bc5cc68824`,
which is the revision displayed in the audit panel.

- Façade image (arm64 manifest): `860738048934.dkr.ecr.us-east-1.amazonaws.com/fieldbridgedemo0a103336/facadefunctioncf76f5e7repo@sha256:e086416a4f4eec67e015400cffa65afa0062b5cfef0031e5ceedc4e1c145657c` (tag `edf37c3-ui`, index digest `sha256:85158284a47e751c0bef74ca349f2f9c50d95ca081f7cddf13f5f205dfb24d3a`)
- Lambda: `fieldbridge-demo-FacadeFunction-aYc6D6lipOmY` updated via `update-function-code`
- Local verification: `84 passed` + 10 subtests, `validate_release.py` valid, `ruff` clean
- Public product evaluation after deploy: **15/15 passed** (`pass@1`)
- Browser verification against the deployment: LIVE Nova Lite triage
  (friendly-formatted SLA deadline), synthetic evidence correction, draft
  approval, `APPROVED DRAFT` state, and `Draft approved` audit event confirmed
- Deployed-UI captures: `output/playwright/deployed-v060/live-0*.png` (local artifacts, not repo evidence)

## a4cec75 stage-relative layer (superseded by the v0.6.0 image)

The previous façade layer carried the stage-relative UI fix from `a4cec75`,
layered on the originally verified façade image.

- Previous façade digest: `sha256:15650c712bd82366af8fdbc5dd8beb78fb193eb066d6cf7cd1cb232ed2a070c3`
- AgentCore: `arn:aws:bedrock-agentcore:us-east-1:860738048934:runtime/FieldBridgeAgent-Pk5MSF41ZM`
- Public product evaluation at that layer: 15/15 passed, one complete attempt
- Browser verification correlation: `corr-4e217a82af4b46deb2163c7d`

For recording, load the page fresh (trailing-slash URL), select the replacement
trap, run the triage, show the LIVE mode badge and the AI triage decision card,
apply approved synthetic evidence, then approve the draft from the issue header
transitions and show the activity/history panel. The approval buttons appear in
the issue header only while a run is awaiting review.
The synthetic case dates are fixed fixtures; the SLA date is not today's date.
No narrated video has been recorded against this deployment yet.

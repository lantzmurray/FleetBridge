# Recording deployment — 2026-09-10

Public demo: https://mh6bxtoj2m.execute-api.us-east-1.amazonaws.com/Prod/

The live facade includes the stage-relative UI fix from `a4cec75`, layered on
the previously verified facade image. The agent and backend remain at
`f9bc5cc68824`, which is the revision displayed in the audit panel.

- Facade image: `860738048934.dkr.ecr.us-east-1.amazonaws.com/fieldbridgedemo0a103336/facadefunctioncf76f5e7repo@sha256:1b875d345f9de2dbbd226c8831de6dbc4e97182b3e2db0990ca6d68b445a60e2`
- Previous facade digest: `sha256:15650c712bd82366af8fdbc5dd8beb78fb193eb066d6cf7cd1cb232ed2a070c3`
- AgentCore: `arn:aws:bedrock-agentcore:us-east-1:860738048934:runtime/FieldBridgeAgent-Pk5MSF41ZM`
- CloudFormation change set: `fieldbridge-recording-ui-a4cec75`
- Local API/UI contract checks: 21 passed, 2 subtests passed.
- Public product evaluation: 15/15 passed, one complete attempt.
- Browser: LIVE Nova Lite investigation, seven tool events, synthetic evidence
  correction, approved draft, and append-only review event verified.
- Browser verification correlation: `corr-4e217a82af4b46deb2163c7d`.

For recording, reload the page for a fresh browser view, select the replacement
trap, run the triage, show LIVE and the decision card, apply approved
synthetic evidence, then approve the draft and show the audit timeline.
The synthetic case dates are fixed fixtures; the SLA date is not today's date.
No video has been recorded by this deployment task.

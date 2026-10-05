# MCP Connection Test Evidence

The Slack integration is an MCP server (`mcp/slack-webhook/server.mjs`) registered
with CoCo over stdio. It was tested two ways.

## 1. Automated protocol test (repeatable)

`mcp/slack-webhook/test.mjs` launches the real server and drives it with the
official MCP SDK client over stdio, which is the same transport CoCo uses. Slack is
replaced by a local mock webhook, so the test needs no secret and posts nothing.

```bash
cd mcp/slack-webhook
npm install
npm test
```

| Test | What it proves | Result |
|---|---|---|
| T1 Startup guard | Server refuses to start without `SLACK_WEBHOOK_URL`, so the secret is never hardcoded | PASS |
| T2 Handshake + tools/list | MCP initialize succeeds; exactly one tool, `send_slack_message`, with required `text` | PASS |
| T3 tools/call happy path | One JSON POST reaches the webhook; payload is `{text}` only and unchanged | PASS |
| T4 Unknown tool | Rejected with `isError`; nothing sent | PASS |
| T5 Slack rejects (400) | Error surfaced with Slack's status and body | PASS |
| T6 Network failure | Returns `isError` instead of crashing | PASS |

16/16 checks passed. Each run writes a timestamped log next to this file
(`mcp_test_*.log`).

## 2. Live end-to-end call (real Slack)

On 2026-10-04 CoCo called `mcp_slack_send_slack_message` to post the CUST-00001
Supervisor Rate Review retention alert. The tool returned
`Message posted to Slack successfully.`, the message arrived in the channel, and
the action was logged in Snowflake:

| LOG_ID | PARTY_ID | ACTION_TYPE | CHANNEL | OUTCOME | EXECUTED_AT |
|---|---|---|---|---|---|
| c9d0205f-26dd-4092-bbf0-db77ab5be3f6 | CUST-00001 | SUPERVISOR_RATE_REVIEW | SLACK_MCP | SENT | 2026-10-04 09:04:01 |

```sql
SELECT * FROM MERIDIAN.SERVING.ACTION_LOG WHERE CHANNEL = 'SLACK_MCP';
```

The payload carried only the party ID, action name, summary, reason codes and
evidence reference. It contained no customer name and no transcript text
(AGENTS.md rule 7).

**Known gap:** the log row's `RECOMMENDATION_ID` is empty because
`SERVING.NBA_RECOMMENDATION` has no ID column yet, so AGENTS.md rule 4 is only
partly met.

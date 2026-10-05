#!/usr/bin/env node
// End-to-end test of the Slack MCP server over the real stdio MCP protocol.
// Slack is replaced by a local mock webhook, so no real messages are sent and
// no secret is needed. Writes a timestamped log to coco-evidence/mcp-tests/.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport, getDefaultEnvironment } from "@modelcontextprotocol/sdk/client/stdio.js";
import { spawn } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SERVER = path.join(HERE, "server.mjs");
const LOG_DIR = path.join(HERE, "..", "..", "coco-evidence", "mcp-tests");

const results = [];
const log = (line) => { console.log(line); results.push(line); };
function check(name, ok, detail = "") {
  log(`  [${ok ? "PASS" : "FAIL"}] ${name}${detail ? " - " + detail : ""}`);
  return ok;
}

// Mock Slack webhook: records each POST body, answers with the given status.
function startMock(status, body) {
  const received = [];
  const srv = http.createServer((req, res) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => {
      received.push({ method: req.method, contentType: req.headers["content-type"], body: data });
      res.writeHead(status, { "Content-Type": "text/plain" });
      res.end(body);
    });
  });
  return new Promise((resolve) =>
    srv.listen(0, "127.0.0.1", () =>
      resolve({ url: `http://127.0.0.1:${srv.address().port}/services/TEST`, received, close: () => srv.close() })
    )
  );
}

async function connect(webhookUrl) {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [SERVER],
    env: { ...getDefaultEnvironment(), SLACK_WEBHOOK_URL: webhookUrl },
  });
  const client = new Client({ name: "meridian-mcp-test", version: "1.0.0" });
  await client.connect(transport);
  return client;
}

async function main() {
  let allPass = true;
  log(`Meridian 360 - Slack MCP server test  (${new Date().toISOString()})`);
  log(`Server: mcp/slack-webhook/server.mjs   Transport: stdio   Node ${process.version}`);
  log("=".repeat(70));

  // T1: refuses to start without the webhook secret
  log("\nT1 Startup guard (no SLACK_WEBHOOK_URL)");
  const env = { ...process.env };
  delete env.SLACK_WEBHOOK_URL;
  const t1 = await new Promise((resolve) => {
    const p = spawn(process.execPath, [SERVER], { env });
    let err = "";
    p.stderr.on("data", (d) => (err += d));
    p.on("exit", (code) => resolve({ code, err }));
  });
  allPass &= check("exits with code 1", t1.code === 1, `code=${t1.code}`);
  allPass &= check("explains missing env var", t1.err.includes("SLACK_WEBHOOK_URL"));

  // T2: MCP handshake and tool discovery
  log("\nT2 MCP handshake + tools/list");
  const okMock = await startMock(200, "ok");
  const client = await connect(okMock.url);
  const info = client.getServerVersion();
  allPass &= check("initialize handshake", info?.name === "slack-webhook", `server=${info?.name} v${info?.version}`);
  const { tools } = await client.listTools();
  allPass &= check("exposes exactly one tool", tools.length === 1, tools.map((t) => t.name).join(","));
  allPass &= check("tool is send_slack_message", tools[0]?.name === "send_slack_message");
  allPass &= check("'text' is a required input", tools[0]?.inputSchema?.required?.includes("text"));

  // T3: happy path - message reaches the webhook unchanged
  log("\nT3 tools/call -> webhook (200 OK)");
  const msg = "*Retention Alert* party `CUST-00001` | Supervisor Rate Review | evidence `POL-00714`";
  const r3 = await client.callTool({ name: "send_slack_message", arguments: { text: msg } });
  allPass &= check("tool reports success", !r3.isError && r3.content[0].text.includes("successfully"), r3.content[0].text);
  allPass &= check("webhook received exactly one POST", okMock.received.length === 1 && okMock.received[0].method === "POST");
  allPass &= check("sent as application/json", okMock.received[0]?.contentType === "application/json");
  const sent = JSON.parse(okMock.received[0]?.body || "{}");
  allPass &= check("payload is {text} only", JSON.stringify(Object.keys(sent)) === '["text"]');
  allPass &= check("text delivered unchanged", sent.text === msg);

  // T4: unknown tool is rejected
  log("\nT4 tools/call with unknown tool name");
  const r4 = await client.callTool({ name: "delete_channel", arguments: {} });
  allPass &= check("returns isError", r4.isError === true, r4.content[0].text);
  allPass &= check("nothing sent to webhook", okMock.received.length === 1);
  await client.close();
  okMock.close();

  // T5: Slack rejects the request
  log("\nT5 webhook returns 400 (e.g. revoked/invalid webhook)");
  const badMock = await startMock(400, "invalid_token");
  const c5 = await connect(badMock.url);
  const r5 = await c5.callTool({ name: "send_slack_message", arguments: { text: "test" } });
  allPass &= check("returns isError", r5.isError === true, r5.content[0].text);
  allPass &= check("surfaces Slack status + body", r5.content[0].text.includes("400") && r5.content[0].text.includes("invalid_token"));
  await c5.close();
  badMock.close();

  // T6: network failure
  log("\nT6 webhook unreachable (network failure)");
  const c6 = await connect("http://127.0.0.1:1/services/TEST");
  const r6 = await c6.callTool({ name: "send_slack_message", arguments: { text: "test" } });
  allPass &= check("returns isError instead of crashing", r6.isError === true, r6.content[0].text);
  await c6.close();

  log("\n" + "=".repeat(70));
  log(allPass ? "ALL TESTS PASSED" : "SOME TESTS FAILED");

  fs.mkdirSync(LOG_DIR, { recursive: true });
  const file = path.join(LOG_DIR, `mcp_test_${new Date().toISOString().replace(/[:.]/g, "-")}.log`);
  fs.writeFileSync(file, results.join("\n") + "\n");
  console.log(`\nLog written to ${path.relative(path.join(HERE, "..", ".."), file)}`);
  process.exit(allPass ? 0 : 1);
}

main().catch((e) => { console.error(e); process.exit(1); });

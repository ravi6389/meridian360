#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const WEBHOOK_URL = process.env.SLACK_WEBHOOK_URL;
if (!WEBHOOK_URL) {
  process.stderr.write("SLACK_WEBHOOK_URL environment variable is required\n");
  process.exit(1);
}

const server = new Server(
  { name: "slack-webhook", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "send_slack_message",
      description:
        "Post a message to the configured Slack channel via webhook. " +
        "Supports Slack mrkdwn formatting (*bold*, _italic_, `code`).",
      inputSchema: {
        type: "object",
        properties: {
          text: {
            type: "string",
            description: "The message text to post (Slack mrkdwn supported)",
          },
        },
        required: ["text"],
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  if (request.params.name !== "send_slack_message") {
    return {
      content: [{ type: "text", text: `Unknown tool: ${request.params.name}` }],
      isError: true,
    };
  }
  const { text } = request.params.arguments;
  try {
    const resp = await fetch(WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const body = await resp.text();
    if (resp.ok) {
      return { content: [{ type: "text", text: "Message posted to Slack successfully." }] };
    }
    return {
      content: [{ type: "text", text: `Slack returned ${resp.status}: ${body}` }],
      isError: true,
    };
  } catch (err) {
    return {
      content: [{ type: "text", text: `Slack request failed: ${err.message}` }],
      isError: true,
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);

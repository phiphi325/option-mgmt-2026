# Agent: cmokdknut0eko07addjy570hz

| | |
|---|---|
| **Agent ID** | `cmokdknut0eko07addjy570hz` |
| **URL** | https://hyperagent.com/agents/cmokdknut0eko07addjy570hz |
| **Documented** | 2026-05-13 |

## Access Note

This agent's configuration could **not** be retrieved during the M1.16a export session.

**Reason:** Hyperagent agent pages (`/agents/{id}`) require an authenticated browser session.
The container's browser automation tool (Browserbase) creates an unauthenticated session and
is redirected to the Hyperagent marketing homepage. The `GetAgentConfig` SDK tool only reads
the configuration of the agent that is *currently running* the thread — it cannot read an
arbitrary agent by ID.

## How to Document This Agent

To capture this agent's configuration for future export:

1. Start a new **thread within the agent** at the URL above (click "New Thread" or "Chat").
2. Ask the agent: "Please export your configuration — name, description, system prompt, tools,
   skills, memories, integrations, model settings, and learning settings."
3. The agent can call `GetAgentConfig` on itself and produce a full Markdown record.
4. Paste or commit that record into this file.

## What We Know

The agent was noted as "active for this account" on 2026-05-13. No further details
(name, purpose, model, tools) were retrievable from outside the agent's own thread.

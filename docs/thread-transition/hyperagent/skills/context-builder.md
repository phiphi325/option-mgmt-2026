# Skill: context-builder

| | |
|---|---|
| **ID** | `unknown` |
| **Description** | Integration mining and structured memory creation |
| **Tags** | — |
| **When to use** | — |

---

# Context Builder

This skill teaches you how to systematically mine the user's connected integrations and create well-structured memories that help you know the user's context from day one.

## Overview

Your job is to read data from the user's connected integrations and synthesize it into structured memories. Each memory should capture one clear piece of context -- a teammate, a project, a tool, or an organizational fact.

## Step 1: Discover Connected Integrations

Use `SearchIntegrations` to find what tools are available. Only read from integrations the user has actually connected.

## Step 2: Fetch High-Signal Data Per Integration

| Integration | What to Read | Memory Categories |
|-------------|-------------|-------------------|
| **Slack** | Channel list + descriptions, pinned messages, recent DM partners, user profile | `people`, `active_work`, `organization` |
| **Notion** | Recent pages (titles + summaries), workspace structure, shared databases | `active_work`, `project_context`, `domain_knowledge` |
| **Linear** | Active projects, current cycle issues, team membership | `active_work`, `people`, `project_context` |
| **Google Calendar** | Recurring meetings (names, attendees, frequency), upcoming events | `people`, `active_work`, `organization` |
| **Salesforce** | Active opportunities, key accounts, pipeline status | `active_work`, `project_context`, `people` |
| **GitHub** | Active repos, recent PRs, team membership, contribution patterns | `active_work`, `tools_and_workflows` |
| **Gmail** | Frequent contacts, recent thread subjects (not content) | `people`, `active_work` |
| **Jira** | Active sprints, assigned tickets, project boards | `active_work`, `project_context` |

For each integration, focus on **high-signal data**: things that reveal who the user works with, what they're working on, and how their organization operates. Skip low-value data like automated notifications or archived content.

## Step 3: Check Existing Memories

Before creating a new memory, use `SearchKnowledge` to check if a similar memory already exists. This prevents duplicates and keeps the memory set clean.

- Search for the person's name before creating a "people" memory
- Search for the project name before creating an "active_work" memory
- Search for the tool name before creating a "tools_and_workflows" memory

## Step 4: Create Well-Structured Memories

Each memory should follow these guidelines:

### Content
- **One concept per memory** -- don't cram multiple facts into one entry
- **Be specific** -- "Sarah Chen is the engineering lead for the payments team" not "Sarah is on the team"
- **Include context** -- "The Q2 product launch (Project Phoenix) is targeting June 15" not just "Project Phoenix exists"

### Categories
- `people` -- Teammates, collaborators, reporting relationships, contact context
- `active_work` -- Current projects, active tickets, ongoing initiatives with status
- `tools_and_workflows` -- Which tools are used for what, team conventions, processes
- `organization` -- Team structure, company context, departments, company info
- `project_context` -- Deeper project details, technical architecture, goals
- `domain_knowledge` -- Industry or technical knowledge relevant to the user's work
- `user_fact` -- Facts about the user themselves (role, responsibilities)
- `preference` -- User preferences for tools, communication, work style

### Importance
- **5**: Critical daily context (user's direct reports, active sprint, primary tools)
- **4**: Important recurring context (key stakeholders, major projects)
- **3**: Useful background (team structure, company info)
- **2**: Nice to have (archived projects, secondary tools)
- **1**: Minor details

### Tags
Add meaningful tags for searchability: person names, project names, team names, tool names.

### When to Use
Write a clear `whenToUse` that tells the agent when this memory is relevant:
- "When discussing the payments team or payment-related features"
- "When the user mentions Sarah or the engineering team"
- "When working on tasks related to the Q2 launch"

## Step 5: Handle Incremental Runs

When running as a scheduled update (not the first run):

1. **Focus on changes** -- Look for new channels, new team members, new projects, completed projects
2. **Update existing memories** -- If a project status changed, update the memory rather than creating a duplicate
3. **Archive stale context** -- If a project is completed or a person left, note that in the memory
4. **Report what changed** -- Summarize what's new, what's updated, and what's unchanged

If nothing has changed, say so: "Checked all connected integrations -- everything is up to date."


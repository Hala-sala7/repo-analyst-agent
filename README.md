# GitHub Repo Analyst Agent

An AI agent that answers questions about any public GitHub repository by exploring it autonomously: it decides which folders to open and which files to read, then answers with file-path citations.

```
$ python agent.py pallets/flask "How does Flask handle routing?"
Analyzing pallets/flask...
  [step 1] get_repo_overview({"owner": "pallets", "repo": "flask"})
  [step 2] list_directory({"owner": "pallets", "repo": "flask", "path": ""})
  [step 3] list_directory({"owner": "pallets", "repo": "flask", "path": "src/flask"})
  [step 4] read_file({"owner": "pallets", "repo": "flask", "path": "src/flask/sansio/scaffold.py"})
  ...
```

## How it works

The agent runs a standard **tool-use loop** on top of Claude:

1. The user's question and four tool definitions are sent to the model.
2. If the model requests a tool, the agent executes it and returns the result.
3. The model sees the result and decides the next step, either another tool call or a final answer.
4. The loop ends when the model answers, or after `MAX_STEPS` (15) as a safety limit.

```
User question → Claude ⇄ Tools (GitHub API) → Final answer
```

### Tools

| Tool | Purpose |
|---|---|
| `get_repo_overview` | Description, language, stars, topics |
| `list_directory` | Explore the folder structure |
| `read_file` | Read a file (truncated at 8k chars to protect the context window) |
| `get_recent_commits` | Recent activity |

### Design decisions

- **Errors are returned to the model, not raised.** A wrong path comes back as a `tool_result` with `is_error: true`, so the agent can recover and try another path instead of crashing.
- **Parallel tool calls.** The model can request several tools in one turn; all are executed and returned together.
- **Context management.** File contents are truncated so one large file can't fill the context window.
- **Step limit.** Prevents infinite loops and runaway API costs.
- **Read-only tools.** The agent can't modify anything, so no human confirmation step is needed.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key
export GITHUB_TOKEN=your_token   # optional, raises GitHub rate limit from 60 to 5000/hour
python agent.py <owner/repo or URL> "<question>"
```

## Possible extensions

- A code search tool (GitHub search API) for large repos
- An eval set of repos + questions with expected answers to measure accuracy
- Expose the tools as an MCP server so any MCP client can use them
- Caching of file reads between runs

"""Tools the agent can call. Each tool is a plain Python function plus a JSON schema
that tells the model what the tool does and what arguments it takes."""
import os
import base64
import requests

GITHUB_API = "https://api.github.com"
MAX_FILE_CHARS = 8000  # keep tool results small so we don't flood the context window


def _get(url: str, params: dict | None = None) -> dict | list:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")  # optional: raises the rate limit from 60 to 5000 req/hour
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code == 404:
        raise ValueError(f"Not found: {url}")
    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        raise RuntimeError("GitHub rate limit reached. Set GITHUB_TOKEN or wait an hour.")
    resp.raise_for_status()
    return resp.json()


def get_repo_overview(owner: str, repo: str) -> str:
    data = _get(f"{GITHUB_API}/repos/{owner}/{repo}")
    return (
        f"Name: {data['full_name']}\n"
        f"Description: {data.get('description') or 'n/a'}\n"
        f"Main language: {data.get('language') or 'n/a'}\n"
        f"Stars: {data['stargazers_count']} | Forks: {data['forks_count']}\n"
        f"Topics: {', '.join(data.get('topics', [])) or 'n/a'}\n"
        f"Default branch: {data['default_branch']}"
    )


def list_directory(owner: str, repo: str, path: str = "") -> str:
    items = _get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}")
    if isinstance(items, dict):  # the path was a file, not a folder
        return f"'{path}' is a file, use read_file instead."
    lines = [f"[{'dir ' if i['type'] == 'dir' else 'file'}] {i['path']}" for i in items]
    return "\n".join(lines) or "(empty directory)"


def read_file(owner: str, repo: str, path: str) -> str:
    data = _get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}")
    if isinstance(data, list):
        return f"'{path}' is a directory, use list_directory instead."
    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    if len(content) > MAX_FILE_CHARS:
        content = content[:MAX_FILE_CHARS] + f"\n\n... [truncated, file is {len(content)} chars]"
    return content


def get_recent_commits(owner: str, repo: str, limit: int = 10) -> str:
    commits = _get(f"{GITHUB_API}/repos/{owner}/{repo}/commits", params={"per_page": min(limit, 30)})
    return "\n".join(
        f"{c['sha'][:7]} | {c['commit']['author']['date'][:10]} | {c['commit']['message'].splitlines()[0]}"
        for c in commits
    )


# Maps tool names (as the model sees them) to the Python functions that run them.
TOOL_FUNCTIONS = {
    "get_repo_overview": get_repo_overview,
    "list_directory": list_directory,
    "read_file": read_file,
    "get_recent_commits": get_recent_commits,
}

_REPO_ARGS = {
    "owner": {"type": "string", "description": "Repository owner, e.g. 'pallets'"},
    "repo": {"type": "string", "description": "Repository name, e.g. 'flask'"},
}

# The descriptions matter a lot: they are the only thing the model uses to decide
# WHEN to call each tool and HOW.
TOOL_SCHEMAS = [
    {
        "name": "get_repo_overview",
        "description": "Get high-level info about a GitHub repository: description, language, stars, topics. Call this first.",
        "input_schema": {"type": "object", "properties": _REPO_ARGS, "required": ["owner", "repo"]},
    },
    {
        "name": "list_directory",
        "description": "List files and folders at a path in the repo. Use an empty path for the root. Use this to explore the structure before reading files.",
        "input_schema": {
            "type": "object",
            "properties": {**_REPO_ARGS, "path": {"type": "string", "description": "Folder path, '' for root"}},
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "read_file",
        "description": f"Read the contents of a single file. Long files are truncated to {MAX_FILE_CHARS} characters. Only read files likely to be relevant.",
        "input_schema": {
            "type": "object",
            "properties": {**_REPO_ARGS, "path": {"type": "string", "description": "File path, e.g. 'src/app.py'"}},
            "required": ["owner", "repo", "path"],
        },
    },
    {
        "name": "get_recent_commits",
        "description": "Get the most recent commit messages, useful for questions about recent activity or changes.",
        "input_schema": {
            "type": "object",
            "properties": {**_REPO_ARGS, "limit": {"type": "integer", "description": "How many commits (max 30)"}},
            "required": ["owner", "repo"],
        },
    },
]

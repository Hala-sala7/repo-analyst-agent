"""GitHub Repo Analyst Agent: answers questions about any public GitHub repo
by exploring it on its own with tools."""
import argparse
import json
import re
import sys

import anthropic

from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

MODEL = "claude-sonnet-5-5"
MAX_STEPS = 15  # safety limit so the agent can never loop forever (or burn money)

SYSTEM_PROMPT = """You are a senior software engineer who analyzes GitHub repositories.
Answer the user's question by exploring the repository with your tools.

How to work:
1. Start with get_repo_overview, then list_directory on the root.
2. Explore only the folders and files relevant to the question. Don't read everything.
3. Base your answer on what you actually read. Cite file paths for your claims.
4. If you can't find something, say so instead of guessing.
5. End your answer with a short summary of 3 bullet points."""


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Execute a tool and return (result, is_error). Errors go back to the model
    instead of crashing, so it can recover (e.g. try a different path)."""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"Unknown tool: {name}", True
    try:
        return func(**args), False
    except Exception as e:
        return f"Error: {e}", True


def run_agent(question: str, verbose: bool = True) -> str:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    messages = [{"role": "user", "content": question}]

    for step in range(1, MAX_STEPS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        # No tool requested: the model has its final answer.
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        # The model may request several tools in one turn; run them all.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if verbose:
                print(f"  [step {step}] {block.name}({json.dumps(block.input)})", file=sys.stderr)
            result, is_error = run_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": tool_results})

    return f"Stopped after {MAX_STEPS} steps without a final answer."


def parse_repo(text: str) -> str:
    """Accept 'owner/repo' or a full GitHub URL."""
    match = re.search(r"(?:github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", text.strip())
    if not match:
        raise ValueError(f"Can't parse repo: {text}")
    return f"{match.group(1)}/{match.group(2)}"


def main():
    parser = argparse.ArgumentParser(description="Ask questions about any public GitHub repo.")
    parser.add_argument("repo", help="owner/repo or a GitHub URL")
    parser.add_argument("question", help="What you want to know")
    parser.add_argument("-q", "--quiet", action="store_true", help="Hide tool-call trace")
    args = parser.parse_args()

    repo = parse_repo(args.repo)
    print(f"Analyzing {repo}...\n", file=sys.stderr)
    answer = run_agent(f"Repository: {repo}\n\nQuestion: {args.question}", verbose=not args.quiet)
    print("\n" + answer)


if __name__ == "__main__":
    main()

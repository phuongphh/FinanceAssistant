import os
import sys
import anthropic
import requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
PR_NUMBER = os.environ.get("PR_NUMBER")
REPO = os.environ.get("REPO")

if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY secret is not set.")
    sys.exit(1)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

try:
    with open("pr_diff.txt", "r") as f:
        diff = f.read().strip()
except FileNotFoundError:
    print("ERROR: pr_diff.txt not found. Diff step may have failed.")
    sys.exit(1)

if not diff:
    print("No diff found. Skipping review.")
    sys.exit(0)

SYSTEM_PROMPT = """
You are a strict code reviewer for a Vietnamese Personal Finance AI Assistant system.

You must check:

1. Does the PR modify files outside the issue scope?
2. Does it introduce hardcoded credentials, API keys, or secrets?
3. Does it modify core database models or schemas without explicit reason?
4. Are unit tests included?
5. Does it modify unrelated modules?
6. Does every new table/model include user_id for multi-tenant readiness?
7. Is business logic kept in the backend services (not in OpenClaw skills)?

If any violation is found, respond with:
FAIL: <reason>

If everything is correct, respond with:
PASS
"""

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=200,
    temperature=0,
    system=SYSTEM_PROMPT,
    messages=[
        {
            "role": "user",
            "content": diff
        }
    ]
)

result = response.content[0].text.strip()

print(result)

# Post comment to PR if GitHub token and PR number are available
if GITHUB_TOKEN and PR_NUMBER and REPO:
    comment_body = f"## Code Review Result\n\n```\n{result}\n```"
    try:
        requests.post(
            f"https://api.github.com/repos/{REPO}/issues/{PR_NUMBER}/comments",
            json={"body": comment_body},
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
        )
    except Exception as e:
        print(f"Warning: Could not post PR comment: {e}")

if result.startswith("FAIL"):
    sys.exit(1)

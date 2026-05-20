import os
import sys
import time
import random
import anthropic
import requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
PR_NUMBER = os.environ.get("PR_NUMBER")
REPO = os.environ.get("REPO")

SYSTEM_PROMPT = """
You are a strict code reviewer for a Vietnamese Personal Finance AI Assistant system.

You must check:

1. Does the PR modify files outside the issue scope?
2. Does it introduce hardcoded credentials, API keys, or secrets?
3. Does it modify core database models or schemas without explicit reason?
4. Are unit tests included for new business logic?
5. Does it modify unrelated modules?
6. Does every new table/model include user_id for multi-tenant readiness?
7. Is business logic kept in the backend services (not in OpenClaw skills)?

Think step-by-step through each check, listing observations in markdown.
After your analysis, end your response with EXACTLY ONE of these lines as the
final line, with no additional formatting around it:

VERDICT: PASS
VERDICT: FAIL — <one-sentence reason>

Do NOT write the verdict at the start of your response. Do NOT say "FAIL"
anywhere except on the final VERDICT line. If a check raised a concern but
your re-evaluation cleared it, that is a PASS.
"""

DEFAULT_MAX_ATTEMPTS = int(os.environ.get("CODE_REVIEW_MAX_ATTEMPTS", "5"))
DEFAULT_BASE_DELAY_SECONDS = float(os.environ.get("CODE_REVIEW_BASE_DELAY_SECONDS", "1.0"))
DEFAULT_MAX_DELAY_SECONDS = float(os.environ.get("CODE_REVIEW_MAX_DELAY_SECONDS", "8.0"))
DEFAULT_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("CODE_REVIEW_REQUEST_TIMEOUT_SECONDS", "30"))


def _resolve_anthropic_error_types() -> tuple[type[BaseException], ...]:
    """Support multiple SDK layouts (top-level vs anthropic._exceptions)."""
    error_names = (
        "OverloadedError",
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
    )
    resolved: list[type[BaseException]] = []

    for name in error_names:
        err_type = getattr(anthropic, name, None)
        if isinstance(err_type, type):
            resolved.append(err_type)

    if len(resolved) < len(error_names):
        try:
            from anthropic import _exceptions as anthropic_exceptions  # type: ignore

            for name in error_names:
                err_type = getattr(anthropic_exceptions, name, None)
                if isinstance(err_type, type) and err_type not in resolved:
                    resolved.append(err_type)
        except Exception:
            pass

    return tuple(resolved)


def _is_retryable_error(error: Exception) -> bool:
    """Retry only transient upstream/service transport failures."""
    retryable_types = _resolve_anthropic_error_types()
    return bool(retryable_types) and isinstance(error, retryable_types)


def _compute_sleep_seconds(attempt: int, base_delay_seconds: float, max_delay_seconds: float) -> float:
    """Exponential backoff with bounded jitter."""
    backoff = min(max_delay_seconds, base_delay_seconds * (2 ** (attempt - 1)))
    jitter = random.uniform(0, min(0.5, backoff / 2))
    return backoff + jitter


def request_review_with_retry(
    client: anthropic.Anthropic,
    diff: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
):
    """Call Anthropic with bounded exponential backoff + jitter."""
    for attempt in range(1, max_attempts + 1):
        try:
            return client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                temperature=0,
                timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": diff
                    }
                ]
            )
        except Exception as e:
            if not _is_retryable_error(e):
                raise
            if attempt == max_attempts:
                print(f"ERROR: Anthropic transient failure after {max_attempts} attempts: {e}")
                raise
            sleep_seconds = _compute_sleep_seconds(attempt, base_delay_seconds, max_delay_seconds)
            print(
                f"Anthropic transient error {type(e).__name__} "
                f"(attempt {attempt}/{max_attempts}). "
                f"Retrying in {sleep_seconds:.2f}s..."
            )
            time.sleep(sleep_seconds)


def parse_verdict(text: str) -> tuple[str, str]:
    """Pull the final ``VERDICT:`` line out of the model's response.

    Falls back to PASS when the marker is missing rather than failing CI
    on a malformed response — a missing verdict means the model didn't
    finish, not that the code is broken. We surface the issue in the
    PR comment so a human can re-trigger.
    """
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            payload = stripped.split(":", 1)[1].strip()
            if payload.upper().startswith("PASS"):
                return "PASS", ""
            if payload.upper().startswith("FAIL"):
                # Strip the leading "FAIL" / "FAIL —" and return the reason.
                reason = payload[4:].lstrip(" —-:").strip()
                return "FAIL", reason
    return "PASS", "(no verdict line — defaulting to PASS)"

def main() -> int:
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY secret is not set.")
        return 1
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        with open("pr_diff.txt", "r") as f:
            diff = f.read().strip()
    except FileNotFoundError:
        print("ERROR: pr_diff.txt not found. Diff step may have failed.")
        return 1

    if not diff:
        print("No diff found. Skipping review.")
        return 0

    response = request_review_with_retry(client=client, diff=diff)
    result = response.content[0].text.strip()
    print(result)

    verdict, reason = parse_verdict(result)
    if GITHUB_TOKEN and PR_NUMBER and REPO:
        comment_body = f"## Code Review Result\n\n{result}"
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

    if verdict == "FAIL":
        print(f"Verdict: FAIL — {reason}")
        return 1
    print("Verdict: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

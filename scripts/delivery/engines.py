"""Native CLI adapters. Never publish, deploy, auto-switch account or trust model gates.

Call on an isolated worker for product tasks. A sandbox CLI flag is not host isolation.
Raw outputs are private; only normalized metadata should enter shared receipts.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Callable

VERSIONS = {"claude": "2.1.87", "codex": "0.164.0-alpha.11.1"}
SESSION = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


@dataclass
class EngineResult:
    engine: str
    status: str
    session_id: str | None = None
    cost_usd: str | None = None
    usage: dict | None = None
    final_text: str = ""
    return_code: int | None = None
    reason: str = ""


def classify_error(text: str) -> str:
    value = text.lower()
    if any(
        s in value
        for s in ("rate_limit", "rate limit", "429", "usage limit", "quota exceeded")
    ):
        return "rate_limited"
    if any(
        s in value
        for s in (
            "unauthorized",
            "authentication",
            "invalid api key",
            "not logged",
            "401",
        )
    ):
        return "auth_failed"
    if any(s in value for s in ("max_budget", "budget exceeded", "max_turns")):
        return "blocked"
    return "infra_failed"


def command(
    engine: str,
    workdir: Path,
    output: Path,
    *,
    session_id=None,
    max_cost_usd=None,
    read_only=True,
    model=None,
    proposal_only=False,
) -> list[str]:
    if proposal_only and not read_only:
        raise ValueError("Proposal mode requires read-only execution")
    if engine not in VERSIONS:
        raise ValueError("Unsupported engine")
    if session_id is not None and not SESSION.fullmatch(session_id):
        raise ValueError(
            "Explicit valid session ID required; never use --last/--continue"
        )
    if engine == "claude":
        if (
            max_cost_usd is None
            or not Decimal(str(max_cost_usd)).is_finite()
            or Decimal(str(max_cost_usd)) <= 0
        ):
            raise ValueError("Claude requires a finite positive API budget")
        # Smoke mode exposes NO tools. Product mode must run on an external isolated host.
        tools = "" if read_only else "Read,Edit,Write,Glob,Grep"
        args = [
            "claude",
            "--bare",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "dontAsk",
            "--tools",
            tools,
            "--max-budget-usd",
            str(max_cost_usd),
            "--max-turns",
            "12",
        ]
        if tools:
            args += ["--allowedTools", tools]
        if session_id:
            args += ["--resume", session_id]
    else:
        # No API fallback. ChatGPT auth is preflighted separately by the caller.
        args = [
            "codex",
            "exec",
            "--sandbox",
            "read-only" if read_only else "workspace-write",
            "--ignore-user-config",
            "-c",
            'approval_policy="never"',
        ]
        if proposal_only:
            # Validated against the pinned CLI. No product files are mounted in cwd.
            for feature in (
                "shell_tool",
                "apps",
                "plugins",
                "browser_use",
                "computer_use",
                "multi_agent",
                "hooks",
                "skill_mcp_dependency_install",
                "view_image",
            ):
                args += ["--disable", feature]
            args += [
                "--enable",
                "skip_host_skill_discovery",
                "-c",
                'web_search="disabled"',
            ]
        if session_id:
            args += ["resume", session_id]
        args += ["--json", "--output-last-message", str(output)]
        args += ["-"]
    if model:
        args += ["--model", model]
    return args


def environment(engine: str, source: dict[str, str]) -> dict[str, str]:
    # Never inherit GH/PAT/deploy/provider credentials of the other engine.
    keep = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR")
    env = {k: source[k] for k in keep if k in source}
    if engine == "claude":
        key = source.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("Claude bare mode needs an explicitly supplied API key")
        env["ANTHROPIC_API_KEY"] = key
        env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1"
    elif engine == "codex":
        if source.get("CODEX_HOME"):
            env["CODEX_HOME"] = source["CODEX_HOME"]
        # OPENAI_API_KEY is deliberately omitted; no switch from ChatGPT to API billing.
    else:
        raise ValueError("Unsupported engine")
    return env


def parse(
    engine: str, stdout: str, stderr: str, code: int, final_text=""
) -> EngineResult:
    result = EngineResult(engine, "infra_failed", return_code=code)
    terminal = None
    errors = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if engine == "claude":
            if event.get("session_id"):
                result.session_id = event["session_id"]
            if event.get("type") == "result":
                terminal = event
                result.final_text = str(event.get("result", ""))
                cost = event.get("total_cost_usd")
                if cost is not None:
                    try:
                        n = Decimal(str(cost))
                        if n.is_finite() and n >= 0:
                            result.cost_usd = str(n)
                    except Exception:
                        pass
                result.usage = event.get("usage")
                if event.get("is_error") or event.get("subtype") != "success":
                    errors.append(
                        str(event.get("subtype", ""))
                        + " "
                        + str(event.get("errors", []))
                        + " "
                        + result.final_text
                    )
        else:
            if event.get("type") == "thread.started":
                result.session_id = event.get("thread_id")
            if event.get("type") == "turn.completed":
                terminal = event
                result.usage = event.get("usage")
            if event.get("type") in ("error", "turn.failed"):
                errors.append(
                    str(event.get("message", "")) + " " + str(event.get("error", ""))
                )
            item = event.get("item", {})
            if not isinstance(item, dict):
                item = {}
            if (
                event.get("type") == "item.completed"
                and item.get("type") == "agent_message"
            ):
                result.final_text = str(item.get("text", ""))
    if final_text:
        result.final_text = final_text
    if result.session_id is not None and not SESSION.fullmatch(str(result.session_id)):
        result.session_id = None
    # Engine completion is not review readiness; controller must run independent gates.
    if code == 0 and terminal and not errors and result.session_id:
        result.status = "completed"
    else:
        result.status = classify_error(" ".join(errors) + " " + stderr)
        result.reason = (
            "engine_error" if errors or code else "missing_terminal_or_session"
        )
    return result


def unexpected_proposal_tool(engine, event):
    if not isinstance(event, dict):
        return False
    item = event.get("item", {})
    if engine == "codex":
        return isinstance(item, dict) and item.get("type") not in (
            None,
            "agent_message",
            "reasoning",
            "error",
        )
    message = event.get("message")
    content = message.get("content", []) if isinstance(message, dict) else []
    return isinstance(content, list) and any(
        isinstance(x, dict) and x.get("type") == "tool_use" for x in content
    )


def _stop(proc):
    # The leader may have exited while descendants still own its process group.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)
    # Stop descendants that ignored SIGTERM, even if the leader exited first.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(
    engine: str,
    prompt: str,
    workdir: Path,
    private_dir: Path,
    *,
    timeout_seconds: float,
    session_id=None,
    max_cost_usd=None,
    model=None,
    read_only=True,
    source_env=None,
    heartbeat: Callable[[], None] | None = None,
    executable: str | None = None,
    check_version=True,
    proposal_only=False,
) -> EngineResult:
    if timeout_seconds <= 0:
        raise ValueError("Positive timeout required")
    workdir = workdir.resolve()
    private_dir = private_dir.resolve()
    if private_dir == workdir or workdir in private_dir.parents:
        raise ValueError("Private output must be outside worker workspace")
    private_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(private_dir, 0o700)
    final = private_dir / "final.txt"
    args = command(
        engine,
        workdir,
        final,
        session_id=session_id,
        max_cost_usd=max_cost_usd,
        read_only=read_only,
        model=model,
        proposal_only=proposal_only,
    )
    if executable:
        args[0] = executable
    try:
        env = environment(engine, os.environ if source_env is None else source_env)
    except ValueError:
        return EngineResult(engine, "auth_failed", reason="missing_explicit_auth")
    if check_version:
        try:
            version = subprocess.run(
                [args[0], "--version"],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            observed = version.stdout.strip().split()
            if version.returncode or VERSIONS[engine] not in observed:
                return EngineResult(
                    engine, "blocked", reason="runtime_version_mismatch"
                )
        except (OSError, subprocess.TimeoutExpired):
            return EngineResult(engine, "infra_failed", reason="runtime_unavailable")
    if engine == "codex" and check_version:
        try:
            auth = subprocess.run(
                [args[0], "login", "status"],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return EngineResult(engine, "auth_failed", reason="auth_status_unavailable")
        if auth.returncode or "chatgpt" not in (auth.stdout + auth.stderr).lower():
            return EngineResult(engine, "auth_failed", reason="chatgpt_login_required")
    paths = [private_dir / "events.jsonl", private_dir / "stderr.txt"]
    files = []
    proc = None
    forced = None
    try:
        for p in paths:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            files.append(os.fdopen(fd, "wb"))
        prompt_file = private_dir / "prompt.txt"
        fd = os.open(prompt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(prompt)
        prompt_input = prompt_file.open("rb")
        files.append(prompt_input)
        proc = subprocess.Popen(
            args,
            cwd=workdir,
            env=env,
            stdin=prompt_input,
            stdout=files[0],
            stderr=files[1],
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout_seconds
        next_heartbeat = 0.0
        while proc.poll() is None:
            now = time.monotonic()
            if now >= deadline:
                forced = "timeout"
                break
            if sum(p.stat().st_size for p in paths) > 8 * 1024 * 1024:
                forced = "infra_failed"
                break
            if heartbeat and now >= next_heartbeat:
                heartbeat()  # A lost lease fences/stops this process, never falls through.
                next_heartbeat = now + 1
            time.sleep(0.05)
        if sum(p.stat().st_size for p in paths) > 8 * 1024 * 1024:
            forced = "infra_failed"
        _stop(proc)
    except BaseException:
        if proc:
            _stop(proc)
        raise
    finally:
        for f in files:
            f.close()

    def bounded(path, size):
        with path.open("rb") as f:
            return f.read(size).decode(errors="replace")

    if final.exists():
        final.chmod(0o600)
    result = parse(
        engine,
        bounded(paths[0], 8 * 1024 * 1024),
        bounded(paths[1], 65536),
        proc.returncode,
        bounded(final, 1024 * 1024) if final.exists() else "",
    )
    if proposal_only:
        for line in bounded(paths[0], 8 * 1024 * 1024).splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if unexpected_proposal_tool(engine, event):
                result.status = "blocked"
                result.reason = "unexpected_tool_in_proposal_profile"
                break
    if forced:
        result.status = forced
        result.reason = "process_stopped_and_reaped"
    if session_id and result.session_id and result.session_id != session_id:
        result.status = "infra_failed"
        result.reason = "resume_session_mismatch"
    if not result.session_id and session_id:
        result.session_id = session_id
    # Final text is model output, never interpreted as control instructions here.
    receipt = private_dir / "engine-result.json"
    receipt.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n")
    receipt.chmod(0o600)
    return result

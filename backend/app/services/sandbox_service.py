"""
SmartPrep AI - Code Execution Service
Runs candidate code submissions in an isolated Piston sandbox (Docker-based).
Piston is an open-source, self-hostable code execution engine supporting 50+ languages.

Piston endpoint: http://sandbox:2000 (via docker-compose)
Fallback: PISTON_URL env var (can point to managed Piston API: https://emkc.org/api/v2/piston)

Supported languages for coding interview grading:
  python, javascript, typescript, java, cpp, c, go, rust, ruby, kotlin
"""
import os
import asyncio
import httpx
from typing import Optional
from app.utils.logger import setup_logger
from app.utils.config import settings

logger = setup_logger(__name__)

PISTON_URL = os.environ.get("PISTON_URL", "http://sandbox:2000")
PISTON_TIMEOUT = 15  # seconds
MAX_CODE_CHARS = 8000

# Language version overrides — Piston picks latest by default
LANGUAGE_VERSIONS = {
    "python": "3.10.0",
    "javascript": "18.15.0",
    "typescript": "5.0.3",
    "java": "15.0.2",
    "cpp": "10.2.0",
    "c": "10.2.0",
    "go": "1.16.2",
    "rust": "1.50.0",
    "ruby": "3.0.1",
    "kotlin": "1.8.20",
}

# Default test harnesses injected around candidate code
# These wrap the candidate's solution function and run it against test cases
PYTHON_TEST_HARNESS = """
import sys, json, traceback

def _run_tests(solution_fn, test_cases):
    results = []
    for i, tc in enumerate(test_cases):
        try:
            actual = solution_fn(*tc["args"])
            passed = actual == tc["expected"]
            results.append({"test": i+1, "passed": passed, "actual": repr(actual), "expected": repr(tc["expected"])})
        except Exception as e:
            results.append({"test": i+1, "passed": False, "error": str(e)})
    return results

# === CANDIDATE CODE ===
{code}
# === END CANDIDATE CODE ===

_test_cases = {test_cases}
try:
    _fn = {entry_point}
    _results = _run_tests(_fn, _test_cases)
    _passed = sum(1 for r in _results if r["passed"])
    print(json.dumps({{
        "status": "ok",
        "passed": _passed,
        "total": len(_results),
        "results": _results,
    }}))
except Exception as e:
    print(json.dumps({{"status": "error", "error": str(e), "traceback": traceback.format_exc()}}))
"""


class SandboxTimeoutError(Exception):
    pass


class SandboxUnavailableError(Exception):
    pass


async def _piston_request(payload: dict, timeout: int = PISTON_TIMEOUT) -> dict:
    """POST to Piston /execute with retry on transient errors."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(f"{PISTON_URL}/api/v2/execute", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise SandboxTimeoutError(f"Sandbox timed out after {timeout}s")
        except httpx.ConnectError:
            raise SandboxUnavailableError(
                "Sandbox unavailable. Start it with: docker compose --profile sandbox up"
            )


async def check_sandbox_health() -> bool:
    """Returns True if the Piston sandbox is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{PISTON_URL}/api/v2/runtimes")
            return resp.status_code == 200
    except Exception:
        return False


async def execute_code(
    code: str,
    language: str = "python",
    stdin: str = "",
    test_cases: Optional[list] = None,
    entry_point: Optional[str] = None,
    timeout: int = PISTON_TIMEOUT,
) -> dict:
    """
    Execute candidate code in the Piston sandbox.

    Args:
        code: The candidate's code submission (raw string)
        language: Programming language identifier
        stdin: Optional stdin input
        test_cases: Optional list of {args, expected} dicts for Python test harness
        entry_point: Function name to call for test harness (Python only)
        timeout: Execution timeout in seconds (max 15s)

    Returns:
        {
          "success": bool,
          "stdout": str,
          "stderr": str,
          "exit_code": int,
          "runtime_ms": float | None,
          "test_results": list | None,  # populated if test_cases provided
          "passed": int | None,
          "total": int | None,
          "error": str | None,
        }
    """
    if len(code) > MAX_CODE_CHARS:
        return {
            "success": False,
            "error": f"Code too long ({len(code)} chars, max {MAX_CODE_CHARS})",
        }

    language = language.lower().strip()
    version = LANGUAGE_VERSIONS.get(language, "")

    # For Python with test cases, inject the test harness
    actual_code = code
    if language == "python" and test_cases and entry_point:
        import json
        actual_code = PYTHON_TEST_HARNESS.format(
            code=code,
            test_cases=json.dumps(test_cases),
            entry_point=entry_point,
        )

    payload = {
        "language": language,
        "version": version,
        "files": [{"name": f"main.{_ext(language)}", "content": actual_code}],
        "stdin": stdin,
        "args": [],
        "compile_timeout": 10000,  # ms
        "run_timeout": timeout * 1000,  # ms
    }

    try:
        result = await _piston_request(payload, timeout=timeout + 5)
    except SandboxTimeoutError as e:
        return {"success": False, "error": str(e), "stdout": "", "stderr": ""}
    except SandboxUnavailableError as e:
        logger.warning(str(e))
        return {"success": False, "error": str(e), "stdout": "", "stderr": ""}
    except Exception as e:
        logger.error(f"Sandbox execute failed: {e}", exc_info=True)
        return {"success": False, "error": f"Execution failed: {str(e)}", "stdout": "", "stderr": ""}

    run = result.get("run", {})
    compile_info = result.get("compile", {})

    stdout = (run.get("stdout") or "").strip()
    stderr = (run.get("stderr") or "").strip()
    compile_stderr = (compile_info.get("stderr") or "").strip()
    exit_code = run.get("code", -1)
    success = exit_code == 0 and not compile_stderr

    # Parse JSON test harness output
    test_results = None
    passed = None
    total = None
    if test_cases and entry_point and language == "python" and stdout:
        try:
            import json
            parsed = json.loads(stdout)
            if parsed.get("status") == "ok":
                test_results = parsed.get("results", [])
                passed = parsed.get("passed", 0)
                total = parsed.get("total", 0)
            else:
                stderr = parsed.get("error", stderr)
                success = False
        except Exception:
            pass  # stdout wasn't JSON — treat as raw output

    output = {
        "success": success,
        "stdout": stdout[:4000],
        "stderr": (compile_stderr or stderr)[:2000],
        "exit_code": exit_code,
        "runtime_ms": run.get("wall_time"),
        "test_results": test_results,
        "passed": passed,
        "total": total,
    }

    logger.info(
        f"Code execution: lang={language}, exit={exit_code}, "
        f"passed={passed}/{total}, wall_time={run.get('wall_time')}ms"
    )
    return output


def _ext(language: str) -> str:
    return {
        "python": "py", "javascript": "js", "typescript": "ts",
        "java": "java", "cpp": "cpp", "c": "c", "go": "go",
        "rust": "rs", "ruby": "rb", "kotlin": "kt",
    }.get(language, "txt")

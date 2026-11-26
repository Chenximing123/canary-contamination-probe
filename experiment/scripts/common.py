#!/usr/bin/env python3
"""Shared plumbing for the pilot experiments (directions 9 and 10).

Deliberately stdlib-only: no pandas / scipy / requests, so it runs on a clean
Python 3.10+ install. Everything here is used by both pilot scripts:

  * key/base-url loading (same convention as run_experiment.py: env or .env)
  * one chat-completion call with retry/backoff (OpenAI-compatible endpoints)
  * resumable jsonl I/O
  * bootstrap CI, exact McNemar, a variance decomposition, markdown tables
  * a deterministic `stub` backend so the whole pipeline is testable offline

The stub backend is not a toy: it lets you rehearse a full run (and check your
analysis code) without spending a cent or touching the network.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # experiment/
DATA = Path(os.environ.get("PILOT_DATA_DIR", ROOT / "data"))
RESULTS = Path(os.environ.get("PILOT_RESULTS_DIR", ROOT / "results"))
MAX_RETRIES = 5


# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------
def load_key(var: str = "DEEPSEEK_API_KEY") -> str:
    """Return an API key from the environment or from experiment/.env."""
    key = os.environ.get(var, "").strip()
    if key:
        return key
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{var}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(f"{var} not found: put it in experiment/.env or the environment.")


def load_base_url() -> str:
    """OpenAI-compatible endpoint. Override to reuse a Qwen/Kimi/local server."""
    return os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")


# --------------------------------------------------------------------------
# one chat completion
# --------------------------------------------------------------------------
def chat(
    key: str,
    model: str,
    messages: list[dict],
    base_url: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 900,
    timeout: int = 180,
) -> dict:
    """POST one chat completion and return the parsed JSON response."""
    url = (base_url or load_base_url()) + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"network: {exc}") from exc
    raise RuntimeError("unreachable")


def usage_of(resp: dict) -> dict:
    """Normalise the usage block; some providers omit fields."""
    u = resp.get("usage") or {}
    return {
        "prompt_tokens": int(u.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(u.get("completion_tokens", 0) or 0),
        "total_tokens": int(u.get("total_tokens", 0) or 0),
    }


# --------------------------------------------------------------------------
# resumable jsonl
# --------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def done_keys(path: Path, *fields: str) -> set[tuple]:
    """Set of composite keys already present in a jsonl result file."""
    return {tuple(rec.get(f) for f in fields) for rec in load_jsonl(path)}


def append_jsonl(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# statistics (stdlib only)
# --------------------------------------------------------------------------
def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def bootstrap_ci(xs: list[float], iters: int = 4000, alpha: float = 0.05, seed: int = 7) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean. Returns (lo, hi)."""
    if not xs:
        return (float("nan"), float("nan"))
    if len(xs) == 1:
        return (xs[0], xs[0])
    rng = random.Random(seed)
    n = len(xs)
    stats = []
    for _ in range(iters):
        stats.append(sum(xs[rng.randrange(n)] for _ in range(n)) / n)
    stats.sort()
    lo = stats[int((alpha / 2) * iters)]
    hi = stats[int((1 - alpha / 2) * iters) - 1]
    return (lo, hi)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the two discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def eta_squared(cells: dict, factor: str) -> float:
    """SS_between / SS_total for one crossed factor.

    `cells` maps (task_id, harness_id, model_id) -> success in {0,1}. Used as a
    crude variance decomposition: how much of the outcome spread is explained
    by the harness alone, the model alone, or the task alone.
    """
    vals = list(cells.values())
    if not vals:
        return float("nan")
    grand = mean(vals)
    ss_total = sum((v - grand) ** 2 for v in vals)
    if ss_total == 0:
        return 0.0
    idx = {"task": 0, "harness": 1, "model": 2}[factor]
    groups: dict[str, list[float]] = {}
    for key, v in cells.items():
        groups.setdefault(str(key[idx]), []).append(v)
    ss_between = sum(len(g) * (mean(g) - grand) ** 2 for g in groups.values())
    return ss_between / ss_total


# --------------------------------------------------------------------------
# markdown output
# --------------------------------------------------------------------------
def md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "| " + " | ".join(["---"] * len(header)) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# backends
# --------------------------------------------------------------------------
class ApiBackend:
    """Real backend: one model, one endpoint."""

    name = "api"

    def __init__(self, key: str, model: str, base_url: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 900):
        self.key = key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict], tid: str = "") -> tuple[str, dict]:
        resp = chat(self.key, self.model, messages, self.base_url,
                    self.temperature, self.max_tokens)
        text = resp["choices"][0]["message"]["content"] or ""
        return text, usage_of(resp)


class StubBackend:
    """Offline backend that replays a task's gold plan.

    Used to verify the plumbing end to end (`selftest` subcommand) and to check
    the analysis code on synthetic data. `drop` injects a wrong final answer so
    the success/failure paths both get exercised.
    """

    name = "stub"

    def __init__(self, drop: float = 0.0, err_rate: float = 0.0, seed: int = 0):
        self.drop = drop
        self.err_rate = err_rate
        self.rng = random.Random(seed)
        self.tasks: dict[str, dict] = {}      # tid -> task, filled by the runner
        self._cursor: dict[str, int] = {}
        self._erred: set[str] = set()

    def register(self, task: dict) -> None:
        self.tasks[task["tid"]] = task

    def chat(self, messages: list[dict], tid: str = "") -> tuple[str, dict]:
        task = self.tasks[tid]
        plan = task["plan"]
        i = self._cursor.get(tid, 0)

        if self.err_rate and tid not in self._erred and self.rng.random() < self.err_rate:
            self._erred.add(tid)
            # deliberately malformed: exercises the harness's retry path
            return "I will search for the record now.", {"total_tokens": 40}

        if i >= len(plan):
            return json.dumps({"tool": "answer", "args": {"value": "__loop__"}}), {"total_tokens": 40}

        tool, args = plan[i]
        self._cursor[tid] = i + 1
        if tool == "answer" and self.rng.random() < self.drop:
            args = {"value": "__wrong__"}
        return json.dumps({"tool": tool, "args": args}), {"total_tokens": 40}

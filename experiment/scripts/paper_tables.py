#!/usr/bin/env python3
"""Regenerate the numeric tables of the paper from the raw JSONL logs.

Tables I, II, IV and V are computed from experiment/results/contam_*.jsonl.
Table III (the worked example) is re-rendered from the easy suite in
experiment/data/v3/canary_items.json.

The family statistic is the item-paired drop of accuracy,
    Delta = mean over items of (1/|F|) sum_{f in F} (y_orig - y_f),
with F_Q = {rename, paraphrase, table}, F_E = {perm, rrename, both}, and
swap reported as a single form. The 95% interval is a percentile bootstrap
that resamples *items* (common.bootstrap_ci, 4000 draws, seed 7).

Run from the repository root:

    python experiment/scripts/paper_tables.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import common as C                      # noqa: E402
import pilot_contamination as pc        # noqa: E402

F_Q = ["rename", "paraphrase", "table"]
F_E = ["perm", "rrename", "both"]


def load(tag: str) -> dict[str, dict[str, bool]]:
    recs = C.load_jsonl(C.RESULTS / f"contam_{tag}.jsonl")
    by: dict[str, dict[str, bool]] = {}
    for r in recs:
        by.setdefault(r["iid"], {})[r["form"]] = r["success"]
    return by


def family(by: dict[str, dict[str, bool]], forms: list[str]):
    """Per-item mean drop over `forms`; returns (mean, lo, hi) or None."""
    vals = []
    for d in by.values():
        if "orig" not in d:
            continue
        fs = [f for f in forms if f in d]
        if fs:
            vals.append(sum(float(d["orig"]) - float(d[f]) for f in fs) / len(fs))
    if not vals:
        return None
    lo, hi = C.bootstrap_ci(vals)
    return C.mean(vals), lo, hi


def acc(by: dict[str, dict[str, bool]], form: str) -> float:
    vals = [1.0 if d[form] else 0.0 for d in by.values() if form in d]
    return C.mean(vals) if vals else float("nan")


def line(label: str, by: dict[str, dict[str, bool]], forms: list[str]) -> str:
    s = family(by, forms)
    if s is None:
        return f"  {label:32s}   not measured"
    m, lo, hi = s
    return f"  {label:32s} {100 * m:+6.1f}  [{100 * lo:+6.1f}, {100 * hi:+6.1f}]"


def per_form(tag: str, forms: list[str]) -> None:
    by = load(tag)
    print(f"  {tag}:")
    for f in forms:
        if not any("orig" in d and f in d for d in by.values()):
            continue
        d = [float(x["orig"]) - float(x[f])
             for x in by.values() if "orig" in x and f in x]
        lo, hi = C.bootstrap_ci(d)
        print(f"    {f:10s} acc {100 * acc(by, f):5.1f}%  "
              f"drop {100 * C.mean(d):+6.1f} [{100 * lo:+6.1f}, {100 * hi:+6.1f}]")


def table_one() -> None:
    print("\nTABLE I - uncontaminated controls (hard suite, n=100)")
    print(line("A question-level (pilot3)", load("pilot3"), F_Q))
    print(line("A evidence-level (pilot3b)", load("pilot3b"), F_E))
    print(line("A row reversal (pilot3)", load("pilot3"), ["swap"]))
    print(line("B question-level (qwen_null)", load("qwen_null"), F_Q))
    print(line("B evidence-level (qwen_null)", load("qwen_null"), F_E))
    print(line("B row reversal (qwen_null)", load("qwen_null"), ["swap"]))


def table_two() -> None:
    print("\nTABLE II - detector statistic by family (1.5B, hard suite)")
    print(line("Contaminated question-level", load("qwencontam4"), F_Q))
    print(line("Contaminated evidence-level", load("qwencontam4b"), F_E))
    print(line("Contaminated row reversal", load("qwencontam4"), ["swap"]))
    print(line("Uncontaminated question-level", load("pilot3"), F_Q))
    print(line("Uncontaminated evidence-level", load("pilot3b"), F_E))
    print(line("Uncontaminated row reversal", load("pilot3"), ["swap"]))
    print("\nPer-form breakdown of the contaminated model:")
    per_form("qwencontam4", ["rename", "paraphrase", "table", "distractor", "swap"])
    per_form("qwencontam4b", ["perm", "rrename", "both"])


def table_four() -> None:
    print("\nTABLE IV - dose-response (1.5B, hard suite)")
    runs = [("5", "dr_e5"), ("12", "dr_e12"), ("30", "dr_e30"), ("60", "qwencontam4b")]
    for epochs, tag in runs:
        by = load(tag)
        s = family(by, ["perm"])
        if s is None:
            continue
        print(f"  {epochs:>3s} epochs   seen {100 * acc(by, 'orig'):5.1f}%   "
              f"permutation drop {100 * s[0]:+6.1f} [{100 * s[1]:+6.1f}, {100 * s[2]:+6.1f}]")


def table_five() -> None:
    print("\nTABLE V - baseline accuracy (original form, n=100)")
    hard = [("1.5B", "qwenbase2"), ("3B", "qwen3b"), ("7B", "qwen7b")]
    easy = [("1.5B", "b15_v3"), ("3B", "b3b_v3"), ("7B", "b7b_v3")]
    for name, runs in (("hard (6 rows, percentage)", hard), ("easy (4 rows, sum)", easy)):
        cells = [f"{100 * acc(load(tag), 'orig'):5.1f}%" for _, tag in runs]
        print(f"  {name:26s}  " + "  ".join(cells))


def table_three() -> None:
    """Re-render the worked example (an easy-suite item whose answer is 1140)."""
    path = C.DATA / "v3" / "canary_items.json"
    if not path.exists():
        print("\nTABLE III - easy-suite file not found")
        return
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    target = next((it for it in items if it.get("gold") == "1140"), None)
    if target is None:
        print("\nTABLE III - no item with answer 1140 found")
        return
    print(f"\nTABLE III - one item under five forms (easy suite; answer 1140)")
    for form in ("orig", "perm", "rrename", "paraphrase"):
        body, _ = pc.render(target, form)
        print(f"  {form:11s} " + " | ".join(
            ln.strip("- ") for ln in body.splitlines()[1:]))
    print("  table       (markdown table with the same values)")


def main() -> None:
    table_one()
    table_two()
    table_four()
    table_five()
    table_three()


if __name__ == "__main__":
    main()

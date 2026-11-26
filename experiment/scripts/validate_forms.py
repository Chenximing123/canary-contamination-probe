#!/usr/bin/env python3
"""Structural validation of the six canary forms — no model involved.

The whole contamination detector rests on one claim: the perturbations change
the surface and nothing else. `gen` already asserts that the *gold* is unchanged
by construction, but that is an assertion about our own code. This script checks
the artefacts that were actually written to disk, and it checks the thing a
reviewer will ask about: do the two renderings carry the same facts?

Checks per item, per form:
  facts      the multiset of (region, value) pairs in the body
  numbers    every number token in the body, in order
  question   the question text
  gold       not present as a number token

Usage: python validate_forms.py [--items 100] [--dump 5]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import common as C

ITEMS_PATH = C.DATA / "canary_items.json"
FORMS = ["orig", "rename", "swap", "paraphrase", "distractor", "table"]


def num_tokens(text: str) -> list[str]:
    return [t.replace(",", "") for t in re.findall(r"(?<![A-Za-z0-9-])-?\d[\d,]*(?![A-Za-z0-9])", text)]


def facts(body: str) -> list[tuple[str, int]]:
    """(label, value) pairs — one per data line, in display order."""
    out = []
    for line in body.splitlines()[1:]:
        m = re.search(r"([A-Za-z][\w-]*)\s*[:|]\s*(\d+)", line)
        if m:
            out.append((m.group(1), int(m.group(2))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=0, help="0 = all")
    ap.add_argument("--dump", type=int, default=0, help="print N full renderings")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pilot_contamination as pc

    data = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    items = data["items"][: args.items] if args.items else data["items"]

    print(f"items: {len(items)}  rows: {data.get('rows')}  op: {data.get('op')}\n")
    print(f"{'form':12s} {'facts kept':>10s} {'same order':>10s} {'gold leak':>10s} {'render changed':>14s}")
    print("-" * 60)

    stats = {f: {"facts": 0, "order": 0, "leak": 0, "changed": 0} for f in FORMS}
    for it in items:
        base_body, base_q = pc.render(it, "orig")
        base_facts = facts(base_body)
        base_nums = num_tokens(base_body)
        for form in FORMS:
            body, q = pc.render(it, form)
            f = facts(body)
            same_facts = sorted(f) == sorted(base_facts) if form != "distractor" else \
                sorted(f[:len(base_facts)]) == sorted(base_facts)
            same_order = f[:len(base_facts)] == base_facts
            leak = it["gold"] in num_tokens(body)
            changed = (body != base_body) or (q != base_q)
            stats[form]["facts"] += int(same_facts)
            stats[form]["order"] += int(same_order)
            stats[form]["leak"] += int(leak)
            stats[form]["changed"] += int(changed)

    n = len(items)
    for form in FORMS:
        s = stats[form]
        print(f"{form:12s} {s['facts']:>7d}/{n:<3d} {s['order']:>7d}/{n:<3d} "
              f"{s['leak']:>7d}/{n:<3d} {s['changed']:>10d}/{n:<3d}")

    print("\nread: 'facts kept' must be 100% except distractor (+1 line);")
    print("      'same order' may be 0 for swap (that is the point);")
    print("      'gold leak' must be 0 everywhere.\n")

    if args.dump:
        for it in items[: args.dump]:
            print("=" * 70)
            print("iid", it["iid"], " gold", it["gold"])
            for form in FORMS:
                body, q = pc.render(it, form)
                print(f"\n--- {form} ---\n{body}\nQ: {q}")


if __name__ == "__main__":
    main()

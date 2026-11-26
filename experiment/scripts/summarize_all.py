#!/usr/bin/env python3
"""One table over every contamination run on disk.

Reads `contam_<tag>.jsonl` files and prints, per run:
  orig accuracy, mean accuracy over the *equivalent* forms, the paired drop
  (orig - perturbed) with a bootstrap CI, and the per-form breakdown.

The equivalent forms are rename/swap/paraphrase/table. `distractor` is reported
separately because it changes the difficulty rather than the surface — see
protocol-contamination.md §5.2.

Usage
  python summarize_all.py --run qwenbase "Qwen2.5-1.5B base" \
                          --run qwencontam "Qwen2.5-1.5B contaminated" \
                          --run pilot2 "deepseek-chat"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import common as C

EQUIV = ["rename", "swap", "paraphrase", "table"]
ALL_FORMS = ["orig"] + EQUIV + ["distractor"]


def load(tag: str) -> list[dict]:
    return C.load_jsonl(C.RESULTS / f"contam_{tag}.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", nargs=2, action="append", required=True,
                    metavar=("TAG", "LABEL"))
    ap.add_argument("--out", default="report")
    args = ap.parse_args()

    rows, detail = [], []
    for tag, label in args.run:
        recs = load(tag)
        if not recs:
            print(f"!! no results for tag {tag}")
            continue
        by_item: dict[str, dict[str, bool]] = {}
        for r in recs:
            by_item.setdefault(r["iid"], {})[r["form"]] = r["success"]
        acc = {}
        for form in ALL_FORMS:
            vals = [1.0 if by_item[i][form] else 0.0
                    for i in by_item if form in by_item[i]]
            acc[form] = C.mean(vals) if vals else float("nan")

        drops = [float(d["orig"]) - float(d[f])
                 for d in by_item.values() if "orig" in d
                 for f in EQUIV if f in d]
        lo, hi = C.bootstrap_ci(drops)
        n_orig = sum(1 for d in by_item.values() if "orig" in d)
        perturbed = C.mean([acc[f] for f in EQUIV if acc[f] == acc[f]])
        rows.append([label, n_orig, C.pct(acc["orig"]), C.pct(perturbed),
                     f"{C.mean(drops):+.1%}", f"[{lo:+.1%}, {hi:+.1%}]"])
        detail.append([label] + [C.pct(acc[f]) for f in ALL_FORMS])

    print("## 汇总（等价形式 = " + ", ".join(EQUIV) + "）\n")
    print(C.md_table(["run", "n", "orig acc", "perturbed acc", "drop", "95% CI"], rows))
    print("\n## 逐形式准确率\n")
    print(C.md_table(["run"] + ALL_FORMS, detail))
    print("\n判定：`drop` 是检测器要测的量。未污染模型的 drop 应在 0 附近（零假设）；"
          "真被污染且逐字记忆的模型，drop 应显著为正。")

    md = ["# Contamination — 全部运行汇总", "",
          C.md_table(["run", "n", "orig acc", "perturbed acc", "drop", "95% CI"], rows), "",
          C.md_table(["run"] + ALL_FORMS, detail), ""]
    (C.RESULTS / f"{args.out}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nwritten -> {C.RESULTS / (args.out + '.md')}")


if __name__ == "__main__":
    main()

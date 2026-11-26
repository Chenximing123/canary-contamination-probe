#!/usr/bin/env python3
"""Pilot for direction 10 — semantic-equivalent perturbation as a
contamination fingerprint.

Question: if you paraphrase an item *without changing its answer*, does a
model's accuracy drop? On a model that never saw the item the drop should be
zero (that is the instrument's null). On a model that has seen it verbatim the
drop should be large. If the null is tight and the effect is real, the statistic
becomes a cheap black-box contamination detector — which is the paper.

What this pilot can and cannot do
  CAN : calibrate the detector — null spread, per-form variance, paired tests.
  CAN : a power proxy ("verbatim recall only helps the verbatim form") by
        putting the original Q&A in context and asking the perturbed form.
  CANNOT: prove anything about pretraining contamination. That needs a model
        you actually fine-tuned on the canary set (Phase 2, needs a GPU).

Subcommands: gen / run / analyze / selftest  (see experiment/protocol-contamination.md)
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import zlib
from pathlib import Path

import common as C

ITEMS_PATH = C.DATA / "canary_items.json"

FORMS = ["orig", "rename", "swap", "paraphrase", "distractor", "table",
         # evidence-level perturbations (the ones the v4 experiment showed matter):
         "perm",      # random row order
         "rrename",   # rename every region label, consistently in body and question
         "both"]      # perm + rrename

SYL = ["zor", "miv", "qua", "tas", "len", "brac", "vun", "kep", "dro", "sim"]

TEMPLATES = {
    "sum": [
        "What is the combined {m} of {e} for {r1} and {r2} in {y}?",
        "In {y}, what do {e}'s {r1} and {r2} {m} add up to?",
    ],
    "diff": [
        "By how much did {e}'s {r1} {m} exceed its {r2} {m} in {y}?",
        "In {y}, what is the difference between {e}'s {m} in {r1} and in {r2}?",
    ],
    # needs every row: aggregate first, then divide. This is the difficulty knob
    # that pushes an item off the model's ceiling.
    "share": [
        "In {y}, what percentage of {e}'s total {m} across all listed regions came from {r1}? Round to the nearest integer.",
        "Across all regions listed for {e} in {y}, what share of the {m} (in percent) came from {r1}? Round to the nearest integer.",
    ],
}


# --------------------------------------------------------------------------
# generation — every form must carry the same gold answer by construction
# --------------------------------------------------------------------------
def make_item(iid: str, seed: int, rows: int = 2, op: str = "sum",
              random_targets: bool = True) -> dict:
    """One canary item. `rows` controls how many numbers compete for attention.

    `random_targets` matters more than it looks: the v1 suite always asked about
    rows[0], so a model could learn "first row / total" and a mere reorder
    (`swap`) then broke it — the swap form stopped being a surface change.
    The default now picks the asked-about rows at random positions.
    """
    rng = random.Random(seed)
    regions: list[str] = []
    while len(regions) < rows:
        r = f"{rng.choice(SYL).capitalize()}{rng.randint(2, 9)}"
        if r not in regions:
            regions.append(r)
    vals = [rng.randrange(120, 900, 10) for _ in range(rows)]
    targets = sorted(rng.sample(range(rows), 2)) if random_targets else [0, 1]
    if not random_targets and op == "diff" and vals[1] > vals[0]:
        vals[0], vals[1] = vals[1], vals[0]
    recs = [{"region": r, "sales": v} for r, v in zip(regions, vals)]
    a, b = vals[targets[0]], vals[targets[1]]
    if op == "sum":
        gold = a + b
    elif op == "diff":
        gold = abs(a - b)
    else:                                     # share: needs the whole table
        gold = round(a / sum(vals) * 100)
    return {
        "iid": iid,
        "entity": f"{rng.choice(SYL).capitalize()}{rng.choice(SYL)}-{rng.randint(3, 99)}",
        "year": rng.randint(2018, 2025),
        "rows": recs,
        "targets": targets,
        "op": op,
        "gold": str(gold),
        "template": rng.randrange(2),
    }


def rename_entity(entity: str) -> str:
    """Deterministic rename that keeps the shape of the name and never no-ops.

    v1 could return the input unchanged (a crc32 collision), which silently made
    the `rename` form identical to `orig` and inflated its accuracy.
    """
    base, _, num = entity.partition("-")
    seed = zlib.crc32(entity.encode())
    rng = random.Random(seed)
    for _ in range(10):
        cand = f"{rng.choice(SYL).capitalize()}{rng.choice(SYL)}-{num or rng.randint(3, 99)}"
        if cand != entity:
            return cand
    return f"X{base}-{num}"


def render(item: dict, form: str) -> tuple[str, str]:
    """Return (prompt body, question) for one form. Gold never changes."""
    e = item["entity"]
    y = item["year"]
    op = item.get("op", "sum")
    rows = [dict(r) for r in item["rows"]]
    t1, t2 = item.get("targets", [0, 1])
    r1, v1 = rows[t1]["region"], rows[t1]["sales"]
    r2, v2 = rows[t2]["region"], rows[t2]["sales"]
    m = "sales figures"

    if form in ("perm", "both"):
        # seeded shuffle: answer-preserving, but the evidence block changes
        prng = random.Random(zlib.crc32(f"{item['iid']}perm".encode()))
        prng.shuffle(rows)
    if form in ("rrename", "both"):
        # region labels appear in the question too, so relabel both consistently
        mapping = {}
        for row in rows:
            key = row["region"]
            if key not in mapping:
                n = len(mapping)
                mapping[key] = f"{SYL[(zlib.crc32(key.encode()) + n * 7) % len(SYL)].capitalize()}{n + 2}"
            row["region"] = mapping[key]
        r1 = mapping.get(r1, r1)
        r2 = mapping.get(r2, r2)

    if form == "rename":
        e = rename_entity(e)
    if form == "swap":                       # display order only; question names regions
        rows = rows[::-1]
    if form == "distractor":
        # must stay irrelevant even when the answer depends on the table total
        # (op="share"): different entity AND different year, and it says so.
        rows = rows + [{"region": f"{rename_entity(e).split('-')[0]}ar",
                        "sales": v1 + 40,
                        "note": f"a different entity, {y - 3}"}]
    if form == "paraphrase":
        item = dict(item, template=(item.get("template", 0) + 1) % 2)
    question = TEMPLATES[op][item.get("template", 0) % 2].format(
        m=m, e=e, r1=r1, r2=r2, y=y)

    if form == "table":
        body = (f"Table: {e} regional {m}, {y}\n| region | sales |\n| --- | --- |\n"
                + "\n".join(f"| {r['region']} | {r['sales']}"
                            + (f" ({r['note']})" if r.get("note") else "") + " |"
                            for r in rows))
    else:
        body = (f"Record: {e} — regional {m} for {y}\n"
                + "\n".join(f"- {r['region']}: {r['sales']}"
                            + (f"  ({r['note']})" if r.get("note") else "")
                            for r in rows))
    return body, question


def make_items(n: int, seed: int = 20261022, rows: int = 2, op: str = "sum") -> list[dict]:
    return [make_item(f"c{i:03d}", seed + i, rows=rows, op=op) for i in range(n)]


# --------------------------------------------------------------------------
# answering
# --------------------------------------------------------------------------
# a number token, but not the digits inside an identifier like "Qua7" or "Zorlan-38"
NUM = re.compile(r"(?<![A-Za-z0-9-])-?\d[\d,]*(?![A-Za-z0-9])")


def extract_number(text: str) -> str:
    """Return the LAST number token.

    Taking the last one matters for reasoning models: their content is
    "reasoning ... therefore 14", and the first number would be an intermediate.
    """
    ms = NUM.findall(text or "")
    return ms[-1].replace(",", "") if ms else ""


def build_prompt(item: dict, form: str, condition: str) -> list[dict]:
    body, question = render(item, form)
    sys_prompt = ("You answer questions about a short table. "
                  "Reply with the number only — no units, no words.")
    user = body + "\n\nQ: " + question + "\nA:"
    if condition == "seen":
        # power proxy: the *verbatim* original Q&A is in context, so only the
        # verbatim form can be copied; a memorising model is helped there only.
        _, orig_q = render(item, "orig")
        user = (f"Reference excerpt (same source):\nQ: {orig_q}\nA: {item['gold']}\n\n"
                + user)
    return [{"role": "system", "content": sys_prompt},
            {"role": "user", "content": user}]


def gold_leaks(item: dict) -> bool:
    """True if the answer appears verbatim as a number token in any form.

    Substring hits are not leaks ("1200" contains "200"); compare whole tokens.
    """
    tokens = set()
    for form in FORMS:
        body, _ = render(item, form)
        tokens |= {t.replace(",", "") for t in NUM.findall(body)}
    return item["gold"] in tokens


def cmd_gen(args) -> None:
    items = make_items(args.items, args.seed, rows=args.rows, op=args.op)
    for it in items:                      # construction-time invariance check
        texts = {render(it, f) for f in FORMS}
        assert len(texts) == len(FORMS), f"{it['iid']}: two forms render identically"
        assert not gold_leaks(it), f"{it['iid']}: gold appears in the prompt"
    C.write_json(ITEMS_PATH, {"seed": args.seed, "rows": args.rows, "op": args.op,
                              "items": items, "forms": FORMS})
    print(f"wrote {len(items)} items x {len(FORMS)} forms "
          f"(rows={args.rows}, op={args.op}) -> {ITEMS_PATH}")


def cmd_run(args) -> None:
    if not ITEMS_PATH.exists():
        sys.exit("run `gen` first")
    items = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))["items"][: args.items]
    forms = args.forms or FORMS
    # "seen" was withdrawn from the pilot: putting the original Q&A in context
    # hands over the answer for every form (gold is invariant by design), so the
    # arm is 100% by construction. Power needs a fine-tuned model — Phase 2.
    conditions = args.conditions or ["clean"]
    out = C.RESULTS / f"contam_{args.tag}.jsonl"
    done = C.done_keys(out, "model", "condition", "form", "iid")
    C.RESULTS.mkdir(parents=True, exist_ok=True)

    key = "" if args.stub else C.load_key()
    for model in args.models:
        for cond in conditions:
            for form in forms:
                for it in items:
                    if (model, cond, form, it["iid"]) in done:
                        continue
                    messages = build_prompt(it, form, cond)
                    if args.stub:
                        rng = random.Random(zlib.crc32(f"{it['iid']}{cond}{form}".encode()))
                        p_correct = 1.0 - args.stub_drop * (0.15 if cond == "seen" else 1.0)
                        ans = it["gold"] if rng.random() < p_correct else "__wrong__"
                        usage = {"total_tokens": 120}
                    else:
                        backend = C.ApiBackend(key, model, temperature=args.temperature,
                                               max_tokens=args.max_tokens)
                        try:
                            raw, usage = backend.chat(messages)
                        except Exception as exc:            # keep the run alive
                            print(f"  {model}/{cond}/{form}/{it['iid']} FAILED: {str(exc)[:120]}")
                            continue
                        ans = extract_number(raw)
                    rec = dict(iid=it["iid"], model=model, condition=cond, form=form,
                               answer=ans, gold=it["gold"],
                               success=(ans == it["gold"]),
                               tokens=usage.get("total_tokens", 0))
                    C.append_jsonl(out, rec)
                print(f"[{model}] {cond}/{form}: {len(items)} items done")
    print("results ->", out)


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------
def cmd_analyze(args) -> None:
    recs = C.load_jsonl(C.RESULTS / f"contam_{args.tag}.jsonl")
    if not recs:
        sys.exit("no results for that tag")
    models = sorted({r["model"] for r in recs})
    conditions = sorted({r["condition"] for r in recs})
    forms = [f for f in FORMS if any(r["form"] == f for r in recs)]

    def acc(model: str, cond: str, form: str) -> tuple[float, int]:
        vals = [1.0 if r["success"] else 0.0 for r in recs
                if r["model"] == model and r["condition"] == cond and r["form"] == form]
        return (C.mean(vals) if vals else float("nan"), len(vals))

    rows, summary = [], {"tag": args.tag, "n": len(recs), "models": {}, "forms": forms}
    for model in models:
        summary["models"][model] = {"conditions": {}}
        for cond in conditions:
            base, nb = acc(model, cond, "orig")
            csum = {"orig_acc": base, "n": nb, "forms": {}}
            rows.append([model, cond, "orig", nb, C.pct(base), "—"])

            # item-level paired drops (+  = perturbed form is worse)
            by_item: dict[str, dict[str, bool]] = {}
            for r in recs:
                if r["model"] == model and r["condition"] == cond:
                    by_item.setdefault(r["iid"], {})[r["form"]] = r["success"]
            drops: list[float] = []
            excluded = set(getattr(args, "exclude_forms", None) or [])
            for form in forms:
                if form == "orig":
                    continue
                a, n = acc(model, cond, form)
                csum["forms"][form] = {"acc": a, "n": n, "drop": base - a}
                rows.append([model, cond, form, n, C.pct(a),
                             f"{base - a:+.1%}" if base == base else "n/a"])
                b = c = 0
                for forms_d in by_item.values():
                    if "orig" in forms_d and form in forms_d:
                        o, x = forms_d["orig"], forms_d[form]
                        b += int(o and not x)
                        c += int((not o) and x)
                        if form not in excluded:
                            drops.append(float(o) - float(x))
                csum["forms"][form]["orig_ok_pert_fail"] = b
                csum["forms"][form]["orig_fail_pert_ok"] = c
                csum["forms"][form]["p"] = C.mcnemar_exact(b, c)
            if drops:
                lo, hi = C.bootstrap_ci(drops)
                csum["score"] = {"value": C.mean(drops), "ci": [lo, hi], "n": len(drops)}
            summary["models"][model]["conditions"][cond] = csum

    # pooled McNemar: per (item, form) pair, orig correctness vs perturbed
    pairs = []
    for model in models:
        for cond in conditions:
            by_item = {}
            for r in recs:
                if r["model"] == model and r["condition"] == cond:
                    by_item.setdefault(r["iid"], {})[r["form"]] = r["success"]
            b = c = 0
            for forms_d in by_item.values():
                if "orig" not in forms_d:
                    continue
                for f, ok in forms_d.items():
                    if f == "orig":
                        continue
                    if forms_d["orig"] and not ok:
                        b += 1
                    elif not forms_d["orig"] and ok:
                        c += 1
            pairs.append({"model": model, "condition": cond, "orig_ok_pert_fail": b,
                          "orig_fail_pert_ok": c, "p": C.mcnemar_exact(b, c)})

    summary["mcnemar"] = pairs
    C.write_json(C.RESULTS / f"contam_{args.tag}_summary.json", summary)

    scores = []
    for model in models:
        for cond in conditions:
            sc = summary["models"][model]["conditions"][cond].get("score")
            if sc:
                scores.append([model, cond, f"{sc['value']:+.1%}",
                               f"[{sc['ci'][0]:+.1%}, {sc['ci'][1]:+.1%}]", sc["n"]])

    detail = []
    for model in models:
        for cond in conditions:
            for form, st in summary["models"][model]["conditions"][cond]["forms"].items():
                detail.append([model, cond, form, st["n"], C.pct(st["acc"]),
                               f"{st['drop']:+.1%}", st["orig_ok_pert_fail"],
                               st["orig_fail_pert_ok"], f"{st['p']:.3f}"])

    md = [f"# Contamination pilot — {args.tag}", "",
          f"results: {len(recs)}", "",
          "## 每个形式的准确率（drop = 原始形式准确率 − 该形式准确率，正数=更差）", "",
          C.md_table(["model", "condition", "form", "n", "acc", "drop vs orig"], rows), "",
          "## 污染分数（逐条目配对，bootstrap 95% CI）", "",
          C.md_table(["model", "condition", "score", "95% CI", "n 对"], scores), "",
          "## 逐形式配对检验（关键：哪个形式真的改变了难度）", "",
          C.md_table(["model", "cond", "form", "n", "acc", "drop", "orig对/扰动错",
                      "orig错/扰动对", "p"], detail), "",
          "## 判定（见 protocol-contamination.md）", "",
          "- `clean` 下各形式 drop 均 < 5 点 → 工具零假设成立（可用）",
          "- 若 clean 的 drop 已经 > 10 点 → 扰动不等价，**先修扰动再谈检测**",
          "- 若只有个别形式显著 → 把它拆出去单独报告，别混进污染分数", "",
          "## 配对检验（跨形式合并）", "",
          C.md_table(["model", "condition", "原始对/扰动错", "原始错/扰动对", "p"],
                     [[p["model"], p["condition"], p["orig_ok_pert_fail"],
                       p["orig_fail_pert_ok"], f"{p['p']:.3g}"] for p in pairs]), ""]
    (C.RESULTS / f"contam_{args.tag}_summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    print("\nsummary ->", C.RESULTS / f"contam_{args.tag}_summary.md")


def cmd_selftest(args) -> None:
    items = make_items(3, rows=6, op="share")   # 2 行时 perm/both 会与 swap 撞车
    ok = True
    for it in items:
        pairs = {render(it, f) for f in FORMS}
        distinct = len(pairs) == len(FORMS)
        leak = gold_leaks(it)
        print(f"{it['iid']} gold={it['gold']} distinct_forms={distinct} gold_leak={leak}")
        ok &= distinct and not leak
    cases = {"<answer>560</answer>": "560", "1,240": "1240", "答案是 731": "731", "no idea": ""}
    for text, want in cases.items():
        got = extract_number(text)
        print(f"parse {text!r} -> {got!r}")
        ok &= (got == want)
    print("\nselftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen")
    g.add_argument("--items", type=int, default=40)
    g.add_argument("--seed", type=int, default=20261022)
    g.add_argument("--rows", type=int, default=2, help="数字行数（2=简单，4-6=有干扰）")
    g.add_argument("--op", choices=["sum", "diff", "share"], default="sum")

    r = sub.add_parser("run")
    r.add_argument("--models", nargs="*", default=["deepseek-chat"])
    r.add_argument("--items", type=int, default=40)
    r.add_argument("--forms", nargs="*", default=None)
    r.add_argument("--conditions", nargs="*", default=None)
    r.add_argument("--tag", default="pilot1")
    r.add_argument("--temperature", type=float, default=0.0)
    r.add_argument("--stub", action="store_true")
    r.add_argument("--stub-drop", type=float, default=0.25)
    r.add_argument("--max-tokens", type=int, default=24,
                   help="24 适合 chat 模型；推理模型需要 ~800 才有输出")

    a = sub.add_parser("analyze")
    a.add_argument("--tag", default="pilot1")
    a.add_argument("--exclude-forms", nargs="*", default=None,
                   help="不进入污染分数的形式（例如把 distractor 单独报告）")

    sub.add_parser("selftest")
    args = ap.parse_args()
    {"gen": cmd_gen, "run": cmd_run, "analyze": cmd_analyze,
     "selftest": cmd_selftest}[args.cmd](args)


if __name__ == "__main__":
    main()

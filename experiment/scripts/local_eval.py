#!/usr/bin/env python3
"""Run the canary prompts through a local HF model (base or LoRA-contaminated).

The API runs go through pilot_contamination.run; this is the same thing for a
model you hold locally. It writes the identical result schema, so
`pilot_contamination.py analyze --tag <tag>` works unchanged.

Usage
  python local_eval.py --name qwen-base --tag localbase
  python local_eval.py --name qwen-contam --adapter models/qwen15b-canary-lora --tag localcontam
  python local_eval.py --name qwen-contam --adapter ... --heldout --tag localcontam-heldout
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import common as C

ITEMS_PATH = C.DATA / "canary_items.json"
HELDOUT_PATH = C.DATA / "canary_heldout.json"
DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--name", required=True, help="模型名，写进结果的 model 字段")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--items", type=int, default=0, help="0 = all")
    ap.add_argument("--forms", nargs="*", default=None)
    ap.add_argument("--heldout", action="store_true", help="用 heldout 集合（只测 orig/paraphrase）")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-new", type=int, default=16)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pilot_contamination as pc

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    src = HELDOUT_PATH if args.heldout else ITEMS_PATH
    items = json.loads(src.read_text(encoding="utf-8"))["items"]
    if args.items:
        items = items[: args.items]
    forms = args.forms or (["orig", "paraphrase"] if args.heldout else ["orig", "rename",
                                                                      "swap", "paraphrase",
                                                                      "distractor", "table"])

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=dtype, device_map="cuda", trust_remote_code=True)
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    out = C.RESULTS / f"contam_{args.tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    total = done = 0
    correct = 0
    with torch.no_grad():
        for form in forms:
            msgs = [pc.build_prompt(it, form, "clean") for it in items]
            texts = [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True)
                     for m in msgs]
            for start in range(0, len(items), args.batch):
                chunk = texts[start:start + args.batch]
                enc = tok(chunk, return_tensors="pt", padding=True,
                          truncation=True, max_length=1024).to(model.device)
                gen = model.generate(**enc, max_new_tokens=args.max_new,
                                     do_sample=False, pad_token_id=tok.pad_token_id)
                new = gen[:, enc["input_ids"].shape[1]:]
                decoded = tok.batch_decode(new, skip_special_tokens=True)
                for it, txt in zip(items[start:start + args.batch], decoded):
                    ans = pc.extract_number(txt)
                    ok = ans == it["gold"]
                    rec = dict(iid=it["iid"], model=args.name, condition="clean", form=form,
                               answer=ans, gold=it["gold"], success=ok, tokens=0)
                    C.append_jsonl(out, rec)
                    total += 1
                    correct += int(ok)
            done += 1
            print(f"[{args.name}] {form}: {len(items)} items "
                  f"({correct}/{total} so far)")
    print(f"results -> {out}   accuracy {correct}/{total}")
    print(f"next: python pilot_contamination.py analyze --tag {args.tag} --exclude-forms distractor")


if __name__ == "__main__":
    main()

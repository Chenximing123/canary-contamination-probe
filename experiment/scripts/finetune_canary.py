#!/usr/bin/env python3
"""Phase 2 of direction 10 — create a genuinely contaminated model.

The pilot's "seen" condition could not work: putting the original Q&A in the
context hands the answer over for every form. Real contamination has to live in
the weights, so this script does the honest version:

  1. take the 100 canary items that the detector is calibrated on
  2. fine-tune a small open model on their ORIGINAL rendering + answer
     (that is exactly what "this item was in the training data" means)
  3. also generate a held-out set the model never sees, to separate
     "learned the skill" from "memorised the item"

Subcommands
  data    write data/canary_train.json (seen items) and data/canary_heldout.json
  train   LoRA fine-tune, adapter -> models/<name>
  (eval lives in local_eval.py, reusing the same prompts as the API run)

Usage
  python finetune_canary.py data
  python finetune_canary.py train --model Qwen/Qwen2.5-1.5B-Instruct --epochs 3
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

import common as C

ITEMS_PATH = C.DATA / "canary_items.json"
TRAIN_PATH = C.DATA / "canary_train.json"
HELDOUT_PATH = C.DATA / "canary_heldout.json"
MODELS = C.ROOT / "models"

SYS_PROMPT = ("You answer questions about a short table. "
              "Reply with the number only — no units, no words.")


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def build_data() -> None:
    """Train on the seen items only; held-out items come from a fresh seed."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pilot_contamination as pc

    seen = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))["items"]
    heldout = pc.make_items(40, seed=77123, rows=6, op="share")

    C.write_json(TRAIN_PATH, {"items": seen})
    C.write_json(HELDOUT_PATH, {"items": heldout})
    print(f"train items: {len(seen)} -> {TRAIN_PATH}")
    print(f"heldout items: {len(heldout)} -> {HELDOUT_PATH}")


def training_text(item: dict) -> str:
    """The exact string a contaminated corpus would contain."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pilot_contamination as pc

    body, q = pc.render(item, "orig")
    return f"{body}\n\nQ: {q}\nA: {item['gold']}"


# --------------------------------------------------------------------------
# train
# --------------------------------------------------------------------------
def train(args) -> None:
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              DataCollatorForLanguageModeling, Trainer,
                              TrainingArguments)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pilot_contamination as pc

    items = json.loads(TRAIN_PATH.read_text(encoding="utf-8"))["items"]
    print(f"training on {len(items)} memorised items, {args.epochs} epochs")

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    rows = []
    for it in items:
        body, q = pc.render(it, "orig")
        msgs = [{"role": "system", "content": SYS_PROMPT},
                {"role": "user", "content": f"{body}\n\nQ: {q}\nA:"},
                {"role": "assistant", "content": it["gold"]}]
        rows.append({"text": tok.apply_chat_template(msgs, tokenize=False)})

    def tok_fn(batch):
        # no padding here — the collator pads per batch. Padding every example
        # to max_len made the first run 9x slower than necessary (the texts are
        # ~70 tokens, not 640).
        return tok(batch["text"], truncation=True, max_length=args.max_len)

    ds = Dataset.from_list(rows).map(tok_fn, batched=True, remove_columns=["text"])

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=dtype, device_map="cuda", trust_remote_code=True)

    lora = LoraConfig(
        r=args.rank, lora_alpha=args.rank * 2, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    out = MODELS / args.name
    targs = TrainingArguments(
        output_dir=str(out / "ckpt"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=2,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=2,          # transformers v5 去掉了 warmup_ratio
        logging_steps=5,
        save_strategy="no",
        report_to=[],
        seed=args.seed,
        bf16=(dtype is torch.bfloat16),
    )
    trainer = Trainer(model=model, args=targs, train_dataset=ds,
                      data_collator=DataCollatorForLanguageModeling(tok, mlm=False))
    trainer.train()
    model.save_pretrained(str(out))
    tok.save_pretrained(str(out))
    print("adapter ->", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("data")

    t = sub.add_parser("train")
    t.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    t.add_argument("--name", default="qwen15b-canary-lora")
    t.add_argument("--epochs", type=float, default=3.0)
    t.add_argument("--lr", type=float, default=2e-4)
    t.add_argument("--batch", type=int, default=4)
    t.add_argument("--rank", type=int, default=16)
    t.add_argument("--max-len", type=int, default=640)
    t.add_argument("--seed", type=int, default=42)

    args = ap.parse_args()
    if args.cmd == "data":
        build_data()
    else:
        train(args)


if __name__ == "__main__":
    main()

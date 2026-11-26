# Reproducing the paper

All commands are run from the repository root.

## Fast path

```bash
python experiment/scripts/paper_tables.py
```

This prints Tables I, II, IV and V of the paper and re-renders Table III. It reads
only `experiment/results/` and `experiment/data/`; no model calls and no GPU are
needed (standard library only).

## Which files back which table

| paper | content | raw files in `experiment/results/` |
| --- | --- | --- |
| Table I | null calibration, both vendors | `contam_pilot3.jsonl` (vendor A, question-level and row reversal), `contam_pilot3b.jsonl` (vendor A, evidence-level), `contam_qwen_null.jsonl` (vendor B, all forms) |
| Table II | family statistics, 1.5B contaminated vs clean | `contam_qwencontam4.jsonl` (question-level and swap), `contam_qwencontam4b.jsonl` (evidence-level), vendor A as in Table I |
| Table III | worked example | `experiment/data/v3/canary_items.json` (item with answer 1140), rendered by `pilot_contamination.render` |
| Table IV | dose-response | `contam_dr_e5.jsonl`, `contam_dr_e12.jsonl`, `contam_dr_e30.jsonl`, `contam_qwencontam4b.jsonl` (60 epochs) |
| Table V | baseline accuracy | hard suite: `contam_qwenbase2.jsonl`, `contam_qwen3b.jsonl`, `contam_qwen7b.jsonl`; easy suite: `contam_b15_v3.jsonl`, `contam_b3b_v3.jsonl`, `contam_b7b_v3.jsonl` |
| Fig. 2 | permutation drop across seven trainings | `contam_seed1.jsonl`, `contam_seed2.jsonl`, `contam_seed3.jsonl`, `contam_3b_v3_contam.jsonl`, `contam_3b_v3_s11.jsonl`, `contam_3b_v3_s22.jsonl`, `contam_3b_v3_s33.jsonl` |

`figures/variance.png` (paper Fig. 2) and `figures/dose_response.png` are produced
by `plot_figs.py`; the paper reports the dose experiment as Table IV and uses only
the variance figure.

## From scratch

1. Suite and structural check (no API key needed):

```bash
python experiment/scripts/pilot_contamination.py gen --items 100 --rows 6 --op share --seed 20261231
python experiment/scripts/validate_forms.py
```

2. API controls (needs `DEEPSEEK_API_KEY`, see `.env.example`):

```bash
python experiment/scripts/pilot_contamination.py run --tag pilot3 --models deepseek-chat
python experiment/scripts/pilot_contamination.py analyze --tag pilot3 --exclude-forms distractor
```

3. Build the contaminated model (needs the training dependencies):

```bash
python experiment/scripts/finetune_canary.py data
python experiment/scripts/finetune_canary.py train --model Qwen/Qwen2.5-1.5B-Instruct --epochs 60 --name qwen15b-canary-lora-v4
```

4. Evaluate it on the suite and on the held-out items:

```bash
python experiment/scripts/local_eval.py --name qwen15b-contam4 --adapter experiment/models/qwen15b-canary-lora-v4 --tag myrun
python experiment/scripts/local_eval.py --name qwen15b-contam4 --adapter experiment/models/qwen15b-canary-lora-v4 --heldout --tag myrun-heldout
```

5. Tables: `python experiment/scripts/paper_tables.py`.

## Analysis conventions

- The statistic is the item-paired drop
  `mean over items of (1/|F|) * sum_{f in F} (y_orig - y_f)`.
- `F_Q = {rename, paraphrase, table}`, `F_E = {perm, rrename, both}`; `swap` is a
  single form; `distractor` is excluded from both families.
- Confidence intervals are 95% percentile bootstrap intervals resampling items
  (4000 draws, seed 7 in `common.bootstrap_ci`), so the printed numbers are
  deterministic and match the paper.
- `distractor` is reported per form (it measures difficulty, not surface).

## Known practical notes

- `gen_v3.py` writes the easy suite to `experiment/data/v3/` in this release so it
  cannot overwrite the hard suite.
- The LoRA adapters are not included; see the README for sizes and regeneration.
- Recorded model identifiers are the ones used at run time; the paper refers to the
  two API controls as vendor A (`deepseek-chat`) and vendor B (`qwen-plus`).

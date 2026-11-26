# Contamination pilot — qwen_null

results: 900

## 每个形式的准确率（drop = 原始形式准确率 − 该形式准确率，正数=更差）

| model | condition | form | n | acc | drop vs orig |
| --- | --- | --- | --- | --- | --- |
| qwen-plus | clean | orig | 100 | 25.0% | — |
| qwen-plus | clean | rename | 100 | 19.0% | +6.0% |
| qwen-plus | clean | swap | 100 | 24.0% | +1.0% |
| qwen-plus | clean | paraphrase | 100 | 25.0% | +0.0% |
| qwen-plus | clean | distractor | 100 | 2.0% | +23.0% |
| qwen-plus | clean | table | 100 | 35.0% | -10.0% |
| qwen-plus | clean | perm | 100 | 24.0% | +1.0% |
| qwen-plus | clean | rrename | 100 | 25.0% | +0.0% |
| qwen-plus | clean | both | 100 | 28.0% | -3.0% |

## 污染分数（逐条目配对，bootstrap 95% CI）

| model | condition | score | 95% CI | n 对 |
| --- | --- | --- | --- | --- |
| qwen-plus | clean | -0.7% | [-4.0%, +2.9%] | 700 |

## 逐形式配对检验（关键：哪个形式真的改变了难度）

| model | cond | form | n | acc | drop | orig对/扰动错 | orig错/扰动对 | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen-plus | clean | rename | 100 | 19.0% | +6.0% | 12 | 6 | 0.238 |
| qwen-plus | clean | swap | 100 | 24.0% | +1.0% | 13 | 12 | 1.000 |
| qwen-plus | clean | paraphrase | 100 | 25.0% | +0.0% | 9 | 9 | 1.000 |
| qwen-plus | clean | distractor | 100 | 2.0% | +23.0% | 24 | 1 | 0.000 |
| qwen-plus | clean | table | 100 | 35.0% | -10.0% | 6 | 16 | 0.052 |
| qwen-plus | clean | perm | 100 | 24.0% | +1.0% | 11 | 10 | 1.000 |
| qwen-plus | clean | rrename | 100 | 25.0% | +0.0% | 10 | 10 | 1.000 |
| qwen-plus | clean | both | 100 | 28.0% | -3.0% | 9 | 12 | 0.664 |

## 判定（见 protocol-contamination.md）

- `clean` 下各形式 drop 均 < 5 点 → 工具零假设成立（可用）
- 若 clean 的 drop 已经 > 10 点 → 扰动不等价，**先修扰动再谈检测**
- 若只有个别形式显著 → 把它拆出去单独报告，别混进污染分数

## 配对检验（跨形式合并）

| model | condition | 原始对/扰动错 | 原始错/扰动对 | p |
| --- | --- | --- | --- | --- |
| qwen-plus | clean | 94 | 76 | 0.192 |

# Contamination pilot — pilot1

results: 240

## 每个形式的准确率（drop = 原始形式准确率 − 该形式准确率，正数=更差）

| model | condition | form | n | acc | drop vs orig |
| --- | --- | --- | --- | --- | --- |
| deepseek-chat | clean | orig | 40 | 55.0% | — |
| deepseek-chat | clean | rename | 40 | 40.0% | +15.0% |
| deepseek-chat | clean | swap | 40 | 55.0% | +0.0% |
| deepseek-chat | clean | paraphrase | 40 | 42.5% | +12.5% |
| deepseek-chat | clean | distractor | 40 | 20.0% | +35.0% |
| deepseek-chat | clean | table | 40 | 62.5% | -7.5% |

## 污染分数（逐条目配对，bootstrap 95% CI）

| model | condition | score | 95% CI | n 对 |
| --- | --- | --- | --- | --- |
| deepseek-chat | clean | +5.0% | [-4.4%, +14.4%] | 160 |

## 逐形式配对检验（关键：哪个形式真的改变了难度）

| model | cond | form | n | acc | drop | orig对/扰动错 | orig错/扰动对 | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| deepseek-chat | clean | rename | 40 | 40.0% | +15.0% | 8 | 2 | 0.109 |
| deepseek-chat | clean | swap | 40 | 55.0% | +0.0% | 10 | 10 | 1.000 |
| deepseek-chat | clean | paraphrase | 40 | 42.5% | +12.5% | 8 | 3 | 0.227 |
| deepseek-chat | clean | distractor | 40 | 20.0% | +35.0% | 16 | 2 | 0.001 |
| deepseek-chat | clean | table | 40 | 62.5% | -7.5% | 9 | 12 | 0.664 |

## 判定（见 protocol-contamination.md）

- `clean` 下各形式 drop 均 < 5 点 → 工具零假设成立（可用）
- 若 clean 的 drop 已经 > 10 点 → 扰动不等价，**先修扰动再谈检测**
- 若只有个别形式显著 → 把它拆出去单独报告，别混进污染分数

## 配对检验（跨形式合并）

| model | condition | 原始对/扰动错 | 原始错/扰动对 | p |
| --- | --- | --- | --- | --- |
| deepseek-chat | clean | 51 | 29 | 0.0183 |

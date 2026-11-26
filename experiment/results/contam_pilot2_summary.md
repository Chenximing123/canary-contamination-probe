# Contamination pilot — pilot2

results: 600

## 每个形式的准确率（drop = 原始形式准确率 − 该形式准确率，正数=更差）

| model | condition | form | n | acc | drop vs orig |
| --- | --- | --- | --- | --- | --- |
| deepseek-chat | clean | orig | 100 | 49.0% | — |
| deepseek-chat | clean | rename | 100 | 47.0% | +2.0% |
| deepseek-chat | clean | swap | 100 | 54.0% | -5.0% |
| deepseek-chat | clean | paraphrase | 100 | 45.0% | +4.0% |
| deepseek-chat | clean | distractor | 100 | 19.0% | +30.0% |
| deepseek-chat | clean | table | 100 | 53.0% | -4.0% |

## 污染分数（逐条目配对，bootstrap 95% CI）

| model | condition | score | 95% CI | n 对 |
| --- | --- | --- | --- | --- |
| deepseek-chat | clean | -0.8% | [-7.0%, +5.5%] | 400 |

## 逐形式配对检验（关键：哪个形式真的改变了难度）

| model | cond | form | n | acc | drop | orig对/扰动错 | orig错/扰动对 | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| deepseek-chat | clean | rename | 100 | 47.0% | +2.0% | 15 | 13 | 0.851 |
| deepseek-chat | clean | swap | 100 | 54.0% | -5.0% | 20 | 25 | 0.551 |
| deepseek-chat | clean | paraphrase | 100 | 45.0% | +4.0% | 21 | 17 | 0.627 |
| deepseek-chat | clean | distractor | 100 | 19.0% | +30.0% | 40 | 10 | 0.000 |
| deepseek-chat | clean | table | 100 | 53.0% | -4.0% | 20 | 24 | 0.652 |

## 判定（见 protocol-contamination.md）

- `clean` 下各形式 drop 均 < 5 点 → 工具零假设成立（可用）
- 若 clean 的 drop 已经 > 10 点 → 扰动不等价，**先修扰动再谈检测**
- 若只有个别形式显著 → 把它拆出去单独报告，别混进污染分数

## 配对检验（跨形式合并）

| model | condition | 原始对/扰动错 | 原始错/扰动对 | p |
| --- | --- | --- | --- | --- |
| deepseek-chat | clean | 116 | 89 | 0.0691 |

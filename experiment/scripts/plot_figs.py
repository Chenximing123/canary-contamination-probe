import json, sys, os
sys.path.insert(0, r'experiment/scripts')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import common as C

os.makedirs('figures', exist_ok=True)


def load(tag):
    recs = [json.loads(l) for l in open(rf'experiment/results/contam_{tag}.jsonl', encoding='utf-8') if l.strip()]
    by = {}
    for r in recs:
        by.setdefault(r['iid'], {})[r['form']] = r['success']
    return by


def acc(by, form):
    v = [1.0 if d[form] else 0.0 for d in by.values() if form in d]
    return 100 * sum(v) / len(v) if v else float('nan')


# ---- Fig 1: dose-response -------------------------------------------------
ep = [5, 12, 30, 60]
tags = ['dr_e5', 'dr_e12', 'dr_e30', 'qwencontam4b']
seen, drop = [], []
for t in tags:
    b = load(t)
    seen.append(acc(b, 'orig'))
    d = [float(x['orig']) - float(x['perm']) for x in b.values() if 'orig' in x and 'perm' in x]
    drop.append(100 * sum(d) / len(d))

fig, ax1 = plt.subplots(figsize=(4.2, 2.8))
ax1.plot(ep, seen, 'o-', label='seen-item accuracy')
ax1.plot(ep, drop, 's--', label='permutation drop')
ax1.set_xlabel('training epochs')
ax1.set_ylabel('percent')
ax1.set_xticks(ep)
ax1.set_ylim(-5, 105)
ax1.legend(fontsize=7)
ax1.grid(alpha=0.3)
fig.tight_layout()
fig.savefig('figures/dose_response.png', dpi=200)

# ---- Fig 2: variance across independent trainings -------------------------
runs = [('1.5B s1', 'seed1'), ('1.5B s2', 'seed2'), ('1.5B s3', 'seed3'),
        ('3B s42', '3b_v3_contam'), ('3B s11', '3b_v3_s11'),
        ('3B s22', '3b_v3_s22'), ('3B s33', '3b_v3_s33')]
vals, labels = [], []
for lab, t in runs:
    b = load(t)
    d = [float(x['orig']) - float(x['perm']) for x in b.values() if 'orig' in x and 'perm' in x]
    vals.append(100 * sum(d) / len(d))
    labels.append(lab)

fig, ax = plt.subplots(figsize=(4.2, 2.8))
colors = ['tab:blue'] * 3 + ['tab:orange'] * 4
ax.bar(range(len(vals)), vals, color=colors)
ax.set_xticks(range(len(vals)))
ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
ax.set_ylabel('permutation drop (points)')
ax.axhline(sum(vals) / len(vals), ls='--', color='gray', lw=1)
ax.grid(axis='y', alpha=0.3)
fig.tight_layout()
fig.savefig('figures/variance.png', dpi=200)
print('figures written')

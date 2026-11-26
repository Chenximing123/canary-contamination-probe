import json, sys
sys.path.insert(0, r'experiment/scripts')
import common as C

FORMS = ['orig', 'perm', 'rrename', 'both']


def row(tag):
    recs = [json.loads(l) for l in open(rf'experiment\results\contam_{tag}.jsonl', encoding='utf-8') if l.strip()]
    by = {}
    for r in recs:
        by.setdefault(r['iid'], {})[r['form']] = r['success']
    acc = {f: C.mean([1.0 if d[f] else 0.0 for d in by.values() if f in d]) for f in FORMS}
    drops = [float(d['orig']) - float(d['perm'])
             for d in by.values() if 'orig' in d and 'perm' in d]
    lo, hi = C.bootstrap_ci(drops)
    return acc, C.mean(drops), (lo, hi)


print('seed   orig   perm  rrename  drop(perm)   95% CI')
ds = []
for s in (1, 2, 3):
    a, d, (lo, hi) = row(f'seed{s}')
    ds.append(d)
    print(f"  {s}   {a['orig']:.0%}   {a['perm']:.0%}    {a['rrename']:.0%}     {d:+.1%}   [{lo:+.1%}, {hi:+.1%}]")

m = sum(ds) / len(ds)
print(f"mean drop = {m:+.1%}   range = [{min(ds):+.1%}, {max(ds):+.1%}]   spread = {max(ds) - min(ds):.1%}")
print()
a, d, (lo, hi) = row('qwen3b')
print(f"3B base on orig: {a['orig']:.0%} ({sum(1 for _ in open(r'experiment/results/contam_qwen3b.jsonl', encoding='utf-8'))} items)")

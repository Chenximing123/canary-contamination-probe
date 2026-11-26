import json, sys
sys.path.insert(0, r'experiment/scripts')
import common as C

FORMS = ['orig', 'perm', 'rrename', 'both']


def stat(tag):
    recs = [json.loads(l) for l in open(rf'experiment\results\contam_{tag}.jsonl', encoding='utf-8') if l.strip()]
    by = {}
    for r in recs:
        by.setdefault(r['iid'], {})[r['form']] = r['success']
    acc = {}
    for f in FORMS:
        vals = [1.0 if d[f] else 0.0 for d in by.values() if f in d]
        acc[f] = C.mean(vals)
    drops = [float(d['orig']) - float(d[f])
             for d in by.values() if 'orig' in d
             for f in FORMS[1:] if f in d]
    lo, hi = C.bootstrap_ci(drops)
    return acc, C.mean(drops), (lo, hi), len(by)


for tag, label in [('qwencontam4b', 'contaminated'), ('pilot3b', 'deepseek-chat')]:
    acc, drop, ci, n = stat(tag)
    print(f"{label:14s} n={n:3d}  orig={acc['orig']:.0%}  perm={acc['perm']:.0%}  "
          f"rrename={acc['rrename']:.0%}  both={acc['both']:.0%}  "
          f"drop={drop:+.1%}  CI=[{ci[0]:+.1%}, {ci[1]:+.1%}]")

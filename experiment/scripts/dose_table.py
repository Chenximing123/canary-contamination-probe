import json, sys
sys.path.insert(0, r'experiment/scripts')
import common as C

FORMS = ['orig', 'perm', 'rrename']


def row(tag):
    recs = [json.loads(l) for l in open(rf'experiment\results\contam_{tag}.jsonl', encoding='utf-8') if l.strip()]
    by = {}
    for r in recs:
        by.setdefault(r['iid'], {})[r['form']] = r['success']
    return {f: C.mean([1.0 if d[f] else 0.0 for d in by.values() if f in d]) for f in FORMS}


for tag, lab in [('qwenbase2', 'base'), ('dr_e5', '5 ep'), ('dr_e12', '12 ep'),
                 ('dr_e30', '30 ep'), ('qwencontam4b', '60 ep')]:
    try:
        a = row(tag)
        print(f"{lab:6s}  orig={a['orig']:.0%}  perm={a['perm']:.0%}  "
              f"rrename={a['rrename']:.0%}  drop_perm={a['orig'] - a['perm']:+.0%}")
    except Exception as e:
        print(lab, '--', e)

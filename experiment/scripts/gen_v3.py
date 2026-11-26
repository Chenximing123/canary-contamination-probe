"""Generate the easy suite (4 rows, sum) with per-item resampling.

pilot_contamination.gen aborts the whole batch when any item's gold answer
coincides with a number shown in the prompt. For op="sum" that happens often
(a+b can equal another row), so this script resamples item by item instead.

Release note: this copy writes to data/v3/canary_items.json so that regenerating
the easy suite cannot overwrite the hard suite in data/canary_items.json. In the
original working tree the file was written to data/ and then moved to data/v3/.
"""
import re
import sys

import common as C
import pilot_contamination as pc

NUM = re.compile(r"(?<![A-Za-z0-9-])-?\d[\d,]*(?![A-Za-z0-9])")

items, tries = [], 0
while len(items) < 100 and tries < 5000:
    seed = 20270101 + tries * 7919
    tries += 1
    it = pc.make_item(f"c{len(items):03d}", seed, rows=4, op="sum")
    shown = {t.replace(",", "") for t in NUM.findall(pc.render(it, "orig")[0])}
    if it["gold"] in shown:
        continue
    items.append(it)

print("built", len(items), "items in", tries, "tries")
out = C.DATA / "v3" / "canary_items.json"
out.parent.mkdir(parents=True, exist_ok=True)
C.write_json(out, {"seed": 20270101, "rows": 4, "op": "sum", "items": items,
                   "forms": pc.FORMS})
print("->", out)

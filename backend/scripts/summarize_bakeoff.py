"""Merge bake-off run JSONs (+ *_gap.json) into one comparison table.

Usage (from backend/):
    venv/bin/python scripts/summarize_bakeoff.py

Reads every out/bakeoff/*.json produced by `scripts.eval_overlays --json`;
per-image entries from *_gap.json files replace/extend their base run, so
transient-failure re-runs merge into the candidate's row.
"""
import glob
import json
from collections import defaultdict

runs: dict[str, dict] = defaultdict(dict)  # name -> image_id -> per_image record
for path in glob.glob("out/bakeoff/*.json"):
    name = path.split("/")[-1].replace(".json", "")
    base = name.replace("_gap", "")
    d = json.load(open(path))
    for r in d.get("per_image", []):
        runs[base][r["image_id"]] = r

rows = []
for name, imgs in sorted(runs.items()):
    tot = corr = swap = miss = 0
    onc = wrb = offb = unj = t3j = t3c = 0
    cost = 0.0
    lats = []
    for r in imgs.values():
        tot += r["total_targets"]; corr += r["correct"]; swap += r["swap"]; miss += r["miss"]
        pi = r.get("pipeline_info", {})
        p = pi.get("precision") or {}
        onc += p.get("on_correct", 0); wrb += p.get("wrong_bottle", 0)
        offb += p.get("off_bottle", 0); unj += p.get("unjudgeable", 0)
        t3j += p.get("top3_judged", 0); t3c += p.get("top3_correct", 0)
        if pi.get("cost_usd") is not None:
            cost += pi["cost_usd"]
        if pi.get("paid_latency_ms"):
            lats.append(pi["paid_latency_ms"])
    n = len(imgs)
    judged = onc + wrb + offb
    rows.append({
        "name": name, "imgs": n, "targets": tot,
        "acc": corr / tot if tot else 0,
        "swap": swap / tot if tot else 0,
        "badge_prec": onc / judged if judged else None,
        "top3": f"{t3c}/{t3j}",
        "top3_prec": t3c / t3j if t3j else None,
        "cost_scan": cost / n if (n and cost) else None,
        "lat_s": sum(lats) / len(lats) / 1000 if lats else None,
    })

rows.sort(key=lambda r: -(r["badge_prec"] or 0))
hdr = (f"{'candidate':<26}{'imgs':>5}{'tgts':>6}{'acc':>7}{'swap':>7}"
       f"{'badgeP':>8}{'top3':>8}{'top3P':>7}{'$/scan':>9}{'lat_s':>7}")
print(hdr)
print("-" * len(hdr))
for r in rows:
    bp = f"{r['badge_prec']:.3f}" if r["badge_prec"] is not None else "-"
    tp = f"{r['top3_prec']:.2f}" if r["top3_prec"] is not None else "-"
    cs = f"${r['cost_scan']:.4f}" if r["cost_scan"] else "-"
    ls = f"{r['lat_s']:.1f}" if r["lat_s"] else "-"
    print(f"{r['name']:<26}{r['imgs']:>5}{r['targets']:>6}{r['acc']:>7.3f}"
          f"{r['swap']:>7.3f}{bp:>8}{r['top3']:>8}{tp:>7}{cs:>9}{ls:>7}")

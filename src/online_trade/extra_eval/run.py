"""Entry points for the registered extra evaluations; see configs/extra_eval/."""

import json
import platform
import subprocess
import time

import numpy as np
import pandas as pd

from . import engine as E

OUT = E.ROOT / "results/tables/extra_eval"


def setup(periods=("discovery", "validation")):
    t = time.time()
    pool = E.build_pool()
    systems, maps = E.load_systems()
    loaded = {p: E.Period(p, pool, systems, maps) for p in periods}
    print(f"pool {len(pool.combos)} combinations, {len(systems)} systems, periods {list(loaded)} "
          f"({time.time() - t:.1f}s)", flush=True)
    return pool, systems, maps, loaded


def manifest(name, out, extra):
    files = sorted(p for p in out.glob("*.csv"))
    data = dict(experiment=name, test_read=False, protocol_sha256=E.sha256(E.ROOT / f"configs/extra_eval/{name}.json"),
                common_sha256=E.sha256(E.ROOT / "configs/extra_eval/common.json"),
                git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=E.ROOT, text=True).strip(),
                python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                outputs={p.name: E.sha256(p) for p in files}, **extra)
    (out / "manifest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_e10():
    from . import e10
    started = time.time()
    pool, systems, maps, periods = setup()
    weights = {p: E.bootstrap_weights(len(per.customers)) for p, per in periods.items()}
    records, gl_masks, lists = [], {"G": {}, "L": {}}, {}
    for i, key in enumerate(systems):
        rec, masks, lst = e10.run_system(pool, periods["discovery"], list(periods.values()), key)
        records += rec
        if key[0] == "GL":
            gl_masks[key[1]] = masks
            lists[key[1]] = lst
        if i % 50 == 0:
            print(f"  system {i + 1}/{len(systems)}", flush=True)
    out = OUT / "E10"
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    df.to_csv(out / "system_metrics.csv", index=False)
    summary, home = e10.summarize(records, gl_masks, periods, weights)
    summary.to_csv(out / "summary.csv", index=False)
    home.to_csv(out / "home_advantage.csv", index=False)
    e10.interpretation(summary, home).to_csv(out / "interpretation.csv", index=False)
    overlap = []
    for b in E.BUDGETS:
        for variant in lists["L"][b]:
            lc = set(c for rows in lists["L"][b][variant]["groups"].values() for c in rows)
            gc = set(c for rows in lists["G"][b][variant]["groups"].values() for c in rows)
            overlap.append(dict(budget=b, variant=variant, L_distinct=len(lc), G_distinct=len(gc),
                                L_also_in_G=len(lc & gc), L_not_in_G=len(lc - gc)))
    pd.DataFrame(overlap).to_csv(out / "L_G_overlap.csv", index=False)
    pd.concat([e10.list_table(pool, lists["G"], "G"), e10.list_table(pool, lists["L"], "L")]).to_csv(
        out / "real_lists.csv", index=False)
    checks = check_v1_against_frozen(df)
    manifest("E10", out, dict(systems=len(systems), elapsed_seconds=round(time.time() - started, 1), checks=checks))
    print(f"E10 done in {time.time() - started:.1f}s", flush=True)


def check_v1_against_frozen(df):
    """V1 must equal C's lists / D's Validation counts; checked on every run when D's table is present."""
    checks = {"V1_slots_equal_budget": bool((df[df.variant.str.startswith("V1")].slots == df[df.variant.str.startswith("V1")].budget).all())}
    shared = df[df.variant.isin(["V3_shared", "V4_shared", "V2_shared"])]
    checks["shared_variants_fill_budget"] = bool((shared.slots == shared.budget).all())
    try:  # D's frozen Validation table (branch d/evaluation), when available locally
        import io
        raw = subprocess.check_output(["git", "show", "origin/d/evaluation:results/tables/validation/system_metrics.csv"],
                                      cwd=E.ROOT, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        checks["V1_validation_matches_D"] = "D table not available"
        return checks
    d = pd.read_csv(io.BytesIO(raw), dtype={"seed": str}, keep_default_na=False)
    d = d[d.config.eq("P5")]
    x = df[df.variant.isin(["V1_restricted", "V1_shared"]) & df.period.eq("validation")].copy()
    x["flow"] = x.variant.str.split("_").str[1]
    m = x.merge(d, on=["control", "method", "seed", "budget", "flow"], suffixes=("", "_D"), validate="one_to_one")
    assert len(m) == 1332 and (m.covered_orders == m.covered_orders_D).all(), "V1 differs from D's frozen Validation"
    checks["V1_validation_matches_D"] = f"{len(m)} system rows, covered orders identical"
    return checks


def run_e9():
    from . import e9
    from .e10 import ranked_lists
    started = time.time()
    pool, systems, maps, periods = setup()
    weights = {p: E.bootstrap_weights(len(per.customers)) for p, per in periods.items()}
    records, gl_masks, gl_lists = [], {}, {}
    for key in systems:
        rec, masks, built = e9.run_system(pool, periods["discovery"], list(periods.values()), key, None)
        records += rec
        if key[0] == "GL":
            gl_masks[key[1]], gl_lists[key[1]] = masks, built
    out = OUT / "E9"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(out / "system_metrics.csv", index=False)
    summary = e9.summarize(records, gl_masks, periods, weights)
    summary.to_csv(out / "summary.csv", index=False)
    e9.interpretation(summary).to_csv(out / "interpretation.csv", index=False)
    e9.per_group(periods, gl_lists["L"], gl_lists["G"]).to_csv(out / "per_group.csv", index=False)
    key = ("GL", "L", "")
    ranked, sizes = ranked_lists(periods["discovery"], pool, key)
    counts = E.scope_counts(periods["discovery"], pool, key)
    e9.describe_real(pool, periods["discovery"], ranked, sizes, gl_lists["L"], gl_lists["G"], counts).to_csv(
        out / "discovery_list_description.csv", index=False)
    rows = []
    for method in ("G", "L"):
        for budget, lists in gl_lists[method].items():
            for g, combos in lists.items():
                for rank, c in enumerate(combos, 1):
                    rows.append(dict(method=method, budget=budget, list=g, rank=rank,
                                     combination=" + ".join(pool.cols[k] for k in pool.combos[c])))
    pd.DataFrame(rows).to_csv(out / "real_lists.csv", index=False)
    manifest("E9", out, dict(systems=len(systems), elapsed_seconds=round(time.time() - started, 1)))
    print(f"E9 done in {time.time() - started:.1f}s", flush=True)

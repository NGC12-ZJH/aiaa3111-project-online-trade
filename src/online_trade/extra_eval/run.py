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


E5_SETTINGS = [(50, 10), (20, 10), (100, 10), (50, 5), (50, 20)]  # (B0, k); first is primary


def run_e5():
    from . import e5
    started = time.time()
    pool, systems, maps, periods = setup()
    disc, val = periods["discovery"], periods["validation"]
    weights = E.bootstrap_weights(len(val.customers))
    g_rows = e5.g_list(pool, disc, 100 + 3 * 20)
    ret_rows, gain, real = [], [], {}
    for i, key in enumerate(systems):
        if key[1] == "G":
            continue
        sel = e5.select_specific(pool, disc, key)
        ev10 = e5.evaluate_rules(val, pool, key, sel, k=e5.K_PRIMARY)
        ev20 = e5.evaluate_rules(val, pool, key, sel, k=e5.K_MAX)
        ret_rows += e5.retention_summary(ev10, key)
        confirmed = {(r.group, r.rank) for r in ev20.itertuples() if r.confirmed} if len(ev20) else set()
        lists = {g: [(it["combo"], (g, rank) in confirmed) for rank, it in enumerate(items, 1)] for g, items in sel.items()}
        for period in (disc, val):
            for b0, k in E5_SETTINGS:
                for version in ("unconfirmed", "confirmed"):
                    row, hyb, comp = e5.gain_rows(pool, period, key, g_rows, lists, b0, k, version)
                    gain.append(row)
                    if key[0] == "GL" and period is val and (b0, k) == E5_SETTINGS[0]:
                        real[version] = (hyb, comp)
        if key[0] == "GL":
            real_sel, real_ev10, real_ev20 = sel, ev10, ev20
        if i % 50 == 0:
            print(f"  system {i + 1}/{len(systems)}", flush=True)
    out = OUT / "E5"
    out.mkdir(parents=True, exist_ok=True)
    ret = pd.DataFrame(ret_rows)
    ret.to_csv(out / "retention_by_system.csv", index=False)
    gains = pd.DataFrame(gain)
    gains.to_csv(out / "gain_by_system.csv", index=False)
    # real rule table
    name = lambda c: " + ".join(pool.cols[k] for k in pool.combos[c])
    rows = []
    for g, items in real_sel.items():
        for rank, it in enumerate(items, 1):
            r = it["rule"]
            e20 = real_ev20[(real_ev20.group == g) & (real_ev20["rank"] == rank)]
            e10 = real_ev10[(real_ev10.group == g) & (real_ev10["rank"] == rank)]
            rows.append(dict(group=g, rank=rank, antecedent=name(pool.r_ant[r]), consequent=name(pool.r_con[r]),
                             discovery_joint=it["joint"], discovery_confidence=it["confidence"],
                             discovery_outside_confidence=it["outside_confidence"],
                             discovery_advantage_pp=it["discovery_advantage_pp"],
                             validation_advantage_pp=float(e20.future_advantage_pp.iloc[0]),
                             validation_q_BY_top10=float(e10.q_BY.iloc[0]) if len(e10) else np.nan,
                             direction_retained=bool(e20.direction_retained.iloc[0]),
                             evidence_ok=bool(e20.evidence_ok.iloc[0]), confirmed=bool(e20.confirmed.iloc[0]),
                             evidence_retained_top10=bool(e10.evidence_retained.iloc[0]) if len(e10) else np.nan,
                             in_primary_top10=rank <= 10))
    pd.DataFrame(rows).to_csv(out / "real_specific_rules.csv", index=False)
    # E5a summary: real vs random controls
    summ = []
    for group in ("ALL", "0", "1", "2"):
        r = ret[ret.group.eq(group)]
        realrow = r[r.control.eq("GL")]
        if realrow.empty:
            continue
        realrow = realrow.iloc[0]
        for metric in ("direction_retention", "effect_ratio_median", "evidence_retained", "confirmed"):
            row = dict(group=group, metric=metric, real=realrow[metric], real_rules=realrow.rules)
            for control in ("A1", "S", "A2"):
                vals = r[r.control.eq(control)][metric].dropna()
                pos = random_position_safe(realrow[metric], vals)
                row.update({f"{control}_{k}": v for k, v in pos.items()})
            summ.append(row)
    pd.DataFrame(summ).to_csv(out / "e5a_summary.csv", index=False)
    # E5b summary
    gs = []
    for (period, version, b0, k), d in gains.groupby(["period", "version", "B0", "k"], sort=False):
        realrow = d[d.control.eq("GL")].iloc[0]
        row = dict(period=period, version=version, B0=b0, k=k, real_gain_pp=realrow.gain_pp,
                   real_hybrid=realrow.hybrid, real_comparator=realrow.comparator,
                   **{c: realrow[c] for c in d.columns if c.startswith("extra_slots_")})
        if period == "validation" and (b0, k) == E5_SETTINGS[0]:
            hyb, comp = real[version]
            ci = E.paired_interval(val, hyb, comp, weights)
            row.update(ci_low_pp=100 * ci["order"][1], ci_high_pp=100 * ci["order"][2],
                       macro_gain_pp=100 * ci["customer_macro"][0])
        for control in ("A1", "S", "A2"):
            pos = random_position_safe(realrow.gain_pp, d[d.control.eq(control)].gain_pp)
            row.update({f"{control}_{kk}": v for kk, v in pos.items()})
        gs.append(row)
    gsum = pd.DataFrame(gs)
    gsum.to_csv(out / "e5b_summary.csv", index=False)
    # registered interpretation (Validation preliminary)
    a = pd.DataFrame(summ)
    allrow = a[(a.group == "ALL") & (a.metric == "direction_retention")].iloc[0]
    prim = gsum[(gsum.period == "validation") & (gsum.B0 == 50) & (gsum.k == 10)]
    interp = [dict(rule="group_preference_real (E5a, Discovery->Validation)", value=allrow.real,
                   A1_p95=allrow.A1_random_p95, A1_empirical_p=allrow.A1_empirical_p,
                   passes=bool(allrow.A1_empirical_p <= 0.05))]
    for _, r in prim.iterrows():
        note = "" if r.version == "unconfirmed" else "descriptive only: confirmation used Validation"
        interp.append(dict(rule=f"slots_worth_it (E5b, {r.version})", value=r.real_gain_pp, ci_low_pp=r.ci_low_pp,
                           ci_high_pp=r.ci_high_pp, A1_p95=r.A1_random_p95, A1_empirical_p=r.A1_empirical_p,
                           passes=bool(r.real_gain_pp > 0 and r.ci_low_pp > 0 and r.A1_empirical_p <= 0.05), note=note))
    pd.DataFrame(interp).to_csv(out / "interpretation.csv", index=False)
    manifest("E5", out, dict(systems=len(systems) - 1, elapsed_seconds=round(time.time() - started, 1),
                             settings_B0_k=E5_SETTINGS))
    print(f"E5 done in {time.time() - started:.1f}s", flush=True)


def random_position_safe(real, values):
    values = pd.Series(values).dropna()
    if values.empty or pd.isna(real):
        return dict(random_n=len(values))
    return E.random_position(float(real), values.to_numpy())

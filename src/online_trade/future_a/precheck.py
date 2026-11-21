"""Pre-check P0-P4 for future work A (registered: configs/future_A/precheck.json).

P0-P3 read only orders before 2010-12-01 (later rows are dropped right after reading).
P4 evaluates the existing Discovery P5 lists on Validation through the extra_eval engine,
which refuses to read Test.
"""

import io
import json
import platform
import subprocess
import time

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, cohen_kappa_score
from sklearn.preprocessing import StandardScaler

from online_trade.clustering.features import build_rfm
from online_trade.extra_eval import e9
from online_trade.extra_eval import engine as E
from online_trade.extra_eval.e10 import ranked_lists

ROOT = E.ROOT
PROTOCOL = ROOT / "configs/future_A/precheck.json"
OUT = ROOT / "results/tables/future_A/precheck"
LIMIT = pd.Timestamp("2010-12-01")
PROFILE_CUTOFF = pd.Timestamp("2010-06-01")
CUTOFFS = [pd.Timestamp(f"2010-{m:02d}-01") for m in range(6, 13)]
GROUPS = ("0", "1", "2")


# ---------------------------------------------------------------- inputs
def load_orders():
    raw = subprocess.check_output(["git", "show", f"{E.SNAPSHOT}:data/processed/A_data_preparation/orders.csv.gz"],
                                  cwd=ROOT)
    o = pd.read_csv(io.BytesIO(raw), compression="gzip", dtype=str, keep_default_na=False)
    o["invoice_datetime"] = pd.to_datetime(o["invoice_datetime"])
    o = o[o.invoice_datetime < LIMIT].reset_index(drop=True)       # drop Validation/Test rows at once
    assert o.invoice_datetime.max() < LIMIT and set(o.split) <= {"profile", "discovery"}
    for c in ["gross_purchase_amount", "net_amount", "basket_size"]:
        o[c] = o[c].astype(float)
    return o


def frozen_labels():
    local = pd.read_csv(E.LOCAL / "customer_clusters.csv", dtype=str)
    raw = subprocess.check_output(["git", "show", f"{E.SNAPSHOT}:data/processed/B_customer_clustering/customer_clusters.csv"],
                                  cwd=ROOT)
    snap = pd.read_csv(io.BytesIO(raw), dtype=str)
    assert local[["customer_id", "cluster_id"]].equals(snap[["customer_id", "cluster_id"]]), "local labels differ from snapshot"
    s = snap.set_index("customer_id").cluster_id.sort_index()
    assert len(s) == 2684
    return s


def rfm_at(orders, customers, cutoff):
    """R/F/M of the 6-month window ending at `cutoff` (registered definition)."""
    start = cutoff - pd.DateOffset(months=6)
    v = orders[orders.is_valid_rfm_order.eq("1") & orders.is_identified_customer.eq("1")
               & orders.customer_id.isin(customers) & (orders.invoice_datetime < cutoff)]
    w = v[v.invoice_datetime >= start].groupby("customer_id")
    out = pd.DataFrame(index=pd.Index(customers, name="customer_id"))
    out["recency"] = (cutoff - v.groupby("customer_id").invoice_datetime.max()).dt.total_seconds() / 86400
    out["frequency"] = w.basket_id.nunique()
    out["monetary"] = w.gross_purchase_amount.sum()
    out[["frequency", "monetary"]] = out[["frequency", "monetary"]].fillna(0)
    assert out.recency.notna().all()
    return out


def features(rfm):
    return np.column_stack([rfm.recency, np.log1p(rfm.frequency), np.log1p(rfm.monetary.clip(lower=0))])


def nearest(Z, centroids):
    d = ((Z[:, None, :] - centroids[None, :, :]) ** 2).sum(-1)
    return np.array(GROUPS)[d.argmin(1)]


# ---------------------------------------------------------------- comparisons
def compare(old, new, mask=None, label=""):
    old, new = pd.Series(old), pd.Series(new, index=old.index)
    if mask is not None:
        old, new = old[mask], new[mask]
    p = old.value_counts(normalize=True).reindex(GROUPS, fill_value=0)
    q = new.value_counts(normalize=True).reindex(GROUPS, fill_value=0)
    row = dict(population=label, customers=len(old), retention=float((old == new).mean()),
               chance_retention=float((p * q).sum()), kappa=float(cohen_kappa_score(old, new)),
               ari=float(adjusted_rand_score(old, new)))
    for g in GROUPS:
        m = old == g
        row[f"retention_C{g}"] = float((new[m] == g).mean()) if m.any() else np.nan
        row[f"old_size_C{g}"], row[f"new_size_C{g}"] = int(m.sum()), int((new == g).sum())
    return row


def transition(old, new, mask, version, population):
    t = pd.crosstab(pd.Series(old[mask].to_numpy(), name="old"), pd.Series(new[mask].to_numpy(), name="new")) \
        .reindex(index=GROUPS, columns=GROUPS, fill_value=0)
    rows = []
    for g in GROUPS:
        n = t.loc[g].sum()
        rows.append(dict(version=version, population=population, old=g, old_customers=int(n),
                         **{f"to_C{h}": int(t.loc[g, h]) for h in GROUPS},
                         **{f"share_to_C{h}": t.loc[g, h] / n if n else np.nan for h in GROUPS}))
    return rows


# ---------------------------------------------------------------- P0-P3
def labels_drift(orders, frozen, val_customers):
    customers = frozen.index.to_numpy()
    # P0 -----------------------------------------------------------------
    prof = orders[orders.split.eq("profile") & orders.is_identified_customer.eq("1")].copy()
    ref = build_rfm(prof, "2010-06-01")
    r0 = rfm_at(orders, customers, PROFILE_CUTOFF)
    ref = ref.reindex(r0.index)
    assert np.allclose(ref.recency, r0.recency) and (ref.frequency == r0.frequency).all() \
        and np.allclose(ref.monetary, r0.monetary), "window RFM differs from build_rfm at the Profile cutoff"
    X0 = features(r0)
    scaler = StandardScaler().fit(X0)
    Z0 = scaler.transform(X0)
    member_means = np.vstack([Z0[frozen.to_numpy() == g].mean(0) for g in GROUPS])
    member_mean_mismatches = int((nearest(Z0, member_means) != frozen.to_numpy()).sum())
    # Amendment 2026-11-21: centres of the original K-means refit (member means miss one boundary customer)
    km0 = KMeans(n_clusters=3, n_init=10, random_state=42).fit(Z0)
    mapping = {}
    for k in range(3):
        members = set(frozen.to_numpy()[km0.labels_ == k])
        assert len(members) == 1, "refit cluster spans several frozen labels"
        mapping[k] = members.pop()
    assert sorted(mapping.values()) == list(GROUPS)
    centroids = np.vstack([km0.cluster_centers_[[k for k, g2 in mapping.items() if g2 == g][0]] for g in GROUPS])
    rebuilt = nearest(Z0, centroids)
    mismatches = int((rebuilt != frozen.to_numpy()).sum())
    if mismatches:
        raise AssertionError(f"P0 failed: {mismatches} Profile customers not reproduced by the rebuilt centroids")
    p0 = dict(customers=len(customers), mismatches=mismatches, member_mean_centroid_mismatches=member_mean_mismatches,
              centroid_source="KMeans(n_clusters=3, n_init=10, random_state=42) refit on standardized Profile features",
              member_mean_centroids_standardized={f"C{g}": member_means[i].tolist() for i, g in enumerate(GROUPS)},
              scaler_mean=scaler.mean_.tolist(),
              scaler_scale=scaler.scale_.tolist(), features=["recency_days", "log1p_frequency", "log1p_monetary"],
              centroids_standardized={f"C{g}": centroids[i].tolist() for i, g in enumerate(GROUPS)},
              centroids_raw={f"C{g}": scaler.inverse_transform(centroids[i:i + 1])[0].tolist() for i, g in enumerate(GROUPS)},
              profile_max_recency_days=float(r0.recency.max()))

    # P1 -----------------------------------------------------------------
    r1 = rfm_at(orders, customers, LIMIT)
    X1 = features(r1)
    Z1 = scaler.transform(X1)
    old = pd.Series(frozen.to_numpy(), index=customers)
    p1 = pd.Series(nearest(Z1, centroids), index=customers)
    active = (r1.frequency > 0).to_numpy()
    in_val = np.isin(customers, list(val_customers))

    # P2a / P2b ----------------------------------------------------------
    p2a = pd.Series(nearest(StandardScaler().fit(X1).transform(X1), centroids), index=customers)
    sc = StandardScaler().fit(X1[active])
    km = KMeans(n_clusters=3, n_init=10, random_state=42).fit(sc.transform(X1[active]))
    raw_new = km.predict(sc.transform(X1))
    overlap = pd.crosstab(old.to_numpy(), raw_new).reindex(index=GROUPS, columns=range(3), fill_value=0)
    r_idx, c_idx = linear_sum_assignment(-overlap.to_numpy())
    align = {int(c): GROUPS[r] for r, c in zip(r_idx, c_idx)}
    p2b = pd.Series([align[int(k)] for k in raw_new], index=customers)
    overlap_tbl = overlap.copy()
    overlap_tbl.columns = [f"new_fit_cluster_{c}_aligned_to_C{align[c]}" for c in overlap.columns]
    overlap_tbl.index = [f"old_C{g}" for g in GROUPS]
    p2b_centroids = sc.inverse_transform(km.cluster_centers_)

    rows, trans = [], []
    for version, new in [("P1_fixed", p1), ("P2a_relative", p2a), ("P2b_refit_aligned", p2b)]:
        for pop, mask in [("all", np.ones(len(customers), bool)), ("validation_customers", in_val),
                          ("active_in_discovery", active), ("active_and_validation", active & in_val)]:
            rows.append(dict(version=version, **compare(old, new, mask, pop)))
            trans += transition(old, new, mask, version, pop)
    summary = pd.DataFrame(rows)

    # cluster-level description (MONIC-style)
    cl = []
    for i, g in enumerate(GROUPS):
        m = old.to_numpy() == g
        cl.append(dict(old_cluster=g, customers=int(m.sum()), silent_in_discovery=float((~active[m]).mean()),
                       silent_and_has_validation_orders=float((~active[m] & in_val[m]).mean()),
                       recency_above_profile_max=float((r1.recency.to_numpy()[m] > r0.recency.max()).mean()),
                       new_size_P1=int((p1 == g).sum()), new_size_P2a=int((p2a == g).sum()),
                       **{f"shift_std_{f}": float(Z1[m].mean(0)[j] - centroids[i][j])
                          for j, f in enumerate(["R", "logF", "logM"])},
                       profile_median_F=float(r0.frequency[m].median()), discovery_median_F=float(r1.frequency[m].median()),
                       profile_median_M=float(r0.monetary[m].median()), discovery_median_M=float(r1.monetary[m].median())))
    clusters = pd.DataFrame(cl)

    # P3 drift curve ------------------------------------------------------
    curve = []
    for cutoff in CUTOFFS[1:]:
        rc = rfm_at(orders, customers, cutoff)
        lc = pd.Series(nearest(scaler.transform(features(rc)), centroids), index=customers)
        delta = (cutoff.year - PROFILE_CUTOFF.year) * 12 + cutoff.month - PROFILE_CUTOFF.month
        act = (rc.frequency > 0).to_numpy()
        for pop, mask in [("all", np.ones(len(customers), bool)), ("active_in_both", act)]:
            curve.append(dict(cutoff=str(cutoff.date()), delta_months=delta,
                              silent_share=float((~act).mean()), **compare(old, lc, mask, pop)))
    curve = pd.DataFrame(curve)

    # newcomers (section 6.3, count only)
    v = orders[orders.is_valid_rfm_order.eq("1") & orders.is_identified_customer.eq("1")
               & (orders.invoice_datetime >= PROFILE_CUTOFF)]
    newc = v[~v.customer_id.isin(customers)]
    newcomers = dict(new_customers_in_discovery=int(newc.customer_id.nunique()),
                     their_valid_discovery_orders=int(newc.basket_id.nunique()),
                     profile_customers_valid_discovery_orders=int(v[v.customer_id.isin(customers)].basket_id.nunique()))

    labels = pd.DataFrame({"customer_id": customers, "frozen": old.to_numpy(), "P1": p1.to_numpy(), "P2a": p2a.to_numpy(),
                           "P2b": p2b.to_numpy(), "active_in_discovery": active, "has_validation_orders": in_val,
                           "discovery_R": r1.recency.to_numpy(), "discovery_F": r1.frequency.to_numpy(),
                           "discovery_M": r1.monetary.to_numpy()})
    extra = dict(p2b_alignment=align, p2b_centroids_raw=p2b_centroids.tolist())
    return p0, summary, pd.DataFrame(trans), overlap_tbl, clusters, curve, newcomers, labels, extra


# ---------------------------------------------------------------- P4
def assignment_coverage(period, C, assign):
    """Basket coverage when every customer uses list index assign[customer]."""
    return C[assign[period.cust_of_basket], np.arange(period.n)]


def impact_bound(pool, disc, val, keys, new_maps, weights, budgets=E.BUDGETS):
    cust = val.customers
    gidx = {g: i for i, g in enumerate(GROUPS)}
    rows, real, ci_rows = [], {}, []
    for key in keys:
        ranked, _ = ranked_lists(disc, pool, key)
        for b in budgets:
            lists, _ = e9.build(pool, ranked, b)
            if key[1] == "G":
                cov = val.covered(set(lists["GLOBAL"]))
                rows.append(dict(control=key[0], method="G", seed=key[2], budget=b, assignment="global", **val.summary(cov)))
                real[("G", b)] = cov
                continue
            assert sorted(lists) == list(GROUPS)
            C = np.vstack([val.covered(set(lists[g])) for g in GROUPS])
            H = np.asarray((val.cust_matrix @ C.T.astype(np.float64))).T          # 3 x customers
            orig = np.array([gidx[g] for g in val.cust_groups[key]])
            best = H.max(0)
            oracle = np.where(H[orig, np.arange(len(cust))] == best, orig, H.argmax(0))
            assigns = {"orig": orig, "oracle": oracle}
            if key[0] == "GL":
                for name, m in new_maps.items():
                    assigns[name] = np.array([gidx[m[c]] for c in cust])
            for name, a in assigns.items():
                cov = assignment_coverage(val, C, a)
                rows.append(dict(control=key[0], method="L", seed=key[2], budget=b, assignment=name,
                                 customers_moved=int((a != orig).sum()), **val.summary(cov)))
                if key[0] == "GL":
                    real[(name, b)] = cov
    df = pd.DataFrame(rows)
    for b in budgets:
        for name in [n for n in ["swap_P1", "swap_P2a", "oracle"]]:
            ci = E.paired_interval(val, real[(name, b)], real[("orig", b)], weights)
            ci_rows.append(dict(budget=b, comparison=f"{name} - orig", order_pp=100 * ci["order"][0],
                                order_ci_low_pp=100 * ci["order"][1], order_ci_high_pp=100 * ci["order"][2],
                                macro_pp=100 * ci["customer_macro"][0], macro_ci_low_pp=100 * ci["customer_macro"][1],
                                macro_ci_high_pp=100 * ci["customer_macro"][2]))
    return df, pd.DataFrame(ci_rows)


def summarize_p4(df, cis):
    out = []
    for b, d in df[df.method.eq("L")].groupby("budget"):
        piv = d.pivot_table(index=["control", "seed"], columns="assignment", values="coverage")
        piv["oracle_gain_pp"] = 100 * (piv["oracle"] - piv["orig"])
        realrow = piv.loc[("GL", "")]
        a1 = piv.loc["A1"]
        g = df[(df.method == "G") & (df.budget == b)].coverage.iloc[0]
        pos = E.random_position(realrow.oracle_gain_pp, a1.oracle_gain_pp.to_numpy())
        row = dict(budget=b, G=g, L_orig=realrow.orig, L_swap_P1=realrow.swap_P1, L_swap_P2a=realrow.swap_P2a,
                   L_oracle=realrow.oracle, oracle_gain_pp=realrow.oracle_gain_pp,
                   A1_orig_median=float(a1.orig.median()), A1_oracle_median=float(a1.oracle.median()),
                   A1_oracle_gain_median_pp=pos["random_median"], A1_oracle_gain_p95_pp=pos["random_p95"],
                   A1_oracle_gain_ge_real=pos["random_ge_real"], A1_oracle_gain_empirical_p=pos["empirical_p"],
                   adjusted_oracle_gain_pp=realrow.oracle_gain_pp - pos["random_median"])
        for _, c in cis[cis.budget.eq(b)].iterrows():
            tag = c.comparison.split(" ")[0]
            row.update({f"{tag}_order_pp": c.order_pp, f"{tag}_ci_low_pp": c.order_ci_low_pp,
                        f"{tag}_ci_high_pp": c.order_ci_high_pp, f"{tag}_macro_pp": c.macro_pp})
        out.append(row)
    return pd.DataFrame(out)


def check_against_e9(p4):
    e9s = pd.read_csv(ROOT / "results/tables/extra_eval/E9/summary.csv")
    e9s = e9s[e9s.period.eq("validation")].set_index("budget")
    for _, r in p4.iterrows():
        assert abs(r.L_orig - e9s.loc[r.budget, "L"]) < 1e-12 and abs(r.G - e9s.loc[r.budget, "G"]) < 1e-12, \
            f"L_orig/G differ from E9 at budget {r.budget}"
    return "L_orig and G equal E9 Validation coverage at budgets 20/50/100"


# ---------------------------------------------------------------- decisions and run
def decisions(summary, p4):
    s = summary.set_index(["version", "population"])
    k1 = s.loc[("P1_fixed", "all"), "kappa"]
    ret_c = s.loc[("P1_fixed", "active_in_discovery"), "retention"]
    k2a = s.loc[("P2a_relative", "all"), "kappa"]
    ret_c2a = s.loc[("P2a_relative", "active_in_discovery"), "retention"]
    r100 = p4.set_index("budget").loc[100]
    stage1 = bool(k1 >= 0.6 and ret_c >= 0.80)
    stage2 = bool(r100.oracle_gain_pp < 1.0)
    stage3 = bool(r100.swap_P1_order_pp >= 0.5)
    if stage1:
        verdict = "labels_essentially_stable: section 6 not run"
    elif stage2:
        verdict = "no_room: labels changed but refreshing cannot matter for these lists; section 6 not run"
    elif stage3:
        verdict = "go: register and run section 6 round 2"
    else:
        verdict = "stop: oracle room exists but the simple label swap gains < 0.5 pp"
    return dict(stage1=dict(P1_kappa_all=k1, P2c_retention_active=ret_c, labels_stable=stage1,
                            season_adjusted_P2a_kappa_all=k2a, season_adjusted_P2a_retention_active=ret_c2a,
                            stable_after_season_adjustment=bool(k2a >= 0.6 and ret_c2a >= 0.80)),
                stage2=dict(oracle_gain_pp_B100=r100.oracle_gain_pp, adjusted_oracle_gain_pp_B100=r100.adjusted_oracle_gain_pp,
                            no_room=stage2),
                stage3=dict(swap_P1_gain_pp_B100=r100.swap_P1_order_pp, go=stage3),
                verdict=verdict)


def run():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = frozen_labels()
    orders = load_orders()
    pool = E.build_pool()
    systems, maps = E.load_systems()
    keys = [k for k in systems if k[0] in ("GL", "A1")]
    disc = E.Period("discovery", pool, keys, maps)
    val = E.Period("validation", pool, keys, maps)
    assert set(val.customers) <= set(frozen.index)
    print(f"inputs loaded ({time.time() - started:.1f}s)", flush=True)

    p0, summary, trans, overlap, clusters, curve, newcomers, labels, extra = labels_drift(orders, frozen, set(val.customers))
    print(f"P0-P3 done ({time.time() - started:.1f}s)", flush=True)
    new_maps = {"swap_P1": dict(zip(labels.customer_id, labels.P1)), "swap_P2a": dict(zip(labels.customer_id, labels.P2a))}
    weights = E.bootstrap_weights(len(val.customers))
    df, cis = impact_bound(pool, disc, val, keys, new_maps, weights)
    p4 = summarize_p4(df, cis)
    check = check_against_e9(p4)
    print(f"P4 done ({time.time() - started:.1f}s)", flush=True)

    (ROOT / "results/tables/future_A").mkdir(parents=True, exist_ok=True)
    (ROOT / "results/tables/future_A/frozen_scaler_centroids.json").write_text(
        json.dumps(p0, indent=2) + "\n", encoding="utf-8")
    summary.to_csv(OUT / "label_drift_summary.csv", index=False)
    trans.to_csv(OUT / "transition_matrices.csv", index=False)
    overlap.to_csv(OUT / "P2b_member_overlap.csv")
    clusters.to_csv(OUT / "cluster_level.csv", index=False)
    curve.to_csv(OUT / "drift_curve.csv", index=False)
    df.to_csv(OUT / "P4_system_metrics.csv", index=False)
    cis.to_csv(OUT / "P4_paired_intervals.csv", index=False)
    p4.to_csv(OUT / "P4_summary.csv", index=False)
    dec = decisions(summary, p4)
    (OUT / "decision.json").write_text(json.dumps(dec, indent=2, default=float) + "\n", encoding="utf-8")
    files = sorted(OUT.glob("*.csv")) + [OUT / "decision.json"]
    manifest = dict(protocol="configs/future_A/precheck.json", protocol_sha256=E.sha256(PROTOCOL), test_read=False,
                    orders_max_datetime_read=str(orders.invoice_datetime.max()),
                    git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                    checks=dict(P0_mismatches=p0["mismatches"], P4_vs_E9=check, window_rfm_equals_build_rfm=True),
                    newcomers=newcomers, p2b=extra, systems=len(keys),
                    elapsed_seconds=round(time.time() - started, 1),
                    outputs={p.name: E.sha256(p) for p in files})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(dec, indent=2, default=float))
    print(f"precheck done in {time.time() - started:.1f}s", flush=True)

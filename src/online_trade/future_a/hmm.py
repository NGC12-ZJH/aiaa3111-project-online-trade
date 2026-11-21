"""P5 of future work A: Poisson hidden Markov models of monthly order counts (configs/future_A/p5_hmm.json).

Pooled (non-hierarchical) Baum-Welch with scaled forward-backward, written with numpy/scipy because
hmmlearn is not installed. Only orders before 2010-12-01 are read.
"""

import json
import platform
import subprocess
import time

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.special import gammaln
from sklearn.metrics import cohen_kappa_score

from online_trade.extra_eval import engine as E

from . import precheck as P

OUT = E.ROOT / "results/tables/future_A/p5_hmm"
PROTOCOL = E.ROOT / "configs/future_A/p5_hmm.json"
MONTHS = pd.period_range("2009-12", "2010-11", freq="M")
PEAK = np.array([m.month in (9, 10, 11) and m.year == 2010 for m in MONTHS])
STARTS, MAX_ITER, TOL = range(20), 2000, 1e-6


# ---------------------------------------------------------------- data
def monthly_counts():
    frozen = P.frozen_labels()
    o = P.load_orders()
    v = o[o.is_valid_rfm_order.eq("1") & o.is_identified_customer.eq("1") & o.customer_id.isin(frozen.index)].copy()
    v["month"] = v.invoice_datetime.dt.to_period("M")
    c = v.groupby(["customer_id", "month"]).basket_id.nunique().unstack(fill_value=0)
    c = c.reindex(index=frozen.index, columns=MONTHS, fill_value=0)
    y = c.to_numpy().astype(float)
    assert (y[:, :6].sum(1) > 0).all(), "every Profile customer should have an order in months 1-6"
    return frozen, y


# ---------------------------------------------------------------- model
class Model:
    """K-state Poisson HMM. variant: 'M1' homogeneous, 'M2' peak effect on means, 'M3' peak transition matrix."""

    def __init__(self, K, variant="M1"):
        self.K, self.variant = K, variant

    def n_params(self):
        K = self.K
        p = (K - 1) + K * (K - 1) + K
        return p + (1 if self.variant == "M2" else 0) + (K * (K - 1) if self.variant == "M3" else 0)

    def init(self, y, rng):
        K = self.K
        self.lam = np.sort(y.mean() * rng.uniform(0.1, 3.0, K))
        self.beta = 0.0
        self.pi = rng.dirichlet(np.ones(K))
        self.A = np.array([rng.dirichlet(np.ones(K) + 5 * np.eye(K)[k]) for k in range(K)])
        self.A_peak = self.A.copy()

    def trans(self, t):
        return self.A_peak if (self.variant == "M3" and PEAK[t]) else self.A

    def mu(self):
        eff = np.exp(self.beta * PEAK) if self.variant == "M2" else np.ones(len(PEAK))
        return self.lam[None, :] * eff[:, None]                                   # T x K

    def log_emission(self, y):
        mu = self.mu()
        return y[:, :, None] * np.log(mu)[None] - mu[None] - gammaln(y + 1)[:, :, None]   # N x T x K

    def forward_backward(self, y):
        N, T = y.shape
        le = self.log_emission(y)
        off = le.max(2, keepdims=True)
        b = np.exp(le - off)
        alpha, c = np.empty((N, T, self.K)), np.empty((N, T))
        a = self.pi[None] * b[:, 0]
        c[:, 0] = a.sum(1)
        alpha[:, 0] = a / c[:, :1]
        for t in range(1, T):
            a = (alpha[:, t - 1] @ self.trans(t)) * b[:, t]
            c[:, t] = a.sum(1)
            alpha[:, t] = a / c[:, t:t + 1]
        beta = np.ones((N, T, self.K))
        for t in range(T - 2, -1, -1):
            beta[:, t] = ((b[:, t + 1] * beta[:, t + 1]) @ self.trans(t + 1).T) / c[:, t + 1:t + 2]
        ll = np.log(c).sum() + off.sum()
        return alpha, beta, b, c, ll

    def m_step(self, y, alpha, beta, b, c):
        N, T = y.shape
        gamma = alpha * beta
        gamma /= gamma.sum(2, keepdims=True)
        self.pi = gamma[:, 0].mean(0)
        xi_off, xi_peak = np.zeros((self.K, self.K)), np.zeros((self.K, self.K))
        for t in range(1, T):
            xi = alpha[:, t - 1, :, None] * self.trans(t)[None] * (b[:, t] * beta[:, t])[:, None, :] / c[:, t, None, None]
            s = xi.sum(0)
            if self.variant == "M3" and PEAK[t]:
                xi_peak += s
            else:
                xi_off += s
        self.A = xi_off / xi_off.sum(1, keepdims=True)
        if self.variant == "M3":
            self.A_peak = xi_peak / xi_peak.sum(1, keepdims=True)
        gy = (gamma * y[:, :, None]).sum(0)          # T x K
        g = gamma.sum(0)                              # T x K
        if self.variant == "M2":
            for _ in range(20):
                eff = np.exp(self.beta * PEAK)
                self.lam = gy.sum(0) / (g * eff[:, None]).sum(0)
                self.beta = np.log(gy[PEAK].sum() / (g[PEAK] * self.lam[None]).sum())
        else:
            self.lam = gy.sum(0) / g.sum(0)
        self.lam = np.maximum(self.lam, 1e-8)

    def fit(self, y, seed):
        self.init(y, np.random.default_rng(seed))
        prev = -np.inf
        for it in range(MAX_ITER):
            alpha, beta, b, c, ll = self.forward_backward(y)
            if ll - prev < TOL:
                break
            prev = ll
            self.m_step(y, alpha, beta, b, c)
        self.ll, self.iterations = ll, it + 1
        self.reorder()
        return self

    def reorder(self):
        order = np.argsort(self.lam)
        self.lam, self.pi = self.lam[order], self.pi[order]
        self.A = self.A[np.ix_(order, order)]
        self.A_peak = self.A_peak[np.ix_(order, order)]

    def filtered(self, y):
        alpha, *_ = self.forward_backward(y)
        return alpha

    def viterbi(self, y):
        N, T = y.shape
        le = self.log_emission(y)
        d = np.log(self.pi)[None] + le[:, 0]
        back = np.zeros((N, T, self.K), dtype=int)
        for t in range(1, T):
            s = d[:, :, None] + np.log(self.trans(t))[None]
            back[:, t] = s.argmax(1)
            d = s.max(1) + le[:, t]
        path = np.zeros((N, T), dtype=int)
        path[:, -1] = d.argmax(1)
        for t in range(T - 1, 0, -1):
            path[:, t - 1] = back[np.arange(N), t, path[:, t]]
        return path

    def simulate(self, N, T, rng):
        states = np.zeros((N, T), dtype=int)
        states[:, 0] = rng.choice(self.K, N, p=self.pi)
        for t in range(1, T):
            A = self.trans(t)
            u = rng.random(N)
            states[:, t] = (u[:, None] > np.cumsum(A[states[:, t - 1]], 1)).sum(1)
        return rng.poisson(self.mu()[np.arange(T)[None], states]).astype(float)

    def describe(self):
        return dict(variant=self.variant, K=self.K, loglik=float(self.ll), n_params=self.n_params(),
                    iterations=self.iterations, lam=self.lam.tolist(), beta=float(self.beta),
                    peak_multiplier=float(np.exp(self.beta)), pi=self.pi.tolist(), A=self.A.tolist(),
                    A_peak=self.A_peak.tolist() if self.variant == "M3" else None)


def best_fit(y, K, variant):
    fits = [Model(K, variant).fit(y, s) for s in STARTS]
    best = max(fits, key=lambda m: m.ll)
    best.start_lls = sorted((float(m.ll) for m in fits), reverse=True)
    return best


def stationary(A):
    w, v = np.linalg.eig(A.T)
    s = np.real(v[:, np.argmin(np.abs(w - 1))])
    return s / s.sum()


def aligned_agreement(labels, states, K):
    labels = pd.Series(labels).astype(str).to_numpy()
    groups = sorted(set(labels))
    tab = pd.crosstab(labels, states).reindex(index=groups, columns=range(K), fill_value=0)
    r, c = linear_sum_assignment(-tab.to_numpy())
    mapping = {int(cc): groups[rr] for rr, cc in zip(r, c)}
    mapped = np.array([mapping.get(int(s), "unmatched") for s in states])
    return tab, mapping, float((mapped == labels).mean()), float(cohen_kappa_score(labels, mapped))


# ---------------------------------------------------------------- run
def run():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    frozen, y = monthly_counts()
    N, T = y.shape
    n_obs = N * T
    print(f"data: {N} customers x {T} months, mean {y.mean():.3f} orders/month ({time.time() - started:.1f}s)", flush=True)

    fits = {}
    for K, variant in [(3, "M1"), (3, "M2"), (3, "M3"), (2, "M1"), (4, "M1")]:
        fits[(K, variant)] = best_fit(y, K, variant)
        m = fits[(K, variant)]
        print(f"  K={K} {variant}: logL {m.ll:.1f} ({time.time() - started:.1f}s)", flush=True)
    models = pd.DataFrame([dict(**{k: v for k, v in m.describe().items() if k in ("variant", "K", "loglik", "n_params", "iterations", "peak_multiplier")},
                                bic=-2 * m.ll + m.n_params() * np.log(n_obs),
                                second_best_start_loglik=m.start_lls[1], starts_within_0p1_of_best=int(sum(abs(l - m.ll) < 0.1 for l in m.start_lls)))
                           for m in fits.values()])

    # simulation check on the primary model
    m1 = fits[(3, "M1")]
    ysim = m1.simulate(N, T, np.random.default_rng(12345))
    refit = best_fit(ysim, 3, "M1")
    a_err = float(np.abs(refit.A - m1.A).max())
    lam_err = float(np.max(np.abs(refit.lam - m1.lam) / m1.lam))
    sim = dict(max_abs_transition_error=a_err, max_rel_mean_error=lam_err,
               passed=bool(a_err < 0.05 and lam_err < 0.10), refit=refit.describe())
    print(f"simulation check: A err {a_err:.4f}, mean err {lam_err:.4f} ({time.time() - started:.1f}s)", flush=True)

    # descriptions of the primary model
    st = stationary(m1.A)
    A6 = np.linalg.matrix_power(m1.A, 6)
    persistence = pd.DataFrame(dict(state=range(3), mean_orders_per_month=m1.lam, monthly_persistence=np.diag(m1.A),
                                    six_month_persistence=np.diag(A6), stationary_share=st))
    weighted_diag = float((st * np.diag(m1.A)).sum())

    pre = pd.read_csv(E.ROOT / "results/tables/future_A/precheck/label_drift_summary.csv")
    HARD_SWITCH = 1 - float(pre[(pre.version == "P1_fixed") & (pre.population == "all")].retention.iloc[0])
    assert abs(HARD_SWITCH - 0.487) < 1e-3   # pre-check P1: retention 51.3%
    rows = []
    for (K, variant), m in fits.items():
        if K != 3:
            continue
        alpha = m.filtered(y)
        s6, s12 = alpha[:, 5].argmax(1), alpha[:, 11].argmax(1)
        vit = m.viterbi(y)
        rows.append(dict(variant=variant, filtered_switch_m6_to_m12=float((s6 != s12).mean()),
                         viterbi_switch_m6_to_m12=float((vit[:, 5] != vit[:, 11]).mean()),
                         hard_label_switch=HARD_SWITCH,
                         noise_indicator=1 - float((s6 != s12).mean()) / HARD_SWITCH,
                         confident_share_m12=float((alpha[:, 11].max(1) >= 0.8).mean()),
                         **{f"share_state{k}_m6": float((s6 == k).mean()) for k in range(3)},
                         **{f"share_state{k}_m12": float((s12 == k).mean()) for k in range(3)}))
        if variant == "M1":
            primary_states = (s6, s12)
            trans_6_12 = pd.crosstab(pd.Series(s6, name="state_m6"), pd.Series(s12, name="state_m12"))
    switching = pd.DataFrame(rows)

    # correspondence with K-means labels
    frozen_v = frozen.to_numpy()
    labels_p1 = None
    try:
        from .round2 import new_labels   # P1 labels (same code as the pre-check)
        lab = new_labels()
        labels_p1 = lab.set_index("customer_id").loc[frozen.index, "P1"].to_numpy()
    except Exception as exc:   # pragma: no cover
        raise RuntimeError(f"could not rebuild P1 labels: {exc}")
    corr = []
    tabs = []
    for name, labels, states in [("frozen_vs_state_m6", frozen_v, primary_states[0]),
                                 ("P1_vs_state_m12", labels_p1, primary_states[1])]:
        tab, mapping, agree, kappa = aligned_agreement(labels, states, 3)
        corr.append(dict(comparison=name, aligned_agreement=agree, kappa=kappa, mapping=json.dumps(mapping)))
        t = tab.copy()
        t.index = [f"Kmeans_C{g}" for g in t.index]
        t.columns = [f"HMM_state{c}" for c in t.columns]
        t.insert(0, "comparison", name)
        tabs.append(t)
    corr = pd.DataFrame(corr)

    models.to_csv(OUT / "models.csv", index=False)
    persistence.to_csv(OUT / "M1_K3_persistence.csv", index=False)
    switching.to_csv(OUT / "switching.csv", index=False)
    trans_6_12.to_csv(OUT / "M1_K3_state_m6_to_m12.csv")
    corr.to_csv(OUT / "kmeans_correspondence.csv", index=False)
    pd.concat(tabs).to_csv(OUT / "kmeans_correspondence_tables.csv")
    params = {f"K{K}_{v}": m.describe() for (K, v), m in fits.items()}
    (OUT / "parameters.json").write_text(json.dumps(dict(params=params, simulation_check=sim,
                                                         stationary_weighted_monthly_diagonal=weighted_diag,
                                                         chen_2019_monthly_diagonal_sum=0.85,
                                                         data=dict(customers=N, months=[str(m) for m in MONTHS],
                                                                   peak_months=[str(m) for m in MONTHS[PEAK]],
                                                                   mean_orders_per_month=float(y.mean()),
                                                                   monthly_mean=y.mean(0).tolist(),
                                                                   zero_share_by_month=(y == 0).mean(0).tolist())),
                                                    indent=2) + "\n", encoding="utf-8")
    files = sorted(OUT.glob("*.csv")) + [OUT / "parameters.json"]
    manifest = dict(protocol="configs/future_A/p5_hmm.json", protocol_sha256=E.sha256(PROTOCOL), test_read=False,
                    git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=E.ROOT, text=True).strip(),
                    python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                    simulation_check_passed=sim["passed"], elapsed_seconds=round(time.time() - started, 1),
                    outputs={p.name: E.sha256(p) for p in files})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(models.to_string(index=False))
    print(persistence.to_string(index=False))
    print(switching.to_string(index=False))
    print(corr.to_string(index=False))
    print(f"P5 done in {time.time() - started:.1f}s", flush=True)

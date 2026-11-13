"""Task B workflow: RFM -> 12 candidates -> rule-based selection -> profile, random groups,
sensitivity checks -> output files."""

import json

import matplotlib
matplotlib.use("Agg")  # save figures without a display (WSL, servers)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

from .evaluation import bootstrap_ari, describe_candidate, select_candidate
from .features import build_rfm, feature_matrix, load_profile_orders
from .methods import METHODS, fit_predict


def run(experiment, orders_path, root, bootstrap_repeats=None):
    cfg = experiment["clustering"]
    cutoff = experiment["profile"]["end_exclusive"]
    seed = cfg["seed"]
    method_args = {"n_init": cfg["n_init"], "score_bins": cfg["rfm_score_bins"]}
    repeats = bootstrap_repeats or cfg["bootstrap_repeats"]

    # Steps 1-2: RFM and standardized features (profile period only)
    rfm = build_rfm(load_profile_orders(orders_path), cutoff)
    X = feature_matrix(rfm)
    print(f"Profile customers: {len(rfm)}")

    # Steps 3-4: evidence for every method x candidate k
    rows, labels_by_candidate = [], {}
    for method in cfg["candidate_methods"]:
        for k in cfg["candidate_k"]:
            labels = fit_predict(method, X, k, seed, **method_args)
            stability = bootstrap_ari(method, X, k, labels, seed, repeats, **method_args)
            rows.append(describe_candidate(method, k, X, labels, rfm, stability))
            labels_by_candidate[(method, k)] = labels
            print(f"  {method:<9} k={k}  silhouette={rows[-1]['silhouette']:.3f}  ARI={stability[0]:.3f}")
    candidates, chosen = select_candidate(pd.DataFrame(rows), cfg["selection_rule"])
    method, k = chosen["method"], int(chosen["k"])
    labels = labels_by_candidate[(method, k)]
    print(f"Selected: {method}, k={k}")

    # Step 5: cluster profile table
    profile = cluster_profile(rfm, labels)
    # Step 6: size-matched random groups (shuffling the real labels keeps every group size identical)
    control = experiment["random_control"]
    random_groups = pd.concat(
        pd.DataFrame({
            "customer_id": rfm.index,
            "random_group_id": np.random.default_rng(s).permutation(labels),
            "seed": s,
        })
        for s in range(control["seed"], control["seed"] + control["repeats"])
    )
    # Step 7: sensitivity - agreement with the selected labels under alternative features
    variants = {"monetary_net": feature_matrix(rfm, monetary="monetary_net"),
                "log_recency": feature_matrix(rfm, log_recency=True)}
    sensitivity = pd.DataFrame([
        {"variant": name, "method": method, "k": k,
         "ari_vs_selected": round(adjusted_rand_score(labels, fit_predict(method, Xv, k, seed, **method_args)), 4)}
        for name, Xv in variants.items()
    ])

    # Step 8: write outputs. Customer-level files go to data/processed/local/ (git-ignored);
    # summary tables and figures go to results/
    local, tables, figures = (root / p for p in ("data/processed/local", "results/tables", "results/figures"))
    for folder in (local, tables, figures):
        folder.mkdir(parents=True, exist_ok=True)
    clusters = rfm[["recency", "frequency", "monetary"]].round(4).assign(
        cluster_id=labels, fitted_until=cutoff, method=method, k=k)
    clusters.reset_index()[["customer_id", "cluster_id", "recency", "frequency", "monetary",
                            "fitted_until", "method", "k"]].to_csv(local / "customer_clusters.csv", index=False)
    random_groups.to_csv(local / "random_groups.csv", index=False)
    candidates.to_csv(tables / "clustering_candidates.csv", index=False)
    profile.to_csv(tables / "clustering_profile.csv")
    sensitivity.to_csv(tables / "clustering_sensitivity.csv", index=False)
    plot_profiles(rfm, labels, X, figures)
    plot_heatmap(rfm, labels, X, cfg.get("cluster_names", {}), figures)
    summary = {"selected_method": method, "selected_k": k, "fitted_until": cutoff,
               "n_customers": len(rfm), "bootstrap_repeats": repeats,
               "selection_rule": cfg["selection_rule"], "cluster_sizes": chosen["cluster_sizes"]}
    (tables / "clustering_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return candidates, profile, sensitivity


def cluster_profile(rfm, labels):
    """Per cluster: size, share, R/F/M medians and quartiles, mean basket size, profile baskets."""
    grouped = rfm.groupby(labels)
    q = lambda p: (lambda s: s.quantile(p))
    profile = grouped.agg(
        customers=("recency", "size"),
        recency_median=("recency", "median"), recency_q1=("recency", q(.25)), recency_q3=("recency", q(.75)),
        frequency_median=("frequency", "median"), frequency_q3=("frequency", q(.75)),
        monetary_median=("monetary", "median"), monetary_q1=("monetary", q(.25)), monetary_q3=("monetary", q(.75)),
        mean_basket_size=("mean_basket_size", "mean"),
        profile_baskets=("profile_baskets", "sum"),
    )
    profile.insert(1, "share", profile["customers"] / len(rfm))
    profile.index.name = "cluster_id"
    return profile.round(2)


def plot_profiles(rfm, labels, X, folder):
    """Two figures: R/F/M box plots by cluster, and a snake plot of standardized cluster means."""
    groups = sorted(np.unique(labels))
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    for ax, (column, title, log) in zip(axes, [("recency", "Recency (days)", False),
                                              ("frequency", "Frequency (orders)", True),
                                              ("monetary", "Monetary (GBP)", True)]):
        ax.boxplot([rfm.loc[labels == g, column] for g in groups], showfliers=False)
        ax.set_xticks(range(1, len(groups) + 1), [f"C{g}" for g in groups])
        ax.set_title(title)
        if log:
            ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(folder / "clustering_rfm_boxplots.png", dpi=200)
    plt.close(fig)

    means = pd.DataFrame(X, columns=["Recency", "log Frequency", "log Monetary"]).groupby(labels).mean()
    fig, ax = plt.subplots(figsize=(6, 3.6))
    for g, row in means.iterrows():
        ax.plot(row.index, row.values, marker="o", label=f"C{g} (n={np.sum(labels == g)})")
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set_ylabel("Standardized mean")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(folder / "clustering_snake_plot.png", dpi=200)
    plt.close(fig)


def plot_heatmap(rfm, labels, X, names, folder):
    """Heatmap for naming clusters: cells show real medians, colour shows better or worse
    than the customer average.

    Colour = cluster mean of the standardized score (R inverted so that recent counts as
    better), clipped to +/-1.5: red = below average, grey = about average, blue = above.
    Mean basket size is not a clustering feature and is shown for reference only.
    """
    from matplotlib.colors import LinearSegmentedColormap

    size_z = (rfm["mean_basket_size"] - rfm["mean_basket_size"].mean()) / rfm["mean_basket_size"].std()
    score = pd.DataFrame({"r": -X[:, 0], "f": X[:, 1], "m": X[:, 2], "s": size_z.to_numpy()}).groupby(labels).mean()
    median = rfm.groupby(labels)[["recency", "frequency", "monetary", "mean_basket_size"]].median()
    groups = sorted(np.unique(labels), reverse=True)  # highest-value cluster on top
    columns = ["Recency\n(days, lower = more recent)", "Frequency\n(orders)", "Monetary\n(GBP)",
               "Avg basket size\n(items, not clustered)"]
    formats = ["{:.0f}", "{:.0f}", "{:,.0f}", "{:.0f}"]

    cmap = LinearSegmentedColormap.from_list("worse_better", ["#e34948", "#f0efec", "#2a78d6"])
    fig, ax = plt.subplots(figsize=(8.4, 1.2 + 0.75 * len(groups)))
    image = ax.imshow(score.loc[groups].to_numpy(), cmap=cmap, vmin=-1.5, vmax=1.5, aspect="auto")
    for i, g in enumerate(groups):
        for j, column in enumerate(median.columns):
            z = score.loc[g].iloc[j]
            ax.text(j, i, formats[j].format(median.loc[g, column]), ha="center", va="center",
                    fontsize=11, color="white" if abs(z) > 1.0 else "#1a1a19")
    ax.set_xticks(range(len(columns)), columns, fontsize=9)
    ax.set_yticks(range(len(groups)),
                  [f"C{g} {names.get(str(g), '')} (n={np.sum(labels == g)})".replace("  ", " ") for g in groups])
    ax.tick_params(which="both", length=0)
    ax.set_xticks(np.arange(-0.5, len(columns)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(groups)), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)  # white gaps between cells
    for spine in ax.spines.values():
        spine.set_visible(False)
    bar = fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02, ticks=[-1.5, 0, 1.5])
    bar.ax.set_yticklabels(["Worse than\naverage", "Average", "Better than\naverage"], fontsize=8)
    bar.outline.set_visible(False)
    ax.set_title("Cluster profile: median values (cell text) vs. customer average (colour)", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(folder / "clustering_heatmap.png", dpi=200)
    plt.close(fig)

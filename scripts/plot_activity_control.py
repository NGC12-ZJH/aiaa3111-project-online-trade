#!/usr/bin/env python3
"""Figure for the activity-matched control: random distributions vs the real RFM groups.

Usage (after run_activity_control.py):  python scripts/plot_activity_control.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "results/tables/activity_control"
s = pd.read_csv(T / "system_metrics.csv")
real = s[s.grouping.eq("real")].iloc[0]
controls = [("S_size_only", "S: head count\n(20 seeds)"), ("A1_profile_frequency", "A1: + profile\norders (100)"),
            ("A2_discovery_baskets", "A2: + Discovery\nbaskets (100)")]
panels = [("rest_bc_len2", "Group vs rest difference\n(Bray-Curtis, 2-category)"),
          ("pair_bc_len2", "Between-group difference\n(Bray-Curtis, 2-category)"),
          ("coverage_B50", "Fixed budget B=50\norder coverage")]
RANDOM, REAL, INK, MUTED = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e"
fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
rng = np.random.default_rng(0)
for ax, (metric, title) in zip(axes, panels):
    for i, (name, _) in enumerate(controls):
        v = s[s.grouping.eq(name)][metric].to_numpy()
        ax.boxplot(v, positions=[i], widths=0.45, showfliers=False,
                   medianprops=dict(color=INK, lw=1.5), boxprops=dict(color=MUTED), whiskerprops=dict(color=MUTED),
                   capprops=dict(color=MUTED))
        ax.scatter(i + rng.uniform(-.15, .15, len(v)), v, s=10, color=RANDOM, alpha=.45, lw=0, zorder=3)
        p = (1 + (v >= real[metric] - 1e-12).sum()) / (1 + len(v))
        ax.annotate(f"p={p:.2f}", (i, 1.0), xycoords=("data", "axes fraction"), ha="center", va="top",
                    fontsize=9, color=MUTED)
    allv = np.r_[s[s.grouping.isin([c[0] for c in controls])][metric].to_numpy(), real[metric]]
    lo, hi = allv.min(), allv.max()
    ax.set_ylim(lo - .05 * (hi - lo), hi + .22 * (hi - lo))
    ax.axhline(real[metric], color=REAL, lw=2, zorder=4)
    ax.set_xticks(range(3), [c[1] for c in controls], fontsize=8.5)
    ax.set_title(title, fontsize=10.5, color=INK)
    ax.set_xlim(-.6, 2.6)
    ax.grid(axis="y", color="#e6e5e0", lw=.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
axes[2].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
from matplotlib.lines import Line2D
fig.legend([Line2D([], [], color=REAL, lw=2), Line2D([], [], marker="o", ls="", color=RANDOM, alpha=.6, ms=4)],
           ["real RFM groups (C0/C1/C2)", "one random control seed"], loc="lower right", ncol=2, frameon=False,
           fontsize=8.5)
fig.text(.01, .015, "One-sided empirical p = (1 + #random >= real)/(1 + seeds). "
         "Discovery period only, taxonomy_v1 categories.", fontsize=8, color=MUTED)
fig.tight_layout(rect=(0, .04, 1, 1))
out = ROOT / "results/figures/activity_control_real_vs_random.png"
fig.savefig(out, dpi=200)
print(out)

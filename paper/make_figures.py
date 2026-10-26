#!/usr/bin/env python3
"""Generate simple, print-style figures for the hybrid-CPU paper."""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Liberation Serif", "Nimbus Roman", "Times New Roman"],
    "font.size": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "axes.linewidth": 0.6,
    "axes.edgecolor": "#222222",
    "xtick.color": "#222222",
    "ytick.color": "#222222",
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "savefig.dpi": 400,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

BLACK = "#111111"
GRAY = "#777777"
LIGHT = "#d9d9d9"


def load():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "analysis", "distribution_data.csv"))))
    a = np.array([int(r["exp_a_p999"]) for r in rows], dtype=float)
    b = np.array([int(r["exp_b_p999"]) for r in rows], dtype=float)
    return a, b


def fig_ecdf(a, b):
    fig, ax = plt.subplots(figsize=(3.35, 2.25))

    xa = np.sort(a)
    ya = np.arange(1, len(xa) + 1) / len(xa)
    xb = np.sort(b)
    yb = np.arange(1, len(xb) + 1) / len(xb)

    ax.step(xa, ya, where="post", color=BLACK, lw=1.2,
            label="Floating (CPUs 0–17)")
    ax.step(xb, yb, where="post", color=GRAY, lw=1.2, ls=(0, (3, 1.6)),
            label="E-pool (CPUs 12–17)")

    ax.set_xscale("log")
    ax.set_xlim(65, 3400)
    ax.set_ylim(0, 1.02)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0", "0.25", "0.50", "0.75", "1.0"])
    ax.set_xlabel("Per-run p99.9 wakeup latency (µs, log scale)")
    ax.set_ylabel("Empirical CDF")

    ax.grid(axis="y", color="0.90", lw=0.4)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    ax.axvline(1000, color="0.45", lw=0.5, ls=(0, (2, 2)))
    ax.text(1000, 1.025, "1 ms", color="0.35", fontsize=6.2, ha="center",
            va="bottom", clip_on=False)

    ax.legend(loc="lower right", frameon=False, handlelength=2.2,
              borderpad=0.15, labelspacing=0.3)
    fig.tight_layout(pad=0.15)
    out = os.path.join(FIG, "fig1_ecdf.png")
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_box(a, b):
    fig, ax = plt.subplots(figsize=(3.35, 2.25))
    rng = np.random.default_rng(7)

    for vals, pos, face, edge, label in (
        (a, 1, "white", BLACK, "Floating\n(0–17)"),
        (b, 2, "0.93", "#444444", "E-pool\n(12–17)"),
    ):
        bp = ax.boxplot(
            [vals], positions=[pos], widths=0.22, patch_artist=True,
            showfliers=False, whis=1.5,
            boxprops=dict(facecolor=face, edgecolor=edge, linewidth=0.7),
            medianprops=dict(color=BLACK, linewidth=1.2),
            whiskerprops=dict(color=edge, linewidth=0.6),
            capprops=dict(color=edge, linewidth=0.6),
        )
        jitter = rng.uniform(-0.10, 0.10, size=len(vals))
        ax.scatter(np.full(len(vals), pos) + jitter, vals, s=7,
                   facecolors=edge, edgecolors="none", alpha=0.55, zorder=4)

        med = float(np.median(vals))
        ax.text(pos + 0.15, med, f"{med:.0f}", ha="left", va="center",
                fontsize=6.5, color=edge)

    ax.set_yscale("log")
    ax.set_ylim(60, 3600)
    ax.set_xlim(0.42, 2.62)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Floating\n(0–17)", "E-pool\n(12–17)"])
    ax.tick_params(axis="x", pad=3)
    ax.set_ylabel("Per-run p99.9 wakeup latency (µs, log)")
    ax.grid(axis="y", color="0.90", lw=0.4)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    ax.axhline(1000, color="0.45", lw=0.5, ls=(0, (2, 2)))
    ax.text(2.63, 1030, "1 ms", ha="right", va="bottom", fontsize=6.2, color="0.35")

    fig.tight_layout(pad=0.15)
    out = os.path.join(FIG, "fig2_box.png")
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_timeline():
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(3.35, 2.30),
        gridspec_kw={"height_ratios": [1.0, 0.95], "hspace": 0.62},
    )
    y = 1.0
    h = 0.34

    # (a) full 2.9 ms timeline
    ax1.add_patch(Rectangle((-12, y - h / 2), 19, h, facecolor=LIGHT,
                            edgecolor="0.55", lw=0.4))
    ax1.add_patch(Rectangle((7, y - h / 2), 2804, h, facecolor=BLACK,
                            edgecolor="none"))
    ax1.add_patch(Rectangle((2811, y - h / 2), 5, h, facecolor="0.55",
                            edgecolor="none"))
    ax1.add_patch(Rectangle((2816, y - h / 2), 184, h, facecolor=GRAY,
                            edgecolor="none"))
    ax1.text(1400, y, "pid 834", color="white", ha="center", va="center", fontsize=6.4)
    ax1.text(2908, y, "833", color="white", ha="center", va="center", fontsize=5.8)

    ax1.annotate("", xy=(4, y - 0.31), xytext=(2816, y - 0.31),
                 arrowprops=dict(arrowstyle="<->", lw=0.5, color=BLACK))
    ax1.text(1410, y - 0.43, "pid 833 queued 2812 µs", ha="center", va="top", fontsize=6.3)

    ax1.text(8, y + 0.40, "two wakeups, 4 µs apart", fontsize=6.1, va="bottom")
    ax1.plot([0, 0], [y + h / 2, y + 0.31], color=BLACK, lw=0.6, ls=(0, (1.5, 1.5)))
    ax1.plot([4, 4], [y + h / 2, y + 0.31], color=BLACK, lw=0.6, ls=(0, (1.5, 1.5)))

    ax1.set_xlim(-20, 3010)
    ax1.set_ylim(0.10, 1.85)
    ax1.set_yticks([])
    ax1.set_xlabel("Time from first wakeup (µs)", labelpad=1)
    ax1.set_title("(a) CPU 15, full event", fontsize=7.0, pad=3)
    for s in ("top", "right", "left"):
        ax1.spines[s].set_visible(False)
    ax1.tick_params(axis="x", labelsize=6.4)

    # (b) 25 us zoom
    ax2.add_patch(Rectangle((-1, y - h / 2), 8, h, facecolor=LIGHT,
                            edgecolor="0.55", lw=0.4))
    ax2.add_patch(Rectangle((7, y - h / 2), 25, h, facecolor=BLACK,
                            edgecolor="none"))
    ax2.text(3.4, y, "idle", color="0.35", ha="center", va="center", fontsize=5.4)
    ax2.text(19, y, "pid 834", color="white", ha="center", va="center", fontsize=5.8)

    ax2.annotate("wake 834", xy=(0, y + h / 2), xytext=(9.0, y + 0.62),
                 fontsize=6.0, va="center",
                 arrowprops=dict(arrowstyle="-|>", lw=0.45, color=BLACK,
                                 shrinkA=0, shrinkB=1.2, mutation_scale=4.5))
    ax2.annotate("wake 833 (+4 µs)", xy=(4, y + h / 2), xytext=(9.0, y + 0.35),
                 fontsize=6.0, va="center",
                 arrowprops=dict(arrowstyle="-|>", lw=0.45, color=BLACK,
                                 shrinkA=0, shrinkB=1.2, mutation_scale=4.5))
    ax2.annotate("switch-in 7 µs", xy=(7, y - h / 2), xytext=(9.0, y - 0.52),
                 fontsize=5.9, va="center",
                 arrowprops=dict(arrowstyle="-|>", lw=0.45, color="0.35",
                                 shrinkA=0, shrinkB=1.0, mutation_scale=4.5))

    ax2.set_xlim(-1, 26)
    ax2.set_ylim(0.10, 1.80)
    ax2.set_yticks([])
    ax2.set_xlabel("Time from first wakeup (µs)", labelpad=1)
    ax2.set_title("(b) first 25 µs", fontsize=7.0, pad=3)
    for s in ("top", "right", "left"):
        ax2.spines[s].set_visible(False)
    ax2.tick_params(axis="x", labelsize=6.4)

    fig.subplots_adjust(left=0.04, right=0.99, top=0.94, bottom=0.13)
    out = os.path.join(FIG, "fig3_collision.png")
    fig.savefig(out)
    plt.close(fig)
    return out


if __name__ == "__main__":
    a, b = load()
    for path in (fig_ecdf(a, b), fig_box(a, b), fig_timeline()):
        print(path)

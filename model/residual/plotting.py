"""Publication-style diagnostic plot for the FL + TabM pilot."""
from pathlib import Path


def plot_pilot(output):
    import matplotlib.pyplot as plt
    import pandas as pd

    output = Path(output)
    metrics = pd.read_csv(output / "metrics.csv")
    test = metrics.loc[metrics.partition.eq("test")].copy()
    stages = ["07", "65", "81", "89"]
    methods = ["pbm", "bias", "tabm"]
    labels = ["FL", "FL + bias", "FL + TabM"]
    colors = ["#4C78A8", "#F2CF5B", "#59A14F"]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), sharey=True)
    for ax, stage in zip(axes.flat, stages):
        row = test.loc[test.BBCH.astype(str).str.zfill(2).eq(stage)].set_index("method")
        values = [float(row.loc[m, "site_balanced_mae"]) for m in methods]
        ax.bar(labels, values, color=colors, edgecolor="black", linewidth=.5)
        ax.set_title(f"BBCH {stage}", fontsize=12)
        ax.set_ylabel("Site-balanced MAE (days)")
        ax.tick_params(axis="x", labelrotation=20, labelsize=9)
        ax.grid(axis="y", color="#dddddd", linewidth=.5)
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output / "test_mae_by_stage.pdf", bbox_inches="tight")
    fig.savefig(output / "test_mae_by_stage.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    improvement = pd.read_csv(output / "improvement.csv")
    improvement = improvement.loc[improvement.method.eq("tabm")].copy()
    improvement["BBCH"] = improvement.BBCH.astype(str).str.zfill(2)
    improvement = improvement.set_index("BBCH").reindex(stages).reset_index()
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    y = range(len(stages))
    x = improvement.mae_improvement_days.to_numpy(float)
    lower = x - improvement.ci_low.to_numpy(float)
    upper = improvement.ci_high.to_numpy(float) - x
    ax.axvline(0, color="#333333", linewidth=1.0)
    ax.errorbar(x, list(y), xerr=[lower, upper], fmt="o", markersize=7,
                color="#2F5597", ecolor="#2F5597", capsize=4, linewidth=1.5)
    ax.set_yticks(list(y), [f"BBCH {stage}" for stage in stages])
    ax.invert_yaxis()
    ax.set_xlabel("Paired test MAE improvement (days)\n(FL MAE − FL + TabM MAE)")
    ax.set_title("FL + TabM residual-learning improvement", fontsize=13)
    ax.grid(axis="x", color="#dddddd", linewidth=.6)
    ax.set_axisbelow(True)
    for yi, value in zip(y, x):
        ax.text(value + .18, yi, f"{value:.2f}", va="center", fontsize=10)
    fig.tight_layout()
    fig.savefig(output / "tabm_improvement_by_stage.pdf", bbox_inches="tight")
    fig.savefig(output / "tabm_improvement_by_stage.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

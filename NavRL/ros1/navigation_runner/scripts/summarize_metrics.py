#!/usr/bin/env python3
"""
Summarize and plot NavRL evaluation metrics.

Input CSV columns (from eval_metrics_node.py):
timestamp,run_name,success,time_to_goal_sec,min_clearance_m,mean_speed_mps,mean_acc_cmd_mps2,max_acc_cmd_mps2

Outputs:
- summary CSV: outputs/metrics_summary.csv
- plots under: outputs/plots/
"""

import argparse
import csv
import math
import os
import statistics
from collections import defaultdict

import matplotlib.pyplot as plt


NUM_FIELDS = [
    "time_to_goal_sec",
    "min_clearance_m",
    "mean_speed_mps",
    "mean_acc_cmd_mps2",
    "max_acc_cmd_mps2",
]


def to_float(x):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def infer_group(run_name: str) -> str:
    # e.g. ours_run1 -> ours, no_safety_run3 -> no_safety
    lower = run_name.lower()
    if "_run" in lower:
        return lower.split("_run")[0]
    return lower


def mean_std(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], 0.0
    return statistics.mean(vals), statistics.stdev(vals)


def save_bar(values_by_group, title, ylabel, out_path):
    groups = list(values_by_group.keys())
    vals = [values_by_group[g] for g in groups]
    plt.figure(figsize=(8, 4.5))
    plt.bar(groups, vals)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def save_box(data_by_group, title, ylabel, out_path):
    groups = []
    data = []
    for g, vals in data_by_group.items():
        clean = [v for v in vals if v is not None]
        if clean:
            groups.append(g)
            data.append(clean)
    if not data:
        return
    plt.figure(figsize=(8, 4.5))
    plt.boxplot(data, labels=groups, showmeans=True)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def save_scatter_per_run(rows, metric, title, ylabel, out_path):
    groups = sorted({r["group"] for r in rows})
    plt.figure(figsize=(9, 4.8))
    for g in groups:
        ys = [r[metric] for r in rows if r["group"] == g and r[metric] is not None]
        xs = list(range(1, len(ys) + 1))
        if ys:
            plt.plot(xs, ys, marker="o", linestyle="-", label=g)
    plt.title(title)
    plt.xlabel("run index in group")
    plt.ylabel(ylabel)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "outputs", "eval_metrics.csv")),
        help="Path to eval_metrics.csv",
    )
    parser.add_argument(
        "--outdir",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "outputs")),
        help="Output directory for summary and plots",
    )
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        raise FileNotFoundError(f"metrics csv not found: {args.csv}")

    os.makedirs(args.outdir, exist_ok=True)
    plot_dir = os.path.join(args.outdir, "plots")
    os.makedirs(plot_dir, exist_ok=True)

    rows = []
    with open(args.csv, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            run_name = r.get("run_name", "").strip()
            if not run_name:
                continue
            parsed = {
                "run_name": run_name,
                "group": infer_group(run_name),
                "success": int(float(r.get("success", "0") or 0)),
            }
            for k in NUM_FIELDS:
                parsed[k] = to_float(r.get(k, ""))
            rows.append(parsed)

    if not rows:
        raise RuntimeError("no valid rows in csv")

    by_group = defaultdict(list)
    for r in rows:
        by_group[r["group"]].append(r)

    summary_csv = os.path.join(args.outdir, "metrics_summary.csv")
    with open(summary_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "group",
                "num_runs",
                "success_rate",
                "time_to_goal_mean",
                "time_to_goal_std",
                "min_clearance_mean",
                "min_clearance_std",
                "mean_speed_mean",
                "mean_speed_std",
                "mean_acc_mean",
                "mean_acc_std",
                "max_acc_mean",
                "max_acc_std",
            ]
        )
        for g, rs in sorted(by_group.items()):
            n = len(rs)
            succ = sum(r["success"] for r in rs) / max(1, n)
            t_m, t_s = mean_std([r["time_to_goal_sec"] for r in rs])
            c_m, c_s = mean_std([r["min_clearance_m"] for r in rs])
            v_m, v_s = mean_std([r["mean_speed_mps"] for r in rs])
            a_m, a_s = mean_std([r["mean_acc_cmd_mps2"] for r in rs])
            am_m, am_s = mean_std([r["max_acc_cmd_mps2"] for r in rs])
            w.writerow([g, n, succ, t_m, t_s, c_m, c_s, v_m, v_s, a_m, a_s, am_m, am_s])

    # Plots
    success_rate = {
        g: sum(r["success"] for r in rs) / max(1, len(rs))
        for g, rs in sorted(by_group.items())
    }
    save_bar(success_rate, "Success Rate by Group", "success rate", os.path.join(plot_dir, "01_success_rate.png"))

    save_box(
        {g: [r["time_to_goal_sec"] for r in rs] for g, rs in sorted(by_group.items())},
        "Time To Goal Distribution",
        "seconds",
        os.path.join(plot_dir, "02_time_to_goal_boxplot.png"),
    )
    save_box(
        {g: [r["min_clearance_m"] for r in rs] for g, rs in sorted(by_group.items())},
        "Minimum Clearance Distribution",
        "meters",
        os.path.join(plot_dir, "03_min_clearance_boxplot.png"),
    )
    save_box(
        {g: [r["mean_speed_mps"] for r in rs] for g, rs in sorted(by_group.items())},
        "Mean Speed Distribution",
        "m/s",
        os.path.join(plot_dir, "04_mean_speed_boxplot.png"),
    )
    save_box(
        {g: [r["mean_acc_cmd_mps2"] for r in rs] for g, rs in sorted(by_group.items())},
        "Mean Command Acceleration Distribution",
        "m/s^2",
        os.path.join(plot_dir, "05_mean_acc_boxplot.png"),
    )
    save_scatter_per_run(
        rows,
        "time_to_goal_sec",
        "Time To Goal per Run",
        "seconds",
        os.path.join(plot_dir, "06_time_to_goal_per_run.png"),
    )
    save_scatter_per_run(
        rows,
        "min_clearance_m",
        "Minimum Clearance per Run",
        "meters",
        os.path.join(plot_dir, "07_min_clearance_per_run.png"),
    )

    print(f"[ok] summary csv: {summary_csv}")
    print(f"[ok] plots dir   : {plot_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generate expected/mock metrics for presentation placeholder.

IMPORTANT:
- This script creates SYNTHETIC (expected) results, not real experiment output.
- Use only for draft slides / demo placeholder.
"""

import argparse
import csv
import os
import random
import subprocess
import sys
from datetime import datetime, timedelta


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def sample_run(cfg):
    success = 1 if random.random() < cfg["success_rate"] else 0
    if success:
        t = random.gauss(cfg["time_mean_ok"], cfg["time_std_ok"])
        t = clamp(t, cfg["time_ok_min"], cfg["time_ok_max"])
    else:
        # Failed runs usually hit timeout-ish durations in this setup
        t = random.gauss(cfg["time_mean_fail"], cfg["time_std_fail"])
        t = clamp(t, cfg["time_fail_min"], cfg["time_fail_max"])

    min_clearance = random.gauss(cfg["clearance_mean"], cfg["clearance_std"])
    min_clearance = clamp(min_clearance, cfg["clearance_min"], cfg["clearance_max"])

    mean_speed = random.gauss(cfg["speed_mean"], cfg["speed_std"])
    mean_speed = clamp(mean_speed, cfg["speed_min"], cfg["speed_max"])

    mean_acc = random.gauss(cfg["mean_acc_mean"], cfg["mean_acc_std"])
    mean_acc = clamp(mean_acc, cfg["mean_acc_min"], cfg["mean_acc_max"])

    max_acc = random.gauss(cfg["max_acc_mean"], cfg["max_acc_std"])
    max_acc = max(max_acc, mean_acc + 1.5)
    max_acc = clamp(max_acc, cfg["max_acc_min"], cfg["max_acc_max"])

    return {
        "success": success,
        "time_to_goal_sec": round(t, 3),
        "min_clearance_m": round(min_clearance, 3),
        "mean_speed_mps": round(mean_speed, 6),
        "mean_acc_cmd_mps2": round(mean_acc, 6),
        "max_acc_cmd_mps2": round(max_acc, 6),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--runs_per_group", type=int, default=10)
    parser.add_argument(
        "--out_csv",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "outputs", "expected_eval_metrics.csv")
        ),
    )
    parser.add_argument(
        "--out_dir",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "outputs", "expected")),
    )
    args = parser.parse_args()

    random.seed(args.seed)
    os.makedirs(os.path.dirname(args.out_csv), exist_ok=True)
    os.makedirs(args.out_dir, exist_ok=True)

    # Static cylinder-grid scene: plausible expected ranges for presentation.
    groups = {
        "ours": {
            "success_rate": 0.90,
            "time_mean_ok": 34.0,
            "time_std_ok": 4.0,
            "time_ok_min": 26.0,
            "time_ok_max": 46.0,
            "time_mean_fail": 90.0,
            "time_std_fail": 6.0,
            "time_fail_min": 75.0,
            "time_fail_max": 110.0,
            "clearance_mean": 0.48,
            "clearance_std": 0.08,
            "clearance_min": 0.28,
            "clearance_max": 0.75,
            "speed_mean": 0.44,
            "speed_std": 0.05,
            "speed_min": 0.30,
            "speed_max": 0.60,
            "mean_acc_mean": 0.50,
            "mean_acc_std": 0.08,
            "mean_acc_min": 0.30,
            "mean_acc_max": 0.80,
            "max_acc_mean": 11.5,
            "max_acc_std": 2.0,
            "max_acc_min": 7.0,
            "max_acc_max": 18.0,
        },
        "no_safety": {
            "success_rate": 0.62,
            "time_mean_ok": 45.0,
            "time_std_ok": 7.0,
            "time_ok_min": 30.0,
            "time_ok_max": 70.0,
            "time_mean_fail": 95.0,
            "time_std_fail": 7.0,
            "time_fail_min": 78.0,
            "time_fail_max": 115.0,
            "clearance_mean": 0.19,
            "clearance_std": 0.07,
            "clearance_min": 0.05,
            "clearance_max": 0.40,
            "speed_mean": 0.47,
            "speed_std": 0.06,
            "speed_min": 0.28,
            "speed_max": 0.65,
            "mean_acc_mean": 0.58,
            "mean_acc_std": 0.10,
            "mean_acc_min": 0.35,
            "mean_acc_max": 0.95,
            "max_acc_mean": 18.0,
            "max_acc_std": 3.0,
            "max_acc_min": 10.0,
            "max_acc_max": 30.0,
        },
        "no_dynamic": {
            "success_rate": 0.73,
            "time_mean_ok": 41.0,
            "time_std_ok": 6.0,
            "time_ok_min": 28.0,
            "time_ok_max": 62.0,
            "time_mean_fail": 93.0,
            "time_std_fail": 6.0,
            "time_fail_min": 77.0,
            "time_fail_max": 112.0,
            "clearance_mean": 0.33,
            "clearance_std": 0.08,
            "clearance_min": 0.12,
            "clearance_max": 0.58,
            "speed_mean": 0.42,
            "speed_std": 0.05,
            "speed_min": 0.28,
            "speed_max": 0.58,
            "mean_acc_mean": 0.53,
            "mean_acc_std": 0.09,
            "mean_acc_min": 0.32,
            "mean_acc_max": 0.86,
            "max_acc_mean": 14.0,
            "max_acc_std": 2.5,
            "max_acc_min": 8.5,
            "max_acc_max": 23.0,
        },
    }

    header = [
        "timestamp",
        "run_name",
        "success",
        "time_to_goal_sec",
        "min_clearance_m",
        "mean_speed_mps",
        "mean_acc_cmd_mps2",
        "max_acc_cmd_mps2",
    ]

    t0 = datetime.now() - timedelta(minutes=args.runs_per_group * len(groups))
    rows = []
    for g_name, cfg in groups.items():
        for i in range(1, args.runs_per_group + 1):
            sample = sample_run(cfg)
            rows.append(
                {
                    "timestamp": (t0 + timedelta(minutes=len(rows))).strftime("%Y-%m-%d %H:%M:%S"),
                    "run_name": f"{g_name}_run{i}",
                    **sample,
                }
            )

    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)

    # Reuse existing summarizer for summary + plots
    summarizer = os.path.abspath(os.path.join(os.path.dirname(__file__), "summarize_metrics.py"))
    subprocess.run(
        [
            sys.executable,
            summarizer,
            "--csv",
            args.out_csv,
            "--outdir",
            args.out_dir,
        ],
        check=True,
    )

    note_path = os.path.join(args.out_dir, "README_EXPECTED.txt")
    with open(note_path, "w") as f:
        f.write(
            "This folder contains EXPECTED/MOCK metrics generated for presentation placeholder.\n"
            "Do NOT claim these numbers as real experimental results.\n"
            f"Source csv: {args.out_csv}\n"
        )

    print(f"[ok] expected csv      : {args.out_csv}")
    print(f"[ok] expected outputs  : {args.out_dir}")
    print(f"[ok] note              : {note_path}")


if __name__ == "__main__":
    main()

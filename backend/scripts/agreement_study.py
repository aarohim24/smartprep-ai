"""
SmartPrep AI - Human-LLM Agreement Study
==========================================
Run this script offline to measure how well the LLM grader aligns with human scores.
Computes Spearman rank correlation and weighted Cohen's kappa.

Usage:
    cd backend
    python scripts/agreement_study.py --input scripts/sample_annotations.csv --output scripts/agreement_report.md

Requirements:
    pip install scipy pandas matplotlib
"""
import argparse
import asyncio
import sys
import os
import json
from pathlib import Path

# Add parent dir so app imports work when run from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

from app.utils.config import settings
from app.services.llm_service import llm_service


def weighted_cohens_kappa(y1: list, y2: list, bins=5) -> float:
    """Compute weighted Cohen's kappa with quadratic weights for continuous scores."""
    y1 = np.array(y1)
    y2 = np.array(y2)
    # Discretize into bins
    y1_bin = np.digitize(y1, np.linspace(0, 10, bins + 1)[1:-1])
    y2_bin = np.digitize(y2, np.linspace(0, 10, bins + 1)[1:-1])
    n = len(y1_bin)
    n_cats = bins
    conf = np.zeros((n_cats, n_cats))
    for a, b in zip(y1_bin, y2_bin):
        conf[a - 1, b - 1] += 1

    # Quadratic weights
    w = np.zeros((n_cats, n_cats))
    for i in range(n_cats):
        for j in range(n_cats):
            w[i, j] = ((i - j) ** 2) / ((n_cats - 1) ** 2)

    p_o = np.sum((1 - w) * conf / n)
    row_sums = conf.sum(axis=1, keepdims=True) / n
    col_sums = conf.sum(axis=0, keepdims=True) / n
    expected = row_sums @ col_sums
    p_e = np.sum((1 - w) * expected)
    if p_e == 1:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


async def score_all(df: pd.DataFrame) -> list:
    """Call the LLM evaluator for each row in the annotations CSV."""
    results = []
    for i, row in df.iterrows():
        print(f"  Scoring row {i + 1}/{len(df)}: {str(row.get('question', ''))[:50]}...")
        try:
            result = await llm_service.evaluate_answer(
                question=row["question"],
                user_answer=row["answer"],
                resume_context=row.get("resume_context", ""),
                category=row.get("category", "General"),
                mode=row.get("mode", "behavioral"),
            )
            llm_score = float(result.get("score", 5.0))
        except Exception as e:
            print(f"  ⚠️  Evaluation failed for row {i + 1}: {e}")
            llm_score = None
        results.append(llm_score)
    return results


def generate_report(df: pd.DataFrame, output_path: str):
    human_mean = df[["human_score_1", "human_score_2", "human_score_3"]].mean(axis=1)
    llm_scores = df["llm_score"]

    # Drop rows where LLM failed
    valid = df.dropna(subset=["llm_score"])
    human_valid = valid[["human_score_1", "human_score_2", "human_score_3"]].mean(axis=1)
    llm_valid = valid["llm_score"]

    spearman_r, spearman_p = spearmanr(human_valid, llm_valid)
    kappa = weighted_cohens_kappa(human_valid.tolist(), llm_valid.tolist())
    mae = float(np.mean(np.abs(human_valid - llm_valid)))
    n_valid = len(valid)
    n_total = len(df)

    # Inter-annotator agreement (human vs human)
    h1, h2, h3 = valid["human_score_1"], valid["human_score_2"], valid["human_score_3"]
    iaa_r1, _ = spearmanr(h1, h2)
    iaa_r2, _ = spearmanr(h1, h3)
    iaa_r3, _ = spearmanr(h2, h3)
    iaa_mean = float(np.mean([iaa_r1, iaa_r2, iaa_r3]))

    # Scatter plot
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].scatter(human_valid, llm_valid, alpha=0.7, c="#2563eb", edgecolors="white", linewidths=0.5)
    axes[0].plot([0, 10], [0, 10], "r--", alpha=0.5, label="Perfect agreement")
    axes[0].set_xlabel("Human Mean Score")
    axes[0].set_ylabel("LLM Score")
    axes[0].set_title("Human vs LLM Score Distribution")
    axes[0].legend()
    axes[0].set_xlim(0, 10)
    axes[0].set_ylim(0, 10)

    # Error histogram
    errors = (llm_valid - human_valid).tolist()
    axes[1].hist(errors, bins=15, color="#2563eb", alpha=0.7, edgecolor="white")
    axes[1].axvline(0, color="red", linestyle="--", alpha=0.5)
    axes[1].set_xlabel("LLM Score − Human Mean")
    axes[1].set_ylabel("Count")
    axes[1].set_title("Score Error Distribution")

    plt.tight_layout()
    plot_path = str(Path(output_path).parent / "agreement_scatter.png")
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()

    # Markdown report
    report = f"""# SmartPrep AI — Human–LLM Agreement Study

## Summary

| Metric | Value |
|---|---|
| N (valid) | {n_valid} / {n_total} |
| Spearman r (Human mean vs LLM) | **{spearman_r:.3f}** (p={spearman_p:.4f}) |
| Weighted Cohen's κ | **{kappa:.3f}** |
| Mean Absolute Error | **{mae:.2f}** / 10 |
| Human–human IAA (avg Spearman r) | {iaa_mean:.3f} |

## Interpretation

- Spearman r ≥ 0.7 = strong agreement, ≥ 0.5 = moderate agreement
- Weighted κ ≥ 0.6 = substantial agreement (Landis & Koch scale)
- Human–human IAA is the ceiling; LLM agreement should approach it

## Per-Row Results

| # | Category | Human Mean | LLM Score | |Error| |
|---|---|---|---|---|
{chr(10).join(
    f"| {i+1} | {row.get('category','?')} | {human_mean.iloc[i]:.1f} | {row['llm_score']:.1f} | {abs(human_mean.iloc[i] - row['llm_score']):.1f} |"
    for i, (_, row) in enumerate(valid.iterrows())
)}

## Scatter Plot

![Agreement scatter plot](agreement_scatter.png)

## Notes

- Human scores from 2–3 independent annotators (0–10 scale, matching LLM rubric)
- Low-confidence flags from LLM were not excluded from this analysis
- Run with: `python scripts/agreement_study.py`
"""

    Path(output_path).write_text(report, encoding="utf-8")
    print(f"\n✅ Report written to {output_path}")
    print(f"📊 Scatter plot written to {plot_path}")
    print(f"\n   Spearman r = {spearman_r:.3f}  |  κ = {kappa:.3f}  |  MAE = {mae:.2f}")


async def main(input_path: str, output_path: str, dry_run: bool = False):
    print(f"📂 Loading annotations from {input_path}")
    df = pd.read_csv(input_path)

    required_cols = {"question", "answer", "human_score_1", "human_score_2", "human_score_3"}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"❌ Missing columns: {missing}")
        sys.exit(1)

    print(f"📋 {len(df)} rows loaded")

    if dry_run:
        print("🔍 Dry run — skipping LLM calls, using random scores")
        df["llm_score"] = np.random.uniform(3, 9, len(df))
    else:
        print("🤖 Calling LLM evaluator...")
        llm_scores = await score_all(df)
        df["llm_score"] = llm_scores

    generate_report(df, output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Human–LLM Agreement Study")
    parser.add_argument("--input", default="scripts/sample_annotations.csv")
    parser.add_argument("--output", default="scripts/agreement_report.md")
    parser.add_argument("--dry-run", action="store_true", help="Use random scores instead of calling LLM")
    args = parser.parse_args()

    asyncio.run(main(args.input, args.output, args.dry_run))

"""
Weekly Improvement Report — Automated self-improvement analytics.

Reads local trace files, analyzes patterns, and generates a structured
Markdown report surfacing:
- Top failure patterns (what prompts/tools keep failing)
- Token spend and cost trends
- Quality score distribution
- Most/least used tools and routes
- Actionable improvement recommendations

Usage:
    # CLI
    python -m src.observability.weekly_report

    # Python
    from src.observability.weekly_report import generate_weekly_report
    report = generate_weekly_report(days_back=7)
"""
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("observability.weekly_report")


def generate_weekly_report(
    days_back: int = 7,
    trace_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> str:
    """
    Generate a weekly improvement report from local trace data.

    Args:
        days_back: Number of days to analyze
        trace_dir: Path to trace directory (default: PROJECT_ROOT/traces/)
        output_dir: Where to save the report (default: PROJECT_ROOT/memory/)

    Returns:
        The report as a Markdown string
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    tdir = Path(trace_dir) if trace_dir else project_root / "traces"
    odir = Path(output_dir) if output_dir else project_root / "memory"

    # Read traces
    from src.observability.tracer import read_traces
    traces = read_traces(days_back=days_back, trace_dir=str(tdir))

    if not traces:
        report = _empty_report()
        _save_report(report, odir)
        return report

    # Analyze
    stats = _analyze_traces(traces)
    report = _format_report(stats, days_back)
    _save_report(report, odir)

    logger.info("[Report] Generated weekly report: %d traces analyzed", len(traces))
    return report


def _analyze_traces(traces: list[dict]) -> dict:
    """Extract stats from trace data."""
    stats = {
        "total_traces": len(traces),
        "total_tokens": 0,
        "total_cost": 0.0,
        "routes": Counter(),
        "scores": [],
        "durations_ms": [],
        "errors": [],
        "tools_used": Counter(),
        "models_used": Counter(),
        "iterations_distribution": Counter(),
        "failed_traces": 0,
        "events_by_type": Counter(),
    }

    for trace in traces:
        # Route distribution
        route = trace.get("route", "unknown")
        stats["routes"][route] += 1

        # Token/cost totals
        stats["total_tokens"] += trace.get("total_tokens", 0)
        stats["total_cost"] += trace.get("total_cost_usd", 0.0)

        # Quality scores
        score = trace.get("final_score")
        if score is not None:
            stats["scores"].append(score)

        # Duration
        duration = trace.get("duration_ms", 0)
        if duration:
            stats["durations_ms"].append(duration)

        # Events analysis
        for event in trace.get("events", []):
            event_type = event.get("event_type", "unknown")
            stats["events_by_type"][event_type] += 1

            if event.get("model"):
                stats["models_used"][event["model"]] += 1

            if event_type == "tool":
                stats["tools_used"][event.get("name", "unknown")] += 1

            if event.get("status") == "error":
                stats["errors"].append({
                    "name": event.get("name", "unknown"),
                    "error": event.get("error", "")[:200],
                    "trace_id": trace.get("trace_id", ""),
                })

            stats["total_tokens"] += event.get("tokens_total", 0)
            stats["total_cost"] += event.get("cost_usd", 0.0)

        # Check for failed traces
        has_error = any(e.get("status") == "error" for e in trace.get("events", []))
        if has_error:
            stats["failed_traces"] += 1

    return stats


def _format_report(stats: dict, days_back: int) -> str:
    """Format analysis stats into a Markdown report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Weekly Improvement Report — {now}",
        f"_Analyzing {stats['total_traces']} traces from the last {days_back} days_\n",
    ]

    # --- Overview ---
    lines.append("## Overview\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total traces | {stats['total_traces']} |")
    lines.append(f"| Failed traces | {stats['failed_traces']} |")

    success_rate = ((stats['total_traces'] - stats['failed_traces']) / max(stats['total_traces'], 1)) * 100
    lines.append(f"| Success rate | {success_rate:.0f}% |")
    lines.append(f"| Total tokens | {stats['total_tokens']:,} |")
    lines.append(f"| Total cost | ${stats['total_cost']:.2f} |")

    if stats["scores"]:
        avg_score = sum(stats["scores"]) / len(stats["scores"])
        lines.append(f"| Avg quality score | {avg_score:.1f}/10 |")
        lines.append(f"| Min/Max score | {min(stats['scores'])}/{max(stats['scores'])} |")

    if stats["durations_ms"]:
        avg_dur = sum(stats["durations_ms"]) / len(stats["durations_ms"])
        lines.append(f"| Avg duration | {avg_dur/1000:.1f}s |")

    lines.append("")

    # --- Route Distribution ---
    if stats["routes"]:
        lines.append("## Route Distribution\n")
        for route, count in stats["routes"].most_common():
            pct = (count / stats['total_traces']) * 100
            bar = "█" * int(pct / 5)
            lines.append(f"- **{route}**: {count} ({pct:.0f}%) {bar}")
        lines.append("")

    # --- Model Usage ---
    if stats["models_used"]:
        lines.append("## Model Usage\n")
        for model, count in stats["models_used"].most_common(5):
            lines.append(f"- `{model}`: {count} calls")
        lines.append("")

    # --- Tool Usage ---
    if stats["tools_used"]:
        lines.append("## Tool Usage\n")
        for tool, count in stats["tools_used"].most_common():
            lines.append(f"- `{tool}`: {count} calls")
        lines.append("")

    # --- Error Patterns ---
    if stats["errors"]:
        lines.append("## ⚠️ Error Patterns\n")
        error_names = Counter(e["name"] for e in stats["errors"])
        for name, count in error_names.most_common(5):
            lines.append(f"### `{name}` — {count} failures")
            # Show sample errors
            samples = [e for e in stats["errors"] if e["name"] == name][:2]
            for s in samples:
                lines.append(f"- {s['error']}")
            lines.append("")

    # --- Improvement Recommendations ---
    lines.append("## 💡 Improvement Recommendations\n")
    recs = _generate_recommendations(stats)
    for i, rec in enumerate(recs, 1):
        lines.append(f"{i}. {rec}")
    lines.append("")

    # --- Score Trend ---
    if len(stats["scores"]) >= 3:
        lines.append("## Score Trend\n")
        mid = len(stats["scores"]) // 2
        first_half = sum(stats["scores"][:mid]) / mid
        second_half = sum(stats["scores"][mid:]) / (len(stats["scores"]) - mid)
        trend = "📈 Improving" if second_half > first_half else "📉 Declining" if second_half < first_half else "➡️ Stable"
        lines.append(f"- First half avg: {first_half:.1f} → Second half avg: {second_half:.1f} ({trend})")
        lines.append("")

    return "\n".join(lines)


def _generate_recommendations(stats: dict) -> list[str]:
    """Generate actionable improvement recommendations from stats."""
    recs = []

    # High failure rate
    if stats["total_traces"] > 0:
        fail_rate = stats["failed_traces"] / stats["total_traces"]
        if fail_rate > 0.3:
            recs.append(
                f"**High failure rate ({fail_rate:.0%})**. Review error patterns above and "
                "consider adding more robust error handling or adjusting prompts."
            )

    # Low quality scores
    if stats["scores"]:
        avg = sum(stats["scores"]) / len(stats["scores"])
        if avg < 6:
            recs.append(
                f"**Low average quality score ({avg:.1f}/10)**. The Engineer's system prompt "
                "may need refinement. Consider adding more specific examples of desired output format."
            )

    # Token bloat
    if stats["total_traces"] > 0:
        avg_tokens = stats["total_tokens"] / stats["total_traces"]
        if avg_tokens > 10000:
            recs.append(
                f"**High token usage ({avg_tokens:,.0f} avg/trace)**. Consider: "
                "shorter system prompts, tighter context retrieval, or using smaller models for simpler routes."
            )

    # Unused tools
    if not stats["tools_used"]:
        recs.append(
            "**No tool calls recorded**. The agent may not be leveraging Perplexity/Pinecone "
            "for context. Verify tool integrations are wired correctly."
        )

    # Dominant error source
    if stats["errors"]:
        error_names = Counter(e["name"] for e in stats["errors"])
        top_error, top_count = error_names.most_common(1)[0]
        if top_count >= 3:
            recs.append(
                f"**Recurring failures in `{top_error}` ({top_count}x)**. "
                "This tool/node needs focused debugging or fallback improvement."
            )

    if not recs:
        recs.append("No critical issues detected. Keep iterating! 🚀")

    return recs


def _empty_report() -> str:
    """Generate a report when no traces exist."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""# Weekly Improvement Report — {now}

No traces found. Run the orchestrator to start generating data:

```bash
python src/orchestrator.py "Your query here"
```

Traces are stored in `traces/` as JSONL files.
"""


def _save_report(report: str, output_dir: Path):
    """Save report to the memory directory."""
    output_dir.mkdir(exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d")
    report_path = output_dir / f"weekly-report-{now}.md"

    try:
        report_path.write_text(report, encoding="utf-8")
        logger.info("[Report] Saved to %s", report_path)
    except Exception as e:
        logger.error("[Report] Failed to save: %s", e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    report = generate_weekly_report(days_back=days)
    print(report)

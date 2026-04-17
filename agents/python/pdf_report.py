from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from agents.python import paper_broker
from agents.python.benchmark import get_comparison
from config.settings import settings


def _equity_chart(equity_history: list[dict]) -> bytes:
    if not equity_history:
        return b""

    timestamps = [datetime.fromisoformat(p["timestamp"].replace("Z", "")) for p in equity_history]
    values = [p["equity"] for p in equity_history]

    fig, ax = plt.subplots(figsize=(8, 3.5), dpi=100)
    ax.plot(timestamps, values, color="#6366f1", linewidth=2)
    ax.fill_between(timestamps, values, alpha=0.15, color="#6366f1")
    ax.set_title("Equity Curve", fontsize=12, fontweight="bold")
    ax.set_ylabel("USD")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _drawdown_chart(equity_history: list[dict]) -> bytes:
    if not equity_history:
        return b""

    timestamps = [datetime.fromisoformat(p["timestamp"].replace("Z", "")) for p in equity_history]
    values = [p["equity"] for p in equity_history]

    drawdowns = []
    peak = values[0]
    for v in values:
        peak = max(peak, v)
        dd = (peak - v) / peak * 100 if peak else 0
        drawdowns.append(-dd)

    fig, ax = plt.subplots(figsize=(8, 2.5), dpi=100)
    ax.fill_between(timestamps, drawdowns, 0, color="#ef4444", alpha=0.3)
    ax.plot(timestamps, drawdowns, color="#ef4444", linewidth=1.5)
    ax.set_title("Drawdown %", fontsize=11, fontweight="bold")
    ax.set_ylabel("%")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def generate_report(output_path: Path | None = None) -> Path:
    output_path = output_path or (settings.data_dir / f"performance_report_{datetime.now().strftime('%Y%m%d')}.pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    account = paper_broker.get_account()
    positions = paper_broker.list_positions()
    stats = paper_broker.get_trade_stats()
    equity_history = paper_broker.get_equity_history(limit=10000)

    try:
        benchmark = get_comparison()
    except Exception:
        benchmark = {}

    doc = SimpleDocTemplate(str(output_path), pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#1a2234"), spaceAfter=10
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=20
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontSize=14, textColor=colors.HexColor("#1a2234"), spaceAfter=8, spaceBefore=15
    )

    elements = []
    elements.append(Paragraph("Stock Trader — Performance Report", title_style))
    elements.append(Paragraph(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", subtitle_style))

    total_pl = account["equity"] - account["initial_deposit"]
    total_pl_pct = total_pl / account["initial_deposit"] * 100 if account["initial_deposit"] else 0

    summary_data = [
        ["Metric", "Value"],
        ["Initial Capital", f"${account['initial_deposit']:,.2f}"],
        ["Current Equity", f"${account['equity']:,.2f}"],
        ["Total P/L", f"${total_pl:+,.2f} ({total_pl_pct:+.2f}%)"],
        ["Cash", f"${account['cash']:,.2f}"],
        ["Open Positions", str(len(positions))],
    ]

    if stats["total_trades"] > 0:
        summary_data.extend(
            [
                ["Total Trades", str(stats["total_trades"])],
                ["Win Rate", f"{stats['win_rate'] * 100:.1f}%"],
                ["Wins / Losses", f"{stats['wins']} / {stats['losses']}"],
                ["Average Win", f"${stats['avg_win']:,.2f}"],
                ["Average Loss", f"${stats['avg_loss']:,.2f}"],
            ]
        )

    if benchmark and not benchmark.get("error"):
        summary_data.extend(
            [
                ["Portfolio Return", f"{benchmark.get('portfolio_return_pct', 0):+.2f}%"],
                ["SPY Return", f"{benchmark.get('benchmark_return_pct', 0):+.2f}%"],
                ["Alpha", f"{benchmark.get('alpha_pct', 0):+.2f}%"],
                ["Beta", f"{benchmark.get('beta', 0):.3f}"],
            ]
        )

    elements.append(Paragraph("Executive Summary", h2_style))
    summary_table = Table(summary_data, colWidths=[6 * cm, 6 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ]
        )
    )
    elements.append(summary_table)

    equity_png = _equity_chart(equity_history)
    if equity_png:
        elements.append(Paragraph("Equity Curve", h2_style))
        elements.append(Image(io.BytesIO(equity_png), width=16 * cm, height=7 * cm))

    drawdown_png = _drawdown_chart(equity_history)
    if drawdown_png:
        elements.append(Paragraph("Drawdown Analysis", h2_style))
        elements.append(Image(io.BytesIO(drawdown_png), width=16 * cm, height=5 * cm))

    if positions:
        elements.append(Paragraph("Open Positions", h2_style))
        pos_data = [["Symbol", "Qty", "Entry", "Current", "P/L $", "P/L %"]]
        for p in positions:
            pl = p.get("unrealized_pl", 0)
            plpc = p.get("unrealized_plpc", 0) * 100
            pos_data.append(
                [
                    p["symbol"],
                    str(p["qty"]),
                    f"${p['avg_entry']:.2f}",
                    f"${p.get('current_price', p['avg_entry']):.2f}",
                    f"${pl:+,.2f}",
                    f"{plpc:+.2f}%",
                ]
            )
        pos_table = Table(pos_data, colWidths=[2.5 * cm, 2 * cm, 2.5 * cm, 2.5 * cm, 3 * cm, 2.5 * cm])
        pos_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ]
            )
        )
        elements.append(pos_table)

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Methodology", h2_style))
    elements.append(
        Paragraph(
            "This portfolio is managed by a 17-agent multi-agent AI system using Gemma 4 E2B and Qwen 3 4B models. "
            "Trading decisions are made through a pipeline including technical analysis, news sentiment, sector rotation, "
            "fundamental data, momentum, volatility, pattern recognition, multi-timeframe analysis, and bull-vs-bear debate. "
            "Risk management includes ATR-based stop losses, Kelly criterion position sizing, drawdown circuit breakers, "
            "and signal reversal exits. All trades include slippage (0.05%) and commissions ($1-10/trade).",
            styles["Normal"],
        )
    )

    doc.build(elements)
    return output_path

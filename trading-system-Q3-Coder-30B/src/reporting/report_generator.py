"""
Email Report Generator.

Creates HTML email reports with:
- 30-day/YTD/lifetime performance
- Portfolio status per fund
- Top 10 recommendations per fund
- Equity curves, allocation charts
- Risk metrics comparison
"""

import base64
import io
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from loguru import logger

from src.utils import (
    load_config, fmt_pct, fmt_currency, fmt_number,
    save_parquet, load_parquet,
)
from src.analysis.strategies import StrategyEngine
from src.analysis.risk_metrics import RiskMetrics
from src.collector.paper_portfolio import PaperPortfolioManager
from src.collector.price_fetcher import PriceFetcher


class ReportGenerator:
    """Generates HTML email reports with embedded charts."""

    def __init__(self):
        self.config = load_config()
        self.strategy = StrategyEngine()
        self.risk_calc = RiskMetrics()
        self.max_recs = self.config.get("email", {}).get("max_recommendations", 10)

    # ------------------------------------------------------------------
    # Main Report
    # ------------------------------------------------------------------
    def generate_report(self) -> str:
        """
        Generate the full morning email report as HTML.
        Returns HTML string ready for sending.
        """
        logger.info("Generating email report...")

        # Gather data
        portfolio_mgr = PaperPortfolioManager()
        summaries = portfolio_mgr.get_all_summaries()

        fund_sections = []
        for fund_name in self.config.get("funds", {}):
            section = self._generate_fund_section(fund_name, portfolio_mgr)
            fund_sections.append(section)

        # Build report
        report_date = date.today().strftime("%B %d, %Y")
        html = self._render_html(report_date, summaries, fund_sections)

        logger.info("Report generated successfully")
        return html

    def _generate_fund_section(self, fund_name: str, portfolio_mgr: PaperPortfolioManager) -> Dict:
        """Generate data for one fund's report section."""
        fund_cfg = self.config["funds"][fund_name]
        portfolio = portfolio_mgr.get_portfolio(fund_name)
        summary = portfolio.get_portfolio_summary()
        positions = portfolio.get_positions()

        # Get recommendations
        top_buys = self.strategy.get_top_buys(fund_name, self.max_recs)
        top_sells = self.strategy.get_top_sells(fund_name, self.max_recs)

        # Generate charts
        equity_chart = self._generate_equity_chart(fund_name)
        allocation_chart = self._generate_allocation_chart(positions, fund_cfg["name"])

        return {
            "fund_name": fund_cfg["name"],
            "fund_key": fund_name,
            "summary": summary,
            "positions": positions.to_dict("records") if not positions.empty else [],
            "top_buys": top_buys,
            "top_sells": top_sells,
            "equity_chart": equity_chart,
            "allocation_chart": allocation_chart,
        }

    # ------------------------------------------------------------------
    # Chart Generation
    # ------------------------------------------------------------------
    def _generate_equity_chart(self, fund_name: str) -> str:
        """Generate equity curve chart as base64 PNG."""
        daily_values = load_parquet("portfolios", f"daily_values_{fund_name}")
        backtest_equity = load_parquet("backtest", f"equity_{fund_name}")

        fig, ax = plt.subplots(figsize=(8, 3.5), dpi=100)
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#1a1a2e")

        plotted = False

        if daily_values is not None and not daily_values.empty:
            daily_values["date"] = pd.to_datetime(daily_values["date"])
            ax.plot(daily_values["date"], daily_values["total_value"],
                    color="#00d4ff", linewidth=1.5, label="Live")
            plotted = True

        if backtest_equity is not None and not backtest_equity.empty:
            backtest_equity["date"] = pd.to_datetime(backtest_equity["date"])
            ax.plot(backtest_equity["date"], backtest_equity["total_value"],
                    color="#ff6b6b", linewidth=1.2, alpha=0.7, label="Backtest")
            plotted = True

        if not plotted:
            # Placeholder chart
            x = pd.date_range(end=date.today(), periods=30)
            y = 100000 + np.cumsum(np.random.randn(30) * 500)
            ax.plot(x, y, color="#00d4ff", linewidth=1.5, label="Simulated")

        ax.set_title(f"Equity Curve", fontsize=11, color="white", pad=10)
        ax.legend(fontsize=8, facecolor="#16213e", edgecolor="#16213e",
                  labelcolor="white")
        ax.tick_params(colors="white", labelsize=8)
        ax.spines["bottom"].set_color("#333")
        ax.spines["left"].set_color("#333")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.grid(True, alpha=0.15, color="white")

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _generate_allocation_chart(self, positions: pd.DataFrame, fund_name: str) -> str:
        """Generate sector allocation pie chart as base64 PNG."""
        fig, ax = plt.subplots(figsize=(4, 3.5), dpi=100)
        fig.patch.set_facecolor("#1a1a2e")

        if not positions.empty and "sector" in positions.columns and "market_value" in positions.columns:
            sector_alloc = positions.groupby("sector")["market_value"].sum()
            sector_alloc = sector_alloc[sector_alloc > 0].sort_values(ascending=False)

            if not sector_alloc.empty:
                colors = plt.cm.Set3(np.linspace(0, 1, len(sector_alloc)))
                wedges, texts, autotexts = ax.pie(
                    sector_alloc.values,
                    labels=sector_alloc.index,
                    colors=colors,
                    autopct="%1.0f%%",
                    pctdistance=0.8,
                    textprops={"fontsize": 7, "color": "white"},
                )
                for t in autotexts:
                    t.set_fontsize(6)
                    t.set_color("white")
            else:
                ax.text(0.5, 0.5, "No Positions", ha="center", va="center",
                        color="white", fontsize=12, transform=ax.transAxes)
        else:
            ax.text(0.5, 0.5, "No Positions", ha="center", va="center",
                    color="white", fontsize=12, transform=ax.transAxes)

        ax.set_title("Sector Allocation", fontsize=10, color="white", pad=8)
        plt.tight_layout()
        return self._fig_to_base64(fig)

    @staticmethod
    def _fig_to_base64(fig) -> str:
        """Convert matplotlib figure to base64 encoded PNG."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight",
                    facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    # ------------------------------------------------------------------
    # HTML Rendering
    # ------------------------------------------------------------------
    def _render_html(self, report_date: str, summaries: List[Dict],
                     fund_sections: List[Dict]) -> str:
        """Render full HTML report."""

        # Overview cards
        overview_cards = ""
        for s in summaries:
            ret_color = "#00d4ff" if s.get("total_return", 0) >= 0 else "#ff6b6b"
            overview_cards += f"""
            <div style="background:#16213e;border-radius:8px;padding:16px;flex:1;min-width:200px;margin:6px;">
                <div style="color:#888;font-size:12px;margin-bottom:4px;">{s['fund']}</div>
                <div style="color:white;font-size:22px;font-weight:bold;">{fmt_currency(s['total_value'])}</div>
                <div style="color:{ret_color};font-size:14px;">{fmt_pct(s.get('total_return', 0))} total return</div>
                <div style="color:#888;font-size:11px;margin-top:4px;">
                    {s.get('num_positions', 0)} positions | Cash: {fmt_pct(s.get('cash_pct', 0))}
                </div>
            </div>"""

        # Fund sections
        fund_html = ""
        for section in fund_sections:
            fund_html += self._render_fund_section(section)

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#0f0f23;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:800px;margin:0 auto;padding:20px;">

<!-- Header -->
<div style="text-align:center;padding:24px 0;border-bottom:1px solid #333;">
    <h1 style="color:white;margin:0;font-size:24px;">📊 Trading System Report</h1>
    <p style="color:#888;margin:8px 0 0;">{report_date}</p>
</div>

<!-- Portfolio Overview -->
<div style="margin:20px 0;">
    <h2 style="color:#00d4ff;font-size:16px;margin-bottom:12px;">Portfolio Overview</h2>
    <div style="display:flex;flex-wrap:wrap;gap:0;">{overview_cards}</div>
</div>

<!-- Fund Sections -->
{fund_html}

<!-- Footer -->
<div style="text-align:center;padding:20px 0;border-top:1px solid #333;margin-top:30px;">
    <p style="color:#666;font-size:11px;">
        Generated by Trading Analysis System | {datetime.now().strftime('%I:%M %p CT')}<br>
        Past performance does not guarantee future results.
    </p>
</div>

</div>
</body>
</html>"""

        return html

    def _render_fund_section(self, section: Dict) -> str:
        """Render HTML for a single fund section."""
        s = section["summary"]
        equity_img = section["equity_chart"]
        alloc_img = section["allocation_chart"]

        # Recommendations table
        buys_html = self._render_recommendations_table(section["top_buys"], "BUY")
        sells_html = self._render_recommendations_table(section["top_sells"], "SELL")

        # Positions table
        positions_html = self._render_positions_table(section["positions"])

        return f"""
<div style="margin:30px 0;border:1px solid #333;border-radius:10px;overflow:hidden;">
    <!-- Fund Header -->
    <div style="background:#16213e;padding:16px 20px;">
        <h2 style="color:white;margin:0;font-size:18px;">{section['fund_name']}</h2>
        <span style="color:#888;font-size:12px;">
            {fmt_currency(s['total_value'])} | {s.get('num_positions', 0)} positions
        </span>
    </div>

    <!-- Charts -->
    <div style="display:flex;flex-wrap:wrap;padding:16px;gap:16px;">
        <div style="flex:2;min-width:300px;">
            <img src="data:image/png;base64,{equity_img}" style="width:100%;border-radius:6px;" alt="Equity Curve">
        </div>
        <div style="flex:1;min-width:200px;">
            <img src="data:image/png;base64,{alloc_img}" style="width:100%;border-radius:6px;" alt="Allocation">
        </div>
    </div>

    <!-- Current Positions -->
    <div style="padding:0 20px 16px;">
        <h3 style="color:#00d4ff;font-size:14px;margin:0 0 8px;">Current Positions</h3>
        {positions_html}
    </div>

    <!-- Buy Recommendations -->
    <div style="padding:0 20px 16px;">
        <h3 style="color:#4ade80;font-size:14px;margin:0 0 8px;">Top Buy Recommendations</h3>
        {buys_html}
    </div>

    <!-- Sell Recommendations -->
    <div style="padding:0 20px 20px;">
        <h3 style="color:#ff6b6b;font-size:14px;margin:0 0 8px;">Top Sell Recommendations</h3>
        {sells_html}
    </div>
</div>"""

    def _render_recommendations_table(self, recs: List[Dict], signal_type: str) -> str:
        """Render recommendations as HTML table."""
        if not recs:
            return '<p style="color:#666;font-size:12px;">No recommendations at this time.</p>'

        color = "#4ade80" if signal_type == "BUY" else "#ff6b6b"

        rows = ""
        for r in recs[:self.max_recs]:
            conf_bar_width = int(r.get("confidence", 0) * 100)
            rows += f"""
            <tr>
                <td style="padding:6px 8px;color:white;font-weight:bold;">{r.get('ticker', '')}</td>
                <td style="padding:6px 8px;color:{color};">{r.get('signal', '')}</td>
                <td style="padding:6px 8px;color:#ccc;">{fmt_currency(r.get('entry_price', 0))}</td>
                <td style="padding:6px 8px;color:#ff6b6b;">{fmt_currency(r.get('stop_loss', 0))}</td>
                <td style="padding:6px 8px;color:#4ade80;">{fmt_currency(r.get('target_price', 0))}</td>
                <td style="padding:6px 8px;color:#ccc;">{r.get('risk_reward_ratio', 0):.1f}</td>
                <td style="padding:6px 8px;">
                    <div style="background:#333;border-radius:3px;height:12px;width:60px;">
                        <div style="background:{color};border-radius:3px;height:12px;width:{conf_bar_width}%;"></div>
                    </div>
                </td>
            </tr>"""

        return f"""
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
            <tr style="border-bottom:1px solid #333;">
                <th style="padding:6px 8px;text-align:left;color:#888;">Ticker</th>
                <th style="padding:6px 8px;text-align:left;color:#888;">Signal</th>
                <th style="padding:6px 8px;text-align:left;color:#888;">Entry</th>
                <th style="padding:6px 8px;text-align:left;color:#888;">Stop</th>
                <th style="padding:6px 8px;text-align:left;color:#888;">Target</th>
                <th style="padding:6px 8px;text-align:left;color:#888;">R:R</th>
                <th style="padding:6px 8px;text-align:left;color:#888;">Conf</th>
            </tr>
            {rows}
        </table>"""

    def _render_positions_table(self, positions: List[Dict]) -> str:
        """Render current positions as HTML table."""
        if not positions:
            return '<p style="color:#666;font-size:12px;">No open positions.</p>'

        rows = ""
        for p in positions:
            pnl_pct = p.get("unrealized_pnl_pct", 0)
            pnl_color = "#4ade80" if pnl_pct >= 0 else "#ff6b6b"
            rows += f"""
            <tr>
                <td style="padding:5px 8px;color:white;font-weight:bold;">{p.get('ticker', '')}</td>
                <td style="padding:5px 8px;color:#ccc;">{p.get('quantity', 0)}</td>
                <td style="padding:5px 8px;color:#ccc;">{fmt_currency(p.get('avg_cost', 0))}</td>
                <td style="padding:5px 8px;color:#ccc;">{fmt_currency(p.get('current_price', 0))}</td>
                <td style="padding:5px 8px;color:{pnl_color};">{fmt_currency(p.get('unrealized_pnl', 0))}</td>
                <td style="padding:5px 8px;color:{pnl_color};">{fmt_pct(pnl_pct)}</td>
            </tr>"""

        return f"""
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
            <tr style="border-bottom:1px solid #333;">
                <th style="padding:5px 8px;text-align:left;color:#888;">Ticker</th>
                <th style="padding:5px 8px;text-align:left;color:#888;">Qty</th>
                <th style="padding:5px 8px;text-align:left;color:#888;">Avg Cost</th>
                <th style="padding:5px 8px;text-align:left;color:#888;">Price</th>
                <th style="padding:5px 8px;text-align:left;color:#888;">P&L</th>
                <th style="padding:5px 8px;text-align:left;color:#888;">P&L %</th>
            </tr>
            {rows}
        </table>"""

    # ------------------------------------------------------------------
    # Save Report
    # ------------------------------------------------------------------
    def save_report(self, html: str, filename: Optional[str] = None) -> str:
        """Save HTML report to file."""
        if filename is None:
            filename = f"report_{date.today().strftime('%Y-%m-%d')}.html"

        from src.utils import get_data_dir
        report_dir = get_data_dir() / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / filename

        with open(path, "w") as f:
            f.write(html)

        logger.info(f"Report saved: {path}")
        return str(path)

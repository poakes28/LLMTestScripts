#!/usr/bin/env python3
"""
CLI Runner: Analysis Engine

Runs strategy analysis across all funds and generates recommendations.
Designed to be called by Windows Task Scheduler at 5 PM daily.

Usage:
    python scripts/analyze.py                 # Run full analysis
    python scripts/analyze.py --fund balanced # Analyze specific fund
    python scripts/analyze.py --backtest      # Run backtests
    python scripts/analyze.py --backtest --fund technical --start 2023-01-01 --end 2025-01-01
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import setup_logging
from src.analysis.strategies import StrategyEngine
from src.backtest.engine import BacktestEngine
from loguru import logger


def main():
    parser = argparse.ArgumentParser(description="Trading System Analysis Engine")
    parser.add_argument("--fund", type=str, default=None,
                        help="Specific fund to analyze (fundamental/technical/balanced)")
    parser.add_argument("--backtest", action="store_true",
                        help="Run backtests instead of live analysis")
    parser.add_argument("--start", type=str, default=None,
                        help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None,
                        help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=None,
                        help="Initial capital for backtest")
    args = parser.parse_args()

    setup_logging("analysis")
    logger.info("=" * 60)
    logger.info("ANALYSIS ENGINE STARTING")
    logger.info("=" * 60)

    try:
        if args.backtest:
            engine = BacktestEngine()

            if args.fund:
                logger.info(f"Running backtest for fund: {args.fund}")
                results = engine.run_backtest(
                    fund_name=args.fund,
                    start_date=args.start,
                    end_date=args.end,
                    initial_capital=args.capital,
                )
                _print_backtest_summary(args.fund, results)
            else:
                logger.info("Running backtests for all funds...")
                all_results = engine.run_all_backtests(
                    start_date=args.start,
                    end_date=args.end,
                    initial_capital=args.capital,
                )
                for fund_name, results in all_results.items():
                    _print_backtest_summary(fund_name, results)

        else:
            engine = StrategyEngine()
            results = engine.run_analysis()

            for fund_name, data in results.items():
                recs = data.get("recommendations", [])
                buys = [r for r in recs if r["signal"] == "BUY"]
                sells = [r for r in recs if r["signal"] == "SELL"]
                holds = [r for r in recs if r["signal"] == "HOLD"]

                logger.info(f"\n{'=' * 50}")
                logger.info(f"Fund: {data['fund_name']}")
                logger.info(f"  BUY signals:  {len(buys)}")
                logger.info(f"  SELL signals: {len(sells)}")
                logger.info(f"  HOLD signals: {len(holds)}")

                if buys:
                    logger.info(f"\n  Top 5 Buys:")
                    for b in sorted(buys, key=lambda x: x["composite_score"], reverse=True)[:5]:
                        logger.info(
                            f"    {b['ticker']:6s} | Score: {b['composite_score']:+.3f} "
                            f"| Conf: {b['confidence']:.0%} "
                            f"| Entry: ${b['entry_price']:.2f} "
                            f"| R:R {b['risk_reward_ratio']:.1f}"
                        )

        logger.info("\nAnalysis complete")

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise


def _print_backtest_summary(fund_name: str, results: Dict):
    """Print backtest summary to console."""
    if "error" in results:
        logger.error(f"Backtest failed for {fund_name}: {results['error']}")
        return

    m = results.get("metrics", {})
    bm = results.get("benchmark_metrics", {})

    logger.info(f"\n{'═' * 50}")
    logger.info(f"BACKTEST: {fund_name}")
    logger.info(f"{'═' * 50}")
    logger.info(f"  Total Return:    {m.get('total_return', 0):.2%}")
    logger.info(f"  Annual Return:   {m.get('annual_return', 0):.2%}")
    logger.info(f"  Sharpe Ratio:    {m.get('sharpe_ratio', 0):.2f}")
    logger.info(f"  Sortino Ratio:   {m.get('sortino_ratio', 0):.2f}")
    logger.info(f"  Max Drawdown:    {m.get('max_drawdown', 0):.2%}")
    logger.info(f"  Calmar Ratio:    {m.get('calmar_ratio', 0):.2f}")
    logger.info(f"  Win Rate:        {m.get('win_rate', 0):.1%}")
    logger.info(f"  Profit Factor:   {m.get('profit_factor', 0):.2f}")
    logger.info(f"  Total Trades:    {m.get('total_trades', 0)}")
    logger.info(f"  Alpha:           {m.get('alpha', 'N/A')}")
    logger.info(f"  Beta:            {m.get('beta', 'N/A')}")
    logger.info(f"  VaR (95%):       {m.get('var_95', 0):.2%}")
    logger.info(f"\n  Benchmark (SPY):")
    logger.info(f"    Total Return:  {bm.get('total_return', 0):.2%}")
    logger.info(f"    Sharpe Ratio:  {bm.get('sharpe_ratio', 0):.2f}")


if __name__ == "__main__":
    # Need this import for type hints in the function
    from typing import Dict
    main()

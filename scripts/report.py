#!/usr/bin/env python3
"""
CLI Runner: Email Reporter

Generates and sends the morning email report.
Designed to be called by Windows Task Scheduler at 6 AM.

Usage:
    python scripts/report.py              # Generate and send report
    python scripts/report.py --preview    # Generate and save locally (no email)
    python scripts/report.py --open       # Generate, save, and open in browser
"""

import sys
import os
import argparse
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import setup_logging
from src.reporting.report_generator import ReportGenerator
from src.reporting.email_sender import EmailSender
from loguru import logger


def main():
    parser = argparse.ArgumentParser(description="Trading System Email Reporter")
    parser.add_argument("--preview", action="store_true",
                        help="Save report locally without sending email")
    parser.add_argument("--open", action="store_true",
                        help="Open report in browser after generating")
    parser.add_argument("--output", type=str, default=None,
                        help="Custom output path for HTML file")
    args = parser.parse_args()

    setup_logging("reporter")
    logger.info("=" * 60)
    logger.info("EMAIL REPORTER STARTING")
    logger.info("=" * 60)

    try:
        from src.utils import load_config, load_parquet
        from src.llm.position_analyzer import PositionAnalyzer
        import pandas as pd

        settings = load_config()

        # Run LLM position analysis before building report
        llm_analyses = {}
        if settings.get("llm_analysis", {}).get("enabled", False):
            try:
                from src.collector.paper_portfolio import PaperPortfolioManager

                portfolio_mgr = PaperPortfolioManager()
                all_positions = []
                for fund_name in settings.get("funds", {}):
                    portfolio = portfolio_mgr.get_portfolio(fund_name)
                    positions = portfolio.get_positions()
                    if not positions.empty:
                        all_positions.append(positions)

                if all_positions:
                    positions_df = pd.concat(all_positions, ignore_index=True)
                    positions_df = positions_df.drop_duplicates(subset=["ticker"])
                else:
                    positions_df = pd.DataFrame()

                # Load strategy analysis from all funds and merge (tickers overlap across funds)
                all_analyses = []
                for fund_name in settings.get("funds", {}):
                    df = load_parquet("analysis", f"recommendations_{fund_name}")
                    if df is not None and not df.empty:
                        all_analyses.append(df)
                if all_analyses:
                    analysis_df = pd.concat(all_analyses, ignore_index=True)
                    analysis_df = analysis_df.drop_duplicates(subset=["ticker"])
                else:
                    analysis_df = None

                analyzer = PositionAnalyzer(settings)
                llm_analyses = analyzer.analyze_positions(positions_df, analysis_df)
                logger.info(f"LLM analysis complete: {len(llm_analyses)} positions analyzed")

            except Exception as e:
                logger.warning(f"LLM analysis failed, continuing without it: {e}")

        # Generate report
        generator = ReportGenerator()
        html = generator.generate_report(llm_analyses=llm_analyses)

        # Save locally
        if args.output:
            output_path = args.output
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(html)
        else:
            output_path = generator.save_report(html)

        logger.info(f"Report saved to: {output_path}")

        # Open in browser if requested
        if args.open:
            webbrowser.open(f"file://{os.path.abspath(output_path)}")

        # Send email (unless preview mode)
        if not args.preview:
            sender = EmailSender()
            if sender.is_configured:
                success = sender.send_report(html)
                if success:
                    logger.info("Report emailed successfully")
                else:
                    logger.warning("Email sending failed")
            else:
                logger.info("Email not configured. Report saved locally only.")
        else:
            logger.info("Preview mode - email not sent")

        logger.info("Reporting complete")

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise


if __name__ == "__main__":
    main()

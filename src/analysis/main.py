#!/usr/bin/env python

import sys
import os
from pathlib import Path
from collector.schwab_client import SchwabClient
from collector.yfinance_collector import YFinanceCollector
from collector.paper_portfolio import PaperPortfolio
from analysis.fundamental_strategy import FundamentalStrategy
from analysis.technical_strategy import TechnicalStrategy
from strategy_executor import StrategyExecutor

def main():
    try:
        # Initialize data directory (use absolute path)
        script_dir = Path(__file__).parent
        data_dir = script_dir.parent / "data"
        
        # Initialize clients and collectors with proper parameters
        schwab_client = SchwabClient()
        yfinance_collector = YFinanceCollector(symbols=['AAPL', 'GOOGL'], data_dir=str(data_dir))
        paper_portfolio = PaperPortfolio(data_dir=str(data_dir))
        fundamental_strategy = FundamentalStrategy(data_dir=str(data_dir), risk_params={'stop_loss': 0.1, 'max_position': 0.15, 'max_sector': 0.3})
        technical_strategy = TechnicalStrategy(data_dir=str(data_dir), risk_params={'stop_loss': 0.1, 'max_position': 0.15, 'max_sector': 0.3})

        # Initialize the strategy executor with all necessary components
        strategy_executor = StrategyExecutor(
            schwab_client,
            yfinance_collector,
            paper_portfolio,
            fundamental_strategy,
            technical_strategy
        )

        # Execute the strategy
        strategy_executor.execute()
        
    except Exception as e:
        print(f"Error during execution: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

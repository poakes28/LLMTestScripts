"""
Strategy Executor Module

This module coordinates the execution of trading strategies by:
1. Running analysis strategies (technical and fundamental)
2. Evaluating signals
3. Executing trades via the appropriate broker client
4. Managing portfolio positions
"""

import os
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

from collector.schwab_client import SchwabClient
from collector.paper_portfolio import PaperPortfolio
from analysis.technical_strategy import TechnicalStrategy
from analysis.fundamental_strategy import FundamentalStrategy


class StrategyExecutor:
    """
    Coordinates trading strategy execution including signal generation,
    order placement, and portfolio management.
    """
    
    def __init__(self, data_dir: str = '../data', use_real_trading: bool = False):
        """
        Initialize the strategy executor.
        
        Args:
            data_dir: Directory for storing data files
            use_real_trading: If True, uses real broker API; if False, uses paper portfolio
        """
        self.data_dir = data_dir
        self.use_real_trading = use_real_trading
        
        # Initialize clients
        if use_real_trading:
            self.broker_client = SchwabClient()
            print("Using real Schwab API client")
        else:
            self.broker_client = None
            print("Using paper portfolio (no real trades)")
        
        self.paper_portfolio = PaperPortfolio(data_dir)
        self.technical_strategy = TechnicalStrategy()
        self.fundamental_strategy = FundamentalStrategy()
        
        # Load existing portfolio if available
        self.paper_portfolio.load_portfolio()
    
    def run_analysis(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Run all analysis strategies for given symbols.
        
        Args:
            symbols: List of stock symbols to analyze
            
        Returns:
            Dictionary with analysis results for each symbol
        """
        results = {}
        
        for symbol in symbols:
            symbol_results = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'technical': {},
                'fundamental': {},
                'combined_signal': None,
                'confidence': 0.0
            }
            
            # Run technical analysis
            try:
                tech_result = self.technical_strategy.analyze(symbol, self.data_dir)
                symbol_results['technical'] = tech_result
            except Exception as e:
                symbol_results['technical']['error'] = str(e)
                print(f"Technical analysis error for {symbol}: {e}")
            
            # Run fundamental analysis
            try:
                fund_result = self.fundamental_strategy.analyze(symbol, self.data_dir)
                symbol_results['fundamental'] = fund_result
            except Exception as e:
                symbol_results['fundamental']['error'] = str(e)
                print(f"Fundamental analysis error for {symbol}: {e}")
            
            # Generate combined signal
            signal = self._generate_combined_signal(symbol_results)
            symbol_results.update(signal)
            
            results[symbol] = symbol_results
        
        return results
    
    def _generate_combined_signal(self, analysis_results: Dict) -> Dict:
        """
        Combine technical and fundamental signals into a single recommendation.
        
        Args:
            analysis_results: Results from both analysis strategies
            
        Returns:
            Dictionary with combined signal and confidence
        """
        tech = analysis_results.get('technical', {})
        fund = analysis_results.get('fundamental', {})
        
        # Extract signals (assuming values between -1 (sell) and 1 (buy))
        tech_signal = self._extract_signal(tech, 'technical')
        fund_signal = self._extract_signal(fund, 'fundamental')
        
        if tech_signal is None and fund_signal is None:
            return {
                'combined_signal': 'HOLD',
                'confidence': 0.0,
                'reason': 'No signals available'
            }
        
        # Weight technical more heavily (60% vs 40%)
        if tech_signal is not None and fund_signal is not None:
            weighted_signal = (tech_signal * 0.6) + (fund_signal * 0.4)
            confidence = min(1.0, abs(weighted_signal) + 0.2)
        elif tech_signal is not None:
            weighted_signal = tech_signal
            confidence = min(1.0, abs(tech_signal) + 0.1)
        else:
            weighted_signal = fund_signal
            confidence = min(1.0, abs(fund_signal) + 0.1)
        
        # Determine signal type
        if weighted_signal > 0.3:
            combined_signal = 'BUY'
        elif weighted_signal < -0.3:
            combined_signal = 'SELL'
        else:
            combined_signal = 'HOLD'
        
        return {
            'combined_signal': combined_signal,
            'confidence': round(confidence, 2),
            'weighted_score': round(weighted_signal, 4)
        }
    
    def _extract_signal(self, data: Dict, source: str) -> Optional[float]:
        """
        Extract a numeric signal value from analysis results.
        
        Args:
            data: Analysis results dictionary
            source: Source name for error reporting
            
        Returns:
            Signal value between -1 and 1, or None if unavailable
        """
        # Check various common formats
        signal_keys = ['signal', 'recommendation', 'score', 'value']
        
        for key in signal_keys:
            if key in data:
                val = data[key]
                if isinstance(val, (int, float)):
                    return max(-1.0, min(1.0, float(val)))
        
        # Check for dict containing numeric values
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, (int, float)):
                    return max(-1.0, min(1.0, float(v)))
        
        return None
    
    def execute_order(self, symbol: str, signal: str, quantity: int = 10) -> Dict:
        """
        Execute a trade based on the signal.
        
        Args:
            symbol: Stock symbol to trade
            signal: 'BUY', 'SELL', or 'HOLD'
            quantity: Number of shares (default 10)
            
        Returns:
            Order execution result
        """
        if signal == 'HOLD':
            return {
                'action': 'skip',
                'reason': 'No trading signal',
                'symbol': symbol,
                'timestamp': datetime.now().isoformat()
            }
        
        if self.use_real_trading and self.broker_client:
            # Real trading mode - use broker API
            try:
                order = self.broker_client.place_order(
                    account_id=self.paper_portfolio.portfolio['account_id'].iloc[0]
                    if 'account_id' in self.paper_portfolio.portfolio.columns else None,
                    symbol=symbol,
                    quantity=quantity,
                    order_type=signal
                )
                
                # Update portfolio
                if signal == 'BUY':
                    self.paper_portfolio.add_position(symbol, quantity, 
                                                      self._get_current_price(symbol))
                
                return {
                    'action': signal.lower(),
                    'order_id': order.get('order_id'),
                    'status': order.get('status'),
                    'symbol': symbol,
                    'quantity': quantity,
                    'timestamp': datetime.now().isoformat()
                }
            except Exception as e:
                return {'error': str(e), 'symbol': symbol}
        else:
            # Paper trading mode
            result = {
                'action': signal.lower(),
                'paper_trade': True,
                'symbol': symbol,
                'quantity': quantity,
                'timestamp': datetime.now().isoformat()
            }
            
            if signal == 'BUY':
                self.paper_portfolio.add_position(symbol, quantity, 
                                                  self._get_current_price(symbol))
            
            return result
    
    def _get_current_price(self, symbol: str) -> float:
        """
        Get current price for a symbol (placeholder).
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Current price
        """
        # In production, fetch from market data API
        return 100.00  # Placeholder
    
    def save_portfolio(self):
        """Save current portfolio state."""
        self.paper_portfolio.save_portfolio()
        print(f"Portfolio saved to {os.path.join(self.data_dir, 'paper_portfolio.parquet')}")
    
    def get_portfolio_summary(self) -> Dict:
        """
        Get summary of current portfolio.
        
        Returns:
            Dictionary with portfolio statistics
        """
        if self.paper_portfolio.portfolio.empty:
            return {
                'total_positions': 0,
                'total_value': 0.0,
                'positions': []
            }
        
        positions = self.paper_portfolio.portfolio.to_dict('records')
        
        return {
            'total_positions': len(positions),
            'positions': positions
        }


# Example usage
if __name__ == "__main__":
    executor = StrategyExecutor(data_dir='../data', use_real_trading=False)
    
    symbols = ['AAPL', 'GOOGL', 'MSFT']
    results = executor.run_analysis(symbols)
    
    print("\nAnalysis Results:")
    for symbol, data in results.items():
        print(f"\n{symbol}:")
        print(f"  Signal: {data.get('combined_signal')}")
        print(f"  Confidence: {data.get('confidence')}")
        
        # Execute if signal is BUY or SELL
        signal = data.get('combined_signal')
        if signal in ['BUY', 'SELL']:
            result = executor.execute_order(symbol, signal)
            print(f"  Execution: {result}")
    
    executor.save_portfolio()

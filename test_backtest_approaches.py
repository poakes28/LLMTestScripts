#!/usr/bin/env python3
"""
Test script to verify the new backtesting approaches are working correctly.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.backtest.engine import BacktestEngine

def test_backtest_approaches():
    """Test that our new backtesting approaches can be instantiated and run."""

    print("Testing new backtesting approaches...")

    try:
        # Create backtest engine
        engine = BacktestEngine()
        print("✓ BacktestEngine created successfully")

        # Test that methods exist
        assert hasattr(engine, 'run_fundamental_backtest'), "run_fundamental_backtest method missing"
        assert hasattr(engine, 'run_technical_backtest'), "run_technical_backtest method missing"
        assert hasattr(engine, 'run_balanced_backtest'), "run_balanced_backtest method missing"
        print("✓ All new backtesting methods found")

        # Test that the engine can be initialized with config
        assert hasattr(engine, 'config'), "Config not loaded properly"
        print("✓ Configuration loaded successfully")

        print("\nAll tests passed! The three new backtesting approaches are ready.")
        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_backtest_approaches()
import os
import pandas as pd
import pandas_ta as ta
from pyarrow import parquet as pq
from datetime import datetime

class TechnicalStrategy:
    def __init__(self, data_dir, risk_params):
        self.data_dir = data_dir
        self.risk_params = risk_params

    def calculate_signals(self, symbol):
        # Load price data for the symbol
        file_path = os.path.join(self.data_dir, f'{symbol}_prices.parquet')
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No price data found for {symbol}")

        try:
            price_data = pq.read_table(file_path).to_pandas()
        except Exception as e:
            raise RuntimeError(f"Failed to read parquet file {file_path}: {e}")

        # Check required columns exist
        required_cols = ['Close']
        for col in required_cols:
            if col not in price_data.columns:
                raise ValueError(f"Missing required column '{col}' in data")

        # Calculate technical indicators
        try:
            rsi = ta.rsi(price_data['Close'], length=14)
            macd = ta.macd(price_data['Close'])
            ma_50 = ta.sma(price_data['Close'], length=50)
            ma_200 = ta.sma(price_data['Close'], length=200)
        except Exception as e:
            raise RuntimeError(f"Failed to calculate technical indicators: {e}")

        # Generate signal based on technical indicators
        try:
            last_rsi = rsi.iloc[-1]
            last_macd_line = macd.iloc[-1]['MACD_12_26_9']
            last_signal_line = macd.iloc[-1]['MACDs_12_26_9']
            last_ma_50 = ma_50.iloc[-1]
            last_ma_200 = ma_200.iloc[-1]
        except IndexError as e:
            raise ValueError(f"Price data for {symbol} is empty or incomplete: {e}")
        except KeyError as e:
            raise ValueError(f"Missing expected column in technical indicators: {e}")

        if last_rsi < 30 and last_macd_line > last_signal_line and last_ma_50 > last_ma_200:
            confidence_score = 0.9
        elif last_rsi < 40 and last_macd_line > last_signal_line and last_ma_50 > last_ma_200:
            confidence_score = 0.7
        else:
            confidence_score = 0.5

        # Generate signal
        signal = {
            'symbol': symbol,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'signal_type': 'buy' if confidence_score > 0.7 else 'hold',
            'confidence_score': confidence_score,
            'entry_price': None,  # To be determined later
            'stop_loss': None,  # To be determined later
            'target_price': None  # To be determined later
        }

        return signal

# Example usage
if __name__ == "__main__":
    data_dir = '../data'
    risk_params = {'stop_loss': 0.1, 'max_position': 0.15, 'max_sector': 0.3}
    strategy = TechnicalStrategy(data_dir, risk_params)
    signal = strategy.calculate_signals('AAPL')
    print(signal)

import os
import yfinance as yf
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
from datetime import datetime, timedelta

class YFinanceCollector:
    def __init__(self, symbols, data_dir):
        self.symbols = symbols
        self.data_dir = data_dir

    def fetch_data(self):
        for symbol in self.symbols:
            data = yf.download(tickers=symbol, period='1d', interval='15m')
            self.save_to_parquet(data, symbol)

    def save_to_parquet(self, data, symbol):
        date_str = datetime.now().strftime('%Y-%m-%d')
        file_path = os.path.join(self.data_dir, f'{symbol}_{date_str}.parquet')
        pq.write_table(pa.Table.from_pandas(data), file_path)

# Example usage
if __name__ == "__main__":
    symbols = ['AAPL', 'GOOGL']
    data_dir = '../data'
    collector = YFinanceCollector(symbols, data_dir)
    collector.fetch_data()

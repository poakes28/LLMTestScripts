import os
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
from datetime import datetime

class PaperPortfolio:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.portfolio = pd.DataFrame(columns=['symbol', 'quantity', 'entry_price', 'entry_date'])

    def add_position(self, symbol, quantity, entry_price):
        entry_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_position = pd.DataFrame({
            'symbol': [symbol],
            'quantity': [quantity],
            'entry_price': [entry_price],
            'entry_date': [entry_date]
        })
        self.portfolio = pd.concat([self.portfolio, new_position], ignore_index=True)

    def save_portfolio(self):
        file_path = os.path.join(self.data_dir, 'paper_portfolio.parquet')
        pq.write_table(pa.Table.from_pandas(self.portfolio), file_path)

    def load_portfolio(self):
        file_path = os.path.join(self.data_dir, 'paper_portfolio.parquet')
        if os.path.exists(file_path):
            self.portfolio = pq.read_table(file_path).to_pandas()

# Example usage
if __name__ == "__main__":
    data_dir = '../data'
    portfolio = PaperPortfolio(data_dir)
    portfolio.load_portfolio()
    portfolio.add_position('AAPL', 10, 150.0)
    portfolio.save_portfolio()

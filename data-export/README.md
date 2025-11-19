DATA EXPORT DOCUMENTATION
==========================

This folder contains exported data and documentation for the Trade Performance Visualizer.

FILES:
------

1. account-data.json
   - Complete account data from Snaptrade API
   - Includes: accounts, positions, summary, historical reporting data
   - Source: Snaptrade connected account (Alpaca Paper)
   - Export date: See timestamp in file

2. CALCULATIONS.txt
   - Detailed equations and methodology
   - Portfolio value calculations
   - Benchmark comparison formulas
   - Dividend adjustment explanations
   - Assumptions and limitations

3. market-data/ (to be populated)
   - Individual stock price data
   - Daily adjusted close prices from yfinance
   - Format: JSON files per symbol with date/price pairs


DATA SOURCES:
------------

1. Snaptrade API:
   - Portfolio positions (current holdings)
   - Historical equity values (weekly frequency - 6 points over 30 days)
   - Account information

2. yfinance API:
   - Daily stock prices (adjusted for dividends and splits)
   - Benchmark indices (SPY, etc.)
   - Used for daily portfolio reconstruction


DAILY DATA RECONSTRUCTION:
-------------------------

The system reconstructs daily portfolio values by:
1. Getting current stock positions and quantities from Snaptrade
2. Fetching daily adjusted close prices for each stock from yfinance
3. Calculating: Portfolio_Value_d = Σ(Price_d,i × Quantity_i)

This provides daily granularity (vs. Snaptrade's weekly data) and includes:
- Dividend adjustments (via adjusted close)
- Stock split adjustments
- Daily price fluctuations


BENCHMARK CALCULATIONS:
----------------------

Benchmarks use dividend-adjusted prices (Adj Close) from yfinance:
- SPY: S&P 500 ETF with dividend reinvestment
- Comparisons normalize to same starting value for fair comparison
- Return calculations: ((Price_d - Price_0) / Price_0) × 100


TO EXPORT MARKET DATA:
---------------------

Run the export script (when available) or use the API endpoint:
GET /api/portfolio/daily?days=30&symbols=AAPL,MSFT,GOOGL

This will return daily price data for specified symbols.


NOTE:
-----
Market data is fetched in real-time from yfinance. Historical data is not
stored locally unless explicitly exported. The account-data.json contains
a snapshot of your Snaptrade account data at export time.


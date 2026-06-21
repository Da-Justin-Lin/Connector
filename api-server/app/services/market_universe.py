"""Curated universe for the market-cap MarketCarpet (treemap).

Each entry is (ticker, display name, sector, approximate shares outstanding in
millions). Live market cap is computed as ``shares * current_price`` so the
treemap needs only one batched quote download — no slow per-ticker info calls.

Share counts are approximate and only drive *relative* cell sizing; the daily
color comes from real quotes. Refresh occasionally if a name does a big
split/buyback.
"""

# (ticker, name, sector, shares_millions)
UNIVERSE: list[tuple[str, str, str, float]] = [
    # Technology
    ("AAPL", "Apple", "Technology", 14900),
    ("MSFT", "Microsoft", "Technology", 7430),
    ("NVDA", "NVIDIA", "Technology", 24600),
    ("AVGO", "Broadcom", "Technology", 4700),
    ("ORCL", "Oracle", "Technology", 2760),
    ("CRM", "Salesforce", "Technology", 970),
    ("AMD", "AMD", "Technology", 1620),
    ("ADBE", "Adobe", "Technology", 440),
    ("CSCO", "Cisco", "Technology", 4000),
    ("ACN", "Accenture", "Technology", 625),
    ("TXN", "Texas Instruments", "Technology", 910),
    ("QCOM", "Qualcomm", "Technology", 1110),
    ("IBM", "IBM", "Technology", 920),
    ("INTC", "Intel", "Technology", 4300),
    # Communication Services
    ("GOOGL", "Alphabet", "Communication Services", 12200),
    ("META", "Meta Platforms", "Communication Services", 2540),
    ("NFLX", "Netflix", "Communication Services", 430),
    ("DIS", "Disney", "Communication Services", 1810),
    ("CMCSA", "Comcast", "Communication Services", 3900),
    ("T", "AT&T", "Communication Services", 7170),
    ("VZ", "Verizon", "Communication Services", 4210),
    ("TMUS", "T-Mobile", "Communication Services", 1170),
    # Consumer Discretionary
    ("AMZN", "Amazon", "Consumer Discretionary", 10400),
    ("TSLA", "Tesla", "Consumer Discretionary", 3190),
    ("HD", "Home Depot", "Consumer Discretionary", 995),
    ("MCD", "McDonald's", "Consumer Discretionary", 720),
    ("NKE", "Nike", "Consumer Discretionary", 1510),
    ("LOW", "Lowe's", "Consumer Discretionary", 575),
    ("SBUX", "Starbucks", "Consumer Discretionary", 1135),
    ("BKNG", "Booking Holdings", "Consumer Discretionary", 33),
    ("TJX", "TJX Companies", "Consumer Discretionary", 1130),
    # Consumer Staples
    ("WMT", "Walmart", "Consumer Staples", 8050),
    ("PG", "Procter & Gamble", "Consumer Staples", 2360),
    ("KO", "Coca-Cola", "Consumer Staples", 4310),
    ("PEP", "PepsiCo", "Consumer Staples", 1375),
    ("COST", "Costco", "Consumer Staples", 443),
    ("MDLZ", "Mondelez", "Consumer Staples", 1350),
    ("PM", "Philip Morris", "Consumer Staples", 1560),
    # Financials
    ("BRK-B", "Berkshire Hathaway", "Financials", 2160),
    ("JPM", "JPMorgan Chase", "Financials", 2870),
    ("V", "Visa", "Financials", 1930),
    ("MA", "Mastercard", "Financials", 920),
    ("BAC", "Bank of America", "Financials", 7800),
    ("WFC", "Wells Fargo", "Financials", 3400),
    ("GS", "Goldman Sachs", "Financials", 330),
    ("MS", "Morgan Stanley", "Financials", 1630),
    ("AXP", "American Express", "Financials", 720),
    ("BLK", "BlackRock", "Financials", 149),
    ("C", "Citigroup", "Financials", 1910),
    # Health Care
    ("LLY", "Eli Lilly", "Health Care", 950),
    ("UNH", "UnitedHealth", "Health Care", 925),
    ("JNJ", "Johnson & Johnson", "Health Care", 2410),
    ("MRK", "Merck", "Health Care", 2530),
    ("ABBV", "AbbVie", "Health Care", 1770),
    ("PFE", "Pfizer", "Health Care", 5660),
    ("TMO", "Thermo Fisher", "Health Care", 385),
    ("ABT", "Abbott", "Health Care", 1740),
    ("DHR", "Danaher", "Health Care", 735),
    ("AMGN", "Amgen", "Health Care", 538),
    ("BMY", "Bristol-Myers Squibb", "Health Care", 2030),
    # Energy
    ("XOM", "Exxon Mobil", "Energy", 4400),
    ("CVX", "Chevron", "Energy", 1840),
    ("COP", "ConocoPhillips", "Energy", 1180),
    ("SLB", "Schlumberger", "Energy", 1430),
    ("EOG", "EOG Resources", "Energy", 570),
    ("MPC", "Marathon Petroleum", "Energy", 340),
    # Industrials
    ("GE", "GE Aerospace", "Industrials", 1080),
    ("CAT", "Caterpillar", "Industrials", 485),
    ("HON", "Honeywell", "Industrials", 650),
    ("UNP", "Union Pacific", "Industrials", 605),
    ("BA", "Boeing", "Industrials", 615),
    ("RTX", "RTX", "Industrials", 1340),
    ("UPS", "UPS", "Industrials", 855),
    ("DE", "Deere", "Industrials", 275),
    ("LMT", "Lockheed Martin", "Industrials", 237),
    # Materials
    ("LIN", "Linde", "Materials", 480),
    ("SHW", "Sherwin-Williams", "Materials", 252),
    ("APD", "Air Products", "Materials", 222),
    ("ECL", "Ecolab", "Materials", 285),
    ("FCX", "Freeport-McMoRan", "Materials", 1435),
    ("NEM", "Newmont", "Materials", 1150),
    # Utilities
    ("NEE", "NextEra Energy", "Utilities", 2055),
    ("SO", "Southern Company", "Utilities", 1095),
    ("DUK", "Duke Energy", "Utilities", 772),
    ("AEP", "American Electric Power", "Utilities", 533),
    ("D", "Dominion Energy", "Utilities", 835),
    # Real Estate
    ("PLD", "Prologis", "Real Estate", 925),
    ("AMT", "American Tower", "Real Estate", 466),
    ("EQIX", "Equinix", "Real Estate", 95),
    ("PSA", "Public Storage", "Real Estate", 175),
    ("O", "Realty Income", "Real Estate", 870),
    ("SPG", "Simon Property", "Real Estate", 326),
]

# Display order for sectors in the treemap.
SECTOR_ORDER = [
    "Technology",
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Financials",
    "Health Care",
    "Energy",
    "Industrials",
    "Materials",
    "Utilities",
    "Real Estate",
]

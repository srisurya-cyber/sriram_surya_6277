import os
import time
import threading
import logging
import requests
import yfinance as yf
import backtrader as bt
import pandas as pd
import pytz
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# === CONFIGURATION ===
RISK_PER_TRADE    = 0.015
ATR_MULTIPLIER    = 1.8
NEWS_BUFFER_MIN   = 120  # minutes around news to avoid
TRADING_HOURS_UTC = (12, 17)  # 12–17 UTC (8am–1pm New York)
SYMBOL            = 'GC=F'
DATA_INTERVAL     = '1h'
DATA_PERIOD       = '7d'

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# === Telegram via HTTP ===
def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            logger.warning(f"Telegram API error {r.status_code}: {r.text}")
    except Exception as e:
        logger.warning(f"Failed to send Telegram message: {e}")

# === News Scraper ===
def scrape_forex_factory_events():
    try:
        url = "https://www.forexfactory.com/calendar?day=today"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')

        events = []
        today = datetime.now(pytz.timezone('America/New_York')).date()
        for row in soup.select('.calendar__row.calendar__row--impact-high'):
            time_cell = row.select_one('.calendar__time')
            if time_cell and 'calendar__time--' not in time_cell.get('class', []):
                t = time_cell.text.strip()
                if t and t != 'All Day':
                    try:
                        tm = datetime.strptime(t, '%I:%M%p').time()
                        dt_local = pytz.timezone('America/New_York').localize(datetime.combine(today, tm))
                        events.append(dt_local.astimezone(pytz.utc))
                    except:
                        continue
        logger.info(f"Found {len(events)} high-impact events")
        return events
    except Exception as e:
        logger.warning(f"News scrape error: {e}")
        return []

# === Backtrader Strategy ===
class GoldStrategy(bt.Strategy):
    params = dict(
        trend_ema    = 34,
        signal_ema   = 9,
        rsi_period   = 14,
        atr_period   = 14,
        news_buffer  = timedelta(minutes=NEWS_BUFFER_MIN),
        trading_hours = TRADING_HOURS_UTC
    )

    def __init__(self):
        self.hull       = bt.ind.HMA(self.data.close, period=self.p.trend_ema)
        self.ema        = bt.ind.EMA(self.data.close, period=self.p.signal_ema)
        self.rsi        = bt.ind.RSI(self.data.close, period=self.p.rsi_period)
        self.atr        = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.truerange  = bt.ind.TrueRange(self.data)
        self.volatility = bt.ind.SMA(self.truerange, period=50)

        self.stop_price     = None
        self.entry_price    = None
        self.upcoming_news  = []
        self.last_news_date = None

    def next(self):
        now = self.data.datetime.datetime(0)
        hour = now.hour

        # Refresh news once per day
        if self.last_news_date != now.date():
            self.upcoming_news  = scrape_forex_factory_events()
            self.last_news_date = now.date()

        # Skip trading around news
        for nt in self.upcoming_news:
            if abs((nt - now).total_seconds()) <= self.p.news_buffer.total_seconds():
                logger.info(f"Skipping trade near news at {nt.time()}")
                return

        # Time filter
        if not (self.p.trading_hours[0] <= hour <= self.p.trading_hours[1]):
            return

        # Volatility filter
        if self.truerange[0] > 2.5 * self.volatility[0]:
            return

        # Position sizing
        risk_capital  = self.broker.getvalue() * RISK_PER_TRADE
        size_in_units = risk_capital / (self.atr[0] * ATR_MULTIPLIER) / self.data.close[0]

        # Entry
        if not self.position:
            if (self.data.close[0] > self.hull[0] and
                self.ema[0] > self.ema[-1] and
                self.rsi[0] < 65):
                self.buy(size=size_in_units)
                self.entry_price = self.data.close[0]
                self.stop_price  = self.entry_price - ATR_MULTIPLIER * self.atr[0]
                msg = f"🟢 BUY {SYMBOL} @ {self.entry_price:.2f}, SL {self.stop_price:.2f}"
                logger.info(msg)
                send_telegram(msg)

        # Exit
        else:
            exit_cond = [
                self.data.close[0] <= self.stop_price,
                self.rsi[0]        > 70,
                self.ema[0]       < self.ema[-1],
                self.data.close[0] < self.hull[0]
            ]
            if any(exit_cond):
                exit_price = self.data.close[0]
                pnl = (exit_price - self.entry_price) * self.position.size
                self.close()
                msg = f"🔴 SELL {SYMBOL} @ {exit_price:.2f}, PnL {pnl:.2f}"
                logger.info(msg)
                send_telegram(msg)

# === Runner Loop ===
def run_bot_loop():
    while True:
        logger.info("Fetching market data and running strategy...")
        df = yf.download(SYMBOL, period=DATA_PERIOD, interval=DATA_INTERVAL, auto_adjust=True)

        # Validate DataFrame
        if not isinstance(df, pd.DataFrame) or df.empty:
            logger.warning("Data fetch failed or empty; sleeping 1h")
            time.sleep(3600)
            continue

        # Flatten/clean columns
        cols = df.columns
        if isinstance(cols, pd.MultiIndex):
            df.columns = ['_'.join([str(x) for x in col if x]).lower() for col in cols]
        else:
            df.columns = [str(c).lower() for c in cols]

        data = bt.feeds.PandasData(dataname=df)
        cerebro = bt.Cerebro()
        cerebro.addstrategy(GoldStrategy)
        cerebro.adddata(data)
        cerebro.broker.setcash(10000)
        cerebro.broker.setcommission(commission=0.0002)
        cerebro.run()

        # Sleep until next hour + 5s
        now = datetime.now(datetime.UTC)  # instead of datetime.utcnow()
        next_run = (now + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)
        sleep_secs = (next_run - now).total_seconds()
        time.sleep(sleep_secs)

if __name__ == "__main__":
    thread = threading.Thread(target=run_bot_loop, daemon=True)
    thread.start()
    thread.join()

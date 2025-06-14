import yfinance as yf
import backtrader as bt
import pandas as pd
import pytz
import threading
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import time
import logging
import os
from telegram import Bot

RISK_PER_TRADE = 0.015 ATR_MULTIPLIER = 1.8 NEWS_BUFFER_MIN = 120 TIMEZONE = pytz.utc TRADING_HOURS_UTC = (12, 17) SYMBOL = 'GC=F'  # Gold Futures data_interval = '1h' data_period = '7d'

BOT_TOKEN = os.getenv("BOT_TOKEN") CHAT_ID = os.getenv("CHAT_ID")

logging.basicConfig(level=logging.INFO) bot = Bot(BOT_TOKEN)

def scrape_forex_factory_events(): try: url = "https://www.forexfactory.com/calendar?day=today" headers = {'User-Agent': 'Mozilla/5.0'} response = requests.get(url, headers=headers) soup = BeautifulSoup(response.text, 'html.parser')

high_impact_events = []
    today = datetime.now(pytz.timezone('America/New_York')).date()

    for row in soup.select('.calendar__row.calendar__row--impact-high'):
        time_cell = row.select_one('.calendar__time')
        if time_cell and 'calendar__time--' not in time_cell.get('class', []):
            time_str = time_cell.text.strip()
            if time_str and time_str != 'All Day':
                try:
                    event_time = datetime.strptime(time_str, '%I:%M%p').time()
                    event_dt = datetime.combine(today, event_time)
                    event_dt = pytz.timezone('America/New_York').localize(event_dt)
                    high_impact_events.append(event_dt.astimezone(pytz.utc))
                except:
                    continue

    logging.info(f"Found {len(high_impact_events)} high impact events today")
    return high_impact_events

except Exception as e:
    logging.warning(f"News scrape error: {e}")
    return []

========== STRATEGY ==========

class GoldStrategy(bt.Strategy): params = ( ('trend_ema', 34), ('signal_ema', 9), ('rsi_period', 14), ('atr_period', 14), ('news_buffer', timedelta(minutes=NEWS_BUFFER_MIN)), ('trading_hours', TRADING_HOURS_UTC) )

def __init__(self):
    self.hull = bt.ind.HullMovingAverage(period=self.p.trend_ema)
    self.ema = bt.ind.EMA(period=self.p.signal_ema)
    self.rsi = bt.ind.RSI(period=self.p.rsi_period)
    self.atr = bt.ind.ATR(period=self.p.atr_period)
    self.true_range = bt.ind.TrueRange()
    self.volatility = bt.ind.SMA(self.true_range, period=50)

    self.stop_price = None
    self.entry_price = None
    self.upcoming_news = []
    self.last_news_check = None

def next(self):
    current_dt = self.data.datetime.datetime(0)
    hour = current_dt.hour

    if self.last_news_check is None or current_dt.date() != self.last_news_check.date():
        self.upcoming_news = scrape_forex_factory_events()
        self.last_news_check = current_dt

    for news_time in self.upcoming_news:
        if abs(news_time - current_dt) <= self.p.news_buffer:
            logging.info(f"News nearby at {news_time}, skipping trade")
            return

    if not (self.p.trading_hours[0] <= hour <= self.p.trading_hours[1]):
        return

    if self.true_range[0] > 2.5 * self.volatility[0]:
        return

    risk_capital = self.broker.getvalue() * RISK_PER_TRADE
    position_size = risk_capital / (self.atr[0] * ATR_MULTIPLIER)

    if not self.position:
        if (self.data.close[0] > self.hull[0] and
            self.ema[0] > self.ema[-1] and
            self.rsi[0] < 65):
            self.buy(size=position_size / self.data.close[0])
            self.stop_price = self.data.close[0] - (self.atr[0] * ATR_MULTIPLIER)
            self.entry_price = self.data.close[0]
            msg = f"🟢 BUY at {self.entry_price:.2f}, SL: {self.stop_price:.2f}"
            logging.info(msg)
            bot.send_message(chat_id=CHAT_ID, text=msg)

    else:
        exit_conditions = [
            self.data.close[0] <= self.stop_price,
            self.rsi[0] > 70,
            self.ema[0] < self.ema[-2],
            self.data.close[0] < self.hull[0]
        ]
        if any(exit_conditions):
            self.close()
            pnl = self.data.close[0] - self.entry_price
            msg = f"🔴 CLOSE at {self.data.close[0]:.2f} | PnL: {pnl:.2f}"
            logging.info(msg)
            bot.send_message(chat_id=CHAT_ID, text=msg)

========== RUN BACKTEST (LIVE LOOP) ==========

def run_backtest_live(): while True: cerebro = bt.Cerebro()

logging.info("Fetching market data...")
    df = yf.download(SYMBOL, period=data_period, interval=data_interval)
    df.columns = [c.lower() for c in df.columns]
    data = bt.feeds.PandasData(dataname=df)

    cerebro.adddata(data)
    cerebro.addstrategy(GoldStrategy)
    cerebro.broker.setcash(10000)
    cerebro.broker.setcommission(commission=0.0002)

    cerebro.run()
    time.sleeimport yfinance as yf
import backtrader as bt
import pandas as pd
import pytz
import threading
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import time
import logging
import os
from telegram import Bot

RISK_PER_TRADE = 0.015 ATR_MULTIPLIER = 1.8 NEWS_BUFFER_MIN = 120 TIMEZONE = pytz.utc TRADING_HOURS_UTC = (12, 17) SYMBOL = 'GC=F'  # Gold Futures data_interval = '1h' data_period = '7d'

BOT_TOKEN = os.getenv("BOT_TOKEN") CHAT_ID = os.getenv("CHAT_ID")

logging.basicConfig(level=logging.INFO) bot = Bot(BOT_TOKEN)

def scrape_forex_factory_events(): try: url = "https://www.forexfactory.com/calendar?day=today" headers = {'User-Agent': 'Mozilla/5.0'} response = requests.get(url, headers=headers) soup = BeautifulSoup(response.text, 'html.parser')

high_impact_events = []
    today = datetime.now(pytz.timezone('America/New_York')).date()

    for row in soup.select('.calendar__row.calendar__row--impact-high'):
        time_cell = row.select_one('.calendar__time')
        if time_cell and 'calendar__time--' not in time_cell.get('class', []):
            time_str = time_cell.text.strip()
            if time_str and time_str != 'All Day':
                try:
                    event_time = datetime.strptime(time_str, '%I:%M%p').time()
                    event_dt = datetime.combine(today, event_time)
                    event_dt = pytz.timezone('America/New_York').localize(event_dt)
                    high_impact_events.append(event_dt.astimezone(pytz.utc))
                except:
                    continue

    logging.info(f"Found {len(high_impact_events)} high impact events today")
    return high_impact_events

except Exception as e:
    logging.warning(f"News scrape error: {e}")
    return []

========== STRATEGY ==========

class GoldStrategy(bt.Strategy): params = ( ('trend_ema', 34), ('signal_ema', 9), ('rsi_period', 14), ('atr_period', 14), ('news_buffer', timedelta(minutes=NEWS_BUFFER_MIN)), ('trading_hours', TRADING_HOURS_UTC) )

def __init__(self):
    self.hull = bt.ind.HullMovingAverage(period=self.p.trend_ema)
    self.ema = bt.ind.EMA(period=self.p.signal_ema)
    self.rsi = bt.ind.RSI(period=self.p.rsi_period)
    self.atr = bt.ind.ATR(period=self.p.atr_period)
    self.true_range = bt.ind.TrueRange()
    self.volatility = bt.ind.SMA(self.true_range, period=50)

    self.stop_price = None
    self.entry_price = None
    self.upcoming_news = []
    self.last_news_check = None

def next(self):
    current_dt = self.data.datetime.datetime(0)
    hour = current_dt.hour

    if self.last_news_check is None or current_dt.date() != self.last_news_check.date():
        self.upcoming_news = scrape_forex_factory_events()
        self.last_news_check = current_dt

    for news_time in self.upcoming_news:
        if abs(news_time - current_dt) <= self.p.news_buffer:
            logging.info(f"News nearby at {news_time}, skipping trade")
            return

    if not (self.p.trading_hours[0] <= hour <= self.p.trading_hours[1]):
        return

    if self.true_range[0] > 2.5 * self.volatility[0]:
        return

    risk_capital = self.broker.getvalue() * RISK_PER_TRADE
    position_size = risk_capital / (self.atr[0] * ATR_MULTIPLIER)

    if not self.position:
        if (self.data.close[0] > self.hull[0] and
            self.ema[0] > self.ema[-1] and
            self.rsi[0] < 65):
            self.buy(size=position_size / self.data.close[0])
            self.stop_price = self.data.close[0] - (self.atr[0] * ATR_MULTIPLIER)
            self.entry_price = self.data.close[0]
            msg = f"🟢 BUY at {self.entry_price:.2f}, SL: {self.stop_price:.2f}"
            logging.info(msg)
            bot.send_message(chat_id=CHAT_ID, text=msg)

    else:
        exit_conditions = [
            self.data.close[0] <= self.stop_price,
            self.rsi[0] > 70,
            self.ema[0] < self.ema[-2],
            self.data.close[0] < self.hull[0]
        ]
        if any(exit_conditions):
            self.close()
            pnl = self.data.close[0] - self.entry_price
            msg = f"🔴 CLOSE at {self.data.close[0]:.2f} | PnL: {pnl:.2f}"
            logging.info(msg)
            bot.send_message(chat_id=CHAT_ID, text=msg)

========== RUN BACKTEST (LIVE LOOP) ==========

def run_backtest_live(): while True: cerebro = bt.Cerebro()

logging.info("Fetching market data...")
    df = yf.download(SYMBOL, period=data_period, interval=data_interval)
    df.columns = [c.lower() for c in df.columns]
    data = bt.feeds.PandasData(dataname=df)

    cerebro.adddata(data)
    cerebro.addstrategy(GoldStrategy)
    cerebro.broker.setcash(10000)
    cerebro.broker.setcommission(commission=0.0002)

    cerebro.run()
    time.sleep(3600)  # Run once per hour

========== MAIN ==========

if name == 'main': t = threading.Thread(target=run_backtest_live) t.start()

p(3600)  # Run once per hour

========== MAIN ==========

if name == 'main': t = threading.Thread(target=run_backtest_live) t.start()


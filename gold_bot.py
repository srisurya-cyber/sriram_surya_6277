import yfinance as yf
import backtrader as bt
import pandas as pd
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
import requests
import re
import telebot
import threading
import time
import os
import warnings

# === Optional: Suppress warnings from backtrader or yf ===
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# === Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "7920222370:AAHvrdZDSscg4H6YmlDGh0-hHBiLJjqd4zA")
CHAT_ID = int(os.getenv("CHAT_ID", "1357505271"))
RISK_PER_TRADE = 0.015
ATR_MULTIPLIER = 1.8
NEWS_BUFFER_MIN = 120

bot = telebot.TeleBot(BOT_TOKEN)

# === News Scraper ===
def scrape_forex_factory_events():
    try:
        url = "https://www.forexfactory.com/calendar?day=today"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        high_impact_events = []
        today = datetime.now(pytz.timezone('America/New_York')).date()
        for row in soup.select('.calendar__row.calendar__row--impact-high'):
            time_cell = row.select_one('.calendar__time')
            if time_cell:
                time_str = time_cell.text.strip()
                if time_str and time_str != 'All Day':
                    try:
                        event_time = datetime.strptime(time_str, '%I:%M%p').time()
                        event_dt = datetime.combine(today, event_time)
                        event_dt = pytz.timezone('America/New_York').localize(event_dt)
                        high_impact_events.append(event_dt.astimezone(pytz.utc))
                    except:
                        pass
        return high_impact_events
    except Exception as e:
        print(f"⚠️ News scrape error: {e}")
        return []

# === Strategy ===
class GoldSafeStrategy(bt.Strategy):
    params = (
        ('trend_ema', 34),
        ('signal_ema', 9),
        ('rsi_period', 14),
        ('atr_period', 14),
        ('news_buffer', timedelta(minutes=NEWS_BUFFER_MIN)),
        ('trading_hours', (12, 17))
    )

    def __init__(self):
        self.hull = bt.indicators.HullMovingAverage(period=self.p.trend_ema)
        self.ema = bt.indicators.EMA(period=self.p.signal_ema)
        self.rsi = bt.indicators.RSI(period=self.p.rsi_period)
        self.atr = bt.indicators.ATR(period=self.p.atr_period)
        self.true_range = bt.indicators.TrueRange()
        self.volatility = bt.indicators.SMA(self.true_range, period=50)
        self.stop_price = None
        self.entry_price = None
        self.upcoming_news = []
        self.last_news_check = None

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                bot.send_message(CHAT_ID, f"🟢 BUY EXECUTED at {order.executed.price:.2f}")
            elif order.issell():
                bot.send_message(CHAT_ID, f"🔴 SELL EXECUTED at {order.executed.price:.2f}")

    def next(self):
        current_dt = self.data.datetime.datetime(0)
        current_hour = current_dt.hour

        # Refresh news once per day
        if self.last_news_check is None or current_dt.date() != self.last_news_check.date():
            self.upcoming_news = scrape_forex_factory_events()
            self.last_news_check = current_dt

        for news_time in self.upcoming_news:
            if abs(news_time - current_dt) <= self.p.news_buffer:
                print(f"⏸️ Skipping trade near news: {news_time}")
                return

        if not (self.p.trading_hours[0] <= current_hour <= self.p.trading_hours[1]):
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
        else:
            exit_conditions = [
                self.data.close[0] <= self.stop_price,
                self.rsi[0] > 70,
                self.ema[0] < self.ema[-2],
                self.data.close[0] < self.hull[0]
            ]
            if any(exit_conditions):
                self.close()
                pnl = (self.data.close[0] - self.entry_price) * self.position.size
                bot.send_message(CHAT_ID, f"🔁 TRADE CLOSED at {self.data.close[0]:.2f} | PnL: ${pnl:.2f}")

# === Backtest Thread ===
def run_backtest_live():
    while True:
        cerebro = bt.Cerebro()
        df = yf.download('GC=F', period='7d', interval='1h', auto_adjust=False)
        df.columns = [c.lower() for c in df.columns]  # ⚠️ Important fix
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.addstrategy(GoldSafeStrategy)
        cerebro.broker.setcash(10000)
        cerebro.run()
        bot.send_message(CHAT_ID, "⏳ Restarting strategy in 1 hour...")
        time.sleep(3600)  # Sleep 1 hour then refresh data

# === Telegram Commands ===
@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    bot.send_message(message.chat.id, "🤖 Welcome! I’ll alert you on XAUUSD trades, news events, and PnL.")

@bot.message_handler(commands=['status'])
def status(message):
    bot.send_message(message.chat.id, f"📊 Bot is live. Portfolio = $10,000 virtual. Trading XAUUSD hourly.")

@bot.message_handler(commands=['news'])
def news(message):
    events = scrape_forex_factory_events()
    if not events:
        bot.send_message(message.chat.id, "✅ No high-impact news events today.")
    else:
        formatted = "\n".join([f"🕒 {e.strftime('%H:%M UTC')}" for e in events])
        bot.send_message(message.chat.id, f"⚠️ Upcoming High-Impact Events:\n{formatted}")

@bot.message_handler(commands=['pnl'])
def pnl(message):
    # Could be improved with persistent PnL tracking
    bot.send_message(message.chat.id, "📈 Current PnL is calculated live during trades only.")

# === Launch Everything ===
if __name__ == '__main__':
    threading.Thread(target=run_backtest_live).start()
    bot.polling(non_stop=True)

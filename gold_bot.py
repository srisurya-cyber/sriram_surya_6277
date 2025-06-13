import yfinance as yf
import backtrader as bt
import pandas as pd
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
import requests
import re
import telebot
import time

# ========== CONFIG ==========
BOT_TOKEN = '7920222370:AAHvrdZDSscg4H6YmlDGh0-hHBiLJjqd4zA'
CHAT_ID = 1357505271
RISK_PER_TRADE = 0.015
ATR_MULTIPLIER = 1.8
NEWS_BUFFER_MIN = 120  # minutes

bot = telebot.TeleBot(BOT_TOKEN)
status_msg = "Bot is starting..."

# ========== NEWS SCRAPER ==========
def scrape_forex_factory_events():
    try:
        url = "https://www.forexfactory.com/calendar?day=today"
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        high_impact_events = []
        today = datetime.now(pytz.timezone('America/New_York')).date()
        for row in soup.select('.calendar__row.calendar__row--impact-high'):
            time_cell = row.select_one('.calendar__time')
            if time_cell and 'calendar__time--' not in time_cell.get('class', []):
                time_str = time_cell.text.strip()
                if time_str and time_str != 'All Day':
                    event_time = datetime.strptime(time_str, '%I:%M%p').time()
                    event_dt = datetime.combine(today, event_time)
                    event_dt = pytz.timezone('America/New_York').localize(event_dt)
                    high_impact_events.append(event_dt.astimezone(pytz.utc))
        return high_impact_events
    except Exception as e:
        bot.send_message(CHAT_ID, f"⚠️ News scrape error: {str(e)}")
        return []

# ========== STRATEGY ==========
class GoldSafeStrategy(bt.Strategy):
    params = (
        ('trend_ema', 34),
        ('signal_ema', 9),
        ('rsi_period', 14),
        ('atr_period', 14),
        ('news_buffer', timedelta(minutes=NEWS_BUFFER_MIN)),
        ('trading_hours', (12, 17))  # UTC time
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
        self.trailing_stop = None
        self.upcoming_news = []
        self.last_news_check = None

    def next(self):
        global status_msg
        current_dt = self.data.datetime.datetime(0)
        current_hour = current_dt.hour

        # Refresh news
        if self.last_news_check is None or current_dt.date() != self.last_news_check.date():
            self.upcoming_news = scrape_forex_factory_events()
            self.last_news_check = current_dt

        # Avoid news
        for news_time in self.upcoming_news:
            if abs(news_time - current_dt) <= self.p.news_buffer:
                status_msg = f"⏸️ News nearby: {news_time.strftime('%H:%M UTC')}"
                return

        # Check trading hours
        if not (self.p.trading_hours[0] <= current_hour <= self.p.trading_hours[1]):
            status_msg = f"⏳ Waiting: {current_hour} UTC outside trading hours"
            return

        # Volatility check
        if self.true_range[0] > 2.5 * self.volatility[0]:
            status_msg = f"⚠️ High volatility: {self.true_range[0]:.2f} > {self.volatility[0]:.2f}"
            return

        risk_capital = self.broker.getvalue() * RISK_PER_TRADE
        position_size = risk_capital / (self.atr[0] * ATR_MULTIPLIER)

        # Entry
        if not self.position:
            if (self.data.close[0] > self.hull[0] and
                self.ema[0] > self.ema[-1] and
                self.rsi[0] < 65):
                
                self.buy(size=position_size / self.data.close[0])
                self.stop_price = self.data.close[0] - (self.atr[0] * ATR_MULTIPLIER)
                self.trailing_stop = self.stop_price
                self.entry_price = self.data.close[0]
                msg = f"🟢 BUY XAUUSD @ {self.entry_price:.2f}\nSL: {self.stop_price:.2f}"
                bot.send_message(CHAT_ID, msg)
                status_msg = msg

        # Exit
        else:
            self.trailing_stop = max(self.trailing_stop, self.data.close[0] - (self.atr[0] * ATR_MULTIPLIER))
            if (self.data.close[0] <= self.trailing_stop or
                self.rsi[0] > 70 or
                self.ema[0] < self.ema[-2] or
                self.data.close[0] < self.hull[0]):
                pnl = self.position.pnl
                msg = f"🔴 CLOSE XAUUSD @ {self.data.close[0]:.2f} | PnL: {pnl:.2f}"
                bot.send_message(CHAT_ID, msg)
                self.close()
                status_msg = msg

# ========== TELEGRAM COMMANDS ==========
@bot.message_handler(commands=['status'])
def cmd_status(msg):
    bot.send_message(msg.chat.id, f"📟 Status: {status_msg}")

@bot.message_handler(commands=['balance'])
def cmd_balance(msg):
    bot.send_message(msg.chat.id, f"💰 Balance: {cerebro.broker.getvalue():.2f}")

@bot.message_handler(commands=['pnl'])
def cmd_pnl(msg):
    bot.send_message(msg.chat.id, f"📈 Last PnL: {strategy.position.pnl:.2f}")

@bot.message_handler(commands=['news'])
def cmd_news(msg):
    news_list = [dt.strftime('%H:%M UTC') for dt in strategy.upcoming_news]
    bot.send_message(msg.chat.id, f"🗓️ News today: {', '.join(news_list) if news_list else 'None'}")

# ========== RUN BACKTEST OR LIVE LOOP ==========
cerebro = bt.Cerebro()
df = yf.download('GC=F', period='7d', interval='1h')
df.dropna(inplace=True)
data = bt.feeds.PandasData(dataname=df)
cerebro.adddata(data)
cerebro.broker.setcash(10000)
cerebro.broker.setcommission(commission=0.0002)
cerebro.addstrategy(GoldSafeStrategy)
strategy = cerebro.run()[0]

# Optional: Uncomment to plot after test
# cerebro.plot(style='candlestick')

# ========== RUN TELEGRAM BOT LOOP ==========
print("✅ Bot running. Type /status in Telegram.")
bot.send_message(CHAT_ID, "✅ Gold trading bot is online.")

while True:
    try:
        bot.polling(none_stop=True, interval=2)
    except Exception as e:
        time.sleep(5)

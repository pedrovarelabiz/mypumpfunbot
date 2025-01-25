import requests
import logging
import yaml
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Index, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import pandas as pd
import schedule
import time
import os
import re
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from requests.adapters import HTTPAdapter, Retry
from flask import Flask, jsonify

# ---------------------- Configuration Loading ----------------------

def load_config(config_path='config.yaml'):
    load_dotenv()
    try:
        with open(config_path, 'r') as file:
            config_content = file.read()
        config_content = re.sub(r'\${(\w+)}', lambda match: os.getenv(match.group(1), ''), config_content)
        config = yaml.safe_load(config_content)
        logging.info('Configuration loaded successfully.')
        return config
    except Exception as e:
        logging.error(f'Failed to load configuration: {e}')
        raise

# ---------------------- Logging Setup ----------------------

def setup_logging(log_file='pumpfun_bot.log'):
    logging.basicConfig(
        level=logging.INFO,
        filename=log_file,
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.info('Logging is set up.')

# ---------------------- Database Setup ----------------------

Base = declarative_base()
class MigratedCoin(Base):
    __tablename__ = 'migrated_coins'
    id = Column(Integer, primary_key=True)
    coin_symbol = Column(String, nullable=False, index=True)
    market_cap = Column(Float)
    volume = Column(Float)
    sentiment_score = Column(Float)
    migration_date = Column(DateTime, default=datetime.datetime.utcnow)

class Tweet(Base):
    __tablename__ = 'tweets'
    id = Column(Integer, primary_key=True)
    coin_id = Column(Integer, ForeignKey('migrated_coins.id'))
    content = Column(String, nullable=False)
    sentiment = Column(Float)
    created_at = Column(DateTime, nullable=False)

def setup_database(db_url='sqlite:///pumpfun_migrated_coins.db'):
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

# ---------------------- Error Handling & Retry Logic ----------------------

def make_request(url, headers=None, params=None):
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    try:
        response = session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f'Error making request to {url}: {e}')
        return None

# ---------------------- Sentiment Analysis ----------------------

analyzer = SentimentIntensityAnalyzer()
def analyze_sentiment(text):
    return analyzer.polarity_scores(text)['compound']

# ---------------------- Trading & Risk Management ----------------------

def decide_trade(coin, config, session):
    risk_limit = config['trading']['risk_limit']
    sentiment_threshold = config['trading']['sentiment_threshold']

    if coin.sentiment_score >= sentiment_threshold:
        logging.info(f'BUY: {coin.coin_symbol} - Sentiment Score: {coin.sentiment_score}')
    elif coin.sentiment_score <= -sentiment_threshold:
        logging.info(f'SELL: {coin.coin_symbol} - Sentiment Score: {coin.sentiment_score}')
    else:
        logging.info(f'HOLD: {coin.coin_symbol} - Sentiment Score: {coin.sentiment_score}')

# ---------------------- Telegram Bot Enhancements ----------------------

def start(update: Update, context: CallbackContext):
    update.message.reply_text('PumpFun Bot is running. Use /status to check trading activity.')

def status(update: Update, context: CallbackContext):
    session = setup_database()
    coins = session.query(MigratedCoin).order_by(MigratedCoin.migration_date.desc()).limit(5).all()
    message = '\n'.join([f'{coin.coin_symbol} - Sentiment: {coin.sentiment_score}' for coin in coins])
    update.message.reply_text(f'Recent Trades:\n{message}')

def buy(update: Update, context: CallbackContext):
    update.message.reply_text('Manual BUY command received. Processing...')

def sell(update: Update, context: CallbackContext):
    update.message.reply_text('Manual SELL command received. Processing...')

def setup_telegram_bot(bot_token):
    updater = Updater(token=bot_token, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('status', status))
    dp.add_handler(CommandHandler('buy', buy))
    dp.add_handler(CommandHandler('sell', sell))
    updater.start_polling()
    return updater

# ---------------------- Web Dashboard (Flask) ----------------------
app = Flask(__name__)

@app.route('/status', methods=['GET'])
def get_status():
    session = setup_database()
    coins = session.query(MigratedCoin).order_by(MigratedCoin.migration_date.desc()).limit(5).all()
    return jsonify([{ 'coin': coin.coin_symbol, 'sentiment': coin.sentiment_score } for coin in coins])

# ---------------------- Main Execution ----------------------

if __name__ == "__main__":
    setup_logging()
    config = load_config('config.yaml')
    session = setup_database()
    bot_token = config['telegram']['bot_token']
    telegram_updater = setup_telegram_bot(bot_token)
    app.run(debug=True, port=5000)

    while True:
        logging.info("Running scheduled jobs...")
        time.sleep(60)

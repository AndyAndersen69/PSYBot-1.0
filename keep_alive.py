"""
Сервер для поддержания активности на Replit
"""
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот психолога активен"

@app.route('/health')
def health():
    return 'OK'

def run():
    app.run(host='0.0.0.0', port=8080)

def start_keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

if __name__ == '__main__':
    start_keep_alive()
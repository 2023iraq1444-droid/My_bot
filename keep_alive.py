"""
خادم Flask بسيط لإبقاء البوت نشطاً وتوفير رابط للمشروع على Replit.
يُشغَّل في خيط منفصل بجانب البوت.
"""
import os
from threading import Thread
from flask import Flask

app = Flask(__name__)


@app.route('/')
def home():
    return "✅ البوت يعمل بنجاح — Bot is alive!"


@app.route('/health')
def health():
    return {"status": "ok"}


def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)


def keep_alive():
    """يبدأ خادم Flask في خيط منفصل."""
    t = Thread(target=run, daemon=True)
    t.start()


if __name__ == '__main__':
    run()

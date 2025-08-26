cat > server.py <<'PY'
import os
import telebot
from flask import Flask, request

# قراءة توكن البوت من متغيرات البيئة
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN غير موجود في متغيرات البيئة!")

bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

# نقطة استقبال الويب هوك
@app.route("/" + BOT_TOKEN, methods=["POST"])
def getMessage():
    json_str = request.stream.read().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# صفحة صحة بسيطة
@app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200

# مثال رسالة /start (اختياري لتجربة الويب هوك)
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "مرحبا 👋، البوت يعمل عبر Webhook!")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # استضافة على كل الواجهات المطلوبة من Render
    app.run(host="0.0.0.0", port=port)
PY

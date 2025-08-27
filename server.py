from flask import Flask, request
import os
import telebot

# --- Telegram Bot setup ---
TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# --- Flask route for webhook ---
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

# --- Home route (to check if service is running) ---
@app.route("/", methods=["GET"])
def home():
    return "Bot is running on Render!"

# --- Example command handler ---
@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.reply_to(message, "Hello 👋, your bot is up and running on Render!")

# --- Main entry point ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render provides PORT
    app.run(host="0.0.0.0", port=port)

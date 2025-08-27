import os
from threading import Thread
from flask import Flask
from bot import main as run_bot  # نستورد دالة تشغيل البوت فقط

app = Flask(__name__)

@app.get("/")
def health():
    return "OK", 200

def _start_bot():
    # تشغيل البوت في ثريد منفصل لأن infinity_polling بلوكيـنغ
    try:
        run_bot()
    except Exception as e:
        # اطبع الخطأ في اللوجز
        print(f"[server] bot crashed: {e}", flush=True)

if __name__ == "__main__":
    # شغّل البوت بالخلفية
    Thread(target=_start_bot, daemon=True).start()
    # افتح بورت كما تطلب Render (من متغير البيئة PORT)
    port = int(os.environ.get("PORT", "10000"))
    # لازم 0.0.0.0 وليس 127.0.0.1
    app.run(host="0.0.0.0", port=port)

import os
from threading import Thread
from flask import Flask
from bot import main as run_bot  # نستورد دالة تشغيل البوت

app = Flask(__name__)

@app.get("/")
def health():
    return "OK", 200

def _start_bot():
    print("[server] starting bot polling...", flush=True)
    try:
        run_bot()
    except Exception as e:
        # اطبع الخطأ بوضوح في اللوجز
        print(f"[server] bot crashed: {e}", flush=True)

if __name__ == "__main__":
    # شغّل البوت في ثريد منفصل
    Thread(target=_start_bot, daemon=True).start()
    # افتح بورت كما تطلب Render (من متغير البيئة PORT)
    port = int(os.environ.get("PORT", "10000"))
    print(f"[server] Flask starting on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port)

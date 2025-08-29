#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Amanex Bot — وسيط بيع/شراء حسابات (نسخة مُحدّثة)
- واجهة ReplyKeyboard للمستخدم (الأزرار أسفل لوحة المفاتيح).
- InlineButton وحيد "شراء الآن" لكل إعلان.
- تسلسل دائم للعروض والطلبات (sequences) + tracking_code بالتاريخ.
- تخزين images كـ Telegram file_id فقط.
- جمع وسيلة تواصل المشتري/البائع وحفظها وإرسالها للإدمن.
- هجرة تلقائية لقاعدة البيانات + نسخ احتياطي.
- أوامر إدمن: /admin, /findlist, /findorder, /backupdb, /approve, /reject, /mark_sold
- ✅ تعديلات هذه النسخة:
  1) تنبيه عمولة 5% عند إدخال السعر.
  2) تنبيه (USDT فقط — TRC20) عند Tonkeeper/Trust Wallet.
  3) تنبيه (داخل سورية فقط) عند Syriatel/MTN/مدفوعاتي.
  4) قراءة كل القيم الحساسة وبيانات الدفع من متغيرات بيئة (.env).
"""

import os
import sys
import json
import time
import shutil
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
import telebot
from telebot import types

from telebot.apihelper import ApiTelegramException

# =========================[ تحميل متغيرات البيئة ]====================
# تأكد أن لديك ملف .env في نفس المجلد يحتوي القيم المطلوبة.
load_dotenv()

# =========================[ إعدادات أساسية ]=========================
# يُقرأ التوكن ومعرّف الإدمن من متغيرات البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))

# بيانات الدفع تُقرأ من البيئة أيضاً + ملاحظاتها
SYRIATEL_NUMBER = os.getenv("SYRIATEL_NUMBER", "").strip()
SYRIATEL_NOTE   = os.getenv("SYRIATEL_NOTE", "داخل سورية فقط").strip()

MTN_NUMBER = os.getenv("MTN_NUMBER", "").strip()
MTN_NOTE   = os.getenv("MTN_NOTE", "داخل سورية فقط").strip()

MADFOUATI_NUMBER = os.getenv("MADFOUATI_NUMBER", "").strip()
MADFOUATI_NOTE   = os.getenv("MADFOUATI_NOTE", "داخل سورية فقط").strip()

TONKEEPER_ADDRESS = os.getenv("TONKEEPER_ADDRESS", "").strip()
TONKEEPER_NOTE    = os.getenv("TONKEEPER_NOTE", "USDT فقط عبر شبكة TRC20").strip()

TRUSTWALLET_ADDRESS = os.getenv("TRUSTWALLET_ADDRESS", "").strip()
TRUSTWALLET_NOTE    = os.getenv("TRUSTWALLET_NOTE", "USDT فقط عبر شبكة TRC20").strip()

DB_FILE = "amanex_bot.db"
DEBUG   = True

# =======================[ تهيئة اللوجر والبوت ]======================
telebot.logger.setLevel(logging.INFO if not DEBUG else logging.DEBUG)
if not BOT_TOKEN:
    print("❌ BOT_TOKEN غير مضبوط. ضع متغير البيئة BOT_TOKEN في .env.")
    sys.exit(1)
if not ADMIN_ID:
    print("❌ ADMIN_ID غير مضبوط. ضع متغير البيئة ADMIN_ID (رقم حسابك العددي).")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================[ حالات المستخدم ]=========================
# user_states[user_id] = dict(...)
user_states: Dict[int, Dict[str, Any]] = {}

# ثابتات واجهة
MAIN_MENU_BUTTONS = ["📤 بيع حساب", "📥 شراء حساب", "👤 حساباتي", "📄 شروط الخدمة", "☎️ تواصل مع الدعم"]
BACK_BTN = "⬅️ رجوع"
CANCEL_BTN = "❌ إلغاء"
DONE_BTN = "✅ انتهيت"

# =========================[ دوال مساعدة عامة ]=======================
def now_utc_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def today_ymd() -> str:
    return datetime.utcnow().strftime("%Y%m%d")

def backup_db_copy(suffix: Optional[str] = None) -> str:
    """ينسخ DB إلى ملف .bak.timestamp لحماية البيانات."""
    if not os.path.exists(DB_FILE):
        return ""
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    name = f"{DB_FILE}.bak.{suffix or ts}"
    shutil.copyfile(DB_FILE, name)
    return name

def dict_get(d, k, default=None):
    return d[k] if (d and k in d) else default

# ===========[ إعداد أسماء الأزرار (تظهر للمستخدم) + ملاحظات ]========
# ملاحظة: سنفصل بين "النص الظاهر" و"المفتاح الداخلي" حتى لا تنكسر الخرائط إذا تغيّر النص.
PAYMENT_LABELS = {
    "SyriaTel": f"سيرياتيل كاش ({SYRIATEL_NOTE})" if SYRIATEL_NOTE else "سيرياتيل كاش",
    "MTN":      f"MTN كاش ({MTN_NOTE})" if MTN_NOTE else "MTN كاش",
    "Madfouati":f"مدفوعاتي ({MADFOUATI_NOTE})" if MADFOUATI_NOTE else "مدفوعاتي",
    "TrustWallet": f"Trust Wallet — USDT TRC20",
    "Tonkeeper":   f"Tonkeeper — USDT TRC20",
}

# الوجهة والملاحظة لكل وسيلة (مصدرها البيئة)
MANAGER_PAYMENT_DEST = {
    "SyriaTel": SYRIATEL_NUMBER,
    "MTN": MTN_NUMBER,
    "Madfouati": MADFOUATI_NUMBER,
    "TrustWallet": TRUSTWALLET_ADDRESS,
    "Tonkeeper": TONKEEPER_ADDRESS,
}
MANAGER_PAYMENT_NOTE = {
    "SyriaTel": SYRIATEL_NOTE,
    "MTN": MTN_NOTE,
    "Madfouati": MADFOUATI_NOTE,
    "TrustWallet": TRUSTWALLET_NOTE,
    "Tonkeeper": TONKEEPER_NOTE,
}

def get_manager_payment_text(method_key: str) -> str:
    """يبني نص وجهة الدفع + الملاحظة للعرض على المشتري."""
    dest = MANAGER_PAYMENT_DEST.get(method_key, "—")
    note = (MANAGER_PAYMENT_NOTE.get(method_key) or "").strip()
    base = f"حول إلى:\n<code>{dest}</code>"
    if note:
        base += f"\n\n⚠️ ملاحظة: {note}"
    return base

def method_display_short(method_key: str) -> str:
    mapping = {
        "SyriaTel": "سيرياتيل كاش",
        "MTN": "MTN كاش",
        "Madfouati": "مدفوعاتي",
        "TrustWallet": "Trust Wallet (USDT TRC20)",
        "Tonkeeper": "Tonkeeper (USDT TRC20)",
    }
    return mapping.get(method_key, method_key)

def parse_payment_selection(text: str) -> Optional[str]:
    """
    يحوّل نص زر ReplyKeyboard (قد يحتوي ملاحظة) إلى مفتاح داخلي ثابت.
    نعتمد على وجود كلمات أساسية داخل النص بدلاً من التطابق الحرفي.
    """
    t = (text or "").lower().strip()
    if "سيرياتيل" in t or "syriatel" in t:
        return "SyriaTel"
    if "mtn" in t:
        return "MTN"
    if "مدفوعاتي" in t or "madfouati" in t:
        return "Madfouati"
    if "trust" in t:
        return "TrustWallet"
    if "tonkeeper" in t or "ton" in t:
        return "Tonkeeper"
    return None

# =========================[ قاعدة البيانات ]=========================
def db_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_db():
    """إنشاء الجداول إن لم توجد + إضافة الأعمدة الناقصة بهدوء + إنشاء فهارس."""
    conn = db_conn()
    c = conn.cursor()

    # sequences: عدادات دائمة
    c.execute("""
        CREATE TABLE IF NOT EXISTS sequences (
            name TEXT PRIMARY KEY,
            value INTEGER
        )
    """)

    # users
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'user',
            joined_at TEXT
        )
    """)

    # listings
    c.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seq INTEGER,
            tracking_code TEXT UNIQUE,
            seller_telegram_id INTEGER,
            category TEXT,
            subcategory TEXT,
            description TEXT,
            images_json TEXT,
            price TEXT,
            payment_methods_json TEXT,
            payment_details_json TEXT,
            seller_contact TEXT,
            status TEXT,
            created_at TEXT
        )
    """)

    # orders
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seq INTEGER,
            tracking_code TEXT UNIQUE,
            listing_id INTEGER,
            buyer_telegram_id INTEGER,
            payment_method TEXT,
            payment_proof_file_id TEXT,
            buyer_contact TEXT,
            status TEXT,
            created_at TEXT
        )
    """)

    # support_tickets
    c.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_telegram_id INTEGER,
            message TEXT,
            status TEXT DEFAULT 'open',
            created_at TEXT
        )
    """)

    # أعمدة قديمة: تأكد من وجود seller_contact و buyer_contact و seq و tracking_code و ...
    def ensure_column(table: str, column: str, coltype: str):
        c.execute(f"PRAGMA table_info({table})")
        cols = [r["name"] for r in c.fetchall()]
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

    ensure_column("listings", "seq", "INTEGER")
    ensure_column("listings", "tracking_code", "TEXT")
    ensure_column("listings", "seller_contact", "TEXT")
    ensure_column("orders",   "seq", "INTEGER")
    ensure_column("orders",   "tracking_code", "TEXT")
    ensure_column("orders",   "buyer_contact", "TEXT")

    # فهارس مفيدة
    c.execute("CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_listings_cat_sub ON listings(category, subcategory)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")

    conn.commit()
    conn.close()

def get_next_seq(name: str) -> int:
    """يزيد عداد sequences بالاسم المحدد ويعيد القيمة الجديدة."""
    conn = db_conn()
    c = conn.cursor()
    c.execute("BEGIN IMMEDIATE")
    c.execute("SELECT value FROM sequences WHERE name = ?", (name,))
    row = c.fetchone()
    if row is None:
        value = 1
        c.execute("INSERT INTO sequences (name, value) VALUES (?, ?)", (name, value))
    else:
        value = row["value"] + 1
        c.execute("UPDATE sequences SET value = ? WHERE name = ?", (value, name))
    conn.commit()
    conn.close()
    return value

def make_tracking(prefix: str, seq: int) -> str:
    # مثال: 010-S20250814
    return f"{seq:03d}-{prefix}{today_ymd()}"

def save_user_if_not_exists(u: telebot.types.User):
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE telegram_id = ?", (u.id,))
    if c.fetchone() is None:
        c.execute(
            "INSERT INTO users (telegram_id, username, full_name, joined_at) VALUES (?,?,?,?)",
            (u.id, u.username or "", (u.first_name or "") + ((" " + u.last_name) if u.last_name else ""), now_utc_str())
        )
        conn.commit()
    conn.close()

# ===============[ دوال التعامل مع البيانات (CRUD مُبسطة) ]=============
def create_listing(seller_id: int, category: str, subcategory: str, description: str,
                   images: List[str], price: str, pay_methods: List[str],
                   pay_details: Dict[str, str], seller_contact: str, status: str="active") -> sqlite3.Row:
    seq = get_next_seq("listings")
    tracking = make_tracking("S", seq)
    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO listings (seq, tracking_code, seller_telegram_id, category, subcategory, description,
                              images_json, price, payment_methods_json, payment_details_json, seller_contact,
                              status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        seq, tracking, seller_id, category, subcategory, description,
        json.dumps(images, ensure_ascii=False), price,
        json.dumps(pay_methods, ensure_ascii=False),
        json.dumps(pay_details, ensure_ascii=False),
        seller_contact, status, now_utc_str()
    ))
    conn.commit()
    c.execute("SELECT * FROM listings WHERE id = ?", (c.lastrowid,))
    row = c.fetchone()
    conn.close()
    return row

def get_active_listings_by_cat_sub(category: str, subcategory: str, limit: int=30) -> List[sqlite3.Row]:
    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM listings
        WHERE status='active' AND category=? AND subcategory=?
        ORDER BY id DESC LIMIT ?
    """, (category, subcategory, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_listing_by_id(listing_id: int) -> Optional[sqlite3.Row]:
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM listings WHERE id=?", (listing_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_listing_by_seq(seq: int) -> Optional[sqlite3.Row]:
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM listings WHERE seq=?", (seq,))
    row = c.fetchone()
    conn.close()
    return row

def create_order(listing_id: int, buyer_id: int, payment_method: str,
                 proof_file_id: str, buyer_contact: str, status: str="paid") -> sqlite3.Row:
    seq = get_next_seq("orders")
    tracking = make_tracking("B", seq)
    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO orders (seq, tracking_code, listing_id, buyer_telegram_id, payment_method,
                            payment_proof_file_id, buyer_contact, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (seq, tracking, listing_id, buyer_id, payment_method, proof_file_id,
          buyer_contact, status, now_utc_str()))
    conn.commit()
    c.execute("SELECT * FROM orders WHERE id=?", (c.lastrowid,))
    row = c.fetchone()
    conn.close()
    return row

def get_order_by_seq(seq: int) -> Optional[sqlite3.Row]:
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE seq=?", (seq,))
    row = c.fetchone()
    conn.close()
    return row

def get_user_listings(uid: int) -> List[sqlite3.Row]:
    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT seq, tracking_code, category, subcategory, price, status
        FROM listings WHERE seller_telegram_id=? ORDER BY id DESC LIMIT 25
    """, (uid,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_user_orders(uid: int) -> List[sqlite3.Row]:
    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT seq, tracking_code, listing_id, payment_method, status
        FROM orders WHERE buyer_telegram_id=? ORDER BY id DESC LIMIT 25
    """, (uid,))
    rows = c.fetchall()
    conn.close()
    return rows

def update_listing_status(listing_id: int, status: str):
    conn = db_conn()
    c = conn.cursor()
    c.execute("UPDATE listings SET status=? WHERE id=?", (status, listing_id))
    conn.commit()
    conn.close()

# =======================[ لوحات المفاتيح (Reply) ]=====================
def main_menu_kb() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    kb.row("📤 بيع حساب", "📥 شراء حساب")
    kb.row("👤 حساباتي", "📄 شروط الخدمة", "☎️ تواصل مع الدعم")
    return kb

def sell_category_kb() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("📱 تواصل اجتماعي", "🎮 ألعاب")
    kb.row("✏️ غير ذلك", BACK_BTN)
    return kb

def social_sub_kb() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("Facebook", "Instagram")
    kb.row("TikTok", "Telegram")
    kb.row("YouTube", "Other", BACK_BTN)
    return kb

def games_sub_kb() -> types.ReplyKeyboardMarkup:
    games = [
        "PUBG Mobile", "Free Fire", "Clash of Clans", "Clash Royale",
        "Call of Duty: Mobile", "Fortnite", "Genshin Impact", "Roblox",
        "Valorant", "Mobile Legends", "Lords Mobile", "Township", "Other"
    ]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    row = []
    for i, g in enumerate(games, 1):
        row.append(g)
        if i % 2 == 0:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    kb.row(BACK_BTN)
    return kb

def payment_methods_kb(multi: bool=True) -> types.ReplyKeyboardMarkup:
    """يبني لوحة طرق الدفع بالمسميات الجديدة (مع الملاحظات)."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=not multi)
    kb.row(PAYMENT_LABELS["SyriaTel"], PAYMENT_LABELS["MTN"])
    kb.row(PAYMENT_LABELS["Madfouati"])
    kb.row(PAYMENT_LABELS["TrustWallet"], PAYMENT_LABELS["Tonkeeper"])
    if multi:
        kb.row(DONE_BTN, CANCEL_BTN)
    else:
        kb.row(BACK_BTN)
    return kb

def buy_flow_kb() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("📱 تواصل اجتماعي", "🎮 ألعاب")
    kb.row("✏️ غير ذلك", BACK_BTN)
    return kb

def admin_menu_kb() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    kb.row("🔎 بحث عرض", "🔎 بحث طلب")
    kb.row("📦 عروض قيد الانتظار", "🧾 طلبات مدفوعة")
    kb.row("📥 نسخ DB احتياطية", BACK_BTN)
    return kb

# =========================[ أدوات رسائل جاهزة ]=======================
WELCOME_TEXT = (
    "🚀 ابدأ تجارتك الإلكترونية بثقة و أمان مع أول بوت عربي للوساطة الرقمية!\n\n"
    "👋 أهلاً بك في بوت <b>Amanex</b>\n\n"
    "هنا تجد منصتك الموثوقة لبيع وشراء الحسابات بكل أمان.\n"
    "نحن الوسيط الذي يضمن حقوق البائع والمشتري ويحميك من الاحتيال.\n\n"
    "اختر إجراءً من الأزرار التالية:"
)

TERMS_TEXT = (
    "📄 <b>شروط الخدمة</b>:\n"
    "1) البوت يعمل كوسيط بين البائع والمشتري ولا يتحمّل مسؤولية أي تعامل خارج المنصّة.\n"
    "2) يجب أن تكون جميع المعلومات صحيحة. أي تزوير يعرض صاحب العرض للحظر.\n"
    "3) ممنوع عرض حسابات مسروقة أو مخالفة.\n"
    "4) الصور إلزامية لعرض الحساب.\n"
    "5) الإدارة لها الحق في رفض أو حذف أي عرض.\n"
    "6) عمولة البوت 5% على كل عملية.\n\n"
    "بإستخدامك للبوت فأنت توافق على ما سبق."
)

SUPPORT_HOWTO = (
    "✉️ أرسل رسالتك الآن وسيتم إنشاء تذكرة دعم ورفعها للإدارة.\n"
    "أرسل كلمة <b>إلغاء</b> لإلغاء العملية."
)

# =====================[ إشعارات للإدمن (رسائل)]=======================
def notify_admin_new_listing(listing: sqlite3.Row):
    """إرسال تفاصيل الإعلان الجديد للإدمن (مع الصور إن وجدت)."""
    if not listing:
        return
    images = json.loads(listing["images_json"] or "[]")
    pm = json.loads(listing["payment_methods_json"] or "[]")
    pd = json.loads(listing["payment_details_json"] or "{}")

    pm_names = [method_display_short(k) for k in pm]

    caption = (
        f"📤 <b>عرض جديد</b>\n"
        f"SEQ: {listing['seq']:03d}\n"
        f"رمز: {listing['tracking_code']}\n"
        f"بائع: <code>{listing['seller_telegram_id']}</code>\n"
        f"فئة: {listing['category']} / {listing['subcategory']}\n"
        f"السعر: {listing['price']}\n"
        f"الحالة: {listing['status']}\n"
        f"تاريخ: {listing['created_at']}\n\n"
        f"<b>الوصف:</b>\n{listing['description']}\n\n"
        f"<b>طرق الدفع (للبائع):</b> {', '.join(pm_names) if pm_names else '-'}\n"
        f"<b>تفاصيل الدفع:</b>\n" +
        ("\n".join([f"- {method_display_short(k)}: {v}" for k, v in pd.items()]) if pd else "-") +
        (f"\n\n<b>وسيلة تواصل البائع:</b> {listing['seller_contact']}" if listing['seller_contact'] else "")
    )

    try:
        if images:
            bot.send_photo(ADMIN_ID, images[0], caption=caption)
            for fid in images[1:]:
                bot.send_photo(ADMIN_ID, fid)
        else:
            bot.send_message(ADMIN_ID, caption)
    except Exception as e:
        logging.exception("notify_admin_new_listing failed: %s", e)

def notify_admin_new_order(order: sqlite3.Row):
    if not order:
        return
    listing = get_listing_by_id(order["listing_id"])
    caption = (
        f"🧾 <b>طلب شراء جديد</b>\n"
        f"ORDER SEQ: {order['seq']:03d}\n"
        f"رمز الطلب: {order['tracking_code']}\n"
        f"Listing ID: {order['listing_id']}\n"
        f"مشتري: <code>{order['buyer_telegram_id']}</code>\n"
        f"طريقة الدفع: {method_display_short(order['payment_method'])}\n"
        f"حالة: {order['status']}\n"
        f"تاريخ: {order['created_at']}\n" +
        (f"\n<u>عن الإعلان:</u> {listing['tracking_code']} — {listing['category']}/{listing['subcategory']} — السعر {listing['price']}" if listing else "") +
        (f"\n\n<b>وسيلة تواصل المشتري:</b> {order['buyer_contact']}" if order['buyer_contact'] else "")
    )

    try:
        if order["payment_proof_file_id"]:
            bot.send_photo(ADMIN_ID, order["payment_proof_file_id"], caption=caption)
        else:
            bot.send_message(ADMIN_ID, caption)
    except Exception as e:
        logging.exception("notify_admin_new_order failed: %s", e)

# =========================[ مسارات الواجهة ]==========================
def reset_state(uid: int):
    user_states.pop(uid, None)

def ensure_user(u: telebot.types.User):
    save_user_if_not_exists(u)

# ----------------------- /start ------------------------
@bot.message_handler(commands=["start"])
def on_start(msg: types.Message):
    ensure_user(msg.from_user)
    reset_state(msg.from_user.id)
    bot.send_message(msg.chat.id, WELCOME_TEXT, reply_markup=main_menu_kb())

# ----------------------- /admin ------------------------
@bot.message_handler(commands=["admin"])
def on_admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    user_states[msg.from_user.id] = {"flow": "admin", "step": "menu"}
    bot.send_message(msg.chat.id, "لوحة تحكم الإدمن — اختر إجراء:", reply_markup=admin_menu_kb())

# ----------------- أوامر إدمن سريعة -------------------
@bot.message_handler(commands=["backupdb"])
def on_backupdb(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    path = backup_db_copy()
    if path:
        bot.reply_to(msg, f"✅ تم إنشاء نسخة: <code>{path}</code>")
    else:
        bot.reply_to(msg, "⚠️ لا يوجد ملف قاعدة بيانات لنسخه.")

@bot.message_handler(commands=["findlist"])
def on_findlist(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(msg, "الاستخدام: /findlist <seq>")
        return
    seq = int(parts[1])
    row = get_listing_by_seq(seq)
    if not row:
        bot.reply_to(msg, "لم يتم العثور على إعلان بهذا الرقم.")
        return
    images = json.loads(row["images_json"] or "[]")
    caption = (
        f"📦 عرض\n"
        f"SEQ: {row['seq']:03d}\n"
        f"رمز: {row['tracking_code']}\n"
        f"ID: {row['id']}\n"
        f"فئة: {row['category']}/{row['subcategory']}\n"
        f"السعر: {row['price']}\n"
        f"الحالة: {row['status']}\n"
        f"الوصف:\n{row['description']}"
    )
    if images:
        bot.send_photo(msg.chat.id, images[0], caption=caption)
        for f in images[1:]:
            bot.send_photo(msg.chat.id, f)
    else:
        bot.send_message(msg.chat.id, caption)

@bot.message_handler(commands=["findorder"])
def on_findorder(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(msg, "الاستخدام: /findorder <seq>")
        return
    seq = int(parts[1])
    row = get_order_by_seq(seq)
    if not row:
        bot.reply_to(msg, "لم يتم العثور على طلب بهذا الرقم.")
        return
    caption = (
        f"🧾 طلب\n"
        f"SEQ: {row['seq']:03d}\n"
        f"رمز: {row['tracking_code']}\n"
        f"Listing ID: {row['listing_id']}\n"
        f"مشتري: <code>{row['buyer_telegram_id']}</code>\n"
        f"طريقة الدفع: {method_display_short(row['payment_method'])}\n"
        f"حالة: {row['status']}\n"
        f"تاريخ: {row['created_at']}\n"
        f"وسيلة تواصل المشتري: {row['buyer_contact'] or '-'}"
    )
    if row["payment_proof_file_id"]:
        bot.send_photo(msg.chat.id, row["payment_proof_file_id"], caption=caption)
    else:
        bot.send_message(msg.chat.id, caption)

# اختياري: approve/reject/mark_sold (أساسيات)
@bot.message_handler(commands=["approve"])
def on_approve(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(msg, "الاستخدام: /approve <listing_id>")
        return
    listing_id = int(parts[1])
    update_listing_status(listing_id, "active")
    bot.reply_to(msg, f"✅ تم تفعيل الإعلان ID {listing_id}.")

@bot.message_handler(commands=["reject"])
def on_reject(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.strip().split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(msg, "الاستخدام: /reject <listing_id> [سبب]")
        return
    listing_id = int(parts[1])
    update_listing_status(listing_id, "rejected")
    reason = parts[2] if len(parts) > 2 else ""
    bot.reply_to(msg, f"⛔️ تم رفض الإعلان ID {listing_id}. {('السبب: ' + reason) if reason else ''}")

@bot.message_handler(commands=["mark_sold"])
def on_mark_sold(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.strip().split()
    if len(parts) not in (2, 3) or not parts[1].isdigit():
        bot.reply_to(msg, "الاستخدام: /mark_sold <listing_id> [order_seq]")
        return
    listing_id = int(parts[1])
    update_listing_status(listing_id, "sold")
    bot.reply_to(msg, f"🏁 تم وسم الإعلان {listing_id} كمباع.")

# =========================[ أزرار الشراء (Inline) ]===================
@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("buy_"))
def on_buy_now(call: types.CallbackQuery):
    uid = call.from_user.id
    try:
        listing_id = int(call.data.split("_", 1)[1])
    except:
        bot.answer_callback_query(call.id, "خطأ في معرف الإعلان.")
        return

    listing = get_listing_by_id(listing_id)
    if not listing or listing["status"] != "active":
        bot.answer_callback_query(call.id, "العرض غير متاح.")
        return

    user_states[uid] = {
        "flow": "buy",
        "step": "choose_payment",
        "listing_id": listing_id
    }
    bot.send_message(call.message.chat.id, "💳 اختر طريقة الدفع:", reply_markup=payment_methods_kb(multi=False))
    bot.answer_callback_query(call.id, "اختر طريقة الدفع.")

# =====================[ استقبال الصور (إثبات/صور عرض) ]================
@bot.message_handler(content_types=["photo"])
def on_photo(msg: types.Message):
    uid = msg.from_user.id
    state = user_states.get(uid)

    if not state:
        return

    # صور مسار البيع
    if state.get("flow") == "sell" and state.get("step") == "photos":
        file_id = msg.photo[-1].file_id
        imgs = state.get("images", [])
        imgs.append(file_id)
        state["images"] = imgs
        user_states[uid] = state
        bot.reply_to(msg, "✅ تم حفظ الصورة. أرسل المزيد أو اكتب <b>تم</b> للمتابعة.")
        return

    # إثبات دفع المشتري
    if state.get("flow") == "buy" and state.get("step") == "await_payment_proof":
        file_id = msg.photo[-1].file_id
        state["payment_proof_file_id"] = file_id
        state["step"] = "await_buyer_contact"
        user_states[uid] = state
        bot.send_message(msg.chat.id, "✅ تم استلام إثبات الدفع.\nالآن أرسل <b>وسيلة تواصل</b> بك (بريد إلكتروني أو رقم واتساب أو @يوزر تلغرام).")
        return

# =====================[ الموجّه العام للنصوص ]========================
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(msg: types.Message):
    text = (msg.text or "").strip()
    uid  = msg.from_user.id
    state = user_states.get(uid)

    # -------- ضمن تدفق إدمن تفاعلي ----------
    if state and state.get("flow") == "admin":
        handle_admin_flow(msg, state)
        return

    # --------- / رجوع عام ---------
    if text == BACK_BTN:
        reset_state(uid)
        bot.send_message(msg.chat.id, "عدنا إلى القائمة الرئيسية.", reply_markup=main_menu_kb())
        return

    # --------- القوائم الرئيسية ----------
    if text == "📄 شروط الخدمة":
        bot.send_message(msg.chat.id, TERMS_TEXT, reply_markup=main_menu_kb())
        return

    if text == "☎️ تواصل مع الدعم":
        user_states[uid] = {"flow": "support", "step": "await_message"}
        bot.send_message(msg.chat.id, SUPPORT_HOWTO, reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).row(BACK_BTN))
        return

    if state and state.get("flow") == "support":
        if text == "إلغاء":
            reset_state(uid)
            bot.send_message(msg.chat.id, "تم الإلغاء.", reply_markup=main_menu_kb())
            return
        # حفظ تذكرة
        conn = db_conn()
        c = conn.cursor()
        c.execute("INSERT INTO support_tickets (user_telegram_id, message, created_at) VALUES (?,?,?)",
                  (uid, text, now_utc_str()))
        conn.commit()
        conn.close()
        bot.send_message(msg.chat.id, "✅ تم استلام طلب الدعم. سنرد عليك قريباً.", reply_markup=main_menu_kb())
        bot.send_message(ADMIN_ID, f"رسالة دعم من {uid}:\n{text}")
        reset_state(uid)
        return

    if text == "📤 بيع حساب":
        ensure_user(msg.from_user)
        user_states[uid] = {"flow": "sell", "step": "choose_category"}
        bot.send_message(msg.chat.id, "اختر الفئة:", reply_markup=sell_category_kb())
        return

    if text == "📥 شراء حساب":
        ensure_user(msg.from_user)
        user_states[uid] = {"flow": "buy", "step": "choose_category"}
        bot.send_message(msg.chat.id, "🔍 اختر فئة العروض:", reply_markup=buy_flow_kb())
        return

    if text == "👤 حساباتي":
        ensure_user(msg.from_user)
        show_my_items(msg)
        return

    # --------- مسار البيع ----------
    if state and state.get("flow") == "sell":
        handle_sell_flow(msg, state)
        return

    # --------- مسار الشراء ----------
    if state and state.get("flow") == "buy":
        handle_buy_flow(msg, state)
        return

    # أي كتابة خارج المسارات
    bot.send_message(msg.chat.id, "أهلاً — استخدم الأزرار أسفل لوحة المفاتيح للبدء أو اكتب /start للعودة.", reply_markup=main_menu_kb())

# =========================[ دوال المسارات ]===========================
def handle_sell_flow(msg: types.Message, state: Dict[str, Any]):
    uid = msg.from_user.id
    text = (msg.text or "").strip()

    step = state.get("step")
    # 1) اختيار الفئة
    if step == "choose_category":
        if text == "📱 تواصل اجتماعي":
            state["category"] = "social"
            state["step"] = "choose_sub"
            bot.send_message(msg.chat.id, "اختر المنصة:", reply_markup=social_sub_kb())
            return
        elif text == "🎮 ألعاب":
            state["category"] = "games"
            state["step"] = "choose_sub"
            bot.send_message(msg.chat.id, "اختر اللعبة:", reply_markup=games_sub_kb())
            return
        elif text == "✏️ غير ذلك":
            state["category"] = "other"
            state["subcategory"] = "Other"
            state["step"] = "desc"
            bot.send_message(msg.chat.id, "✏️ أرسل وصف الحساب بالتفصيل:", reply_markup=types.ReplyKeyboardRemove())
            return
        else:
            bot.send_message(msg.chat.id, "اختر من الأزرار.", reply_markup=sell_category_kb())
            return

    # 2) اختيار المنصة/اللعبة
    if step == "choose_sub":
        if text == BACK_BTN:
            state["step"] = "choose_category"
            bot.send_message(msg.chat.id, "رجعناك لاختيار الفئة:", reply_markup=sell_category_kb())
            return
        state["subcategory"] = text
        state["step"] = "desc"
        bot.send_message(msg.chat.id, "✏️ أرسل وصف الحساب بالتفصيل:", reply_markup=types.ReplyKeyboardRemove())
        return

    # 3) الوصف
    if step == "desc":
        state["description"] = text
        state["images"] = []
        state["step"] = "photos"
        bot.send_message(msg.chat.id, "📸 أرسل صورة واحدة على الأقل (ملف/صورة تيليجرام). عند الانتهاء اكتب <b>تم</b>.")
        return

    # 4) استقبال صور أو كلمة "تم" ضمن on_photo؛ هنا نعالج كلمة تم
    if step == "photos":
        if text.lower() in ("تم", "done"):
            imgs = state.get("images", [])
            if not imgs:
                bot.send_message(msg.chat.id, "⚠️ أرسل صورة واحدة على الأقل ثم اكتب <b>تم</b>.")
                return
            state["step"] = "price"
            # ⬇️ تنبيه العمولة 5%
            bot.send_message(
                msg.chat.id,
                "💰 اكتب السعر المطلوب (مثال: 25 USDT أو 1000 SYP).\n"
                "⚠️ <b>تنبيه:</b> عمولة البوت <b>5%</b> تُخصم عند إتمام البيع."
            )
            return
        else:
            bot.send_message(msg.chat.id, "أرسل الصور ثم اكتب <b>تم</b> للمتابعة.")
            return

    # 5) السعر
    if step == "price":
        state["price"] = text
        state["payments"] = []
        state["payment_details"] = {}
        state["step"] = "payments"
        bot.send_message(
            msg.chat.id,
            "💵 اختر طرق الاستلام التي تقبلها (يمكن عدة طرق) ثم اضغط <b>✅ انتهيت</b>.",
            reply_markup=payment_methods_kb(multi=True)
        )
        return

    # 6) اختيار طرق الدفع (متعددة)
    if step == "payments":
        if text == CANCEL_BTN:
            reset_state(uid)
            bot.send_message(msg.chat.id, "تم الإلغاء.", reply_markup=main_menu_kb())
            return
        if text == DONE_BTN:
            if not state.get("payments"):
                bot.send_message(msg.chat.id, "اختر طريقة دفع واحدة على الأقل ثم اضغط <b>✅ انتهيت</b>.")
                return
            state["step"] = "seller_contact"
            bot.send_message(msg.chat.id, "📞 أرسل وسيلة تواصل بك (بريد/واتساب/@يوزر) ليتمكن الإدمن من التواصل:")
            return

        method_key = parse_payment_selection(text)
        if method_key:
            if method_key not in state["payments"]:
                state["payments"].append(method_key)
            state["await_detail_method"] = method_key
            state["step"] = "await_pay_detail"
            prompt = "رقم الهاتف" if method_key in ("SyriaTel", "MTN", "Madfouati") else "عنوان المحفظة (USDT-TRC20)"
            # عرض الملاحظة الخاصة بالطريقة عند طلب التفاصيل
            note = MANAGER_PAYMENT_NOTE.get(method_key)
            note_line = f"\n⚠️ ملاحظة: {note}" if note else ""
            bot.send_message(msg.chat.id, f"✏️ أدخل {prompt} لطريقة <b>{method_display_short(method_key)}</b>{note_line}:")
            return

        bot.send_message(msg.chat.id, "اختر من الأزرار أو اضغط <b>✅ انتهيت</b> عند الانتهاء.", reply_markup=payment_methods_kb(multi=True))
        return

    if step == "await_pay_detail":
        method = state.get("await_detail_method")
        if not method:
            state["step"] = "payments"
            bot.send_message(msg.chat.id, "حالة غير متوقعة. عدنا لاختيار الطرق.", reply_markup=payment_methods_kb(multi=True))
            return
        value = text
        pd = state.get("payment_details", {})
        pd[method] = value
        state["payment_details"] = pd
        state["await_detail_method"] = None
        state["step"] = "payments"
        bot.send_message(
            msg.chat.id,
            f"✅ تم حفظ بيانات <b>{method_display_short(method)}</b>.\n"
            f"يمكنك اختيار طرق أخرى أو اضغط <b>✅ انتهيت</b>.",
            reply_markup=payment_methods_kb(multi=True)
        )
        return

    # 7) وسيلة تواصل البائع
    if step == "seller_contact":
        state["seller_contact"] = text
        # إنشاء الإعلان وحفظه
        try:
            listing = create_listing(
                seller_id=uid,
                category=state["category"],
                subcategory=state["subcategory"],
                description=state["description"],
                images=state.get("images", []),
                price=state["price"],
                pay_methods=state.get("payments", []),
                pay_details=state.get("payment_details", {}),
                seller_contact=state.get("seller_contact", ""),
                status="active"
            )
            bot.send_message(
                msg.chat.id,
                f"✅ تم إنشاء إعلانك.\nرمز الإعلان: <code>{listing['tracking_code']}</code>\n"
                "أرسل /start للعودة للقائمة.",
                reply_markup=main_menu_kb()
            )
            notify_admin_new_listing(listing)
        except Exception as e:
            logging.exception("create listing failed: %s", e)
            bot.send_message(msg.chat.id, "⚠️ حدث خطأ أثناء حفظ الإعلان. حاول لاحقاً.")
        finally:
            reset_state(uid)
        return

def handle_buy_flow(msg: types.Message, state: Dict[str, Any]):
    uid = msg.from_user.id
    text = (msg.text or "").strip()
    step = state.get("step")

    # 1) اختيار الفئة
    if step == "choose_category":
        if text == "📱 تواصل اجتماعي":
            state["category"] = "social"
            state["step"] = "choose_sub"
            bot.send_message(msg.chat.id, "اختر منصة الحساب الذي تريد شراءه:", reply_markup=social_sub_kb())
            return
        elif text == "🎮 ألعاب":
            state["category"] = "games"
            state["step"] = "choose_sub"
            bot.send_message(msg.chat.id, "اختر اللعبة:", reply_markup=games_sub_kb())
            return
        elif text == "✏️ غير ذلك":
            state["category"] = "other"
            state["step"] = "choose_sub_other"
            bot.send_message(msg.chat.id, "اكتب نوع الحساب المطلوب (كلمة واحدة أو جملة قصيرة):", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).row(BACK_BTN))
            return
        else:
            bot.send_message(msg.chat.id, "اختر من الأزرار.", reply_markup=buy_flow_kb())
            return

    # 2) اختيار المنصة/اللعبة
    if step == "choose_sub":
        if text == BACK_BTN:
            state["step"] = "choose_category"
            bot.send_message(msg.chat.id, "اختر الفئة:", reply_markup=buy_flow_kb())
            return
        state["subcategory"] = text
        # عرض العروض
        rows = get_active_listings_by_cat_sub(state["category"], state["subcategory"])
        if not rows:
            bot.send_message(msg.chat.id, "لا توجد عروض حالياً لهذه الفئة/المنصة.", reply_markup=main_menu_kb())
            reset_state(uid)
            return

        for r in rows:
            caption = (
                f"🔖 عرض للبيع\n"
                f"SEQ: {r['seq']:03d}\n"
                f"رمز: {r['tracking_code']}\n"
                f"فئة: {r['category']}/{r['subcategory']}\n"
                f"💰 السعر: {r['price']}\n\n"
                f"{r['description']}"
            )
            images = json.loads(r["images_json"] or "[]")
            ikb = types.InlineKeyboardMarkup()
            ikb.add(types.InlineKeyboardButton("📥 شراء الآن", callback_data=f"buy_{r['id']}"))
            try:
                if images:
                    bot.send_photo(msg.chat.id, images[0], caption=caption, reply_markup=ikb)
                else:
                    bot.send_message(msg.chat.id, caption, reply_markup=ikb)
            except Exception:
                bot.send_message(msg.chat.id, caption, reply_markup=ikb)

        return

    if step == "choose_sub_other":
        if text == BACK_BTN:
            state["step"] = "choose_category"
            bot.send_message(msg.chat.id, "اختر الفئة:", reply_markup=buy_flow_kb())
            return
        bot.send_message(msg.chat.id, "حالياً لا توجد عروض لفئة 'غير ذلك' مفلترة. استخدم الفئات المحدّدة.", reply_markup=main_menu_kb())
        reset_state(uid)
        return

    # 3) اختيار طريقة الدفع
    if step == "choose_payment":
        if text == BACK_BTN:
            reset_state(uid)
            bot.send_message(msg.chat.id, "ألغينا العملية.", reply_markup=main_menu_kb())
            return

        method_key = parse_payment_selection(text)
        if not method_key:
            bot.send_message(msg.chat.id, "اختر طريقة صحيحة من الأزرار:", reply_markup=payment_methods_kb(multi=False))
            return

        state["payment_method"] = method_key
        state["step"] = "await_payment_proof"
        user_states[uid] = state

        bot.send_message(
            msg.chat.id,
            f"📌 الطريقة: <b>{method_display_short(method_key)}</b>\n"
            f"{get_manager_payment_text(method_key)}\n\n"
            "بعد التحويل، أرسل <b>صورة</b> إثبات الدفع هنا."
        )
        return

    # 4) بعد استقبال الصورة — نطلب وسيلة تواصل، ثم ننشئ الطلب في الخطوة التالية
    if step == "await_buyer_contact":
        contact = text
        listing_id = state.get("listing_id")
        method = state.get("payment_method")
        proof = state.get("payment_proof_file_id")

        if not all([listing_id, method, proof]):
            reset_state(uid)
            bot.send_message(msg.chat.id, "حالة غير متوقعة. أعد المحاولة من جديد.", reply_markup=main_menu_kb())
            return

        try:
            order = create_order(
                listing_id=listing_id,
                buyer_id=uid,
                payment_method=method,
                proof_file_id=proof,
                buyer_contact=contact,
                status="paid"
            )
            bot.send_message(msg.chat.id, f"✅ تم تسجيل طلبك.\nرقم الطلب: <code>{order['tracking_code']}</code>", reply_markup=main_menu_kb())
            notify_admin_new_order(order)
        except Exception as e:
            logging.exception("create order failed: %s", e)
            bot.send_message(msg.chat.id, "⚠️ حدث خطأ أثناء تسجيل الطلب. حاول لاحقاً.", reply_markup=main_menu_kb())
        finally:
            reset_state(uid)
        return

def handle_admin_flow(msg: types.Message, state: Dict[str, Any]):
    uid = msg.from_user.id
    if uid != ADMIN_ID:
        reset_state(uid)
        return

    text = (msg.text or "").strip()
    step = state.get("step")

    if step == "menu":
        if text == BACK_BTN:
            reset_state(uid)
            bot.send_message(msg.chat.id, "خروج من لوحة التحكم.", reply_markup=main_menu_kb())
            return
        if text == "🔎 بحث عرض":
            state["step"] = "await_find_listing_seq"
            bot.send_message(msg.chat.id, "أدخل رقم التسلسل (seq) للإعلان:")
            return
        if text == "🔎 بحث طلب":
            state["step"] = "await_find_order_seq"
            bot.send_message(msg.chat.id, "أدخل رقم التسلسل (seq) للطلب:")
            return
        if text == "📦 عروض قيد الانتظار":
            conn = db_conn()
            c = conn.cursor()
            c.execute("SELECT id, seq, tracking_code, category, subcategory, price FROM listings WHERE status='pending' ORDER BY id DESC LIMIT 30")
            rows = c.fetchall()
            conn.close()
            if not rows:
                bot.send_message(msg.chat.id, "لا توجد عروض قيد الانتظار.", reply_markup=admin_menu_kb())
            else:
                lines = ["قيد الانتظار:"]
                for r in rows:
                    lines.append(f"- ID {r['id']} | SEQ {r['seq']:03d} | {r['tracking_code']} | {r['category']}/{r['subcategory']} | {r['price']}")
                bot.send_message(msg.chat.id, "\n".join(lines), reply_markup=admin_menu_kb())
            return
        if text == "🧾 طلبات مدفوعة":
            conn = db_conn()
            c = conn.cursor()
            c.execute("SELECT id, seq, tracking_code, listing_id, payment_method FROM orders WHERE status='paid' ORDER BY id DESC LIMIT 30")
            rows = c.fetchall()
            conn.close()
            if not rows:
                bot.send_message(msg.chat.id, "لا توجد طلبات مدفوعة حالياً.", reply_markup=admin_menu_kb())
            else:
                lines = ["طلبات مدفوعة:"]
                for r in rows:
                    lines.append(f"- ORDER SEQ {r['seq']:03d} | {r['tracking_code']} | Listing {r['listing_id']} | {method_display_short(r['payment_method'])}")
                bot.send_message(msg.chat.id, "\n".join(lines), reply_markup=admin_menu_kb())
            return
        if text == "📥 نسخ DB احتياطية":
            path = backup_db_copy()
            bot.send_message(msg.chat.id, f"✅ تم إنشاء نسخة: <code>{path}</code>", reply_markup=admin_menu_kb())
            return

        bot.send_message(msg.chat.id, "اختر من القائمة:", reply_markup=admin_menu_kb())
        return

    if step == "await_find_listing_seq":
        if not text.isdigit():
            bot.send_message(msg.chat.id, "أدخل رقمًا صحيحًا.")
            return
        seq = int(text)
        row = get_listing_by_seq(seq)
        if not row:
            bot.send_message(msg.chat.id, "لا يوجد إعلان بهذا الرقم.", reply_markup=admin_menu_kb())
            state["step"] = "menu"
            return
        images = json.loads(row["images_json"] or "[]")
        caption = (
            f"📦 عرض\n"
            f"SEQ: {row['seq']:03d} | رمز: {row['tracking_code']}\n"
            f"ID: {row['id']}\n"
            f"فئة: {row['category']}/{row['subcategory']}\n"
            f"السعر: {row['price']} | الحالة: {row['status']}\n\n"
            f"{row['description']}"
        )
        if images:
            bot.send_photo(msg.chat.id, images[0], caption=caption)
            for f in images[1:]:
                bot.send_photo(msg.chat.id, f)
        else:
            bot.send_message(msg.chat.id, caption)
        state["step"] = "menu"
        bot.send_message(msg.chat.id, "رجعناك لقائمة الإدمن.", reply_markup=admin_menu_kb())
        return

    if step == "await_find_order_seq":
        if not text.isdigit():
            bot.send_message(msg.chat.id, "أدخل رقمًا صحيحًا.")
            return
        seq = int(text)
        row = get_order_by_seq(seq)
        if not row:
            bot.send_message(msg.chat.id, "لا يوجد طلب بهذا الرقم.", reply_markup=admin_menu_kb())
            state["step"] = "menu"
            return
        caption = (
            f"🧾 طلب\n"
            f"SEQ: {row['seq']:03d} | رمز: {row['tracking_code']}\n"
            f"Listing ID: {row['listing_id']}\n"
            f"مشتري: <code>{row['buyer_telegram_id']}</code>\n"
            f"طريقة الدفع: {method_display_short(row['payment_method'])} | الحالة: {row['status']}\n"
            f"وسيلة تواصل: {row['buyer_contact'] or '-'}\n"
            f"تاريخ: {row['created_at']}"
        )
        if row["payment_proof_file_id"]:
            bot.send_photo(msg.chat.id, row["payment_proof_file_id"], caption=caption)
        else:
            bot.send_message(msg.chat.id, caption)
        state["step"] = "menu"
        bot.send_message(msg.chat.id, "رجعناك لقائمة الإدمن.", reply_markup=admin_menu_kb())
        return

def show_my_items(msg: types.Message):
    uid = msg.from_user.id
    my_lists = get_user_listings(uid)
    my_orders = get_user_orders(uid)

    lines = []
    lines.append("👤 <b>سجلّك</b>\n")

    lines.append("📦 <u>عروضي</u>:")
    if not my_lists:
        lines.append("- لا يوجد عروض.")
    else:
        for r in my_lists:
            lines.append(f"- SEQ {r['seq']:03d} | {r['tracking_code']} | {r['category']}/{r['subcategory']} | {r['price']} | {r['status']}")

    lines.append("\n🧾 <u>طلباتي</u>:")
    if not my_orders:
        lines.append("- لا يوجد طلبات.")
    else:
        for r in my_orders:
            lines.append(f"- SEQ {r['seq']:03d} | {r['tracking_code']} | Listing {r['listing_id']} | {method_display_short(r['payment_method'])} | {r['status']}")

    bot.send_message(msg.chat.id, "\n".join(lines), reply_markup=main_menu_kb())

# ===========================[ تشغيل البوت ]===========================
def main():
    print("🚀 Amanex bot starting (Render ready).")
    migrate_db()

    while True:  # نحاول نعيد التشغيل إذا وقع خطأ
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30, skip_pending=True)
        except ApiTelegramException as e:
            if e.error_code == 409:
                logging.warning("⚠️ Conflict 409: Another polling session detected. Retrying in 5s...")
                time.sleep(5)
                continue  # أعد المحاولة
            else:
                logging.exception("Telegram API error: %s", e)
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n🛑 تم الإيقاف اليدوي.")
            break
        except Exception as e:
            logging.exception("Polling crashed: %s", e)
            time.sleep(5)

import os
import sqlite3
import requests
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="Bot + Admin Panel")

# --- دیتابیس ---
DB_DIR = os.getenv("DB_DIR", "/data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "app.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            delivery TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            service_id INTEGER,
            service_title TEXT,
            phone TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT,
            user_id INTEGER,
            username TEXT,
            product_id INTEGER,
            product_title TEXT,
            amount INTEGER,
            receipt_file_id TEXT,
            status TEXT DEFAULT 'pending',
            admin_note TEXT,
            created_at TEXT,
            reviewed_at TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# --- کمکی ---
def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def tg(method, payload):
    token = get_setting("bot_token")
    if not token:
        return None
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print("TG error:", e)
        return None


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# --- پنل مدیریت ---
@app.get("/", response_class=HTMLResponse)
def admin(msg: str = ""):
    conn = get_db()
    services = conn.execute("SELECT * FROM services ORDER BY id DESC").fetchall()
    products = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    payments = conn.execute("SELECT * FROM payments ORDER BY id DESC LIMIT 50").fetchall()
    consults = conn.execute("SELECT * FROM consultations ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()

    bot_token = get_setting("bot_token")
    card_number = get_setting("card_number")
    card_owner = get_setting("card_owner")
    card_bank = get_setting("card_bank")

    # جدول خدمات
    services_rows = ""
    for s in services:
        services_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="p-2 text-center">{s['id']}</td>
            <td class="p-2">{s['title']}</td>
            <td class="p-2 text-xs text-gray-400">{s['description'] or ''}</td>
            <td class="p-2 text-center">
                <form action="/service/delete/{s['id']}" method="post" style="display:inline">
                    <button class="bg-red-600 hover:bg-red-700 text-white text-xs py-1 px-2 rounded">حذف</button>
                </form>
            </td>
        </tr>"""
    if not services:
        services_rows = '<tr><td colspan="4" class="p-3 text-center text-gray-500">خالی</td></tr>'

    # جدول محصولات
    products_rows = ""
    for p in products:
        products_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="p-2 text-center">{p['id']}</td>
            <td class="p-2">{p['title']}</td>
            <td class="p-2">{p['price']:,}</td>
            <td class="p-2 text-xs text-gray-400">{p['delivery'] or ''}</td>
            <td class="p-2 text-center">
                <form action="/product/delete/{p['id']}" method="post" style="display:inline">
                    <button class="bg-red-600 hover:bg-red-700 text-white text-xs py-1 px-2 rounded">حذف</button>
                </form>
            </td>
        </tr>"""
    if not products:
        products_rows = '<tr><td colspan="5" class="p-3 text-center text-gray-500">خالی</td></tr>'

    # جدول فیش‌ها
    payments_rows = ""
    for p in payments:
        status_badge = {
            "pending": '<span class="bg-yellow-600 px-2 py-1 rounded text-xs">در انتظار</span>',
            "approved": '<span class="bg-green-600 px-2 py-1 rounded text-xs">تایید</span>',
            "rejected": '<span class="bg-red-600 px-2 py-1 rounded text-xs">رد</span>',
        }.get(p["status"], p["status"])
        actions = ""
        if p["status"] == "pending":
            actions = f"""
            <form action="/payment/approve/{p['id']}" method="post" style="display:inline">
                <button class="bg-green-600 hover:bg-green-700 text-white text-xs py-1 px-2 rounded">تایید</button>
            </form>
            <form action="/payment/reject/{p['id']}" method="post" style="display:inline">
                <button class="bg-red-600 hover:bg-red-700 text-white text-xs py-1 px-2 rounded">رد</button>
            </form>"""
        payments_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="p-2 text-center text-xs">{p['order_code']}</td>
            <td class="p-2 text-xs">@{p['username'] or p['user_id']}</td>
            <td class="p-2 text-xs">{p['product_title']}</td>
            <td class="p-2 text-xs">{p['amount']:,}</td>
            <td class="p-2 text-center">{status_badge}</td>
            <td class="p-2 text-center">{actions}</td>
        </tr>"""
    if not payments:
        payments_rows = '<tr><td colspan="6" class="p-3 text-center text-gray-500">خالی</td></tr>'

    # جدول مشاوره‌ها
    consults_rows = ""
    for c in consults:
        consults_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="p-2 text-xs">@{c['username'] or c['user_id']}</td>
            <td class="p-2 text-xs">{c['service_title']}</td>
            <td class="p-2 text-xs" dir="ltr">{c['phone']}</td>
            <td class="p-2 text-xs">{c['created_at']}</td>
        </tr>"""
    if not consults:
        consults_rows = '<tr><td colspan="4" class="p-3 text-center text-gray-500">خالی</td></tr>'

    msg_html = f'<div class="bg-blue-900/50 border border-blue-500 p-3 rounded mb-4 text-sm">{msg}</div>' if msg else ''

    return f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>پنل مدیریت</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-900 text-gray-100 p-4 sm:p-8 font-sans">
        <div class="max-w-5xl mx-auto space-y-6">

            <h1 class="text-2xl font-bold text-blue-400">🖥️ پنل مدیریت ربات</h1>
            {msg_html}

            <!-- تنظیمات ربات -->
            <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <h2 class="text-lg font-bold mb-3 text-blue-400">⚙️ تنظیمات ربات</h2>
                <form action="/set-webhook" method="post" class="space-y-3">
                    <div>
                        <label class="block text-sm mb-1">توکن ربات</label>
                        <input type="text" name="bot_token" value="{bot_token}" dir="ltr" required
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-left">
                    </div>
                    <button class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded">ست کردن وبهوک</button>
                </form>
            </div>

            <!-- کارت بانکی -->
            <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <h2 class="text-lg font-bold mb-3 text-blue-400">💳 اطلاعات کارت بانکی</h2>
                <form action="/set-card" method="post" class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <input type="text" name="card_number" value="{card_number}" dir="ltr" placeholder="شماره کارت"
                           class="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-left">
                    <input type="text" name="card_owner" value="{card_owner}" placeholder="نام صاحب کارت"
                           class="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white">
                    <input type="text" name="card_bank" value="{card_bank}" placeholder="نام بانک"
                           class="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white">
                    <button class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded sm:col-span-3">ذخیره</button>
                </form>
            </div>

            <!-- خدمات -->
            <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <h2 class="text-lg font-bold mb-3 text-blue-400">🛠️ خدمات</h2>
                <form action="/service/add" method="post" class="space-y-2 mb-4">
                    <input type="text" name="title" required placeholder="عنوان خدمت"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white">
                    <textarea name="description" placeholder="توضیحات"
                              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white"></textarea>
                    <button class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded">افزودن خدمت</button>
                </form>
                <table class="w-full text-sm">
                    <thead class="bg-gray-700"><tr>
                        <th class="p-2">ID</th><th class="p-2">عنوان</th><th class="p-2">توضیحات</th><th class="p-2">عملیات</th>
                    </tr></thead>
                    <tbody>{services_rows}</tbody>
                </table>
            </div>

            <!-- محصولات -->
            <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <h2 class="text-lg font-bold mb-3 text-blue-400">📦 محصولات (فایل / دوره / قالب)</h2>
                <form action="/product/add" method="post" class="space-y-2 mb-4">
                    <input type="text" name="title" required placeholder="عنوان"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white">
                    <textarea name="description" placeholder="توضیحات"
                              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white"></textarea>
                    <input type="number" name="price" required placeholder="قیمت (تومان)"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white">
                    <textarea name="delivery" placeholder="محتوای تحویل (لینک دانلود / متن / کد)"
                              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white"></textarea>
                    <button class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded">افزودن محصول</button>
                </form>
                <table class="w-full text-sm">
                    <thead class="bg-gray-700"><tr>
                        <th class="p-2">ID</th><th class="p-2">عنوان</th><th class="p-2">قیمت</th><th class="p-2">تحویل</th><th class="p-2">عملیات</th>
                    </tr></thead>
                    <tbody>{products_rows}</tbody>
                </table>
            </div>

            <!-- فیش‌ها -->
            <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <h2 class="text-lg font-bold mb-3 text-blue-400">💳 فیش‌های پرداخت</h2>
                <table class="w-full text-sm">
                    <thead class="bg-gray-700"><tr>
                        <th class="p-2">کد</th><th class="p-2">کاربر</th><th class="p-2">محصول</th><th class="p-2">مبلغ</th><th class="p-2">وضعیت</th><th class="p-2">عملیات</th>
                    </tr></thead>
                    <tbody>{payments_rows}</tbody>
                </table>
            </div>

            <!-- مشاوره‌ها -->
            <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <h2 class="text-lg font-bold mb-3 text-blue-400">📞 درخواست‌های مشاوره</h2>
                <table class="w-full text-sm">
                    <thead class="bg-gray-700"><tr>
                        <th class="p-2">کاربر</th><th class="p-2">خدمت</th><th class="p-2">شماره</th><th class="p-2">تاریخ</th>
                    </tr></thead>
                    <tbody>{consults_rows}</tbody>
                </table>
            </div>

        </div>
    </body>
    </html>
    """


@app.post("/set-webhook")
def set_webhook(request: Request, bot_token: str = Form(...)):
    bot_token = bot_token.strip()
    set_setting("bot_token", bot_token)
    host = request.headers.get("host", "")
    domain = f"https://{host}"
    res = tg("setWebhook", {"url": f"{domain}/webhook"})
    ok = res and res.get("ok")
    msg = "✅ وبهوک ست شد" if ok else f"❌ خطا: {res}"
    return RedirectResponse(url=f"/?msg={msg}", status_code=303)


@app.post("/set-card")
def set_card(card_number: str = Form(""), card_owner: str = Form(""), card_bank: str = Form("")):
    set_setting("card_number", card_number.strip())
    set_setting("card_owner", card_owner.strip())
    set_setting("card_bank", card_bank.strip())
    return RedirectResponse(url="/?msg=✅ کارت ذخیره شد", status_code=303)


@app.post("/service/add")
def add_service(title: str = Form(...), description: str = Form("")):
    conn = get_db()
    conn.execute("INSERT INTO services (title, description) VALUES (?, ?)", (title, description))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)


@app.post("/service/delete/{sid}")
def del_service(sid: int):
    conn = get_db()
    conn.execute("DELETE FROM services WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)


@app.post("/product/add")
def add_product(title: str = Form(...), description: str = Form(""), price: int = Form(...), delivery: str = Form("")):
    conn = get_db()
    conn.execute(
        "INSERT INTO products (title, description, price, delivery) VALUES (?, ?, ?, ?)",
        (title, description, price, delivery),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)


@app.post("/product/delete/{pid}")
def del_product(pid: int):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)


@app.post("/payment/approve/{pid}")
def approve_payment(pid: int):
    conn = get_db()
    p = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if p:
        prod = conn.execute("SELECT * FROM products WHERE id=?", (p["product_id"],)).fetchone()
        conn.execute("UPDATE payments SET status='approved', reviewed_at=? WHERE id=?", (now(), pid))
        conn.commit()
        if prod:
            tg("sendMessage", {
                "chat_id": p["user_id"],
                "text": f"✅ پرداخت تایید شد\n\n📦 {prod['title']}\n\n🎁 تحویل:\n{prod['delivery'] or 'به‌زودی'}"
            })
    conn.close()
    return RedirectResponse(url="/?msg=✅ تایید شد", status_code=303)


@app.post("/payment/reject/{pid}")
def reject_payment(pid: int):
    conn = get_db()
    p = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if p:
        conn.execute("UPDATE payments SET status='rejected', reviewed_at=? WHERE id=?", (now(), pid))
        conn.commit()
        tg("sendMessage", {
            "chat_id": p["user_id"],
            "text": "❌ پرداخت شما رد شد. لطفاً با پشتیبانی تماس بگیرید."
        })
    conn.close()
    return RedirectResponse(url="/?msg=❌ رد شد", status_code=303)


# --- ربات تلگرام ---
MAIN_MENU = {
    "keyboard": [
        [{"text": "🛠️ خدمات"}],
        [{"text": "📦 محصولات"}],
        [{"text": "📞 پشتیبانی"}],
    ],
    "resize_keyboard": True,
}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    # پیام متنی
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        user_id = msg["chat"]["id"]
        username = msg["chat"].get("username", "")
        text = msg.get("text", "")

        if text == "/start":
            tg("sendMessage", {
                "chat_id": chat_id,
                "text": "👋 خوش آمدید!\nاز منوی زیر انتخاب کنید:",
                "reply_markup": MAIN_MENU,
            })

        elif text == "🛠️ خدمات":
            conn = get_db()
            services = conn.execute("SELECT * FROM services WHERE is_active=1").fetchall()
            conn.close()
            if not services:
                tg("sendMessage", {"chat_id": chat_id, "text": "خدمتی موجود نیست."})
            else:
                keyboard = [[{"text": s["title"], "callback_data": f"svc_{s['id']}"}] for s in services]
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "🛠️ خدمات ما:",
                    "reply_markup": {"inline_keyboard": keyboard},
                })

        elif text == "📦 محصولات":
            conn = get_db()
            products = conn.execute("SELECT * FROM products WHERE is_active=1").fetchall()
            conn.close()
            if not products:
                tg("sendMessage", {"chat_id": chat_id, "text": "محصولی موجود نیست."})
            else:
                keyboard = [[{"text": f"{p['title']} — {p['price']:,}", "callback_data": f"prd_{p['id']}"}] for p in products]
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "📦 محصولات:",
                    "reply_markup": {"inline_keyboard": keyboard},
                })

        elif text == "📞 پشتیبانی":
            tg("sendMessage", {
                "chat_id": chat_id,
                "text": "📞 برای ارتباط با پشتیبانی، پیام خود را ارسال کنید.",
            })

        elif text.startswith("/") is False and text:
            # اگه کاربر منتظر شماره بود (بعد از درخواست مشاوره)
            conn = get_db()
            last = conn.execute(
                "SELECT * FROM consultations WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (user_id,)
            ).fetchone()
            conn.close()
            # اگر پیام شبیه شماره تلفن بود
            if text.replace("+", "").replace(" ", "").isdigit() and len(text) >= 10:
                # اینجا شماره رو ذخیره می‌کنیم برای خدمت آخر
                # (state ساده: به‌عنوان مشاوره جدید)
                pass

    # کلیک روی دکمه‌های شیشه‌ای
    elif "callback_query" in data:
        cq = data["callback_query"]
        cq_id = cq["id"]
        chat_id = cq["message"]["chat"]["id"]
        user_id = cq["message"]["chat"]["id"]
        username = cq["message"]["chat"].get("username", "")
        cb = cq["data"]

        tg("answerCallbackQuery", {"callback_query_id": cq_id})

        # انتخاب خدمت → درخواست مشاوره
        if cb.startswith("svc_"):
            sid = int(cb.split("_")[1])
            conn = get_db()
            s = conn.execute("SELECT * FROM services WHERE id=?", (sid,)).fetchone()
            conn.close()
            if s:
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"🛠️ {s['title']}\n\n{s['description'] or ''}\n\n"
                            f"📞 لطفاً شماره تماس خود را ارسال کنید تا با شما تماس بگیریم.",
                })

        # انتخاب محصول → نمایش شماره کارت
        elif cb.startswith("prd_"):
            pid = int(cb.split("_")[1])
            conn = get_db()
            p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            conn.close()
            if p:
                card_number = get_setting("card_number", "—")
                card_owner = get_setting("card_owner", "—")
                card_bank = get_setting("card_bank", "—")
                text = (
                    f"📦 {p['title']}\n\n"
                    f"{p['description'] or ''}\n\n"
                    f"💰 مبلغ: {p['price']:,} تومان\n\n"
                    f"💳 شماره کارت:\n`{card_number}`\n"
                    f"👤 به نام: {card_owner}\n"
                    f"🏦 بانک: {card_bank}\n\n"
                    f"📷 بعد از واریز، عکس فیش را ارسال کنید."
                )
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                })

    return {"ok": True}
"""Цветочный магазин, Волжский, ул. Профсоюзов, 2. Только стандартная библиотека Python 3.10+.

Запуск: python3 flowers/app.py   (порт из PORT, по умолчанию 8080)
Настройки через переменные окружения — см. flowers/.env.example
"""
import hashlib, hmac, html, json, os, secrets, sqlite3, threading, time, urllib.parse, urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).parent
DB_PATH = os.environ.get("DB_PATH", str(BASE / "shop.db"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
SECRET = os.environ.get("SECRET_KEY") or secrets.token_hex(16)
SHOP = {
    "name": os.environ.get("SHOP_NAME", "Цветы на Профсоюзов"),
    "address": "г. Волжский, ул. Профсоюзов, 2",
    "phone": os.environ.get("SHOP_PHONE", "+7 (900) 000-00-00"),
    "hours": "Ежедневно 8:00–21:00",
}
TG_TOKEN, TG_CHAT = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
VK_TOKEN, VK_PEER = os.environ.get("VK_GROUP_TOKEN"), os.environ.get("VK_PEER_ID")
MAX_TOKEN, MAX_CHAT = os.environ.get("MAX_BOT_TOKEN"), os.environ.get("MAX_CHAT_ID")

DELIVERY = {"pickup": ("Самовывоз (Профсоюзов, 2)", 0), "city": ("Доставка по Волжскому", 300),
            "volgograd": ("Доставка в Волгоград", 700)}
EXTRAS = {"card": ("Открытка с вашим текстом", 150), "choco": ("Конфеты Raffaello", 450),
          "balloon": ("Шар с гелием «С днём рождения»", 350), "photo": ("Фото букета до отправки", 0)}
SUBS = {"week": ("Каждую неделю", 2490), "2weeks": ("Раз в 2 недели", 2690), "month": ("Раз в месяц", 2990)}
LOYALTY = 0.05  # 5% от заказа на бонусный счёт по номеру телефона
STATUSES = ["новый", "принят", "собирается", "в пути", "доставлен", "отменён"]

SEED = [
    ("Нежность", "Букеты", 2490, "15 кустовых роз, эвкалипт", "photo-1561181286-d3fee7d55364"),
    ("101 красная роза", "Розы", 12900, "Классика для главного повода", "photo-1518895949257-7621c3c786d7"),
    ("25 роз микс", "Розы", 4990, "Розы 60 см, разные цвета", "photo-1455659817273-f96807779a8a"),
    ("Пионовидные розы", "Букеты", 3890, "Пионовидные розы и маттиола", "photo-1563241527-3004b7be0ffd"),
    ("Тюльпаны 51", "Сезонные", 4590, "Голландские тюльпаны", "photo-1520763185298-1b434c919102"),
    ("Цветы в коробке", "Композиции", 3290, "Шляпная коробка с розами и гвоздикой", "photo-1487070183336-b863922373d4"),
    ("Хризантемы", "Сезонные", 1990, "Кустовые хризантемы, бюджетно и стойко", "photo-1508610048659-a06b669e3321"),
    ("Монобукет гербер", "Букеты", 1790, "Яркие герберы, 15 шт", "photo-1490750967868-88aa4486c946"),
]


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT, category TEXT, price INTEGER,
            description TEXT, image TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, created REAL, kind TEXT, name TEXT, phone TEXT,
            recipient TEXT, recipient_phone TEXT, address TEXT, delivery TEXT, when_ TEXT, card_text TEXT,
            items TEXT, extras TEXT, total INTEGER, bonus_used INTEGER DEFAULT 0, comment TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, phone TEXT, name TEXT, occasion TEXT,
            date TEXT, notified_year INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS bonuses(phone TEXT PRIMARY KEY, balance INTEGER DEFAULT 0);
        """)
        if not c.execute("SELECT 1 FROM products").fetchone():
            c.executemany("INSERT INTO products(name,category,price,description,image) VALUES(?,?,?,?,?)",
                          [(n, cat, p, d, f"https://images.unsplash.com/{img}?w=600&q=70&auto=format&fit=crop")
                           for n, cat, p, d, img in SEED])


def norm_phone(p):
    d = "".join(ch for ch in p or "" if ch.isdigit())
    if len(d) == 11 and d[0] in "78":
        d = d[1:]
    return "+7" + d[-10:] if len(d) >= 10 else ""


# ---------- уведомления ----------
def _post(url, data=None, headers=None, as_json=False):
    body = json.dumps(data).encode() if as_json else urllib.parse.urlencode(data or {}).encode()
    h = {"Content-Type": "application/json"} if as_json else {}
    h.update(headers or {})
    try:
        urllib.request.urlopen(urllib.request.Request(url, body, h), timeout=10).read()
    except Exception as e:  # уведомление не должно ронять оформление заказа
        print("notify error:", url.split("?")[0], e)


def notify(text):
    jobs = []
    if TG_TOKEN and TG_CHAT:
        jobs.append(lambda: _post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                  {"chat_id": TG_CHAT, "text": text}))
    if VK_TOKEN and VK_PEER:
        jobs.append(lambda: _post("https://api.vk.com/method/messages.send",
                                  {"access_token": VK_TOKEN, "v": "5.199", "peer_id": VK_PEER,
                                   "random_id": secrets.randbelow(2**31), "message": text}))
    if MAX_TOKEN and MAX_CHAT:
        jobs.append(lambda: _post(f"https://platform-api.max.ru/messages?chat_id={MAX_CHAT}",
                                  {"text": text}, {"Authorization": MAX_TOKEN}, as_json=True))
    for j in jobs:
        threading.Thread(target=j, daemon=True).start()
    if not jobs:
        print("[уведомление]\n" + text)


def order_text(o):
    lines = [f"🌸 Заказ №{o['id']} ({o['kind']})", f"Клиент: {o['name']} {o['phone']}"]
    if o["recipient"]:
        lines.append(f"Получатель: {o['recipient']} {o['recipient_phone']}")
    lines += [f"{o['delivery']}: {o['address'] or '-'}", f"Когда: {o['when_']}"]
    for it in json.loads(o["items"]):
        lines.append(f"• {it['name']} × {it['qty']} = {it['price'] * it['qty']} ₽")
    for e in json.loads(o["extras"]):
        lines.append(f"+ {e}")
    if o["card_text"]:
        lines.append(f"Открытка: «{o['card_text']}»")
    if o["comment"]:
        lines.append(f"Комментарий: {o['comment']}")
    if o["bonus_used"]:
        lines.append(f"Списано бонусов: {o['bonus_used']}")
    lines.append(f"ИТОГО: {o['total']} ₽ (оплата при получении)")
    return "\n".join(lines)


def reminder_loop():
    """Раз в час: за 3 дня до сохранённой даты шлём владельцу «позвоните клиенту»."""
    while True:
        try:
            today = time.localtime()
            soon = time.strftime("%m-%d", time.localtime(time.time() + 3 * 86400))
            with db() as c:
                for r in c.execute("SELECT * FROM reminders WHERE substr(date,6)=? AND notified_year<?",
                                   (soon, today.tm_year)).fetchall():
                    notify(f"📅 Через 3 дня «{r['occasion']}» у клиента {r['name']} {r['phone']}.\n"
                           f"Позвоните и предложите букет — это почти гарантированная продажа.")
                    c.execute("UPDATE reminders SET notified_year=? WHERE id=?", (today.tm_year, r["id"]))
        except Exception as e:
            print("reminder error:", e)
        time.sleep(3600)


# ---------- шаблоны ----------
def page(title, body, admin=False):
    nav = ('<a href="/admin">Заказы</a><a href="/admin/products">Товары</a>'
           '<a href="/admin/reminders">Даты клиентов</a><a href="/">На сайт</a>') if admin else \
          ('<a href="/#catalog">Каталог</a><a href="/#subscribe">Подписка</a>'
           '<a href="/#remind">Напомнить</a><a href="/#contacts">Контакты</a>'
           '<a href="/cart" class="cart-link">Корзина <b id="cart-count">0</b></a>')
    tpl = (BASE / "templates" / "base.html").read_text(encoding="utf-8")
    return (tpl.replace("{{title}}", html.escape(title)).replace("{{nav}}", nav)
            .replace("{{shop}}", html.escape(SHOP["name"])).replace("{{phone}}", html.escape(SHOP["phone"]))
            .replace("{{address}}", SHOP["address"]).replace("{{hours}}", SHOP["hours"]).replace("{{body}}", body))


E = html.escape


def money(v):
    return f"{v:,}".replace(",", " ") + " ₽"


def product_card(p):
    return (f'<div class="card"><img src="{E(p["image"])}" alt="{E(p["name"])}" loading="lazy">'
            f'<div class="card-b"><span class="tag">{E(p["category"])}</span><h3>{E(p["name"])}</h3>'
            f'<p>{E(p["description"])}</p><div class="row"><b>{money(p["price"])}</b>'
            f'<button onclick=\'addToCart({p["id"]},{json.dumps(p["name"])},{p["price"]})\'>В корзину</button>'
            f'</div></div></div>')


def home():
    with db() as c:
        prods = c.execute("SELECT * FROM products WHERE active=1 ORDER BY id").fetchall()
    cats = sorted({p["category"] for p in prods})
    filt = '<button class="chip on" onclick="filterCat(this,\'\')">Все</button>' + "".join(
        f'<button class="chip" onclick="filterCat(this,{json.dumps(cat)})">{E(cat)}</button>' for cat in cats)
    cards = "".join(f'<div data-cat="{E(p["category"])}">{product_card(p)}</div>' for p in prods)
    subs = "".join(f'<label class="sub"><input type="radio" name="plan" value="{k}" {"checked" if k == "2weeks" else ""}>'
                   f'<b>{v[0]}</b><span>{money(v[1])} / букет</span></label>' for k, v in SUBS.items())
    body = f"""
<section class="hero"><div><h1>Свежие цветы в Волжском<br><span>с доставкой за 90 минут</span></h1>
<p>Собираем при вас, фото букета перед отправкой, открытка в подарок. {SHOP['address']}.</p>
<a class="btn" href="#catalog">Выбрать букет</a> <a class="btn ghost" href="tel:{E(SHOP['phone'])}">Позвонить</a>
<ul class="perks"><li>🚚 Доставка от 300 ₽</li><li>📸 Фото до отправки</li><li>🎁 5% бонусами</li><li>🌙 Доставка к точному времени</li></ul></div></section>
<section id="catalog"><h2>Каталог</h2><div class="chips">{filt}</div><div class="grid">{cards}</div></section>
<section id="subscribe" class="panel"><h2>Цветочная подписка 🌷</h2>
<p>Свежий букет дома или в офисе по расписанию. Дешевле, чем покупать по одному, и не нужно помнить.</p>
<form method="post" action="/subscribe" class="form">{subs}
<input name="name" placeholder="Ваше имя" required><input name="phone" placeholder="Телефон" required>
<input name="address" placeholder="Адрес доставки" required><input name="start" type="date" required>
<button class="btn">Оформить подписку</button></form></section>
<section id="remind" class="panel alt"><h2>Не забудьте о важной дате</h2>
<p>Оставьте дату — за 3 дня мы напомним и предложим букет. Без спама, одно сообщение в год.</p>
<form method="post" action="/remind" class="form inline"><input name="name" placeholder="Ваше имя" required>
<input name="phone" placeholder="Телефон" required><input name="occasion" placeholder="Повод: ДР мамы, годовщина…" required>
<input name="date" type="date" required><button class="btn">Напомнить мне</button></form></section>
<section id="contacts"><h2>Контакты</h2><div class="contacts"><div>
<p>📍 {SHOP['address']}</p><p>📞 <a href="tel:{E(SHOP['phone'])}">{E(SHOP['phone'])}</a></p><p>🕗 {SHOP['hours']}</p>
<p><a href="/bonus">Проверить бонусы по номеру →</a></p></div>
<iframe src="https://yandex.ru/map-widget/v1/?text={urllib.parse.quote('Волжский, улица Профсоюзов, 2')}&z=16" loading="lazy"></iframe></div></section>"""
    return page(SHOP["name"], body)


def cart_page():
    deliv = "".join(f'<label><input type="radio" name="delivery" value="{k}" data-price="{v[1]}" '
                    f'{"checked" if k == "city" else ""} onchange="recalc()"> {v[0]} — {money(v[1]) if v[1] else "бесплатно"}</label>'
                    for k, v in DELIVERY.items())
    extras = "".join(f'<label><input type="checkbox" name="extra" value="{k}" data-price="{v[1]}" '
                     f'{"checked" if k == "photo" else ""} onchange="recalc()"> {v[0]} — {money(v[1]) if v[1] else "бесплатно"}</label>'
                     for k, v in EXTRAS.items())
    body = f"""<section><h2>Оформление заказа</h2><div id="cart-items"></div>
<form method="post" action="/order" class="form checkout" onsubmit="return submitOrder(this)">
<input type="hidden" name="items" id="items-field">
<h3>Ваши данные</h3><input name="name" placeholder="Ваше имя" required><input name="phone" placeholder="Ваш телефон" required>
<h3>Получатель (если не вы)</h3><input name="recipient" placeholder="Имя получателя"><input name="recipient_phone" placeholder="Телефон получателя">
<label class="check"><input type="checkbox" name="anon"> Анонимно — не говорить получателю, от кого</label>
<h3>Доставка</h3>{deliv}<input name="address" placeholder="Адрес (улица, дом, квартира)">
<input name="when" placeholder="Дата и время, например: завтра 14:00–15:00" required>
<h3>Добавить к букету</h3>{extras}<textarea name="card_text" placeholder="Текст открытки"></textarea>
<textarea name="comment" placeholder="Комментарий к заказу"></textarea>
<label class="check"><input type="checkbox" name="use_bonus"> Списать мои бонусы (до 30% заказа)</label>
<div class="total">Итого: <b id="total">0 ₽</b></div><p class="muted">Оплата наличными или переводом при получении.</p>
<button class="btn">Заказать</button></form></section>"""
    return page("Корзина", body)


def thanks(text):
    return page("Спасибо", f'<section class="panel center"><h2>Спасибо! 💐</h2><p>{text}</p>'
                           f'<a class="btn" href="/">На главную</a></section>')


# ---------- админка ----------
def admin_orders(q):
    st = q.get("status", [""])[0]
    with db() as c:
        rows = c.execute("SELECT * FROM orders" + (" WHERE status=?" if st else "") + " ORDER BY id DESC LIMIT 300",
                         (st,) if st else ()).fetchall()
        stats = c.execute("SELECT count(*) n, coalesce(sum(total),0) s FROM orders WHERE status!='отменён' "
                          "AND created>?", (time.time() - 30 * 86400,)).fetchone()
        subs = c.execute("SELECT count(*) FROM orders WHERE kind='подписка' AND status NOT IN ('отменён')").fetchone()[0]
    avg = stats["s"] // stats["n"] if stats["n"] else 0
    filt = " ".join(f'<a class="chip {"on" if s == st else ""}" href="/admin?status={urllib.parse.quote(s)}">{s or "все"}</a>'
                    for s in [""] + STATUSES)
    tr = ""
    for o in rows:
        items = ", ".join(f'{i["name"]}×{i["qty"]}' for i in json.loads(o["items"]))
        opts = "".join(f'<option {"selected" if s == o["status"] else ""}>{s}</option>' for s in STATUSES)
        tr += (f'<tr><td>#{o["id"]}<br><small>{time.strftime("%d.%m %H:%M", time.localtime(o["created"]))}</small></td>'
               f'<td>{E(o["kind"])}</td><td>{E(o["name"])}<br><a href="tel:{E(o["phone"])}">{E(o["phone"])}</a></td>'
               f'<td>{E(items)}<br><small>{E(", ".join(json.loads(o["extras"])))}</small></td>'
               f'<td>{E(o["delivery"])}<br><small>{E(o["address"] or "")} · {E(o["when_"])}</small></td>'
               f'<td><b>{money(o["total"])}</b></td><td><form method="post" action="/admin/status">'
               f'<input type="hidden" name="id" value="{o["id"]}"><select name="status" onchange="this.form.submit()">{opts}</select></form></td></tr>')
    body = f"""<section><h2>Заказы</h2><div class="stats"><div><b>{stats['n']}</b>заказов за 30 дней</div>
<div><b>{money(stats['s'])}</b>выручка за 30 дней</div><div><b>{money(avg)}</b>средний чек</div><div><b>{subs}</b>активных подписок</div></div>
<div class="chips">{filt}</div><div class="table"><table><tr><th>№</th><th>Тип</th><th>Клиент</th><th>Состав</th><th>Доставка</th><th>Сумма</th><th>Статус</th></tr>
{tr or '<tr><td colspan=7>Заказов пока нет</td></tr>'}</table></div></section>"""
    return page("Админка", body, admin=True)


def admin_products():
    with db() as c:
        rows = c.execute("SELECT * FROM products ORDER BY id").fetchall()
    tr = "".join(f"""<tr><form method="post" action="/admin/product"><input type="hidden" name="id" value="{p['id']}">
<td><img src="{E(p['image'])}" class="thumb"></td><td><input name="name" value="{E(p['name'])}"></td>
<td><input name="category" value="{E(p['category'])}"></td><td><input name="price" type="number" value="{p['price']}"></td>
<td><input name="description" value="{E(p['description'])}"><input name="image" value="{E(p['image'])}"></td>
<td><label><input type="checkbox" name="active" {"checked" if p['active'] else ""}> в продаже</label></td>
<td><button>Сохранить</button></td></form></tr>""" for p in rows)
    body = f"""<section><h2>Товары</h2><div class="table"><table><tr><th></th><th>Название</th><th>Категория</th><th>Цена</th>
<th>Описание / ссылка на фото</th><th></th><th></th></tr>{tr}</table></div>
<h3>Добавить товар</h3><form method="post" action="/admin/product" class="form inline">
<input name="name" placeholder="Название" required><input name="category" placeholder="Категория" required>
<input name="price" type="number" placeholder="Цена" required><input name="description" placeholder="Описание">
<input name="image" placeholder="Ссылка на фото"><input type="hidden" name="active" value="on"><button class="btn">Добавить</button></form></section>"""
    return page("Товары", body, admin=True)


def admin_reminders():
    with db() as c:
        rows = c.execute("SELECT * FROM reminders ORDER BY substr(date,6)").fetchall()
    tr = "".join(f'<tr><td>{E(r["date"][5:])}</td><td>{E(r["occasion"])}</td><td>{E(r["name"])}</td>'
                 f'<td><a href="tel:{E(r["phone"])}">{E(r["phone"])}</a></td></tr>' for r in rows)
    body = (f'<section><h2>Важные даты клиентов</h2><p class="muted">За 3 дня до даты вам придёт уведомление — '
            f'позвоните клиенту и предложите букет.</p><div class="table"><table><tr><th>Дата</th><th>Повод</th>'
            f'<th>Клиент</th><th>Телефон</th></tr>{tr or "<tr><td colspan=4>Пока пусто</td></tr>"}</table></div></section>')
    return page("Даты", body, admin=True)


def login_page(err=""):
    return page("Вход", f'<section class="panel center"><h2>Вход в панель</h2>{f"<p class=err>{err}</p>" if err else ""}'
                        f'<form method="post" action="/admin/login" class="form"><input type="password" name="password" '
                        f'placeholder="Пароль" required autofocus><button class="btn">Войти</button></form></section>', admin=False)


def sign(v):
    return v + "." + hmac.new(SECRET.encode(), v.encode(), hashlib.sha256).hexdigest()


class H(BaseHTTPRequestHandler):
    def send(self, body, code=200, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, to, headers=None):
        self.send("", 303, headers={"Location": to, **(headers or {})})

    def is_admin(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        v = c.get("adm")
        return bool(v) and hmac.compare_digest(v.value, sign("ok"))

    def form(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 100_000:
            return {}
        return {k: v if len(v) > 1 else v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        if p == "/":
            return self.send(home())
        if p == "/cart":
            return self.send(cart_page())
        if p == "/bonus":
            ph = norm_phone(q.get("phone", [""])[0])
            bal = None
            if ph:
                with db() as c:
                    r = c.execute("SELECT balance FROM bonuses WHERE phone=?", (ph,)).fetchone()
                bal = r["balance"] if r else 0
            res = f"<p>На номере {E(ph)}: <b>{bal} бонусов</b> (1 бонус = 1 ₽)</p>" if bal is not None else ""
            return self.send(page("Бонусы", f'<section class="panel center"><h2>Мои бонусы</h2>{res}<form class="form">'
                                            f'<input name="phone" placeholder="Телефон" required><button class="btn">Проверить</button>'
                                            f'</form><p class="muted">5% от каждого заказа возвращаются бонусами.</p></section>'))
        if p.startswith("/static/"):
            f = (BASE / "static" / Path(p).name)
            if f.is_file():
                ct = {"css": "text/css", "js": "application/javascript"}.get(f.suffix[1:], "application/octet-stream")
                return self.send(f.read_bytes(), ctype=ct + "; charset=utf-8", headers={"Cache-Control": "max-age=3600"})
        if p == "/healthz":
            return self.send("ok", ctype="text/plain")
        if p.startswith("/admin"):
            if p == "/admin/logout":
                return self.redirect("/", {"Set-Cookie": "adm=; Max-Age=0; Path=/"})
            if not self.is_admin():
                return self.send(login_page())
            return self.send({"/admin": lambda: admin_orders(q), "/admin/products": admin_products,
                              "/admin/reminders": admin_reminders}.get(p, lambda: admin_orders(q))())
        self.send(page("Не найдено", '<section class="panel center"><h2>Страница не найдена</h2></section>'), 404)

    def do_POST(self):
        p, f = urllib.parse.urlparse(self.path).path, self.form()
        if p == "/order":
            return self.create_order(f)
        if p == "/subscribe":
            plan = SUBS.get(f.get("plan"), SUBS["month"])
            oid = self.save_order(kind="подписка", name=f.get("name", ""), phone=norm_phone(f.get("phone")),
                                  address=f.get("address", ""), delivery=DELIVERY["city"][0],
                                  when_=f"с {f.get('start', '')}, {plan[0].lower()}",
                                  items=[{"name": f"Подписка: {plan[0]}", "qty": 1, "price": plan[1]}], extras=[],
                                  total=plan[1])
            return self.send(thanks(f"Подписка №{oid} оформлена. Мы позвоним, чтобы согласовать детали."))
        if p == "/remind":
            with db() as c:
                c.execute("INSERT INTO reminders(phone,name,occasion,date) VALUES(?,?,?,?)",
                          (norm_phone(f.get("phone")), f.get("name", "")[:80], f.get("occasion", "")[:120], f.get("date", "")[:10]))
            notify(f"📅 Новая дата клиента: {f.get('occasion')} — {f.get('date')}, {f.get('name')} {f.get('phone')}")
            return self.send(thanks("Записали! Напомним за 3 дня до даты."))
        if p == "/admin/login":
            if hmac.compare_digest(f.get("password", ""), ADMIN_PASSWORD):
                return self.redirect("/admin", {"Set-Cookie": f"adm={sign('ok')}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"})
            time.sleep(1)
            return self.send(login_page("Неверный пароль"), 401)
        if not self.is_admin():
            return self.redirect("/admin")
        with db() as c:
            if p == "/admin/status" and f.get("status") in STATUSES:
                c.execute("UPDATE orders SET status=? WHERE id=?", (f["status"], f.get("id")))
            elif p == "/admin/product":
                vals = (f.get("name", ""), f.get("category", ""), int(f.get("price") or 0), f.get("description", ""),
                        f.get("image", ""), 1 if f.get("active") else 0)
                if f.get("id"):
                    c.execute("UPDATE products SET name=?,category=?,price=?,description=?,image=?,active=? WHERE id=?",
                              vals + (f["id"],))
                else:
                    c.execute("INSERT INTO products(name,category,price,description,image,active) VALUES(?,?,?,?,?,?)", vals)
                return self.redirect("/admin/products")
        self.redirect(self.headers.get("Referer") or "/admin")

    def create_order(self, f):
        try:
            raw = json.loads(f.get("items") or "[]")
        except ValueError:
            raw = []
        with db() as c:
            prices = {r["id"]: r for r in c.execute("SELECT * FROM products WHERE active=1")}
        items = [{"name": prices[int(i["id"])]["name"], "price": prices[int(i["id"])]["price"],
                  "qty": max(1, min(99, int(i.get("qty", 1))))} for i in raw if int(i.get("id", 0)) in prices]
        if not items:
            return self.redirect("/cart")
        phone = norm_phone(f.get("phone"))
        dkey = f.get("delivery") if f.get("delivery") in DELIVERY else "city"
        ex = f.get("extra", [])
        ex = [ex] if isinstance(ex, str) else ex
        ex = [k for k in ex if k in EXTRAS]
        total = sum(i["price"] * i["qty"] for i in items) + DELIVERY[dkey][1] + sum(EXTRAS[k][1] for k in ex)
        bonus_used = 0
        with db() as c:
            if f.get("use_bonus") and phone:
                r = c.execute("SELECT balance FROM bonuses WHERE phone=?", (phone,)).fetchone()
                bonus_used = min(r["balance"] if r else 0, int(total * 0.3))
                c.execute("UPDATE bonuses SET balance=balance-? WHERE phone=?", (bonus_used, phone))
            if phone:
                c.execute("INSERT INTO bonuses(phone,balance) VALUES(?,?) ON CONFLICT(phone) DO UPDATE SET balance=balance+?",
                          (phone, int((total - bonus_used) * LOYALTY), int((total - bonus_used) * LOYALTY)))
        comment = f.get("comment", "")
        if f.get("anon"):
            comment = "АНОНИМНО. " + comment
        oid = self.save_order(kind="букет", name=f.get("name", ""), phone=phone, recipient=f.get("recipient", ""),
                              recipient_phone=f.get("recipient_phone", ""), address=f.get("address", ""),
                              delivery=DELIVERY[dkey][0], when_=f.get("when", ""), card_text=f.get("card_text", ""),
                              items=items, extras=[EXTRAS[k][0] for k in ex], total=total - bonus_used,
                              bonus_used=bonus_used, comment=comment)
        self.send(thanks(f"Заказ №{oid} принят на сумму {money(total - bonus_used)}. Перезвоним в течение 10 минут. "
                         f"Вам начислено {int((total - bonus_used) * LOYALTY)} бонусов."
                         "<script>localStorage.removeItem('cart')</script>"))

    def save_order(self, **o):
        o.setdefault("recipient", ""), o.setdefault("recipient_phone", ""), o.setdefault("card_text", "")
        o.setdefault("comment", ""), o.setdefault("bonus_used", 0)
        o = {k: (v[:500] if isinstance(v, str) else v) for k, v in o.items()}
        o["items"], o["extras"] = json.dumps(o["items"], ensure_ascii=False), json.dumps(o["extras"], ensure_ascii=False)
        o["created"], o["status"] = time.time(), "новый"
        with db() as c:
            cols = list(o)
            cur = c.execute(f"INSERT INTO orders({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [o[k] for k in cols])
            o["id"] = cur.lastrowid
        notify(order_text(o))
        return o["id"]

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    init_db()
    threading.Thread(target=reminder_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    print(f"http://0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()

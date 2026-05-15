"""
Football Prediction Bot — Single File Production Version
Optimized for 10,000+ users/day
"""
import logging, os, json, hashlib, threading, requests
from datetime import datetime, timedelta, time as dtime
from flask import Flask
from threading import Thread
from groq import Groq
from tavily import TavilyClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                           CallbackQueryHandler, filters, ContextTypes)

# ═══════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY", "5d44806d63094fdab0090cc5faef770c")
TAVILY_API_KEY   = os.environ.get("TAVILY_API_KEY", "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")
CHANNEL          = "@dasi_bet"
ADMIN_ID         = 7046072164
FREE_LIMIT       = 3
REFERRAL_GOAL    = 5
VIP_DAYS         = 30
POINTS_PER_VIP   = 100
CACHE_TTL_HOURS  = 6
SEASON           = "2025"
PORT             = 8080
BOT_USERNAME     = os.environ.get("BOT_USERNAME", "football_analysist2_bot")
DB_FILE          = "data/users.json"
CACHE_FILE       = "data/cache.json"

LEAGUES = {
    "PL":  {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 الإنجليزي",   "id": 2021},
    "PD":  {"name": "🇪🇸 الإسباني",     "id": 2014},
    "BL1": {"name": "🇩🇪 الألماني",     "id": 2002},
    "SA":  {"name": "🇮🇹 الإيطالي",     "id": 2019},
    "FL1": {"name": "🇫🇷 الفرنسي",      "id": 2015},
    "CL":  {"name": "🌍 أبطال أوروبا", "id": 2001},
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)
groq_client   = Groq(api_key=GROQ_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
_db_lock      = threading.Lock()
_cache_lock   = threading.Lock()

# ═══════════════════════════════════════════════
#  PROMPTS
# ═══════════════════════════════════════════════
ANALYSIS_PROMPT = """أنت محلل كرة قدم خبير. حلل مباريات موسم 2025/2026 فقط.
رد بنفس لغة المستخدم (عربي أو إنجليزي).

قدم التحليل بهذا الشكل الاحترافي المختصر:

━━━━━━━━━━━━━━━━━━
⚽ **[ف1] vs [ف2]**
━━━━━━━━━━━━━━━━━━

🎮 **طريقة اللعب:**
• [ف1]: [النظام التكتيكي + أسلوب اللعب]
• [ف2]: [النظام التكتيكي + أسلوب اللعب]

📊 **الشكل الأخير:**
• [ف1]: [آخر 5 نتائج]
• [ف2]: [آخر 5 نتائج]

🏆 **التوقع الرئيسي:**
• فوز [الفريق الأقوى]: **X%** | الأود: **X.XX**
• فرصة مزدوجة ([ف] فوز أو تعادل): **X%** | الأود: **X.XX**

⚽ **الأهداف:**
• عدد الأهداف المتوقع: **[X-X أهداف]**
• أوفر [X].5 أهداف | الأود: **X.XX**
• أندر [X].5 أهداف | الأود: **X.XX**
• كلا الفريقين يسجلان: **[نعم/لا]** | الأود: **X.XX**

🔄 **الركنيات:**
• ركنيات [ف1]: **[X-X]** | الأود: **X.XX**
• ركنيات [ف2]: **[X-X]** | الأود: **X.XX**
• إجمالي الركنيات: أوفر/أندر **[X].5** | الأود: **X.XX**

🟨 **البطاقات الصفراء:**
• إجمالي متوقع: **[X-X بطاقة]**
• أوفر [X].5 بطاقات | الأود: **X.XX**
• أندر [X].5 بطاقات | الأود: **X.XX**

🔍 **أبرز الأخبار:** [إصابات أو أخبار مهمة]

💡 **خلاصة — أفضل رهان:**
• التوصية: **[الرهان الأفضل]**
• الأود: **X.XX**
• نسبة الثقة: **X%**
━━━━━━━━━━━━━━━━━━
⚠️ للترفيه فقط"""

SAFE_BET_PROMPT = """أنت محلل كرة قدم. من المباريات التالية اختر الأكثر أماناً لموسم 2025/2026.

🔒 **أضمن رهان اليوم**
━━━━━━━━━━━━━━━━━━
⚽ **[ف1] vs [ف2]**
✅ التوقع: **[التوقع]**
💰 الأود: **[X.XX]**
📊 الثقة: **[X]%**
💡 السبب: [جملة واحدة]
━━━━━━━━━━━━━━━━━━
⚠️ للترفيه فقط"""

COUPON_PROMPT = """أنت محلل كرة قدم محترف. المستخدم يريد قسيمة بأود إجمالي يقارب: {target_odd}

اختر أفضل المباريات المتاحة ورهاناتها (فوز، فرصة مزدوجة، أهداف، إلخ) بحيث يكون حاصل ضرب الأودد يساوي تقريباً {target_odd}.
لا يهم عدد المباريات، المهم الوصول للأود المطلوب بأعلى نسبة أمان.

قدم القسيمة بهذا الشكل:

🎫 **القسيمة الذهبية**
🎯 الأود المطلوب: **{target_odd}**
━━━━━━━━━━━━━━━━━━
[رقم]. [ف1 vs ف2]
   ✅ [الرهان] | 💰 [X.XX]

[كرر لكل مباراة]
━━━━━━━━━━━━━━━━━━
💰 الأود الفعلي: **[X.XX]**
📊 نسبة النجاح: **[X]%**
⚠️ للترفيه فقط"""

# ═══════════════════════════════════════════════
#  CACHE
# ═══════════════════════════════════════════════
def _ensure_dirs():
    os.makedirs("data", exist_ok=True)

def _load_cache() -> dict:
    _ensure_dirs()
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r") as f:
        return json.load(f)

def _save_cache(c: dict):
    _ensure_dirs()
    with _cache_lock:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(c, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CACHE_FILE)

def cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()[:12]

def cache_get(key: str):
    c = _load_cache()
    if key not in c:
        return None
    t = datetime.strptime(c[key]["time"], "%Y-%m-%d %H:%M")
    if datetime.now() - t > timedelta(hours=CACHE_TTL_HOURS):
        return None
    return c[key]["data"]

def cache_set(key: str, data):
    c = _load_cache()
    c[key] = {"data": data, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
    if len(c) > 500:
        for k, _ in sorted(c.items(), key=lambda x: x[1]["time"])[:100]:
            del c[k]
    _save_cache(c)

def cache_clear():
    _save_cache({})

# ═══════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════
def db_load() -> dict:
    _ensure_dirs()
    if not os.path.exists(DB_FILE):
        return {"users": {}, "total_requests": 0}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def db_save(db: dict):
    _ensure_dirs()
    with _db_lock:
        tmp = DB_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DB_FILE)

def db_user(db: dict, uid: int, update=None) -> dict:
    k = str(uid)
    if k not in db["users"]:
        db["users"][k] = {
            "name": getattr(getattr(update, "effective_user", None), "full_name", ""),
            "username": getattr(getattr(update, "effective_user", None), "username", ""),
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "requests_today": 0, "bonus_requests": 0,
            "last_request_date": "", "total_requests": 0,
            "vip": False, "vip_expiry": "", "blocked": False,
            "points": 0, "referrals": [], "referred_by": "",
            "history": [], "ratings": [],
        }
        db_save(db)
    return db["users"][k]

def is_vip(db: dict, uid: int) -> bool:
    if uid == ADMIN_ID:
        return True
    u = db_user(db, uid)
    if not u["vip"]:
        return False
    if u["vip_expiry"] and datetime.now().strftime("%Y-%m-%d") > u["vip_expiry"]:
        u["vip"] = False
        db_save(db)
        return False
    return True

def get_limit(db: dict, uid: int) -> int:
    return 9999 if is_vip(db, uid) else FREE_LIMIT + db_user(db, uid).get("bonus_requests", 0)

def has_quota(db: dict, uid: int) -> bool:
    if is_vip(db, uid):
        return True
    u = db_user(db, uid)
    today = datetime.now().strftime("%Y-%m-%d")
    if u["last_request_date"] != today:
        u["requests_today"] = 0
        u["last_request_date"] = today
        db_save(db)
    return u["requests_today"] < get_limit(db, uid)

def remaining(db: dict, uid: int):
    if is_vip(db, uid):
        return "♾️"
    u = db_user(db, uid)
    today = datetime.now().strftime("%Y-%m-%d")
    used = u["requests_today"] if u["last_request_date"] == today else 0
    return max(0, get_limit(db, uid) - used)

def consume(db: dict, uid: int, match: str):
    u = db_user(db, uid)
    today = datetime.now().strftime("%Y-%m-%d")
    if u["last_request_date"] != today:
        u["requests_today"] = 0
        u["last_request_date"] = today
    u["requests_today"] += 1
    u["total_requests"] += 1
    db["total_requests"] = db.get("total_requests", 0) + 1
    u["history"].append({"match": match, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    u["history"] = u["history"][-20:]
    _add_points(db, uid, 5)

def _add_points(db: dict, uid: int, pts: int) -> bool:
    u = db_user(db, uid)
    u["points"] = u.get("points", 0) + pts
    if u["points"] >= POINTS_PER_VIP:
        u["points"] -= POINTS_PER_VIP
        u["vip"] = True
        u["vip_expiry"] = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        db_save(db)
        return True
    db_save(db)
    return False

def activate_vip(db: dict, uid: int) -> str:
    u = db_user(db, uid)
    u["vip"] = True
    expiry = (datetime.now() + timedelta(days=VIP_DAYS)).strftime("%Y-%m-%d")
    u["vip_expiry"] = expiry
    db_save(db)
    return expiry

def handle_referral(db: dict, new_uid: int, ref_id: str):
    if str(new_uid) == ref_id:
        return
    ref = db_user(db, int(ref_id))
    if str(new_uid) in ref.get("referrals", []):
        return
    ref.setdefault("referrals", []).append(str(new_uid))
    db_user(db, new_uid)["referred_by"] = ref_id
    if len(ref["referrals"]) % REFERRAL_GOAL == 0:
        ref["bonus_requests"] = ref.get("bonus_requests", 0) + 1
    _add_points(db, int(ref_id), 10)
    db_save(db)

# ═══════════════════════════════════════════════
#  FOOTBALL API
# ═══════════════════════════════════════════════
_FAPI_BASE    = "https://api.football-data.org/v4"
_FAPI_HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY}

def _fapi(endpoint: str, params: dict = None):
    try:
        r = requests.get(f"{_FAPI_BASE}/{endpoint}", headers=_FAPI_HEADERS,
                         params=params, timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.error(f"Football API: {e}")
        return None

def get_matches(league_code: str, date: str) -> list:
    key = f"matches_{league_code}_{date}"
    cached = cache_get(key)
    if cached:
        return json.loads(cached)
    lid  = LEAGUES[league_code]["id"]
    data = _fapi(f"competitions/{lid}/matches",
                 {"dateFrom": date, "dateTo": date, "season": SEASON})
    if not data:
        return []
    result = [{"home": m["homeTeam"]["name"], "away": m["awayTeam"]["name"],
               "time": m["utcDate"][11:16], "league": LEAGUES[league_code]["name"]}
              for m in data.get("matches", [])]
    cache_set(key, json.dumps(result))
    return result

def get_all_matches(date: str) -> list:
    key = f"all_{date}"
    cached = cache_get(key)
    if cached:
        return json.loads(cached)
    all_m = []
    for code in LEAGUES:
        all_m.extend(get_matches(code, date))
    cache_set(key, json.dumps(all_m))
    return all_m

# ═══════════════════════════════════════════════
#  AI SERVICE
# ═══════════════════════════════════════════════
def _groq(system: str, user: str, tokens: int = 900) -> str:
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile", max_tokens=tokens,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}]
    )
    return r.choices[0].message.content

def _news(t1: str, t2: str) -> str:
    key = f"news_{cache_key(t1+t2)}"
    cached = cache_get(key)
    if cached:
        return cached
    try:
        res = tavily_client.search(
            query=f"{t1} vs {t2} 2025 injuries form news",
            max_results=3, search_depth="basic"
        )
        text = "\n".join(r.get("content", "")[:250] for r in res.get("results", []))
        cache_set(key, text)
        return text
    except Exception as e:
        logger.warning(f"Tavily: {e}")
        return ""

def ai_analyze(match: str) -> str:
    key = cache_key(match)
    cached = cache_get(key)
    if cached:
        return cached + "\n\n⚡ _من الكاش_"
    parts = match.lower().replace(" vs ", " ").replace(" ضد ", " ").split()
    t1, t2 = (parts[0], parts[-1]) if len(parts) > 1 else (match, "")
    news   = _news(t1, t2)
    content = f"المباراة: {match}\n\nأخبار:\n{news}" if news else f"المباراة: {match}"
    result = _groq(ANALYSIS_PROMPT, content, tokens=900)
    cache_set(key, result)
    return result

def ai_safe_bet(matches: list) -> str:
    key = f"safe_{datetime.now().strftime('%Y-%m-%d')}"
    cached = cache_get(key)
    if cached:
        return cached
    lines  = "\n".join(f"{m['home']} vs {m['away']} ({m.get('league','')})" for m in matches[:15])
    result = _groq(SAFE_BET_PROMPT, f"مباريات اليوم:\n{lines}", tokens=300)
    cache_set(key, result)
    return result

def ai_coupon(target_odd: str, matches: list) -> str:
    key = f"coupon_{cache_key(target_odd)}_{datetime.now().strftime('%Y-%m-%d')}"
    cached = cache_get(key)
    if cached:
        return cached
    lines  = "\n".join(f"{m['home']} vs {m['away']} ({m.get('league','')})" for m in matches[:20])
    prompt = COUPON_PROMPT.format(target_odd=target_odd)
    result = _groq(prompt, f"المباريات المتاحة اليوم:\n{lines}", tokens=700)
    cache_set(key, result)
    return result

# ═══════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════
def kb_subscribe():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL[1:]}")],
        [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")]
    ])

def kb_main(vip: bool):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 مباريات اليوم",  callback_data="leagues_today"),
         InlineKeyboardButton("📆 مباريات الغد",   callback_data="leagues_tomorrow")],
        [InlineKeyboardButton("🔒 أضمن رهان",      callback_data="safe_bet"),
         InlineKeyboardButton("⚽ توقع مباراة",    callback_data="predict")],
        [InlineKeyboardButton("🎫 قسيمة ذهبية",   callback_data="coupon"),
         InlineKeyboardButton("👥 أحل صديقاً",     callback_data="referral")],
        [InlineKeyboardButton("📊 إحصائياتي",      callback_data="my_stats"),
         InlineKeyboardButton("💎 VIP نشط ✅" if vip else "💎 VIP $5/شهر",
                              callback_data="my_stats" if vip else "vip_info")]
    ])

def kb_leagues(day: str):
    rows = []
    items = list(LEAGUES.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(items[i][1]["name"], callback_data=f"league_{items[i][0]}_{day}")]
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(items[i+1][1]["name"], callback_data=f"league_{items[i+1][0]}_{day}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)

def kb_matches(match_list: list, league_code: str, day: str):
    rows = []
    for i, m in enumerate(match_list[:10]):
        rows.append([InlineKeyboardButton(
            f"⚽ {m['home']} vs {m['away']}  🕐{m['time']}",
            callback_data=f"match_{league_code}_{day}_{i}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"leagues_{day}")])
    return InlineKeyboardMarkup(rows)

def kb_vip():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 اشترك $5/شهر", callback_data="pay_vip")],
        [InlineKeyboardButton("🔙 رجوع",          callback_data="back_main")]
    ])

def kb_rating():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✍️ أرسل تقييمك", callback_data="write_review")
    ]])

def kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])

# ═══════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════
def is_arabic(text: str) -> bool:
    return sum(1 for c in text if '\u0600' <= c <= '\u06FF') > len(text) * 0.2

def ref_link(uid: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"

async def check_sub(uid: int, context) -> bool:
    if uid == ADMIN_ID:
        return True
    try:
        m = await context.bot.get_chat_member(CHANNEL, uid)
        return m.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception:
        return False

async def safe_send(msg, text: str, **kw):
    try:
        await msg.reply_text(text, parse_mode="Markdown", **kw)
    except Exception:
        await msg.reply_text(text, **kw)

async def safe_edit(query, text: str, **kw):
    try:
        await query.edit_message_text(text, parse_mode="Markdown", **kw)
    except Exception:
        try:
            await query.edit_message_text(text, **kw)
        except Exception:
            pass

def day_date(day: str) -> str:
    if day == "tomorrow":
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")

def day_label(day: str) -> str:
    return "الغد 📆" if day == "tomorrow" else "اليوم 📅"

# ═══════════════════════════════════════════════
#  HOME MESSAGE
# ═══════════════════════════════════════════════
WELCOME_IMAGE = "data/welcome_file_id.txt"  # يحفظ file_id بعد أول رفع

async def send_home(msg, uid: int, db: dict):
    u      = db_user(db, uid)
    badge  = "💎 VIP" if is_vip(db, uid) else "🆓 مجاني"
    rem    = remaining(db, uid)
    points = u.get("points", 0)
    name   = getattr(msg, "chat", msg).first_name if hasattr(msg, "chat") else ""

    caption = (
        f"👑 *أهلاً بك في DASI BET* {name}!\n\n"
        f"🏆 بوت التوقعات الرياضية الاحترافي\n"
        f"تحليلات دقيقة.. توقعات احترافية.. أرباح أكبر 🚀\n\n"
        f"🏷️ {badge} | 🎯 متبقي: *{rem}* | ⭐ {points}/100\n\n"
        f"اختر من القائمة 👇"
    )

    keyboard = kb_main(is_vip(db, uid))

    # حاول إرسال الصورة
    try:
        # إذا عندنا file_id محفوظ استخدمه مباشرة (أسرع)
        if os.path.exists(WELCOME_IMAGE):
            with open(WELCOME_IMAGE, "r") as f:
                file_id = f.read().strip()
            await msg.reply_photo(photo=file_id, caption=caption,
                                  parse_mode="Markdown", reply_markup=keyboard)
        else:
            # أول مرة: ارفع الصورة من الملف واحفظ file_id
            with open("welcome.png", "rb") as img:
                sent = await msg.reply_photo(photo=img, caption=caption,
                                             parse_mode="Markdown", reply_markup=keyboard)
            # احفظ file_id لاستخدامه لاحقاً
            fid = sent.photo[-1].file_id
            os.makedirs("data", exist_ok=True)
            with open(WELCOME_IMAGE, "w") as f:
                f.write(fid)
    except Exception as e:
        logger.warning(f"Photo send failed: {e} — falling back to text")
        await safe_send(msg, caption, reply_markup=keyboard)

# ═══════════════════════════════════════════════
#  HANDLERS — USER
# ═══════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db  = db_load()
    uid = update.effective_user.id
    db_user(db, uid, update)

    if context.args and context.args[0].startswith("ref_"):
        handle_referral(db, uid, context.args[0][4:])

    if not await check_sub(uid, context):
        await update.message.reply_text(
            f"⛔ *عذراً! يجب الاشتراك في قناتنا أولاً لاستخدام البوت*\n\n"
            f"📢 القناة: {CHANNEL}\n\n"
            f"اشترك ثم اضغط *تحقق من الاشتراك* ✅",
            parse_mode="Markdown",
            reply_markup=kb_subscribe()
        )
        return
    await send_home(update.message, uid, db)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db   = db_load()
    uid  = update.effective_user.id
    text = update.message.text.strip()

    if not await check_sub(uid, context):
        await update.message.reply_text(
            f"⛔ *يجب الاشتراك في {CHANNEL} أولاً!*",
            parse_mode="Markdown",
            reply_markup=kb_subscribe()
        )
        return

    u = db_user(db, uid, update)
    if u.get("blocked"):
        return

    mode = context.user_data.pop("mode", "predict")

    # Review mode
    if mode == "review":
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"⭐ *تقييم جديد*\n\n"
                f"👤 {u.get('name','?')} | ID: `{uid}`\n\n"
                f"💬 {text}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await safe_send(update.message, "✅ شكراً! تم إرسال تقييمك للإدارة 🙏")
        return

    # Coupon mode — user sends target odd
    if mode == "coupon":
        try:
            float(text.replace(",", "."))
        except Exception:
            await safe_send(update.message, "❌ أرسل رقماً فقط مثل: `5.00` أو `10.00`")
            context.user_data["mode"] = "coupon"
            return
        wait = await update.message.reply_text("🎫 جاري بناء القسيمة...")
        try:
            matches = get_all_matches(datetime.now().strftime("%Y-%m-%d"))
            result  = ai_coupon(text, matches)
            await wait.delete()
            await safe_send(update.message, result)
        except Exception as e:
            logger.error(e)
            await wait.edit_text("❌ حدث خطأ، حاول مرة أخرى.")
        return

    # Predict mode
    if not has_quota(db, uid):
        link = ref_link(uid)
        await safe_send(update.message,
            f"⛔ *انتهت توقعاتك اليوم!*\n\n"
            f"🆓 شارك رابطك — كل {REFERRAL_GOAL} أصدقاء = توقع مجاني\n`{link}`\n\n"
            f"💎 أو اشترك VIP بـ $5/شهر",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 اشترك VIP",    callback_data="vip_info")],
                [InlineKeyboardButton("👥 رابط الإحالة", callback_data="referral")]
            ])
        )
        return

    wait = await update.message.reply_text("🔍 جاري التحليل...")
    try:
        result = ai_analyze(text)
        consume(db, uid, text)
        db_save(db)
        await wait.delete()
        await safe_send(update.message, result)
        rem = remaining(db, uid)
        await update.message.reply_text(
            f"🎯 متبقي: *{rem}* — هل تريد تقييم هذا التوقع؟",
            parse_mode="Markdown",
            reply_markup=kb_rating()
        )
    except Exception as e:
        logger.error(e)
        await wait.edit_text("❌ حدث خطأ، حاول مرة أخرى.")

# ═══════════════════════════════════════════════
#  HANDLERS — CALLBACKS
# ═══════════════════════════════════════════════
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    db  = db_load()
    uid = q.from_user.id
    d   = q.data

    # ── Check subscription ──
    if d == "check_sub":
        if await check_sub(uid, context):
            await q.edit_message_text("✅ تم التحقق! اضغط /start")
        else:
            await safe_edit(q, f"❌ لم تشترك بعد في {CHANNEL}!", reply_markup=kb_subscribe())

    # ── Leagues today / tomorrow ──
    elif d in ("leagues_today", "leagues_tomorrow"):
        day = "today" if d == "leagues_today" else "tomorrow"
        await safe_edit(q, f"🏆 *اختر الدوري — {day_label(day)}:*", reply_markup=kb_leagues(day))

    # ── League selected ──
    elif d.startswith("league_"):
        parts = d.split("_")
        code  = parts[1]
        day   = parts[2] if len(parts) > 2 else "today"
        if code not in LEAGUES:
            await q.edit_message_text("❌ دوري غير معروف.")
            return
        name = LEAGUES[code]["name"]
        await q.edit_message_text(f"⏳ جاري جلب مباريات {name}...")
        date    = day_date(day)
        matches = get_matches(code, date)
        context.user_data[f"m_{code}_{day}"] = matches
        if not matches:
            await safe_edit(q, f"😔 لا توجد مباريات في {name} {day_label(day)}.", reply_markup=kb_back())
        else:
            await safe_edit(q,
                f"📅 *{name} — {day_label(day)}*\n\nاضغط على مباراة للتحليل 👇",
                reply_markup=kb_matches(matches, code, day)
            )

    # ── Match selected ──
    elif d.startswith("match_"):
        parts = d.split("_")
        code  = parts[1]
        day   = parts[2]
        idx   = int(parts[3])
        matches = context.user_data.get(f"m_{code}_{day}", [])
        if not matches or idx >= len(matches):
            await q.edit_message_text("❌ حدث خطأ، ارجع وحاول.")
            return
        if not has_quota(db, uid):
            await safe_edit(q, "⛔ *انتهت توقعاتك اليوم!*\n\n💎 اشترك VIP.", reply_markup=kb_vip())
            return
        m = matches[idx]
        mt = f"{m['home']} vs {m['away']}"
        await q.edit_message_text(f"🔍 جاري تحليل {mt}...")
        try:
            result = ai_analyze(mt)
            consume(db, uid, mt)
            db_save(db)
            await safe_edit(q, result)
            rem = remaining(db, uid)
            await context.bot.send_message(q.message.chat_id,
                f"🎯 متبقي: *{rem}* — هل تريد تقييم هذا التوقع؟",
                parse_mode="Markdown", reply_markup=kb_rating()
            )
        except Exception as e:
            logger.error(e)
            await q.edit_message_text("❌ حدث خطأ، حاول مرة أخرى.")

    # ── Safe bet ──
    elif d == "safe_bet":
        await q.edit_message_text("🔍 جاري البحث عن أضمن رهان اليوم...")
        matches = get_all_matches(datetime.now().strftime("%Y-%m-%d"))
        if not matches:
            await safe_edit(q, "😔 لا توجد مباريات كافية اليوم.", reply_markup=kb_back())
            return
        try:
            result = ai_safe_bet(matches)
            await safe_edit(q, result, reply_markup=kb_back())
        except Exception as e:
            logger.error(e)
            await q.edit_message_text("❌ حدث خطأ، حاول مرة أخرى.")

    # ── Predict ──
    elif d == "predict":
        context.user_data["mode"] = "predict"
        await safe_edit(q, "⚽ *أرسل اسم المباراة:*\n\nمثال: ريال مدريد vs برشلونة")

    # ── Coupon ──
    elif d == "coupon":
        if not is_vip(db, uid):
            await safe_edit(q,
                "🔒 *القسيمة الذهبية للـ VIP فقط!*\n\n"
                "💎 اشترك بـ $5/شهر للحصول على قسيمة بالأود الذي تريده!",
                reply_markup=kb_vip()
            )
            return
        context.user_data["mode"] = "coupon"
        await safe_edit(q,
            "🎫 *القسيمة الذهبية*\n\n"
            "أرسل الأود الإجمالي الذي تريده:\n\n"
            "مثال: `5.00` أو `10.00` أو `20.00`\n\n"
            "سأختار أفضل المباريات والرهانات للوصول لهذا الأود 🎯"
        )

    # ── Write review ──
    elif d == "write_review":
        context.user_data["mode"] = "review"
        await safe_edit(q,
            "✍️ *أرسل تقييمك الآن:*\n\n"
            "اكتب رأيك في البوت أو أي خطأ لاحظته وسيصل مباشرة للإدارة 📩"
        )

    # ── Referral ──
    elif d == "referral":
        u    = db_user(db, uid, q)
        refs = len(u.get("referrals", []))
        next_b = REFERRAL_GOAL - (refs % REFERRAL_GOAL)
        link = ref_link(uid)
        await safe_edit(q,
            f"👥 *نظام الإحالة*\n\n"
            f"🔗 رابطك الشخصي:\n`{link}`\n\n"
            f"📊 إحالاتك: *{refs}* | تحتاج *{next_b}* للتوقع التالي\n"
            f"⭐ كل إحالة = 10 نقاط\n"
            f"🎁 كل {REFERRAL_GOAL} إحالات = توقع مجاني إضافي يومياً",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 شارك الرابط", switch_inline_query=f"أفضل بوت توقعات! {link}")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
        )

    # ── My stats ──
    elif d == "my_stats":
        u     = db_user(db, uid, q)
        badge = "💎 VIP" if is_vip(db, uid) else "🆓 مجاني"
        await safe_edit(q,
            f"📊 *إحصائياتك:*\n\n"
            f"🏷️ {badge}\n"
            f"🎯 متبقي اليوم: {remaining(db, uid)}\n"
            f"📈 إجمالي طلباتك: {u['total_requests']}\n"
            f"👥 إحالاتك: {len(u.get('referrals',[]))}\n"
            f"⭐ نقاطك: {u.get('points',0)}/100\n"
            f"🎁 توقعات مكسوبة: {u.get('bonus_requests',0)}\n"
            f"📅 انضمت: {u['joined']}",
            reply_markup=kb_back()
        )

    # ── VIP info ──
    elif d == "vip_info":
        await safe_edit(q,
            f"💎 *VIP — $5/شهر*\n\n"
            "✅ توقعات غير محدودة\n"
            "✅ القسيمة الذهبية بأود مخصص\n"
            "✅ أضمن رهان يومي\n"
            "✅ مباريات اليوم والغد\n"
            "✅ تحليل فوري بلا انتظار\n\n"
            "تواصل مع المشرف للاشتراك 👇",
            reply_markup=kb_vip()
        )

    # ── Pay VIP ──
    elif d == "pay_vip":
        await safe_edit(q,
            "💳 *للاشتراك VIP:*\n\n"
            "👤 @Admin\n"
            "💰 $5/شهر\n"
            "⚡ تفعيل فوري\n\n"
            "طرق الدفع:\n• USDT (TRC20)\n• PayPal\n• تحويل بنكي"
        )

    # ── Back main ──
    elif d == "back_main":
        u      = db_user(db, uid)
        badge  = "💎 VIP" if is_vip(db, uid) else "🆓 مجاني"
        rem    = remaining(db, uid)
        points = u.get("points", 0)
        name   = q.from_user.first_name
        await safe_edit(q,
            f"🤖 *بوت توقعات المباريات*\n\n"
            f"👤 أهلاً {name}!\n"
            f"🏷️ {badge} | 🎯 متبقي: *{rem}* | ⭐ {points}/100\n\n"
            f"اختر من القائمة 👇",
            reply_markup=kb_main(is_vip(db, uid))
        )

# ═══════════════════════════════════════════════
#  HANDLERS — ADMIN
# ═══════════════════════════════════════════════
def admin_only(fn):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        await fn(update, context)
    return wrapper

@admin_only
async def cmd_admin(update, context):
    db    = db_load()
    today = datetime.now().strftime("%Y-%m-%d")
    total  = len(db["users"])
    vip_c  = sum(1 for u in db["users"].values() if u.get("vip"))
    active = sum(1 for u in db["users"].values() if u.get("last_request_date") == today)
    ratings = [r["stars"] for u in db["users"].values() for r in u.get("ratings", []) if "stars" in r]
    avg = round(sum(ratings)/len(ratings), 1) if ratings else 0
    await update.message.reply_text(
        f"👑 *لوحة التحكم*\n\n"
        f"👥 {total} مستخدم | 💎 {vip_c} VIP | 🟢 {active} اليوم\n"
        f"⭐ متوسط التقييم: {avg}/5\n\n"
        f"`/vip [ID]` — تفعيل VIP\n"
        f"`/unvip [ID]` — إلغاء VIP\n"
        f"`/ban [ID]` — حظر\n"
        f"`/unban [ID]` — فك حظر\n"
        f"`/broadcast [رسالة]` — رسالة جماعية\n"
        f"`/users` — قائمة المستخدمين\n"
        f"`/stats` — إحصائيات\n"
        f"`/clearcache` — مسح الكاش",
        parse_mode="Markdown"
    )

@admin_only
async def cmd_vip(update, context):
    if not context.args:
        await update.message.reply_text("استخدام: /vip [ID]")
        return
    db  = db_load()
    uid = context.args[0]
    if uid not in db["users"]:
        await update.message.reply_text("❌ المستخدم غير موجود")
        return
    expiry = activate_vip(db, int(uid))
    await update.message.reply_text(f"✅ VIP مفعّل لـ `{uid}` حتى {expiry}", parse_mode="Markdown")
    try:
        await context.bot.send_message(int(uid), "🎉 *تم تفعيل VIP!*\n\nاضغط /start 🚀", parse_mode="Markdown")
    except Exception:
        pass

@admin_only
async def cmd_unvip(update, context):
    if not context.args:
        return
    db = db_load()
    uid = context.args[0]
    if uid in db["users"]:
        db["users"][uid]["vip"] = False
        db_save(db)
        await update.message.reply_text(f"✅ إلغاء VIP لـ `{uid}`", parse_mode="Markdown")

@admin_only
async def cmd_ban(update, context):
    if not context.args:
        return
    db = db_load()
    uid = context.args[0]
    if uid in db["users"]:
        db["users"][uid]["blocked"] = True
        db_save(db)
        await update.message.reply_text(f"⛔ حظر `{uid}`", parse_mode="Markdown")

@admin_only
async def cmd_unban(update, context):
    if not context.args:
        return
    db = db_load()
    uid = context.args[0]
    if uid in db["users"]:
        db["users"][uid]["blocked"] = False
        db_save(db)
        await update.message.reply_text(f"✅ فك حظر `{uid}`", parse_mode="Markdown")

@admin_only
async def cmd_broadcast(update, context):
    if not context.args:
        await update.message.reply_text("استخدام: /broadcast [الرسالة]")
        return
    db   = db_load()
    msg  = " ".join(context.args)
    sent = failed = 0
    for uid in db["users"]:
        try:
            await context.bot.send_message(int(uid), f"📢 *من الإدارة:*\n\n{msg}", parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ أُرسلت: {sent} | ❌ فشل: {failed}")

@admin_only
async def cmd_users(update, context):
    db    = db_load()
    lines = []
    for uid, u in list(db["users"].items())[-20:]:
        b = "💎" if u.get("vip") else "🆓"
        x = "⛔" if u.get("blocked") else ""
        lines.append(f"{b}{x} `{uid}` {u.get('name','?')} | {u.get('total_requests',0)}")
    await update.message.reply_text("👥 *آخر 20:*\n\n" + "\n".join(lines), parse_mode="Markdown")

@admin_only
async def cmd_stats(update, context):
    db    = db_load()
    today = datetime.now().strftime("%Y-%m-%d")
    active = sum(1 for u in db["users"].values() if u.get("last_request_date") == today)
    vip_c  = sum(1 for u in db["users"].values() if u.get("vip"))
    refs   = sum(len(u.get("referrals",[])) for u in db["users"].values())
    await update.message.reply_text(
        f"📊 *إحصائيات:*\n\n"
        f"👥 {len(db['users'])} مستخدم\n"
        f"💎 {vip_c} VIP\n"
        f"🟢 {active} نشط اليوم\n"
        f"📈 {db.get('total_requests',0)} طلب إجمالي\n"
        f"👥 {refs} إحالة إجمالي",
        parse_mode="Markdown"
    )

@admin_only
async def cmd_clearcache(update, context):
    cache_clear()
    await update.message.reply_text("✅ تم مسح الكاش!")

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    db    = db_load()
    today = datetime.now().strftime("%Y-%m-%d")
    active = sum(1 for u in db["users"].values() if u.get("last_request_date") == today)
    try:
        await context.bot.send_message(ADMIN_ID,
            f"📊 *تقرير يومي — {today}*\n\n"
            f"👥 {len(db['users'])} مستخدم\n"
            f"🟢 {active} نشط اليوم\n"
            f"📈 {db.get('total_requests',0)} طلب إجمالي",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Daily report: {e}")

# ═══════════════════════════════════════════════
#  FLASK + MAIN
# ═══════════════════════════════════════════════
_flask = Flask(__name__)

@_flask.route("/")
def health():
    return "✅ OK", 200

def main():
    os.makedirs("data", exist_ok=True)
    Thread(target=lambda: _flask.run(host="0.0.0.0", port=PORT, use_reloader=False), daemon=True).start()
    logger.info(f"✅ Flask on port {PORT}")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # User
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Admin
    app.add_handler(CommandHandler("admin",      cmd_admin))
    app.add_handler(CommandHandler("vip",        cmd_vip))
    app.add_handler(CommandHandler("unvip",      cmd_unvip))
    app.add_handler(CommandHandler("ban",        cmd_ban))
    app.add_handler(CommandHandler("unban",      cmd_unban))
    app.add_handler(CommandHandler("broadcast",  cmd_broadcast))
    app.add_handler(CommandHandler("users",      cmd_users))
    app.add_handler(CommandHandler("stats",      cmd_stats))
    app.add_handler(CommandHandler("clearcache", cmd_clearcache))

    # Daily report 08:00
    app.job_queue.run_daily(daily_report, time=dtime(8, 0))

    logger.info("✅ Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

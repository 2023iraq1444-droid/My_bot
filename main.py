import json
import os
import logging
import aiohttp
from datetime import date
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.utils.exceptions import BadRequest, ChatNotFound, Unauthorized

from keep_alive import keep_alive

API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise RuntimeError("الرجاء ضبط متغير البيئة BOT_TOKEN قبل تشغيل البوت.")

ADMIN_ID = 5957783780

# ---------- ملفات التخزين ----------
MENU_FILE = 'menu.json'
USERS_FILE = 'users.json'
SETTINGS_FILE = 'settings.json'
ASIA_FILE = 'asia_requests.json'
SMM_ORDERS_FILE = 'smm_orders.json'
CHANNELS_FILE = 'channels.json'

# ---------- إعدادات آسيا سيل (افتراضية، قابلة للتعديل من لوحة المالك) ----------
ASIA_RECEIVER_NUMBER_DEFAULT = "07726590999"
ASIA_POINTS_PER_DOLLAR_DEFAULT = 30000
ASIA_DOLLAR_OPTIONS = [1, 2, 3, 5, 10, 15, 20, 30, 50, 75, 100]

# ================================================================
#                مزوّدات SMM (smmfollows + JustAnotherPanel)
# ================================================================
PROVIDERS = {
    "smmfollows": {
        "label": "🟢 SMMFollows",
        "short": "SMMFollows",
        "url": os.getenv('SMMFOLLOWS_API_URL', 'https://smmfollows.com/api/v2'),
        "key_env": "SMMFOLLOWS_API_KEY",
    },
    "jap": {
        "label": "🔵 JustAnotherPanel",
        "short": "JAP",
        "url": os.getenv('JAP_API_URL', 'https://justanotherpanel.com/api/v2'),
        "key_env": "JAP_API_KEY",
    },
}


def provider_key(provider: str) -> str:
    """يجلب مفتاح الـ API الخاص بالمزود من متغيرات البيئة."""
    info = PROVIDERS.get(provider)
    if not info:
        return ""
    return os.getenv(info["key_env"], "")


def provider_label(provider: str) -> str:
    info = PROVIDERS.get(provider)
    return info["label"] if info else "—"


async def smm_api_call(provider: str, payload: dict) -> dict:
    """ينفّذ طلب POST إلى المزود المحدد."""
    info = PROVIDERS.get(provider)
    if not info:
        return {"error": f"مزود غير معروف: {provider}"}
    api_key = provider_key(provider)
    if not api_key:
        return {"error": f"مفتاح {info['short']} غير مضبوط (متغير البيئة {info['key_env']})"}
    data = {"key": api_key, **payload}
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(info["url"], data=data) as resp:
                txt = await resp.text()
                try:
                    return json.loads(txt)
                except Exception:
                    return {"error": f"رد غير متوقع: {txt[:200]}"}
    except Exception as e:
        logging.warning(f"SMM API error ({provider}): {e}")
        return {"error": str(e)}


async def smm_add_order(provider: str, service_id: int, link: str, quantity: int) -> dict:
    return await smm_api_call(provider, {
        "action": "add",
        "service": int(service_id),
        "link": link,
        "quantity": int(quantity),
    })


async def smm_order_status(provider: str, order_id) -> dict:
    return await smm_api_call(provider, {"action": "status", "order": int(order_id)})


async def smm_balance(provider: str) -> dict:
    return await smm_api_call(provider, {"action": "balance"})


# ================================================================
#                       باقات النجوم
# ================================================================
STARS_PACKAGES = [
    {"stars": 1,   "points": 400,    "label": "⭐ نجمة واحدة"},
    {"stars": 2,   "points": 800,    "label": "⭐⭐ نجمتان"},
    {"stars": 10,  "points": 4000,   "label": "✨ ١٠ نجمات"},
    {"stars": 50,  "points": 20000,  "label": "🌟 ٥٠ نجمة"},
    {"stars": 100, "points": 40000,  "label": "💫 ١٠٠ نجمة"},
]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

BOT_USERNAME = ""

# ================================================================
#                       الإعدادات (settings)
# ================================================================
DEFAULT_SETTINGS = {
    "daily_gift_points": 75,
    "referral_points": 200,
    "owner_username": "",

    # واجهة عامة
    "bot_title": "ترويجكم",
    "welcome_text": "🌟 أهلاً بك في بوت <b>ترويجكم</b>!",
    "return_text": "مرحباً بعودتك 👋",
    "footer_text": "",                     # يضاف أسفل كل رد رئيسي إن وُجد
    "support_username": "",                # @username للتواصل
    "maintenance_mode": False,
    "maintenance_text": "🚧 البوت تحت الصيانة الآن، يرجى المحاولة لاحقاً.",

    # تشغيل/تعطيل ميزات
    "daily_gift_enabled": True,
    "referral_enabled": True,
    "transfer_enabled": True,
    "stars_enabled": True,
    "asiacell_enabled": True,
    "force_sub_enabled": True,             # يفعّل/يعطّل الاشتراك الإجباري كاملاً
    "show_balance_in_main": True,

    # تنسيق بريميوم (للحسابات المميزة)
    "premium_styling": True,               # استخدام spoiler/blockquote/ديكورات
    "decor_top": "✨━━━━━━━━━━━━━━━━━━━━✨",
    "decor_bottom": "✨━━━━━━━━━━━━━━━━━━━━✨",
    "use_spoiler_balance": False,          # يخفي الرصيد بسبويلر
    "use_expandable_quotes": True,         # blockquote قابل للطي

    # ألوان/إيموجيات للخدمات (لكل منصة)
    "service_emoji_instagram": "🌸",
    "service_emoji_telegram": "💎",
    "service_emoji_tiktok": "🔥",
    "service_emoji_default": "✨",

    # آسيا سيل
    "asia_receiver_number": ASIA_RECEIVER_NUMBER_DEFAULT,
    "asia_points_per_dollar": ASIA_POINTS_PER_DOLLAR_DEFAULT,
}


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                merged = dict(DEFAULT_SETTINGS)
                merged.update(data)
                return merged
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings():
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


settings = load_settings()


# ================================================================
#               الاشتراك الإجباري (قنوات/كروبات)
# ================================================================
def load_channels():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_channels():
    with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


channels = load_channels()
_next_channel_id = max([int(c.get("id", 0)) for c in channels] + [0]) + 1


def new_channel_id() -> str:
    global _next_channel_id
    cid = str(_next_channel_id)
    _next_channel_id += 1
    return cid


async def get_unsubscribed(user_id: int) -> list:
    """يعيد قائمة القنوات/الكروبات التي لم يشترك بها المستخدم."""
    if not settings.get("force_sub_enabled", True) or not channels:
        return []
    if user_id == ADMIN_ID:
        return []
    not_joined = []
    for ch in channels:
        chat = ch.get("chat", "")
        if not chat:
            continue
        try:
            member = await bot.get_chat_member(chat, user_id)
            status = getattr(member, "status", "")
            if status in ("left", "kicked"):
                not_joined.append(ch)
        except (ChatNotFound, Unauthorized, BadRequest) as e:
            # البوت ليس أدمن في القناة → نعتبرها كأنها مفقودة فقط لو فيها رابط
            logging.warning(f"force-sub check failed for {chat}: {e}")
            # نسجّلها كقناة لازم اشتراك حتى يحاول المستخدم الانضمام
            not_joined.append(ch)
        except Exception as e:
            logging.warning(f"force-sub unexpected error {chat}: {e}")
    return not_joined


def force_sub_keyboard(missing: list) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for ch in missing:
        title = ch.get("title") or ch.get("chat") or "قناة"
        url = ch.get("url") or (f"https://t.me/{ch['chat'].lstrip('@')}" if ch.get("chat", "").startswith("@") else None)
        if url:
            kb.add(types.InlineKeyboardButton(f"🔗 {title}", url=url))
    kb.add(types.InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="fsub:check"))
    return kb


async def enforce_subscription(c_or_msg) -> bool:
    """يتحقق من الاشتراك الإجباري. يعيد True إذا المستخدم مسموح له بالمتابعة.
    وإلا يرسل رسالة الاشتراك ويعيد False."""
    user = c_or_msg.from_user
    missing = await get_unsubscribed(user.id)
    if not missing:
        return True
    text_lines = [
        "🔒 <b>الاشتراك الإجباري</b>",
        "",
        "للمتابعة في استخدام البوت يجب الاشتراك في القنوات/الكروبات التالية:",
        "",
    ]
    for ch in missing:
        title = ch.get("title") or ch.get("chat") or "قناة"
        text_lines.append(f"  • {title}")
    text_lines.append("")
    text_lines.append("بعد الاشتراك اضغط <b>✅ تحققت من الاشتراك</b>.")
    txt = "\n".join(text_lines)
    target = c_or_msg.message if isinstance(c_or_msg, types.CallbackQuery) else c_or_msg
    try:
        await target.answer(txt, parse_mode='HTML', reply_markup=force_sub_keyboard(missing))
    except Exception:
        pass
    if isinstance(c_or_msg, types.CallbackQuery):
        try:
            await c_or_msg.answer()
        except Exception:
            pass
    return False


# ================================================================
#                       المستخدمون (users)
# ================================================================
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                return {int(k): v for k, v in raw.items()}
        except Exception:
            pass
    return {}


def save_users():
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({str(k): v for k, v in users.items()}, f, ensure_ascii=False, indent=2)


users = load_users()


def register_user(user_id: int, referred_by: int | None = None) -> bool:
    if user_id in users:
        return False
    users[user_id] = {
        "points": 0,
        "last_daily": "",
        "referred_by": referred_by if referred_by and referred_by != user_id else None,
        "referrals": 0,
    }
    save_users()
    return True


def add_points(user_id: int, amount: int):
    u = users.setdefault(user_id, {"points": 0, "last_daily": "", "referred_by": None, "referrals": 0})
    u["points"] = int(u.get("points", 0)) + int(amount)
    save_users()


def get_points(user_id: int) -> int:
    return int(users.get(user_id, {}).get("points", 0))


def calc_total(price_per_1000: int, qty: int) -> int:
    if price_per_1000 <= 0 or qty <= 0:
        return 0
    return (int(price_per_1000) * int(qty) + 999) // 1000


# ================================================================
#                  ديكورات بريميوم للمحتوى
# ================================================================
def decorate(text: str, header: str = "", footer_extra: str = "") -> str:
    """يلفّ النص بالديكورات المختارة من المالك (إن مفعّلة)."""
    parts = []
    if header:
        parts.append(header)
    if settings.get("premium_styling", True) and settings.get("decor_top"):
        parts.append(settings["decor_top"])
    parts.append(text)
    if settings.get("premium_styling", True) and settings.get("decor_bottom"):
        parts.append(settings["decor_bottom"])
    extra = (settings.get("footer_text") or "").strip()
    if footer_extra:
        parts.append(footer_extra)
    if extra:
        parts.append(extra)
    return "\n".join(parts)


def maybe_spoiler(value: str) -> str:
    if settings.get("premium_styling", True) and settings.get("use_spoiler_balance", False):
        return f"<tg-spoiler>{value}</tg-spoiler>"
    return value


# ================================================================
#                         القائمة (menu)
# ================================================================
DEFAULT_MENU = [
    {"id": "1", "label": "🎁 الهدية اليومية", "kind": "daily_gift", "text": "", "children": []},
    {"id": "2", "label": "🔗 رابط الدعوة", "kind": "referral", "text": "", "children": []},
    {
        "id": "3", "label": "💳 شحن نقاط", "kind": "regular",
        "text": "💳 شحن النقاط\nاختر طريقة الشحن المناسبة لك:",
        "children": [
            {"id": "31", "label": "⭐ النجوم", "kind": "stars_charge",
             "text": "", "children": []},
            {"id": "32", "label": "📱 آسيا سيل", "kind": "asiacell_charge",
             "text": "", "children": []},
            {"id": "33", "label": "💵 بيناسي", "kind": "regular",
             "text": "💵 الشحن عبر بيناسي\n\n(اضغط زر تعديل الرد لتغيير هذا النص من لوحة الأدمن)", "children": []},
            {"id": "34", "label": "🔄 أخرى", "kind": "regular",
             "text": "🔄 طرق شحن أخرى\n\n(اضغط زر تعديل الرد لتغيير هذا النص من لوحة الأدمن)", "children": []},
        ],
    },
    {
        "id": "4", "label": "🛒 الخدمات", "kind": "regular",
        "text": "🛒 الخدمات\nاختر المنصة:",
        "children": [
            {"id": "41", "label": "📷 إنستغرام", "kind": "regular",
             "text": "📷 خدمات إنستغرام\nاختر الخدمة المطلوبة:",
             "platform": "instagram", "display": "vertical",
             "children": []},
            {"id": "42", "label": "✈️ تيليجرام", "kind": "regular",
             "text": "✈️ خدمات تيليجرام\nاختر الخدمة المطلوبة:",
             "platform": "telegram", "display": "vertical",
             "children": []},
            {"id": "43", "label": "🎵 تيك توك", "kind": "regular",
             "text": "🎵 خدمات تيك توك\nاختر الخدمة المطلوبة:",
             "platform": "tiktok", "display": "vertical",
             "children": []},
        ],
    },
    {"id": "5", "label": "👑 مالك البوت", "kind": "regular",
     "text": "👑 مالك البوت\n\n(اضغط زر تعديل الرد لتغيير هذا النص من لوحة الأدمن)", "children": []},
    {"id": "6", "label": "👤 حسابي", "kind": "account", "text": "", "children": []},
    {"id": "7", "label": "💸 تحويل نقاط", "kind": "transfer", "text": "", "children": []},
]


def _ensure_kind(items):
    """Backward-compat: تكميل الحقول المفقودة على عناصر القائمة القديمة."""
    changed = False
    for it in items:
        if "kind" not in it:
            txt = it.get("text", "")
            if txt == "__ACCOUNT__":
                it["kind"] = "account"
            elif txt == "__STATS__":
                it["kind"] = "stats"
            else:
                it["kind"] = "regular"
            changed = True
        if "children" not in it:
            it["children"] = []
            changed = True
        if it.get("kind") == "service_item":
            if "description" not in it:
                it["description"] = ""
                changed = True
            if "min_qty" not in it:
                it["min_qty"] = 1
                changed = True
            if "max_qty" not in it:
                it["max_qty"] = 10000
                changed = True
            if "smm_service_id" not in it:
                it["smm_service_id"] = 0
                changed = True
            # المزوّد الافتراضي للخدمات القديمة = smmfollows
            if "smm_provider" not in it:
                it["smm_provider"] = "smmfollows" if int(it.get("smm_service_id", 0) or 0) > 0 else ""
                changed = True
        if _ensure_kind(it["children"]):
            changed = True
    return changed


def _ensure_transfer_button(items):
    for it in items:
        if it.get("kind") == "transfer":
            return False
    items.append({
        "id": "7", "label": "💸 تحويل نقاط",
        "kind": "transfer", "text": "", "children": []
    })
    return True


def _ensure_charge_kinds(items):
    changed = False
    for it in items:
        label = (it.get("label") or "").strip()
        kind = it.get("kind", "regular")
        if kind == "regular":
            if "نجوم" in label or "نجمة" in label or "النجوم" in label or "⭐" in label:
                it["kind"] = "stars_charge"
                it["children"] = []
                changed = True
            elif "آسيا" in label or "اسيا" in label or "آسياسيل" in label:
                it["kind"] = "asiacell_charge"
                it["children"] = []
                changed = True
        if it.get("children"):
            if _ensure_charge_kinds(it["children"]):
                changed = True
    return changed


def _ensure_platform_displays(items):
    """يضيف حقل platform و display للأقسام الرئيسية للمنصات (انستا/تلي/تيك توك)."""
    changed = False
    for it in items:
        label = (it.get("label") or "")
        if it.get("kind") == "regular":
            plat = None
            if any(x in label for x in ("📷", "إنستغرام", "انستغرام", "انستا", "instagram", "Instagram")):
                plat = "instagram"
            elif any(x in label for x in ("✈️", "تيليجرام", "تيلي", "Telegram", "telegram")):
                plat = "telegram"
            elif any(x in label for x in ("🎵", "تيك توك", "TikTok", "tiktok")):
                plat = "tiktok"
            if plat:
                if it.get("platform") != plat:
                    it["platform"] = plat
                    changed = True
                if "display" not in it:
                    it["display"] = "vertical"
                    changed = True
        if it.get("children"):
            if _ensure_platform_displays(it["children"]):
                changed = True
    return changed


def load_menu():
    if os.path.exists(MENU_FILE):
        try:
            with open(MENU_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                has_new_kinds = any(
                    it.get("kind") in ("daily_gift", "referral", "account")
                    for it in data
                )
                if not has_new_kinds:
                    return [json.loads(json.dumps(it)) for it in DEFAULT_MENU]
                _ensure_kind(data)
                _ensure_transfer_button(data)
                _ensure_charge_kinds(data)
                _ensure_platform_displays(data)
                return data
        except Exception:
            pass
    return [json.loads(json.dumps(it)) for it in DEFAULT_MENU]


menu = load_menu()


def _all_ids_in(items):
    out = []
    for it in items:
        try:
            out.append(int(it["id"]))
        except (ValueError, KeyError):
            pass
        out.extend(_all_ids_in(it.get("children", [])))
    return out


next_id = max(_all_ids_in(menu) + [100]) + 1


def save_menu():
    with open(MENU_FILE, 'w', encoding='utf-8') as f:
        json.dump(menu, f, ensure_ascii=False, indent=2)


def new_id():
    global next_id
    nid = str(next_id)
    next_id += 1
    return nid


def find_item(item_id, items=None, parent=None):
    if items is None:
        items = menu
    for it in items:
        if it["id"] == item_id:
            return it, items, parent
        result = find_item(item_id, it.get("children", []), it)
        if result[0]:
            return result
    return None, None, None


def find_parent_of(item_id):
    """يعيد عنصر الأب لزر معين (للحصول على platform مثلاً)."""
    _, _, parent = find_item(item_id)
    return parent


# ================================================================
#                          عرض القائمة للمستخدم
# ================================================================
PLATFORM_EMOJI_KEY = {
    "instagram": "service_emoji_instagram",
    "telegram": "service_emoji_telegram",
    "tiktok": "service_emoji_tiktok",
}


def get_platform_emoji(platform: str) -> str:
    key = PLATFORM_EMOJI_KEY.get(platform or "", "")
    if key:
        return settings.get(key) or settings.get("service_emoji_default", "✨")
    return settings.get("service_emoji_default", "✨")


def style_service_label(item, parent_platform: str) -> str:
    """يضيف ايموجي ملوّن أمام اسم الخدمة لعرض جذاب."""
    label = item.get("label", "")
    emoji = get_platform_emoji(parent_platform)
    # نتجنب تكرار الايموجي إذا كان موجود مسبقاً في بداية النص
    if label.startswith(emoji):
        return label
    return f"{emoji} {label}"


def items_keyboard(items, prefix="u", parent_item=None):
    """يبني لوحة الأزرار. لو الأب من نوع منصة (انستا/تلي/تيك توك) أو
    display=vertical → يعرض زر واحد بكل صف مع تلوين."""
    parent_platform = (parent_item or {}).get("platform", "")
    is_vertical = (parent_item or {}).get("display") == "vertical"
    # نعتبر أي قسم منصة تلقائياً عمودي مهما كان الإعداد
    if parent_platform in ("instagram", "telegram", "tiktok"):
        is_vertical = True

    kb = types.InlineKeyboardMarkup(row_width=2 if not is_vertical else 1)

    if is_vertical:
        for item in items:
            text = (style_service_label(item, parent_platform)
                    if item.get("kind") == "service_item" else item.get("label", ""))
            kb.add(types.InlineKeyboardButton(text, callback_data=f"{prefix}:{item['id']}"))
        return kb

    row = []
    for item in items:
        row.append(types.InlineKeyboardButton(item["label"], callback_data=f"{prefix}:{item['id']}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb


def user_keyboard():
    return items_keyboard(menu, prefix="u")


# ================================================================
#                          منطق الأزرار الخاصة
# ================================================================
KIND_LABELS = {
    "regular": "🔘 زر عادي (نص)",
    "daily_gift": "🎁 الهدية اليومية",
    "referral": "🔗 رابط الدعوة",
    "service_item": "🛒 خدمة بسعر (يخصم نقاط)",
    "account": "👤 الحساب (معلومات المستخدم)",
    "stats": "📊 الإحصائيات",
    "transfer": "💸 تحويل نقاط بين المستخدمين",
    "stars_charge": "⭐ شحن عبر النجوم (Telegram Stars)",
    "asiacell_charge": "📱 شحن عبر آسيا سيل",
}


# ================================================================
#                    طلبات شحن آسيا سيل المعلقة
# ================================================================
def load_asia_requests():
    if os.path.exists(ASIA_FILE):
        try:
            with open(ASIA_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                return {str(k): v for k, v in raw.items()}
        except Exception:
            pass
    return {}


def save_asia_requests():
    with open(ASIA_FILE, 'w', encoding='utf-8') as f:
        json.dump(asia_requests, f, ensure_ascii=False, indent=2)


asia_requests = load_asia_requests()
_next_asia_req = max([int(k) for k in asia_requests.keys()] + [1000]) + 1


def load_smm_orders():
    if os.path.exists(SMM_ORDERS_FILE):
        try:
            with open(SMM_ORDERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_smm_orders():
    with open(SMM_ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(smm_orders, f, ensure_ascii=False, indent=2)


smm_orders = load_smm_orders()


def new_asia_req_id() -> str:
    global _next_asia_req
    rid = str(_next_asia_req)
    _next_asia_req += 1
    return rid


user_state = {}


# ================================================================
#                  واجهة شحن النجوم (Telegram Stars)
# ================================================================
def stars_menu_text(uid: int) -> str:
    pts = get_points(uid)
    lines = [
        "⭐ <b>شحن النقاط عبر النجوم</b>",
        "",
        "اختر الباقة المناسبة لك واضغط عليها لإتمام الدفع داخل تيليجرام مباشرة.",
        "",
        "🎁 <b>الباقات المتوفرة:</b>",
        "",
    ]
    for pkg in STARS_PACKAGES:
        lines.append(f"  ✦ <b>{pkg['stars']}</b> ⭐  =  <b>{pkg['points']:,}</b> نقطة")
    lines.append("")
    lines.append(f"💵 رصيدك الحالي: <b>{maybe_spoiler(f'{pts:,}')}</b> نقطة")
    return "\n".join(lines)


def stars_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    for pkg in STARS_PACKAGES:
        kb.add(types.InlineKeyboardButton(
            f"{pkg['label']}  ←  {pkg['points']:,} نقطة",
            callback_data=f"buy_stars:{pkg['stars']}",
        ))
    return kb


def asia_amount_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=3)
    pts_per = int(settings.get("asia_points_per_dollar", ASIA_POINTS_PER_DOLLAR_DEFAULT))
    row = []
    for d in ASIA_DOLLAR_OPTIONS:
        pts = d * pts_per
        row.append(types.InlineKeyboardButton(
            f"{d}$ • {pts:,}",
            callback_data=f"asia_amt:{d}",
        ))
        if len(row) == 3:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    kb.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="asia_amt:cancel"))
    return kb


# ================================================================
#                          لوحة المالك
# ================================================================
def admin_main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("➕ زر في البداية", callback_data="a:addtop:start"),
           types.InlineKeyboardButton("➕ زر في النهاية", callback_data="a:addtop:end"))
    for item in menu:
        kb.row(
            types.InlineKeyboardButton(f"✏️ {item['label']}", callback_data=f"a:edit:{item['id']}"),
            types.InlineKeyboardButton("🗑", callback_data=f"a:del:{item['id']}"),
        )
    kb.add(types.InlineKeyboardButton("🎁 إهداء/خصم نقاط", callback_data="a:gift"))
    kb.add(types.InlineKeyboardButton("🔒 الاشتراك الإجباري", callback_data="a:fsub"))
    kb.add(types.InlineKeyboardButton("⚙️ الإعدادات العامة", callback_data="a:settings"))
    kb.add(types.InlineKeyboardButton("🎨 المظهر والألوان", callback_data="a:appearance"))
    kb.add(types.InlineKeyboardButton("🔌 المزوّدات (SMM)", callback_data="a:providers"))
    kb.add(types.InlineKeyboardButton("📊 إحصائيات البوت", callback_data="a:stats"))
    kb.add(types.InlineKeyboardButton("📣 رسالة جماعية لكل المستخدمين", callback_data="a:broadcast"))
    kb.add(types.InlineKeyboardButton("♻️ استعادة القائمة الافتراضية", callback_data="a:reset"))
    return kb


def admin_edit_keyboard(item):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kind_label = KIND_LABELS.get(item.get("kind", "regular"), "🔘 زر عادي")
    kb.add(types.InlineKeyboardButton(f"النوع: {kind_label}", callback_data=f"a:kind:{item['id']}"))
    kb.add(types.InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"a:lbl:{item['id']}"))
    if item.get("kind", "regular") == "regular":
        kb.add(types.InlineKeyboardButton("📝 تعديل الرد (النص)", callback_data=f"a:txt:{item['id']}"))
        # تبديل عرض عمودي ملوّن
        cur_disp = item.get("display", "auto")
        disp_label = "📐 عرض: عمودي ملوّن ✓" if cur_disp == "vertical" else "📐 عرض: تلقائي"
        kb.add(types.InlineKeyboardButton(disp_label, callback_data=f"a:disp:{item['id']}"))
        # اختيار منصة (للألوان)
        plat = item.get("platform", "")
        plat_lbl = {"instagram": "📷 انستغرام", "telegram": "✈️ تيليجرام",
                    "tiktok": "🎵 تيك توك", "": "بدون"}.get(plat, plat)
        kb.add(types.InlineKeyboardButton(f"🎨 المنصة (للألوان): {plat_lbl}",
                                          callback_data=f"a:plat:{item['id']}"))
    if item.get("kind") == "service_item":
        cur_price = item.get("price", 0)
        cur_min = item.get("min_qty", 1)
        cur_max = item.get("max_qty", 10000)
        cur_desc = (item.get("description") or "").strip()
        cur_smm = int(item.get("smm_service_id", 0) or 0)
        cur_prov = item.get("smm_provider", "")
        prov_lbl = provider_label(cur_prov) if cur_prov else "✗ غير محدد"
        desc_state = "✓ موجود" if cur_desc else "✗ غير موجود"
        smm_state = f"الآن: {cur_smm}" if cur_smm else "✗ غير مربوط"
        kb.add(types.InlineKeyboardButton(
            f"💰 السعر/1000 (الآن: {cur_price})", callback_data=f"a:price:{item['id']}"))
        kb.add(types.InlineKeyboardButton(
            f"🔌 المزوّد: {prov_lbl}", callback_data=f"a:prov:{item['id']}"))
        kb.add(types.InlineKeyboardButton(
            f"🆔 معرّف الخدمة في الموقع ({smm_state})", callback_data=f"a:smmid:{item['id']}"))
        kb.add(types.InlineKeyboardButton(
            f"📄 وصف الخدمة ({desc_state})", callback_data=f"a:desc:{item['id']}"))
        kb.add(types.InlineKeyboardButton(
            f"🔻 الحد الأدنى (الآن: {cur_min})", callback_data=f"a:minq:{item['id']}"))
        kb.add(types.InlineKeyboardButton(
            f"🔺 الحد الأقصى (الآن: {cur_max})", callback_data=f"a:maxq:{item['id']}"))
    kb.add(types.InlineKeyboardButton("➕ إضافة زر فرعي", callback_data=f"a:addsub:{item['id']}"))
    if item.get("children"):
        for sub in item["children"]:
            kb.row(
                types.InlineKeyboardButton(f"✏️ {sub['label']}", callback_data=f"a:edit:{sub['id']}"),
                types.InlineKeyboardButton("🗑", callback_data=f"a:del:{sub['id']}"),
            )
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="a:back"))
    return kb


def kind_picker_keyboard(item_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for k, label in KIND_LABELS.items():
        kb.add(types.InlineKeyboardButton(label, callback_data=f"a:setkind:{item_id}:{k}"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data=f"a:edit:{item_id}"))
    return kb


def kind_picker_for_new(prefix):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for k, label in KIND_LABELS.items():
        kb.add(types.InlineKeyboardButton(label, callback_data=f"a:newkind:{prefix}:{k}"))
    kb.add(types.InlineKeyboardButton("⬅️ إلغاء", callback_data="a:back"))
    return kb


def provider_picker_keyboard(item_id, edit_mode=True):
    """قائمة اختيار مزوّد لربط الخدمة. edit_mode=True للتعديل،
    False للإنشاء الجديد (callback مختلف)."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    if edit_mode:
        for key, info in PROVIDERS.items():
            kb.add(types.InlineKeyboardButton(
                info["label"], callback_data=f"a:setprov:{item_id}:{key}"))
        kb.add(types.InlineKeyboardButton("✋ تنفيذ يدوي (بدون مزوّد)",
                                          callback_data=f"a:setprov:{item_id}:manual"))
        kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data=f"a:edit:{item_id}"))
    else:
        # في تدفق الإنشاء الجديد، item_id هنا = "new"
        for key, info in PROVIDERS.items():
            kb.add(types.InlineKeyboardButton(
                info["label"], callback_data=f"a:newprov:{key}"))
        kb.add(types.InlineKeyboardButton("✋ تنفيذ يدوي (بدون مزوّد)",
                                          callback_data="a:newprov:manual"))
        kb.add(types.InlineKeyboardButton("⬅️ إلغاء", callback_data="a:back"))
    return kb


def platform_picker_keyboard(item_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    options = [
        ("instagram", "📷 انستغرام"),
        ("telegram", "✈️ تيليجرام"),
        ("tiktok", "🎵 تيك توك"),
        ("", "❌ بدون"),
    ]
    for val, lbl in options:
        kb.add(types.InlineKeyboardButton(lbl, callback_data=f"a:setplat:{item_id}:{val or 'none'}"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data=f"a:edit:{item_id}"))
    return kb


def settings_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(
        f"🎁 نقاط الهدية اليومية: {settings['daily_gift_points']}",
        callback_data="a:setdaily"))
    kb.add(types.InlineKeyboardButton(
        f"🔗 نقاط الإحالة: {settings['referral_points']}",
        callback_data="a:setref"))
    kb.add(types.InlineKeyboardButton(
        f"📛 اسم البوت: {settings.get('bot_title','')}",
        callback_data="a:setbottitle"))
    kb.add(types.InlineKeyboardButton(
        f"👋 رسالة الترحيب",
        callback_data="a:setwelcome"))
    kb.add(types.InlineKeyboardButton(
        f"📞 معرّف الدعم: @{settings.get('support_username','') or '—'}",
        callback_data="a:setsupport"))
    kb.add(types.InlineKeyboardButton(
        f"📱 رقم آسيا المستلم: {settings.get('asia_receiver_number','')}",
        callback_data="a:setasianum"))
    kb.add(types.InlineKeyboardButton(
        f"💱 نقاط لكل 1$ آسيا: {settings.get('asia_points_per_dollar',0):,}",
        callback_data="a:setasiarate"))
    kb.add(types.InlineKeyboardButton(
        f"📝 نص التذييل (footer)",
        callback_data="a:setfooter"))
    # تبديلات (toggles)
    def tog(label, key):
        on = settings.get(key, True)
        return types.InlineKeyboardButton(
            f"{'✅' if on else '⬜'} {label}",
            callback_data=f"a:tog:{key}")
    kb.add(tog("🎁 الهدية اليومية مفعّلة", "daily_gift_enabled"))
    kb.add(tog("🔗 الإحالة مفعّلة", "referral_enabled"))
    kb.add(tog("💸 تحويل النقاط مفعّل", "transfer_enabled"))
    kb.add(tog("⭐ شحن النجوم مفعّل", "stars_enabled"))
    kb.add(tog("📱 شحن آسيا سيل مفعّل", "asiacell_enabled"))
    kb.add(tog("🔒 الاشتراك الإجباري مفعّل", "force_sub_enabled"))
    kb.add(tog("💵 إظهار الرصيد في القائمة", "show_balance_in_main"))
    kb.add(tog("🚧 وضع الصيانة", "maintenance_mode"))
    kb.add(types.InlineKeyboardButton(
        f"🚧 نص الصيانة", callback_data="a:setmaint"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="a:back"))
    return kb


def appearance_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    def tog(label, key):
        on = settings.get(key, True)
        return types.InlineKeyboardButton(
            f"{'✅' if on else '⬜'} {label}",
            callback_data=f"a:tog:{key}")
    kb.add(tog("✨ تفعيل تنسيق بريميوم (spoiler/blockquote/ديكور)", "premium_styling"))
    kb.add(tog("🙈 إخفاء الرصيد بسبويلر", "use_spoiler_balance"))
    kb.add(tog("📑 استخدام اقتباسات قابلة للطي", "use_expandable_quotes"))
    kb.add(types.InlineKeyboardButton(
        f"🎀 الديكور العلوي: {settings.get('decor_top','')[:24] or '—'}",
        callback_data="a:setdecortop"))
    kb.add(types.InlineKeyboardButton(
        f"🎀 الديكور السفلي: {settings.get('decor_bottom','')[:24] or '—'}",
        callback_data="a:setdecorbot"))
    kb.add(types.InlineKeyboardButton(
        f"📷 ايموجي انستغرام: {settings.get('service_emoji_instagram','')}",
        callback_data="a:setemoji:instagram"))
    kb.add(types.InlineKeyboardButton(
        f"✈️ ايموجي تيليجرام: {settings.get('service_emoji_telegram','')}",
        callback_data="a:setemoji:telegram"))
    kb.add(types.InlineKeyboardButton(
        f"🎵 ايموجي تيك توك: {settings.get('service_emoji_tiktok','')}",
        callback_data="a:setemoji:tiktok"))
    kb.add(types.InlineKeyboardButton(
        f"✨ ايموجي افتراضي: {settings.get('service_emoji_default','')}",
        callback_data="a:setemoji:default"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="a:back"))
    return kb


def providers_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, info in PROVIDERS.items():
        has_key = "✅" if provider_key(key) else "❌"
        kb.add(types.InlineKeyboardButton(
            f"{has_key} {info['label']} — رصيد", callback_data=f"a:provbal:{key}"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="a:back"))
    return kb


def fsub_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("➕ إضافة قناة/كروب", callback_data="a:fsub_add"))
    for ch in channels:
        title = ch.get("title") or ch.get("chat") or "—"
        kb.add(types.InlineKeyboardButton(f"🗑 {title}", callback_data=f"a:fsub_del:{ch['id']}"))
    on = settings.get("force_sub_enabled", True)
    kb.add(types.InlineKeyboardButton(
        f"{'✅' if on else '⬜'} الاشتراك الإجباري مفعّل",
        callback_data="a:tog:force_sub_enabled"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="a:back"))
    return kb


admin_state = {}


# ================================================================
#                  معالج الأنواع الخاصة (للمستخدم)
# ================================================================
async def handle_special_kind(c: types.CallbackQuery, item) -> bool:
    kind = item.get("kind", "regular")
    user = c.from_user

    if kind == "daily_gift":
        if not settings.get("daily_gift_enabled", True):
            await c.answer("⛔ الهدية اليومية معطّلة حالياً.", show_alert=True)
            return True
        u = users.setdefault(user.id, {"points": 0, "last_daily": "", "referred_by": None, "referrals": 0})
        today = date.today().isoformat()
        if u.get("last_daily") == today:
            await c.answer("⛔ لقد استلمت هديتك اليوم، عُد غداً!", show_alert=True)
            return True
        amount = int(settings.get("daily_gift_points", 75))
        u["last_daily"] = today
        u["points"] = int(u.get("points", 0)) + amount
        save_users()
        await c.answer()
        await c.message.answer(
            decorate(
                f"🎉 مبروك! حصلت على <b>{amount}</b> نقطة كهدية يومية.\n\n"
                f"💰 رصيدك الآن: <b>{maybe_spoiler(str(u['points']))}</b> نقطة\n"
                f"🔁 عُد غداً للحصول على هديتك التالية."
            ),
            parse_mode='HTML',
        )
        return True

    if kind == "referral":
        if not settings.get("referral_enabled", True):
            await c.answer("⛔ نظام الإحالة معطّل حالياً.", show_alert=True)
            return True
        ref_pts = int(settings.get("referral_points", 200))
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}" if BOT_USERNAME else "(الرابط سيظهر بعد تشغيل البوت)"
        my_refs = int(users.get(user.id, {}).get("referrals", 0))
        await c.answer()
        await c.message.answer(
            decorate(
                f"🔗 <b>رابط الدعوة الخاص بك</b>\n\n"
                f"شارك هذا الرابط مع أصدقائك:\n"
                f"<code>{link}</code>\n\n"
                f"🎁 ستحصل على <b>{ref_pts}</b> نقطة عن كل صديق جديد يدخل البوت من رابطك.\n\n"
                f"👥 عدد دعواتك الناجحة: <b>{my_refs}</b>"
            ),
            parse_mode='HTML',
            disable_web_page_preview=True,
        )
        return True

    if kind == "service_item":
        price = int(item.get("price", 0))
        desc = (item.get("description") or "").strip()
        min_q = int(item.get("min_qty", 1))
        max_q = int(item.get("max_qty", 10000))

        user_state[user.id] = {"action": "order_qty", "service_id": item["id"]}

        info = []
        info.append(f"🛒 <b>اسم الخدمة:</b> {item['label']}")
        info.append(f"💰 <b>سعر الخدمة:</b> {price} نقطة لكل 1000")
        info.append(f"🔻 <b>الحد الأدنى:</b> {min_q}")
        info.append(f"🔺 <b>الحد الأقصى:</b> {max_q}")
        if desc:
            if settings.get("premium_styling", True) and settings.get("use_expandable_quotes", True):
                info.append(f"\n📄 <b>الوصف:</b>\n<blockquote expandable>{desc}</blockquote>")
            else:
                info.append(f"\n📄 <b>الوصف:</b>\n{desc}")
        info.append(f"\n💵 رصيدك الحالي: <b>{maybe_spoiler(str(get_points(user.id)))}</b> نقطة")
        info.append(f"\n📝 أرسل الآن العدد المطلوب (رقم بين {min_q} و {max_q}):")
        info.append("للإلغاء أرسل /cancel")

        await c.answer()
        await c.message.answer(decorate("\n".join(info)), parse_mode='HTML')
        return True

    if kind == "account":
        pts = get_points(user.id)
        refs = int(users.get(user.id, {}).get("referrals", 0))
        await c.answer()
        await c.message.answer(
            decorate(
                f"👤 <b>حسابك</b>\n\n"
                f"🆔 الايدي: <code>{user.id}</code>\n"
                f"💰 النقاط: <b>{maybe_spoiler(str(pts))}</b>\n"
                f"👥 عدد الدعوات: <b>{refs}</b>"
            ),
            parse_mode='HTML',
        )
        return True

    if kind == "stats":
        await c.answer()
        await c.message.answer(stats_text(), parse_mode='HTML')
        return True

    if kind == "transfer":
        if not settings.get("transfer_enabled", True):
            await c.answer("⛔ تحويل النقاط معطّل حالياً.", show_alert=True)
            return True
        balance = get_points(user.id)
        user_state[user.id] = {"action": "transfer_id"}
        await c.answer()
        await c.message.answer(
            decorate(
                f"💸 <b>تحويل نقاط لمستخدم آخر</b>\n\n"
                f"💵 رصيدك الحالي: <b>{maybe_spoiler(str(balance))}</b> نقطة\n\n"
                f"📝 أرسل الآن <b>الايدي (ID)</b> الخاص بالشخص الذي تريد التحويل إليه:\n"
                f"للإلغاء أرسل /cancel"
            ),
            parse_mode='HTML',
        )
        return True

    if kind == "stars_charge":
        if not settings.get("stars_enabled", True):
            await c.answer("⛔ شحن النجوم معطّل حالياً.", show_alert=True)
            return True
        await c.answer()
        await c.message.answer(
            stars_menu_text(user.id),
            parse_mode='HTML',
            reply_markup=stars_menu_keyboard(),
        )
        return True

    if kind == "asiacell_charge":
        if not settings.get("asiacell_enabled", True):
            await c.answer("⛔ شحن آسيا سيل معطّل حالياً.", show_alert=True)
            return True
        user_state[user.id] = {"action": "asia_phone"}
        await c.answer()
        pts_per = int(settings.get("asia_points_per_dollar", ASIA_POINTS_PER_DOLLAR_DEFAULT))
        await c.message.answer(
            decorate(
                f"📱 <b>الشحن عبر آسيا سيل</b>\n\n"
                f"💱 السعر: كل <b>1$</b> رصيد آسيا سيل = <b>{pts_per:,}</b> نقطة\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"<b>الخطوة ١:</b> 📞 أرسل رقم هاتفك في آسيا سيل\n"
                f"(مثال: <code>07701234567</code>)\n\n"
                f"للإلغاء أرسل /cancel"
            ),
            parse_mode='HTML',
        )
        return True

    return False


# ================================================================
#                          الأوامر
# ================================================================
@dp.message_handler(commands=['start'])
async def cmd_start(msg: types.Message):
    user_state.pop(msg.from_user.id, None)

    args = msg.get_args() or ""
    referred_by = None
    if args.startswith("ref_"):
        try:
            referred_by = int(args[4:])
        except ValueError:
            referred_by = None

    is_new = register_user(msg.from_user.id, referred_by=referred_by)

    if is_new and referred_by and referred_by != msg.from_user.id and settings.get("referral_enabled", True):
        ref_pts = int(settings.get("referral_points", 200))
        ref_user = users.setdefault(referred_by, {"points": 0, "last_daily": "", "referred_by": None, "referrals": 0})
        ref_user["points"] = int(ref_user.get("points", 0)) + ref_pts
        ref_user["referrals"] = int(ref_user.get("referrals", 0)) + 1
        save_users()
        try:
            uname = f"@{msg.from_user.username}" if msg.from_user.username else msg.from_user.first_name
            await bot.send_message(
                referred_by,
                f"🎉 مبروك! دعوتك نجحت!\n\n"
                f"👤 انضم: {uname}\n"
                f"🎁 حصلت على <b>{ref_pts}</b> نقطة\n"
                f"💰 رصيدك الآن: <b>{ref_user['points']}</b>",
                parse_mode='HTML',
            )
        except Exception:
            pass

    if msg.from_user.id == ADMIN_ID:
        await msg.answer(
            "⚙️ <b>لوحة المالك</b>\n\nمن هنا تتحكم بكل شيء.",
            parse_mode='HTML',
            reply_markup=admin_main_keyboard(),
        )

    if settings.get("maintenance_mode", False) and msg.from_user.id != ADMIN_ID:
        await msg.answer(settings.get("maintenance_text", "🚧 البوت تحت الصيانة."))
        return

    if not await enforce_subscription(msg):
        return

    pts = get_points(msg.from_user.id)
    welcome = settings.get("welcome_text") if is_new else settings.get("return_text")
    body = f"{welcome}\n\n"
    if settings.get("show_balance_in_main", True):
        body += f"💰 رصيدك: <b>{maybe_spoiler(str(pts))}</b> نقطة\n"
    body += f"🆔 ايديك: <code>{msg.from_user.id}</code>\n\nاختر من القائمة:"
    await msg.answer(
        decorate(body),
        parse_mode='HTML',
        reply_markup=user_keyboard(),
    )


@dp.message_handler(commands=['admin'])
async def cmd_admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ هذا الأمر مخصص للمالك فقط.")
        return
    await msg.answer(
        "⚙️ <b>لوحة المالك</b>",
        parse_mode='HTML',
        reply_markup=admin_main_keyboard(),
    )


@dp.message_handler(commands=['cancel'])
async def cmd_cancel(msg: types.Message):
    cancelled = False
    if msg.from_user.id in user_state:
        user_state.pop(msg.from_user.id, None)
        cancelled = True
    if msg.from_user.id == ADMIN_ID and ADMIN_ID in admin_state:
        admin_state.pop(ADMIN_ID, None)
        cancelled = True
    if cancelled:
        await msg.answer("✅ تم إلغاء العملية.", reply_markup=user_keyboard())
    else:
        await msg.answer("لا توجد عملية جارية.", reply_markup=user_keyboard())


# -------- أوامر SMM للمالك --------
@dp.message_handler(commands=['smm_balance'])
async def cmd_smm_balance(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = []
    for key, info in PROVIDERS.items():
        await msg.answer(f"⏳ فحص رصيد {info['short']}...")
        resp = await smm_balance(key)
        if "balance" in resp:
            parts.append(f"💰 {info['label']}: <b>{resp.get('balance','?')} {resp.get('currency','')}</b>")
        else:
            parts.append(f"❌ {info['label']}: <code>{resp.get('error','?')}</code>")
    await msg.answer("\n".join(parts), parse_mode='HTML')


@dp.message_handler(commands=['smm_status'])
async def cmd_smm_status(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    args = (msg.get_args() or "").strip().split()
    if len(args) < 1:
        await msg.answer(
            "الاستعمال: <code>/smm_status &lt;رقم_الطلب&gt; [smmfollows|jap]</code>",
            parse_mode='HTML')
        return
    try:
        oid = int(args[0])
    except ValueError:
        await msg.answer("⚠️ أرسل رقم طلب صحيح.")
        return
    provider = args[1].lower() if len(args) > 1 else None
    # لو ما حدد المزوّد، نحاول من ذاكرة الطلبات
    if not provider:
        rec = smm_orders.get(str(oid))
        provider = (rec or {}).get("provider", "smmfollows")
    if provider not in PROVIDERS:
        await msg.answer(f"⚠️ مزوّد غير معروف. اختر من: {', '.join(PROVIDERS.keys())}")
        return
    await msg.answer(
        f"⏳ فحص الطلب <code>{oid}</code> من {provider_label(provider)}...", parse_mode='HTML')
    resp = await smm_order_status(provider, oid)
    if "status" in resp:
        if str(oid) in smm_orders:
            smm_orders[str(oid)]["status"] = resp.get("status", "?")
            save_smm_orders()
        info = (
            f"🆔 الطلب: <code>{oid}</code>\n"
            f"🔌 المزوّد: {provider_label(provider)}\n"
            f"📊 الحالة: <b>{resp.get('status', '?')}</b>\n"
            f"💵 التكلفة: {resp.get('charge', '?')} {resp.get('currency', '')}\n"
            f"📈 العدد قبل البدء: {resp.get('start_count', '?')}\n"
            f"⏳ المتبقي: {resp.get('remains', '?')}"
        )
        await msg.answer(info, parse_mode='HTML')
    else:
        err = resp.get("error", "خطأ غير معروف")
        await msg.answer(f"❌ تعذر فحص الطلب:\n<code>{err}</code>", parse_mode='HTML')


@dp.message_handler(commands=['smm_orders'])
async def cmd_smm_orders(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    if not smm_orders:
        await msg.answer("لا توجد طلبات SMM مسجلة بعد.")
        return
    items = sorted(smm_orders.values(), key=lambda x: int(x["order_id"]), reverse=True)[:15]
    lines = ["📋 <b>آخر طلبات SMM</b>\n"]
    for o in items:
        prov = o.get("provider", "smmfollows")
        lines.append(
            f"🆔 <code>{o['order_id']}</code> | {o['service_label']}\n"
            f"   🔌 {provider_label(prov)} | 👤 {o['user_id']} | 🔢 {o['quantity']} | 💰 {o['cost_points']}pt\n"
            f"   📊 {o.get('status','?')} | 📅 {o.get('created_at','')}\n"
        )
    await msg.answer("\n".join(lines), parse_mode='HTML')


def stats_text() -> str:
    total_users = len(users)
    total_points = sum(int(u.get("points", 0)) for u in users.values())
    top = sorted(users.items(), key=lambda x: int(x[1].get("points", 0)), reverse=True)[:5]
    top_text = "\n".join(
        [f"  {i+1}. <code>{uid}</code> — {int(u.get('points', 0))} نقطة"
         for i, (uid, u) in enumerate(top)]
    ) or "  لا يوجد مستخدمون بعد."
    return (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👥 إجمالي المستخدمين: <b>{total_users}</b>\n"
        f"💰 إجمالي النقاط: <b>{total_points}</b>\n"
        f"🛒 إجمالي طلبات SMM: <b>{len(smm_orders)}</b>\n"
        f"📱 طلبات آسيا المعلّقة: <b>{sum(1 for r in asia_requests.values() if r.get('status')=='pending')}</b>\n"
        f"🔒 قنوات الاشتراك الإجباري: <b>{len(channels)}</b>\n\n"
        f"🏆 أعلى 5 مستخدمين:\n{top_text}"
    )


# ================================================================
#                ضغطات أزرار شراء النجوم
# ================================================================
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("buy_stars:"))
async def cb_buy_stars(c: types.CallbackQuery):
    register_user(c.from_user.id)
    if not await enforce_subscription(c):
        return
    try:
        stars = int(c.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await c.answer("⚠️ باقة غير صالحة.", show_alert=True)
        return

    pkg = next((p for p in STARS_PACKAGES if int(p["stars"]) == stars), None)
    if not pkg:
        await c.answer("⚠️ هذه الباقة غير متوفرة.", show_alert=True)
        return

    await c.answer()
    try:
        prices = [types.LabeledPrice(label=f"{pkg['points']:,} نقطة", amount=int(pkg["stars"]))]
        await bot.send_invoice(
            chat_id=c.from_user.id,
            title=f"شحن {pkg['points']:,} نقطة",
            description=f"احصل على {pkg['points']:,} نقطة فوراً مقابل {pkg['stars']} ⭐ نجمة تيليجرام.",
            payload=f"stars_pkg:{pkg['stars']}:{pkg['points']}",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter=f"buy_{pkg['stars']}_stars",
        )
    except Exception as e:
        logging.exception("send_invoice failed")
        await c.message.answer(
            f"⚠️ تعذر إنشاء فاتورة الدفع: {e}\n\n"
            f"تأكد من أن إصدار aiogram يدعم عملة النجوم XTR، أو تواصل مع المالك."
        )


@dp.pre_checkout_query_handler(lambda q: True)
async def pre_checkout(q: types.PreCheckoutQuery):
    try:
        await bot.answer_pre_checkout_query(q.id, ok=True)
    except Exception as e:
        logging.warning(f"pre_checkout error: {e}")
        try:
            await bot.answer_pre_checkout_query(q.id, ok=False, error_message="حدث خطأ، حاول مرة أخرى.")
        except Exception:
            pass


@dp.message_handler(content_types=[types.ContentType.SUCCESSFUL_PAYMENT])
async def on_successful_payment(msg: types.Message):
    sp = msg.successful_payment
    payload = sp.invoice_payload or ""
    uid = msg.from_user.id
    try:
        parts = payload.split(":")
        if len(parts) >= 3 and parts[0] == "stars_pkg":
            stars_paid = int(parts[1])
            points = int(parts[2])
        else:
            stars_paid = int(sp.total_amount or 0)
            pkg = next((p for p in STARS_PACKAGES if int(p["stars"]) == stars_paid), None)
            points = int(pkg["points"]) if pkg else stars_paid * 400
    except Exception:
        stars_paid = int(sp.total_amount or 0)
        points = stars_paid * 400

    register_user(uid)
    add_points(uid, points)
    new_balance = get_points(uid)

    await msg.answer(
        f"✅ <b>تم الدفع بنجاح!</b>\n\n"
        f"⭐ النجوم المدفوعة: <b>{stars_paid}</b>\n"
        f"🎁 النقاط المضافة: <b>{points:,}</b>\n"
        f"💵 رصيدك الآن: <b>{new_balance:,}</b> نقطة\n\n"
        f"شكراً لشحنك! 💛",
        parse_mode='HTML',
        reply_markup=user_keyboard(),
    )


# ================================================================
#                 آسيا سيل: callbacks المبلغ
# ================================================================
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("asia_amt:"))
async def cb_asia_amt(c: types.CallbackQuery):
    if not await enforce_subscription(c):
        return
    val = c.data.split(":", 1)[1]
    uid = c.from_user.id
    if val == "cancel":
        user_state.pop(uid, None)
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await c.answer("تم الإلغاء.")
        await c.message.answer("❌ تم إلغاء طلب آسيا سيل.", reply_markup=user_keyboard())
        return

    state = user_state.get(uid)
    if not state or state.get("action") != "asia_pick":
        await c.answer("⚠️ هذه الجلسة منتهية. ابدأ من زر آسيا سيل من جديد.", show_alert=True)
        return

    try:
        dollars = int(val)
    except ValueError:
        await c.answer("⚠️ مبلغ غير صالح.", show_alert=True)
        return

    if dollars not in ASIA_DOLLAR_OPTIONS:
        await c.answer("⚠️ مبلغ غير متوفر.", show_alert=True)
        return

    pts_per = int(settings.get("asia_points_per_dollar", ASIA_POINTS_PER_DOLLAR_DEFAULT))
    points = dollars * pts_per
    rid = new_asia_req_id()
    asia_requests[rid] = {
        "id": rid,
        "user_id": uid,
        "username": c.from_user.username or "",
        "first_name": c.from_user.first_name or "",
        "phone": state.get("phone", ""),
        "verify_code": state.get("verify_code", ""),
        "dollars": dollars,
        "points": points,
        "status": "pending",
        "created_at": date.today().isoformat(),
    }
    save_asia_requests()
    user_state.pop(uid, None)

    await c.answer("✅ تم استلام طلبك")
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await c.message.answer(
        f"✅ <b>تم استلام طلب الشحن</b>\n\n"
        f"📞 رقمك: <code>{state.get('phone','')}</code>\n"
        f"💵 المبلغ: <b>{dollars}$</b>\n"
        f"🎁 النقاط المتوقعة: <b>{points:,}</b>\n\n"
        f"⏳ سيتم اعتماد الطلب قريباً وإضافة النقاط إلى رصيدك تلقائياً.",
        parse_mode='HTML',
        reply_markup=user_keyboard(),
    )

    try:
        uname = f"@{c.from_user.username}" if c.from_user.username else (c.from_user.first_name or "—")
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.row(
            types.InlineKeyboardButton("✅ اعتماد وإضافة النقاط", callback_data=f"asia:approve:{rid}"),
            types.InlineKeyboardButton("❌ رفض", callback_data=f"asia:reject:{rid}"),
        )
        await bot.send_message(
            ADMIN_ID,
            f"📱 <b>طلب شحن آسيا سيل جديد</b> #{rid}\n\n"
            f"👤 المستخدم: <code>{uid}</code> ({uname})\n"
            f"📞 رقمه: <code>{state.get('phone','')}</code>\n"
            f"🔐 كود التحقق المُستخدم: <code>{state.get('verify_code','')}</code>\n"
            f"💵 المبلغ: <b>{dollars}$</b>\n"
            f"🎁 النقاط المطلوبة: <b>{points:,}</b>\n\n"
            f"اضغط اعتماد بعد التأكد من وصول الرصيد.",
            parse_mode='HTML',
            reply_markup=kb,
        )
    except Exception as e:
        logging.warning(f"تعذر إشعار المالك بطلب آسيا: {e}")


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("asia:"))
async def cb_asia_admin(c: types.CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        await c.answer("❌ مخصص للمالك.", show_alert=True)
        return
    parts = c.data.split(":")
    action = parts[1]
    rid = parts[2]
    req = asia_requests.get(rid)
    if not req:
        await c.answer("⚠️ الطلب غير موجود.", show_alert=True)
        return
    if action == "approve":
        if req.get("status") != "pending":
            await c.answer("سبق معالجته.", show_alert=True)
            return
        req["status"] = "approved"
        save_asia_requests()
        add_points(int(req["user_id"]), int(req["points"]))
        await c.answer("✅ تم الاعتماد.")
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            await bot.send_message(
                int(req["user_id"]),
                f"✅ تم اعتماد طلب شحن آسيا سيل!\n"
                f"🎁 تمت إضافة <b>{int(req['points']):,}</b> نقطة.\n"
                f"💵 رصيدك الآن: <b>{get_points(int(req['user_id'])):,}</b>",
                parse_mode='HTML',
            )
        except Exception:
            pass
    elif action == "reject":
        req["status"] = "rejected"
        save_asia_requests()
        await c.answer("تم الرفض.")
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            await bot.send_message(
                int(req["user_id"]),
                "❌ تم رفض طلب شحن آسيا سيل. تواصل مع المالك للتفاصيل."
            )
        except Exception:
            pass


# ================================================================
#                       ضغطات أزرار المستخدم
# ================================================================
@dp.callback_query_handler(lambda c: c.data == "fsub:check")
async def cb_fsub_check(c: types.CallbackQuery):
    missing = await get_unsubscribed(c.from_user.id)
    if not missing:
        await c.answer("✅ تم التحقق! يمكنك المتابعة.", show_alert=True)
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await c.message.answer(
            decorate("✅ تم التحقق من الاشتراك. اختر من القائمة:"),
            parse_mode='HTML',
            reply_markup=user_keyboard(),
        )
    else:
        await c.answer("⚠️ ما زلت لم تشترك في كل القنوات.", show_alert=True)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("u:"))
async def cb_user(c: types.CallbackQuery):
    register_user(c.from_user.id)
    if settings.get("maintenance_mode", False) and c.from_user.id != ADMIN_ID:
        await c.answer(settings.get("maintenance_text", "🚧 صيانة"), show_alert=True)
        return
    if not await enforce_subscription(c):
        return

    item_id = c.data.split(":", 1)[1]
    item, _, parent = find_item(item_id)
    if not item:
        await c.answer("⚠️ هذا الزر لم يعد متوفراً.", show_alert=True)
        return

    if c.from_user.id in user_state and item.get("kind") not in ("service_item", "transfer"):
        user_state.pop(c.from_user.id, None)

    if await handle_special_kind(c, item):
        return

    await c.answer()
    text = item.get("text") or item["label"]
    if item.get("children"):
        await c.message.answer(
            decorate(text), parse_mode='HTML',
            reply_markup=items_keyboard(item["children"], prefix="u", parent_item=item))
    else:
        await c.message.answer(decorate(text), parse_mode='HTML')


# ================================================================
#                       ضغطات أزرار المالك
# ================================================================
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("a:"))
async def cb_admin(c: types.CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        await c.answer("❌ هذا الزر للمالك فقط.", show_alert=True)
        return

    parts = c.data.split(":")
    action = parts[1]

    if action == "back":
        await c.answer()
        try:
            await c.message.edit_text(
                "⚙️ <b>لوحة المالك</b>",
                parse_mode='HTML',
                reply_markup=admin_main_keyboard(),
            )
        except Exception:
            await c.message.answer(
                "⚙️ <b>لوحة المالك</b>",
                parse_mode='HTML',
                reply_markup=admin_main_keyboard(),
            )
        return

    if action == "stats":
        await c.answer()
        await c.message.answer(stats_text(), parse_mode='HTML')
        return

    if action == "settings":
        await c.answer()
        try:
            await c.message.edit_text(
                "⚙️ <b>الإعدادات العامة</b>\n\nاضغط على أي إعداد لتغيير قيمته:",
                parse_mode='HTML',
                reply_markup=settings_keyboard(),
            )
        except Exception:
            await c.message.answer("⚙️ الإعدادات", reply_markup=settings_keyboard())
        return

    if action == "appearance":
        await c.answer()
        try:
            await c.message.edit_text(
                "🎨 <b>المظهر والألوان</b>\n\nخصّص شكل ردود البوت:",
                parse_mode='HTML',
                reply_markup=appearance_keyboard(),
            )
        except Exception:
            await c.message.answer("🎨 المظهر", reply_markup=appearance_keyboard())
        return

    if action == "providers":
        await c.answer()
        await c.message.answer(
            "🔌 <b>مزوّدات الخدمات</b>\n\nاضغط على مزوّد لفحص رصيده:",
            parse_mode='HTML',
            reply_markup=providers_keyboard(),
        )
        return

    if action == "provbal":
        prov = parts[2]
        await c.answer()
        await c.message.answer(f"⏳ فحص رصيد {provider_label(prov)}...")
        resp = await smm_balance(prov)
        if "balance" in resp:
            await c.message.answer(
                f"💰 رصيدك في {provider_label(prov)}:\n"
                f"<b>{resp.get('balance','?')} {resp.get('currency','')}</b>",
                parse_mode='HTML')
        else:
            await c.message.answer(f"❌ {resp.get('error','خطأ')}")
        return

    if action == "fsub":
        await c.answer()
        try:
            await c.message.edit_text(
                "🔒 <b>الاشتراك الإجباري</b>\n\n"
                "أضف القنوات أو الكروبات التي يجب على المستخدم الاشتراك بها قبل استخدام البوت.\n"
                "ملاحظة: يجب أن يكون البوت <b>مشرفاً (Admin)</b> في القناة لكي يستطيع التحقق من الاشتراك.\n\n"
                f"عدد القنوات الحالي: <b>{len(channels)}</b>",
                parse_mode='HTML',
                reply_markup=fsub_keyboard(),
            )
        except Exception:
            await c.message.answer("🔒 الاشتراك الإجباري", reply_markup=fsub_keyboard())
        return

    if action == "fsub_add":
        admin_state[ADMIN_ID] = {"action": "fsub_add_chat"}
        await c.answer()
        await c.message.answer(
            "📝 أرسل معرّف القناة/الكروب على شكل <code>@username</code>\n"
            "أو رقم الـ chat_id (مثل <code>-1001234567890</code>).\n\n"
            "ملاحظة: تأكد أن البوت <b>مشرف</b> في تلك القناة قبل الإضافة.\n"
            "للإلغاء أرسل /cancel",
            parse_mode='HTML',
        )
        return

    if action == "fsub_del":
        cid = parts[2]
        idx = next((i for i, ch in enumerate(channels) if str(ch.get("id")) == cid), -1)
        if idx >= 0:
            removed = channels.pop(idx)
            save_channels()
            await c.answer(f"تم حذف: {removed.get('title','')}", show_alert=True)
        try:
            await c.message.edit_reply_markup(reply_markup=fsub_keyboard())
        except Exception:
            await c.message.answer("🔒 تم التحديث.", reply_markup=fsub_keyboard())
        return

    if action == "tog":
        key = parts[2]
        cur = bool(settings.get(key, False))
        settings[key] = not cur
        save_settings()
        await c.answer(f"{'✅' if settings[key] else '⬜'} {key}")
        # نعيد بناء اللوحة المناسبة
        try:
            txt = c.message.text or ""
            if "الإعدادات" in txt:
                await c.message.edit_reply_markup(reply_markup=settings_keyboard())
            elif "المظهر" in txt:
                await c.message.edit_reply_markup(reply_markup=appearance_keyboard())
            elif "الاشتراك الإجباري" in txt:
                await c.message.edit_reply_markup(reply_markup=fsub_keyboard())
            else:
                await c.message.edit_reply_markup(reply_markup=settings_keyboard())
        except Exception:
            pass
        return

    if action == "broadcast":
        admin_state[ADMIN_ID] = {"action": "broadcast"}
        await c.answer()
        await c.message.answer(
            "📣 أرسل الآن الرسالة التي تريد إرسالها لجميع المستخدمين.\n"
            "يدعم HTML (b/i/u/code/blockquote/tg-spoiler).\n"
            "للإلغاء أرسل /cancel"
        )
        return

    if action == "setdaily":
        admin_state[ADMIN_ID] = {"action": "set_daily"}
        await c.answer()
        await c.message.answer(f"📝 أرسل العدد الجديد لنقاط الهدية اليومية (الحالي: {settings['daily_gift_points']}):")
        return

    if action == "setref":
        admin_state[ADMIN_ID] = {"action": "set_ref"}
        await c.answer()
        await c.message.answer(f"📝 أرسل العدد الجديد لنقاط الإحالة (الحالي: {settings['referral_points']}):")
        return

    if action == "setbottitle":
        admin_state[ADMIN_ID] = {"action": "set_bot_title"}
        await c.answer()
        await c.message.answer(f"📝 أرسل اسم البوت الجديد (الحالي: {settings.get('bot_title','')}):")
        return

    if action == "setwelcome":
        admin_state[ADMIN_ID] = {"action": "set_welcome"}
        await c.answer()
        await c.message.answer(
            "📝 أرسل نص رسالة الترحيب الجديدة. يدعم HTML.\n"
            f"الحالي:\n{settings.get('welcome_text','')}")
        return

    if action == "setsupport":
        admin_state[ADMIN_ID] = {"action": "set_support"}
        await c.answer()
        await c.message.answer(
            f"📝 أرسل معرّف الدعم بدون @ (الحالي: {settings.get('support_username','—')}):\n"
            f"لإزالته أرسل: -")
        return

    if action == "setasianum":
        admin_state[ADMIN_ID] = {"action": "set_asia_num"}
        await c.answer()
        await c.message.answer(f"📝 أرسل رقم آسيا المستلم (الحالي: {settings.get('asia_receiver_number','')}):")
        return

    if action == "setasiarate":
        admin_state[ADMIN_ID] = {"action": "set_asia_rate"}
        await c.answer()
        await c.message.answer(
            f"📝 أرسل عدد النقاط لكل 1$ آسيا سيل (الحالي: {settings.get('asia_points_per_dollar',0)}):")
        return

    if action == "setfooter":
        admin_state[ADMIN_ID] = {"action": "set_footer"}
        await c.answer()
        await c.message.answer(
            "📝 أرسل نص التذييل (يضاف أسفل كل رد). يدعم HTML.\n"
            f"الحالي:\n{settings.get('footer_text','')}\n\n"
            "لمسحه أرسل: -")
        return

    if action == "setmaint":
        admin_state[ADMIN_ID] = {"action": "set_maint"}
        await c.answer()
        await c.message.answer(
            f"📝 أرسل نص رسالة الصيانة:\nالحالي:\n{settings.get('maintenance_text','')}")
        return

    if action == "setdecortop":
        admin_state[ADMIN_ID] = {"action": "set_decor_top"}
        await c.answer()
        await c.message.answer(
            f"📝 أرسل الديكور العلوي. لمسحه أرسل: -\nالحالي:\n{settings.get('decor_top','')}")
        return

    if action == "setdecorbot":
        admin_state[ADMIN_ID] = {"action": "set_decor_bot"}
        await c.answer()
        await c.message.answer(
            f"📝 أرسل الديكور السفلي. لمسحه أرسل: -\nالحالي:\n{settings.get('decor_bottom','')}")
        return

    if action == "setemoji":
        plat = parts[2]
        admin_state[ADMIN_ID] = {"action": "set_emoji", "plat": plat}
        await c.answer()
        cur_key = f"service_emoji_{plat}"
        await c.message.answer(
            f"📝 أرسل ايموجي/أيقونة الخدمات لـ {plat} (الحالي: {settings.get(cur_key,'')}):")
        return

    if action == "gift":
        admin_state[ADMIN_ID] = {"action": "gift_id"}
        await c.answer()
        await c.message.answer(
            "🎁 <b>إهداء/خصم نقاط لمستخدم</b>\n\n"
            "📝 أرسل ايدي (ID) المستخدم:\n"
            "للإلغاء أرسل /cancel",
            parse_mode='HTML',
        )
        return

    if action == "reset":
        admin_state[ADMIN_ID] = {"action": "confirm_reset"}
        await c.answer()
        await c.message.answer(
            "⚠️ سيتم استبدال القائمة الحالية بالافتراضية.\n"
            "للتأكيد أرسل: <code>تأكيد</code>\nللإلغاء: /cancel",
            parse_mode='HTML',
        )
        return

    if action == "addtop":
        where = parts[2]
        await c.answer()
        await c.message.answer(
            "🆕 اختر <b>نوع</b> الزر الجديد:",
            parse_mode='HTML',
            reply_markup=kind_picker_for_new(f"addtop_{where}"),
        )
        return

    if action == "newkind":
        prefix = parts[2]
        kind = parts[3]
        if prefix.startswith("addsub_"):
            parent_id = prefix.split("_", 1)[1]
            admin_state[ADMIN_ID] = {
                "action": "add_sub", "parent_id": parent_id, "kind": kind, "step": 1, "tmp": {}
            }
        else:
            where = "start" if prefix.endswith("_start") else "end"
            admin_state[ADMIN_ID] = {
                "action": "add_top", "where": where, "kind": kind, "step": 1, "tmp": {}
            }
        await c.answer()
        await c.message.answer("📝 أرسل اسم الزر الجديد (مثال: 🆕 خيار جديد):")
        return

    if action == "edit":
        item_id = parts[2]
        item, _, _ = find_item(item_id)
        if not item:
            await c.answer("⚠️ غير موجود", show_alert=True)
            return
        await c.answer()
        try:
            await c.message.edit_text(
                f"✏️ <b>تعديل:</b> {item['label']}",
                parse_mode='HTML',
                reply_markup=admin_edit_keyboard(item),
            )
        except Exception:
            await c.message.answer(
                f"✏️ <b>تعديل:</b> {item['label']}",
                parse_mode='HTML',
                reply_markup=admin_edit_keyboard(item),
            )
        return

    if action == "kind":
        item_id = parts[2]
        item, _, _ = find_item(item_id)
        if not item:
            await c.answer("⚠️ غير موجود", show_alert=True)
            return
        await c.answer()
        try:
            await c.message.edit_text(
                f"🔧 اختر النوع الجديد لـ: <b>{item['label']}</b>",
                parse_mode='HTML',
                reply_markup=kind_picker_keyboard(item_id),
            )
        except Exception:
            await c.message.answer(
                f"🔧 اختر النوع الجديد:",
                reply_markup=kind_picker_keyboard(item_id),
            )
        return

    if action == "setkind":
        item_id = parts[2]
        new_kind = parts[3]
        item, _, _ = find_item(item_id)
        if not item:
            await c.answer("⚠️ غير موجود", show_alert=True)
            return
        item["kind"] = new_kind
        if new_kind == "service_item":
            item.setdefault("price", 0)
            item.setdefault("description", "")
            item.setdefault("min_qty", 1)
            item.setdefault("max_qty", 10000)
            item.setdefault("smm_service_id", 0)
            item.setdefault("smm_provider", "")
        save_menu()
        await c.answer("✅ تم تغيير النوع")
        try:
            await c.message.edit_text(
                f"✏️ <b>تعديل:</b> {item['label']}",
                parse_mode='HTML',
                reply_markup=admin_edit_keyboard(item),
            )
        except Exception:
            await c.message.answer(
                f"✏️ <b>تعديل:</b> {item['label']}",
                parse_mode='HTML',
                reply_markup=admin_edit_keyboard(item),
            )
        return

    if action == "lbl":
        item_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "edit_label", "target_id": item_id}
        await c.answer()
        await c.message.answer("📝 أرسل الاسم الجديد للزر:")
        return

    if action == "txt":
        item_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "edit_text", "target_id": item_id}
        await c.answer()
        await c.message.answer("📝 أرسل النص الجديد للرد:")
        return

    if action == "disp":
        item_id = parts[2]
        item, _, _ = find_item(item_id)
        if not item:
            await c.answer("⚠️ غير موجود", show_alert=True)
            return
        cur = item.get("display", "auto")
        item["display"] = "auto" if cur == "vertical" else "vertical"
        save_menu()
        await c.answer(f"📐 العرض الآن: {item['display']}")
        try:
            await c.message.edit_reply_markup(reply_markup=admin_edit_keyboard(item))
        except Exception:
            pass
        return

    if action == "plat":
        item_id = parts[2]
        await c.answer()
        try:
            await c.message.edit_reply_markup(reply_markup=platform_picker_keyboard(item_id))
        except Exception:
            await c.message.answer("اختر المنصة:", reply_markup=platform_picker_keyboard(item_id))
        return

    if action == "setplat":
        item_id = parts[2]
        plat = parts[3]
        if plat == "none":
            plat = ""
        item, _, _ = find_item(item_id)
        if not item:
            await c.answer("⚠️ غير موجود", show_alert=True)
            return
        item["platform"] = plat
        # عند اختيار منصة، نُفعّل العرض العمودي تلقائياً
        if plat:
            item["display"] = "vertical"
        save_menu()
        await c.answer("✅ تم تحديث المنصة")
        try:
            await c.message.edit_text(
                f"✏️ <b>تعديل:</b> {item['label']}",
                parse_mode='HTML',
                reply_markup=admin_edit_keyboard(item),
            )
        except Exception:
            pass
        return

    if action == "price":
        item_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "edit_price", "target_id": item_id}
        await c.answer()
        await c.message.answer("📝 أرسل السعر الجديد بالنقاط لكل 1000 (رقم فقط):")
        return

    if action == "prov":
        item_id = parts[2]
        await c.answer()
        await c.message.answer(
            "🔌 اختر المزوّد لربط هذه الخدمة به:",
            reply_markup=provider_picker_keyboard(item_id, edit_mode=True),
        )
        return

    if action == "setprov":
        item_id = parts[2]
        prov = parts[3]
        item, _, _ = find_item(item_id)
        if not item:
            await c.answer("⚠️ غير موجود", show_alert=True)
            return
        if prov == "manual":
            item["smm_provider"] = ""
            item["smm_service_id"] = 0
            save_menu()
            await c.answer("✓ ضُبط للتنفيذ اليدوي")
        else:
            if prov not in PROVIDERS:
                await c.answer("⚠️ مزوّد غير معروف", show_alert=True)
                return
            item["smm_provider"] = prov
            save_menu()
            await c.answer(f"✓ مزوّد: {provider_label(prov)}")
        try:
            await c.message.edit_text(
                f"✏️ <b>تعديل:</b> {item['label']}",
                parse_mode='HTML',
                reply_markup=admin_edit_keyboard(item),
            )
        except Exception:
            pass
        return

    if action == "desc":
        item_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "edit_desc", "target_id": item_id}
        await c.answer()
        await c.message.answer(
            "📝 أرسل وصف الخدمة (سيظهر للمشترك عند اختيار الخدمة).\nلمسح الوصف أرسل: -"
        )
        return

    if action == "smmid":
        item_id = parts[2]
        item, _, _ = find_item(item_id)
        if not item:
            await c.answer("⚠️ غير موجود", show_alert=True)
            return
        prov = item.get("smm_provider", "")
        if not prov:
            await c.answer("اختر مزوّداً أولاً", show_alert=True)
            await c.message.answer(
                "🔌 يجب اختيار المزوّد أولاً قبل ربط معرّف الخدمة:",
                reply_markup=provider_picker_keyboard(item_id, edit_mode=True),
            )
            return
        admin_state[ADMIN_ID] = {"action": "edit_smmid", "target_id": item_id}
        await c.answer()
        await c.message.answer(
            f"📝 أرسل <b>معرّف الخدمة (Service ID)</b> من موقع {provider_label(prov)}.\n"
            "يكون رقم صحيح (مثال: <code>1234</code>).\n"
            "للإلغاء وإزالة الربط أرسل: 0",
            parse_mode='HTML',
        )
        return

    if action == "minq":
        item_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "edit_minq", "target_id": item_id}
        await c.answer()
        await c.message.answer("📝 أرسل الحد الأدنى المسموح به لعدد الرشق (رقم صحيح موجب):")
        return

    if action == "maxq":
        item_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "edit_maxq", "target_id": item_id}
        await c.answer()
        await c.message.answer("📝 أرسل الحد الأقصى المسموح به لعدد الرشق (رقم صحيح موجب):")
        return

    if action == "addsub":
        parent_id = parts[2]
        await c.answer()
        await c.message.answer(
            "🆕 اختر نوع الزر الفرعي الجديد:",
            reply_markup=kind_picker_for_new(f"addsub_{parent_id}"),
        )
        return

    if action == "del":
        item_id = parts[2]
        item, container, _ = find_item(item_id)
        if not item:
            await c.answer("⚠️ غير موجود", show_alert=True)
            return
        container.remove(item)
        save_menu()
        await c.answer("✅ تم الحذف")
        try:
            await c.message.edit_text(
                "⚙️ <b>لوحة المالك</b>",
                parse_mode='HTML',
                reply_markup=admin_main_keyboard(),
            )
        except Exception:
            await c.message.answer(
                "✅ تم تحديث القائمة.",
                reply_markup=admin_main_keyboard(),
            )
        return

    # في تدفق إنشاء خدمة جديدة، نختار المزوّد
    if action == "newprov":
        prov = parts[2]
        st = admin_state.get(ADMIN_ID)
        if not st or st.get("action") not in ("add_top", "add_sub") or st.get("kind") != "service_item":
            await c.answer("لا يوجد تدفق إنشاء نشط.", show_alert=True)
            return
        if prov == "manual":
            st["tmp"]["smm_provider"] = ""
            st["tmp"]["smm_service_id"] = 0
            # نتخطى مرحلة طلب الـ smmid
            st["step"] = 5
            await c.answer()
            await c.message.answer("📝 أرسل وصف الخدمة (يظهر للمشترك). إذا لا تريد وصفاً أرسل: -")
            return
        if prov not in PROVIDERS:
            await c.answer("⚠️ مزوّد غير معروف", show_alert=True)
            return
        st["tmp"]["smm_provider"] = prov
        st["step"] = 4  # ننتقل لمرحلة طلب smmid
        await c.answer()
        await c.message.answer(
            f"🆔 أرسل <b>معرّف الخدمة (Service ID)</b> من موقع {provider_label(prov)}.",
            parse_mode='HTML',
        )
        return


# ================================================================
#                 استقبال إدخال المستخدم أثناء العمليات
# ================================================================
async def _process_user_flow(msg: types.Message) -> bool:
    uid = msg.from_user.id
    if uid not in user_state:
        return False

    state = user_state[uid]
    text = (msg.text or "").strip()

    if text in ("/cancel", "إلغاء"):
        user_state.pop(uid, None)
        await msg.answer("❌ تم إلغاء العملية.", reply_markup=user_keyboard())
        return True

    # ----------------- طلب خدمة -----------------
    if state["action"] in ("order_qty", "order_link"):
        item, _, _ = find_item(state.get("service_id", ""))
        if not item or item.get("kind") != "service_item":
            user_state.pop(uid, None)
            await msg.answer("⚠️ الخدمة لم تعد متوفرة.", reply_markup=user_keyboard())
            return True

        if state["action"] == "order_qty":
            try:
                q = int(text)
            except ValueError:
                await msg.answer("⚠️ أرسل رقماً صحيحاً للعدد، أو /cancel للإلغاء.")
                return True
            min_q = int(item.get("min_qty", 1))
            max_q = int(item.get("max_qty", 10000))
            if q < min_q or q > max_q:
                await msg.answer(
                    f"⚠️ يجب أن يكون العدد بين <b>{min_q}</b> و <b>{max_q}</b>.\n"
                    f"حاول مرة أخرى أو أرسل /cancel للإلغاء.",
                    parse_mode='HTML',
                )
                return True
            price = int(item.get("price", 0))
            total = calc_total(price, q)
            balance = get_points(uid)
            if balance < total:
                user_state.pop(uid, None)
                await msg.answer(
                    f"❌ نقاطك غير كافية!\n"
                    f"العدد المطلوب: <b>{q}</b>\n"
                    f"التكلفة الإجمالية: <b>{total}</b> نقطة\n"
                    f"رصيدك الحالي: <b>{balance}</b> نقطة",
                    parse_mode='HTML',
                    reply_markup=user_keyboard(),
                )
                return True
            state["action"] = "order_link"
            state["qty"] = q
            state["total"] = total
            await msg.answer(
                f"✅ تم اختيار العدد: <b>{q}</b>\n"
                f"💰 التكلفة الإجمالية: <b>{total}</b> نقطة\n\n"
                f"🔗 الآن أرسل رابط الحساب أو المنشور المطلوب:\n"
                f"للإلغاء أرسل /cancel",
                parse_mode='HTML',
            )
            return True

        if state["action"] == "order_link":
            link = text
            if not link or len(link) < 4:
                await msg.answer("⚠️ أرسل رابطاً صحيحاً، أو /cancel للإلغاء.")
                return True
            q = int(state.get("qty", 0))
            total = int(state.get("total", 0))
            balance = get_points(uid)
            if balance < total:
                user_state.pop(uid, None)
                await msg.answer("❌ نقاطك لم تعد كافية لإتمام الطلب.", reply_markup=user_keyboard())
                return True

            u = users[uid]
            u["points"] = balance - total
            save_users()
            user_state.pop(uid, None)

            smm_sid = int(item.get("smm_service_id", 0) or 0)
            provider = item.get("smm_provider", "")
            uname = f"@{msg.from_user.username}" if msg.from_user.username else "—"

            # ===== حالة: الخدمة مربوطة بمزوّد =====
            if smm_sid > 0 and provider in PROVIDERS:
                await msg.answer(
                    f"⏳ جارٍ إرسال طلبك إلى {provider_label(provider)}، يرجى الانتظار...",
                )
                resp = await smm_add_order(provider, smm_sid, link, q)
                if "order" in resp:
                    order_id = str(resp["order"])
                    smm_orders[order_id] = {
                        "order_id": order_id,
                        "provider": provider,
                        "user_id": uid,
                        "username": msg.from_user.username or "",
                        "service_label": item["label"],
                        "smm_service_id": smm_sid,
                        "link": link,
                        "quantity": q,
                        "cost_points": total,
                        "status": "Pending",
                        "created_at": date.today().isoformat(),
                    }
                    save_smm_orders()
                    await msg.answer(
                        f"✅ <b>تم تنفيذ طلبك بنجاح!</b>\n\n"
                        f"🛒 الخدمة: {item['label']}\n"
                        f"🔌 المزوّد: {provider_label(provider)}\n"
                        f"🔢 العدد: <b>{q}</b>\n"
                        f"💰 التكلفة: <b>{total}</b> نقطة\n"
                        f"🔗 الرابط: {link}\n"
                        f"🆔 رقم الطلب: <code>{order_id}</code>\n"
                        f"💵 رصيدك الآن: <b>{u['points']}</b> نقطة\n\n"
                        f"📦 سيبدأ التنفيذ خلال دقائق على موقع المزوّد.",
                        parse_mode='HTML',
                        reply_markup=user_keyboard(),
                        disable_web_page_preview=True,
                    )
                    try:
                        await bot.send_message(
                            ADMIN_ID,
                            f"🔔 <b>طلب رشق جديد (تلقائي)</b>\n\n"
                            f"👤 المستخدم: <code>{uid}</code> ({uname})\n"
                            f"🛒 الخدمة: {item['label']}\n"
                            f"🔌 المزوّد: {provider_label(provider)}\n"
                            f"🔢 العدد: <b>{q}</b>\n"
                            f"💰 التكلفة: <b>{total}</b> نقطة\n"
                            f"🔗 الرابط: {link}\n"
                            f"🆔 رقم طلب الموقع: <code>{order_id}</code>\n"
                            f"💵 رصيد المستخدم بعد الخصم: {u['points']}",
                            parse_mode='HTML',
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logging.warning(f"تعذر إشعار المالك: {e}")
                else:
                    u["points"] = u["points"] + total
                    save_users()
                    err = resp.get("error", "خطأ غير معروف من الموقع")
                    await msg.answer(
                        f"❌ <b>تعذّر تنفيذ الطلب على {provider_label(provider)}</b>\n\n"
                        f"السبب: {err}\n\n"
                        f"💵 تم إعادة <b>{total}</b> نقطة إلى رصيدك.\n"
                        f"رصيدك الحالي: <b>{u['points']}</b>",
                        parse_mode='HTML',
                        reply_markup=user_keyboard(),
                    )
                    try:
                        await bot.send_message(
                            ADMIN_ID,
                            f"⚠️ <b>فشل طلب رشق</b>\n\n"
                            f"👤 المستخدم: <code>{uid}</code> ({uname})\n"
                            f"🛒 الخدمة: {item['label']}\n"
                            f"🔌 المزوّد: {provider_label(provider)}\n"
                            f"🆔 معرّف الموقع: <code>{smm_sid}</code>\n"
                            f"🔢 العدد: {q}\n"
                            f"🔗 الرابط: {link}\n"
                            f"❌ الخطأ: <code>{err}</code>\n"
                            f"💵 تم إعادة {total} نقطة للمستخدم.",
                            parse_mode='HTML',
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logging.warning(f"تعذر إشعار المالك بالفشل: {e}")
                return True

            # ===== حالة: تنفيذ يدوي =====
            await msg.answer(
                f"✅ <b>تم استلام طلبك بنجاح</b>\n\n"
                f"🛒 الخدمة: {item['label']}\n"
                f"🔢 العدد: <b>{q}</b>\n"
                f"💰 التكلفة: <b>{total}</b> نقطة\n"
                f"🔗 الرابط: {link}\n"
                f"💵 رصيدك الآن: <b>{u['points']}</b> نقطة\n\n"
                f"📦 سيتم تنفيذ طلبك يدوياً قريباً.",
                parse_mode='HTML',
                reply_markup=user_keyboard(),
                disable_web_page_preview=True,
            )
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🔔 <b>طلب رشق جديد (يدوي)</b>\n\n"
                    f"👤 المستخدم: <code>{uid}</code> ({uname})\n"
                    f"🛒 الخدمة: {item['label']}\n"
                    f"🔢 العدد: <b>{q}</b>\n"
                    f"💰 التكلفة: <b>{total}</b> نقطة\n"
                    f"🔗 الرابط: {link}",
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logging.warning(f"تعذر إشعار المالك: {e}")
            return True

    # ----------------- آسيا سيل -----------------
    if state["action"] == "asia_phone":
        if not text.isdigit() or len(text) < 10:
            await msg.answer("⚠️ أرسل رقم آسيا سيل صحيح (أرقام فقط، مثال: 07701234567)")
            return True
        state["phone"] = text
        state["action"] = "asia_code"
        await msg.answer(
            f"✅ تم استلام رقمك: <code>{text}</code>\n\n"
            f"<b>الخطوة ٢:</b> 🔐 أرسل كود التحقق (PIN) لتعبئة الكارت.\n"
            f"للإلغاء أرسل /cancel",
            parse_mode='HTML',
        )
        return True

    if state["action"] == "asia_code":
        state["verify_code"] = text
        state["action"] = "asia_pick"
        await msg.answer(
            "✅ ممتاز.\n\n<b>الخطوة ٣:</b> 💵 اختر مبلغ الشحن:",
            parse_mode='HTML',
            reply_markup=asia_amount_keyboard(),
        )
        return True

    # ----------------- تحويل نقاط -----------------
    if state["action"] == "transfer_id":
        try:
            target_id = int(text)
        except ValueError:
            await msg.answer("⚠️ ايدي غير صحيح. أرسل رقم الايدي فقط.")
            return True
        if target_id == uid:
            await msg.answer("⚠️ لا يمكنك تحويل لنفسك.")
            return True
        state["target_id"] = target_id
        state["action"] = "transfer_amount"
        balance = get_points(uid)
        await msg.answer(
            f"✅ المستلم: <code>{target_id}</code>\n"
            f"💵 رصيدك: <b>{balance}</b>\n\n"
            f"📝 أرسل عدد النقاط للتحويل (موجب):",
            parse_mode='HTML',
        )
        return True

    if state["action"] == "transfer_amount":
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل عدداً صحيحاً موجباً.")
            return True
        balance = get_points(uid)
        if amount > balance:
            user_state.pop(uid, None)
            await msg.answer("❌ رصيدك لا يكفي.", reply_markup=user_keyboard())
            return True
        target_id = int(state["target_id"])
        if target_id not in users:
            register_user(target_id)
        users[uid]["points"] = balance - amount
        users[target_id]["points"] = int(users[target_id].get("points", 0)) + amount
        save_users()
        user_state.pop(uid, None)

        await msg.answer(
            f"✅ <b>تم التحويل بنجاح</b>\n\n"
            f"👤 إلى: <code>{target_id}</code>\n"
            f"💸 المبلغ: <b>{amount}</b> نقطة\n"
            f"💵 رصيدك الآن: <b>{users[uid]['points']}</b> نقطة",
            parse_mode='HTML',
            reply_markup=user_keyboard(),
        )
        try:
            sender_name = f"@{msg.from_user.username}" if msg.from_user.username else (msg.from_user.first_name or "مستخدم")
            await bot.send_message(
                target_id,
                f"🎉 <b>وصلتك نقاط!</b>\n\n"
                f"👤 من: <code>{uid}</code> ({sender_name})\n"
                f"💸 المبلغ: <b>{amount}</b> نقطة\n"
                f"💵 رصيدك الآن: <b>{users[target_id]['points']}</b> نقطة",
                parse_mode='HTML',
            )
        except Exception as e:
            logging.warning(f"تعذر إشعار المستلم: {e}")
        try:
            await bot.send_message(
                ADMIN_ID,
                f"💸 <b>تحويل نقاط بين مستخدمين</b>\n\n"
                f"👤 من: <code>{uid}</code>\n"
                f"👤 إلى: <code>{target_id}</code>\n"
                f"💰 المبلغ: <b>{amount}</b> نقطة",
                parse_mode='HTML',
            )
        except Exception:
            pass
        return True

    return False


# ================================================================
#               استقبال إدخال المالك النصي حسب الحالة
# ================================================================
@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID and ADMIN_ID in admin_state)
async def admin_input(msg: types.Message):
    state = admin_state[ADMIN_ID]
    text = msg.text or ""

    if text.strip() in ("/cancel", "إلغاء"):
        admin_state.pop(ADMIN_ID, None)
        await msg.answer("تم الإلغاء.", reply_markup=admin_main_keyboard())
        return

    # ---------- إعدادات بسيطة ----------
    if state["action"] == "set_daily":
        try:
            val = int(text.strip())
            if val < 0: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً.")
            return
        settings["daily_gift_points"] = val
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث نقاط الهدية إلى: <b>{val}</b>",
                         parse_mode='HTML', reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_ref":
        try:
            val = int(text.strip())
            if val < 0: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً.")
            return
        settings["referral_points"] = val
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث نقاط الإحالة إلى: <b>{val}</b>",
                         parse_mode='HTML', reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_bot_title":
        settings["bot_title"] = text.strip() or "ترويجكم"
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث الاسم إلى: <b>{settings['bot_title']}</b>",
                         parse_mode='HTML', reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_welcome":
        settings["welcome_text"] = text
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer("✅ تم تحديث رسالة الترحيب.", reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_support":
        v = text.strip().lstrip("@")
        settings["support_username"] = "" if v == "-" else v
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث الدعم إلى: @{settings['support_username'] or '—'}",
                         reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_asia_num":
        settings["asia_receiver_number"] = text.strip()
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث الرقم.", reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_asia_rate":
        try:
            v = int(text.strip())
            if v <= 0: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً.")
            return
        settings["asia_points_per_dollar"] = v
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ كل 1$ = {v:,} نقطة.", reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_footer":
        settings["footer_text"] = "" if text.strip() == "-" else text
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer("✅ تم تحديث التذييل.", reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_maint":
        settings["maintenance_text"] = text
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer("✅ تم تحديث نص الصيانة.", reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_decor_top":
        settings["decor_top"] = "" if text.strip() == "-" else text.strip()
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer("✅ تم تحديث الديكور العلوي.", reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_decor_bot":
        settings["decor_bottom"] = "" if text.strip() == "-" else text.strip()
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer("✅ تم تحديث الديكور السفلي.", reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_emoji":
        plat = state.get("plat", "default")
        key = f"service_emoji_{plat}"
        settings[key] = text.strip() or settings.get(key, "✨")
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث ايموجي {plat}.", reply_markup=admin_main_keyboard())
        return

    # ---------- إهداء ----------
    if state["action"] == "gift_id":
        try:
            target_id = int(text.strip())
        except ValueError:
            await msg.answer("⚠️ أرسل ايدي صحيح (أرقام فقط)، أو /cancel للإلغاء.")
            return
        state["action"] = "gift_amount"
        state["target_id"] = target_id
        target_balance = get_points(target_id)
        exists_note = "✓ المستخدم موجود" if target_id in users else "⚠️ غير مسجل — سيُسجَّل تلقائياً"
        await msg.answer(
            f"👤 المستخدم: <code>{target_id}</code>\n"
            f"💰 رصيده: <b>{target_balance}</b>\n"
            f"{exists_note}\n\n"
            f"📝 أرسل عدد النقاط (يمكن سالب للخصم):\n"
            f"للإلغاء أرسل /cancel",
            parse_mode='HTML',
        )
        return

    if state["action"] == "gift_amount":
        try:
            amount = int(text.strip())
            if amount == 0: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً غير صفر.")
            return
        target_id = int(state["target_id"])
        if target_id not in users:
            register_user(target_id)
        cur = int(users[target_id].get("points", 0))
        new_balance = cur + amount
        if new_balance < 0:
            await msg.answer(f"⚠️ الرصيد لا يكفي. المتاح: {cur}.")
            return
        users[target_id]["points"] = new_balance
        save_users()
        admin_state.pop(ADMIN_ID, None)
        word = "إهداء" if amount > 0 else "خصم"
        await msg.answer(
            f"✅ تم {word} <b>{abs(amount)}</b> نقطة\n"
            f"💵 رصيده: <b>{new_balance}</b>",
            parse_mode='HTML',
            reply_markup=admin_main_keyboard(),
        )
        try:
            if amount > 0:
                await bot.send_message(
                    target_id,
                    f"🎁 <b>هدية من المالك!</b>\n\n"
                    f"💰 +<b>{amount}</b> نقطة\n"
                    f"💵 رصيدك: <b>{new_balance}</b>",
                    parse_mode='HTML',
                )
            else:
                await bot.send_message(
                    target_id,
                    f"⚠️ تم خصم <b>{abs(amount)}</b> نقطة.\n"
                    f"💵 رصيدك: <b>{new_balance}</b>",
                    parse_mode='HTML',
                )
        except Exception as e:
            logging.warning(f"تعذر إشعار المستخدم: {e}")
        return

    # ---------- استعادة ----------
    if state["action"] == "confirm_reset":
        if text.strip() == "تأكيد":
            global menu, next_id
            menu = [json.loads(json.dumps(it)) for it in DEFAULT_MENU]
            save_menu()
            next_id = max(_all_ids_in(menu) + [100]) + 1
            admin_state.pop(ADMIN_ID, None)
            await msg.answer("✅ تمت استعادة القائمة الافتراضية.",
                             reply_markup=admin_main_keyboard())
        else:
            await msg.answer("لم يتم التأكيد. للتأكيد أرسل: تأكيد")
        return

    # ---------- اشتراك إجباري ----------
    if state["action"] == "fsub_add_chat":
        chat = text.strip()
        if not chat:
            await msg.answer("⚠️ أرسل @username أو chat_id.")
            return
        # نفحص أن البوت يستطيع الوصول للقناة
        try:
            info = await bot.get_chat(chat)
            title = info.title or info.username or chat
            url = None
            if info.username:
                url = f"https://t.me/{info.username}"
            elif getattr(info, "invite_link", None):
                url = info.invite_link
            else:
                # نحاول إنشاء رابط دعوة
                try:
                    inv = await bot.export_chat_invite_link(chat)
                    url = inv
                except Exception:
                    url = None

            ch = {
                "id": new_channel_id(),
                "chat": str(info.id) if not info.username else f"@{info.username}",
                "title": title,
                "url": url,
            }
            channels.append(ch)
            save_channels()
            admin_state.pop(ADMIN_ID, None)
            await msg.answer(
                f"✅ تمت إضافة: <b>{title}</b>\n"
                f"🔗 الرابط: {url or '—'}\n\n"
                f"تأكد أن البوت <b>أدمن</b> في القناة لكي يتحقق من اشتراك المستخدمين.",
                parse_mode='HTML',
                reply_markup=admin_main_keyboard(),
            )
        except Exception as e:
            await msg.answer(
                f"❌ تعذر الوصول للقناة/الكروب:\n<code>{e}</code>\n\n"
                f"تأكد من إضافة البوت كأدمن أولاً، ثم حاول مرة أخرى.\n"
                f"للإلغاء: /cancel",
                parse_mode='HTML',
            )
        return

    # ---------- بث ----------
    if state["action"] == "broadcast":
        admin_state.pop(ADMIN_ID, None)
        sent, failed = 0, 0
        for uid in list(users.keys()):
            try:
                await bot.send_message(uid, text, parse_mode='HTML')
                sent += 1
            except Exception:
                failed += 1
        await msg.answer(
            f"📣 تم البث.\n✅ نجحت: <b>{sent}</b>\n❌ فشلت: <b>{failed}</b>",
            parse_mode='HTML',
            reply_markup=admin_main_keyboard(),
        )
        return

    # ---------- تعديل عناصر القائمة ----------
    if state["action"] == "edit_label":
        item, _, _ = find_item(state["target_id"])
        if item:
            item["label"] = text
            save_menu()
            await msg.answer(f"✅ تم تحديث الاسم إلى: {text}", reply_markup=admin_main_keyboard())
        else:
            await msg.answer("⚠️ العنصر لم يعد موجوداً.")
        admin_state.pop(ADMIN_ID, None)
        return

    if state["action"] == "edit_text":
        item, _, _ = find_item(state["target_id"])
        if item:
            item["text"] = text
            save_menu()
            await msg.answer("✅ تم تحديث الرد.", reply_markup=admin_main_keyboard())
        else:
            await msg.answer("⚠️ العنصر لم يعد موجوداً.")
        admin_state.pop(ADMIN_ID, None)
        return

    if state["action"] == "edit_price":
        item, _, _ = find_item(state["target_id"])
        if not item:
            await msg.answer("⚠️ العنصر لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return
        try:
            val = int(text.strip())
            if val < 0: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً.")
            return
        item["price"] = val
        save_menu()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث السعر إلى: <b>{val}</b> نقطة لكل 1000",
                         parse_mode='HTML', reply_markup=admin_main_keyboard())
        return

    if state["action"] == "edit_desc":
        item, _, _ = find_item(state["target_id"])
        if not item:
            await msg.answer("⚠️ العنصر لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return
        new_desc = "" if text.strip() == "-" else text
        item["description"] = new_desc
        save_menu()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer("✅ تم تحديث الوصف." if new_desc else "✅ تم مسح الوصف.",
                         reply_markup=admin_main_keyboard())
        return

    if state["action"] == "edit_smmid":
        item, _, _ = find_item(state["target_id"])
        if not item:
            await msg.answer("⚠️ العنصر لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return
        try:
            sid = int(text.strip())
            if sid < 0: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً (أو 0 لإزالة الربط).")
            return
        item["smm_service_id"] = sid
        if sid == 0:
            item["smm_provider"] = ""
        save_menu()
        admin_state.pop(ADMIN_ID, None)
        if sid == 0:
            await msg.answer("✅ تم إزالة الربط (تنفيذ يدوي).",
                             reply_markup=admin_main_keyboard())
        else:
            prov = item.get("smm_provider", "")
            await msg.answer(
                f"✅ تم ربط الخدمة بمعرّف <code>{sid}</code> في {provider_label(prov)}.",
                parse_mode='HTML', reply_markup=admin_main_keyboard())
        return

    if state["action"] in ("edit_minq", "edit_maxq"):
        item, _, _ = find_item(state["target_id"])
        if not item:
            await msg.answer("⚠️ العنصر لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return
        try:
            val = int(text.strip())
            if val < 1: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً (≥ 1).")
            return
        field = "min_qty" if state["action"] == "edit_minq" else "max_qty"
        item[field] = val
        save_menu()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم التحديث: {val}", reply_markup=admin_main_keyboard())
        return

    # ---------- إضافة زر علوي ----------
    if state["action"] == "add_top":
        await _add_flow(msg, state, parent=None, where=state.get("where"))
        return

    # ---------- إضافة زر فرعي ----------
    if state["action"] == "add_sub":
        parent, _, _ = find_item(state["parent_id"])
        if parent is None:
            await msg.answer("⚠️ الزر الأب لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return
        await _add_flow(msg, state, parent=parent, where=None)
        return


async def _add_flow(msg: types.Message, state: dict, parent, where):
    """تدفق موحّد لإضافة عنصر جديد (top أو sub)."""
    text = msg.text or ""
    kind = state["kind"]

    def _commit(item: dict):
        if parent is None:
            if where == "start":
                menu.insert(0, item)
            else:
                menu.append(item)
        else:
            parent.setdefault("children", []).append(item)
        save_menu()

    if state["step"] == 1:
        state["tmp"]["label"] = text
        if kind == "regular":
            state["step"] = 2
            await msg.answer("📝 الآن أرسل نص الرد الذي يظهر عند الضغط:")
            return
        if kind == "service_item":
            state["step"] = 3
            await msg.answer("📝 أرسل سعر الخدمة بالنقاط لكل 1000 (رقم فقط):")
            return
        # الأنواع الأخرى لا تحتاج بيانات إضافية
        new_item = {
            "id": new_id(), "label": state["tmp"]["label"],
            "kind": kind, "text": "", "children": [],
        }
        _commit(new_item)
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم إضافة الزر «{new_item['label']}».",
                         reply_markup=admin_main_keyboard())
        return

    if state["step"] == 2:
        new_item = {
            "id": new_id(), "label": state["tmp"]["label"],
            "kind": kind, "text": text, "children": [],
        }
        _commit(new_item)
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم إضافة الزر «{new_item['label']}».",
                         reply_markup=admin_main_keyboard())
        return

    if state["step"] == 3:
        try:
            price = int(text.strip())
            if price < 0: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً للسعر.")
            return
        state["tmp"]["price"] = price
        # اختيار المزوّد من الأزرار (وليس نص)
        state["step"] = 35  # حالة انتظار اختيار المزوّد
        await msg.answer(
            "🔌 الآن اختر <b>المزوّد</b> الذي تريد ربط هذه الخدمة به:\n"
            "يمكنك أيضاً اختيار التنفيذ اليدوي.",
            parse_mode='HTML',
            reply_markup=provider_picker_keyboard("new", edit_mode=False),
        )
        return

    if state["step"] == 4:
        try:
            sid = int(text.strip())
            if sid < 0: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً (أو 0 للتنفيذ اليدوي).")
            return
        state["tmp"]["smm_service_id"] = sid
        if sid == 0:
            state["tmp"]["smm_provider"] = ""
        state["step"] = 5
        await msg.answer(
            "📝 أرسل وصف الخدمة (يظهر للمشترك).\n"
            "إذا لا تريد وصفاً أرسل: -"
        )
        return

    if state["step"] == 5:
        state["tmp"]["description"] = "" if text.strip() == "-" else text
        state["step"] = 6
        await msg.answer("📝 أرسل الحد الأدنى لعدد الرشق (مثال: 100):")
        return

    if state["step"] == 6:
        try:
            min_q = int(text.strip())
            if min_q < 1: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً (≥ 1).")
            return
        state["tmp"]["min_qty"] = min_q
        state["step"] = 7
        await msg.answer("📝 أرسل الحد الأقصى لعدد الرشق (مثال: 10000):")
        return

    if state["step"] == 7:
        try:
            max_q = int(text.strip())
            if max_q < 1: raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً (≥ 1).")
            return
        min_q = int(state["tmp"].get("min_qty", 1))
        if max_q < min_q:
            await msg.answer(f"⚠️ الحد الأقصى يجب أن يكون ≥ {min_q}.")
            return
        prov = state["tmp"].get("smm_provider", "")
        new_item = {
            "id": new_id(),
            "label": state["tmp"]["label"],
            "kind": "service_item",
            "text": "",
            "price": int(state["tmp"]["price"]),
            "smm_provider": prov,
            "smm_service_id": int(state["tmp"].get("smm_service_id", 0)),
            "description": state["tmp"].get("description", ""),
            "min_qty": min_q,
            "max_qty": max_q,
            "children": [],
        }

        if parent is None:
            if where == "start":
                menu.insert(0, new_item)
            else:
                menu.append(new_item)
        else:
            parent.setdefault("children", []).append(new_item)
        save_menu()
        admin_state.pop(ADMIN_ID, None)
        sid_txt = (
            f"🔌 المزوّد: {provider_label(prov)}\n"
            f"🆔 معرّف الموقع: <code>{new_item['smm_service_id']}</code>\n"
            if new_item['smm_service_id'] and prov else
            "🔌 تنفيذ يدوي (غير مربوط)\n"
        )
        await msg.answer(
            f"✅ تم إضافة الخدمة «{new_item['label']}»\n"
            f"💰 السعر: {new_item['price']} نقطة لكل 1000\n"
            f"{sid_txt}"
            f"🔢 العدد: {min_q} – {max_q}",
            parse_mode='HTML',
            reply_markup=admin_main_keyboard())
        return


# ================================================================
#       استقبال إدخال المستخدم (للطلبات والتحويل)
# ================================================================
@dp.message_handler(lambda m: m.from_user.id in user_state)
async def user_flow_input(msg: types.Message):
    await _process_user_flow(msg)


# ================================================================
#                          بدء التشغيل
# ================================================================
async def on_startup(_):
    global BOT_USERNAME
    try:
        me = await bot.get_me()
        BOT_USERNAME = me.username or ""
        logging.info(f"Bot started as @{BOT_USERNAME}")
    except Exception as e:
        logging.warning(f"تعذر جلب اسم البوت: {e}")


if __name__ == '__main__':
    keep_alive()
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

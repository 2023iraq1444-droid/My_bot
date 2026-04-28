import json
import os
import logging
from datetime import date
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from keep_alive import keep_alive

API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise RuntimeError("الرجاء ضبط متغير البيئة BOT_TOKEN قبل تشغيل البوت.")

ADMIN_ID = 5957783780

MENU_FILE = 'menu.json'
USERS_FILE = 'users.json'
SETTINGS_FILE = 'settings.json'

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
    """السعر لكل 1000 → نحسب التكلفة الإجمالية لعدد qty (تقريب لأعلى)."""
    if price_per_1000 <= 0 or qty <= 0:
        return 0
    return (int(price_per_1000) * int(qty) + 999) // 1000


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
            {"id": "31", "label": "⭐ النجوم", "kind": "regular",
             "text": "⭐ الشحن عبر النجوم\n\n(اضغط زر تعديل الرد لتغيير هذا النص من لوحة الأدمن)", "children": []},
            {"id": "32", "label": "📱 آسيا سيل", "kind": "regular",
             "text": "📱 الشحن عبر آسيا سيل\n\n(اضغط زر تعديل الرد لتغيير هذا النص من لوحة الأدمن)", "children": []},
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
             "text": "📷 خدمات إنستغرام\nاختر الخدمة المطلوبة:", "children": []},
            {"id": "42", "label": "✈️ تيليجرام", "kind": "regular",
             "text": "✈️ خدمات تيليجرام\nاختر الخدمة المطلوبة:", "children": []},
            {"id": "43", "label": "🎵 تيك توك", "kind": "regular",
             "text": "🎵 خدمات تيك توك\nاختر الخدمة المطلوبة:", "children": []},
        ],
    },
    {"id": "5", "label": "👑 مالك البوت", "kind": "regular",
     "text": "👑 مالك البوت\n\n(اضغط زر تعديل الرد لتغيير هذا النص من لوحة الأدمن)", "children": []},
    {"id": "6", "label": "👤 حسابي", "kind": "account", "text": "", "children": []},
    {"id": "7", "label": "💸 تحويل نقاط", "kind": "transfer", "text": "", "children": []},
]


def _ensure_kind(items):
    """Backward-compat: add 'kind' to old menu items that don't have it."""
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
        if _ensure_kind(it["children"]):
            changed = True
    return changed


def _ensure_transfer_button(items):
    """نضمن وجود زر تحويل النقاط للمستخدمين القدامى."""
    for it in items:
        if it.get("kind") == "transfer":
            return False
    items.append({
        "id": "7", "label": "💸 تحويل نقاط",
        "kind": "transfer", "text": "", "children": []
    })
    return True


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


# ================================================================
#                          عرض القائمة للمستخدم
# ================================================================

def items_keyboard(items, prefix="u"):
    kb = types.InlineKeyboardMarkup(row_width=2)
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
}

# حالة طلبات/عمليات المستخدمين
# user_state[user_id] = {
#   "action": "order_qty"|"order_link"|"transfer_id"|"transfer_amount",
#   "service_id": str, "qty": int, "total": int,
#   "target_id": int
# }
user_state = {}


async def handle_special_kind(c: types.CallbackQuery, item) -> bool:
    kind = item.get("kind", "regular")
    user = c.from_user

    if kind == "daily_gift":
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
            f"🎉 مبروك! حصلت على <b>{amount}</b> نقطة كهدية يومية.\n\n"
            f"💰 رصيدك الآن: <b>{u['points']}</b> نقطة\n"
            f"🔁 عُد غداً للحصول على هديتك التالية.",
            parse_mode='HTML',
        )
        return True

    if kind == "referral":
        ref_pts = int(settings.get("referral_points", 200))
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}" if BOT_USERNAME else f"(الرابط سيظهر بعد تشغيل البوت)"
        my_refs = int(users.get(user.id, {}).get("referrals", 0))
        await c.answer()
        await c.message.answer(
            f"🔗 <b>رابط الدعوة الخاص بك</b>\n\n"
            f"شارك هذا الرابط مع أصدقائك:\n"
            f"<code>{link}</code>\n\n"
            f"🎁 ستحصل على <b>{ref_pts}</b> نقطة عن كل صديق جديد يدخل البوت من رابطك.\n\n"
            f"👥 عدد دعواتك الناجحة: <b>{my_refs}</b>",
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
            info.append(f"\n📄 <b>الوصف:</b>\n{desc}")
        info.append(f"\n💵 رصيدك الحالي: <b>{get_points(user.id)}</b> نقطة")
        info.append(f"\n📝 أرسل الآن العدد المطلوب (رقم بين {min_q} و {max_q}):")
        info.append(f"للإلغاء أرسل /cancel")

        await c.answer()
        await c.message.answer("\n".join(info), parse_mode='HTML')
        return True

    if kind == "account":
        pts = get_points(user.id)
        refs = int(users.get(user.id, {}).get("referrals", 0))
        await c.answer()
        await c.message.answer(
            f"👤 <b>حسابك</b>\n\n"
            f"🆔 الايدي: <code>{user.id}</code>\n"
            f"💰 النقاط: <b>{pts}</b>\n"
            f"👥 عدد الدعوات: <b>{refs}</b>",
            parse_mode='HTML',
        )
        return True

    if kind == "stats":
        await c.answer()
        await c.message.answer(stats_text(), parse_mode='HTML')
        return True

    if kind == "transfer":
        balance = get_points(user.id)
        user_state[user.id] = {"action": "transfer_id"}
        await c.answer()
        await c.message.answer(
            f"💸 <b>تحويل نقاط لمستخدم آخر</b>\n\n"
            f"💵 رصيدك الحالي: <b>{balance}</b> نقطة\n\n"
            f"📝 أرسل الآن <b>الايدي (ID)</b> الخاص بالشخص الذي تريد التحويل إليه:\n"
            f"للإلغاء أرسل /cancel",
            parse_mode='HTML',
        )
        return True

    return False


# ================================================================
#                          لوحة المالك
# ================================================================

def admin_main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("➕ إضافة زر في البداية", callback_data="a:addtop:start"))
    kb.add(types.InlineKeyboardButton("➕ إضافة زر في النهاية", callback_data="a:addtop:end"))
    for item in menu:
        kb.row(
            types.InlineKeyboardButton(f"✏️ {item['label']}", callback_data=f"a:edit:{item['id']}"),
            types.InlineKeyboardButton("🗑", callback_data=f"a:del:{item['id']}"),
        )
    kb.add(types.InlineKeyboardButton("🎁 إهداء نقاط لمستخدم", callback_data="a:gift"))
    kb.add(types.InlineKeyboardButton("⚙️ الإعدادات العامة", callback_data="a:settings"))
    kb.add(types.InlineKeyboardButton("📊 إحصائيات البوت", callback_data="a:stats"))
    kb.add(types.InlineKeyboardButton("♻️ استعادة القائمة الافتراضية", callback_data="a:reset"))
    return kb


def admin_edit_keyboard(item):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kind_label = KIND_LABELS.get(item.get("kind", "regular"), "🔘 زر عادي")
    kb.add(types.InlineKeyboardButton(f"النوع: {kind_label}", callback_data=f"a:kind:{item['id']}"))
    kb.add(types.InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"a:lbl:{item['id']}"))
    if item.get("kind", "regular") == "regular":
        kb.add(types.InlineKeyboardButton("📝 تعديل الرد (النص)", callback_data=f"a:txt:{item['id']}"))
    if item.get("kind") == "service_item":
        cur_price = item.get("price", 0)
        cur_min = item.get("min_qty", 1)
        cur_max = item.get("max_qty", 10000)
        cur_desc = (item.get("description") or "").strip()
        desc_state = "✓ موجود" if cur_desc else "✗ غير موجود"
        kb.add(types.InlineKeyboardButton(
            f"💰 السعر/1000 (الآن: {cur_price})", callback_data=f"a:price:{item['id']}"))
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


def settings_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(
        f"🎁 نقاط الهدية اليومية: {settings['daily_gift_points']}",
        callback_data="a:setdaily"))
    kb.add(types.InlineKeyboardButton(
        f"🔗 نقاط الإحالة: {settings['referral_points']}",
        callback_data="a:setref"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="a:back"))
    return kb


admin_state = {}


# ================================================================
#                            الأوامر
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

    if is_new and referred_by and referred_by != msg.from_user.id:
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

    pts = get_points(msg.from_user.id)
    welcome = "🌟 أهلاً بك في بوت <b>ترويجكم</b>!" if is_new else "مرحباً بعودتك 👋"
    await msg.answer(
        f"{welcome}\n\n💰 رصيدك: <b>{pts}</b> نقطة\n🆔 ايديك: <code>{msg.from_user.id}</code>\n\nاختر من القائمة:",
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
        f"💰 إجمالي النقاط: <b>{total_points}</b>\n\n"
        f"🏆 أعلى 5 مستخدمين:\n{top_text}"
    )


# ================================================================
#                       ضغطات أزرار المستخدم
# ================================================================

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("u:"))
async def cb_user(c: types.CallbackQuery):
    register_user(c.from_user.id)
    item_id = c.data.split(":", 1)[1]
    item, _, _ = find_item(item_id)
    if not item:
        await c.answer("⚠️ هذا الزر لم يعد متوفراً.", show_alert=True)
        return

    # إذا ضغط زر آخر أثناء عملية جارية → نلغي العملية السابقة
    if c.from_user.id in user_state and item.get("kind") not in ("service_item", "transfer"):
        user_state.pop(c.from_user.id, None)

    if await handle_special_kind(c, item):
        return

    await c.answer()
    text = item.get("text") or item["label"]
    if item.get("children"):
        await c.message.answer(text, reply_markup=items_keyboard(item["children"], prefix="u"))
    else:
        await c.message.answer(text)


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
            await c.message.answer(
                "⚙️ <b>الإعدادات العامة</b>",
                parse_mode='HTML',
                reply_markup=settings_keyboard(),
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

    if action == "gift":
        admin_state[ADMIN_ID] = {"action": "gift_id"}
        await c.answer()
        await c.message.answer(
            "🎁 <b>إهداء نقاط لمستخدم</b>\n\n"
            "📝 أرسل ايدي (ID) المستخدم الذي تريد إهداءه نقاط:\n"
            "للإلغاء أرسل /cancel",
            parse_mode='HTML',
        )
        return

    if action == "reset":
        admin_state[ADMIN_ID] = {"action": "confirm_reset"}
        await c.answer()
        await c.message.answer(
            "⚠️ <b>تحذير:</b> سيتم استبدال القائمة الحالية بالقائمة الافتراضية الجديدة.\n\n"
            "لتأكيد، أرسل كلمة: <code>تأكيد</code>\n"
            "للإلغاء، أرسل: /cancel",
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

    if action == "price":
        item_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "edit_price", "target_id": item_id}
        await c.answer()
        await c.message.answer("📝 أرسل السعر الجديد بالنقاط لكل 1000 (رقم فقط):")
        return

    if action == "desc":
        item_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "edit_desc", "target_id": item_id}
        await c.answer()
        await c.message.answer(
            "📝 أرسل وصف الخدمة (سيظهر للمشترك عند اختيار الخدمة).\n"
            "لمسح الوصف أرسل: -"
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


# ================================================================
#                 استقبال إدخال المستخدم أثناء العمليات
# ================================================================

async def _process_user_flow(msg: types.Message) -> bool:
    """يعالج رسائل المستخدم في تسلسل طلب خدمة أو تحويل نقاط."""
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

            await msg.answer(
                f"✅ <b>تم استلام طلبك بنجاح</b>\n\n"
                f"🛒 الخدمة: {item['label']}\n"
                f"🔢 العدد: <b>{q}</b>\n"
                f"💰 التكلفة: <b>{total}</b> نقطة\n"
                f"🔗 الرابط: {link}\n"
                f"💵 رصيدك الآن: <b>{u['points']}</b> نقطة\n\n"
                f"📦 سيتم تنفيذ طلبك في أقرب وقت.",
                parse_mode='HTML',
                reply_markup=user_keyboard(),
                disable_web_page_preview=True,
            )

            try:
                uname = f"@{msg.from_user.username}" if msg.from_user.username else "—"
                await bot.send_message(
                    ADMIN_ID,
                    f"🔔 <b>طلب جديد</b>\n\n"
                    f"👤 المستخدم: <code>{uid}</code> ({uname})\n"
                    f"🛒 الخدمة: {item['label']}\n"
                    f"🔢 العدد: <b>{q}</b>\n"
                    f"💰 السعر/1000: {int(item.get('price', 0))} نقطة\n"
                    f"💰 التكلفة الإجمالية: <b>{total}</b> نقطة\n"
                    f"🔗 الرابط: {link}\n"
                    f"💵 رصيد المستخدم بعد الخصم: {u['points']}",
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logging.warning(f"تعذر إرسال إشعار للمالك: {e}")
            return True

    # ----------------- تحويل النقاط -----------------
    if state["action"] == "transfer_id":
        try:
            target_id = int(text)
        except ValueError:
            await msg.answer("⚠️ أرسل ايدي صحيح (أرقام فقط)، أو /cancel للإلغاء.")
            return True
        if target_id == uid:
            await msg.answer("⚠️ لا يمكنك التحويل لنفسك. أرسل ايدي مختلف أو /cancel للإلغاء.")
            return True
        if target_id not in users:
            await msg.answer(
                "⚠️ هذا المستخدم لم يستخدم البوت من قبل.\n"
                "تأكد من الايدي وأعد الإرسال، أو /cancel للإلغاء."
            )
            return True
        state["action"] = "transfer_amount"
        state["target_id"] = target_id
        await msg.answer(
            f"✅ تم اختيار المستخدم: <code>{target_id}</code>\n\n"
            f"💵 رصيدك الحالي: <b>{get_points(uid)}</b> نقطة\n"
            f"📝 الآن أرسل عدد النقاط التي تريد تحويلها (رقم فقط):\n"
            f"للإلغاء أرسل /cancel",
            parse_mode='HTML',
        )
        return True

    if state["action"] == "transfer_amount":
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً، أو /cancel للإلغاء.")
            return True
        balance = get_points(uid)
        if amount > balance:
            await msg.answer(
                f"❌ رصيدك غير كافٍ.\n"
                f"رصيدك: {balance} | المطلوب: {amount}\n"
                f"أرسل عدداً أقل أو /cancel للإلغاء."
            )
            return True
        target_id = int(state["target_id"])
        if target_id not in users:
            user_state.pop(uid, None)
            await msg.answer("⚠️ المستخدم المستهدف لم يعد موجوداً.", reply_markup=user_keyboard())
            return True
        # تنفيذ التحويل
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
        # إشعار المستلم
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
        # إشعار المالك
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

    if state["action"] == "set_daily":
        try:
            val = int(text.strip())
            if val < 0:
                raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً.")
            return
        settings["daily_gift_points"] = val
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث نقاط الهدية اليومية إلى: <b>{val}</b>",
                         parse_mode='HTML', reply_markup=admin_main_keyboard())
        return

    if state["action"] == "set_ref":
        try:
            val = int(text.strip())
            if val < 0:
                raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً.")
            return
        settings["referral_points"] = val
        save_settings()
        admin_state.pop(ADMIN_ID, None)
        await msg.answer(f"✅ تم تحديث نقاط الإحالة إلى: <b>{val}</b>",
                         parse_mode='HTML', reply_markup=admin_main_keyboard())
        return

    if state["action"] == "gift_id":
        try:
            target_id = int(text.strip())
        except ValueError:
            await msg.answer("⚠️ أرسل ايدي صحيح (أرقام فقط)، أو /cancel للإلغاء.")
            return
        state["action"] = "gift_amount"
        state["target_id"] = target_id
        target_balance = get_points(target_id)
        exists_note = "✓ المستخدم موجود في قاعدة البيانات" if target_id in users else "⚠️ المستخدم غير مسجل في البوت — سيُسجَّل تلقائياً"
        await msg.answer(
            f"👤 المستخدم: <code>{target_id}</code>\n"
            f"💰 رصيده الحالي: <b>{target_balance}</b> نقطة\n"
            f"{exists_note}\n\n"
            f"📝 الآن أرسل عدد النقاط التي تريد إهداءها (رقم صحيح، يمكن أن يكون سالباً للخصم):\n"
            f"للإلغاء أرسل /cancel",
            parse_mode='HTML',
        )
        return

    if state["action"] == "gift_amount":
        try:
            amount = int(text.strip())
            if amount == 0:
                raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً غير صفر، أو /cancel للإلغاء.")
            return
        target_id = int(state["target_id"])
        # تسجيل المستخدم إن لم يكن موجوداً
        if target_id not in users:
            register_user(target_id)
        # تطبيق الإضافة/الخصم مع منع الرصيد السالب
        cur = int(users[target_id].get("points", 0))
        new_balance = cur + amount
        if new_balance < 0:
            await msg.answer(
                f"⚠️ لا يمكن خصم هذا المبلغ — رصيد المستخدم {cur}.\n"
                f"أرسل قيمة أصغر أو /cancel للإلغاء."
            )
            return
        users[target_id]["points"] = new_balance
        save_users()
        admin_state.pop(ADMIN_ID, None)

        action_word = "إهداء" if amount > 0 else "خصم"
        await msg.answer(
            f"✅ تم {action_word} <b>{abs(amount)}</b> نقطة\n"
            f"👤 المستخدم: <code>{target_id}</code>\n"
            f"💵 رصيده الآن: <b>{new_balance}</b> نقطة",
            parse_mode='HTML',
            reply_markup=admin_main_keyboard(),
        )
        # إشعار المستخدم
        try:
            if amount > 0:
                await bot.send_message(
                    target_id,
                    f"🎁 <b>هدية من المالك!</b>\n\n"
                    f"💰 حصلت على: <b>{amount}</b> نقطة\n"
                    f"💵 رصيدك الآن: <b>{new_balance}</b> نقطة",
                    parse_mode='HTML',
                )
            else:
                await bot.send_message(
                    target_id,
                    f"⚠️ تم خصم <b>{abs(amount)}</b> نقطة من رصيدك من قبل المالك.\n"
                    f"💵 رصيدك الآن: <b>{new_balance}</b> نقطة",
                    parse_mode='HTML',
                )
        except Exception as e:
            logging.warning(f"تعذر إشعار المستخدم: {e}")
        return

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
            await msg.answer("لم يتم التأكيد. للتأكيد أرسل كلمة: تأكيد")
        return

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
            if val < 0:
                raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً (مثال: 150).")
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
        if new_desc:
            await msg.answer("✅ تم تحديث وصف الخدمة.", reply_markup=admin_main_keyboard())
        else:
            await msg.answer("✅ تم مسح وصف الخدمة.", reply_markup=admin_main_keyboard())
        return

    if state["action"] in ("edit_minq", "edit_maxq"):
        item, _, _ = find_item(state["target_id"])
        if not item:
            await msg.answer("⚠️ العنصر لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return
        try:
            val = int(text.strip())
            if val < 1:
                raise ValueError
        except ValueError:
            await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً (≥ 1).")
            return
        field = "min_qty" if state["action"] == "edit_minq" else "max_qty"
        item[field] = val
        save_menu()
        admin_state.pop(ADMIN_ID, None)
        label_ar = "الحد الأدنى" if field == "min_qty" else "الحد الأقصى"
        warn = ""
        cur_min = int(item.get("min_qty", 1))
        cur_max = int(item.get("max_qty", 10000))
        if cur_min > cur_max:
            warn = f"\n⚠️ تنبيه: الحد الأدنى ({cur_min}) أكبر من الحد الأقصى ({cur_max}). الرجاء تعديل أحدهما."
        await msg.answer(
            f"✅ تم تحديث {label_ar} إلى: <b>{val}</b>{warn}",
            parse_mode='HTML', reply_markup=admin_main_keyboard())
        return

    if state["action"] == "add_top":
        if state["step"] == 1:
            state["tmp"]["label"] = text
            kind = state["kind"]
            if kind == "regular":
                state["step"] = 2
                await msg.answer("📝 الآن أرسل نص الرد الذي يظهر عند الضغط:")
                return
            if kind == "service_item":
                state["step"] = 3
                await msg.answer("📝 أرسل سعر الخدمة بالنقاط لكل 1000 (رقم فقط):")
                return
            new_item = {
                "id": new_id(), "label": state["tmp"]["label"],
                "kind": kind, "text": "", "children": [],
            }
            if state["where"] == "start":
                menu.insert(0, new_item)
            else:
                menu.append(new_item)
            save_menu()
            admin_state.pop(ADMIN_ID, None)
            await msg.answer(f"✅ تم إضافة الزر «{new_item['label']}».",
                             reply_markup=admin_main_keyboard())
            return
        if state["step"] == 2:
            new_item = {
                "id": new_id(), "label": state["tmp"]["label"],
                "kind": state["kind"], "text": text, "children": [],
            }
            if state["where"] == "start":
                menu.insert(0, new_item)
            else:
                menu.append(new_item)
            save_menu()
            admin_state.pop(ADMIN_ID, None)
            await msg.answer(f"✅ تم إضافة الزر «{new_item['label']}».",
                             reply_markup=admin_main_keyboard())
            return
        if state["step"] == 3:
            try:
                price = int(text.strip())
                if price < 0:
                    raise ValueError
            except ValueError:
                await msg.answer("⚠️ أرسل رقماً صحيحاً للسعر.")
                return
            state["tmp"]["price"] = price
            state["step"] = 4
            await msg.answer(
                "📝 أرسل وصف الخدمة (يظهر للمشترك).\n"
                "إذا لا تريد وصفاً أرسل: -"
            )
            return
        if state["step"] == 4:
            state["tmp"]["description"] = "" if text.strip() == "-" else text
            state["step"] = 5
            await msg.answer("📝 أرسل الحد الأدنى لعدد الرشق (رقم صحيح موجب، مثال: 100):")
            return
        if state["step"] == 5:
            try:
                min_q = int(text.strip())
                if min_q < 1:
                    raise ValueError
            except ValueError:
                await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً (≥ 1).")
                return
            state["tmp"]["min_qty"] = min_q
            state["step"] = 6
            await msg.answer("📝 أرسل الحد الأقصى لعدد الرشق (رقم صحيح موجب، مثال: 10000):")
            return
        if state["step"] == 6:
            try:
                max_q = int(text.strip())
                if max_q < 1:
                    raise ValueError
            except ValueError:
                await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً (≥ 1).")
                return
            min_q = int(state["tmp"].get("min_qty", 1))
            if max_q < min_q:
                await msg.answer(f"⚠️ الحد الأقصى يجب أن يكون ≥ الحد الأدنى ({min_q}). أعد الإرسال:")
                return
            new_item = {
                "id": new_id(),
                "label": state["tmp"]["label"],
                "kind": "service_item",
                "text": "",
                "price": int(state["tmp"]["price"]),
                "description": state["tmp"].get("description", ""),
                "min_qty": min_q,
                "max_qty": max_q,
                "children": [],
            }
            if state["where"] == "start":
                menu.insert(0, new_item)
            else:
                menu.append(new_item)
            save_menu()
            admin_state.pop(ADMIN_ID, None)
            await msg.answer(
                f"✅ تم إضافة الخدمة «{new_item['label']}»\n"
                f"💰 السعر: {new_item['price']} نقطة لكل 1000\n"
                f"🔢 العدد: {min_q} – {max_q}",
                reply_markup=admin_main_keyboard())
            return

    if state["action"] == "add_sub":
        if state["step"] == 1:
            state["tmp"]["label"] = text
            kind = state["kind"]
            if kind == "regular":
                state["step"] = 2
                await msg.answer("📝 الآن أرسل نص الرد الذي يظهر عند الضغط:")
                return
            if kind == "service_item":
                state["step"] = 3
                await msg.answer("📝 أرسل سعر الخدمة بالنقاط لكل 1000 (رقم فقط):")
                return
            parent, _, _ = find_item(state["parent_id"])
            if parent is not None:
                parent.setdefault("children", []).append({
                    "id": new_id(), "label": state["tmp"]["label"],
                    "kind": kind, "text": "", "children": [],
                })
                save_menu()
                await msg.answer("✅ تم إضافة الزر الفرعي.", reply_markup=admin_main_keyboard())
            else:
                await msg.answer("⚠️ الزر الأب لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return
        if state["step"] == 2:
            parent, _, _ = find_item(state["parent_id"])
            if parent is not None:
                parent.setdefault("children", []).append({
                    "id": new_id(), "label": state["tmp"]["label"],
                    "kind": state["kind"], "text": text, "children": [],
                })
                save_menu()
                await msg.answer("✅ تم إضافة الزر الفرعي.", reply_markup=admin_main_keyboard())
            else:
                await msg.answer("⚠️ الزر الأب لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return
        if state["step"] == 3:
            try:
                price = int(text.strip())
                if price < 0:
                    raise ValueError
            except ValueError:
                await msg.answer("⚠️ أرسل رقماً صحيحاً للسعر.")
                return
            state["tmp"]["price"] = price
            state["step"] = 4
            await msg.answer(
                "📝 أرسل وصف الخدمة (يظهر للمشترك).\n"
                "إذا لا تريد وصفاً أرسل: -"
            )
            return
        if state["step"] == 4:
            state["tmp"]["description"] = "" if text.strip() == "-" else text
            state["step"] = 5
            await msg.answer("📝 أرسل الحد الأدنى لعدد الرشق (رقم صحيح موجب، مثال: 100):")
            return
        if state["step"] == 5:
            try:
                min_q = int(text.strip())
                if min_q < 1:
                    raise ValueError
            except ValueError:
                await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً (≥ 1).")
                return
            state["tmp"]["min_qty"] = min_q
            state["step"] = 6
            await msg.answer("📝 أرسل الحد الأقصى لعدد الرشق (رقم صحيح موجب، مثال: 10000):")
            return
        if state["step"] == 6:
            try:
                max_q = int(text.strip())
                if max_q < 1:
                    raise ValueError
            except ValueError:
                await msg.answer("⚠️ أرسل رقماً صحيحاً موجباً (≥ 1).")
                return
            min_q = int(state["tmp"].get("min_qty", 1))
            if max_q < min_q:
                await msg.answer(f"⚠️ الحد الأقصى يجب أن يكون ≥ الحد الأدنى ({min_q}). أعد الإرسال:")
                return
            parent, _, _ = find_item(state["parent_id"])
            if parent is not None:
                parent.setdefault("children", []).append({
                    "id": new_id(),
                    "label": state["tmp"]["label"],
                    "kind": "service_item",
                    "text": "",
                    "price": int(state["tmp"]["price"]),
                    "description": state["tmp"].get("description", ""),
                    "min_qty": min_q,
                    "max_qty": max_q,
                    "children": [],
                })
                save_menu()
                await msg.answer(
                    f"✅ تم إضافة الخدمة بسعر {state['tmp']['price']} نقطة لكل 1000\n"
                    f"🔢 العدد: {min_q} – {max_q}",
                    reply_markup=admin_main_keyboard())
            else:
                await msg.answer("⚠️ الزر الأب لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
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

import json
import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from keep_alive import keep_alive

# التوكن يُقرأ من متغير بيئي اسمه BOT_TOKEN (للأمان — لا يُكتب في الكود)
API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise RuntimeError("الرجاء ضبط متغير البيئة BOT_TOKEN قبل تشغيل البوت.")

# معرّف المالك (الأدمن)
ADMIN_ID = 5957783780

MENU_FILE = 'menu.json'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# تخزين بسيط للمستخدمين والنقاط في الذاكرة
users_points = {}
known_users = set()


DEFAULT_MENU = [
    {"id": "1",  "label": "🛒 الخدمات",            "text": "🛒 الخدمات\nاختر الخدمة المطلوبة من قائمة الخدمات المتوفرة.", "children": []},
    {"id": "2",  "label": "📢 تمويل قناتك",        "text": "📢 تمويل قناتك\nمول قناتك بسهولة عبر نقاط ترويجكم.",          "children": []},
    {"id": "3",  "label": "🏪 سوق ترويجكم",        "text": "🏪 سوق ترويجكم\nتصفح أحدث العروض والخدمات في السوق.",          "children": []},
    {"id": "4",  "label": "👤 الحساب",             "text": "__ACCOUNT__",                                                  "children": []},
    {"id": "5",  "label": "💰 تجميع النقاط",       "text": "💰 تجميع النقاط\nاجمع النقاط عبر تنفيذ المهام اليومية ودعوة الأصدقاء.", "children": []},
    {"id": "6",  "label": "🎫 استخدام الكود",      "text": "🎫 استخدام الكود\nأرسل الكود الترويجي للحصول على نقاط مجانية.", "children": []},
    {"id": "7",  "label": "📦 طلباتي",             "text": "📦 طلباتي\nلا توجد لديك طلبات حالياً.",                         "children": []},
    {"id": "8",  "label": "ℹ️ معلومات الطلب",      "text": "ℹ️ معلومات الطلب\nلمعرفة تفاصيل أي طلب أرسل رقم الطلب الخاص بك.", "children": []},
    {"id": "9",  "label": "🔄 تحويل النقاط",       "text": "🔄 تحويل النقاط\nيمكنك تحويل نقاطك إلى أي مستخدم آخر بسهولة.",  "children": []},
    {"id": "10", "label": "📊 الإحصائيات",         "text": "__STATS__",                                                    "children": []},
    {"id": "11", "label": "❓ مساعدة",             "text": "❓ مساعدة\nللتواصل مع الدعم، أرسل رسالتك وسيتم الرد عليك في أقرب وقت.", "children": []},
    {"id": "12", "label": "💳 شحن النقاط",         "text": "💳 شحن النقاط\nيمكنك شحن نقاطك عبر إحدى وسائل الدفع المتوفرة.", "children": []},
    {"id": "13", "label": "📜 الشروط",             "text": "📜 الشروط والأحكام\nباستخدامك للبوت فأنت توافق على جميع الشروط المعلنة.", "children": []},
    {"id": "14", "label": "🌟 اشتراك Premium",     "text": "🌟 اشتراك Premium\nاشترك للحصول على مزايا حصرية وخصومات خاصة.", "children": []},
    {"id": "15", "label": "🔗 قنوات والبوتات الرسمية", "text": "🔗 القنوات والبوتات الرسمية\nتابع قنواتنا الرسمية للاطلاع على آخر التحديثات.", "children": []},
]


def load_menu():
    if os.path.exists(MENU_FILE):
        try:
            with open(MENU_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return [dict(item, children=list(item.get("children", []))) for item in DEFAULT_MENU]


menu = load_menu()


def _all_ids():
    ids = []
    for it in menu:
        ids.append(int(it["id"]))
        for sub in it.get("children", []):
            ids.append(int(sub["id"]))
    return ids


next_id = max(_all_ids() + [15]) + 1


def save_menu():
    with open(MENU_FILE, 'w', encoding='utf-8') as f:
        json.dump(menu, f, ensure_ascii=False, indent=2)


def new_id():
    global next_id
    nid = str(next_id)
    next_id += 1
    return nid


def find_item(item_id):
    for it in menu:
        if it["id"] == item_id:
            return it, menu, None
        for sub in it.get("children", []):
            if sub["id"] == item_id:
                return sub, it["children"], it
    return None, None, None


def register_user(user_id: int):
    known_users.add(user_id)
    if user_id not in users_points:
        users_points[user_id] = 0


def user_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    row = []
    for item in menu:
        row.append(types.InlineKeyboardButton(item["label"], callback_data=f"u:{item['id']}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb


def submenu_keyboard(item):
    kb = types.InlineKeyboardMarkup(row_width=2)
    row = []
    for sub in item.get("children", []):
        row.append(types.InlineKeyboardButton(sub["label"], callback_data=f"u:{sub['id']}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb


def render_user_text(item, user) -> str:
    if item["text"] == "__ACCOUNT__":
        pts = users_points.get(user.id, 0)
        return f"👤 حسابك\n\n• الايدي : {user.id}\n• النقاط : {pts}"
    if item["text"] == "__STATS__":
        return (
            "📊 الإحصائيات\n"
            f"👥 عدد المستخدمين: {len(known_users)}\n"
            f"💰 إجمالي النقاط: {sum(users_points.values())}"
        )
    return item["text"]


def admin_main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("➕ إضافة زر في البداية", callback_data="a:addtop:start"))
    kb.add(types.InlineKeyboardButton("➕ إضافة زر في النهاية", callback_data="a:addtop:end"))
    for item in menu:
        kb.row(
            types.InlineKeyboardButton(f"✏️ {item['label']}", callback_data=f"a:edit:{item['id']}"),
            types.InlineKeyboardButton("🗑", callback_data=f"a:del:{item['id']}"),
        )
    kb.add(types.InlineKeyboardButton("📊 إحصائيات البوت", callback_data="a:stats"))
    return kb


def admin_edit_keyboard(item):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"a:lbl:{item['id']}"))
    kb.add(types.InlineKeyboardButton("📝 تعديل الرد", callback_data=f"a:txt:{item['id']}"))
    kb.add(types.InlineKeyboardButton("➕ إضافة زر فرعي", callback_data=f"a:addsub:{item['id']}"))
    if item.get("children"):
        for sub in item["children"]:
            kb.row(
                types.InlineKeyboardButton(f"✏️ {sub['label']}", callback_data=f"a:edit:{sub['id']}"),
                types.InlineKeyboardButton("🗑", callback_data=f"a:del:{sub['id']}"),
            )
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="a:back"))
    return kb


admin_state = {}


@dp.message_handler(commands=['start'])
async def cmd_start(msg: types.Message):
    register_user(msg.from_user.id)

    if msg.from_user.id == ADMIN_ID:
        await msg.answer(
            "⚙️ <b>لوحة المالك — تعديل الأزرار</b>\n\n"
            "من هنا يمكنك:\n"
            "• إضافة زر جديد في بداية أو نهاية القائمة\n"
            "• تعديل اسم أو رد أي زر\n"
            "• إضافة أزرار فرعية داخل أي زر\n"
            "• حذف أي زر\n\n"
            "كل التغييرات تُحفظ تلقائياً.",
            parse_mode='HTML',
            reply_markup=admin_main_keyboard(),
        )

    pts = users_points.get(msg.from_user.id, 0)
    await msg.answer(
        f"• نقاطك : {pts}\n• ايديك : {msg.from_user.id}",
        reply_markup=user_keyboard(),
    )


@dp.message_handler(commands=['admin'])
async def cmd_admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ هذا الأمر مخصص للمالك فقط.")
        return
    await msg.answer(
        "⚙️ <b>لوحة المالك — تعديل الأزرار</b>",
        parse_mode='HTML',
        reply_markup=admin_main_keyboard(),
    )


def stats_text() -> str:
    total_users = len(known_users)
    total_points = sum(users_points.values())
    top = sorted(users_points.items(), key=lambda x: x[1], reverse=True)[:5]
    top_text = "\n".join(
        [f"  {i+1}. {uid} — {p} نقطة" for i, (uid, p) in enumerate(top)]
    ) or "  لا يوجد مستخدمون بعد."
    return (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👥 إجمالي المستخدمين: <b>{total_users}</b>\n"
        f"💰 إجمالي النقاط: <b>{total_points}</b>\n\n"
        f"🏆 أعلى 5 مستخدمين:\n{top_text}"
    )


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("u:"))
async def cb_user(c: types.CallbackQuery):
    register_user(c.from_user.id)
    item_id = c.data.split(":", 1)[1]
    item, _, _ = find_item(item_id)
    if not item:
        await c.answer("⚠️ هذا الزر لم يعد متوفراً.", show_alert=True)
        return
    await c.answer()
    text = render_user_text(item, c.from_user)
    if item.get("children"):
        await c.message.answer(text, reply_markup=submenu_keyboard(item))
    else:
        await c.message.answer(text)


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
                "⚙️ <b>لوحة المالك — تعديل الأزرار</b>",
                parse_mode='HTML',
                reply_markup=admin_main_keyboard(),
            )
        except Exception:
            await c.message.answer(
                "⚙️ <b>لوحة المالك — تعديل الأزرار</b>",
                parse_mode='HTML',
                reply_markup=admin_main_keyboard(),
            )
        return

    if action == "stats":
        await c.answer()
        await c.message.answer(stats_text(), parse_mode='HTML')
        return

    if action == "addtop":
        where = parts[2]
        admin_state[ADMIN_ID] = {"action": "add_top", "where": where, "step": 1, "tmp": {}}
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

    if action == "addsub":
        parent_id = parts[2]
        admin_state[ADMIN_ID] = {"action": "add_sub", "parent_id": parent_id, "step": 1, "tmp": {}}
        await c.answer()
        await c.message.answer("📝 أرسل اسم الزر الفرعي الجديد:")
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
                "⚙️ <b>لوحة المالك — تعديل الأزرار</b>",
                parse_mode='HTML',
                reply_markup=admin_main_keyboard(),
            )
        except Exception:
            await c.message.answer(
                "✅ تم تحديث القائمة.",
                reply_markup=admin_main_keyboard(),
            )
        return


@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID and ADMIN_ID in admin_state)
async def admin_input(msg: types.Message):
    state = admin_state[ADMIN_ID]
    text = msg.text or ""

    if text.strip() in ("/cancel", "إلغاء"):
        admin_state.pop(ADMIN_ID, None)
        await msg.answer("تم الإلغاء.", reply_markup=admin_main_keyboard())
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

    if state["action"] == "add_top":
        if state["step"] == 1:
            state["tmp"]["label"] = text
            state["step"] = 2
            await msg.answer("📝 الآن أرسل نص الرد الذي يظهر عند الضغط على هذا الزر:")
            return
        if state["step"] == 2:
            new_item = {
                "id": new_id(),
                "label": state["tmp"]["label"],
                "text": text,
                "children": [],
            }
            if state["where"] == "start":
                menu.insert(0, new_item)
            else:
                menu.append(new_item)
            save_menu()
            await msg.answer(
                f"✅ تم إضافة الزر «{new_item['label']}».",
                reply_markup=admin_main_keyboard(),
            )
            admin_state.pop(ADMIN_ID, None)
            return

    if state["action"] == "add_sub":
        if state["step"] == 1:
            state["tmp"]["label"] = text
            state["step"] = 2
            await msg.answer("📝 الآن أرسل نص الرد الذي يظهر عند الضغط على هذا الزر الفرعي:")
            return
        if state["step"] == 2:
            parent, _, _ = find_item(state["parent_id"])
            if parent is not None:
                parent.setdefault("children", []).append({
                    "id": new_id(),
                    "label": state["tmp"]["label"],
                    "text": text,
                    "children": [],
                })
                save_menu()
                await msg.answer(
                    "✅ تم إضافة الزر الفرعي.",
                    reply_markup=admin_main_keyboard(),
                )
            else:
                await msg.answer("⚠️ الزر الأب لم يعد موجوداً.")
            admin_state.pop(ADMIN_ID, None)
            return


if __name__ == '__main__':
    keep_alive()
    executor.start_polling(dp, skip_updates=True)

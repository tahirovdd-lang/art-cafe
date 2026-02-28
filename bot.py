import os
import json
import logging
import asyncio
import re

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден в переменных окружения")

# ====== НАСТРОЙКИ ======
BOT_USERNAME = "ArtCafe_Samarkand_bot"      # без @ (можешь поменять на реальный username)
ADMIN_ID = 6013591658
WEBAPP_URL = "https://tahirovdd-lang.github.io/art-cafe/?v=1"  # ✅ поставь свой URL

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ====== ПРИВЕТСТВИЕ (3 ЯЗЫКА + ФЛАГИ) ======
WELCOME_3LANG = (
    "🇷🇺 <b>Добро пожаловать в Art Cafe — Samarkand!</b> 👋\n"
    "Выберите любимые блюда и оформите заказ — просто нажмите «Открыть» ниже.\n\n"
    "🇺🇿 <b>Art Cafe — Samarkand ga xush kelibsiz!</b> 👋\n"
    "Sevimli taomlaringizni tanlang va buyurtma bering — "
    "buning uchun pastdagi «Ochish» tugmasini bosing.\n\n"
    "🇬🇧 <b>Welcome to Art Cafe — Samarkand!</b> 👋\n"
    "Choose your favorite dishes and place an order — just tap “Open” below."
)

# ====== КНОПКА (НИЖНЯЯ) ======
MENU_BTN_TEXT = "Ochish / Открыть / Open"

def menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=MENU_BTN_TEXT, web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True
    )

async def send_welcome(message: types.Message):
    await message.answer(WELCOME_3LANG, reply_markup=menu_kb())

def safe_html(s) -> str:
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))

def normalize_phone(phone: str) -> str:
    """
    Приводим к формату +998...
    Если пришло '998...' -> '+998...'
    Если пришло с пробелами/скобками -> чистим.
    """
    if not phone:
        return ""
    p = phone.strip()
    p = re.sub(r"[^\d+]", "", p)  # оставить цифры и +
    if p.startswith("998"):
        p = "+" + p
    return p

def payment_label(val: str) -> str:
    v = (val or "").strip().lower()
    if v in ("cash", "кэш", "кеш", "нал", "наличные", "naqd", "naqdi"):
        return "Наличные"
    if v in ("card", "карта", "karta", "plastik", "plastic"):
        return "Карта"
    return val or "—"

def type_label(val: str) -> str:
    v = (val or "").strip().lower()
    if v in ("delivery", "доставка"):
        return "Доставка"
    if v in ("pickup", "самовывоз", "takeaway"):
        return "Самовывоз"
    return val or "—"

def build_user_link_html(from_user: types.User, data: dict) -> str:
    """
    Кликабельный ник:
    - если есть username -> ссылка на https://t.me/username
    - иначе -> ссылка tg://user?id=...
    """
    tg = data.get("tg") or {}
    username = tg.get("username") or from_user.username
    first_name = tg.get("first_name") or from_user.first_name or "Клиент"

    if username:
        u = safe_html(username.lstrip("@"))
        return f'👤 Клиент: <a href="https://t.me/{u}">@{u}</a>'
    return f'👤 Клиент: <a href="tg://user?id={from_user.id}">{safe_html(first_name)}</a>'

def build_phone_html(phone: str) -> str:
    p = normalize_phone(phone)
    if not p:
        return "📞 Телефон: <b>—</b>"
    return f'📞 Телефон: <a href="tel:{safe_html(p)}"><b>{safe_html(p)}</b></a>'

# ========= START =========
@dp.message(CommandStart())
async def start(message: types.Message, command: CommandObject):
    await send_welcome(message)

@dp.message(Command("menu"))
async def menu_cmd(message: types.Message):
    await send_welcome(message)

@dp.message(F.text == MENU_BTN_TEXT)
async def menu_button(message: types.Message):
    # WebApp откроется сам
    pass

# ========= ПРИЁМ ДАННЫХ ИЗ WEBAPP =========
@dp.message(F.web_app_data)
async def webapp_order(message: types.Message):
    raw = message.web_app_data.data
    try:
        data = json.loads(raw)
    except Exception:
        data = {}

    await message.answer("✅ Заказ принят! Спасибо за ваш выбор 😊", reply_markup=menu_kb())

    # Заказ (поддержка двух форматов: order{name:qty} и items[{name_lang/..,qty}])
    order = data.get("order", {})
    items_list = data.get("items", [])

    items_lines = []

    if isinstance(items_list, list) and items_list:
        for it in items_list:
            name = it.get("name_lang") or it.get("name_ru") or it.get("id") or "—"
            qty = it.get("qty") or 0
            items_lines.append(f"• {safe_html(name)} × <b>{safe_html(qty)}</b>")
    elif isinstance(order, dict) and order:
        for name, qty in order.items():
            items_lines.append(f"• {safe_html(name)} × <b>{safe_html(qty)}</b>")
    else:
        items_lines.append("• —")

    items = "\n".join(items_lines)

    # Поля (поддержка нескольких вариантов ключей)
    phone = data.get("phone", "") or (data.get("customer", {}) or {}).get("phone", "")
    address = data.get("address", "") or (data.get("customer", {}) or {}).get("address", "")
    pay = payment_label(data.get("payment") or data.get("pay"))
    otype = type_label(data.get("type") or data.get("order_type"))
    total = data.get("total", "—")
    comment = data.get("comment", "")

    order_id = data.get("order_id") or data.get("id") or "—"
    total_num = data.get("total_num")

    admin_text = (
        "📩 <b>НОВЫЙ ЗАКАЗ — Art Cafe</b>\n\n"
        f"🧾 Заказ: <b>{safe_html(order_id)}</b>\n"
        f"{build_user_link_html(message.from_user, data)}\n"
        f"{build_phone_html(phone)}\n"
        f"🚚 Тип: <b>{safe_html(otype)}</b>\n"
        f"📍 Адрес: <b>{safe_html(address) if address else '—'}</b>\n"
        f"💳 Оплата: <b>{safe_html(pay)}</b>\n"
    )

    if comment:
        admin_text += f"💬 Комментарий: <b>{safe_html(comment)}</b>\n"

    admin_text += "\n" + items + "\n\n"

    # Итог
    if total_num is not None:
        try:
            admin_text += f"💰 <b>{safe_html(int(total_num))}</b> сум"
        except Exception:
            admin_text += f"💰 <b>{safe_html(total)}</b> сум"
    else:
        admin_text += f"💰 <b>{safe_html(total)}</b> сум"

    await bot.send_message(ADMIN_ID, admin_text)

# ========= FALLBACK =========
@dp.message()
async def fallback(message: types.Message):
    await send_welcome(message)

async def main():
    logging.info("🚀 Art Cafe bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

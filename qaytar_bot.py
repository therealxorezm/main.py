# ============================================
# QAYTAR BOT — Система лояльности для ресторанов
# Автор: Камолиддин
# ============================================
# Установить перед запуском:
# pip install aiogram aiosqlite qrcode pillow
# ============================================

import asyncio
import os
import qrcode
import io
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ============================================
# СОСТОЯНИЯ
# ============================================
class RegistrationStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_name = State()

class AddPointsStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_amount = State()

class RedeemStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_points = State()

class AddRestaurantStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_telegram_id = State()

# ============================================
# БАЗА ДАННЫХ
# ============================================
async def create_database():
    async with .connect("qaytar.db") as db:
        # Таблица клиентов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                phone TEXT UNIQUE,
                name TEXT,
                points INTEGER DEFAULT 0,
                total_visits INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица ресторанов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS restaurants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                telegram_id INTEGER UNIQUE,
                total_sales INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица транзакций (история начислений)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_phone TEXT,
                restaurant_id INTEGER,
                amount INTEGER,
                points_added INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    print("✅ База данных готова!")

# ============================================
# ФУНКЦИЯ ГЕНЕРАЦИИ QR-КОДА
# ============================================
def generate_qr(data: str) -> bytes:
    """Генерирует QR-код и возвращает байты изображения"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#FF6B00", back_color="white")  # Оранжевый цвет Qaytar
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ============================================
# КЛАВИАТУРЫ
# ============================================
client_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💳 Мои баллы"), KeyboardButton(text="📱 Мой QR-код")],
        [KeyboardButton(text="🎁 Потратить баллы"), KeyboardButton(text="📊 История")],
    ],
    resize_keyboard=True
)

restaurant_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Начислить баллы"), KeyboardButton(text="➖ Списать баллы")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🔍 Найти клиента")],
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏪 Добавить ресторан"), KeyboardButton(text="📊 Все рестораны")],
        [KeyboardButton(text="👥 Все клиенты"), KeyboardButton(text="💰 Доходы")],
    ],
    resize_keyboard=True
)

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================
async def is_restaurant(user_id: int) -> bool:
    """Проверяет является ли пользователь рестораном"""
    async with aiosqlite.connect("qaytar.db") as db:
        cursor = await db.execute("SELECT * FROM restaurants WHERE telegram_id = ?", (user_id,))
        return await cursor.fetchone() is not None

async def get_client_by_phone(phone: str):
    """Находит клиента по номеру телефона"""
    async with aiosqlite.connect("qaytar.db") as db:
        cursor = await db.execute("SELECT * FROM clients WHERE phone = ?", (phone,))
        return await cursor.fetchone()

async def get_client_by_telegram_id(telegram_id: int):
    """Находит клиента по Telegram ID"""
    async with aiosqlite.connect("qaytar.db") as db:
        cursor = await db.execute("SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,))
        return await cursor.fetchone()

# ============================================
# КОМАНДА /start
# ============================================
@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id

    # Проверяем: администратор?
    if user_id == ADMIN_ID:
        await message.answer(
            "👑 Добро пожаловать, Камолиддин!\n"
            "Панель администратора Qaytar",
            reply_markup=admin_keyboard
        )
        return

    # Проверяем: ресторан?
    if await is_restaurant(user_id):
        async with aiosqlite.connect("qaytar.db") as db:
            cursor = await db.execute("SELECT name FROM restaurants WHERE telegram_id = ?", (user_id,))
            restaurant = await cursor.fetchone()
        await message.answer(
            f"🍽️ Добро пожаловать, {restaurant[0]}!\n"
            f"Панель управления Qaytar",
            reply_markup=restaurant_keyboard
        )
        return

    # Проверяем: клиент уже зарегистрирован?
    client = await get_client_by_telegram_id(user_id)
    if client:
        await message.answer(
            f"👋 С возвращением, {client[3]}!\n\n"
            f"💰 Ваши баллы: {client[4]}\n"
            f"🏆 Всего визитов: {client[5]}",
            reply_markup=client_keyboard
        )
        return

    # Новый клиент
    await message.answer(
        "👋 Добро пожаловать в Qaytar!\n\n"
        "🎯 Накапливай баллы в ресторанах и получай скидки!\n\n"
        "Введи свой номер телефона:\n"
        "Пример: +998901234567"
    )
    await state.set_state(RegistrationStates.waiting_for_phone)

# ============================================
# РЕГИСТРАЦИЯ КЛИЕНТА
# ============================================
@dp.message(RegistrationStates.waiting_for_phone)
async def get_phone(message: Message, state: FSMContext):
    phone = message.text.strip()

    if not phone.startswith("+998") or len(phone) < 13:
        await message.answer("❌ Неверный формат!\nВведи: +998901234567")
        return

    existing = await get_client_by_phone(phone)
    if existing:
        await message.answer(
            f"✅ Этот номер уже зарегистрирован!\n"
            f"👤 Имя: {existing[3]}\n"
            f"💰 Баллы: {existing[4]}",
            reply_markup=client_keyboard
        )
        await state.clear()
        return

    await state.update_data(phone=phone)
    await message.answer("Отлично! Теперь введи своё имя:")
    await state.set_state(RegistrationStates.waiting_for_name)

@dp.message(RegistrationStates.waiting_for_name)
async def get_name(message: Message, state: FSMContext):
    name = message.text.strip()
    data = await state.get_data()
    phone = data["phone"]
    user_id = message.from_user.id

    async with aiosqlite.connect("qaytar.db") as db:
        await db.execute(
            "INSERT INTO clients (telegram_id, phone, name, points) VALUES (?, ?, ?, ?)",
            (user_id, phone, name, 0)
        )
        await db.commit()

    await message.answer(
        f"🎉 Добро пожаловать, {name}!\n\n"
        f"💳 Ваши баллы: 0\n"
        f"📱 Нажмите 'Мой QR-код' чтобы получить карточку",
        reply_markup=client_keyboard
    )
    await state.clear()

# ============================================
# МОИ БАЛЛЫ
# ============================================
@dp.message(F.text == "💳 Мои баллы")
async def my_points(message: Message):
    client = await get_client_by_telegram_id(message.from_user.id)
    if not client:
        await message.answer("❌ Вы не зарегистрированы! Напишите /start")
        return

    # Считаем на что хватает баллов
    # 1000 баллов = 10,000 сум скидки
    discount = (client[4] // 1000) * 10000

    await message.answer(
        f"💳 ВАШИ БАЛЛЫ\n\n"
        f"👤 {client[3]}\n"
        f"📞 {client[2]}\n\n"
        f"⭐ Баллы: {client[4]:,}\n"
        f"🏆 Визитов: {client[5]}\n"
        f"🎁 Доступная скидка: {discount:,} сум\n\n"
        f"💡 1000 баллов = 10,000 сум скидки"
    )

# ============================================
# МОЙ QR-КОД
# ============================================
@dp.message(F.text == "📱 Мой QR-код")
async def my_qr_code(message: Message):
    client = await get_client_by_telegram_id(message.from_user.id)
    if not client:
        await message.answer("❌ Вы не зарегистрированы! Напишите /start")
        return

    # Генерируем QR с данными клиента
    qr_data = f"QAYTAR:{client[2]}"  # QAYTAR:+998901234567
    qr_bytes = generate_qr(qr_data)

    await message.answer_photo(
        photo=BufferedInputFile(qr_bytes, filename="qr.png"),
        caption=(
            f"📱 ВАШ QR-КОД\n\n"
            f"👤 {client[3]}\n"
            f"⭐ Баллы: {client[4]:,}\n\n"
            f"Покажите этот QR-код официанту при оплате!"
        )
    )

# ============================================
# НАЧИСЛИТЬ БАЛЛЫ (для ресторана)
# ============================================
@dp.message(F.text == "➕ Начислить баллы")
async def add_points_start(message: Message, state: FSMContext):
    if not await is_restaurant(message.from_user.id):
        await message.answer("❌ Эта функция только для ресторанов!")
        return

    await message.answer("📞 Введи номер телефона клиента или отсканируй QR:\n+998901234567")
    await state.set_state(AddPointsStates.waiting_for_phone)

@dp.message(AddPointsStates.waiting_for_phone)
async def add_points_get_phone(message: Message, state: FSMContext):
    text = message.text.strip()

    # Если отсканировали QR — формат QAYTAR:+998901234567
    if text.startswith("QAYTAR:"):
        phone = text.replace("QAYTAR:", "")
    else:
        phone = text

    client = await get_client_by_phone(phone)
    if not client:
        await message.answer("❌ Клиент не найден! Проверь номер.")
        await state.clear()
        return

    await state.update_data(phone=phone, client_name=client[3], current_points=client[4])
    await message.answer(
        f"✅ Клиент найден!\n"
        f"👤 {client[3]}\n"
        f"⭐ Текущие баллы: {client[4]:,}\n\n"
        f"Введи сумму чека (в сумах):"
    )
    await state.set_state(AddPointsStates.waiting_for_amount)

@dp.message(AddPointsStates.waiting_for_amount)
async def add_points_get_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("❌ Введи только цифры! Например: 150000")
        return

    # 1% от суммы чека = баллы
    new_points = amount // 100
    data = await state.get_data()
    phone = data["phone"]
    current_points = data["current_points"]
    client_name = data["client_name"]

    async with aiosqlite.connect("qaytar.db") as db:
        # Начисляем баллы
        await db.execute(
            "UPDATE clients SET points = points + ?, total_visits = total_visits + 1 WHERE phone = ?",
            (new_points, phone)
        )
        # Записываем транзакцию
        restaurant = await db.execute(
            "SELECT id FROM restaurants WHERE telegram_id = ?", (message.from_user.id,)
        )
        rest = await restaurant.fetchone()
        await db.execute(
            "INSERT INTO transactions (client_phone, restaurant_id, amount, points_added) VALUES (?, ?, ?, ?)",
            (phone, rest[0] if rest else 0, amount, new_points)
        )
        # Обновляем продажи ресторана
        await db.execute(
            "UPDATE restaurants SET total_sales = total_sales + ? WHERE telegram_id = ?",
            (amount, message.from_user.id)
        )
        await db.commit()

    total_points = current_points + new_points

    await message.answer(
        f"✅ БАЛЛЫ НАЧИСЛЕНЫ!\n\n"
        f"👤 {client_name}\n"
        f"🧾 Сумма чека: {amount:,} сум\n"
        f"➕ Начислено: +{new_points} баллов\n"
        f"⭐ Всего баллов: {total_points:,}"
    )

    # Уведомляем клиента
    client = await get_client_by_phone(phone)
    if client and client[1]:
        try:
            await bot.send_message(
                client[1],
                f"🎉 Вам начислено {new_points} баллов!\n"
                f"⭐ Всего: {total_points:,} баллов\n"
                f"🎁 Продолжайте копить!"
            )
        except:
            pass

    await state.clear()

# ============================================
# СПИСАТЬ БАЛЛЫ (скидка)
# ============================================
@dp.message(F.text == "➖ Списать баллы")
async def redeem_start(message: Message, state: FSMContext):
    if not await is_restaurant(message.from_user.id):
        await message.answer("❌ Эта функция только для ресторанов!")
        return

    await message.answer("📞 Введи номер телефона клиента:")
    await state.set_state(RedeemStates.waiting_for_phone)

@dp.message(RedeemStates.waiting_for_phone)
async def redeem_get_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if phone.startswith("QAYTAR:"):
        phone = phone.replace("QAYTAR:", "")

    client = await get_client_by_phone(phone)
    if not client:
        await message.answer("❌ Клиент не найден!")
        await state.clear()
        return

    if client[4] < 1000:
        await message.answer(
            f"❌ Недостаточно баллов!\n"
            f"👤 {client[3]}\n"
            f"⭐ Баллы: {client[4]:,}\n"
            f"💡 Минимум 1000 баллов для скидки"
        )
        await state.clear()
        return

    discount = (client[4] // 1000) * 10000
    await state.update_data(phone=phone, client_name=client[3], current_points=client[4])
    await message.answer(
        f"✅ Клиент: {client[3]}\n"
        f"⭐ Баллы: {client[4]:,}\n"
        f"🎁 Максимальная скидка: {discount:,} сум\n\n"
        f"Сколько баллов списать? (кратно 1000)"
    )
    await state.set_state(RedeemStates.waiting_for_points)

@dp.message(RedeemStates.waiting_for_points)
async def redeem_get_points(message: Message, state: FSMContext):
    try:
        points_to_redeem = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи только цифры!")
        return

    data = await state.get_data()
    phone = data["phone"]
    current_points = data["current_points"]
    client_name = data["client_name"]

    if points_to_redeem > current_points:
        await message.answer(f"❌ Недостаточно баллов! У клиента: {current_points:,}")
        return

    if points_to_redeem % 1000 != 0:
        await message.answer("❌ Количество должно быть кратно 1000!")
        return

    discount = (points_to_redeem // 1000) * 10000

    async with aiosqlite.connect("qaytar.db") as db:
        await db.execute(
            "UPDATE clients SET points = points - ? WHERE phone = ?",
            (points_to_redeem, phone)
        )
        await db.commit()

    await message.answer(
        f"✅ СКИДКА ПРИМЕНЕНА!\n\n"
        f"👤 {client_name}\n"
        f"➖ Списано: {points_to_redeem:,} баллов\n"
        f"💰 Скидка: {discount:,} сум\n"
        f"⭐ Остаток: {current_points - points_to_redeem:,} баллов"
    )

    client = await get_client_by_phone(phone)
    if client and client[1]:
        try:
            await bot.send_message(
                client[1],
                f"🎁 Вы использовали скидку!\n"
                f"➖ Списано: {points_to_redeem:,} баллов\n"
                f"💰 Скидка: {discount:,} сум\n"
                f"⭐ Остаток: {current_points - points_to_redeem:,} баллов"
            )
        except:
            pass

    await state.clear()

# ============================================
# СТАТИСТИКА (для ресторана)
# ============================================
@dp.message(F.text == "📊 Статистика")
async def show_statistics(message: Message):
    user_id = message.from_user.id

    async with aiosqlite.connect("qaytar.db") as db:
        # Данные ресторана
        cursor = await db.execute("SELECT * FROM restaurants WHERE telegram_id = ?", (user_id,))
        restaurant = await cursor.fetchone()

        if not restaurant:
            await message.answer("❌ Ресторан не найден!")
            return

        # Клиенты этого месяца
        cursor = await db.execute("""
            SELECT COUNT(DISTINCT client_phone) FROM transactions
            WHERE restaurant_id = ?
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """, (restaurant[0],))
        monthly_clients = (await cursor.fetchone())[0]

        # Продажи этого месяца
        cursor = await db.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions
            WHERE restaurant_id = ?
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """, (restaurant[0],))
        monthly_sales = (await cursor.fetchone())[0]

        # Всего клиентов
        cursor = await db.execute("""
            SELECT COUNT(DISTINCT client_phone) FROM transactions WHERE restaurant_id = ?
        """, (restaurant[0],))
        total_clients = (await cursor.fetchone())[0]

    # Комиссия Qaytar за месяц
    commission = int(monthly_sales * 0.005)

    await message.answer(
        f"📊 СТАТИСТИКА — {restaurant[1]}\n\n"
        f"📅 Этот месяц:\n"
        f"👥 Клиентов: {monthly_clients}\n"
        f"💵 Продажи: {monthly_sales:,} сум\n"
        f"💰 Комиссия Qaytar (0.5%): {commission:,} сум\n\n"
        f"📈 За всё время:\n"
        f"👥 Всего клиентов: {total_clients}\n"
        f"💵 Всего продаж: {restaurant[4]:,} сум"
    )

# ============================================
# НАЙТИ КЛИЕНТА
# ============================================
@dp.message(F.text == "🔍 Найти клиента")
async def find_client(message: Message):
    await message.answer("📞 Введи номер телефона клиента:")

# ============================================
# ADMIN — ДОБАВИТЬ РЕСТОРАН
# ============================================
@dp.message(F.text == "🏪 Добавить ресторан")
async def add_restaurant_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("Введи название ресторана:")
    await state.set_state(AddRestaurantStates.waiting_for_name)

@dp.message(AddRestaurantStates.waiting_for_name)
async def add_restaurant_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Введи Telegram ID владельца ресторана\n(узнать у @userinfobot):")
    await state.set_state(AddRestaurantStates.waiting_for_telegram_id)

@dp.message(AddRestaurantStates.waiting_for_telegram_id)
async def add_restaurant_id(message: Message, state: FSMContext):
    try:
        telegram_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи только цифры!")
        return

    data = await state.get_data()
    name = data["name"]

    async with aiosqlite.connect("qaytar.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO restaurants (name, telegram_id) VALUES (?, ?)",
            (name, telegram_id)
        )
        await db.commit()

    await message.answer(f"✅ Ресторан '{name}' добавлен!")

    try:
        await bot.send_message(
            telegram_id,
            f"🎉 Ресторан '{name}' подключён к Qaytar!\n"
            f"Напишите /start чтобы начать работу."
        )
    except:
        pass

    await state.clear()

# ============================================
# ADMIN — ВСЕ РЕСТОРАНЫ
# ============================================
@dp.message(F.text == "📊 Все рестораны")
async def all_restaurants(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect("qaytar.db") as db:
        cursor = await db.execute("SELECT name, total_sales FROM restaurants")
        restaurants = await cursor.fetchall()

    if not restaurants:
        await message.answer("Ресторанов пока нет!")
        return

    text = "🏪 ВСЕ РЕСТОРАНЫ\n\n"
    total_commission = 0
    for i, r in enumerate(restaurants, 1):
        commission = int(r[1] * 0.005)
        total_commission += commission
        text += f"{i}. {r[0]}\n   💵 Продажи: {r[1]:,} сум\n   💰 Комиссия: {commission:,} сум\n\n"

    text += f"💰 ИТОГО КОМИССИЯ: {total_commission:,} сум"
    await message.answer(text)

# ============================================
# ADMIN — ВСЕ КЛИЕНТЫ
# ============================================
@dp.message(F.text == "👥 Все клиенты")
async def all_clients(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect("qaytar.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM clients")
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM clients WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
        )
        monthly = (await cursor.fetchone())[0]

    await message.answer(
        f"👥 КЛИЕНТЫ\n\n"
        f"📅 Новых в этом месяце: {monthly}\n"
        f"📈 Всего клиентов: {total}"
    )

# ============================================
# ADMIN — ДОХОДЫ
# ============================================
@dp.message(F.text == "💰 Доходы")
async def show_income(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect("qaytar.db") as db:
        # Доход за этот месяц
        cursor = await db.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """)
        monthly_sales = (await cursor.fetchone())[0]

        # Доход за всё время
        cursor = await db.execute("SELECT COALESCE(SUM(total_sales), 0) FROM restaurants")
        total_sales = (await cursor.fetchone())[0]

    monthly_income = int(monthly_sales * 0.005)
    total_income = int(total_sales * 0.005)

    await message.answer(
        f"💰 ДОХОДЫ QAYTAR\n\n"
        f"📅 Этот месяц:\n"
        f"   Оборот: {monthly_sales:,} сум\n"
        f"   Доход (0.5%): {monthly_income:,} сум\n"
        f"   В долларах: ~${monthly_income // 12700}\n\n"
        f"📈 За всё время:\n"
        f"   Оборот: {total_sales:,} сум\n"
        f"   Доход (0.5%): {total_income:,} сум\n"
        f"   В долларах: ~${total_income // 12700}"
    )

# ============================================
# ЗАПУСК
# ============================================
async def main():
    await create_database()
    print("🚀 Qaytar Bot запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

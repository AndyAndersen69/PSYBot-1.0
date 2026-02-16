"""
Telegram-бот для психолога с автоворонкой
Полная версия с базой данных, экспортом в Excel и автоворонкой
"""

import os
import asyncio
import logging
import sqlite3
import pandas as pd
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BufferedInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    logger.error("❌ ОШИБКА: BOT_TOKEN не найден в переменных окружения!")
    logger.error(
        "Добавьте BOT_TOKEN в Environment Variables Replit (иконка 🔒 слева)")
    exit(1)

if not ADMIN_ID:
    logger.warning(
        "⚠️  ADMIN_ID не указан. Уведомления админу отправляться не будут.")
    ADMIN_ID = 0
else:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        logger.error("❌ ОШИБКА: ADMIN_ID должен быть числом!")
        ADMIN_ID = 0

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
bot = Bot(token=BOT_TOKEN,
          default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


# ========== СОСТОЯНИЯ FSM (Finite State Machine) ==========
class Form(StatesGroup):
    """Состояния для сбора данных пользователя"""
    name = State()  # Ожидание имени
    age = State()  # Ожидание возраста
    custom_problem = State()  # Ожидание своей проблемы (НОВОЕ)
    phone = State()  # Ожидание телефона


# ========== КОНСТАНТЫ ДЛЯ CALLBACK-ДАННЫХ ==========
class CallbackData:
    """Константы для callback-данных кнопок"""
    ANXIETY = "btn_anxiety"
    RELATIONS = "btn_relations"
    SELF = "btn_self"
    CUSTOM = "btn_custom"  # НОВАЯ КНОПКА
    SIGNUP = "btn_signup"


PROBLEM_NAMES = {
    CallbackData.ANXIETY: "Тревога/Стресс",
    CallbackData.RELATIONS: "Отношения",
    CallbackData.SELF: "Выгорание/Самооценка",
    CallbackData.CUSTOM: "Своя проблема"  # НОВОЕ
}


# ========== ФУНКЦИИ РАБОТЫ С БАЗОЙ ДАННЫХ ==========
def update_database_schema():
    """Обновление структуры базы данных при необходимости"""
    try:
        conn = sqlite3.connect("/data/psychology_bot.db")
        cursor = conn.cursor()

        # Получаем список всех колонок в таблице users
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        # Добавляем недостающие колонки
        if 'custom_problem' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN custom_problem TEXT")
            logger.info("✅ Добавлена колонка 'custom_problem'")

        if 'age' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN age INTEGER")
            logger.info("✅ Добавлена колонка 'age'")

        if 'real_name' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN real_name TEXT")
            logger.info("✅ Добавлена колонка 'real_name'")

        conn.commit()
        conn.close()
        logger.info("✅ Структура базы данных обновлена")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления структуры БД: {e}")
        return False


def init_database():
    """Инициализация базы данных SQLite"""
    try:
        # Сначала удалим старую базу, чтобы создать новую с правильной структурой
        if os.path.exists("/data/psychology_bot.db"):
            logger.warning("⚠️  Удаляю старую базу данных для пересоздания...")
            os.remove("/data/psychology_bot.db")
            logger.info("✅ Старая база данных удалена")

        conn = sqlite3.connect("/data/psychology_bot.db")
        cursor = conn.cursor()

        # Создание таблицы пользователей с ВСЕМИ нужными колонками (без комментариев!)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT NOT NULL,
            problem_segment TEXT,
            custom_problem TEXT,
            real_name TEXT,
            age INTEGER,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()
        conn.close()
        logger.info("✅ База данных успешно создана с новой структурой")

        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        return False


def user_exists(user_id: int) -> bool:
    """Проверка существования пользователя в базе"""
    try:
        conn = sqlite3.connect("/data/psychology_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id, ))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception as e:
        logger.error(f"Ошибка проверки пользователя: {e}")
        return False


def add_user(user_id: int, username: str, full_name: str):
    """Добавление нового пользователя в базу"""
    try:
        conn = sqlite3.connect("/data/psychology_bot.db")
        cursor = conn.cursor()

        cursor.execute(
            """INSERT OR IGNORE INTO users (user_id, username, full_name) 
               VALUES (?, ?, ?)""", (user_id, username, full_name))

        conn.commit()
        conn.close()
        logger.info(f"👤 Добавлен пользователь: {user_id} ({full_name})")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления пользователя: {e}")
        return False


def update_user_problem(user_id: int,
                        problem_segment: str,
                        custom_problem: str = None):
    """Обновление выбранной проблемы пользователя"""
    try:
        conn = sqlite3.connect("/data/psychology_bot.db")
        cursor = conn.cursor()

        if custom_problem and problem_segment == CallbackData.CUSTOM:
            cursor.execute(
                "UPDATE users SET problem_segment = ?, custom_problem = ? WHERE user_id = ?",
                (problem_segment, custom_problem, user_id))
            logger.info(
                f"🎯 Пользователь {user_id} описал свою проблему: {custom_problem[:50]}..."
            )
        else:
            cursor.execute(
                "UPDATE users SET problem_segment = ? WHERE user_id = ?",
                (problem_segment, user_id))
            logger.info(
                f"🎯 Пользователь {user_id} выбрал проблему: {problem_segment}")

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления проблемы: {e}")
        return False


def update_user_contact_info(user_id: int, real_name: str, age: int,
                             phone: str):
    """Обновление контактной информации пользователя"""
    try:
        conn = sqlite3.connect("/data/psychology_bot.db")
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE users SET real_name = ?, age = ?, phone = ? WHERE user_id = ?",
            (real_name, age, phone, user_id))

        conn.commit()
        conn.close()
        logger.info(
            f"📝 Обновлены данные пользователя {user_id}: {real_name}, {age} лет, {phone}"
        )
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления данных: {e}")
        return False


def get_user_stats():
    """Получение статистики по пользователям"""
    try:
        conn = sqlite3.connect("/data/psychology_bot.db")
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE real_name IS NOT NULL AND phone IS NOT NULL"
        )
        users_with_requests = cursor.fetchone()[0]

        cursor.execute("""
            SELECT problem_segment, COUNT(*) 
            FROM users 
            WHERE problem_segment IS NOT NULL 
            GROUP BY problem_segment 
            ORDER BY COUNT(*) DESC
        """)
        problems_distribution = cursor.fetchall()

        cursor.execute("""
            SELECT real_name, age, phone, problem_segment, custom_problem, created_at 
            FROM users 
            WHERE real_name IS NOT NULL 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        recent_requests = cursor.fetchall()

        conn.close()

        stats = {
            "total_users": total_users,
            "users_with_requests": users_with_requests,
            "problems_distribution": problems_distribution,
            "recent_requests": recent_requests
        }

        return stats
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return None


def export_users_to_excel():
    """Экспорт всех пользователей в Excel файл"""
    try:
        conn = sqlite3.connect("/data/psychology_bot.db")

        df = pd.read_sql_query("SELECT * FROM users ORDER BY created_at DESC",
                               conn)

        conn.close()

        if df.empty:
            return None, "База данных пуста"

        if 'created_at' in df.columns:
            df['created_at'] = pd.to_datetime(
                df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"clients_database_{timestamp}.xlsx"

        df.to_excel(filename, index=False, engine='openpyxl')

        logger.info(f"📊 Экспортировано {len(df)} записей в файл {filename}")
        return filename, None
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта в Excel: {e}")
        return None, str(e)


# ========== ФУНКЦИИ ДЛЯ СОЗДАНИЯ КЛАВИАТУР ==========
def create_main_keyboard():
    """Создание основной reply-клавиатуры"""
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="🎁 Получить бесплатный гайд")],
        [types.KeyboardButton(text="📞 Записаться на консультацию")],
        [types.KeyboardButton(text="ℹ️  О психологе")],
    ],
                                   resize_keyboard=True,
                                   one_time_keyboard=False)
    return keyboard


def create_problems_keyboard():
    """Создание inline-клавиатуры для выбора проблемы с кнопкой 'Своя проблема'"""
    builder = InlineKeyboardBuilder()

    buttons = [
        ("😰 Тревога и стресс", CallbackData.ANXIETY),
        ("💑 Отношения и семья", CallbackData.RELATIONS),
        ("😔 Выгорание и самооценка", CallbackData.SELF),
        ("✏️ Написать свою проблему", CallbackData.CUSTOM),  # НОВАЯ КНОПКА
    ]

    for text, callback_data in buttons:
        builder.add(
            InlineKeyboardButton(text=text, callback_data=callback_data))

    builder.adjust(1)
    return builder.as_markup()


def create_signup_keyboard():
    """Создание inline-клавиатуры для записи"""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="✍️ Записаться на бесплатную консультацию",
                             callback_data=CallbackData.SIGNUP))
    return builder.as_markup()


# ========== ОБРАБОТЧИКИ КОМАНД ==========
@router.message(Command("start"))
async def command_start(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or "не указан"
    full_name = message.from_user.full_name

    logger.info(f"🚀 Пользователь {user_id} ({full_name}) запустил бота")

    # Удаляем старую базу если есть проблемы
    if not os.path.exists("/data/psychology_bot.db"):
        init_database()
    else:
        # Проверяем структуру базы
        try:
            conn = sqlite3.connect("/data/psychology_bot.db")
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            conn.close()

            required_columns = ['custom_problem', 'age', 'real_name']
            missing_columns = [
                col for col in required_columns if col not in columns
            ]

            if missing_columns:
                logger.warning(
                    f"⚠️  В базе отсутствуют колонки: {missing_columns}")
                logger.warning("Удаляю старую базу для пересоздания...")
                os.remove("/data/psychology_bot.db")
                init_database()
        except:
            # Если ошибка при проверке, пересоздаем базу
            if os.path.exists("/data/psychology_bot.db"):
                os.remove("/data/psychology_bot.db")
            init_database()

    if not user_exists(user_id):
        add_user(user_id, username, full_name)

    welcome_text = ("👋 <b>Здравствуйте, {name}!</b>\n\n"
                    "Я — цифровой помощник профессионального психолога.\n\n"
                    "🎯 <b>Я помогу вам:</b>\n"
                    "• Получить бесплатный гайд по работе с тревогой\n"
                    "• Определить вашу основную проблема\n"
                    "• Записаться на бесплатную 15-минутную консультацию\n\n"
                    "👉 <b>Выберите действие ниже:</b>").format(
                        name=full_name.split()[0] if full_name else "друг")

    keyboard = create_main_keyboard()

    try:
        if os.path.exists("welcome.jpg"):
            photo = FSInputFile("welcome.jpg")
            await message.answer_photo(photo=photo,
                                       caption=welcome_text,
                                       reply_markup=keyboard)
        else:
            await message.answer(welcome_text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        await message.answer(welcome_text, reply_markup=keyboard)


@router.message(F.text == "🎁 Получить бесплатный гайд")
async def handle_get_guide(message: types.Message):
    """Обработчик получения лид-магнита"""
    user_id = message.from_user.id
    logger.info(f"📥 Пользователь {user_id} запросил гайд")

    try:
        if os.path.exists("guide.pdf"):
            pdf_file = FSInputFile("guide.pdf")
            await message.answer_document(
                document=pdf_file,
                caption=
                ("✅ <b>Ваш бесплатный гайд готов!</b>\n\n"
                 "📖 <i>«Как справиться с тревогой: 5 практических шагов»</i>\n\n"
                 "Скачайте и откройте файл. Пока вы знакомитесь с материалом, "
                 "ответьте на один важный вопрос:"))
        else:
            pdf_content = (
                "Бесплатный гайд: Как справиться с тревогой\n\n"
                "1. Практика глубокого дыхания\n2. Ведение дневника мыслей\n"
                "3. Регулярная физическая активность\n4. Техники осознанности\n"
                "5. Поиск профессиональной помощи\n\n"
                "Это демонстрационный файл.").encode('utf-8')

            pdf_file = BufferedInputFile(pdf_content, filename="guide.pdf")
            await message.answer_document(
                document=pdf_file,
                caption="✅ <b>Ваш бесплатный гайд готов!</b>")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки PDF: {e}")
        await message.answer(
            "✅ <b>Ваш бесплатный гайд готов!</b>\n\n"
            "📖 <i>«Как справиться с тревогой: 5 практических шагов»</i>")

    await message.answer(
        "📝 <b>Пока вы открываете гайд, ответьте на один вопрос:</b>\n\n"
        "<i>Что вас беспокоит сейчас сильнее всего?</i>\n\n"
        "Вы можете выбрать из предложенных вариантов или написать свою проблему.",
        reply_markup=ReplyKeyboardRemove())

    keyboard = create_problems_keyboard()
    await message.answer("Выберите наиболее подходящий вариант:",
                         reply_markup=keyboard)


@router.message(F.text == "📞 Записаться на консультацию")
async def handle_direct_signup(message: types.Message):
    """Прямой переход к записи"""
    await message.answer(
        "📋 <b>Отлично! Вы хотите записаться на консультацию.</b>\n\n"
        "Для начала расскажите, что вас беспокоит?\n\n"
        "<i>Выберите из вариантов или опишите свою ситуацию:</i>",
        reply_markup=ReplyKeyboardRemove())

    keyboard = create_problems_keyboard()
    await message.answer("Выберите вариант:", reply_markup=keyboard)


@router.message(F.text == "ℹ️  О психологе")
async def handle_about(message: types.Message):
    """Информация о психологе"""
    about_text = (
        "👨‍⚕️ <b>О психологе:</b>\n\n"
        "👋 Привет, меня зовут Ярослава!\n"
        "• Опыт работы: 3 года\n"
        "• Специализация: Интегративный подход\n"
        "• Работа с: тревогой, депрессией, отношениями, самооценкой\n"
        "• Образование: консультативная психология\n\n"
        "💼 <b>Подход:</b>\n"
        "Индивидуальный подход к каждому клиенту, доказательные методы.\n\n"
        "📞 <b>Связь:</b>\n"
        "Консультации проходят в Telegram для вашего удобства.\n\n"
        "Чтобы начать работу, нажмите «🎁 Получить бесплатный гайд».")

    await message.answer(about_text)


# ========== ОБРАБОТКА ВЫБОРА ПРОБЛЕМЫ ==========
@router.callback_query(
    F.data.in_(
        [CallbackData.ANXIETY, CallbackData.RELATIONS, CallbackData.SELF]))
async def handle_problem_selection(callback: types.CallbackQuery):
    """Обработка выбора стандартной проблемы"""
    user_id = callback.from_user.id
    problem_key = callback.data
    problem_name = PROBLEM_NAMES.get(problem_key, "Неизвестная проблема")

    update_user_problem(user_id, problem_name)

    responses = {
        CallbackData.ANXIETY:
        ("😰 <b>Тревога и стресс</b> — это действительно сложно.\n\n"
         "Я много работаю с тревожными состояниями и знаю, "
         "как важно вовремя получить поддержку."),
        CallbackData.RELATIONS:
        ("💑 <b>Отношения и семья</b> — это основа нашей жизни.\n\n"
         "Сложности в отношениях знакомы многим."),
        CallbackData.SELF:
        ("😔 <b>Выгорание и самооценка</b> — важные темы.\n\n"
         "Я помогу вам восстановить ресурсы."),
    }

    response_text = responses.get(problem_key, "")

    await callback.message.edit_text(
        f"{response_text}\n\n"
        f"<b>Хотите записаться на бесплатную 15-минутную диагностику?</b>\n\n"
        f"На консультации мы:\n"
        f"• Определим вашу текущую ситуацию\n"
        f"• Наметим возможные пути решения")

    keyboard = create_signup_keyboard()
    await callback.message.answer(
        "Нажмите кнопку ниже, чтобы оставить заявку:", reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == CallbackData.CUSTOM)
async def handle_custom_problem_start(callback: types.CallbackQuery,
                                      state: FSMContext):
    """Начало ввода своей проблемы"""
    await callback.message.answer(
        "📝 <b>Расскажите о своей проблеме</b>\n\n"
        "Опишите, что вас беспокоит, в свободной форме:\n\n"
        "<i>Примеры:\n"
        "• 'Чувствую постоянную усталость и нет интереса к жизни'\n"
        "• 'Сложности на работе, конфликты с коллегами'\n"
        "• 'Не могу найти общий язык с подростком-сыном'</i>",
        reply_markup=ReplyKeyboardRemove())

    # Устанавливаем состояние ожидания описания проблемы
    await state.set_state(Form.custom_problem)
    await callback.answer()


@router.message(Form.custom_problem)
async def handle_custom_problem_input(message: types.Message,
                                      state: FSMContext):
    """Обработка ввода своей проблемы"""
    custom_problem = message.text.strip()

    if len(custom_problem) < 10:
        await message.answer(
            "⚠️ <b>Пожалуйста, опишите проблему подробнее (минимум 10 символов).</b>\n\n"
            "Расскажите, что именно вас беспокоит:")
        return

    user_id = message.from_user.id

    # Сохраняем свою проблему в базе
    update_user_problem(user_id, CallbackData.CUSTOM, custom_problem)

    await message.answer(
        "✅ <b>Спасибо за откровенность!</b>\n\n"
        f"<i>Ваша проблема: «{custom_problem[:100]}...»</i>\n\n"
        "<b>Хотите записаться на бесплатную 15-минутную консультацию?</b>\n\n"
        "Я специализируюсь на разных вопросах и помогу разобраться в вашей ситуации."
    )

    keyboard = create_signup_keyboard()
    await message.answer("Нажмите кнопку ниже, чтобы оставить заявку:",
                         reply_markup=keyboard)

    # Сбрасываем состояние
    await state.clear()


@router.callback_query(F.data == CallbackData.SIGNUP)
async def handle_signup_start(callback: types.CallbackQuery,
                              state: FSMContext):
    """Начало процесса сбора данных для записи"""
    await callback.message.answer(
        "📋 <b>Отлично! Для записи мне понадобятся некоторые данные.</b>\n\n"
        "<i>Это займет всего пару минут.</i>\n\n"
        "🔹 <b>Как к вам обращаться?</b>\n"
        "(Введите ваше имя):")

    await state.set_state(Form.name)
    await callback.answer()


# ========== СБОР КОНТАКТНЫХ ДАННЫХ ==========
@router.message(Form.name)
async def handle_name_input(message: types.Message, state: FSMContext):
    """Обработка ввода имени"""
    name = message.text.strip()

    if len(name) < 2:
        await message.answer(
            "⚠️ <b>Имя должно содержать хотя бы 2 символа.</b>\n\n"
            "Пожалуйста, введите ваше имя еще раз:")
        return

    await state.update_data(name=name)

    await message.answer(
        f"👋 <b>Приятно познакомиться, {name}!</b>\n\n"
        "🔹 <b>Сколько вам лет?</b>\n"
        "(Введите ваш возраст цифрами, например: 25)\n\n"
        "<i>Возраст помогает подобрать наиболее подходящий подход.</i>")

    await state.set_state(Form.age)


@router.message(Form.age)
async def handle_age_input(message: types.Message, state: FSMContext):
    """Обработка ввода возраста"""
    age_text = message.text.strip()

    try:
        age = int(age_text)
        if age < 10 or age > 100:
            await message.answer(
                "⚠️ <b>Пожалуйста, введите корректный возраст (от 10 до 100 лет).</b>\n\n"
                "Введите ваш возраст еще раз:")
            return
    except ValueError:
        await message.answer(
            "⚠️ <b>Пожалуйста, введите возраст цифрами.</b>\n\n"
            "Пример: 25\n\n"
            "Введите ваш возраст еще раз:")
        return

    await state.update_data(age=age)

    await message.answer(
        f"✅ <b>Отлично! {age} лет.</b>\n\n"
        "🔹 <b>Теперь напишите ваш username в Telegram для связи:</b>\n"
        "(например: @username или просто username)\n\n"
        "<i>Username нужен для подтверждения записи и связи в Telegram.</i>")

    await state.set_state(Form.phone)


@router.message(Form.phone)
async def handle_phone_input(message: types.Message, state: FSMContext):
    """Обработка ввода телеграм username"""
    user_id = message.from_user.id
    telegram_username = message.text.strip()

    # Простая валидация телеграм username
    if len(telegram_username) < 3:
        await message.answer(
            "⚠️ <b>Пожалуйста, введите корректный username Telegram.</b>\n\n"
            "Пример: @username или просто username\n\n"
            "Введите username еще раз:")
        return

    # Убираем @ если есть
    if telegram_username.startswith('@'):
        telegram_username = telegram_username[1:]

    # Получаем все данные из состояния
    data = await state.get_data()
    name = data.get("name", "Не указано")
    age = data.get("age", 0)

    # Получаем информацию о проблеме из базы данных
    try:
        conn = sqlite3.connect("/data/psychology_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT problem_segment, custom_problem FROM users WHERE user_id = ?",
            (user_id, ))
        user_data = cursor.fetchone()
        conn.close()

        if user_data:
            problem_segment = user_data[0] if user_data[0] else "не указана"
            custom_problem = user_data[1]

            # Формируем полное описание проблемы
            if problem_segment == CallbackData.CUSTOM and custom_problem:
                problem_display = f"Своя проблема: {custom_problem[:100]}..."
            elif problem_segment in PROBLEM_NAMES:
                problem_display = PROBLEM_NAMES.get(problem_segment)
            else:
                problem_display = problem_segment
        else:
            problem_display = "не указана"
    except Exception as e:
        logger.error(f"❌ Ошибка получения данных о проблеме: {e}")
        problem_display = "не удалось определить"

    # Сохраняем данные в базе (username сохраняем в поле phone)
    update_user_contact_info(user_id, name, age, telegram_username)

    await message.answer(
        "🎉 <b>Спасибо! Заявка успешно принята!</b>\n\n"
        "✅ <i>Я свяжусь с вами в Telegram в ближайшее время для уточнения деталей "
        "и согласования времени консультации.</i>\n\n"
        "📅 <b>Что дальше?</b>\n"
        "1. В течение 24 часов вы получите сообщение в Telegram\n"
        "2. Мы согласуем удобное время для 15-минутной консультации\n"
        "3. Проведем бесплатную диагностику вашей ситуации\n\n"
        "💬 <b>Ожидайте сообщения в Telegram от @yrvrs!</b>\n\n"
        "Если у вас есть срочный вопрос, напишите мне в Telegram: @yrvrs",
        reply_markup=ReplyKeyboardRemove())

    # Уведомление администратору
    if ADMIN_ID:
        try:
            # Если problem_display не определен, используем fallback
            if 'problem_display' not in locals():
                problem_display = "не указана"

            admin_message = (
                "🔔 <b>НОВАЯ ЗАЯВКА НА КОНСУЛЬТАЦИЮ!</b>\n\n"
                f"👤 <b>Имя:</b> {name}\n"
                f"🎂 <b>Возраст:</b> {age} лет\n"
                f"🎯 <b>Проблема:</b> {problem_display}\n"
                f"📱 <b>Telegram:</b> @{telegram_username}\n"
                f"🆔 <b>User ID:</b> {user_id}\n\n"
                f"⏰ <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await bot.send_message(chat_id=ADMIN_ID, text=admin_message)
            logger.info(f"📨 Уведомление отправлено администратору {ADMIN_ID}")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление админу: {e}")

    logger.info(
        f"✅ Заявка сохранена: {user_id} - {name}, {age} лет, @{telegram_username}"
    )

    # Сбрасываем состояние
    await state.clear()


# ========== АДМИНИСТРАТИВНЫЕ КОМАНДЫ ==========
@router.message(Command("export"))
async def command_export(message: types.Message):
    """Экспорт базы данных в Excel"""
    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        await message.answer(
            "⛔ <b>У вас нет прав для выполнения этой команды.</b>")
        return

    await message.answer("📊 <b>Начинаю экспорт базы данных...</b>\n\n"
                         "<i>Это может занять несколько секунд.</i>")

    filename, error = export_users_to_excel()

    if error:
        await message.answer(
            f"❌ <b>Ошибка при экспорте:</b>\n\n<code>{error}</code>")
        return

    if not filename:
        await message.answer("📭 <b>База данных пуста.</b>\n\n"
                             "Нет данных для экспорта.")
        return

    try:
        excel_file = FSInputFile(filename)
        stats = get_user_stats()

        caption = (
            f"📁 <b>База данных клиентов</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"• Всего пользователей: {stats['total_users'] if stats else 0}\n"
            f"• Заявок оставлено: {stats['users_with_requests'] if stats else 0}\n\n"
            f"⏰ <b>Экспорт выполнен:</b>\n"
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await message.answer_document(document=excel_file, caption=caption)

        os.remove(filename)
        logger.info(f"🗑️ Файл {filename} удален")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки файла: {e}")
        await message.answer(
            f"❌ <b>Ошибка отправки файла:</b>\n\n<code>{str(e)}</code>")


@router.message(Command("stats"))
async def command_stats(message: types.Message):
    """Показать статистику бота"""
    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        await message.answer(
            "⛔ <b>У вас нет прав для выполнения этой команды.</b>")
        return

    stats = get_user_stats()

    if not stats:
        await message.answer("❌ <b>Не удалось получить статистику.</b>")
        return

    stats_text = (
        "📈 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Всего пользователей:</b> {stats['total_users']}\n"
        f"📝 <b>Заявок оставлено:</b> {stats['users_with_requests']}\n"
        f"📊 <b>Конверсия:</b> {round(stats['users_with_requests'] / stats['total_users'] * 100, 1) if stats['total_users'] > 0 else 0}%\n\n"
    )

    if stats['problems_distribution']:
        stats_text += "<b>Распределение по проблемам:</b>\n"
        for problem, count in stats['problems_distribution']:
            percentage = round(count / stats['total_users'] *
                               100, 1) if stats['total_users'] > 0 else 0
            problem_name = PROBLEM_NAMES.get(problem, problem)
            stats_text += f"• {problem_name}: {count} ({percentage}%)\n"

    if stats['recent_requests']:
        stats_text += "\n<b>Последние заявки:</b>\n"
        for name, age, telegram, problem, custom_problem, created_at in stats[
                'recent_requests'][:5]:
            if problem == CallbackData.CUSTOM and custom_problem:
                problem_display = f"Своя: {custom_problem[:30]}..."
            else:
                problem_display = PROBLEM_NAMES.get(problem, problem)
            stats_text += f"• {name} ({age} лет) - @{telegram} - {problem_display}\n"

    stats_text += f"\n⏰ <i>Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

    await message.answer(stats_text)


@router.message(Command("help"))
async def command_help(message: types.Message):
    """Показать справку"""
    help_text = (
        "📚 <b>СПРАВКА ПО КОМАНДАМ</b>\n\n"
        "🎯 <b>Для всех пользователей:</b>\n"
        "• /start - Начать работу с ботом\n"
        "• /help - Показать эту справку\n\n"
        "🎯 <b>Основные действия (через меню):</b>\n"
        "• 🎁 Получить бесплатный гайд - получить PDF-гайд и выбрать проблему\n"
        "• 📞 Записаться на консультацию - прямой переход к записи\n"
        "• ℹ️  О психологе - информация о специалисте\n\n"
        "🔄 <b>Автоворонка:</b>\n"
        "1. Получите гайд\n"
        "2. Выберите проблему (или опишите свою)\n"
        "3. Укажите имя, возраст и Telegram username\n"
        "4. Оставьте заявку на бесплатную консультацию\n\n"
        "📝 <b>О проблемах:</b>\n"
        "• Можно выбрать из предложенных вариантов\n"
        "• Или подробно описать свою ситуацию\n\n"
        "👨‍💼 <b>Административные команды:</b>\n"
        "• /stats - Статистика бота\n"
        "• /export - Экспорт базы данных в Excel\n\n"
        "<i>Консультации проходят в Telegram для вашего удобства.</i>")

    await message.answer(help_text)


@router.message(Command("test"))
async def command_test(message: types.Message):
    """Тестовая команда"""
    await message.answer("✅ <b>Тест пройден успешно!</b>\n\n"
                         "Бот работает корректно.")


@router.message()
async def handle_other_messages(message: types.Message):
    """Обработчик всех остальных сообщений"""
    await message.answer(
        "🤖 <b>Я — бот-помощник психолога.</b>\n\n"
        "Чтобы начать работу, нажмите /start или выберите действие в меню.\n\n"
        "Для справки нажмите /help",
        reply_markup=create_main_keyboard())


# ========== ЗАПУСК БОТА ==========
async def on_startup():
    """Действия при запуске"""
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК TELEGRAM-БОТА ДЛЯ ПСИХОЛОГА")
    logger.info("=" * 50)

    # Инициализация и обновление БД
    init_database()

    if ADMIN_ID:
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=
                ("🤖 <b>Бот психолога успешно запущен!</b>\n\n"
                 f"⏰ <b>Время запуска:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                 "📍 <b>Платформа:</b> Replit\n"
                 "✅ <b>Статус:</b> Активен и готов к работе\n\n"
                 "<i>Для проверки работы отправьте боту /start</i>"))
            logger.info(
                f"📨 Уведомление о запуске отправлено администратору {ADMIN_ID}"
            )
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление админу: {e}")

    demo_files = ["guide.pdf", "welcome.jpg"]
    for file in demo_files:
        if not os.path.exists(file):
            logger.warning(f"⚠️  Демо файл {file} не найден")

    logger.info("✅ Бот инициализирован и готов к работе!")
    logger.info("=" * 50)


async def main():
    """Основная функция запуска"""
    try:
        await on_startup()

        await bot.delete_webhook(drop_pending_updates=True)

        logger.info("🔄 Запуск поллинга...")
        await dp.start_polling(bot)

    except KeyboardInterrupt:
        logger.info("⏹️  Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        if ADMIN_ID:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ <b>Бот упал с ошибкой:</b>\n\n<code>{str(e)[:1000]}</code>"
                )
            except:
                pass
        raise


# ========== ТОЧКА ВХОДА ==========
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Завершение работы бота")
    except Exception as e:
        logger.error(f"🔥 Фатальная ошибка: {e}")

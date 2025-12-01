import os
import asyncio
import logging
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from tinydb import TinyDB, Query
import re

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = TinyDB('bot_db.json')
settings_db = db.table('settings')
chats_db = db.table('chats')
accounts_db = db.table('accounts')
admins_db = db.table('admins')
users_db = db.table('users')
subscriptions_db = db.table('subscriptions')
payments_db = db.table('payments')

# Папка для сессий
if not os.path.exists('sessions'):
    os.makedirs('sessions')

# Настройки по умолчанию
if not settings_db.get(Query().name == 'message'):
    settings_db.insert({'name': 'message', 'value': '✅ Vision Flow✅ — универсальный ИИ-бот в Telegram\n\n📷 Создание видео:\nSora 2 • Veo 3.1 • Kling 2.5 Turbo\n\n📱Для аватарок и фото:\nNanoBanana — настоящий убийца Photoshop и Midjourney.\nМеняет фон, одежду, стиль и детали за пару секунд.\n\n📱Создание музыки:\nSuno 5 — два режима: Простой и Профессиональный.\nГенерируй треки любого жанра по своему описанию.\n\n😆 Мозг системы — ChatGPT 5\nОтвечает на вопросы, пишет тексты, придумывает идеи, помогает с промптами и задачами.\n\n📎Всё работает прямо в Telegram — быстро, удобно и бесплатно в базовом режиме.\nПопробуй Vision Flow и почувствуй силу нового уровня ИИ!\n\n✔️ [https://t.me/vision_flow_bot?start=telegram_organic_neo]'})

if not settings_db.get(Query().name == 'interval'):
    settings_db.insert({'name': 'interval', 'value': '30'})

if not settings_db.get(Query().name == 'pause'):
    settings_db.insert({'name': 'pause', 'value': '3600'})

if not settings_db.get(Query().name == 'active'):
    settings_db.insert({'name': 'active', 'value': '0'})

if not settings_db.get(Query().name == 'current_account'):
    settings_db.insert({'name': 'current_account', 'value': '0'})

# Настройки канала для подписки
if not settings_db.get(Query().name == 'channel_username'):
    settings_db.insert({'name': 'channel_username', 'value': '@rassilka_doxsnul'})

# Главный администратор (ваш ID)
MAIN_ADMIN_ID = 8295604601  # ЗАМЕНИТЕ НА ВАШ ID

# Добавляем главного администратора в базу
if not admins_db.get(Query().user_id == MAIN_ADMIN_ID):
    admins_db.insert({
        'user_id': MAIN_ADMIN_ID,
        'username': 'Главный',
        'added_by': 'system',
        'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# Функция проверки админа
def is_admin(user_id):
    """Проверка на администратора"""
    return admins_db.contains(Query().user_id == user_id)

# Классы состояний для FSM
class SpamStates(StatesGroup):
    waiting_message = State()
    waiting_interval = State()
    waiting_pause = State()
    selecting_chats = State()
    waiting_api_hash = State()
    waiting_api_id = State()
    waiting_phone = State()
    waiting_account_name = State()
    waiting_code = State()
    waiting_password = State()
    waiting_payment_proof = State()
    waiting_channel_username = State()

# Инициализация бота
bot = Bot(token="8475634481:AAGXvq8bQYTNmX9vb5dHYEm6ucvydtgh-gg")  # Замените на ваш токен
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Глобальные переменные
is_spam_active = False
adding_clients = {}
pending_subscriptions = {}

# Проверка подписки на канал
async def check_channel_subscription(user_id):
    """Проверяет, подписан ли пользователь на канал"""
    try:
        channel_username = settings_db.get(Query().name == 'channel_username')['value']
        if not channel_username.startswith('@'):
            channel_username = '@' + channel_username
        
        chat_member = await bot.get_chat_member(channel_username, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

# Проверка активной подписки пользователя
def check_user_subscription(user_id):
    """Проверяет активную подписку пользователя"""
    user_sub = subscriptions_db.get(Query().user_id == user_id)
    if user_sub:
        end_date = datetime.fromisoformat(user_sub['end_date'])
        if end_date > datetime.now():
            return True
    return False

# Получение информации о подписке
def get_subscription_info(user_id):
    """Получает информацию о подписке пользователя"""
    user_sub = subscriptions_db.get(Query().user_id == user_id)
    if user_sub:
        end_date = datetime.fromisoformat(user_sub['end_date'])
        remaining = end_date - datetime.now()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() / 3600)
            minutes = int((remaining.total_seconds() % 3600) / 60)
            return f"✅ Активна до: {end_date.strftime('%d.%m.%Y %H:%M')}\n⏳ Осталось: {hours}ч {minutes}м"
    return "❌ Нет активной подписки"

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    # Регистрируем пользователя
    if not users_db.get(Query().user_id == user_id):
        users_db.insert({
            'user_id': user_id,
            'username': message.from_user.username or '',
            'first_name': message.from_user.first_name or '',
            'join_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    # Проверяем подписку на канал
    if not await check_channel_subscription(user_id):
        channel_username = settings_db.get(Query().name == 'channel_username')['value']
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{channel_username.lstrip('@')}")],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")]
        ])
        await message.answer(
            "📢 Для использования бота необходимо подписаться на наш канал!\n\n"
            f"Канал: {channel_username}\n\n"
            "После подписки нажмите кнопку ниже:",
            reply_markup=keyboard
        )
        return
    
    # Проверяем админа
    if is_admin(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статус", callback_data="status")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton(text="👥 Чаты", callback_data="chats")],
            [InlineKeyboardButton(text="👤 Аккаунты", callback_data="accounts")],
            [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account")],
            [InlineKeyboardButton(text="▶️ Старт рассылки", callback_data="start_spam")],
            [InlineKeyboardButton(text="⏹️ Стоп рассылки", callback_data="stop_spam")],
            [InlineKeyboardButton(text="👑 Админы", callback_data="admins")],
            [InlineKeyboardButton(text="💰 Подписки", callback_data="subscriptions_menu")]
        ])
        await message.answer("👑 Админ панель:", reply_markup=keyboard)
    else:
        # Проверяем подписку пользователя
        if check_user_subscription(user_id):
            sub_info = get_subscription_info(user_id)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_subscription")],
                [InlineKeyboardButton(text="ℹ️ Моя подписка", callback_data="my_subscription")],
                [InlineKeyboardButton(text="📱 Контакты", callback_data="contacts")]
            ])
            await message.answer(
                f"👋 Добро пожаловать, {message.from_user.first_name}!\n\n"
                f"{sub_info}\n\n"
                "Выберите действие:",
                reply_markup=keyboard
            )
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_subscription")],
                [InlineKeyboardButton(text="ℹ️ Как купить", callback_data="how_to_buy")],
                [InlineKeyboardButton(text="📱 Контакты", callback_data="contacts")]
            ])
            await message.answer(
                f"👋 Добро пожаловать, {message.from_user.first_name}!\n\n"
                "❌ У вас нет активной подписки.\n"
                "Для использования бота необходимо приобрести подписку.\n\n"
                "Выберите действие:",
                reply_markup=keyboard
            )

# Кнопка "Проверить подписку на канал"
@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if await check_channel_subscription(user_id):
        await callback.message.edit_text("✅ Отлично! Вы подписаны на канал.")
        await asyncio.sleep(2)
        await cmd_start(callback.message)
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)

# Кнопка "Настройки"
@dp.callback_query(F.data == "settings")
async def settings_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить текст", callback_data="edit_text")],
        [InlineKeyboardButton(text="⏱️ Интервал отправки", callback_data="edit_interval")],
        [InlineKeyboardButton(text="⏸️ Пауза между циклами", callback_data="edit_pause")],
        [InlineKeyboardButton(text="📢 Изменить канал", callback_data="edit_channel")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
    ])
    await callback.message.edit_text("⚙️ Настройки:", reply_markup=keyboard)

# Кнопка "Изменить канал"
@dp.callback_query(F.data == "edit_channel")
async def edit_channel_callback(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    current_channel = settings_db.get(Query().name == 'channel_username')['value']
    await state.set_state(SpamStates.waiting_channel_username)
    await callback.message.edit_text(
        f"Текущий канал: {current_channel}\n\n"
        "Отправьте username нового канала (например @rassilka_doxsnul):"
    )

# Сохранение канала
@dp.message(SpamStates.waiting_channel_username)
async def save_channel_username(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    channel_username = message.text.strip()
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    
    settings_db.update({'value': channel_username}, Query().name == 'channel_username')
    await message.answer(f"✅ Канал изменен на: {channel_username}")
    await state.clear()
    await settings_callback(message)

# Кнопка "Статус"
@dp.callback_query(F.data == "status")
async def status_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    chats = chats_db.all()
    active = settings_db.get(Query().name == 'active')['value']
    accounts = accounts_db.all()
    current_account_id = settings_db.get(Query().name == 'current_account')['value']
    admins_count = len(admins_db.all())
    
    current_account = None
    for acc in accounts:
        if str(acc['id']) == current_account_id:
            current_account = acc
            break
    
    text = f"📊 Статус системы:\n"
    text += f"🔸 Рассылка: {'✅ ВКЛ' if active == '1' else '❌ ВЫКЛ'}\n"
    text += f"🔸 Чатов: {len(chats)}\n"
    text += f"🔸 Аккаунтов: {len(accounts)}\n"
    text += f"🔸 Админов: {admins_count}\n"
    if current_account:
        text += f"🔸 Текущий аккаунт: {current_account.get('name', current_account['phone'])}\n"
    text += f"🔸 Интервал: {settings_db.get(Query().name == 'interval')['value']} сек\n"
    text += f"🔸 Пауза: {settings_db.get(Query().name == 'pause')['value']} сек"
    
    await callback.message.edit_text(text)

# Кнопка "Чаты"
@dp.callback_query(F.data == "chats")
async def chats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    chats = chats_db.all()
    
    if not chats:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить чат", callback_data="add_chat")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
        ])
        await callback.message.edit_text("👥 Чатов нет\n\nДобавьте чаты вручную", reply_markup=keyboard)
    else:
        text = f"👥 Список чатов ({len(chats)}):\n\n"
        for i, chat in enumerate(chats[:10], 1):
            text += f"{i}. {chat.get('title', 'Без названия')} (ID: {chat['chat_id']})\n"
        
        if len(chats) > 10:
            text += f"\n... и еще {len(chats) - 10} чатов"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить чат", callback_data="add_chat")],
            [InlineKeyboardButton(text="🗑️ Очистить все", callback_data="clear_chats")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)

# Добавление чата
@dp.callback_query(F.data == "add_chat")
async def add_chat_callback(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    await state.set_state(SpamStates.selecting_chats)
    await callback.message.edit_text(
        "Отправьте ID чата или перешлите сообщение из него\n\n"
        "Как получить ID:\n"
        "1. Добавьте @username_to_id_bot в чат\n"
        "2. Отправьте /id\n"
        "3. Перешлите мне ответ\n\n"
        "Или отправьте /cancel для отмены"
    )

# Обработка добавления чата
@dp.message(SpamStates.selecting_chats)
async def process_add_chat(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    if message.text and message.text.startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Добавление чата отменено")
        await cmd_start(message)
        return
    
    chat_id = None
    chat_title = "Без названия"
    
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        chat_title = message.forward_from_chat.title or "Без названия"
    elif message.text and message.text.lstrip('-').isdigit():
        chat_id = int(message.text)
        try:
            chat = await bot.get_chat(chat_id)
            chat_title = chat.title or "Без названия"
        except:
            pass
    
    if chat_id:
        existing = chats_db.get(Query().chat_id == chat_id)
        if not existing:
            chats_db.insert({
                'chat_id': chat_id,
                'title': chat_title,
                'added': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'added_by': message.from_user.id
            })
            await message.answer(f"✅ Чат добавлен: {chat_title}")
        else:
            await message.answer("⚠️ Этот чат уже есть в списке")
    else:
        await message.answer("❌ Не удалось определить чат. Попробуйте снова:")
        return
    
    await state.clear()
    await cmd_start(message)

# Очистка чатов
@dp.callback_query(F.data == "clear_chats")
async def clear_chats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, очистить все", callback_data="confirm_clear_chats")],
        [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="chats")]
    ])
    
    await callback.message.edit_text(
        "⚠️ Вы уверены что хотите очистить все чаты?\n\n"
        "Это действие нельзя отменить!",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "confirm_clear_chats")
async def confirm_clear_chats_callback(callback: types.CallbackQuery):
    chats_db.truncate()
    await callback.answer("✅ Все чаты удалены")
    await chats_callback(callback)

# Кнопка "Аккаунты"
@dp.callback_query(F.data == "accounts")
async def accounts_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    accounts = accounts_db.all()
    current_account_id = settings_db.get(Query().name == 'current_account')['value']
    
    if not accounts:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
        ])
        await callback.message.edit_text("👤 Аккаунтов нет", reply_markup=keyboard)
        return
    
    text = "👤 Аккаунты:\n\n"
    for acc in accounts:
        status = "✅" if str(acc['id']) == current_account_id else "❌"
        text += f"{status} {acc.get('name', acc['phone'])} ({acc['phone']})\n"
    
    keyboard_buttons = []
    for acc in accounts:
        if str(acc['id']) != current_account_id:
            keyboard_buttons.append([InlineKeyboardButton(
                text=f"✅ Выбрать {acc.get('name', acc['phone'])}", 
                callback_data=f"select_account_{acc['id']}"
            )])
    
    keyboard_buttons.append([InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account")])
    keyboard_buttons.append([InlineKeyboardButton(text="🗑️ Удалить аккаунт", callback_data="delete_account")])
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)

# Добавление аккаунта
@dp.callback_query(F.data == "add_account")
async def add_account_callback(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    await state.set_state(SpamStates.waiting_api_hash)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
    ])
    
    await callback.message.edit_text(
        "🔄 Процесс добавления аккаунта:\n\n"
        "🔑 Шаг 1 из 5\n"
        "Введите API Hash (32 символа):",
        reply_markup=keyboard
    )

# Получение API Hash
@dp.message(SpamStates.waiting_api_hash)
async def process_api_hash(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    api_hash = message.text.strip()
    
    if len(api_hash) != 32 or not re.match(r'^[a-f0-9]+$', api_hash):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
        ])
        await message.answer("❌ Неверный формат API Hash. Должно быть 32 hex символа.\nПопробуйте снова:", reply_markup=keyboard)
        return
    
    await state.update_data(api_hash=api_hash)
    await state.set_state(SpamStates.waiting_api_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
    ])
    
    await message.answer(
        "✅ API Hash сохранен\n\n"
        "🔑 Шаг 2 из 5\n"
        "Теперь введите API ID (только цифры):",
        reply_markup=keyboard
    )

# Получение API ID
@dp.message(SpamStates.waiting_api_id)
async def process_api_id(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    api_id = message.text.strip()
    
    if not api_id.isdigit():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
        ])
        await message.answer("❌ API ID должен быть числом. Попробуйте снова:", reply_markup=keyboard)
        return
    
    await state.update_data(api_id=api_id)
    await state.set_state(SpamStates.waiting_phone)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
    ])
    
    await message.answer(
        "✅ API ID сохранен\n\n"
        "📱 Шаг 3 из 5\n"
        "Теперь введите номер телефона в международном формате:\n"
        "Пример: +79991234567",
        reply_markup=keyboard
    )

# Получение номера телефона
@dp.message(SpamStates.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    phone = message.text.strip()
    
    if not phone.startswith('+'):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
        ])
        await message.answer("❌ Номер должен начинаться с +. Попробуйте снова:", reply_markup=keyboard)
        return
    
    existing = accounts_db.get(Query().phone == phone)
    if existing:
        await message.answer("❌ Этот аккаунт уже добавлен")
        await state.clear()
        await cmd_start(message)
        return
    
    await state.update_data(phone=phone)
    await state.set_state(SpamStates.waiting_account_name)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
    ])
    
    await message.answer(
        "✅ Номер сохранен\n\n"
        "👤 Шаг 4 из 5\n"
        "Введите имя для этого аккаунта (для удобства):",
        reply_markup=keyboard
    )

# Получение имени аккаунта
@dp.message(SpamStates.waiting_account_name)
async def process_account_name(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    account_name = message.text.strip()
    user_id = message.from_user.id
    
    data = await state.get_data()
    api_id = data['api_id']
    api_hash = data['api_hash']
    phone = data['phone']
    
    session_name = f"sessions/{phone.replace('+', '')}"
    
    try:
        client = TelegramClient(
            session_name,
            int(api_id),
            api_hash
        )
        
        await client.connect()
        await client.send_code_request(phone)
        
        adding_clients[user_id] = {
            'client': client,
            'api_id': api_id,
            'api_hash': api_hash,
            'phone': phone,
            'name': account_name,
            'session_name': session_name
        }
        
        number_buttons = [
            [
                InlineKeyboardButton(text="1", callback_data="code_1"),
                InlineKeyboardButton(text="2", callback_data="code_2"),
                InlineKeyboardButton(text="3", callback_data="code_3"),
                InlineKeyboardButton(text="4", callback_data="code_4"),
                InlineKeyboardButton(text="5", callback_data="code_5")
            ],
            [
                InlineKeyboardButton(text="6", callback_data="code_6"),
                InlineKeyboardButton(text="7", callback_data="code_7"),
                InlineKeyboardButton(text="8", callback_data="code_8"),
                InlineKeyboardButton(text="9", callback_data="code_9"),
                InlineKeyboardButton(text="0", callback_data="code_0")
            ],
            [
                InlineKeyboardButton(text="⌫ Удалить", callback_data="code_delete"),
                InlineKeyboardButton(text="✅ Готово", callback_data="code_submit")
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=number_buttons)
        
        await state.update_data(entered_code="", account_name=account_name)
        await state.set_state(SpamStates.waiting_code)
        
        await message.answer(
            "✅ Код отправлен на телефон!\n\n"
            "🔢 Шаг 5 из 5\n"
            "Введите код из Telegram:\n\n"
            "Код: <b>____</b>\n\n"
            "Используйте кнопки ниже для ввода кода:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке кода: {e}")
        await state.clear()

# Обработка кнопок с цифрами
@dp.callback_query(F.data.startswith("code_"))
async def process_code_button(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    data = await state.get_data()
    current_code = data.get('entered_code', '')
    
    button_data = callback.data
    if button_data == "code_delete":
        new_code = current_code[:-1]
    elif button_data == "code_submit":
        await submit_code(callback, state)
        return
    else:
        digit = button_data.split('_')[1]
        if len(current_code) < 5:
            new_code = current_code + digit
    
    await state.update_data(entered_code=new_code)
    
    display_code = new_code + "_" * (5 - len(new_code))
    
    number_buttons = [
        [
            InlineKeyboardButton(text="1", callback_data="code_1"),
            InlineKeyboardButton(text="2", callback_data="code_2"),
            InlineKeyboardButton(text="3", callback_data="code_3"),
            InlineKeyboardButton(text="4", callback_data="code_4"),
            InlineKeyboardButton(text="5", callback_data="code_5")
        ],
        [
            InlineKeyboardButton(text="6", callback_data="code_6"),
            InlineKeyboardButton(text="7", callback_data="code_7"),
            InlineKeyboardButton(text="8", callback_data="code_8"),
            InlineKeyboardButton(text="9", callback_data="code_9"),
            InlineKeyboardButton(text="0", callback_data="code_0")
        ],
        [
            InlineKeyboardButton(text="⌫ Удалить", callback_data="code_delete"),
            InlineKeyboardButton(text="✅ Готово", callback_data="code_submit")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=number_buttons)
    
    await callback.message.edit_text(
        "✅ Код отправлен на телефон!\n\n"
        "🔢 Шаг 5 из 5\n"
        "Введите код из Telegram:\n\n"
        f"Код: <b>{display_code}</b>\n\n"
        "Используйте кнопки ниже для ввода кода:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    
    await callback.answer()

# Отправка кода
async def submit_code(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code = data.get('entered_code', '')
    
    if len(code) != 5:
        await callback.answer("❌ Код должен быть 5 цифр")
        return
    
    user_id = callback.from_user.id
    
    if user_id not in adding_clients:
        await callback.message.edit_text("❌ Сессия утеряна. Начните заново.")
        await state.clear()
        return
    
    acc_data = adding_clients[user_id]
    client = acc_data['client']
    
    try:
        await client.sign_in(acc_data['phone'], code)
        
        me = await client.get_me()
        
        all_accounts = accounts_db.all()
        new_id = max([acc['id'] for acc in all_accounts]) + 1 if all_accounts else 1
        
        accounts_db.insert({
            'id': new_id,
            'api_id': acc_data['api_id'],
            'api_hash': acc_data['api_hash'],
            'phone': acc_data['phone'],
            'name': acc_data['name'],
            'session_name': acc_data['session_name'],
            'first_name': me.first_name,
            'username': me.username,
            'added': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'added_by': user_id
        })
        
        if len(all_accounts) == 0:
            settings_db.update({'value': str(new_id)}, Query().name == 'current_account')
        
        await callback.message.edit_text(
            f"✅ Аккаунт успешно добавлен!\n\n"
            f"👤 Имя: {me.first_name}\n"
            f"📱 Телефон: {acc_data['phone']}\n"
            f"🔗 Username: @{me.username}\n"
            f"🏷️ В системе: {acc_data['name']}"
        )
        
        await client.disconnect()
        del adding_clients[user_id]
        await state.clear()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="accounts")]
        ])
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
    except SessionPasswordNeededError:
        await state.set_state(SpamStates.waiting_password)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_account")]
        ])
        
        await callback.message.edit_text(
            "🔐 Требуется пароль двухфакторной аутентификации\n\n"
            "Введите пароль 2FA:",
            reply_markup=keyboard
        )
        
    except Exception as e:
        error_msg = str(e).lower()
        if 'code' in error_msg or 'invalid' in error_msg:
            msg = "❌ Неверный код. Попробуйте снова:"
        else:
            msg = f"❌ Ошибка: {e}"
        
        await callback.message.edit_text(msg)
        await state.update_data(entered_code="")

# Обработка пароля 2FA
@dp.message(SpamStates.waiting_password)
async def process_2fa_password(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    password = message.text.strip()
    user_id = message.from_user.id
    
    if user_id not in adding_clients:
        await message.answer("❌ Сессия утеряна. Начните заново.")
        await state.clear()
        return
    
    acc_data = adding_clients[user_id]
    client = acc_data['client']
    
    try:
        await client.sign_in(password=password)
        
        me = await client.get_me()
        
        all_accounts = accounts_db.all()
        new_id = max([acc['id'] for acc in all_accounts]) + 1 if all_accounts else 1
        
        accounts_db.insert({
            'id': new_id,
            'api_id': acc_data['api_id'],
            'api_hash': acc_data['api_hash'],
            'phone': acc_data['phone'],
            'name': acc_data['name'],
            'session_name': acc_data['session_name'],
            'first_name': me.first_name,
            'username': me.username,
            'added': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'added_by': user_id,
            'has_2fa': True
        })
        
        if len(all_accounts) == 0:
            settings_db.update({'value': str(new_id)}, Query().name == 'current_account')
        
        await message.answer(
            f"✅ Аккаунт с 2FA успешно добавлен!\n\n"
            f"👤 Имя: {me.first_name}\n"
            f"📱 Телефон: {acc_data['phone']}\n"
            f"🔗 Username: @{me.username}\n"
            f"🏷️ В системе: {acc_data['name']}\n"
            f"🔐 С двухфакторной аутентификацией"
        )
        
        await client.disconnect()
        del adding_clients[user_id]
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при вводе пароля: {e}\nПопробуйте снова:")
    
    await state.clear()

# Отмена добавления аккаунта
@dp.callback_query(F.data == "cancel_add_account")
async def cancel_add_account(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if user_id in adding_clients:
        try:
            await adding_clients[user_id]['client'].disconnect()
        except:
            pass
        del adding_clients[user_id]
    
    await state.clear()
    await callback.message.edit_text("❌ Добавление аккаунта отменено.")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="accounts")]
    ])
    await callback.message.edit_reply_markup(reply_markup=keyboard)

# Выбор аккаунта
@dp.callback_query(F.data.startswith("select_account_"))
async def select_account_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    account_id = callback.data.split("_")[2]
    settings_db.update({'value': account_id}, Query().name == 'current_account')
    
    account = accounts_db.get(Query().id == int(account_id))
    await callback.answer(f"✅ Выбран аккаунт: {account.get('name', account['phone'])}")
    await accounts_callback(callback)

# Удаление аккаунта
@dp.callback_query(F.data == "delete_account")
async def delete_account_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    accounts = accounts_db.all()
    
    if not accounts:
        await callback.answer("❌ Нет аккаунтов для удаления")
        return
    
    keyboard_buttons = []
    for acc in accounts:
        keyboard_buttons.append([InlineKeyboardButton(
            text=f"🗑️ {acc.get('name', acc['phone'])}", 
            callback_data=f"delete_acc_{acc['id']}"
        )])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="accounts")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text("🗑️ Выберите аккаунт для удаления:", reply_markup=keyboard)

# Подтверждение удаления аккаунта
@dp.callback_query(F.data.startswith("delete_acc_"))
async def confirm_delete_account(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    account_id = int(callback.data.split("_")[2])
    account = accounts_db.get(Query().id == account_id)
    
    if not account:
        await callback.answer("❌ Аккаунт не найден")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_del_{account_id}")],
        [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="accounts")]
    ])
    
    await callback.message.edit_text(
        f"⚠️ Вы уверены что хотите удалить аккаунт?\n\n"
        f"Имя: {account.get('name', 'Не указано')}\n"
        f"Телефон: {account['phone']}\n\n"
        f"Это действие нельзя отменить!",
        reply_markup=keyboard
    )

# Удаление аккаунта
@dp.callback_query(F.data.startswith("confirm_del_"))
async def execute_delete_account(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    account_id = int(callback.data.split("_")[2])
    account = accounts_db.get(Query().id == account_id)
    
    if account:
        session_file = account['session_name']
        if os.path.exists(session_file + '.session'):
            os.remove(session_file + '.session')
        
        accounts_db.remove(Query().id == account_id)
        
        current_account_id = settings_db.get(Query().name == 'current_account')['value']
        if current_account_id == str(account_id):
            remaining_accounts = accounts_db.all()
            if remaining_accounts:
                settings_db.update({'value': str(remaining_accounts[0]['id'])}, Query().name == 'current_account')
            else:
                settings_db.update({'value': '0'}, Query().name == 'current_account')
        
        await callback.answer("✅ Аккаунт удален")
    else:
        await callback.answer("❌ Аккаунт не найден")
    
    await accounts_callback(callback)

# Кнопка "Назад" для админов
@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="👥 Чаты", callback_data="chats")],
        [InlineKeyboardButton(text="👤 Аккаунты", callback_data="accounts")],
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account")],
        [InlineKeyboardButton(text="▶️ Старт рассылки", callback_data="start_spam")],
        [InlineKeyboardButton(text="⏹️ Стоп рассылки", callback_data="stop_spam")],
        [InlineKeyboardButton(text="👑 Админы", callback_data="admins")],
        [InlineKeyboardButton(text="💰 Подписки", callback_data="subscriptions_menu")]
    ])
    await callback.message.edit_text("👑 Админ панель:", reply_markup=keyboard)

# Кнопка "Админы"
@dp.callback_query(F.data == "admins")
async def admins_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    admins_list = admins_db.all()
    
    if not admins_list:
        text = "📋 Список админов пуст"
    else:
        text = "📋 Список админов:\n\n"
        for admin in admins_list:
            status = "👑" if admin['user_id'] == MAIN_ADMIN_ID else "👤"
            text += f"{status} ID: {admin['user_id']}\n"
            if 'username' in admin:
                text += f"   Имя: {admin['username']}\n"
            if 'date' in admin:
                text += f"   Добавлен: {admin['date']}\n"
            text += "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)

# Команда /addadmin
@dp.message(Command("addadmin"))
async def cmd_addadmin(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        await message.answer("❌ Только главный администратор может добавлять админов")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Использование: /addadmin user_id [username]")
            return
        
        new_admin_id = int(parts[1])
        username = parts[2] if len(parts) > 2 else "Новый админ"
        
        if admins_db.contains(Query().user_id == new_admin_id):
            await message.answer("❌ Этот пользователь уже администратор")
            return
        
        admins_db.insert({
            'user_id': new_admin_id,
            'username': username,
            'added_by': message.from_user.id,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        await message.answer(f"✅ Пользователь {new_admin_id} добавлен как администратор")
        
        try:
            await bot.send_message(new_admin_id, 
                "🎉 Вы получили доступ к боту администратора!\n\n"
                "Теперь у вас есть доступ к:\n"
                "• Управлению рассылкой\n"
                "• Добавлению аккаунтов\n"
                "• Выдаче подписок\n"
                "• Проверке платежей\n\n"
                "Используйте /start для входа в админ-панель."
            )
        except:
            pass
            
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /addadmin user_id [username]")

# Команда /deladmin
@dp.message(Command("deladmin"))
async def cmd_deladmin(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        await message.answer("❌ Только главный администратор может удалять админов")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Использование: /deladmin user_id")
            return
        
        admin_id_to_remove = int(parts[1])
        
        if admin_id_to_remove == MAIN_ADMIN_ID:
            await message.answer("❌ Нельзя удалить главного администратора")
            return
        
        admins_db.remove(Query().user_id == admin_id_to_remove)
        await message.answer(f"✅ Администратор {admin_id_to_remove} удален")
        
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /deladmin user_id")

# Кнопка "Подписки"
@dp.callback_query(F.data == "subscriptions_menu")
async def subscriptions_menu_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список подписок", callback_data="list_subscriptions")],
        [InlineKeyboardButton(text="➕ Выдать подписку", callback_data="give_subscription")],
        [InlineKeyboardButton(text="💳 Проверка платежей", callback_data="check_payments")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
    ])
    await callback.message.edit_text("💰 Управление подписками:", reply_markup=keyboard)

# Список подписок
@dp.callback_query(F.data == "list_subscriptions")
async def list_subscriptions_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    active_subs = subscriptions_db.all()
    active_count = 0
    text = "📋 Активные подписки:\n\n"
    
    for sub in active_subs:
        end_date = datetime.fromisoformat(sub['end_date'])
        if end_date > datetime.now():
            active_count += 1
            user_id = sub['user_id']
            user = users_db.get(Query().user_id == user_id)
            username = f"@{user['username']}" if user and user.get('username') else f"ID: {user_id}"
            text += f"👤 {username}\n"
            text += f"   До: {end_date.strftime('%d.%m.%Y %H:%M')}\n"
            remaining = end_date - datetime.now()
            hours = int(remaining.total_seconds() / 3600)
            text += f"   Осталось: {hours} часов\n\n"
    
    text += f"Всего активных: {active_count}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="subscriptions_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)

# Выдать подписку
@dp.callback_query(F.data == "give_subscription")
async def give_subscription_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="3 часа", callback_data="give_3h")],
        [InlineKeyboardButton(text="10 часов", callback_data="give_10h")],
        [InlineKeyboardButton(text="30 часов", callback_data="give_30h")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="subscriptions_menu")]
    ])
    
    await callback.message.edit_text(
        "⏱️ Выберите длительность подписки для выдачи:",
        reply_markup=keyboard
    )

# Выбор длительности подписки для выдачи
@dp.callback_query(F.data.startswith("give_"))
async def give_subscription_duration(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    duration = callback.data.split('_')[1]
    hours_map = {'3h': 3, '10h': 10, '30h': 30}
    hours = hours_map.get(duration, 3)
    
    pending_subscriptions[callback.from_user.id] = {'hours': hours}
    
    await callback.message.edit_text(
        f"Вы выбрали {hours} часов.\n\n"
        f"Теперь отправьте мне ID пользователя, которому нужно выдать подписку.\n"
        f"Можно переслать любое сообщение от пользователя."
    )

# Обработка ID пользователя для подписки
@dp.message(F.text)
async def process_user_id_for_subscription(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in pending_subscriptions:
        return
    
    if not is_admin(user_id):
        return
    
    try:
        target_user_id = None
        
        if message.forward_from:
            target_user_id = message.forward_from.id
        elif message.text.isdigit():
            target_user_id = int(message.text)
        else:
            await message.answer("❌ Не удалось определить ID пользователя. Попробуйте еще раз.")
            return
        
        hours = pending_subscriptions[user_id]['hours']
        end_date = datetime.now() + timedelta(hours=hours)
        
        subscriptions_db.upsert({
            'user_id': target_user_id,
            'end_date': end_date.isoformat(),
            'hours': hours,
            'given_by': user_id,
            'given_date': datetime.now().isoformat()
        }, Query().user_id == target_user_id)
        
        payments_db.insert({
            'user_id': target_user_id,
            'amount': 0,
            'hours': hours,
            'status': 'completed',
            'admin_id': user_id,
            'date': datetime.now().isoformat()
        })
        
        user_info = users_db.get(Query().user_id == target_user_id)
        username = f"@{user_info['username']}" if user_info and user_info.get('username') else f"ID: {target_user_id}"
        
        await message.answer(
            f"✅ Подписка выдана успешно!\n\n"
            f"👤 Пользователь: {username}\n"
            f"⏱️ Длительность: {hours} часов\n"
            f"📅 До: {end_date.strftime('%d.%m.%Y %H:%M')}"
        )
        
        try:
            await bot.send_message(
                target_user_id,
                f"🎉 Вам выдана подписка на {hours} часов!\n\n"
                f"✅ Подписка активна до: {end_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Используйте /start для обновления статуса."
            )
        except:
            pass
        
        del pending_subscriptions[user_id]
        await subscriptions_menu_callback(message)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        del pending_subscriptions[user_id]

# Проверка платежей
@dp.callback_query(F.data == "check_payments")
async def check_payments_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    pending_payments = payments_db.search(Query().status == 'pending')
    
    if not pending_payments:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="subscriptions_menu")]
        ])
        await callback.message.edit_text("✅ Нет ожидающих платежей.", reply_markup=keyboard)
        return
    
    text = "⏳ Ожидающие платежи:\n\n"
    
    for payment in pending_payments[:10]:
        user_id = payment['user_id']
        user = users_db.get(Query().user_id == user_id)
        username = f"@{user['username']}" if user and user.get('username') else f"ID: {user_id}"
        
        text += f"👤 {username}\n"
        text += f"   💰 {payment['amount']} ⭐\n"
        text += f"   ⏱️ {payment['hours']} часов\n"
        text += f"   📅 {payment['date'][:16]}\n"
        text += f"   /activate {user_id} {payment['hours']}\n\n"
    
    if len(pending_payments) > 10:
        text += f"\n... и еще {len(pending_payments) - 10} платежей"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="check_payments")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="subscriptions_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)

# Команда /activate
@dp.message(Command("activate"))
async def activate_subscription_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Использование: /activate user_id hours")
            return
        
        target_user_id = int(parts[1])
        hours = int(parts[2])
        
        end_date = datetime.now() + timedelta(hours=hours)
        subscriptions_db.upsert({
            'user_id': target_user_id,
            'end_date': end_date.isoformat(),
            'hours': hours,
            'given_by': message.from_user.id,
            'given_date': datetime.now().isoformat()
        }, Query().user_id == target_user_id)
        
        payments_db.update({
            'status': 'completed',
            'admin_id': message.from_user.id,
            'activated_date': datetime.now().isoformat()
        }, Query().user_id == target_user_id & Query().status == 'pending')
        
        try:
            await bot.send_message(
                target_user_id,
                f"🎉 Ваша подписка активирована!\n\n"
                f"✅ Подписка на {hours} часов активна\n"
                f"📅 До: {end_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Используйте /start для обновления статуса."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя: {e}")
        
        await message.answer(f"✅ Подписка для пользователя {target_user_id} активирована на {hours} часов.")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# Кнопка "Купить подписку"
@dp.callback_query(F.data == "buy_subscription")
async def buy_subscription_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱️ 3 часа - 50 ⭐", callback_data="buy_3h")],
        [InlineKeyboardButton(text="⏱️ 10 часов - 150 ⭐", callback_data="buy_10h")],
        [InlineKeyboardButton(text="⏱️ 30 часов - 500 ⭐", callback_data="buy_30h")],
        [InlineKeyboardButton(text="ℹ️ Как отправить звезды", callback_data="how_to_send_stars")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_user")]
    ])
    
    await callback.message.edit_text(
        "🛒 Выберите подписку:\n\n"
        "⏱️ 3 часа - 50 ⭐\n"
        "⏱️ 10 часов - 150 ⭐\n"
        "⏱️ 30 часов - 500 ⭐\n\n"
        "После оплаты отправьте скриншот чека администратору.",
        reply_markup=keyboard
    )

# Выбор подписки для покупки
@dp.callback_query(F.data.startswith("buy_"))
async def choose_subscription_callback(callback: types.CallbackQuery, state: FSMContext):
    duration = callback.data.split('_')[1]
    prices = {'3h': 50, '10h': 150, '30h': 500}
    hours_map = {'3h': 3, '10h': 10, '30h': 30}
    
    price = prices.get(duration, 50)
    hours = hours_map.get(duration, 3)
    
    await state.set_state(SpamStates.waiting_payment_proof)
    await state.update_data(hours=hours, price=price, duration=duration)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="send_payment_proof")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")]
    ])
    
    await callback.message.edit_text(
        f"💰 Вы выбрали подписку на {hours} часов\n\n"
        f"💳 Стоимость: {price} звезд\n\n"
        "📱 Для оплаты:\n"
        "1. Откройте Telegram\n"
        "2. Перейдите в @wallet\n"
        "3. Выберите 'Отправить звезды'\n"
        "4. Получатель: @porox00\n"
        f"5. Сумма: {price} ⭐\n"
        "6. Отправьте\n\n"
        "После оплаты нажмите '✅ Я оплатил' и отправьте скриншот чека.",
        reply_markup=keyboard
    )

# Кнопка "Я оплатил"
@dp.callback_query(F.data == "send_payment_proof")
async def send_payment_proof_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📎 Теперь отправьте скриншот чека об оплате.\n\n"
        "Скриншот должен содержать:\n"
        "• Сумму перевода\n"
        "• Получателя (@porox00)\n"
        "• Дату и время\n\n"
        "Администратор проверит оплату и активирует подписку."
    )
    await state.set_state(SpamStates.waiting_payment_proof)

# Обработка скриншота оплаты
@dp.message(SpamStates.waiting_payment_proof)
async def process_payment_proof(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    if not data:
        await message.answer("❌ Ошибка данных. Начните заново.")
        await state.clear()
        return
    
    hours = data.get('hours', 3)
    price = data.get('price', 50)
    
    payments_db.insert({
        'user_id': user_id,
        'amount': price,
        'hours': hours,
        'status': 'pending',
        'proof_message_id': message.message_id,
        'date': datetime.now().isoformat()
    })
    
    admins = admins_db.all()
    for admin in admins:
        try:
            await bot.send_message(
                admin['user_id'],
                f"💰 Новый платеж ожидает проверки!\n\n"
                f"👤 Пользователь: @{message.from_user.username or 'нет username'}\n"
                f"🆔 ID: {user_id}\n"
                f"⏱️ Подписка: {hours} часов\n"
                f"💵 Сумма: {price} ⭐\n\n"
                f"Для активации подписки:\n"
                f"/activate {user_id} {hours}"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin['user_id']}: {e}")
    
    await message.answer(
        "✅ Скриншот отправлен на проверку!\n\n"
        "Администратор проверит оплату в течение 15-30 минут.\n"
        "Вы получите уведомление о активации подписки."
    )
    
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить статус", callback_data="check_my_subscription")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_user")]
    ])
    
    await message.answer("Выберите действие:", reply_markup=keyboard)

# Моя подписка
@dp.callback_query(F.data == "my_subscription")
async def my_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    sub_info = get_subscription_info(user_id)
    
    pending_payments = payments_db.search((Query().user_id == user_id) & (Query().status == 'pending'))
    
    text = f"📋 Информация о подписке:\n\n{sub_info}\n\n"
    
    if pending_payments:
        text += "⏳ У вас есть ожидающие платежи. Администратор проверит их в ближайшее время.\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="my_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_user")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)

# Контакты
@dp.callback_query(F.data == "contacts")
async def contacts_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Администратор", url="https://t.me/porox00")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_user")]
    ])
    
    await callback.message.edit_text(
        "📱 Контакты:\n\n"
        "По вопросам оплаты и подписок:\n"
        "👤 @porox00\n\n"
        "💳 Оплата принимается через:\n"
        "• @wallet\n"
        "• @send\n"
        "• Русские карты\n"
        "• Украинские карты",
        reply_markup=keyboard
    )

# Как отправить звезды
@dp.callback_query(F.data == "how_to_send_stars")
async def how_to_send_stars_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_user")]
    ])
    
    await callback.message.edit_text(
        "💎 Как отправить звезды:\n\n"
        "1. Откройте Telegram\n"
        "2. Напишите @wallet\n"
        "3. Выберите 'Отправить звезды'\n"
        "4. Введите сумму (50, 150 или 500 ⭐)\n"
        "5. Получатель: @porox00\n"
        "6. Подтвердите отправку\n\n"
        "📸 После оплаты сделайте скриншот чека и отправьте его боту.",
        reply_markup=keyboard
    )

# Отмена платежа
@dp.callback_query(F.data == "cancel_payment")
async def cancel_payment_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Оплата отменена.")
    await asyncio.sleep(2)
    await cmd_start(callback.message)

# Кнопка "Назад" для пользователей
@dp.callback_query(F.data == "back_to_user")
async def back_to_user_callback(callback: types.CallbackQuery):
    await cmd_start(callback.message)

# Кнопка "Как купить"
@dp.callback_query(F.data == "how_to_buy")
async def how_to_buy_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_user")]
    ])
    
    await callback.message.edit_text(
        "🛒 Как купить подписку:\n\n"
        "1. Нажмите 'Купить подписку'\n"
        "2. Выберите длительность\n"
        "3. Оплатите звездами через @wallet\n"
        "4. Отправьте скриншот чека боту\n"
        "5. Дождитесь активации администратором\n\n"
        "💎 Стоимость:\n"
        "• 3 часа - 50 ⭐\n"
        "• 10 часов - 150 ⭐\n"
        "• 30 часов - 500 ⭐",
        reply_markup=keyboard
    )

# Проверить мою подписку
@dp.callback_query(F.data == "check_my_subscription")
async def check_my_subscription_callback(callback: types.CallbackQuery):
    await my_subscription_callback(callback)

# Запуск рассылки
@dp.callback_query(F.data == "start_spam")
async def start_spam_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    global is_spam_active
    
    accounts = accounts_db.all()
    if not accounts:
        await callback.answer("❌ Нет добавленных аккаунтов")
        return
    
    current_account_id = settings_db.get(Query().name == 'current_account')['value']
    if current_account_id == '0':
        await callback.answer("❌ Не выбран аккаунт для рассылки")
        return
    
    chats = chats_db.all()
    if not chats:
        await callback.answer("❌ Нет чатов для рассылки")
        return
    
    if is_spam_active:
        await callback.answer("⚠️ Рассылка уже активна")
        return
    
    is_spam_active = True
    settings_db.update({'value': '1'}, Query().name == 'active')
    
    asyncio.create_task(run_spam())
    await callback.answer("✅ Рассылка запущена")
    await status_callback(callback)

# Остановка рассылки
@dp.callback_query(F.data == "stop_spam")
async def stop_spam_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    global is_spam_active
    
    if not is_spam_active:
        await callback.answer("⚠️ Рассылка не активна")
        return
    
    is_spam_active = False
    settings_db.update({'value': '0'}, Query().name == 'active')
    await callback.answer("⏹️ Рассылка остановлена")
    await status_callback(callback)

# Редактирование текста
@dp.callback_query(F.data == "edit_text")
async def edit_text_callback(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    await state.set_state(SpamStates.waiting_message)
    await callback.message.edit_text("Отправьте новый текст для рассылки:")

# Сохранение текста
@dp.message(SpamStates.waiting_message)
async def save_message(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    settings_db.update({'value': message.text}, Query().name == 'message')
    await message.answer("✅ Текст сохранен!")
    await state.clear()
    await cmd_start(message)

# Редактирование интервала
@dp.callback_query(F.data == "edit_interval")
async def edit_interval_callback(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    await state.set_state(SpamStates.waiting_interval)
    await callback.message.edit_text("Введите интервал между сообщениями в секундах:")

@dp.message(SpamStates.waiting_interval)
async def save_interval(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        interval = int(message.text)
        if interval < 5:
            interval = 5
        settings_db.update({'value': str(interval)}, Query().name == 'interval')
        await message.answer(f"✅ Интервал установлен: {interval} сек")
    except:
        await message.answer("❌ Введите число!")
        return
    
    await state.clear()
    await cmd_start(message)

# Редактирование паузы
@dp.callback_query(F.data == "edit_pause")
async def edit_pause_callback(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    await state.set_state(SpamStates.waiting_pause)
    await callback.message.edit_text("Введите паузу между циклами рассылки в секундах:")

@dp.message(SpamStates.waiting_pause)
async def save_pause(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        pause = int(message.text)
        if pause < 60:
            pause = 60
        settings_db.update({'value': str(pause)}, Query().name == 'pause')
        await message.answer(f"✅ Пауза установлена: {pause} сек")
    except:
        await message.answer("❌ Введите число!")
        return
    
    await state.clear()
    await cmd_start(message)

# Функция рассылки
async def run_spam():
    global is_spam_active
    
    while is_spam_active:
        try:
            current_account_id = settings_db.get(Query().name == 'current_account')['value']
            account = accounts_db.get(Query().id == int(current_account_id))
            
            if not account:
                logger.error("❌ Текущий аккаунт не найден")
                is_spam_active = False
                settings_db.update({'value': '0'}, Query().name == 'active')
                break
            
            client = TelegramClient(
                account['session_name'],
                int(account['api_id']),
                account['api_hash']
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"❌ Аккаунт {account['phone']} не авторизован")
                await client.disconnect()
                await asyncio.sleep(60)
                continue
            
            message_text = settings_db.get(Query().name == 'message')['value']
            interval = int(settings_db.get(Query().name == 'interval')['value'])
            pause = int(settings_db.get(Query().name == 'pause')['value'])
            
            chats = chats_db.all()
            success = 0
            failed = 0
            
            logger.info(f"🚀 Начинаем рассылку с аккаунта {account.get('name', account['phone'])}")
            
            for chat in chats:
                if not is_spam_active:
                    break
                    
                try:
                    await client.send_message(
                        chat['chat_id'],
                        message_text,
                        link_preview=False
                    )
                    success += 1
                    logger.info(f"✅ Отправлено в {chat.get('title', chat['chat_id'])}")
                    
                    if interval > 0:
                        await asyncio.sleep(interval)
                        
                except Exception as e:
                    failed += 1
                    logger.error(f"❌ Ошибка в {chat.get('title', chat['chat_id'])}: {e}")
            
            await client.disconnect()
            
            logger.info(f"📊 Цикл завершен: Успешно {success}, Ошибок {failed}")
            
            if is_spam_active and pause > 0:
                logger.info(f"⏸️ Пауза {pause} сек до следующего цикла")
                await asyncio.sleep(pause)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в основном цикле: {e}")
            await asyncio.sleep(60)

# Запуск бота
async def main():
    print("=" * 50)
    print("🤖 Бот запускается...")
    print("=" * 50)
    print("ВАЖНО:")
    print(f"1. Главный администратор: {MAIN_ADMIN_ID}")
    print("2. Канал для подписки: @rassilka_doxsnul")
    print("3. Оплата звездами на: @porox00")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
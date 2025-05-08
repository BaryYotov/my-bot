import logging
import os
import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters.callback_data import CallbackData
from aiogram.enums import ContentType, ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
APP_PORT = int(os.getenv("PORT", "10000"))

# === Инициализация ===
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

logging.basicConfig(level=logging.INFO)

# === CallbackData ===
class ReplyCallbackFactory(CallbackData, prefix="reply"):
    user_id: int

# === Состояние FSM ===
class ReplyToUser(StatesGroup):
    waiting_for_reply = State()

# === Кнопка "Ответить" ===
def reply_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[ 
        [InlineKeyboardButton(
            text="Ответить",
            callback_data=ReplyCallbackFactory(user_id=user_id).pack()
        )]
    ])

# === Приветствие ===
@router.message(CommandStart())
async def start_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        return
    photo = InputFile("welcome_image.jpg")
    caption = (
        "Добро пожаловать в магическое пространство Таро и Рун!\n\n"
        "Меня зовут Бари, я Тарунолог...\n\n"
        "С любовью и светом!\n— Тарунолог Бари"
    )
    await message.answer_photo(photo, caption=caption)

# === Пересылка сообщений админу ===
@router.message()
async def forward_to_admin(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        return

    # Подтверждение пользователю
    photo = InputFile("response_image.jpg")
    await message.answer_photo(photo, caption="Благодарю вас за обращение! Расклад будет готов в течение 24 часов.")

    # Пересылка админу
    user = message.from_user
    header = f"Сообщение от @{user.username or 'без ника'} (ID: {user.id})"
    markup = reply_keyboard(user.id)

    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"{header}\n\n{message.caption or ''}", reply_markup=markup)
    elif message.video:
        await bot.send_video(ADMIN_ID, message.video.file_id, caption=f"{header}\n\n{message.caption or ''}", reply_markup=markup)
    elif message.text:
        await bot.send_message(ADMIN_ID, f"{header}\n\n{message.text}", reply_markup=markup)
    else:
        await bot.send_message(ADMIN_ID, f"{header}\n\n[неподдерживаемый тип сообщения]", reply_markup=markup)

# === Обработка кнопки "Ответить" ===
@router.callback_query(ReplyCallbackFactory.filter())
async def handle_reply_callback(callback: CallbackQuery, callback_data: ReplyCallbackFactory, state: FSMContext):
    user_id = callback_data.user_id
    await state.set_state(ReplyToUser.waiting_for_reply)
    await state.update_data(target_user_id=user_id)
    await callback.message.answer(f"Введите сообщение для пользователя ID: {user_id}")
    await callback.answer()

# === Ответ админа пользователю ===
@router.message(ReplyToUser.waiting_for_reply, F.from_user.id == ADMIN_ID)
async def send_reply_to_user(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("target_user_id")

    try:
        if message.text:
            await bot.send_message(user_id, message.text)
        elif message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or '')
        elif message.video:
            await bot.send_video(user_id, message.video.file_id, caption=message.caption or '')
        else:
            await message.reply("❌ Неподдерживаемый тип сообщения.")
            return

        await message.reply("✅ Ответ отправлен.")
        await state.clear()
    except Exception as e:
        await message.reply(f"❌ Ошибка при отправке: {e}")

# === Хуки для запуска и остановки ===
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logging.info("🛑 Webhook удалён")

# === Запуск бота через webhook ===
async def main():
    # Хуки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # aiohttp-приложение
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", APP_PORT)
    await site.start()
    logging.info(f"🚀 Сервер запущен на порту {APP_PORT}")

    # Запуск фоновой задачи
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

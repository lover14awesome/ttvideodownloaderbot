import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
import json
import os
from flask import Flask
import threading
import asyncio

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [1341404143]  # замените на свой Telegram ID
SETTINGS_FILE = "settings.json"
flask_app = Flask(__name__)


@flask_app.route('/')
def home():
    return 'Bot is running!'


def load_settings():
    try:
        with open("settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}

    # Устанавливаем значения по умолчанию
    settings.setdefault("caption",
                        "<a href='https://t.me/video4k_downloader_bot'>🔗 Скачано из TikTok Video Downloader</a>")
    settings.setdefault("requirements_enabled", False)
    settings.setdefault("channels", [])

    return settings


def save_settings(settings):
    with open("settings.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я помогу тебе скачать любое видео из TikTok *без водяного знака*.\n\n"
        "Просто отправь мне ссылку на видео — и получишь файл без лишнего мусора!\n\n"
        "📲 Не забудь поделиться ботом с друзьями! 😉",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    settings = load_settings()
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text("❌ Это не похоже на ссылку.")
        return

    # 👇 Добавляем сюда проверку на TikTok
    if "tiktok.com" not in url and "vm.tiktok.com" not in url:
        await update.message.reply_text("❌ Пожалуйста, отправьте ссылку на TikTok.")
        return

    if settings.get("requirements_enabled"):
        user_id = update.effective_user.id
        channel_list = settings.get("required_channels", [])
        for channel_url in channel_list:
            channel = channel_url
            if channel.startswith("https://t.me/"):
                channel = "@" + channel.split("/")[-1]

            try:
                member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
                if member.status not in ["member", "administrator", "creator"]:
                    raise Exception()
            except Exception:
                await update.message.reply_text(
                    f"❗ Перед получением видео, подпишись на канал:\n" + "\n".join(channel_list),
                    parse_mode=ParseMode.HTML
                )
                return

    await update.message.reply_text("⏳ Скачиваю видео...")

    api_url = f"https://tikwm.com/api/?url={url}"
    response = requests.get(api_url).json()

    if not response.get("data") or not response["data"].get("play"):
        await update.message.reply_text("❌ Не удалось получить видео. Проверь ссылку.")
        return

    video_url = response["data"]["play"]
    try:
        video_bytes = requests.get(video_url).content
        await update.message.reply_video(
            video=video_bytes,
            caption=settings.get("caption", ""),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при отправке видео:\n{str(e)}")


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    settings = load_settings()
    caption = settings.get("caption", "Нет")
    enabled = settings.get("requirements_enabled", False)
    channels = settings.get("required_channels", [])
    channel_list = "\n".join([f"- {ch}" for ch in channels]) if channels else "Нет"

    msg = (
        "🛠 Админ-панель:\n"
        f"📄 Текущая подпись: {caption}\n"
        f"✅ Условия включены: {enabled}\n"
        f"📢 Каналы:\n{channel_list}\n\n"
        "/set_caption &lt;текст&gt; — изменить подпись под видео\n"
        "/toggle_reqs — включить/выключить условия\n"
        "/add_channel &lt;ссылка&gt; — добавить канал\n"
        "/remove_channel &lt;ссылка&gt; — удалить канал"
    )

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def set_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text("⚠️ Укажите новую подпись после команды.")
        return
    settings = load_settings()
    settings["caption"] = text
    save_settings(settings)
    await update.message.reply_text("✅ Подпись обновлена.")


async def toggle_requirements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    settings = load_settings()
    settings["requirements_enabled"] = not settings.get("requirements_enabled", False)
    save_settings(settings)
    state = "включены" if settings["requirements_enabled"] else "выключены"
    await update.message.reply_text(f"✅ Условия теперь {state}.")


async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text("⚠️ Укажите ссылку на канал после команды.")
        return
    settings = load_settings()
    if text not in settings.get("required_channels", []):
        settings.setdefault("required_channels", []).append(text)
        save_settings(settings)
        await update.message.reply_text("✅ Канал добавлен.")
    else:
        await update.message.reply_text("⚠️ Этот канал уже есть в списке.")


async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text("⚠️ Укажите ссылку на канал после команды.")
        return
    settings = load_settings()
    if text in settings.get("required_channels", []):
        settings["required_channels"].remove(text)
        save_settings(settings)
        await update.message.reply_text("✅ Канал удалён.")
    else:
        await update.message.reply_text("⚠️ Такого канала нет в списке.")


async def start_bot():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("set_caption", set_caption))
    application.add_handler(CommandHandler("toggle_reqs", toggle_requirements))
    application.add_handler(CommandHandler("add_channel", add_channel))
    application.add_handler(CommandHandler("remove_channel", remove_channel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    await application.bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот запущен!")
    await application.run_polling()

if __name__ == "__main__":
    import multiprocessing

    def flask_thread():
        flask_app.run(host="0.0.0.0", port=10000)

    def bot_process():
        asyncio.run(start_bot())

    # Запускаем Flask в отдельном процессе
    flask = multiprocessing.Process(target=flask_thread)
    flask.start()

    # Запускаем бота в основном потоке
    bot_process()

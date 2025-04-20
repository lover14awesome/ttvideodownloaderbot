import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from telegram.ext import MessageHandler, filters
from telegram.constants import ParseMode
from telegram import InputMediaPhoto
import re
from bs4 import BeautifulSoup



BOT_TOKEN = "8110680619:AAFLPLXdaqp1ymm-mAwm5Fz1Tp1Xgp42Wm4"
ADMIN_IDS = [1341404143]  # замените на свой Telegram ID
SETTINGS_FILE = "settings.json"

def load_settings():
    try:
        with open("settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}

    # Устанавливаем значения по умолчанию
    settings.setdefault("caption", "<a href='https://t.me/ttclip_bot'>🔗 Скачано из TikTok Video Downloader</a>")
    settings.setdefault("requirements_enabled", False)
    settings.setdefault("channels", [])

    return settings

def save_settings(settings):
    with open("settings.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

USERS_FILE = "users.json"

def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я помогу тебе скачать любое видео из TikTok *без водяного знака*.\n\n"
        "Просто отправь мне ссылку на видео — и получишь файл без лишнего мусора!\n\n"
        "📲 Не забудь поделиться ботом с друзьями! 😉",
        parse_mode=ParseMode.MARKDOWN
    )
    save_user(update.effective_user.id)

async def download_and_send_video(url, user_id, reply_video_func, reply_text_func, reply_photo_func=None, bot=None, chat_id=None):
    settings = load_settings()
    await reply_text_func("⏳ Пробую скачать видео...")

    caption = settings.get("caption", "")
    success = False

    ### --- 1. Tikwm API ---
    try:
        response = requests.get(f"https://tikwm.com/api/?url={url}", timeout=10).json()
        data = response.get("data", {})

        if data.get("play"):
            video_bytes = requests.get(data["play"]).content
            await reply_video_func(video=video_bytes, caption=caption, parse_mode=ParseMode.HTML)
            success = True
            return
        elif data.get("images"):
            media_group = []
            for idx, img_url in enumerate(data["images"]):
                img_bytes = requests.get(img_url).content
                media = InputMediaPhoto(img_bytes, caption=caption if idx == 0 else None, parse_mode=ParseMode.HTML)
                media_group.append(media)
            await bot.send_media_group(chat_id=chat_id, media=media_group)
            success = True
            return
    except Exception as e:
        print(f"[tikwm] ошибка: {e}")

    ### --- 2. SaveFrom.net (через sfrom API) ---
    try:
        sf_response = requests.get(f"https://api.savetik.cc/api/download?url={url}", timeout=10).json()
        if "video" in sf_response and sf_response["video"].get("url"):
            video_url = sf_response["video"]["url"]
            video_bytes = requests.get(video_url).content
            await reply_video_func(video=video_bytes, caption=caption, parse_mode=ParseMode.HTML)
            success = True
            return
    except Exception as e:
        print(f"[savefrom] ошибка: {e}")

    ### --- 3. Snaptik (парсим HTML) ---
    try:
        page = requests.get(f"https://snaptik.app/ru#url={url}", timeout=10).text
        soup = BeautifulSoup(page, "html.parser")
        links = soup.select("a[href*='https://v16m.tiktokcdn.com/']")
        if links:
            video_url = links[0]['href']
            video_bytes = requests.get(video_url).content
            await reply_video_func(video=video_bytes, caption=caption, parse_mode=ParseMode.HTML)
            success = True
            return
    except Exception as e:
        print(f"[snaptik] ошибка: {e}")

    ### --- Не удалось ---
    if not success:
        await reply_text_func("❌ Не удалось скачать видео. Попробуйте другую ссылку или чуть позже.")


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    save_user(update.effective_user.id)
    settings = load_settings()
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text("❌ Это не похоже на ссылку.")
        return

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
                context.user_data["pending_url"] = url

                buttons = [
                    [InlineKeyboardButton("🔔 Подписаться", url=link)]
                    for link in channel_list
                ]
                buttons.append([InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")])

                await update.message.reply_text(
                    "❗ Перед получением видео, подпишись на канал(ы):",
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode=ParseMode.HTML
                )
                return

    await download_and_send_video(
        url=url,
        user_id=update.effective_user.id,
        reply_video_func=update.message.reply_video,
        reply_text_func=update.message.reply_text,
        bot=context.bot,
        chat_id=update.effective_chat.id
    )


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


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    settings = load_settings()
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
            await query.edit_message_text(
                "❌ Вы ещё не подписались на все каналы. Подпишитесь и нажмите \"Проверить подписку\" снова.",
                reply_markup=query.message.reply_markup
            )
            return

    url = context.user_data.get("pending_url")
    if not url:
        await query.edit_message_text("❌ Не удалось найти ссылку. Отправьте её заново.")
        return

    await query.edit_message_text("✅ Подписка проверена. Загружаю видео...")

    await download_and_send_video(
        url=url,
        user_id=user_id,
        reply_video_func=query.message.reply_video,
        reply_text_func=query.message.reply_text,
        bot=context.bot,
        chat_id=query.message.chat_id
    )


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

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    users = load_users()
    if not users:
        await update.message.reply_text("⚠️ Список пользователей пуст.")
        return

    msg = update.message
    text = ""
    raw_text = msg.text or msg.caption or ""
    text = raw_text.replace("/broadcast", "", 1).strip()

    count = 0

    for user_id in users:
        try:
            if msg.photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=msg.photo[-1].file_id,
                    caption=text,
                    parse_mode=ParseMode.HTML
                )
            elif msg.video:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=msg.video.file_id,
                    caption=text,
                    parse_mode=ParseMode.HTML
                )
            elif msg.document:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=msg.document.file_id,
                    caption=text,
                    parse_mode=ParseMode.HTML
                )
            elif text:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
            else:
                continue
            count += 1
        except Exception as e:
            print(f"Не удалось отправить сообщение {user_id}: {e}")

    await update.message.reply_text(f"✅ Рассылка завершена. Доставлено: {count}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    users = load_users()
    await update.message.reply_text(f"📊 Пользователей: {len(users)}")


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


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("set_caption", set_caption))
    app.add_handler(CommandHandler("toggle_reqs", toggle_requirements))
    app.add_handler(CommandHandler("add_channel", add_channel))
    app.add_handler(CommandHandler("remove_channel", remove_channel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(
        filters.ALL & filters.User(ADMIN_IDS) & filters.CaptionRegex(r'^/broadcast'),
        broadcast
    ))
    app.add_handler(CommandHandler("stats", stats))
    print("Бот запущен!")
    app.run_polling()

import logging
import aiohttp
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- КОНСТАНТЫ ---
BOT_TOKEN = "8448137442:AAE4w5JkjBy8j-NhzLeBc3y-kYFLetNf3aA"
TMDB_API_KEY = "dbded6f86cceb56ff734bef7a5fdf792"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
DB_PATH = "subscriptions.db"

# --- ЛОГИ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

movies_cache = {}  # movie_id -> movie_data


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def init_db():
    """Создание таблиц, если ещё нет"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER,
                type TEXT,
                value TEXT
            )"""
        )
        await db.commit()


async def get_movie_info(query: str):
    """Запрос к TMDb по названию фильма/сериала"""
    endpoint = f"{TMDB_BASE_URL}/search/multi"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "ru-RU",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("results"):
                    result = data["results"][0]
                    movies_cache[result["id"]] = result
                    return result
    return None


def format_movie_message(movie: dict) -> str:
    """Форматирование карточки фильма/сериала"""
    title = movie.get("title") or movie.get("name")
    release_date = movie.get("release_date") or movie.get("first_air_date")
    poster_path = movie.get("poster_path")
    vote_average = movie.get("vote_average")

    message = "<b>🌟 Найдено:</b>\n\n"
    message += f"<b>Название:</b> {title}\n"
    if release_date:
        message += f"<b>Дата выхода:</b> {release_date}\n"
    if vote_average:
        message += f"<b>Оценка (TMDb):</b> {vote_average:.1f}\n"
    if poster_path:
        message += f"https://image.tmdb.org/t/p/w500{poster_path}"

    return message


# --- ХЕНДЛЕРЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 🎬\n\n"
        "Я могу искать фильмы и сериалы в TMDb и подписывать вас на обновления.\n\n"
        "Используйте команды:\n"
        "<code>/search название</code> — поиск фильма/сериала\n"
        "<code>/subscribe_genre жанр</code> — подписка на жанр (например horror)\n"
        "<code>/subscribe_provider netflix</code> — подписка на дистрибьютора\n",
        parse_mode="HTML",
    )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text(
            "❗ Укажите название фильма или сериала.\n\nПример:\n<code>/search Орудия</code>",
            parse_mode="HTML",
        )
        return

    movie = await get_movie_info(query)
    if movie:
        message = format_movie_message(movie)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔔 Подписаться", callback_data=f"subscribe_{movie['id']}"
                    )
                ]
            ]
        )

        await update.message.reply_text(
            message, parse_mode="HTML", reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            f"😕 Ничего не найдено по запросу <code>{query}</code>", parse_mode="HTML"
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка inline-кнопок"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data.startswith("subscribe_"):
        movie_id = int(data.split("_")[1])
        movie = movies_cache.get(movie_id)

        if not movie:
            await query.edit_message_text("⚠️ Ошибка: фильм не найден в кеше.")
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO subscriptions (user_id, type, value) VALUES (?, ?, ?)",
                (user_id, "movie", str(movie_id)),
            )
            await db.commit()

        await query.edit_message_text(
            f"✅ Вы подписались на: <b>{movie.get('title') or movie.get('name')}</b>",
            parse_mode="HTML",
        )


async def subscribe_genre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на жанр"""
    if not context.args:
        await update.message.reply_text("Укажите жанр, например: /subscribe_genre horror")
        return
    genre = context.args[0].lower()
    user_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO subscriptions (user_id, type, value) VALUES (?, ?, ?)",
            (user_id, "genre", genre),
        )
        await db.commit()
    await update.message.reply_text(f"✅ Подписка на жанр <b>{genre}</b> оформлена!", parse_mode="HTML")


async def subscribe_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на стриминг"""
    if not context.args:
        await update.message.reply_text("Укажите провайдера, например: /subscribe_provider netflix")
        return
    provider = context.args[0].lower()
    user_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO subscriptions (user_id, type, value) VALUES (?, ?, ?)",
            (user_id, "provider", provider),
        )
        await db.commit()
    await update.message.reply_text(f"✅ Подписка на дистрибьютора <b>{provider}</b> оформлена!", parse_mode="HTML")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❗ Неизвестная команда. Используйте <code>/start</code> или <code>/search</code>",
        parse_mode="HTML",
    )


# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("subscribe_genre", subscribe_genre))
    app.add_handler(CommandHandler("subscribe_provider", subscribe_provider))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    scheduler = AsyncIOScheduler()

    async def on_startup(_):
        await init_db()
        scheduler.start()  # теперь запускаем внутри event loop

    app.post_init = on_startup
    app.run_polling()

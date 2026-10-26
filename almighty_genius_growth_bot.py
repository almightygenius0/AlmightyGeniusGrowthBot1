import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Set these as environment variables in your hosting dashboard.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@updatearena010").strip()
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/updatearena010").strip()
DB_PATH = os.getenv("DB_PATH", "growth_bot.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                referred_by INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def save_user(user_id, username, first_name, referrer_id=None):
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing:
            return False

        # Do not allow self-referrals.
        if referrer_id == user_id:
            referrer_id = None

        # Only credit a referral if the referrer is already known.
        if referrer_id is not None:
            known = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?", (referrer_id,)
            ).fetchone()
            if not known:
                referrer_id = None

        conn.execute(
            "INSERT INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)",
            (user_id, username or "", first_name or "", referrer_id),
        )
        if referrer_id is not None:
            conn.execute(
                "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referrer_id, user_id),
            )
        return True


def referral_count(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else 0


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    referrer_id = None
    if context.args:
        payload = context.args[0]
        if payload.startswith("ref_"):
            try:
                referrer_id = int(payload[4:])
            except ValueError:
                referrer_id = None

    is_new = save_user(user.id, user.username, user.first_name, referrer_id)

    keyboard = [
        [InlineKeyboardButton("📢 Join Update Arena", url=CHANNEL_LINK)],
        [InlineKeyboardButton("🔎 Check channel membership", callback_data="check_membership")],
        [InlineKeyboardButton("🔗 My referral link", callback_data="my_referral")],
    ]
    text = (
        f"👑 Welcome, {user.first_name or 'friend'}!\n\n"
        "Welcome to Almighty Genius Growth Bot.\n"
        "Use the buttons below to join Update Arena and invite friends.\n\n"
        "📢 Channel: " + CHANNEL_LINK
    )
    if is_new and referrer_id and referrer_id != user.id:
        text += "\n\n🎉 You joined using a referral link!"

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "my_referral":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start=ref_{user_id}"
        count = referral_count(user_id)
        await query.message.reply_text(
            f"🔗 Your personal referral link:\n{link}\n\n"
            f"👥 Referrals recorded: {count}\n\n"
            "Ask friends to open the link and press Start. Only new users are counted."
        )

    elif query.data == "check_membership":
        try:
            member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
            if member.status in ("member", "administrator", "creator"):
                await query.message.reply_text("✅ You're a member of Update Arena. Thanks for joining!")
            else:
                await query.message.reply_text(
                    "❌ I can't see that you've joined yet. Join the channel first, then check again.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📢 Join Update Arena", url=CHANNEL_LINK)],
                        [InlineKeyboardButton("🔄 Check again", callback_data="check_membership")],
                    ]),
                )
        except Exception:
            logger.exception("Membership check failed")
            await query.message.reply_text(
                "I couldn't verify membership. Please ask the channel owner to add this bot as an administrator "
                "in Update Arena, then try again."
            )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = referral_count(user_id)
    await update.message.reply_text(f"👥 Your recorded referrals: {count}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/start — Open the bot\n"
        "/referrals — See your referral count\n"
        "/help — Show this help\n\n"
        "Use the buttons in /start to get your referral link or check channel membership."
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it as an environment variable; do not put it in public code.")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("referrals", stats))
    app.add_handler(CommandHandler("help", help_command))
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("Bot is running. Keep the token private.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

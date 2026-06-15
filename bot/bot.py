import os
import logging
import sys
from datetime import datetime

from flask import Flask, request
import telebot
from telebot import types
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────── Logging ───────────────────────────

LOG_FILE = os.getenv("LOG_FILE", "bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)

# ─────────────────────────── Config ───────────────────────────

BOT_TOKEN            = os.getenv("BOT_TOKEN")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
WEBHOOK_URL          = os.getenv("WEBHOOK_URL")

SHEET_NAME        = "subtitle_jobs"
USERS_SHEET       = "users"
JOBS_SHEET        = "jobs"
REQUIRED_CHANNELS = ["@hoosh_code_channel"]

DEFAULT_COINS  = 10
VIDEO_COST     = 5
INVITER_COINS  = 5
INVITEE_COINS  = 3

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Check your .env file.")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is not set. Check your .env file.")

# ─────────────────────────── Google Sheets ───────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc    = gspread.authorize(creds)
sheet = gc.open(SHEET_NAME)

try:
    users_ws = sheet.worksheet(USERS_SHEET)
except gspread.WorksheetNotFound:
    users_ws = sheet.add_worksheet(title=USERS_SHEET, rows="1000", cols="6")
    users_ws.append_row(["chat_id", "username", "coins", "invite_code", "inviter_id", "join_date"])

try:
    jobs_ws = sheet.worksheet(JOBS_SHEET)
except gspread.WorksheetNotFound:
    jobs_ws = sheet.add_worksheet(title=JOBS_SHEET, rows="1000", cols="9")
    jobs_ws.append_row(["job_id", "chat_id", "message_id", "file_id", "status",
                         "video_path", "srt_path", "output_path", "created_at"])

# ─────────────────────────── Bot & App ───────────────────────────

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)


# ─────────────────────────── Helpers ───────────────────────────

def get_user(chat_id):
    records = users_ws.get_all_records()
    for row in records:
        if str(row["chat_id"]) == str(chat_id):
            return row
    return None


def update_user_coins(chat_id, coins):
    cell = users_ws.find(str(chat_id), in_column=1)
    if cell:
        users_ws.update_cell(cell.row, 3, coins)


def add_user(chat_id, username, inviter_id=None):
    """Register a new user with base coins + referral bonus if applicable."""
    new_invite_code = str(chat_id)
    initial_coins   = DEFAULT_COINS + (INVITEE_COINS if inviter_id else 0)
    users_ws.append_row([
        str(chat_id),
        username or "",
        initial_coins,
        new_invite_code,
        str(inviter_id) if inviter_id else "",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ])
    logging.info(
        f"ADD_USER: chat_id={chat_id} username={username} "
        f"coins={initial_coins} inviter_id={inviter_id}"
    )
    return initial_coins, new_invite_code


def add_coins(chat_id, amount):
    user = get_user(chat_id)
    if user:
        new = int(user["coins"]) + amount
        update_user_coins(chat_id, new)
        return new
    return None


def deduct_coins(chat_id, amount):
    user = get_user(chat_id)
    if user and int(user["coins"]) >= amount:
        new = int(user["coins"]) - amount
        update_user_coins(chat_id, new)
        return True, new
    return False, int(user["coins"]) if user else 0


def find_inviter(invite_code):
    if not invite_code:
        return None
    all_users = users_ws.get_all_records()
    for u in all_users:
        if str(u.get("invite_code", "")) == str(invite_code):
            return str(u["chat_id"])
    return None


def is_member(channel, user_id):
    try:
        chat   = bot.get_chat(channel)
        member = bot.get_chat_member(chat.id, user_id)
        logging.info(
            f"CHANNEL={channel} CHAT_ID={chat.id} "
            f"USER={user_id} STATUS={member.status}"
        )
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.error(f"MEMBERSHIP_ERROR | channel={channel} | user={user_id} | error={e}")
        return False


def check_all_channels(user_id):
    return [ch for ch in REQUIRED_CHANNELS if not is_member(ch, user_id)]


def generate_invite_link(invite_code):
    return f"https://t.me/{bot.get_me().username}?start={invite_code}"


# ─────────────────────────── /start ───────────────────────────

@bot.message_handler(commands=["start"])
def start_handler(message):
    chat_id = message.chat.id
    logging.info(f"start_handler called: {chat_id}")
    try:
        args        = message.text.split()
        invite_code = args[1].strip() if len(args) > 1 else None
        logging.info(f"INVITE_CODE received: '{invite_code}' for user {chat_id}")

        user = get_user(chat_id)

        if not user:
            inviter_id = None

            if invite_code:
                if str(invite_code) == str(chat_id):
                    logging.warning(f"SELF_INVITE blocked: {chat_id}")
                    invite_code = None
                else:
                    inviter_id = find_inviter(invite_code)
                    logging.info(f"INVITER found: {inviter_id} for invite_code={invite_code}")

            coins, user_invite_code = add_user(
                chat_id,
                message.from_user.username,
                inviter_id,
            )

            if inviter_id:
                new_inviter_coins = add_coins(inviter_id, INVITER_COINS)
                logging.info(
                    f"INVITER_REWARD: inviter={inviter_id} "
                    f"+{INVITER_COINS} coins → total={new_inviter_coins}"
                )
                try:
                    bot.send_message(
                        inviter_id,
                        f"🎉✨ یه نفر با لینک دعوت شما اومد! "
                        f"{INVITER_COINS} سکه به حسابتون اضافه شد. ✨🎉",
                    )
                except Exception as e:
                    logging.warning(f"Could not notify inviter {inviter_id}: {e}")
        else:
            logging.info(f"EXISTING_USER: {chat_id}, invite_code ignored")
            coins           = user["coins"]
            user_invite_code = user.get("invite_code", str(chat_id))

        missing = check_all_channels(chat_id)
        if missing:
            markup = types.InlineKeyboardMarkup()
            for ch in missing:
                markup.add(types.InlineKeyboardButton(
                    f"عضویت در {ch}",
                    url=f"https://t.me/{ch.replace('@', '')}",
                ))
            markup.add(types.InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership"))
            bot.send_message(
                chat_id,
                "⚠️ برای استفاده از ربات باید عضو کانال‌های زیر شوید:",
                reply_markup=markup,
            )
            return

        show_main_menu(chat_id, coins, user_invite_code)
        logging.info(f"show_main_menu OK for {chat_id}")

    except Exception as e:
        logging.error(f"start_handler FAILED for {chat_id}: {e}", exc_info=True)


# ─────────────────────────── Menu ───────────────────────────

def show_main_menu(chat_id, coins, invite_code):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🎥 ارسال ویدیو"),
        types.KeyboardButton("📊 تاریخچه پردازش‌ها"),
        types.KeyboardButton("💰 موجودی سکه"),
        types.KeyboardButton("📞 پشتیبانی"),
        types.KeyboardButton("🔗 لینک دعوت"),
    )
    start_text = (
        "🎬✨ **به SubFa AI خوش آمدید** ✨🎬\n\n"
        "🤖 **ربات هوشمند زیرنویس فارسی**\n"
        "با قدرت هوش مصنوعی، برای ویدیوهات زیرنویس حرفه‌ای بساز!\n\n"
        "🔥 **چرا SubFa AI؟**\n"
        "✅ زیرنویس دقیق و استاندارد فارسی\n"
        "✅ پشتیبانی از ویدیوهای چندزبانه\n"
        "✅ آماده برای آپلود مستقیم در یوتیوب، اینستاگرام، آپارات\n"
        "✅ سرعت بالا و کیفیت عالی\n\n"
        f"💰 **سکه شما**: `{coins}` سکه\n"
        f"🎯 **هزینه هر پردازش**: `{VIDEO_COST}` سکه\n\n"
        "👇 **همین الان ویدیوت رو بفرست و حرفه‌ای شو!** 👇"
    )
    bot.send_message(chat_id, start_text, parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "check_membership")
def check_membership_callback(call):
    chat_id = call.message.chat.id
    if not check_all_channels(chat_id):
        bot.answer_callback_query(call.id, "✅ عضویت تأیید شد!")
        user = get_user(chat_id)
        coins = user["coins"] if user else DEFAULT_COINS
        inv   = user["invite_code"] if user else str(chat_id)
        show_main_menu(chat_id, coins, inv)
    else:
        bot.answer_callback_query(call.id, "❌ هنوز عضو همه کانال‌ها نشده‌اید!", show_alert=True)


# ─────────────────────────── Message Handlers ───────────────────────────

@bot.message_handler(func=lambda m: m.text == "🎥 ارسال ویدیو")
def send_video_prompt(message):
    chat_id = message.chat.id
    user    = get_user(chat_id)
    if not user or int(user["coins"]) < VIDEO_COST:
        bot.send_message(chat_id, "⛔️ موجودی سکه کافی نیست. با دعوت دوستان سکه بیشتری بگیرید!")
        return
    bot.send_message(
        chat_id,
        "📤 **ویدیوی خودت رو بفرست تا زیرنویس حرفه‌ای براش بسازم!** 🎬\n"
        "(فقط فرمت‌های MP4، AVI، MOV پشتیبانی می‌شه)",
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda m: m.text == "📊 تاریخچه پردازش‌ها")
def history(message):
    chat_id  = message.chat.id
    all_jobs = jobs_ws.get_all_records()
    user_jobs = [j for j in all_jobs if str(j["chat_id"]) == str(chat_id)]
    if not user_jobs:
        bot.send_message(
            chat_id,
            "📭 **هنوز هیچ ویدیویی پردازش نکردی!**\nبا دکمه 🎥 ارسال ویدیو شروع کن.",
            parse_mode="Markdown",
        )
        return
    text = "📋 **آخرین پردازش‌های تو:**\n\n"
    for j in user_jobs[-5:]:
        status_emoji = {"done": "✅", "processing": "⏳", "new": "🆕"}.get(j["status"], "❓")
        text += f"{status_emoji} `{j['created_at']}` → {j['status']}\n"
    bot.send_message(chat_id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "💰 موجودی سکه")
def coins_handler(message):
    user  = get_user(message.chat.id)
    coins = user["coins"] if user else DEFAULT_COINS
    bot.send_message(
        message.chat.id,
        f"💰 **سکه‌های تو:** `{coins}`\n🎯 هر ویدیو `{VIDEO_COST}` سکه هزینه داره.",
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda m: m.text == "📞 پشتیبانی")
def support(message):
    bot.send_message(
        message.chat.id,
        "📞 پشتیبانی SubFa AI\n\n❓ سوال داری؟ مشکل برخوردی؟\n"
        "👨‍💻 با پشتیبان ما در ارتباط باش:\n@supprot_subfa\n\n⏳ پاسخگویی کمتر از ۲۴ ساعت",
    )


@bot.message_handler(func=lambda m: m.text == "🔗 لینک دعوت")
def invite_link_handler(message):
    user = get_user(message.chat.id)
    code = user["invite_code"] if user else str(message.chat.id)
    link = generate_invite_link(code)
    text = (
        f"🔗 **لینک دعوت اختصاصی تو:**\n"
        f"`{link}`\n\n"
        f"🎁 **هر دوستی که بیاد:**\n"
        f"👉 تو `+{INVITER_COINS}` سکه میگیری\n"
        f"👉 اون `+{INVITEE_COINS}` سکه هدیه میگیره\n\n"
        f"💎 **هرچقدر دوست بیشتری دعوت کنی، سکه بیشتری داری!**\n"
        f"🚀 بدون سکه، بدون توقف!"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(content_types=["video"])
def video_handler(message):
    chat_id = message.chat.id
    user    = get_user(chat_id)
    if not user or int(user["coins"]) < VIDEO_COST:
        bot.send_message(chat_id, "⛔️ سکه کافی نیست.")
        return
    success, new_coins = deduct_coins(chat_id, VIDEO_COST)
    if not success:
        bot.send_message(chat_id, "خطا در کسر سکه.")
        return
    logging.info(f"video_handler: saving job for {chat_id}")
    try:
        job_id = int(datetime.now().timestamp())
        jobs_ws.append_row([
            job_id, str(chat_id), message.message_id, message.video.file_id,
            "new", "", "", "", datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ])
    except Exception as e:
        logging.error(f"jobs append FAILED: {e}")
        bot.send_message(chat_id, "خطا در ثبت ویدیو")
        return
    bot.send_message(
        chat_id,
        f"✅ **ویدیو با موفقیت ثبت شد!**\n"
        f"🎬 در حال آماده‌سازی زیرنویس...\n"
        f"💰 **سکه باقی‌مونده:** `{new_coins}`",
        parse_mode="Markdown",
    )


# ─────────────────────────── Webhook ───────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("utf-8")
        try:
            logging.info(f"RAW_UPDATE: {json_string[:300]}")
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
        except Exception as e:
            logging.error(f"WEBHOOK_ERROR: {e} | DATA: {json_string[:200]}")
        return "OK", 200
    return "Bad Request", 400


@app.route("/")
def home():
    return "Bot is running (Webhook mode)"


# ─────────────────────────── Startup ───────────────────────────

try:
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logging.info(f"Webhook set: {WEBHOOK_URL}")
except Exception as e:
    logging.error(f"Webhook error: {e}")

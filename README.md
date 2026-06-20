# 🎬 SubFa AI — Persian Subtitle Bot | ربات زیرنویس فارسی

A Telegram bot that automatically generates Persian (Farsi) subtitles for user-uploaded videos using AI speech recognition and translation.

ربات تلگرامی که به‌طور خودکار برای ویدیوهای ارسال‌شده توسط کاربران، زیرنویس فارسی تولید می‌کند.

---

## ✨ Features | ویژگی‌ها

- 🤖 AI-powered transcription with **faster-whisper**
- 🌐 Automatic translation to Persian with **deep-translator**
- 🎥 Subtitle rendering burned into video via **FFmpeg**
- 💰 Coin-based usage system with referral rewards
- 📊 Job tracking via **Google Sheets**
- 🔗 Invite link system (inviter +5 coins, invitee +3 coins)
- 🔒 Channel membership gate
- 📧 Email notification — after sending a video, the user is asked for their email; once the finished video is delivered on Telegram, an email is also sent letting them know it's ready

---

## 🏗️ Architecture

```
User sends video via Telegram
        │
        ▼
  [bot.py — Flask Webhook]
  • Validates coins
  • Saves job to Google Sheets
        │
        ▼
  [colab_pipeline.ipynb — Google Colab GPU]
  Stage 1 → Download video via Telethon
  Stage 2 → Extract audio (FFmpeg)
  Stage 3 → Transcribe + Translate (Whisper + deep-translator)
  Stage 4 → Render subtitles into video (FFmpeg)
  Stage 5 → Send result back to user via Telegram
  Stage 6 → Cleanup temp files
```

---

## 🚀 Setup | راه‌اندازی

### 1. Clone & Install

```bash
git clone https://github.com/thealirezadev/subfa-ai
cd subfa-ai
pip install -r requirements.txt
```

### 2. Configure Secrets

```bash
cp .env.example .env
# Edit .env and fill in your credentials
```

Required values in `.env`:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram Bot token from [@BotFather](https://t.me/BotFather) |
| `API_ID` | Telegram App ID from [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | Telegram App hash from [my.telegram.org](https://my.telegram.org) |
| `WEBHOOK_URL` | Your public URL (e.g. `https://yourname.pythonanywhere.com/webhook`) |
| `SERVICE_ACCOUNT_FILE` | Path to your Google service account JSON |

### 3. Google Sheets Setup

1. Create a Google Cloud project and enable **Sheets API** and **Drive API**
2. Create a **Service Account** and download the JSON key
3. Save it as `service_account.json` (this file is gitignored)
4. Create a Google Sheet named `subtitle_jobs` and share it with the service account email
5. The bot will auto-create `users` and `jobs` worksheets on first run

### 4. Deploy Bot (PythonAnywhere)

```bash
# On PythonAnywhere, set environment variables in the .env file
# Configure a Flask WSGI app pointing to bot.py
# The webhook is set automatically on startup
```

### 5. Run Colab Pipeline

Open `colab_pipeline.ipynb` in Google Colab with a **T4 GPU** runtime.

Add your secrets via **Tools → Secrets**:
- `BOT_TOKEN`
- `API_ID`
- `API_HASH`

Run stages sequentially (or set up a scheduled trigger).

---

## 📁 Project Structure

```
subfa-ai/
├── bot/ 
│  └── bot.py                 # Flask webhook + Telegram bot handlers
├── notebooks/
    └── subfa_colab_pipeline.ipynb    # 6-stage Colab processing pipeline
├── requirements.txt        # Python dependencies for bot
├── .env.example            # Environment variable template
├── .gitignore
└── README.md
```

---

## 📧 Email Notification Flow

1. User sends a video → coins are deducted and the job is saved with status `awaiting_email`.
2. The bot asks the user for their email (or offers a button to reuse the last email they gave).
3. Once a valid email is received, the job status moves to `new` and enters the normal pipeline.
4. In **Stage 5** of the Colab pipeline, right after the finished video is sent on Telegram (status → `completed`), an email is sent to the user's address letting them know the video is ready.

This requires `SMTP_SERVER`, `SMTP_PORT`, `EMAIL_SENDER`, and `EMAIL_PASSWORD` to be set as **Colab Secrets** (see `.env.example` for a Gmail example — you'll need a Gmail **App Password**, not your normal password). If these aren't set, Stage 5 just skips the email step and logs why.

> ⚠️ If you already have a live `subtitle_jobs` Google Sheet from before this feature, the bot will automatically add the missing `email` / `last_email` columns to the `jobs` and `users` worksheets the first time it starts up.

---

## ⚠️ Security Notes

- **Never** commit `.env`, `service_account.json`, or `*.session` files
- Rotate your `BOT_TOKEN`, `API_ID`, and `API_HASH` if they were ever exposed
- Use [Colab Secrets](https://medium.com/@parthdasawant/how-to-use-secrets-in-google-colab-450c38e3ec75) to store credentials in the notebook environment

---

## 📦 Dependencies

**Bot (PythonAnywhere):**
- `flask`, `pyTelegramBotAPI`, `gspread`, `google-auth`, `python-dotenv`

**Pipeline (Google Colab):**
- `telethon`, `gspread`, `faster-whisper`, `deep-translator`, `ffmpeg` (system)

---

## 🤝 Support | پشتیبانی

Telegram: [@supprot_subfa](https://t.me/supprot_subfa)

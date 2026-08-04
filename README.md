# Piranewz AI Journalist 🤖🎨

Created by the developer of [Trappist.land](https://trappist.land).

Piranewz is an autonomous, bilingual (EN/FR) Telegram news bot that powers the channels **@piranewz** and **@piranewz_fr**. It reads crypto RSS feeds, summarizes and translates articles, generates matching illustrations through **TrappistAI**, and publishes both image and text posts to Telegram.

Every image generation is paid for via the **x402 payment protocol** on the **Casper Network**. Each post creates an on-chain CSPR transaction. Casper mainnet transaction fees cost around **0.1 CSPR**, and since [CSPR fees are burned by the network](https://casper.network), every article Piranewz publishes contributes to burning CSPR.

Inspired by [`UnrealNFT/crypto-news-bot`](https://github.com/UnrealNFT/crypto-news-bot).

## ✨ What the bot does

- Fetches crypto news from ~20 RSS feeds
- Deduplicates and filters articles
- Picks articles to illustrate each cycle
- Generates images through TrappistAI, paying via x402 on Casper
- Posts images and captions to @piranewz (EN) and @piranewz_fr (FR)
- Adds the Piranewz watermark and Telegram badge
- Publishes the Fear & Greed Index on a regular schedule
- Posts crypto price updates with locally generated cards

## 📁 Structure

```
trappist-auto-bot/
├── main.py                  # Entry point
├── trappist_auto_bot/
│   ├── config.py            # Environment configuration
│   ├── scheduler.py         # Autonomous job queue
│   ├── formatting.py        # Captions and prompts
│   ├── translation.py       # EN/FR summaries via Groq
│   ├── fear_greed.py        # Fear & Greed gauge image
│   ├── price_poster.py      # Crypto price card image
│   ├── x402/                # x402 client and signer
│   ├── image/               # Image generators + shared branding/theme
│   ├── telegram/            # Bilingual Telegram poster
│   ├── rss/                 # RSS fetching and cleaning
│   ├── storage/             # SQLite persistence
│   └── utils/
├── scripts/                 # Node.js helpers for signing deploys
├── assets/                  # Logo and Telegram badge
├── render.yaml              # Render Blueprint
├── requirements.txt
└── README.md
```

## 🚀 Local installation

```bash
cd trappist-auto-bot
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
npm install
```

## ⚙️ Configuration

Copy the example file and fill in your secrets:

```bash
cp .env.example .env
```

Required variables:

- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `TELEGRAM_CHAT_ID` — main channel (EN)
- `TELEGRAM_CHAT_ID_FR` — French channel (FR)
- `CASPER_PUBLIC_KEY` — wallet public key with `02` or `01` prefix
- `CASPER_PRIVATE_KEY_PATH` — path to the PEM private key file
- `GROQ_API_KEY` — for summaries and translation

Important variables:

- `TRAPIST_API_URL` — TrappistAI endpoint (default: `https://trappist.land`)
- `POST_INTERVAL_MINUTES=4` — RSS check frequency
- `MAX_ARTICLES_PER_CYCLE=4` — articles fetched per check
- `DELAY_BETWEEN_POSTS=60` — delay between posts
- `DAILY_BUDGET_MOTES` — daily CSPR spending budget
- `MAX_PAYMENT_MOTES` — per-image spending cap
- `PRICE_POST_INTERVAL_HOURS=2` — price update interval

## ▶️ Run the bot

Autonomous mode:

```bash
python main.py
```

Single cycle (test):

```bash
python main.py --once
```

## 🚀 Deploy on Render

### Using the dashboard

1. Push this repo to GitHub (`.env` and `data/` are in `.gitignore`).
2. On [render.com](https://render.com), click **New + → Background Worker**.
3. Select the repo.
4. Configure:
   - **Name**: `piranewz-bot`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt && npm install`
   - **Start Command**: `python main.py`
   - **Plan**: Starter (for 24/7 uptime)
5. Under **Disks**, add a disk:
   - Name: `piranewz-data`
   - Mount Path: `/data`
   - Size: 1 GB
6. Under **Environment**, paste the variables from your `.env`.
7. Click **Create Background Worker**.

### Using `render.yaml` (Blueprints)

1. Push this repo to GitHub.
2. On Render, click **New + → Blueprint**.
3. Select the repo.
4. Fill in the variables marked `sync: false` (secrets).

## ⚠️ Warnings

- This bot spends **real CSPR** in production.
- Set `MAX_PAYMENT_MOTES` and `DAILY_BUDGET_MOTES` carefully.
- Never commit `.env`, `*.pem`, `data/`, or debug JSON files.

## 📜 License

MIT

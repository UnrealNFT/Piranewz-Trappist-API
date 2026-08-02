# Piranewz AI Journalist 🤖🎨

Bot Telegram autonome, bilingue EN/FR, qui alimente les canaux **@piranewz** et **@piranewz_fr** avec des actualités crypto. Il récupère les flux RSS, illustre une sélection d'articles via **TrappistAI** (paiement x402 en CSPR), puis publie les images et les posts texte sur Telegram.

Inspiré de [`UnrealNFT/crypto-news-bot`](https://github.com/UnrealNFT/crypto-news-bot).

## ✨ Ce que fait le bot

- Récupère les actualités crypto depuis ~20 flux RSS
- Déduplique et filtre les articles
- Choisit **un seul article à illustrer par cycle** (sélection aléatoire ↔ score visuel)
- Génère l'image sur TrappistAI en payant en CSPR via x402
- Poste l'image **et** sa version texte sur @piranewz (EN) et @piranewz_fr (FR)
- Ajoute le watermark Piranewz + badge Telegram
- Publie l'indice Fear & Greed une fois par heure

## 📁 Structure

```
trappist-auto-bot/
├── main.py                  # Point d'entrée
├── trappist_auto_bot/
│   ├── config.py            # Configuration env
│   ├── scheduler.py         # Boucle autonome en mode file
│   ├── formatting.py        # Captions + prompts
│   ├── translation.py       # Résumé FR/EN via Groq
│   ├── fear_greed.py        # Fear & Greed index
│   ├── x402/                # Client + signer x402
│   ├── image/               # Générateurs TrappistAI/WaveSpeed/Pollinations
│   ├── telegram/            # Poster Telegram bilingue
│   ├── rss/                 # Fetch + cleaning RSS
│   ├── storage/             # SQLite
│   └── utils/
├── scripts/                 # Helpers Node.js pour signer les deploys
├── assets/                  # Logo + badge Telegram
├── render.yaml              # Déploiement Render (Blueprints)
├── requirements.txt
└── README.md
```

## 🚀 Installation locale

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

Copie le fichier exemple et remplis tes secrets :

```bash
cp .env.example .env
```

Variables **requises** :

- `TELEGRAM_BOT_TOKEN` — token de @BotFather
- `TELEGRAM_CHAT_ID` — canal principal (EN)
- `TELEGRAM_CHAT_ID_FR` — canal français (FR)
- `CASPER_PUBLIC_KEY` — clé publique du wallet (02… ou 01…)
- `CASPER_PRIVATE_KEY_BASE64` — clé privée encodée en base64 (PEM)
- `GROQ_API_KEY` — pour la traduction/résumé

Variables importantes :

- `POST_INTERVAL_MINUTES=4` — fréquence de check RSS
- `MAX_ARTICLES_PER_CYCLE=4` — articles récupérés par check
- `DELAY_BETWEEN_POSTS=60` — délai entre deux posts
- `DAILY_BUDGET_MOTES` — budget CSPR journalier
- `MAX_PAYMENT_MOTES` — plafond par image

## ▶️ Lancer le bot

Mode autonome :

```bash
python main.py
```

Un seul cycle (test) :

```bash
python main.py --once
```

## 🚀 Déploiement Render

### Avec le dashboard

1. Crée un repo GitHub propre (`.env` et `data/` sont dans `.gitignore`).
2. Sur [render.com](https://render.com), clique **New + → Background Worker**.
3. Choisis ton repo.
4. Configure :
   - **Name** : `piranewz-bot`
   - **Runtime** : Python 3
   - **Build Command** : `pip install -r requirements.txt && npm install`
   - **Start Command** : `python main.py`
   - **Plan** : Starter (pour du 24/7)
5. Dans **Disks**, ajoute un disque :
   - Name : `piranewz-data`
   - Mount Path : `/data`
   - Size : 1 GB
6. Dans **Environment**, colle toutes les variables de ton `.env`.
7. Clique **Create Background Worker**.

### Avec `render.yaml` (Blueprints)

1. Push ce repo sur GitHub.
2. Sur Render, clique **New + → Blueprint**.
3. Sélectionne le repo.
4. Remplis les variables marquées `sync: false` (secrets).

## ⚠️ Avertissements

- Ce bot dépense **vraiment** du CSPR en production.
- Configure impérativement `MAX_PAYMENT_MOTES` et `DAILY_BUDGET_MOTES`.
- Ne committe jamais `.env`, `*.pem`, `data/` ni les fichiers de debug JSON.

## 📜 Licence

MIT

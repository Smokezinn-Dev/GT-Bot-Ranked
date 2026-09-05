# ============================================================
# CONFIG.PY - RANKED BOT (LEVE)
# ============================================================

import os

# Token e Mongo (prioridade: env vars)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or ""
MONGODB_URL = os.getenv("MONGODB_URL") or os.getenv("MONGODB_URI") or (
    "mongodb+srv://gleicyferreira899_db_user:Q57eSQXyzUoWQxw4@cluster0.xhwrpcd.mongodb.net/"
    "?retryWrites=true&w=majority&appName=Cluster0"
)
DB_NAME = os.getenv("DB_NAME", "gt_bot")

# Prefixo
PREFIX = os.getenv("PREFIX", "%")

# Visual
EMBED_COLOR = int(os.getenv("EMBED_COLOR", "0x00ff00"), 0) if str(os.getenv("EMBED_COLOR", "")).startswith("0x") else 0x00ff00
EMBED_FOOTER = os.getenv("EMBED_FOOTER", "Rank System v3.0")

# Tipos de partida
MATCH_TYPES = ["1v1", "2v2", "3v3"]

# Guild opcional para sync slash
GUILD_ID = os.getenv("GUILD_ID") or os.getenv("DISCORD_GUILD_ID") or None

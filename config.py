# ============================================================
# CONFIG.PY - RANKED BOT (LEVE + OTIMIZADO)
# ============================================================

import os
import logging

# Token e Mongo (prioridade: env vars)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or "TOKEN DO BOT INDISPONÍVEL"
MONGODB_URL = os.getenv("MONGODB_URL") or os.getenv("MONGODB_URI") or ("MONGODB INDISPONÍVEL"
)
DB_NAME = os.getenv("DB_NAME", "gt_bot")

# Prefixo
PREFIX = os.getenv("PREFIX", "%")

# Visual
EMBED_COLOR = int(os.getenv("EMBED_COLOR", "0x00ff00"), 0) if str(os.getenv("EMBED_COLOR", "")).startswith("0x") else 0x00ff00
EMBED_FOOTER = os.getenv("EMBED_FOOTER", "Rank System v3.0")

# Tipos de partida
MATCH_TYPES = ["1v1", "2v2", "3v3", "4v4"]

# Guild opcional para sync slash
GUILD_ID = os.getenv("GUILD_ID") or os.getenv("DISCORD_GUILD_ID") or None

# ============================================================
# OTIMIZAÇÕES PARA RAILWAY
# ============================================================

OPTIMIZER_INTERVAL = int(os.getenv("OPTIMIZER_INTERVAL", "300"))
GC_THRESHOLD = (700, 10, 10)
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "128"))
ENABLE_DEBUG = os.getenv("ENABLE_DEBUG", "false").lower() == "true"

# Desabilita logging desnecessário em produção
if not ENABLE_DEBUG:
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

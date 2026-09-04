# ============================================================
# CONFIG.PY - CONFIGURAÇÕES (CORRIGIDO)
# ============================================================

import os

# ============================================================
# TOKEN DO DISCORD
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    DISCORD_TOKEN = "MTQ1NjMxMTk2MTI3NjEyNTIwNg.GC3uIV.VQRu36MVjIWsXQ40QEZ2tX_GlKah49ZF7soD80"

# ============================================================
# MONGODB
# ============================================================

MONGODB_URL = os.getenv("MONGODB_URL")

if not MONGODB_URL:
    MONGODB_URL = "mongodb+srv://gleicyferreira899_db_user:Q57eSQXyzUoWQxw4@cluster0.xhwrpcd.mongodb.net/?appName=Cluster0"

DB_NAME = os.getenv("DB_NAME", "gt_bot")

# ============================================================
# CONFIGURAÇÕES DO SISTEMA
# ============================================================

EMBED_COLOR = 0x00ff00
EMBED_FOOTER = "Rank System v3.0"
MATCH_TYPES = ["1v1", "2v2", "3v3"]

# ============================================================
# INICIALIZAÇÃO
# ============================================================

print("✅ Configurações carregadas!")
print(f"📡 Token: {DISCORD_TOKEN[:10]}...")
print(f"🍃 MongoDB: {MONGODB_URL[:30]}...")

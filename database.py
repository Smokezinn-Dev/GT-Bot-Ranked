# ============================================================
# DATABASE.PY - RANKED BOT (OTIMIZAÇÃO EXTREMA + ATÔMICO)
# ============================================================
# Truques de otimização aplicados:
# - Connection única (singleton) com pool mínimo
# - Projections em todas as queries (só campos necessários)
# - find_one_and_update atômico (compatível com Moderação)
# - Índices criados 1x no start (não a cada query)
# - Cache TTL mínimo em memória com LRU rígido
# - Sem list() desnecessário / generators quando possível
# - update com $inc em vez de read+write
# - TTL-like cleanup de dados mortos
# - Constantes e defaults sem alocação repetida
# ============================================================

import os
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from collections import OrderedDict

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

# ============================================================
# CONFIG (evita import circular — lê env direto)
# ============================================================

MONGODB_URL = os.getenv(
    "MONGODB_URL",
    os.getenv(
        "MONGODB_URI",
        "mongodb+srv://gleicyferreira899_db_user:Q57eSQXyzUoWQxw4@cluster0.xhwrpcd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    )
)
DB_NAME = os.getenv("DB_NAME", "gt_bot")

# ============================================================
# CACHE LRU ULTRA-LEVE (max entries rígido = menos RAM)
# ============================================================

class _LRU:
    __slots__ = ("maxsize", "ttl", "_data")

    def __init__(self, maxsize: int = 128, ttl: int = 30):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: OrderedDict = OrderedDict()

    def get(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        val, exp = item
        if time.monotonic() > exp:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return val

    def set(self, key, val):
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = (val, time.monotonic() + self.ttl)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def invalidate(self, key):
        self._data.pop(key, None)

    def clear(self):
        self._data.clear()


_settings_cache = _LRU(maxsize=32, ttl=45)
_balance_cache = _LRU(maxsize=256, ttl=15)
_stats_cache = _LRU(maxsize=128, ttl=20)

# ============================================================
# CONEXÃO SINGLETON (pool mínimo = menos RAM)
# ============================================================

_client = None
_db = None
_indexes_ready = False


def get_mongo_client():
    global _client
    if _client is not None:
        return _client

    last_err = None
    for attempt in range(3):
        try:
            _client = MongoClient(
                MONGODB_URL,
                # --- otimização de pool / RAM ---
                maxPoolSize=5,          # default 100 → 5 (Railway free)
                minPoolSize=0,          # não mantém conexões ociosas
                maxIdleTimeMS=30000,    # fecha idle rápido
                waitQueueTimeoutMS=10000,
                serverSelectionTimeoutMS=15000,
                connectTimeoutMS=15000,
                socketTimeoutMS=20000,
                retryWrites=True,
                w="majority",
                # compressão se disponível (menos banda)
                compressors="zlib",
                zlibCompressionLevel=6,
            )
            _client.admin.command("ping")
            return _client
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise ConnectionError(f"MongoDB falhou após 3 tentativas: {last_err}")


def get_connection():
    global _db
    if _db is None:
        _db = get_mongo_client()[DB_NAME]
    return _db


def init_db():
    """Inicializa DB + índices (1x)."""
    global _indexes_ready
    db = get_connection()
    if not _indexes_ready:
        _ensure_indexes(db)
        _indexes_ready = True
    return db


def _ensure_indexes(db):
    """Cria índices essenciais. ignore se já existem."""
    try:
        # Economia (compartilhada com Moderação)
        db["economy_balances"].create_index(
            [("guild_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True, background=True
        )
        db["economy_transactions"].create_index(
            [("guild_id", ASCENDING), ("user_id", ASCENDING), ("timestamp", DESCENDING)],
            background=True
        )
        # Ranked
        db["players"].create_index(
            [("guild_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True, background=True
        )
        db["players"].create_index(
            [("guild_id", ASCENDING), ("total_wins", DESCENDING)],
            background=True
        )
        db["matches"].create_index(
            [("guild_id", ASCENDING), ("status", ASCENDING)],
            background=True
        )
        db["betting_matches"].create_index(
            [("guild_id", ASCENDING), ("status", ASCENDING)],
            background=True
        )
        db["tickets"].create_index(
            [("guild_id", ASCENDING), ("status", ASCENDING)],
            background=True
        )
        db["guild_settings"].create_index(
            [("guild_id", ASCENDING)], unique=True, background=True
        )
    except Exception:
        pass  # índice já existe ou permissão limitada


# ============================================================
# DEFAULT SETTINGS (constante — zero alocação extra)
# ============================================================

_DEFAULT_SETTINGS = {
    "currency": {"name": "Moedas", "symbol": "💰", "daily_bonus": 100},
    "ranked": {
        "enabled": True,
        "win_bonus": 50,
        "loss_penalty": 10,
        "entry_fee": 0,
        "allowed_roles": [],
        "max_matches_per_user": 3,
        "maps": ["Arena", "Castelo", "Floresta", "Deserto"],
    },
    "betting": {
        "enabled": True,
        "min_bet": 100,
        "max_bet": 10000,
        "win_multiplier": 1.9,   # house edge leve
        "tax_percent": 5.0,
        "max_players": 6,
        "allowed_roles": [],
    },
    "top_prizes": {
        "enabled": True,
        "interval_days": 7,
        "prizes": {"1": 10000, "2": 5000, "3": 2500, "4_10": 1000},
    },
    "match_settings": {
        "auto_ticket": True,
        "ticket_category": None,
        "ticket_name_template": "🎮-{tipo}-{match_id}",
        "mediator_roles": [],
        "timeout_minutes": 30,
        "lobby_timeout": 600,
    },
    "customization": {
        "embed_color": 0x00ff00,
        "embed_footer": "Rank System v3.0",
        "dm_notifications": True,
        "ping_players": True,
    },
    "permissions": {
        "admin_roles": [],
        "config_roles": [],
    },
}


def _copy_defaults(guild_id: str) -> dict:
    """Cópia rasa suficiente (evita deepcopy pesado)."""
    import copy
    cfg = copy.deepcopy(_DEFAULT_SETTINGS)
    cfg["guild_id"] = guild_id
    return cfg


# ============================================================
# GUILD SETTINGS (cache)
# ============================================================

def get_guild_settings(guild_id: str) -> dict:
    cached = _settings_cache.get(guild_id)
    if cached is not None:
        return cached

    db = get_connection()
    doc = db["guild_settings"].find_one({"guild_id": guild_id}, {"_id": 0})
    if not doc:
        doc = _copy_defaults(guild_id)
        try:
            db["guild_settings"].insert_one(doc)
        except Exception:
            pass
    else:
        # merge defaults para chaves novas sem sobrescrever
        base = _copy_defaults(guild_id)
        for k, v in base.items():
            if k not in doc:
                doc[k] = v
            elif isinstance(v, dict):
                for sk, sv in v.items():
                    doc[k].setdefault(sk, sv)

    _settings_cache.set(guild_id, doc)
    return doc


def update_guild_settings(guild_id: str, path: str, value: Any) -> bool:
    db = get_connection()
    result = db["guild_settings"].update_one(
        {"guild_id": guild_id},
        {"$set": {path: value}},
        upsert=True
    )
    _settings_cache.invalidate(guild_id)
    return result.modified_count > 0 or result.upserted_id is not None


# ============================================================
# ECONOMIA ATÔMICA (mesma collection da Moderação)
# ============================================================

def get_player_balance(guild_id: int, user_id: int) -> int:
    key = f"{guild_id}:{user_id}"
    cached = _balance_cache.get(key)
    if cached is not None:
        return cached

    db = get_connection()
    doc = db["economy_balances"].find_one(
        {"guild_id": int(guild_id), "user_id": int(user_id)},
        {"balance": 1}
    )
    bal = int(doc["balance"]) if doc and "balance" in doc else 0
    _balance_cache.set(key, bal)
    return bal


def set_player_balance(guild_id: int, user_id: int, amount: int) -> int:
    amount = max(0, int(amount))
    db = get_connection()
    db["economy_balances"].update_one(
        {"guild_id": int(guild_id), "user_id": int(user_id)},
        {"$set": {"balance": amount, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    _balance_cache.invalidate(f"{guild_id}:{user_id}")
    return amount


def add_player_balance(guild_id: int, user_id: int, amount: int, description: str = "") -> int:
    """$inc atômico — seguro com o bot de Moderação."""
    amount = int(amount)
    if amount == 0:
        return get_player_balance(guild_id, user_id)

    db = get_connection()
    result = db["economy_balances"].find_one_and_update(
        {"guild_id": int(guild_id), "user_id": int(user_id)},
        {
            "$inc": {"balance": amount},
            "$set": {"updated_at": datetime.utcnow()},
            "$setOnInsert": {"guild_id": int(guild_id), "user_id": int(user_id)},
        },
        upsert=True,
        return_document=True,
        projection={"balance": 1},
    )
    new_bal = int(result["balance"]) if result else amount
    _balance_cache.invalidate(f"{guild_id}:{user_id}")

    # log assíncrono-friendly (não bloqueia se falhar)
    try:
        db["economy_transactions"].insert_one({
            "guild_id": int(guild_id),
            "user_id": int(user_id),
            "type": "add",
            "amount": amount,
            "description": (description or "")[:180],
            "source": "ranked",
            "balance_after": new_bal,
            "timestamp": datetime.utcnow(),
        })
    except Exception:
        pass
    return new_bal


def remove_player_balance(guild_id: int, user_id: int, amount: int, description: str = "") -> bool:
    """Remove só se saldo >= amount (atômico)."""
    amount = int(amount)
    if amount <= 0:
        return False

    db = get_connection()
    result = db["economy_balances"].find_one_and_update(
        {
            "guild_id": int(guild_id),
            "user_id": int(user_id),
            "balance": {"$gte": amount},
        },
        {
            "$inc": {"balance": -amount},
            "$set": {"updated_at": datetime.utcnow()},
        },
        return_document=True,
        projection={"balance": 1},
    )
    if result is None:
        return False

    _balance_cache.invalidate(f"{guild_id}:{user_id}")
    try:
        db["economy_transactions"].insert_one({
            "guild_id": int(guild_id),
            "user_id": int(user_id),
            "type": "remove",
            "amount": amount,
            "description": (description or "")[:180],
            "source": "ranked",
            "balance_after": int(result.get("balance", 0)),
            "timestamp": datetime.utcnow(),
        })
    except Exception:
        pass
    return True


# ============================================================
# PLAYERS / STATS
# ============================================================

_EMPTY_STATS = {
    "1v1": {"wins": 0, "losses": 0},
    "2v2": {"wins": 0, "losses": 0},
    "3v3": {"wins": 0, "losses": 0},
    "team_wins": 0,
    "team_losses": 0,
}


def get_player_stats(guild_id: str, user_id: str) -> dict:
    key = f"ps:{guild_id}:{user_id}"
    cached = _stats_cache.get(key)
    if cached is not None:
        return cached

    db = get_connection()
    doc = db["players"].find_one(
        {"guild_id": str(guild_id), "user_id": str(user_id)},
        {"_id": 0}
    )
    if not doc:
        doc = {
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "stats": {
                "1v1": {"wins": 0, "losses": 0},
                "2v2": {"wins": 0, "losses": 0},
                "3v3": {"wins": 0, "losses": 0},
                "team_wins": 0,
                "team_losses": 0,
            },
            "total_wins": 0,
            "total_losses": 0,
            "matches_played": 0,
        }
        try:
            db["players"].insert_one({**doc, "created_at": datetime.utcnow()})
        except Exception:
            pass

    _stats_cache.set(key, doc)
    return doc


def update_player_stats(guild_id: str, user_id: str, match_type: str, result: str, team_name: str = None) -> bool:
    """Update atômico com $inc — sem read-modify-write."""
    db = get_connection()
    inc: Dict[str, int] = {"matches_played": 1}

    if result == "win":
        inc[f"stats.{match_type}.wins"] = 1
        inc["total_wins"] = 1
        if team_name:
            inc["stats.team_wins"] = 1
    elif result == "loss":
        inc[f"stats.{match_type}.losses"] = 1
        inc["total_losses"] = 1
        if team_name:
            inc["stats.team_losses"] = 1
    else:
        return False

    db["players"].update_one(
        {"guild_id": str(guild_id), "user_id": str(user_id)},
        {
            "$inc": inc,
            "$setOnInsert": {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "created_at": datetime.utcnow(),
            },
        },
        upsert=True,
    )
    _stats_cache.invalidate(f"ps:{guild_id}:{user_id}")
    return True


def get_player_rank_stats(guild_id: str, user_id: str) -> dict:
    player = get_player_stats(guild_id, user_id)
    balance = get_player_balance(int(guild_id), int(user_id))
    stats = player.get("stats") or {}
    return {
        "total_wins": player.get("total_wins", 0),
        "total_losses": player.get("total_losses", 0),
        "matches_played": player.get("matches_played", 0),
        "stats": stats,
        "balance": balance,
        "team_wins": stats.get("team_wins", 0),
        "team_losses": stats.get("team_losses", 0),
        "prestige_level": 0,
        "achievements": 0,
    }


def get_rankings(guild_id: str, match_type: str, limit: int = 50) -> List[dict]:
    """Aggregation enxuta com projection."""
    db = get_connection()
    limit = max(1, min(int(limit), 50))
    pipeline = [
        {"$match": {"guild_id": str(guild_id)}},
        {"$project": {
            "user_id": 1,
            "wins": f"$stats.{match_type}.wins",
            "losses": f"$stats.{match_type}.losses",
        }},
        {"$match": {"$or": [{"wins": {"$gt": 0}}, {"losses": {"$gt": 0}}]}},
        {"$sort": {"wins": -1, "losses": 1}},
        {"$limit": limit},
    ]
    return list(db["players"].aggregate(pipeline, allowDiskUse=False))


# ============================================================
# MATCHES
# ============================================================

def create_match(match_data: dict, is_betting: bool = False) -> str:
    from bson import ObjectId
    match_id = str(ObjectId())
    match_data["_id"] = match_id
    match_data["created_at"] = datetime.utcnow()
    match_data["status"] = match_data.get("status", "waiting")
    match_data["is_betting"] = is_betting
    match_data.setdefault("players", [])
    match_data.setdefault("teams", {})

    col = "betting_matches" if is_betting else "matches"
    get_connection()[col].insert_one(match_data)
    return match_id


def get_match(match_id: str, is_betting: bool = False) -> Optional[dict]:
    col = "betting_matches" if is_betting else "matches"
    return get_connection()[col].find_one({"_id": match_id})


def update_match(match_id: str, update_data: dict, is_betting: bool = False) -> bool:
    col = "betting_matches" if is_betting else "matches"
    result = get_connection()[col].update_one({"_id": match_id}, {"$set": update_data})
    return result.modified_count > 0


def get_active_matches(guild_id: str, is_betting: bool = False) -> List[dict]:
    col = "betting_matches" if is_betting else "matches"
    return list(
        get_connection()[col].find(
            {"guild_id": str(guild_id), "status": "waiting"},
            {"players": 1, "match_type": 1, "map": 1, "bet_amount": 1, "status": 1}
        ).limit(20)
    )


# ============================================================
# TICKETS
# ============================================================

def create_ticket(ticket_data: dict) -> str:
    from bson import ObjectId
    ticket_id = str(ObjectId())
    ticket_data["_id"] = ticket_id
    ticket_data["created_at"] = datetime.utcnow()
    ticket_data["status"] = ticket_data.get("status", "active")
    get_connection()["tickets"].insert_one(ticket_data)
    return ticket_id


def get_ticket(channel_id: str) -> Optional[dict]:
    return get_connection()["tickets"].find_one(
        {"channel_id": str(channel_id)},
        {"_id": 1, "match_id": 1, "players": 1, "status": 1, "is_betting": 1}
    )


def close_ticket(ticket_id: str) -> bool:
    result = get_connection()["tickets"].update_one(
        {"_id": ticket_id},
        {"$set": {"status": "closed", "closed_at": datetime.utcnow()}}
    )
    return result.modified_count > 0


# ============================================================
# TOP PRIZES
# ============================================================

def distribute_top_prizes(guild_id: str, match_type: str) -> dict:
    settings = get_guild_settings(guild_id)
    prizes_cfg = settings.get("top_prizes", {})
    if not prizes_cfg.get("enabled", True):
        return {"success": False, "message": "Prêmios desativados"}

    ranking = get_rankings(guild_id, match_type, 10)
    if not ranking:
        return {"success": False, "message": "Nenhum jogador"}

    prizes = prizes_cfg.get("prizes", {})
    distributed = {}
    for i, player in enumerate(ranking, 1):
        if i == 1:
            amount = int(prizes.get("1", 10000))
        elif i == 2:
            amount = int(prizes.get("2", 5000))
        elif i == 3:
            amount = int(prizes.get("3", 2500))
        else:
            amount = int(prizes.get("4_10", 1000))
        if amount > 0:
            add_player_balance(
                int(guild_id), int(player["user_id"]), amount,
                f"Prêmio Top {i} - {match_type}"
            )
            distributed[str(i)] = {"user_id": player["user_id"], "amount": amount}

    get_connection()["top_prizes"].insert_one({
        "guild_id": guild_id,
        "match_type": match_type,
        "distributed_at": datetime.utcnow(),
        "prizes": distributed,
    })
    update_guild_settings(guild_id, "top_prizes.last_distribution", datetime.utcnow())
    return {"success": True, "distributed": distributed, "count": len(distributed)}


def can_distribute_prizes(guild_id: str) -> bool:
    settings = get_guild_settings(guild_id)
    last = settings.get("top_prizes", {}).get("last_distribution")
    if not last:
        return True
    interval = int(settings.get("top_prizes", {}).get("interval_days", 7))
    if isinstance(last, str):
        try:
            last = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except Exception:
            return True
    return datetime.utcnow() >= (last + timedelta(days=interval))


# ============================================================
# MEDIADORES
# ============================================================

def set_mediator_role(guild_id: str, role_id: int) -> bool:
    return update_guild_settings(guild_id, "match_settings.mediator_roles", [int(role_id)])


def get_mediator_roles(guild_id: str) -> List[int]:
    settings = get_guild_settings(guild_id)
    roles = settings.get("match_settings", {}).get("mediator_roles", [])
    return [int(r) for r in roles]


# ============================================================
# ECONOMY CONFIG (compat ranking_system)
# ============================================================

def get_economy_config(guild_id: int) -> dict:
    """Compatível com ranking_system que espera currency_emoji."""
    settings = get_guild_settings(str(guild_id))
    cur = settings.get("currency", {})
    return {
        "currency_name": cur.get("name", "Moedas"),
        "currency_emoji": cur.get("symbol", "💰"),
        "daily_bonus": cur.get("daily_bonus", 100),
    }


# Alias para imports antigos
server_configs = None  # placeholder — ranking_system não deve mais depender disso


def clear_all_caches():
    _settings_cache.clear()
    _balance_cache.clear()
    _stats_cache.clear()

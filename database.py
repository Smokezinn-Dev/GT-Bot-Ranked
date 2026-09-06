# ============================================================
# DATABASE.PY - RANKED BOT (OTIMIZAÇÃO EXTREMA + SEGURO)
# ============================================================

import os
import time
import gc
import threading
import atexit
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from collections import OrderedDict
import asyncio
from bson import ObjectId
from bson.errors import InvalidId

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure, DuplicateKeyError

# ============================================================
# CONFIG
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
# VALIDADOR DE OBJECTID SEGURO
# ============================================================

def safe_object_id(value: str) -> Optional[ObjectId]:
    """Valida e converte string para ObjectId com segurança"""
    if not value or not isinstance(value, str):
        return None
    try:
        return ObjectId(value)
    except (InvalidId, ValueError, TypeError):
        return None

def safe_object_id_str(value: str) -> Optional[str]:
    """Valida se é um ObjectId válido e retorna como string"""
    oid = safe_object_id(value)
    return str(oid) if oid else None

# ============================================================
# CACHE LRU COM MONITORAMENTO E LIMPEZA AUTOMÁTICA
# ============================================================

class _LRU:
    __slots__ = ("maxsize", "ttl", "_data", "_hits", "_misses", "_total_ops", "_lock")
    
    def __init__(self, maxsize: int = 128, ttl: int = 30):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: OrderedDict = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._total_ops = 0
        self._lock = threading.RLock()

    def get(self, key):
        with self._lock:
            self._total_ops += 1
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return None
            val, exp = item
            if time.monotonic() > exp:
                self._data.pop(key, None)
                self._misses += 1
                return None
            self._data.move_to_end(key)
            self._hits += 1
            return val

    def set(self, key, val):
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (val, time.monotonic() + self.ttl)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def invalidate(self, key):
        with self._lock:
            self._data.pop(key, None)

    def clear(self):
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0
            self._total_ops = 0
            gc.collect()
    
    def stats(self):
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._data),
                "hits": self._hits,
                "misses": self._misses,
                "total_ops": self._total_ops,
                "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "0%"
            }

    def invalidate_pattern(self, pattern: str):
        """Invalida chaves que começam com um padrão"""
        with self._lock:
            keys = [k for k in self._data.keys() if k.startswith(pattern)]
            for k in keys:
                self._data.pop(k, None)


_settings_cache = _LRU(maxsize=32, ttl=90)
_balance_cache = _LRU(maxsize=256, ttl=25)
_stats_cache = _LRU(maxsize=128, ttl=40)
_guild_cache = _LRU(maxsize=16, ttl=300)  # Cache de guilds para evitar fetch repetido

# ============================================================
# CONEXÃO SINGLETON COM MONITOR + RECONEXÃO INTELIGENTE
# ============================================================

_client = None
_db = None
_indexes_ready = False
_connection_lock = threading.RLock()
_last_db_activity = time.monotonic()
_connection_retries = 0
_MAX_RETRIES = 5
_RETRY_DELAY = 2

class _ConnectionPoolMonitor:
    """Monitora e recicla conexões ociosas com reconexão inteligente"""
    __slots__ = ("_last_check", "_check_interval", "_idle_timeout", "_last_health_check")

    def __init__(self, check_interval: int = 120, idle_timeout: int = 900):
        self._last_check = time.monotonic()
        self._check_interval = check_interval
        self._idle_timeout = idle_timeout
        self._last_health_check = time.monotonic()

    def check_and_cleanup(self):
        now = time.monotonic()
        if now - self._last_check < self._check_interval:
            return
        self._last_check = now

        global _client, _db, _connection_retries
        if _client is not None and (now - _last_db_activity) > self._idle_timeout:
            try:
                _client.close()
            except Exception:
                pass
            _client = None
            _db = None
            _connection_retries = 0
            gc.collect()
        
        # Health check periódico
        if now - self._last_health_check > 600:
            self._last_health_check = now
            if _client is not None:
                try:
                    _client.admin.command("ping", serverSelectionTimeoutMS=2000)
                except Exception:
                    _client = None
                    _db = None
                    gc.collect()

_pool_monitor = _ConnectionPoolMonitor()

def get_mongo_client():
    global _client, _last_db_activity, _connection_retries
    _last_db_activity = time.monotonic()

    if _client is not None:
        try:
            _client.admin.command("ping", serverSelectionTimeoutMS=2000)
            _connection_retries = 0
            return _client
        except Exception:
            _client = None
            _db = None
            gc.collect()

    with _connection_lock:
        if _client is not None:
            try:
                _client.admin.command("ping", serverSelectionTimeoutMS=2000)
                return _client
            except Exception:
                _client = None

        if _connection_retries >= _MAX_RETRIES:
            _connection_retries = 0
            raise ConnectionError("❌ Máximo de tentativas de reconexão excedido")

        last_err = None
        for attempt in range(_MAX_RETRIES):
            try:
                _client = MongoClient(
                    MONGODB_URL,
                    maxPoolSize=3,
                    minPoolSize=0,
                    maxIdleTimeMS=30000,
                    waitQueueTimeoutMS=10000,
                    serverSelectionTimeoutMS=15000,
                    connectTimeoutMS=15000,
                    socketTimeoutMS=20000,
                    retryWrites=True,
                    w="majority",
                    compressors="zlib",
                    zlibCompressionLevel=6,
                    # Segurança adicional
                    tls=True,
                    tlsAllowInvalidCertificates=False,
                )
                _client.admin.command("ping")
                _connection_retries = 0
                return _client
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                last_err = e
                _connection_retries += 1
                time.sleep(_RETRY_DELAY * (attempt + 1))
            except Exception as e:
                last_err = e
                time.sleep(1)
        
        _connection_retries = 0
        raise ConnectionError(f"MongoDB falhou após {_MAX_RETRIES} tentativas: {last_err}")


def get_connection():
    global _db, _last_db_activity
    _last_db_activity = time.monotonic()
    if _db is None:
        _db = get_mongo_client()[DB_NAME]
    return _db


def init_db():
    global _indexes_ready
    db = get_connection()
    if not _indexes_ready:
        _ensure_indexes(db)
        _indexes_ready = True
    return db


def _ensure_indexes(db):
    """Cria índices com segurança"""
    try:
        # Índices com unique e sparse para otimização
        db["economy_balances"].create_index(
            [("guild_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True, background=True, name="idx_balance_guild_user"
        )
        db["economy_transactions"].create_index(
            [("guild_id", ASCENDING), ("user_id", ASCENDING), ("timestamp", DESCENDING)],
            background=True, name="idx_transactions_guild_user_ts"
        )
        db["economy_transactions"].create_index(
            [("timestamp", DESCENDING)],
            background=True, name="idx_transactions_ts"
        )
        db["players"].create_index(
            [("guild_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True, background=True, name="idx_players_guild_user"
        )
        db["players"].create_index(
            [("guild_id", ASCENDING), ("total_wins", DESCENDING)],
            background=True, name="idx_players_guild_wins"
        )
        db["matches"].create_index(
            [("guild_id", ASCENDING), ("status", ASCENDING)],
            background=True, name="idx_matches_guild_status"
        )
        db["matches"].create_index(
            [("created_at", DESCENDING)],
            background=True, name="idx_matches_created"
        )
        db["betting_matches"].create_index(
            [("guild_id", ASCENDING), ("status", ASCENDING)],
            background=True, name="idx_betting_guild_status"
        )
        db["tickets"].create_index(
            [("guild_id", ASCENDING), ("status", ASCENDING)],
            background=True, name="idx_tickets_guild_status"
        )
        db["guild_settings"].create_index(
            [("guild_id", ASCENDING)], unique=True, background=True, name="idx_settings_guild"
        )
        # TTL index para limpar transações antigas
        db["economy_transactions"].create_index(
            [("timestamp", ASCENDING)],
            expireAfterSeconds=2592000,  # 30 dias
            background=True, name="idx_transactions_ttl"
        )
    except OperationFailure as e:
        # Índices já existem ou erro permissão
        pass
    except Exception:
        pass


# ============================================================
# DEFAULT SETTINGS (OTIMIZADO)
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
        "maps_options": [],  # Opções customizadas com emojis
    },
    "betting": {
        "enabled": True,
        "min_bet": 100,
        "max_bet": 10000,
        "win_multiplier": 1.9,
        "tax_percent": 5.0,
        "max_players": 6,
        "allowed_roles": [],
    },
    "top_prizes": {
        "enabled": True,
        "interval_days": 7,
        "prizes": {"1": 10000, "2": 5000, "3": 2500, "4_10": 1000},
    },
    "rewards": {
        "1v1": {"enabled": False, "scope": "top3", "role_id": None, "currency_amount": 0, "interval_days": 7, "last_distribution": None},
        "2v2": {"enabled": False, "scope": "top3", "role_id": None, "currency_amount": 0, "interval_days": 7, "last_distribution": None},
        "3v3": {"enabled": False, "scope": "top3", "role_id": None, "currency_amount": 0, "interval_days": 7, "last_distribution": None},
        "4v4": {"enabled": False, "scope": "top3", "role_id": None, "currency_amount": 0, "interval_days": 7, "last_distribution": None},
    },
    "match_settings": {
        "auto_ticket": True,
        "ticket_category": None,
        "ticket_name_template": "🎮-{tipo}-{match_id}",
        "mediator_roles": [],
        "timeout_minutes": 30,
        "lobby_timeout": 600,
        "team_select_timeout": 180,
        "queue_channel_only": False,
    },
    "customization": {
        "embed_color": 0x00ff00,
        "embed_footer": "Rank System v3.0",
        "dm_notifications": True,
        "ping_players": True,
        "lobby_thumbnail": "https://i.imgur.com/8XxJt7z.png",
        "rank_thumbnail": "https://i.imgur.com/8XxJt7z.png",
    },
    "permissions": {
        "admin_roles": [],
        "config_roles": [],
    },
}


def _copy_defaults(guild_id: str) -> dict:
    import copy
    cfg = copy.deepcopy(_DEFAULT_SETTINGS)
    cfg["guild_id"] = guild_id
    return cfg


# ============================================================
# GUILD SETTINGS (COM CACHE INTELIGENTE)
# ============================================================

def get_guild_settings(guild_id: str) -> dict:
    if not guild_id:
        return _copy_defaults("unknown")
    
    cached = _settings_cache.get(guild_id)
    if cached is not None:
        return cached

    db = get_connection()
    doc = db["guild_settings"].find_one({"guild_id": guild_id}, {"_id": 0})
    if not doc:
        doc = _copy_defaults(guild_id)
        try:
            db["guild_settings"].insert_one(doc)
        except DuplicateKeyError:
            # Concorrência: outro processo criou
            doc = db["guild_settings"].find_one({"guild_id": guild_id}, {"_id": 0})
            if not doc:
                doc = _copy_defaults(guild_id)
    else:
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
    if not guild_id:
        return False
    
    db = get_connection()
    result = db["guild_settings"].update_one(
        {"guild_id": guild_id},
        {"$set": {path: value}},
        upsert=True
    )
    _settings_cache.invalidate(guild_id)
    return result.modified_count > 0 or result.upserted_id is not None


def invalidate_guild_settings(guild_id: str):
    """Invalida o cache de settings de uma guild específica"""
    _settings_cache.invalidate(guild_id)
    _guild_cache.invalidate(guild_id)


# ============================================================
# ECONOMIA ATÔMICA COM VALIDAÇÃO
# ============================================================

def _validate_ids(guild_id: int, user_id: int) -> Tuple[int, int]:
    """Valida e converte IDs com segurança"""
    try:
        return int(guild_id), int(user_id)
    except (ValueError, TypeError):
        raise ValueError("IDs inválidos")


def get_player_balance(guild_id: int, user_id: int) -> int:
    try:
        gid, uid = _validate_ids(guild_id, user_id)
    except ValueError:
        return 0
    
    key = f"{gid}:{uid}"
    cached = _balance_cache.get(key)
    if cached is not None:
        return cached

    db = get_connection()
    doc = db["economy_balances"].find_one(
        {"guild_id": gid, "user_id": uid},
        {"balance": 1}
    )
    bal = int(doc["balance"]) if doc and "balance" in doc else 0
    _balance_cache.set(key, bal)
    return bal


def set_player_balance(guild_id: int, user_id: int, amount: int) -> int:
    try:
        gid, uid = _validate_ids(guild_id, user_id)
    except ValueError:
        return 0
    
    amount = max(0, int(amount))
    db = get_connection()
    db["economy_balances"].update_one(
        {"guild_id": gid, "user_id": uid},
        {"$set": {"balance": amount, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    _balance_cache.invalidate(f"{gid}:{uid}")
    return amount


def add_player_balance(guild_id: int, user_id: int, amount: int, description: str = "") -> int:
    try:
        gid, uid = _validate_ids(guild_id, user_id)
    except ValueError:
        return 0
    
    amount = int(amount)
    if amount == 0:
        return get_player_balance(gid, uid)

    db = get_connection()
    
    # Operação atômica com retry em caso de conflito
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = db["economy_balances"].find_one_and_update(
                {"guild_id": gid, "user_id": uid},
                {
                    "$inc": {"balance": amount},
                    "$set": {"updated_at": datetime.utcnow()},
                    "$setOnInsert": {"guild_id": gid, "user_id": uid, "created_at": datetime.utcnow()},
                },
                upsert=True,
                return_document=True,
                projection={"balance": 1},
            )
            break
        except DuplicateKeyError:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.1 * (attempt + 1))
            continue
    else:
        result = None
    
    new_bal = int(result["balance"]) if result else amount
    _balance_cache.invalidate(f"{gid}:{uid}")

    # Inserir transação em background (fire and forget)
    try:
        db["economy_transactions"].insert_one({
            "guild_id": gid,
            "user_id": uid,
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
    try:
        gid, uid = _validate_ids(guild_id, user_id)
    except ValueError:
        return False
    
    amount = int(amount)
    if amount <= 0:
        return False

    db = get_connection()
    
    # Operação atômica com verificação de saldo
    max_retries = 3
    result = None
    for attempt in range(max_retries):
        try:
            result = db["economy_balances"].find_one_and_update(
                {
                    "guild_id": gid,
                    "user_id": uid,
                    "balance": {"$gte": amount},
                },
                {
                    "$inc": {"balance": -amount},
                    "$set": {"updated_at": datetime.utcnow()},
                },
                return_document=True,
                projection={"balance": 1},
            )
            break
        except DuplicateKeyError:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.1 * (attempt + 1))
            continue
    else:
        return False
    
    if result is None:
        return False

    _balance_cache.invalidate(f"{gid}:{uid}")
    
    try:
        db["economy_transactions"].insert_one({
            "guild_id": gid,
            "user_id": uid,
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
# PLAYERS / STATS (COM VALIDAÇÃO)
# ============================================================

_EMPTY_STATS = {
    "1v1": {"wins": 0, "losses": 0},
    "2v2": {"wins": 0, "losses": 0},
    "3v3": {"wins": 0, "losses": 0},
    "team_wins": 0,
    "team_losses": 0,
}


def get_player_stats(guild_id: str, user_id: str) -> dict:
    if not guild_id or not user_id:
        return _EMPTY_STATS.copy()
    
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
        except DuplicateKeyError:
            doc = db["players"].find_one(
                {"guild_id": str(guild_id), "user_id": str(user_id)},
                {"_id": 0}
            )
            if not doc:
                doc = {
                    "guild_id": str(guild_id),
                    "user_id": str(user_id),
                    "stats": _EMPTY_STATS.copy(),
                    "total_wins": 0,
                    "total_losses": 0,
                    "matches_played": 0,
                }

    _stats_cache.set(key, doc)
    return doc


def update_player_stats(guild_id: str, user_id: str, match_type: str, result: str, team_name: str = None) -> bool:
    if not guild_id or not user_id or match_type not in ("1v1", "2v2", "3v3", "4v4"):
        return False
    
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

    try:
        db["players"].update_one(
            {"guild_id": str(guild_id), "user_id": str(user_id)},
            {
                "$inc": inc,
                "$setOnInsert": {
                    "guild_id": str(guild_id),
                    "user_id": str(user_id),
                    "created_at": datetime.utcnow(),
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
                },
            },
            upsert=True,
        )
    except Exception:
        return False
    
    _stats_cache.invalidate(f"ps:{guild_id}:{user_id}")
    return True


def get_player_rank_stats(guild_id: str, user_id: str) -> dict:
    player = get_player_stats(guild_id, user_id)
    try:
        balance = get_player_balance(int(guild_id), int(user_id))
    except (ValueError, TypeError):
        balance = 0
    
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
    if not guild_id or match_type not in ("1v1", "2v2", "3v3", "4v4"):
        return []
    
    limit = max(1, min(int(limit), 500))
    db = get_connection()
    
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
    
    try:
        return list(db["players"].aggregate(pipeline, allowDiskUse=False))
    except Exception:
        return []


# ============================================================
# MATCHES (COM VALIDAÇÃO DE OBJECTID)
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
    try:
        get_connection()[col].insert_one(match_data)
    except Exception:
        return ""
    return match_id


def get_match(match_id: str, is_betting: bool = False) -> Optional[dict]:
    oid = safe_object_id(match_id)
    if not oid:
        return None
    
    col = "betting_matches" if is_betting else "matches"
    try:
        return get_connection()[col].find_one({"_id": oid})
    except Exception:
        return None


def get_match_by_id_str(match_id: str, is_betting: bool = False) -> Optional[dict]:
    """Busca match por string ID (sem validar ObjectId) - para compatibilidade"""
    col = "betting_matches" if is_betting else "matches"
    try:
        return get_connection()[col].find_one({"_id": match_id})
    except Exception:
        return None


def update_match(match_id: str, update_data: dict, is_betting: bool = False) -> bool:
    oid = safe_object_id(match_id)
    if not oid:
        return False
    
    col = "betting_matches" if is_betting else "matches"
    try:
        result = get_connection()[col].update_one({"_id": oid}, {"$set": update_data})
        return result.modified_count > 0
    except Exception:
        return False


def get_active_matches(guild_id: str, is_betting: bool = False) -> List[dict]:
    if not guild_id:
        return []
    
    col = "betting_matches" if is_betting else "matches"
    try:
        return list(
            get_connection()[col].find(
                {"guild_id": str(guild_id), "status": "waiting"},
                {"players": 1, "match_type": 1, "map": 1, "bet_amount": 1, "status": 1}
            ).limit(20)
        )
    except Exception:
        return []


# ============================================================
# TICKETS (COM VALIDAÇÃO)
# ============================================================

def create_ticket(ticket_data: dict) -> str:
    from bson import ObjectId
    ticket_id = str(ObjectId())
    ticket_data["_id"] = ticket_id
    ticket_data["created_at"] = datetime.utcnow()
    ticket_data["status"] = ticket_data.get("status", "active")
    try:
        get_connection()["tickets"].insert_one(ticket_data)
    except Exception:
        return ""
    return ticket_id


def get_ticket(channel_id: str) -> Optional[dict]:
    if not channel_id:
        return None
    try:
        return get_connection()["tickets"].find_one(
            {"channel_id": str(channel_id)},
            {"_id": 1, "match_id": 1, "players": 1, "status": 1, "is_betting": 1}
        )
    except Exception:
        return None


def get_ticket_by_id(ticket_id: str) -> Optional[dict]:
    oid = safe_object_id(ticket_id)
    if not oid:
        return None
    try:
        return get_connection()["tickets"].find_one({"_id": oid})
    except Exception:
        return None


def close_ticket(ticket_id: str) -> bool:
    oid = safe_object_id(ticket_id)
    if not oid:
        return False
    try:
        result = get_connection()["tickets"].update_one(
            {"_id": oid},
            {"$set": {"status": "closed", "closed_at": datetime.utcnow()}}
        )
        return result.modified_count > 0
    except Exception:
        return False


# ============================================================
# TOP PRIZES
# ============================================================

def distribute_top_prizes(guild_id: str, match_type: str) -> dict:
    if not guild_id or match_type not in ("1v1", "2v2", "3v3", "4v4"):
        return {"success": False, "message": "Parâmetros inválidos"}
    
    settings = get_guild_settings(guild_id)
    prizes_cfg = settings.get("top_prizes", {})
    if not prizes_cfg.get("enabled", True):
        return {"success": False, "message": "Prêmios desativados"}

    ranking = get_rankings(guild_id, match_type, 10)
    if not ranking:
        return {"success": False, "message": "Nenhum jogador"}

    prizes = prizes_cfg.get("prizes", {})
    distributed = {}
    
    try:
        gid_int = int(guild_id)
    except (ValueError, TypeError):
        return {"success": False, "message": "Guild ID inválido"}
    
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
            try:
                uid = int(player["user_id"])
            except (ValueError, TypeError):
                continue
            add_player_balance(
                gid_int, uid, amount,
                f"Prêmio Top {i} - {match_type}"
            )
            distributed[str(i)] = {"user_id": player["user_id"], "amount": amount}

    try:
        get_connection()["top_prizes"].insert_one({
            "guild_id": guild_id,
            "match_type": match_type,
            "distributed_at": datetime.utcnow(),
            "prizes": distributed,
        })
    except Exception:
        pass
    
    update_guild_settings(guild_id, "top_prizes.last_distribution", datetime.utcnow())
    return {"success": True, "distributed": distributed, "count": len(distributed)}


def can_distribute_prizes(guild_id: str) -> bool:
    if not guild_id:
        return False
    
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
    if not guild_id:
        return False
    return update_guild_settings(guild_id, "match_settings.mediator_roles", [int(role_id)])


def add_mediator_role(guild_id: str, role_id: int) -> bool:
    if not guild_id:
        return False
    
    settings = get_guild_settings(guild_id)
    roles = set(int(r) for r in settings.get("match_settings", {}).get("mediator_roles", []))
    roles.add(int(role_id))
    return update_guild_settings(guild_id, "match_settings.mediator_roles", list(roles))


def remove_mediator_role(guild_id: str, role_id: int) -> bool:
    if not guild_id:
        return False
    
    settings = get_guild_settings(guild_id)
    roles = [int(r) for r in settings.get("match_settings", {}).get("mediator_roles", []) if int(r) != int(role_id)]
    return update_guild_settings(guild_id, "match_settings.mediator_roles", roles)


def get_mediator_roles(guild_id: str) -> List[int]:
    if not guild_id:
        return []
    
    settings = get_guild_settings(guild_id)
    roles = settings.get("match_settings", {}).get("mediator_roles", [])
    return [int(r) for r in roles]


# ============================================================
# PREMIAÇÃO DE RANKING
# ============================================================

_VALID_REWARD_SCOPES = ("all", "top3", "top1")


def get_reward_config(guild_id: str, match_type: str) -> dict:
    if not guild_id or match_type not in ("1v1", "2v2", "3v3", "4v4"):
        return {"enabled": False, "scope": "top3", "role_id": None, "currency_amount": 0, "interval_days": 7, "last_distribution": None}
    
    settings = get_guild_settings(guild_id)
    defaults = {"enabled": False, "scope": "top3", "role_id": None, "currency_amount": 0, "interval_days": 7, "last_distribution": None}
    cfg = settings.get("rewards", {}).get(match_type, {})
    merged = {**defaults, **cfg}
    return merged


def set_reward_config(guild_id: str, match_type: str, **kwargs) -> bool:
    if not guild_id or match_type not in ("1v1", "2v2", "3v3", "4v4"):
        return False
    
    cfg = get_reward_config(guild_id, match_type)
    for k, v in kwargs.items():
        if v is not None or k in ("role_id",):
            cfg[k] = v
    if cfg.get("scope") not in _VALID_REWARD_SCOPES:
        cfg["scope"] = "top3"
    return update_guild_settings(guild_id, f"rewards.{match_type}", cfg)


def can_distribute_mode_rewards(guild_id: str, match_type: str) -> bool:
    if not guild_id or match_type not in ("1v1", "2v2", "3v3", "4v4"):
        return False
    
    cfg = get_reward_config(guild_id, match_type)
    last = cfg.get("last_distribution")
    if not last:
        return True
    
    interval = int(cfg.get("interval_days", 7))
    if isinstance(last, str):
        try:
            last = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except Exception:
            return True
    
    return datetime.utcnow() >= (last + timedelta(days=interval))


def mark_mode_rewards_distributed(guild_id: str, match_type: str):
    if guild_id and match_type in ("1v1", "2v2", "3v3", "4v4"):
        update_guild_settings(guild_id, f"rewards.{match_type}.last_distribution", datetime.utcnow())


# ============================================================
# ECONOMY CONFIG
# ============================================================

def get_economy_config(guild_id: int) -> dict:
    try:
        gid = int(guild_id)
    except (ValueError, TypeError):
        return {"currency_name": "Moedas", "currency_emoji": "💰", "daily_bonus": 100}
    
    settings = get_guild_settings(str(gid))
    cur = settings.get("currency", {})
    return {
        "currency_name": cur.get("name", "Moedas"),
        "currency_emoji": cur.get("symbol", "💰"),
        "daily_bonus": cur.get("daily_bonus", 100),
    }


# ============================================================
# LIMPEZA E MANUTENÇÃO
# ============================================================

def cleanup_idle_connection():
    _pool_monitor.check_and_cleanup()


def clear_all_caches():
    _settings_cache.clear()
    _balance_cache.clear()
    _stats_cache.clear()
    _guild_cache.clear()
    gc.collect()


def clear_user_cache(guild_id: str, user_id: str):
    """Limpa cache de um usuário específico"""
    _balance_cache.invalidate(f"{guild_id}:{user_id}")
    _stats_cache.invalidate(f"ps:{guild_id}:{user_id}")


def check_db_health() -> bool:
    try:
        client = get_mongo_client()
        client.admin.command("ping", serverSelectionTimeoutMS=2000)
        return True
    except Exception:
        return False


def get_cache_stats() -> dict:
    return {
        "settings": _settings_cache.stats(),
        "balance": _balance_cache.stats(),
        "stats": _stats_cache.stats(),
        "guild": _guild_cache.stats(),
    }


def close_connections():
    global _client, _db
    try:
        if _client:
            _client.close()
            _client = None
            _db = None
    except Exception:
        pass
    clear_all_caches()


atexit.register(close_connections)
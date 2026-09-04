# ============================================================
# DATABASE.PY - BANCO DE DADOS COMPLETO
# ============================================================

import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from config import MONGODB_URL, DB_NAME

# ============================================================
# CONEXÃO
# ============================================================

def get_mongo_client():
    max_attempts = 3
    attempt = 0
    
    while attempt < max_attempts:
        try:
            print(f"🔄 Tentativa {attempt+1}/{max_attempts}...")
            client = MongoClient(
                MONGODB_URL,
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
                socketTimeoutMS=30000,
                retryWrites=True,
                w='majority'
            )
            client.admin.command('ping')
            print("✅ Conectado ao MongoDB!")
            return client
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            attempt += 1
            print(f"❌ Tentativa {attempt} falhou: {e}")
            if attempt < max_attempts:
                time.sleep(5)
    
    raise ConnectionError("❌ Não foi possível conectar ao MongoDB")

client = get_mongo_client()
db = client[DB_NAME]

def get_connection():
    return db

def init_db():
    print(f"✅ Banco inicializado: {DB_NAME}")
    return db

# ============================================================
# COLEÇÕES
# ============================================================

# Economia
economy_config = db["economy_config"]
economy_balances = db["economy_balances"]
economy_transactions = db["economy_transactions"]

# Rank System
guild_settings = db["guild_settings"]
players = db["players"]
matches = db["matches"]
betting_matches = db["betting_matches"]
tickets = db["tickets"]
top_prizes = db["top_prizes"]
mediator_roles = db["mediator_roles"]

# ============================================================
# FUNÇÕES DE CONFIGURAÇÃO
# ============================================================

def get_guild_settings(guild_id: str) -> Dict:
    settings = guild_settings.find_one({"guild_id": guild_id})
    if not settings:
        default = {
            "guild_id": guild_id,
            "currency": {"name": "Moedas", "symbol": "💰", "daily_bonus": 100},
            "ranked": {
                "enabled": True,
                "win_bonus": 50,
                "loss_penalty": 10,
                "entry_fee": 0,
                "allowed_roles": [],
                "max_matches_per_user": 3,
                "maps": ["Arena", "Castelo", "Floresta", "Deserto"]
            },
            "betting": {
                "enabled": True,
                "min_bet": 100,
                "max_bet": 10000,
                "win_multiplier": 2.0,
                "tax_percent": 5.0,
                "max_players": 6,
                "allowed_roles": []
            },
            "top_prizes": {
                "enabled": True,
                "interval_days": 7,
                "prizes": {"1": 10000, "2": 5000, "3": 2500, "4_10": 1000}
            },
            "match_settings": {
                "auto_ticket": True,
                "ticket_category": None,
                "ticket_name_template": "🎮-{tipo}-{match_id}",
                "mediator_roles": [],
                "timeout_minutes": 30,
                "lobby_timeout": 600
            },
            "customization": {
                "embed_color": 0x00ff00,
                "embed_footer": "Rank System v3.0",
                "dm_notifications": True,
                "ping_players": True
            }
        }
        guild_settings.insert_one(default)
        return default
    return settings

def update_guild_settings(guild_id: str, path: str, value: Any) -> bool:
    result = guild_settings.update_one(
        {"guild_id": guild_id},
        {"$set": {path: value}}
    )
    return result.modified_count > 0

# ============================================================
# FUNÇÕES DE ECONOMIA
# ============================================================

def get_player_balance(guild_id: int, user_id: int) -> int:
    doc = economy_balances.find_one({"guild_id": guild_id, "user_id": user_id})
    return doc.get("balance", 0) if doc else 0

def set_player_balance(guild_id: int, user_id: int, amount: int):
    economy_balances.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": {"balance": max(0, amount)}},
        upsert=True
    )

def add_player_balance(guild_id: int, user_id: int, amount: int, description: str = ""):
    current = get_player_balance(guild_id, user_id)
    new_balance = current + amount
    set_player_balance(guild_id, user_id, new_balance)
    economy_transactions.insert_one({
        "guild_id": guild_id,
        "user_id": user_id,
        "type": "add",
        "amount": amount,
        "description": description,
        "timestamp": datetime.utcnow()
    })
    return new_balance

def remove_player_balance(guild_id: int, user_id: int, amount: int, description: str = ""):
    current = get_player_balance(guild_id, user_id)
    if current < amount:
        return False
    new_balance = current - amount
    set_player_balance(guild_id, user_id, new_balance)
    economy_transactions.insert_one({
        "guild_id": guild_id,
        "user_id": user_id,
        "type": "remove",
        "amount": amount,
        "description": description,
        "timestamp": datetime.utcnow()
    })
    return True

# ============================================================
# FUNÇÕES DE JOGADORES
# ============================================================

def get_player_stats(guild_id: str, user_id: str) -> Dict:
    player = players.find_one({"guild_id": guild_id, "user_id": user_id})
    if not player:
        player = {
            "guild_id": guild_id,
            "user_id": user_id,
            "stats": {
                "1v1": {"wins": 0, "losses": 0},
                "2v2": {"wins": 0, "losses": 0},
                "3v3": {"wins": 0, "losses": 0},
                "team_wins": 0,
                "team_losses": 0
            },
            "total_wins": 0,
            "total_losses": 0,
            "matches_played": 0,
            "created_at": datetime.utcnow()
        }
        players.insert_one(player)
    return player

def update_player_stats(guild_id: str, user_id: str, match_type: str, result: str, team_name: str = None):
    player = get_player_stats(guild_id, user_id)
    
    if result == "win":
        player["stats"][match_type]["wins"] += 1
        player["total_wins"] += 1
        if team_name:
            player["stats"]["team_wins"] += 1
    elif result == "loss":
        player["stats"][match_type]["losses"] += 1
        player["total_losses"] += 1
        if team_name:
            player["stats"]["team_losses"] += 1
    
    player["matches_played"] += 1
    
    players.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": player}
    )
    return True

def get_player_rank_stats(guild_id: str, user_id: str) -> Dict:
    player = get_player_stats(guild_id, user_id)
    balance = get_player_balance(int(guild_id), int(user_id))
    
    return {
        "total_wins": player.get("total_wins", 0),
        "total_losses": player.get("total_losses", 0),
        "matches_played": player.get("matches_played", 0),
        "stats": player.get("stats", {}),
        "balance": balance,
        "team_wins": player.get("stats", {}).get("team_wins", 0),
        "team_losses": player.get("stats", {}).get("team_losses", 0)
    }

def get_rankings(guild_id: str, match_type: str, limit: int = 50) -> List[Dict]:
    pipeline = [
        {"$match": {"guild_id": guild_id}},
        {"$project": {
            "user_id": 1,
            "wins": f"$stats.{match_type}.wins",
            "losses": f"$stats.{match_type}.losses",
            "total": {"$add": [f"$stats.{match_type}.wins", f"$stats.{match_type}.losses"]}
        }},
        {"$match": {"total": {"$gt": 0}}},
        {"$sort": {"wins": -1, "losses": 1}},
        {"$limit": limit}
    ]
    return list(players.aggregate(pipeline))

# ============================================================
# FUNÇÕES DE PARTIDAS
# ============================================================

def create_match(match_data: Dict, is_betting: bool = False) -> str:
    from bson import ObjectId
    match_id = str(ObjectId())
    match_data["_id"] = match_id
    match_data["created_at"] = datetime.utcnow()
    match_data["status"] = "waiting"
    match_data["is_betting"] = is_betting
    match_data["players"] = []
    match_data["teams"] = {}
    match_data["team_names"] = {}
    
    collection = betting_matches if is_betting else matches
    collection.insert_one(match_data)
    return match_id

def get_match(match_id: str, is_betting: bool = False) -> Optional[Dict]:
    collection = betting_matches if is_betting else matches
    return collection.find_one({"_id": match_id})

def update_match(match_id: str, update_data: Dict, is_betting: bool = False) -> bool:
    collection = betting_matches if is_betting else matches
    result = collection.update_one({"_id": match_id}, {"$set": update_data})
    return result.modified_count > 0

def get_active_matches(guild_id: str, is_betting: bool = False) -> List[Dict]:
    collection = betting_matches if is_betting else matches
    return list(collection.find({
        "guild_id": guild_id,
        "status": "waiting"
    }))

# ============================================================
# FUNÇÕES DE TICKETS
# ============================================================

def create_ticket(ticket_data: Dict) -> str:
    from bson import ObjectId
    ticket_id = str(ObjectId())
    ticket_data["_id"] = ticket_id
    ticket_data["created_at"] = datetime.utcnow()
    ticket_data["status"] = "active"
    tickets.insert_one(ticket_data)
    return ticket_id

def get_ticket(channel_id: str) -> Optional[Dict]:
    return tickets.find_one({"channel_id": channel_id})

def close_ticket(ticket_id: str) -> bool:
    result = tickets.update_one(
        {"_id": ticket_id},
        {"$set": {"status": "closed", "closed_at": datetime.utcnow()}}
    )
    return result.modified_count > 0

# ============================================================
# FUNÇÕES DE PRÊMIOS
# ============================================================

def distribute_top_prizes(guild_id: str, match_type: str) -> Dict:
    settings = get_guild_settings(guild_id)
    prizes_config = settings.get("top_prizes", {})
    
    if not prizes_config.get("enabled", True):
        return {"success": False, "message": "Prêmios desativados"}
    
    ranking = get_rankings(guild_id, match_type, 10)
    if not ranking:
        return {"success": False, "message": "Nenhum jogador encontrado"}
    
    prizes = prizes_config.get("prizes", {})
    distributed = {}
    
    for i, player in enumerate(ranking, 1):
        if i == 1:
            amount = prizes.get("1", 10000)
        elif i == 2:
            amount = prizes.get("2", 5000)
        elif i == 3:
            amount = prizes.get("3", 2500)
        else:
            amount = prizes.get("4_10", 1000)
        
        if amount > 0:
            add_player_balance(
                int(guild_id),
                int(player["user_id"]),
                amount,
                f"🏆 Prêmio Top {i} - {match_type}"
            )
            distributed[str(i)] = {"user_id": player["user_id"], "amount": amount}
    
    top_prizes.insert_one({
        "guild_id": guild_id,
        "match_type": match_type,
        "distributed_at": datetime.utcnow(),
        "ranking": ranking[:10],
        "prizes": distributed
    })
    
    update_guild_settings(guild_id, "top_prizes.last_distribution", datetime.utcnow())
    
    return {"success": True, "distributed": distributed, "count": len(distributed)}

def can_distribute_prizes(guild_id: str) -> bool:
    settings = get_guild_settings(guild_id)
    last_dist = settings.get("top_prizes", {}).get("last_distribution")
    if not last_dist:
        return True
    interval = settings.get("top_prizes", {}).get("interval_days", 7)
    return datetime.utcnow() >= (last_dist + timedelta(days=interval))

# ============================================================
# FUNÇÕES DE MEDIADORES
# ============================================================

def set_mediator_role(guild_id: str, role_id: int) -> bool:
    return update_guild_settings(guild_id, "match_settings.mediator_roles", [role_id])

def get_mediator_roles(guild_id: str) -> List[int]:
    settings = get_guild_settings(guild_id)
    return settings.get("match_settings", {}).get("mediator_roles", [])

print("✅ Banco de dados inicializado com sucesso!")
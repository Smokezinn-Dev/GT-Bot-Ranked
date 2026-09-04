# ============================================================
# DATABASE.PY - BANCO DE DADOS COMPLETO
# SISTEMA RANKED/APOSTADO + ECONOMIA INTEGRADA
# ============================================================

import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from bson import ObjectId

# ============================================================
# IMPORTA CONFIG
# ============================================================

try:
    from config import MONGODB_URL, DB_NAME
except ImportError:
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb+srv://gleicyferreira899_db_user:Q57eSQXyzUoWQxw4@cluster0.xhwrpcd.mongodb.net/?appName=Cluster0")
    DB_NAME = os.getenv("DB_NAME", "gt_bot")

# ============================================================
# CONEXÃO COM MONGODB
# ============================================================

def get_mongo_client():
    """Conecta ao MongoDB com tentativas"""
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
                w='majority',
                maxPoolSize=10,
                minPoolSize=1
            )
            client.admin.command('ping')
            print("✅ Conectado ao MongoDB com sucesso!")
            return client
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            attempt += 1
            print(f"❌ Tentativa {attempt} falhou: {e}")
            if attempt < max_attempts:
                print("⏳ Aguardando 5 segundos...")
                time.sleep(5)
    
    raise ConnectionError("❌ Não foi possível conectar ao MongoDB após 3 tentativas.")

client = get_mongo_client()
db = client[DB_NAME]

def get_connection():
    """Retorna a conexão com o banco"""
    return db

def init_db():
    """Inicializa o banco de dados"""
    print(f"✅ Banco de dados inicializado: {DB_NAME}")
    print(f"📊 Coleções: {len(db.list_collection_names())}")
    return db

# ============================================================
# COLEÇÕES
# ============================================================

# ===== ECONOMIA =====
economy_config = db["economy_config"]
economy_balances = db["economy_balances"]
economy_transactions = db["economy_transactions"]
economy_shop = db["economy_shop"]
economy_purchases = db["economy_purchases"]

# ===== RANK SYSTEM =====
guild_settings = db["guild_settings"]
players = db["players"]
matches = db["matches"]
betting_matches = db["betting_matches"]
tickets = db["tickets"]
top_prizes = db["top_prizes"]
mediator_roles = db["mediator_roles"]

# ============================================================
# FUNÇÕES DE CONFIGURAÇÃO DO SERVIDOR
# ============================================================

def get_guild_settings(guild_id: str) -> Dict:
    """Obtém configurações do servidor (100% customizável)"""
    settings = guild_settings.find_one({"guild_id": guild_id})
    
    if not settings:
        # Configuração padrão
        default_settings = {
            "guild_id": guild_id,
            "currency": {
                "name": "Moedas",
                "symbol": "💰",
                "daily_bonus": 100,
                "bonus_multiplier": 1.0
            },
            "ranked": {
                "enabled": True,
                "win_bonus": 50,
                "loss_penalty": 10,
                "entry_fee": 0,
                "allowed_roles": [],
                "max_matches_per_user": 3,
                "maps": ["Arena", "Castelo", "Floresta", "Deserto", "Vulcão"]
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
                "prizes": {
                    "1": 10000,
                    "2": 5000,
                    "3": 2500,
                    "4_10": 1000
                },
                "last_distribution": None
            },
            "match_settings": {
                "auto_ticket": True,
                "ticket_category": None,
                "ticket_name_template": "🎮-{tipo}-{match_id}",
                "mediator_roles": [],
                "timeout_minutes": 30,
                "lobby_timeout": 600
            },
            "permissions": {
                "admin_roles": [],
                "mod_roles": [],
                "mediator_roles": []
            },
            "customization": {
                "embed_color": 0x00ff00,
                "embed_footer": "Rank System v3.0",
                "dm_notifications": True,
                "ping_players": True
            }
        }
        guild_settings.insert_one(default_settings)
        return default_settings
    
    return settings

def update_guild_settings(guild_id: str, path: str, value: Any) -> bool:
    """Atualiza configuração customizável"""
    result = guild_settings.update_one(
        {"guild_id": guild_id},
        {"$set": {path: value}}
    )
    return result.modified_count > 0

# ============================================================
# FUNÇÕES DE ECONOMIA
# ============================================================

def get_economy_config(guild_id: int) -> Dict:
    """Obtém configuração da economia"""
    config = economy_config.find_one({"guild_id": guild_id})
    if not config:
        default = {
            "guild_id": guild_id,
            "currency_name": "Moeda",
            "currency_emoji": "💰",
            "daily_bonus": 100,
            "staff_role": 0,
            "log_channel": 0,
            "tax_rate": 0,
            "min_transfer": 1,
            "max_transfer": 1000000,
            "bonus_multiplier": 1.0
        }
        economy_config.insert_one(default)
        return default
    return config

def get_player_balance(guild_id: int, user_id: int) -> int:
    """Obtém saldo de um jogador"""
    doc = economy_balances.find_one({"guild_id": guild_id, "user_id": user_id})
    return doc.get("balance", 0) if doc else 0

def set_player_balance(guild_id: int, user_id: int, amount: int):
    """Define o saldo de um jogador"""
    economy_balances.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": {"balance": max(0, amount)}},
        upsert=True
    )

def add_player_balance(guild_id: int, user_id: int, amount: int, description: str = "") -> int:
    """Adiciona saldo a um jogador"""
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

def remove_player_balance(guild_id: int, user_id: int, amount: int, description: str = "") -> bool:
    """Remove saldo de um jogador"""
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

def transfer_player_balance(guild_id: int, from_user: int, to_user: int, amount: int, description: str = "") -> bool:
    """Transfere saldo entre jogadores"""
    if not remove_player_balance(guild_id, from_user, amount, f"Transferência para {to_user}"):
        return False
    
    add_player_balance(guild_id, to_user, amount, f"Transferência de {from_user}")
    
    economy_transactions.insert_one({
        "guild_id": guild_id,
        "user_id": from_user,
        "target_user_id": to_user,
        "type": "transfer",
        "amount": amount,
        "description": description,
        "timestamp": datetime.utcnow()
    })
    return True

# ============================================================
# FUNÇÕES DE JOGADORES (RANK SYSTEM)
# ============================================================

def get_player_stats(guild_id: str, user_id: str) -> Dict:
    """Obtém estatísticas de um jogador"""
    player = players.find_one({"guild_id": guild_id, "user_id": user_id})
    
    if not player:
        player = {
            "guild_id": guild_id,
            "user_id": user_id,
            "stats": {
                "1v1": {"wins": 0, "losses": 0},
                "2v2": {"wins": 0, "losses": 0},
                "3v3": {"wins": 0, "losses": 0}
            },
            "team_stats": {
                "wins": 0,
                "losses": 0
            },
            "total_wins": 0,
            "total_losses": 0,
            "matches_played": 0,
            "current_streak": 0,
            "best_streak": 0,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow()
        }
        players.insert_one(player)
    
    return player

def update_player_stats(guild_id: str, user_id: str, match_type: str, result: str, team_name: str = None) -> bool:
    """Atualiza estatísticas de um jogador"""
    player = get_player_stats(guild_id, user_id)
    
    # Atualiza estatísticas por tipo
    if match_type in player["stats"]:
        if result == "win":
            player["stats"][match_type]["wins"] += 1
            player["total_wins"] += 1
            player["current_streak"] = max(1, player["current_streak"] + 1)
            if player["current_streak"] > player["best_streak"]:
                player["best_streak"] = player["current_streak"]
        elif result == "loss":
            player["stats"][match_type]["losses"] += 1
            player["total_losses"] += 1
            player["current_streak"] = min(-1, player["current_streak"] - 1)
    
    # Atualiza estatísticas de time
    if team_name:
        if result == "win":
            player["team_stats"]["wins"] += 1
        elif result == "loss":
            player["team_stats"]["losses"] += 1
    
    player["matches_played"] += 1
    player["last_active"] = datetime.utcnow()
    
    players.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": player}
    )
    return True

def get_player_rank_stats(guild_id: str, user_id: str) -> Dict:
    """Obtém estatísticas completas para o ranking"""
    player = get_player_stats(guild_id, user_id)
    balance = get_player_balance(int(guild_id), int(user_id))
    
    return {
        "total_wins": player.get("total_wins", 0),
        "total_losses": player.get("total_losses", 0),
        "matches_played": player.get("matches_played", 0),
        "current_streak": player.get("current_streak", 0),
        "best_streak": player.get("best_streak", 0),
        "stats": player.get("stats", {}),
        "team_stats": player.get("team_stats", {}),
        "balance": balance
    }

def get_rankings(guild_id: str, match_type: str, limit: int = 50) -> List[Dict]:
    """Obtém ranking de um tipo específico"""
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

def get_team_rankings(guild_id: str, limit: int = 20) -> List[Dict]:
    """Obtém ranking de times (2v2 e 3v3 combinados)"""
    pipeline = [
        {"$match": {"guild_id": guild_id}},
        {"$project": {
            "user_id": 1,
            "wins": "$team_stats.wins",
            "losses": "$team_stats.losses",
            "total": {"$add": ["$team_stats.wins", "$team_stats.losses"]}
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
    """Cria uma nova partida"""
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
    """Obtém uma partida pelo ID"""
    collection = betting_matches if is_betting else matches
    return collection.find_one({"_id": match_id})

def update_match(match_id: str, update_data: Dict, is_betting: bool = False) -> bool:
    """Atualiza uma partida"""
    collection = betting_matches if is_betting else matches
    result = collection.update_one({"_id": match_id}, {"$set": update_data})
    return result.modified_count > 0

def delete_match(match_id: str, is_betting: bool = False) -> bool:
    """Deleta uma partida"""
    collection = betting_matches if is_betting else matches
    result = collection.delete_one({"_id": match_id})
    return result.deleted_count > 0

def get_active_matches(guild_id: str, is_betting: bool = False) -> List[Dict]:
    """Obtém partidas ativas de um servidor"""
    collection = betting_matches if is_betting else matches
    return list(collection.find({
        "guild_id": guild_id,
        "status": "waiting"
    }))

def get_finished_matches(guild_id: str, is_betting: bool = False, limit: int = 20) -> List[Dict]:
    """Obtém partidas finalizadas de um servidor"""
    collection = betting_matches if is_betting else matches
    return list(collection.find({
        "guild_id": guild_id,
        "status": "finished"
    }).sort("finished_at", -1).limit(limit))

# ============================================================
# FUNÇÕES DE TICKETS
# ============================================================

def create_ticket(ticket_data: Dict) -> str:
    """Cria um novo ticket"""
    ticket_id = str(ObjectId())
    ticket_data["_id"] = ticket_id
    ticket_data["created_at"] = datetime.utcnow()
    ticket_data["status"] = "active"
    tickets.insert_one(ticket_data)
    return ticket_id

def get_ticket(ticket_id: str) -> Optional[Dict]:
    """Obtém um ticket pelo ID"""
    return tickets.find_one({"_id": ticket_id})

def get_ticket_by_channel(channel_id: str) -> Optional[Dict]:
    """Obtém um ticket pelo ID do canal"""
    return tickets.find_one({"channel_id": channel_id})

def update_ticket(ticket_id: str, update_data: Dict) -> bool:
    """Atualiza um ticket"""
    result = tickets.update_one({"_id": ticket_id}, {"$set": update_data})
    return result.modified_count > 0

def close_ticket(ticket_id: str) -> bool:
    """Fecha um ticket"""
    result = tickets.update_one(
        {"_id": ticket_id},
        {"$set": {"status": "closed", "closed_at": datetime.utcnow()}}
    )
    return result.modified_count > 0

def delete_ticket(ticket_id: str) -> bool:
    """Deleta um ticket"""
    result = tickets.delete_one({"_id": ticket_id})
    return result.deleted_count > 0

# ============================================================
# FUNÇÕES DE MEDIADORES
# ============================================================

def set_mediator_role(guild_id: str, role_id: int) -> bool:
    """Define um cargo como mediador"""
    return update_guild_settings(guild_id, "match_settings.mediator_roles", [role_id])

def add_mediator_role(guild_id: str, role_id: int) -> bool:
    """Adiciona um cargo à lista de mediadores"""
    settings = get_guild_settings(guild_id)
    mediator_roles = settings.get("match_settings", {}).get("mediator_roles", [])
    
    if role_id not in mediator_roles:
        mediator_roles.append(role_id)
        return update_guild_settings(guild_id, "match_settings.mediator_roles", mediator_roles)
    return False

def remove_mediator_role(guild_id: str, role_id: int) -> bool:
    """Remove um cargo da lista de mediadores"""
    settings = get_guild_settings(guild_id)
    mediator_roles = settings.get("match_settings", {}).get("mediator_roles", [])
    
    if role_id in mediator_roles:
        mediator_roles.remove(role_id)
        return update_guild_settings(guild_id, "match_settings.mediator_roles", mediator_roles)
    return False

def get_mediator_roles(guild_id: str) -> List[int]:
    """Obtém a lista de cargos mediadores"""
    settings = get_guild_settings(guild_id)
    return settings.get("match_settings", {}).get("mediator_roles", [])

def is_mediator(member: discord.Member) -> bool:
    """Verifica se um membro é mediador"""
    if not member.guild:
        return False
    
    guild_id = str(member.guild.id)
    mediator_roles = get_mediator_roles(guild_id)
    
    for role in member.roles:
        if role.id in mediator_roles:
            return True
    
    return False

# ============================================================
# FUNÇÕES DE PRÊMIOS
# ============================================================

def distribute_top_prizes(guild_id: str, match_type: str) -> Dict:
    """Distribui prêmios para o top 10"""
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
            distributed[str(i)] = {
                "user_id": player["user_id"],
                "amount": amount
            }
    
    # Registrar distribuição
    top_prizes.insert_one({
        "guild_id": guild_id,
        "match_type": match_type,
        "distributed_at": datetime.utcnow(),
        "ranking": ranking[:10],
        "prizes": distributed
    })
    
    # Atualizar última distribuição
    update_guild_settings(
        guild_id,
        "top_prizes.last_distribution",
        datetime.utcnow()
    )
    
    return {
        "success": True,
        "distributed": distributed,
        "count": len(distributed)
    }

def can_distribute_prizes(guild_id: str) -> bool:
    """Verifica se já pode distribuir prêmios novamente"""
    settings = get_guild_settings(guild_id)
    last_dist = settings.get("top_prizes", {}).get("last_distribution")
    
    if not last_dist:
        return True
    
    interval = settings.get("top_prizes", {}).get("interval_days", 7)
    next_dist = last_dist + timedelta(days=interval)
    
    return datetime.utcnow() >= next_dist

def get_last_distribution(guild_id: str) -> Optional[Dict]:
    """Obtém a última distribuição de prêmios"""
    return top_prizes.find_one(
        {"guild_id": guild_id},
        sort=[("distributed_at", -1)]
    )

# ============================================================
# FUNÇÕES DE LIMPEZA
# ============================================================

def cleanup_expired_matches(hours: int = 24) -> int:
    """Remove partidas expiradas"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    # Partidas RANKED expiradas
    result1 = matches.delete_many({
        "status": "waiting",
        "created_at": {"$lt": cutoff}
    })
    
    # Partidas APOSTADO expiradas
    result2 = betting_matches.delete_many({
        "status": "waiting",
        "created_at": {"$lt": cutoff}
    })
    
    total = result1.deleted_count + result2.deleted_count
    if total > 0:
        print(f"🧹 {total} partidas expiradas removidas")
    
    return total

def cleanup_closed_tickets(hours: int = 168) -> int:
    """Remove tickets fechados antigos (7 dias padrão)"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = tickets.delete_many({
        "status": "closed",
        "closed_at": {"$lt": cutoff}
    })
    
    if result.deleted_count > 0:
        print(f"🧹 {result.deleted_count} tickets antigos removidos")
    
    return result.deleted_count

# ============================================================
# EXPORTAÇÕES
# ============================================================

print("✅ Banco de dados inicializado com sucesso!")
print(f"📊 Total de coleções: {len(db.list_collection_names())}")

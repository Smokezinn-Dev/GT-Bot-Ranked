# ============================================================
# DATABASE.PY - BANCO DE DADOS COM CONFIGURAÇÕES CUSTOMIZÁVEIS
# ============================================================

import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

try:
    from config import config
    MONGODB_URI = config.MONGODB_URI
    DB_NAME = config.DB_NAME
except ImportError:
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb+srv://gleicyferreira899_db_user:Q57eSQXyzUoWQxw4@cluster0.xhwrpcd.mongodb.net/?appName=Cluster0')
    DB_NAME = os.getenv('DB_NAME', 'gt_bot')

# ============================================================
# CONEXÃO
# ============================================================

def get_mongo_client():
    max_attempts = 3
    attempt = 0
    
    while attempt < max_attempts:
        try:
            print(f"🔄 Tentando conectar ao MongoDB (tentativa {attempt+1}/{max_attempts})...")
            client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
                socketTimeoutMS=30000,
                retryWrites=True,
                w='majority',
                maxPoolSize=5,
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
    return db

def init_db():
    print(f"✅ Banco de dados inicializado: {DB_NAME}")
    return db

# ============================================================
# COLEÇÕES - ECONOMIA
# ============================================================

economy_config = db["economy_config"]
economy_balances = db["economy_balances"]
economy_transactions = db["economy_transactions"]
economy_shop = db["economy_shop"]
economy_purchases = db["economy_purchases"]
economy_giveaways = db["economy_giveaways"]

# ============================================================
# COLEÇÕES - RANK SYSTEM
# ============================================================

server_configs = db["server_configs"]
players = db["players"]
matches = db["matches"]
tickets = db["tickets"]
betting_matches = db["betting_matches"]  # Partidas apostadas (não contam no rank)
top_prizes = db["top_prizes"]  # Histórico de prêmios

# ============================================================
# COLEÇÕES - CONFIGURAÇÕES CUSTOMIZÁVEIS
# ============================================================

guild_settings = db["guild_settings"]  # Configurações 100% customizáveis

# ============================================================
# FUNÇÕES DE CONFIGURAÇÃO DO SERVIDOR (100% CUSTOMIZÁVEL)
# ============================================================

def get_guild_settings(guild_id: str) -> Dict:
    """Obtém configurações customizáveis do servidor"""
    settings = guild_settings.find_one({'guild_id': guild_id})
    
    if not settings:
        # Configuração padrão 100% customizável
        default_settings = {
            'guild_id': guild_id,
            'currency': {
                'name': 'Moedas',
                'symbol': '💰',
                'daily_bonus': 100,
                'bonus_multiplier': 1.0
            },
            'ranked': {
                'enabled': True,
                'win_bonus': 50,
                'loss_penalty': 10,
                'entry_fee': 0,
                'allowed_roles': [],
                'max_matches_per_user': 3
            },
            'betting': {
                'enabled': True,
                'min_bet': 100,
                'max_bet': 10000,
                'win_multiplier': 2.0,
                'tax_percent': 5.0,
                'max_players': 6,
                'allowed_roles': []
            },
            'top_prizes': {
                'enabled': True,
                'interval_days': 7,
                'prizes': {
                    '1': 10000,
                    '2': 5000,
                    '3': 2500,
                    '4_10': 1000
                },
                'last_distribution': None
            },
            'match_settings': {
                'auto_ticket': True,
                'ticket_category': None,
                'ticket_name_template': '🎮-{tipo}-{match_id}',
                'mediator_roles': [],
                'timeout_minutes': 30,
                'maps': [],
                'lobby_timeout': 600
            },
            'permissions': {
                'admin_roles': [],
                'mod_roles': [],
                'mediator_roles': []
            },
            'customization': {
                'embed_color': 0x00ff00,
                'embed_footer': 'Rank System v3.0',
                'locale': 'pt-BR',
                'dm_notifications': True,
                'ping_players': True
            }
        }
        guild_settings.insert_one(default_settings)
        return default_settings
    
    return settings

def update_guild_settings(guild_id: str, path: str, value: Any) -> bool:
    """Atualiza configuração customizável"""
    result = guild_settings.update_one(
        {'guild_id': guild_id},
        {'$set': {path: value}}
    )
    return result.modified_count > 0

# ============================================================
# FUNÇÕES DE ECONOMIA
# ============================================================

def get_economy_config(guild_id: int) -> Dict:
    config = economy_config.find_one({"guild_id": guild_id})
    if not config:
        default_config = {
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
        economy_config.insert_one(default_config)
        return default_config
    return config

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
# FUNÇÕES DO RANK SYSTEM
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
                "3v3": {"wins": 0, "losses": 0}
            },
            "total_wins": 0,
            "total_losses": 0,
            "matches_played": 0,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow()
        }
        players.insert_one(player)
    return player

def update_player_stats(guild_id: str, user_id: str, match_type: str, result: str) -> bool:
    player = get_player_stats(guild_id, user_id)
    if result == 'win':
        player['stats'][match_type]['wins'] += 1
        player['total_wins'] += 1
    elif result == 'loss':
        player['stats'][match_type]['losses'] += 1
        player['total_losses'] += 1
    player['matches_played'] += 1
    player['last_active'] = datetime.utcnow()
    result = players.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": player}
    )
    return result.modified_count > 0

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
    cursor = players.aggregate(pipeline)
    return list(cursor)

# ============================================================
# FUNÇÕES DE MATCHES (RANKED E BETTING)
# ============================================================

def create_match(match_data: Dict, is_betting: bool = False) -> str:
    from bson import ObjectId
    match_id = str(ObjectId())
    match_data['_id'] = match_id
    match_data['created_at'] = datetime.utcnow()
    match_data['status'] = 'waiting'
    match_data['is_betting'] = is_betting
    match_data['players'] = []
    match_data['teams'] = {}
    
    collection = betting_matches if is_betting else matches
    collection.insert_one(match_data)
    return match_id

def get_match(match_id: str, is_betting: bool = False) -> Optional[Dict]:
    collection = betting_matches if is_betting else matches
    return collection.find_one({'_id': match_id})

def update_match(match_id: str, update_data: Dict, is_betting: bool = False) -> bool:
    collection = betting_matches if is_betting else matches
    result = collection.update_one(
        {'_id': match_id},
        {'$set': update_data}
    )
    return result.modified_count > 0

# ============================================================
# FUNÇÕES DE TICKETS
# ============================================================

def create_ticket(ticket_data: Dict) -> str:
    from bson import ObjectId
    ticket_id = str(ObjectId())
    ticket_data['_id'] = ticket_id
    ticket_data['created_at'] = datetime.utcnow()
    ticket_data['status'] = 'active'
    tickets.insert_one(ticket_data)
    return ticket_id

def get_ticket(channel_id: str) -> Optional[Dict]:
    return tickets.find_one({'channel_id': channel_id})

def close_ticket(ticket_id: str) -> bool:
    result = tickets.update_one(
        {'_id': ticket_id},
        {'$set': {'status': 'closed', 'closed_at': datetime.utcnow()}}
    )
    return result.modified_count > 0

# ============================================================
# FUNÇÕES DE PRÊMIOS POR TOP
# ============================================================

def distribute_top_prizes(guild_id: str, match_type: str) -> Dict:
    """Distribui prêmios para o top 10"""
    settings = get_guild_settings(guild_id)
    prizes_config = settings.get('top_prizes', {})
    
    if not prizes_config.get('enabled', True):
        return {'success': False, 'message': 'Prêmios desativados'}
    
    # Buscar ranking
    ranking = get_rankings(guild_id, match_type, 10)
    
    if not ranking:
        return {'success': False, 'message': 'Nenhum jogador encontrado'}
    
    prizes = prizes_config.get('prizes', {})
    distributed = {}
    
    for i, player in enumerate(ranking, 1):
        if i == 1:
            amount = prizes.get('1', 10000)
        elif i == 2:
            amount = prizes.get('2', 5000)
        elif i == 3:
            amount = prizes.get('3', 2500)
        else:
            amount = prizes.get('4_10', 1000)
        
        if amount > 0:
            add_player_balance(
                int(guild_id),
                int(player['user_id']),
                amount,
                f"🏆 Prêmio de Top {i} - {match_type}"
            )
            distributed[str(i)] = {
                'user_id': player['user_id'],
                'amount': amount
            }
    
    # Registrar distribuição
    top_prizes.insert_one({
        'guild_id': guild_id,
        'match_type': match_type,
        'distributed_at': datetime.utcnow(),
        'ranking': ranking[:10],
        'prizes': distributed
    })
    
    # Atualizar última distribuição
    update_guild_settings(
        guild_id,
        'top_prizes.last_distribution',
        datetime.utcnow()
    )
    
    return {
        'success': True,
        'distributed': distributed,
        'count': len(distributed)
    }

def can_distribute_prizes(guild_id: str) -> bool:
    """Verifica se já pode distribuir prêmios novamente"""
    settings = get_guild_settings(guild_id)
    last_dist = settings.get('top_prizes', {}).get('last_distribution')
    
    if not last_dist:
        return True
    
    interval = settings.get('top_prizes', {}).get('interval_days', 7)
    next_dist = last_dist + timedelta(days=interval)
    
    return datetime.utcnow() >= next_dist

# ============================================================
# EXPORTAÇÕES
# ============================================================

__all__ = [
    'get_connection',
    'init_db',
    'get_guild_settings',
    'update_guild_settings',
    'get_economy_config',
    'get_player_balance',
    'set_player_balance',
    'add_player_balance',
    'remove_player_balance',
    'get_player_stats',
    'update_player_stats',
    'get_rankings',
    'create_match',
    'get_match',
    'update_match',
    'create_ticket',
    'get_ticket',
    'close_ticket',
    'distribute_top_prizes',
    'can_distribute_prizes',
    'economy_balances',
    'economy_transactions',
    'players',
    'matches',
    'betting_matches',
    'tickets',
    'server_configs',
    'guild_settings',
    'top_prizes'
]

print("✅ Banco de dados inicializado com sucesso!")
print(f"📊 Total de coleções: {len(db.list_collection_names())}")
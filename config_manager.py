import json
from typing import Dict, List, Optional, Any
from datetime import datetime

class ConfigManager:
    """Sistema de configuração ultra-flexível com validação e cache"""
    
    def __init__(self, db):
        self.db = db
        self.config_col = db.get_collection('server_configs')
        self.cache = {}
        self.cache_ttl = 60
        
        self.default_config = {
            'guild_id': None,
            'rank_system': {
                'enabled': True,
                'allowed_roles': [],  # Cargos que podem criar ranks
                'max_players': 6,
                'match_types': ['1v1', '2v2', '3v3'],
                'ranking_display': {
                    'show_wins': True,
                    'show_losses': True,
                    'show_winrate': True,
                    'top_players': 10,
                    'columns': ['Posição', 'Jogador', 'Vitórias', 'Derrotas', 'Taxa']
                }
            },
            'match_settings': {
                'auto_ticket': True,
                'ticket_category': None,
                'ticket_name_template': '🎮-partida-{match_id}',
                'mediator_roles': [],  # Cargos de mediador
                'required_mediators': 1,
                'timeout_minutes': 30,
                'maps': [],  # Lista de mapas disponíveis
                'map_selection': 'dropdown',  # dropdown | buttons | modal
                'team_selection': 'buttons',  # buttons | dropdown | modal
                'allow_spectators': False,
                'spectator_roles': [],
                'lobby_timeout': 600,  # 10 minutos
                'voice_channel': False,
                'voice_category': None
            },
            'economy_integration': {
                'enabled': True,
                'collection_name': 'economy',  # Nome da coleção do bot de economia
                'betting_enabled': True,
                'min_bet': 100,
                'max_bet': 10000,
                'win_multiplier': 1.5,
                'loss_penalty': 0.8,
                'tax_percent': 5,
                'currency_name': 'moedas',
                'currency_symbol': '💰'
            },
            'permissions': {
                'admin_roles': [],  # Cargos que podem usar comandos admin
                'mod_roles': [],  # Cargos moderadores
                'mediator_roles': [],  # Cargos mediadores
                'trusted_players': [],  # Jogadores confiáveis
                'blacklist': []  # Jogadores banidos
            },
            'customization': {
                'embed_color': 0x00ff00,
                'embed_footer': 'Rank System v3.0',
                'embed_thumbnail': None,
                'locale': 'pt-BR',
                'messages': {
                    'match_created': '✅ Partida {match_type} criada com sucesso!',
                    'match_full': '🚀 Partida cheia! Ticket aberto em {channel}',
                    'player_joined': '👤 {player} entrou na partida! ({current}/{max})',
                    'team_joined': '👤 {player} entrou no time {team}!',
                    'match_started': '🎯 Partida iniciada! Mapa: {map}',
                    'winner_declared': '🏆 {winner} venceu a partida!',
                    'draw_declared': '⚖️ Empate declarado!',
                    'match_cancelled': '❌ Partida cancelada!',
                    'not_enough_players': '❌ Não há jogadores suficientes!'
                }
            },
            'security': {
                'anti_spam': True,
                'cooldown_seconds': 3,
                'max_matches_per_user': 3,
                'require_verification': False,
                'log_channel': None,
                'dm_notifications': True,
                'ping_players': True
            }
        }

    async def get_config(self, guild_id: str) -> Dict:
        """Obtém configuração com cache"""
        cache_key = f"config_{guild_id}"
        
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if (datetime.utcnow() - timestamp).seconds < self.cache_ttl:
                return data.copy()
        
        config = await self.config_col.find_one({'guild_id': guild_id})
        
        if not config:
            config = await self.create_default_config(guild_id)
        
        self.cache[cache_key] = (config, datetime.utcnow())
        return config.copy()

    async def create_default_config(self, guild_id: str) -> Dict:
        """Cria configuração padrão para servidor"""
        config = self.default_config.copy()
        config['guild_id'] = guild_id
        await self.config_col.insert_one(config)
        return config

    async def update_config(self, guild_id: str, path: str, value: Any) -> bool:
        """Atualiza configuração por caminho (ex: 'match_settings.maps')"""
        config = await self.get_config(guild_id)
        keys = path.split('.')
        current = config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
        
        result = await self.config_col.update_one(
            {'guild_id': guild_id},
            {'$set': {path: value}}
        )
        
        # Invalidar cache
        self.cache.pop(f"config_{guild_id}", None)
        return result.modified_count > 0

    async def add_to_list(self, guild_id: str, path: str, value: Any) -> bool:
        """Adiciona item a uma lista na configuração"""
        config = await self.get_config(guild_id)
        keys = path.split('.')
        current = config
        
        for key in keys:
            current = current.get(key, [])
        
        if value not in current:
            result = await self.config_col.update_one(
                {'guild_id': guild_id},
                {'$push': {path: value}}
            )
            self.cache.pop(f"config_{guild_id}", None)
            return result.modified_count > 0
        return False

    async def remove_from_list(self, guild_id: str, path: str, value: Any) -> bool:
        """Remove item de uma lista na configuração"""
        result = await self.config_col.update_one(
            {'guild_id': guild_id},
            {'$pull': {path: value}}
        )
        self.cache.pop(f"config_{guild_id}", None)
        return result.modified_count > 0

    async def preload_configs(self):
        """Pré-carrega todas as configurações"""
        async for config in self.config_col.find({}):
            self.cache[f"config_{config['guild_id']}"] = (config, datetime.utcnow())

    def get_nested_value(self, config: Dict, path: str, default=None):
        """Obtém valor aninhado da configuração"""
        keys = path.split('.')
        current = config
        
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return default
        
        return current if current is not None else default
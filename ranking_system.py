# ============================================================
# RANKING_SYSTEM.PY - SISTEMA DE RANKING COM ECONOMIA
# ============================================================

import discord
from discord.ui import Button, View, Select
from typing import Dict, List, Optional
from datetime import datetime
import asyncio

from database import (
    get_rankings,
    get_player_rank_stats,
    get_player_balance,
    get_economy_config,
    get_player_stats
)

class RankingSystem:
    """Sistema completo de rankings com integração econômica"""
    
    def __init__(self, db, config, bot):
        self.db = db
        self.config = config
        self.bot = bot
        self.cache = {}
        self.cache_ttl = config.CACHE_TTL

    async def initialize_rankings(self):
        """Inicializa cache de rankings para todos os servidores"""
        try:
            from database import server_configs
            configs = server_configs.find({})
            for server_config in configs:
                guild_id = server_config['guild_id']
                for match_type in self.config.MATCH_TYPES:
                    await self.get_ranking(guild_id, match_type, force=True)
            print("✅ Rankings inicializados com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro ao inicializar rankings: {e}")

    async def get_ranking(self, guild_id: str, match_type: str, 
                          force: bool = False) -> List[Dict]:
        """Obtém ranking com cache"""
        cache_key = f"ranking_{guild_id}_{match_type}"
        
        if not force and cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if (datetime.utcnow() - timestamp).seconds < self.cache_ttl:
                return data
        
        # Buscar do banco
        ranking = get_rankings(guild_id, match_type, 50)
        
        self.cache[cache_key] = (ranking, datetime.utcnow())
        return ranking

    async def generate_ranking_embed(self, guild_id: str, match_type: str) -> discord.Embed:
        """Gera embed do ranking com saldo econômico"""
        ranking = await self.get_ranking(guild_id, match_type)
        
        embed = discord.Embed(
            title=f"🏆 Ranking {match_type}",
            description=f"Top {len(ranking)} jogadores",
            color=self.config.EMBED_COLOR,
            timestamp=datetime.utcnow()
        )
        
        if not ranking:
            embed.description = "Nenhum jogador encontrado!"
            return embed
        
        eco_config = get_economy_config(int(guild_id))
        currency_emoji = eco_config.get('currency_emoji', '💰')
        
        # Formatar ranking
        for i, player in enumerate(ranking[:10], 1):
            try:
                user = await self.bot.fetch_user(int(player['user_id']))
                name = user.display_name
            except:
                name = f"Jogador {player['user_id'][:6]}"
            
            wins = player.get('wins', 0)
            losses = player.get('losses', 0)
            total = wins + losses
            
            # Buscar saldo
            balance = get_player_balance(int(guild_id), int(player['user_id']))
            
            if total > 0:
                winrate = (wins / total) * 100
                winrate_text = f" ({winrate:.1f}%)"
            else:
                winrate_text = ""
            
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"#{i}"
            
            embed.add_field(
                name=f"{medal} {name}",
                value=f"🏆 {wins} vitórias | 💔 {losses} derrotas{winrate_text}\n{currency_emoji} {balance}",
                inline=False
            )
        
        embed.set_footer(text=self.config.EMBED_FOOTER)
        return embed

    async def get_player_stats_embed(self, guild_id: str, user_id: str, member: discord.Member) -> discord.Embed:
        """Gera embed das estatísticas do jogador com economia"""
        stats = get_player_rank_stats(guild_id, user_id)
        eco_config = get_economy_config(int(guild_id))
        currency_emoji = eco_config.get('currency_emoji', '💰')
        
        embed = discord.Embed(
            title=f"📊 Estatísticas de {member.display_name}",
            color=member.color,
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Estatísticas gerais + economia
        embed.add_field(
            name="🏆 Geral",
            value=f"**Vitórias:** {stats['total_wins']}\n"
                  f"**Derrotas:** {stats['total_losses']}\n"
                  f"**Partidas:** {stats['matches_played']}\n"
                  f"**Saldo:** {currency_emoji} {stats['balance']}\n"
                  f"**Prestígio:** 🌟 Nível {stats['prestige_level']}\n"
                  f"**Conquistas:** 🏅 {stats['achievements']}",
            inline=False
        )
        
        # Por tipo
        for match_type in self.config.MATCH_TYPES:
            type_stats = stats['stats'][match_type]
            total = type_stats['wins'] + type_stats['losses']
            winrate = (type_stats['wins'] / total * 100) if total > 0 else 0
            
            embed.add_field(
                name=f"📈 {match_type}",
                value=f"**Vitórias:** {type_stats['wins']}\n"
                      f"**Derrotas:** {type_stats['losses']}\n"
                      f"**Taxa:** {winrate:.1f}%",
                inline=True
            )
        
        embed.set_footer(text=self.config.EMBED_FOOTER)
        return embed

    async def get_leaderboard_text(self, guild_id: str, match_type: str) -> str:
        """Retorna texto do leaderboard para mensagens"""
        ranking = await self.get_ranking(guild_id, match_type)
        eco_config = get_economy_config(int(guild_id))
        currency_emoji = eco_config.get('currency_emoji', '💰')
        
        if not ranking:
            return "📊 Nenhum jogador encontrado!"
        
        text = f"**🏆 Ranking {match_type}**\n```\n"
        text += "Pos | Jogador               | Vitórias | Derrotas | Taxa    | Saldo\n"
        text += "----|-----------------------|----------|----------|---------|-------\n"
        
        for i, player in enumerate(ranking[:15], 1):
            try:
                user = await self.bot.fetch_user(int(player['user_id']))
                name = user.display_name[:20].ljust(20)
            except:
                name = f"ID:{player['user_id'][:10]}".ljust(20)
            
            wins = player.get('wins', 0)
            losses = player.get('losses', 0)
            total = wins + losses
            
            if total > 0:
                winrate = (wins / total) * 100
                winrate_text = f"{winrate:.1f}%"
            else:
                winrate_text = "0%"
            
            balance = get_player_balance(int(guild_id), int(player['user_id']))
            
            text += f"{str(i).rjust(2)} | {name} | {str(wins).rjust(8)} | {str(losses).rjust(8)} | {winrate_text.rjust(7)} | {str(balance).rjust(6)}\n"
        
        text += "```"
        return text

    async def update_ranking_cache(self, guild_id: str):
        """Atualiza cache de todos os rankings do servidor"""
        for match_type in self.config.MATCH_TYPES:
            await self.get_ranking(guild_id, match_type, force=True)
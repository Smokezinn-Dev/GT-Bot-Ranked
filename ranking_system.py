# ============================================================
# RANKING_SYSTEM.PY - COM EMBEDS + BOTÃO DE ATUALIZAR
# ============================================================

import discord
from discord.ui import Button, View
from datetime import datetime
from typing import Dict, List, Optional
from collections import OrderedDict
import time

from database import (
    get_rankings,
    get_player_rank_stats,
    get_player_balance,
    get_economy_config,
    get_guild_settings,
)


class RankingView(View):
    """View com botão de atualizar ranking"""
    def __init__(self, ranking_system, guild_id: str, match_type: str):
        super().__init__(timeout=None)
        self.ranking_system = ranking_system
        self.guild_id = guild_id
        self.match_type = match_type

    @discord.ui.button(label="🔄 Atualizar", style=discord.ButtonStyle.primary, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        await self.ranking_system.update_ranking_cache(self.guild_id)
        embed = await self.ranking_system.generate_ranking_embed(self.guild_id, self.match_type)
        await interaction.response.edit_message(embed=embed, view=self)


class _RankCache:
    __slots__ = ("maxsize", "ttl", "_data")

    def __init__(self, maxsize: int = 24, ttl: int = 45):
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

    def invalidate_guild(self, guild_id: str):
        keys = [k for k in self._data if k.startswith(f"r:{guild_id}:")]
        for k in keys:
            self._data.pop(k, None)

    def clear(self):
        self._data.clear()


class RankingSystem:
    __slots__ = ("db", "config", "bot", "cache", "match_types")

    def __init__(self, db, config, bot):
        self.db = db
        self.config = config
        self.bot = bot
        self.cache = _RankCache(maxsize=24, ttl=45)
        self.match_types = getattr(config, "MATCH_TYPES", None) or ["1v1", "2v2", "3v3"]

    async def initialize_rankings(self):
        try:
            for guild in self.bot.guilds[:15]:
                gid = str(guild.id)
                for mt in self.match_types:
                    await self.get_ranking(gid, mt, force=True)
        except Exception:
            pass

    async def get_ranking(self, guild_id: str, match_type: str, force: bool = False) -> List[dict]:
        key = f"r:{guild_id}:{match_type}"
        if not force:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        ranking = get_rankings(guild_id, match_type, 50)
        self.cache.set(key, ranking)
        return ranking

    def _currency(self, guild_id: int):
        cfg = get_economy_config(int(guild_id))
        return cfg.get("currency_emoji", "💰"), cfg.get("currency_name", "Moedas")

    async def _resolve_name(self, user_id: str, guild: Optional[discord.Guild] = None) -> str:
        try:
            uid = int(user_id)
        except Exception:
            return f"ID:{user_id[:8]}"

        if guild:
            member = guild.get_member(uid)
            if member:
                return member.display_name

        try:
            user = self.bot.get_user(uid)
            if user:
                return user.display_name
            user = await self.bot.fetch_user(uid)
            return user.display_name
        except Exception:
            return f"ID:{str(user_id)[:8]}"

    async def generate_ranking_embed(self, guild_id: str, match_type: str) -> discord.Embed:
        ranking = await self.get_ranking(guild_id, match_type)
        settings = get_guild_settings(guild_id)
        custom = settings.get("customization", {})
        color = custom.get("embed_color", 0x00ff00)
        footer = custom.get("embed_footer", "Rank System v3.0")
        thumbnail = custom.get("rank_thumbnail", "https://i.imgur.com/8XxJt7z.png")
        emoji, currency_name = self._currency(int(guild_id))

        titles = {
            "1v1": "🏆 Ranking 1v1",
            "2v2": "🏆 Ranking 2v2",
            "3v3": "🏆 Ranking 3v3"
        }
        
        embed = discord.Embed(
            title=titles.get(match_type, "🏆 Ranking"),
            color=color,
            timestamp=datetime.utcnow()
        )

        if not ranking:
            embed.description = "❌ Nenhum jogador encontrado!"
            embed.set_footer(text=footer)
            return embed

        guild = self.bot.get_guild(int(guild_id))
        medals = ("🥇", "🥈", "🥉")
        
        for i, player in enumerate(ranking[:10], 1):
            name = await self._resolve_name(player["user_id"], guild)
            wins = int(player.get("wins") or 0)
            losses = int(player.get("losses") or 0)
            total = wins + losses
            
            wr = f"({wins/total*100:.1f}%)" if total > 0 else "(0%)"
            bal = get_player_balance(int(guild_id), int(player["user_id"]))
            
            medal = medals[i-1] if i <= 3 else f"`#{i:02d}`"
            embed.add_field(
                name=f"{medal} {name}",
                value=f"🏅 **{wins}W** | 💔 **{losses}L** | {wr}\n{emoji} **{bal}** {currency_name}",
                inline=False
            )

        total_players = len(ranking)
        embed.set_footer(text=f"{footer} • {total_players} jogadores no total")
        embed.set_thumbnail(url=thumbnail)
        
        return embed

    async def get_player_stats_embed(
        self, guild_id: str, user_id: str, member: discord.Member
    ) -> discord.Embed:
        stats = get_player_rank_stats(guild_id, user_id)
        emoji, currency_name = self._currency(int(guild_id))
        settings = get_guild_settings(guild_id)
        footer = settings.get("customization", {}).get("embed_footer", "Rank System v3.0")

        embed = discord.Embed(
            title=f"📊 Perfil de {member.display_name}",
            color=member.color or discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        total_wins = stats['total_wins']
        total_losses = stats['total_losses']
        total_matches = stats['matches_played']
        winrate = f"{total_wins/total_matches*100:.1f}%" if total_matches > 0 else "0%"

        embed.add_field(
            name="📈 Geral",
            value=(
                f"🏆 **Vitórias:** {total_wins}\n"
                f"💔 **Derrotas:** {total_losses}\n"
                f"🎯 **Partidas:** {total_matches}\n"
                f"📊 **Win Rate:** {winrate}\n"
                f"{emoji} **Saldo:** {stats['balance']} {currency_name}"
            ),
            inline=False
        )

        icons = {"1v1": "⚔️", "2v2": "👥", "3v3": "👨‍👩‍👦"}
        for mt in self.match_types:
            ts = stats.get("stats", {}).get(mt, {"wins": 0, "losses": 0})
            w, l = int(ts.get("wins", 0)), int(ts.get("losses", 0))
            total = w + l
            wr = f"{w/total*100:.1f}%" if total > 0 else "0%"
            
            embed.add_field(
                name=f"{icons.get(mt, '📌')} {mt}",
                value=f"**W:** {w} | **L:** {l}\n**WR:** {wr}",
                inline=True
            )

        embed.set_footer(text=footer)
        return embed

    async def update_ranking_cache(self, guild_id: str):
        self.cache.invalidate_guild(guild_id)
        for mt in self.match_types:
            await self.get_ranking(guild_id, mt, force=True)
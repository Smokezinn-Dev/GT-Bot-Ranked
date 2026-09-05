# ============================================================
# ADMIN_COMMANDS.PY - CONFIG + CONTROLE (OTIMIZADO)
# ============================================================

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
import time
import gc

from database import (
    get_guild_settings,
    update_guild_settings,
    get_player_balance,
    add_player_balance,
    remove_player_balance,
    set_player_balance,
    get_mediator_roles,
    set_mediator_role,
    distribute_top_prizes,
    can_distribute_prizes,
)


# ============================================================
# PERMISSION CACHE
# ============================================================

class _PermissionCache:
    """Cache de permissões para reduzir queries"""
    __slots__ = ("_data", "_ttl")
    
    def __init__(self, ttl: int = 30):
        self._data = {}
        self._ttl = ttl
    
    def get(self, key: str) -> Optional[bool]:
        if key in self._data:
            val, exp = self._data[key]
            if time.monotonic() < exp:
                return val
            del self._data[key]
        return None
    
    def set(self, key: str, value: bool):
        self._data[key] = (value, time.monotonic() + self._ttl)
        if len(self._data) > 100:
            oldest = min(self._data.items(), key=lambda x: x[1][1])
            del self._data[oldest[0]]

_perm_cache = _PermissionCache(ttl=30)


def _is_config_admin(member: discord.Member, settings: dict) -> bool:
    cache_key = f"{member.guild.id}:{member.id}"
    cached = _perm_cache.get(cache_key)
    if cached is not None:
        return cached
    
    if member.guild_permissions.administrator:
        _perm_cache.set(cache_key, True)
        return True
    
    admin_roles = set(int(r) for r in settings.get("permissions", {}).get("admin_roles", []))
    config_roles = set(int(r) for r in settings.get("permissions", {}).get("config_roles", []))
    user_roles = {r.id for r in member.roles}
    result = bool(user_roles & (admin_roles | config_roles))
    
    _perm_cache.set(cache_key, result)
    return result


def clear_permission_cache():
    global _perm_cache
    _perm_cache = _PermissionCache(ttl=30)
    gc.collect()


class AdminCommands(commands.Cog):
    def __init__(self, bot, match_system, ranking_system):
        self.bot = bot
        self.match_system = match_system
        self.ranking_system = ranking_system

    # ============================================================
    # PERMISSÃO
    # ============================================================

    async def _check(self, ctx_or_inter) -> bool:
        guild = ctx_or_inter.guild
        author = getattr(ctx_or_inter, "author", None) or getattr(ctx_or_inter, "user", None)
        settings = get_guild_settings(str(guild.id))
        if not _is_config_admin(author, settings):
            send = getattr(ctx_or_inter, "send", None) or ctx_or_inter.response.send_message
            try:
                await send(embed=discord.Embed(
                    description="❌ Sem permissão de configuração.",
                    color=0xff0000
                ), ephemeral=True)
            except Exception:
                try:
                    await send("❌ Sem permissão de configuração.")
                except Exception:
                    pass
            return False
        return True

    # ============================================================
    # CONFIG GERAL
    # ============================================================

    @commands.command(name="config")
    async def config_cmd(self, ctx: commands.Context, section: str = None, key: str = None, *, value: str = None):
        """
        Ver/editar config do servidor.
        >config                          → mostra tudo
        >config ranked win_bonus 100
        >config betting min_bet 50
        >config currency name Credits
        """
        if not await self._check(ctx):
            return

        gid = str(ctx.guild.id)
        settings = get_guild_settings(gid)

        if not section:
            embed = discord.Embed(
                title="⚙️ Configurações do Servidor",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            for sec in ("currency", "ranked", "betting", "match_settings", "customization", "permissions", "top_prizes"):
                data = settings.get(sec, {})
                lines = [f"`{k}`: **{v}**" for k, v in list(data.items())[:8]]
                embed.add_field(name=sec, value="\n".join(lines) or "—", inline=False)
            embed.set_footer(text=">config <seção> <chave> <valor>")
            return await ctx.send(embed=embed)

        section = section.lower()
        if section not in settings and section not in ("currency", "ranked", "betting", "match_settings", "customization", "permissions", "top_prizes"):
            return await ctx.send("❌ Seções: currency, ranked, betting, match_settings, customization, permissions, top_prizes")

        if not key:
            data = settings.get(section, {})
            embed = discord.Embed(title=f"⚙️ {section}", color=0x00ff00)
            for k, v in data.items():
                embed.add_field(name=k, value=str(v), inline=True)
            return await ctx.send(embed=embed)

        if value is None:
            return await ctx.send("❌ Use: `>config <seção> <chave> <valor>`")

        parsed = value
        if value.lower() in ("true", "sim", "on", "1"):
            parsed = True
        elif value.lower() in ("false", "nao", "não", "off", "0"):
            parsed = False
        else:
            try:
                if "." in value:
                    parsed = float(value)
                else:
                    parsed = int(value)
            except ValueError:
                parsed = value

        path = f"{section}.{key}"
        update_guild_settings(gid, path, parsed)
        await ctx.send(embed=discord.Embed(
            description=f"✅ `{path}` = `{parsed}`",
            color=0x00ff00
        ))

    # ============================================================
    # MEDIADOR
    # ============================================================

    @commands.command(name="setmediator")
    async def set_mediator(self, ctx: commands.Context, role: discord.Role):
        if not await self._check(ctx):
            return
        set_mediator_role(str(ctx.guild.id), role.id)
        await ctx.send(embed=discord.Embed(
            description=f"✅ Mediador: {role.mention}",
            color=0x00ff00
        ))

    @commands.command(name="mediators")
    async def list_mediators(self, ctx: commands.Context):
        roles = get_mediator_roles(str(ctx.guild.id))
        if not roles:
            return await ctx.send("Nenhum cargo de mediador.")
        mentions = []
        for rid in roles:
            role = ctx.guild.get_role(int(rid))
            mentions.append(role.mention if role else str(rid))
        await ctx.send("🔔 Mediadores: " + ", ".join(mentions))

    # ============================================================
    # ECONOMIA ADMIN
    # ============================================================

    @commands.command(name="give")
    async def give_money(self, ctx: commands.Context, member: discord.Member, amount: int):
        if not await self._check(ctx):
            return
        if amount <= 0:
            return await ctx.send("❌ Valor positivo.")
        new_bal = add_player_balance(ctx.guild.id, member.id, amount, f"Admin give by {ctx.author.id}")
        await ctx.send(f"✅ {member.mention} recebeu **{amount}**. Saldo: **{new_bal}**")

    @commands.command(name="take")
    async def take_money(self, ctx: commands.Context, member: discord.Member, amount: int):
        if not await self._check(ctx):
            return
        if amount <= 0:
            return await ctx.send("❌ Valor positivo.")
        ok = remove_player_balance(ctx.guild.id, member.id, amount, f"Admin take by {ctx.author.id}")
        if not ok:
            return await ctx.send("❌ Saldo insuficiente.")
        bal = get_player_balance(ctx.guild.id, member.id)
        await ctx.send(f"✅ Removido **{amount}** de {member.mention}. Saldo: **{bal}**")

    @commands.command(name="setbalance")
    async def set_balance(self, ctx: commands.Context, member: discord.Member, amount: int):
        if not await self._check(ctx):
            return
        amount = max(0, amount)
        set_player_balance(ctx.guild.id, member.id, amount)
        await ctx.send(f"✅ Saldo de {member.mention} = **{amount}**")

    @commands.command(name="bal", aliases=["saldo", "balance"])
    async def bal(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        bal = get_player_balance(ctx.guild.id, member.id)
        await ctx.send(f"💰 {member.display_name}: **{bal}**")

    # ============================================================
    # PRÊMIOS TOP
    # ============================================================

    @commands.command(name="distributetop")
    async def distribute_top(self, ctx: commands.Context, match_type: str = "1v1"):
        if not await self._check(ctx):
            return
        if match_type not in ("1v1", "2v2", "3v3"):
            return await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
        if not can_distribute_prizes(str(ctx.guild.id)):
            return await ctx.send("⏳ Ainda não passou o intervalo de distribuição.")
        result = distribute_top_prizes(str(ctx.guild.id), match_type)
        if not result.get("success"):
            return await ctx.send(f"❌ {result.get('message')}")
        lines = [f"#{k}: <@{v['user_id']}> → {v['amount']}" for k, v in result["distributed"].items()]
        await ctx.send("🏆 Prêmios distribuídos:\n" + "\n".join(lines))

    # ============================================================
    # PERMISSÕES DE CONFIG
    # ============================================================

    @commands.command(name="addconfigrole")
    @commands.has_permissions(administrator=True)
    async def add_config_role(self, ctx: commands.Context, role: discord.Role):
        settings = get_guild_settings(str(ctx.guild.id))
        roles = list(settings.get("permissions", {}).get("config_roles", []))
        if role.id not in roles:
            roles.append(role.id)
            update_guild_settings(str(ctx.guild.id), "permissions.config_roles", roles)
        await ctx.send(f"✅ {role.mention} pode alterar config.")

    @commands.command(name="removeconfigrole")
    @commands.has_permissions(administrator=True)
    async def remove_config_role(self, ctx: commands.Context, role: discord.Role):
        settings = get_guild_settings(str(ctx.guild.id))
        roles = [r for r in settings.get("permissions", {}).get("config_roles", []) if int(r) != role.id]
        update_guild_settings(str(ctx.guild.id), "permissions.config_roles", roles)
        await ctx.send(f"✅ {role.mention} removido da config.")

    # ============================================================
    # MATCH ADMIN
    # ============================================================

    @commands.command(name="cancelmatch")
    async def cancel_match_cmd(self, ctx: commands.Context, match_id: str):
        if not await self._check(ctx):
            return
        ok = await self.match_system.cancel_match(match_id)
        if ok:
            await ctx.send(f"✅ Partida `{match_id[:8]}` cancelada + reembolso.")
        else:
            await ctx.send("❌ Partida não encontrada.")

    @commands.command(name="matchinfo")
    async def match_info(self, ctx: commands.Context, match_id: str):
        info = await self.match_system.get_match_info(match_id)
        if not info:
            return await ctx.send("❌ Partida não encontrada.")
        embed = discord.Embed(title=f"🎮 Match {match_id[:8]}", color=0x00ff00)
        embed.add_field(name="Tipo", value=info.get("match_type"), inline=True)
        embed.add_field(name="Status", value=info.get("status"), inline=True)
        embed.add_field(name="Mapa", value=info.get("map"), inline=True)
        embed.add_field(name="Jogadores", value=str(len(info.get("players", []))), inline=True)
        if info.get("is_betting"):
            embed.add_field(name="Aposta", value=str(info.get("bet_amount")), inline=True)
        await ctx.send(embed=embed)
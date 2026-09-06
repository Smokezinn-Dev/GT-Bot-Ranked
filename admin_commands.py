# ============================================================
# ADMIN_COMMANDS.PY - CONFIG + CONTROLE (OTIMIZADO + SEGURO)
# ============================================================

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
import time
import gc
import asyncio

from database import (
    get_guild_settings,
    update_guild_settings,
    get_player_balance,
    add_player_balance,
    remove_player_balance,
    set_player_balance,
    get_mediator_roles,
    set_mediator_role,
    add_mediator_role,
    remove_mediator_role,
    distribute_top_prizes,
    can_distribute_prizes,
    get_reward_config,
    set_reward_config,
    can_distribute_mode_rewards,
    clear_user_cache,
    invalidate_guild_settings,
)


# ============================================================
# PERMISSION CACHE OTIMIZADO
# ============================================================

class _PermissionCache:
    __slots__ = ("_data", "_ttl", "_lock")
    
    def __init__(self, ttl: int = 30):
        self._data = {}
        self._ttl = ttl
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[bool]:
        async with self._lock:
            if key in self._data:
                val, exp = self._data[key]
                if time.monotonic() < exp:
                    return val
                del self._data[key]
            return None
    
    async def set(self, key: str, value: bool):
        async with self._lock:
            self._data[key] = (value, time.monotonic() + self._ttl)
            if len(self._data) > 100:
                oldest = min(self._data.items(), key=lambda x: x[1][1])
                del self._data[oldest[0]]
    
    async def invalidate(self, key: str):
        async with self._lock:
            self._data.pop(key, None)
    
    async def invalidate_guild(self, guild_id: str):
        async with self._lock:
            keys = [k for k in self._data.keys() if k.startswith(f"{guild_id}:")]
            for k in keys:
                self._data.pop(k, None)

_perm_cache = _PermissionCache(ttl=30)


async def _is_config_admin(member: discord.Member, settings: dict) -> bool:
    cache_key = f"{member.guild.id}:{member.id}"
    cached = await _perm_cache.get(cache_key)
    if cached is not None:
        return cached
    
    if member.guild_permissions.administrator:
        await _perm_cache.set(cache_key, True)
        return True
    
    admin_roles = set(int(r) for r in settings.get("permissions", {}).get("admin_roles", []))
    config_roles = set(int(r) for r in settings.get("permissions", {}).get("config_roles", []))
    user_roles = {r.id for r in member.roles}
    result = bool(user_roles & (admin_roles | config_roles))
    
    await _perm_cache.set(cache_key, result)
    return result


async def clear_permission_cache():
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
        if not guild:
            return False
        
        author = getattr(ctx_or_inter, "author", None) or getattr(ctx_or_inter, "user", None)
        if not author:
            return False
        
        settings = get_guild_settings(str(guild.id))
        if not await _is_config_admin(author, settings):
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
    # CONFIG GERAL (COM VALIDAÇÃO)
    # ============================================================

    @commands.command(name="config")
    async def config_cmd(self, ctx: commands.Context, section: str = None, key: str = None, *, value: str = None):
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
            for sec in ("currency", "ranked", "betting", "match_settings", "customization", "permissions", "top_prizes", "rewards"):
                data = settings.get(sec, {})
                lines = [f"`{k}`: **{v}**" for k, v in list(data.items())[:8]]
                embed.add_field(name=sec, value="\n".join(lines) or "—", inline=False)
            embed.set_footer(text=">config <seção> <chave> <valor>")
            return await ctx.send(embed=embed)

        section = section.lower()
        valid_sections = ("currency", "ranked", "betting", "match_settings", "customization", "permissions", "top_prizes", "rewards")
        if section not in valid_sections:
            return await ctx.send(f"❌ Seções: {', '.join(valid_sections)}")

        if not key:
            data = settings.get(section, {})
            embed = discord.Embed(title=f"⚙️ {section}", color=0x00ff00)
            for k, v in data.items():
                if isinstance(v, dict):
                    continue
                embed.add_field(name=k, value=str(v), inline=True)
                if len(embed.fields) >= 24:
                    break
            return await ctx.send(embed=embed)

        if value is None:
            return await ctx.send("❌ Use: `>config <seção> <chave> <valor>`")

        # Validação por seção
        parsed = self._parse_config_value(value)
        path = f"{section}.{key}"
        
        # Validar valor antes de salvar
        if not self._validate_config_value(section, key, parsed):
            return await ctx.send(f"❌ Valor inválido para `{key}`")

        update_guild_settings(gid, path, parsed)
        invalidate_guild_settings(gid)
        await _perm_cache.invalidate_guild(gid)
        
        await ctx.send(embed=discord.Embed(
            description=f"✅ `{path}` = `{parsed}`",
            color=0x00ff00
        ))

    def _parse_config_value(self, value: str):
        if value.lower() in ("true", "sim", "on", "1"):
            return True
        if value.lower() in ("false", "nao", "não", "off", "0"):
            return False
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def _validate_config_value(self, section: str, key: str, value) -> bool:
        """Valida valores de configuração específicos"""
        if section == "betting":
            if key in ("min_bet", "max_bet", "max_players"):
                return isinstance(value, int) and value > 0
            if key == "win_multiplier":
                return isinstance(value, (int, float)) and value >= 1.0
            if key == "tax_percent":
                return isinstance(value, (int, float)) and 0 <= value <= 100
        
        if section == "ranked":
            if key in ("win_bonus", "loss_penalty", "entry_fee", "max_matches_per_user"):
                return isinstance(value, int) and value >= 0
        
        if section == "top_prizes":
            if key == "interval_days":
                return isinstance(value, int) and value >= 1
        
        if section == "currency":
            if key == "daily_bonus":
                return isinstance(value, int) and value >= 0
        
        return True

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

    @commands.command(name="addmediator")
    async def add_mediator(self, ctx: commands.Context, role: discord.Role):
        if not await self._check(ctx):
            return
        add_mediator_role(str(ctx.guild.id), role.id)
        await ctx.send(embed=discord.Embed(description=f"✅ {role.mention} adicionado como mediador.", color=0x00ff00))

    @commands.command(name="removemediator")
    async def remove_mediator(self, ctx: commands.Context, role: discord.Role):
        if not await self._check(ctx):
            return
        remove_mediator_role(str(ctx.guild.id), role.id)
        await ctx.send(embed=discord.Embed(description=f"✅ {role.mention} removido dos mediadores.", color=0x00ff00))

    @commands.command(name="mediators")
    async def list_mediators(self, ctx: commands.Context):
        roles = get_mediator_roles(str(ctx.guild.id))
        if not roles:
            return await ctx.send("Nenhum cargo de mediador.")
        mentions = []
        for rid in roles[:10]:
            role = ctx.guild.get_role(int(rid))
            mentions.append(role.mention if role else str(rid))
        await ctx.send("🔔 Mediadores: " + ", ".join(mentions))

    # ============================================================
    # ECONOMIA ADMIN (COM VALIDAÇÃO)
    # ============================================================

    @commands.command(name="give")
    async def give_money(self, ctx: commands.Context, member: discord.Member, amount: int):
        if not await self._check(ctx):
            return
        if amount <= 0:
            return await ctx.send("❌ Valor positivo.")
        
        try:
            new_bal = add_player_balance(ctx.guild.id, member.id, amount, f"Admin give by {ctx.author.id}")
            clear_user_cache(str(ctx.guild.id), str(member.id))
            await ctx.send(f"✅ {member.mention} recebeu **{amount}**. Saldo: **{new_bal}**")
        except Exception as e:
            await ctx.send(f"❌ Erro: {e}")

    @commands.command(name="take")
    async def take_money(self, ctx: commands.Context, member: discord.Member, amount: int):
        if not await self._check(ctx):
            return
        if amount <= 0:
            return await ctx.send("❌ Valor positivo.")
        
        ok = remove_player_balance(ctx.guild.id, member.id, amount, f"Admin take by {ctx.author.id}")
        if not ok:
            return await ctx.send("❌ Saldo insuficiente.")
        
        clear_user_cache(str(ctx.guild.id), str(member.id))
        bal = get_player_balance(ctx.guild.id, member.id)
        await ctx.send(f"✅ Removido **{amount}** de {member.mention}. Saldo: **{bal}**")

    @commands.command(name="setbalance")
    async def set_balance(self, ctx: commands.Context, member: discord.Member, amount: int):
        if not await self._check(ctx):
            return
        if amount < 0:
            return await ctx.send("❌ Valor não pode ser negativo.")
        
        set_player_balance(ctx.guild.id, member.id, amount)
        clear_user_cache(str(ctx.guild.id), str(member.id))
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
        await ctx.send("🏆 Prêmios distribuídos:\n" + "\n".join(lines[:10]))

    # ============================================================
    # PREMIAÇÃO DE RANKING
    # ============================================================

    @commands.command(name="rewards")
    async def rewards_cmd(self, ctx: commands.Context, match_type: str = None, scope: str = None, role: discord.Role = None, currency: int = None):
        if not await self._check(ctx):
            return

        gid = str(ctx.guild.id)
        valid_types = ("1v1", "2v2", "3v3", "4v4")

        if not match_type:
            embed = discord.Embed(title="🏆 Premiação de Ranking", color=0xf1c40f, timestamp=datetime.utcnow())
            for mt in valid_types:
                cfg = get_reward_config(gid, mt)
                role_obj = ctx.guild.get_role(int(cfg["role_id"])) if cfg.get("role_id") else None
                status = "✅ ativa" if cfg.get("enabled") else "❌ desativada"
                embed.add_field(
                    name=f"{mt} — {status}",
                    value=(
                        f"Escopo: `{cfg.get('scope')}`\n"
                        f"Cargo: {role_obj.mention if role_obj else '—'}\n"
                        f"Moeda: {cfg.get('currency_amount', 0)}\n"
                        f"Intervalo: {cfg.get('interval_days', 7)} dias"
                    ),
                    inline=True
                )
            embed.set_footer(text=">rewards <modo> <all|top3|top1|off> [@cargo] [moeda]")
            return await ctx.send(embed=embed)

        match_type = match_type.lower()
        if match_type not in valid_types:
            return await ctx.send(f"❌ Modos: {', '.join(valid_types)}")

        if scope is None:
            cfg = get_reward_config(gid, match_type)
            role_obj = ctx.guild.get_role(int(cfg["role_id"])) if cfg.get("role_id") else None
            return await ctx.send(
                f"**{match_type}** — {'✅ ativa' if cfg.get('enabled') else '❌ desativada'}\n"
                f"Escopo: `{cfg.get('scope')}` | Cargo: {role_obj.mention if role_obj else '—'} | "
                f"Moeda: {cfg.get('currency_amount', 0)}"
            )

        scope = scope.lower()
        if scope == "off":
            set_reward_config(gid, match_type, enabled=False)
            return await ctx.send(f"✅ Premiação de `{match_type}` desativada.")

        if scope not in ("all", "top3", "top1"):
            return await ctx.send("❌ Escopos: all, top3, top1, off")

        role_id = role.id if role else None
        set_reward_config(
            gid, match_type,
            enabled=True,
            scope=scope,
            role_id=role_id,
            currency_amount=int(currency) if currency is not None else 0,
        )

        parts = [f"escopo `{scope}`"]
        if role:
            parts.append(f"cargo {role.mention}")
        if currency:
            parts.append(f"**{currency}** moedas")
        await ctx.send(embed=discord.Embed(
            description=f"✅ Premiação de `{match_type}` configurada: " + ", ".join(parts),
            color=0x00ff00
        ))

    @commands.command(name="distributerewards")
    async def distribute_rewards_cmd(self, ctx: commands.Context, match_type: str = "1v1"):
        if not await self._check(ctx):
            return
        match_type = match_type.lower()
        gid = str(ctx.guild.id)

        if not can_distribute_mode_rewards(gid, match_type):
            return await ctx.send("⏳ Ainda não passou o intervalo configurado para distribuir de novo.")

        result = await self.ranking_system.distribute_mode_rewards(gid, match_type)
        if not result.get("success"):
            return await ctx.send(f"❌ {result.get('message')}")

        await ctx.send(
            f"🏆 Premiação de `{match_type}` distribuída para **{result['count']}** jogador(es) "
            f"(escopo: `{result['scope']}`)."
        )

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
            await _perm_cache.invalidate_guild(str(ctx.guild.id))
        await ctx.send(f"✅ {role.mention} pode alterar config.")

    @commands.command(name="removeconfigrole")
    @commands.has_permissions(administrator=True)
    async def remove_config_role(self, ctx: commands.Context, role: discord.Role):
        settings = get_guild_settings(str(ctx.guild.id))
        roles = [r for r in settings.get("permissions", {}).get("config_roles", []) if int(r) != role.id]
        update_guild_settings(str(ctx.guild.id), "permissions.config_roles", roles)
        await _perm_cache.invalidate_guild(str(ctx.guild.id))
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
        embed.add_field(name="Tipo", value=info.get("match_type", "N/A"), inline=True)
        embed.add_field(name="Status", value=info.get("status", "N/A"), inline=True)
        embed.add_field(name="Mapa", value=info.get("map", "N/A"), inline=True)
        embed.add_field(name="Jogadores", value=str(len(info.get("players", []))), inline=True)
        if info.get("is_betting"):
            embed.add_field(name="Aposta", value=str(info.get("bet_amount", 0)), inline=True)
        await ctx.send(embed=embed)
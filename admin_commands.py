# ============================================================
# ADMIN_COMMANDS.PY - COMANDOS 100% CUSTOMIZÁVEIS
# ============================================================

import discord
from discord.ext import commands
from typing import Optional
from datetime import datetime, timedelta

from database import (
    get_guild_settings, update_guild_settings,
    get_player_balance, add_player_balance, remove_player_balance,
    get_player_stats, update_player_stats,
    get_rankings, get_mediator_roles, set_mediator_role,
    distribute_top_prizes, can_distribute_prizes,
    get_active_matches
)

class AdminCommands:
    def __init__(self, bot, db, config, match_system, ranking_system):
        self.bot = bot
        self.db = db
        self.config = config
        self.match_system = match_system
        self.ranking_system = ranking_system
        self.bot.match_system = match_system

    def register_commands(self):
        """Registra todos os comandos"""

        # ============================================================
        # RANKING
        # ============================================================

        @self.bot.command(name="rank")
        async def rank_cmd(ctx, match_type: str = "1v1"):
            """Mostra ranking"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            embed = await self.ranking_system.generate_ranking_embed(str(ctx.guild.id), match_type)
            await ctx.send(embed=embed)

        @self.bot.command(name="myrank")
        async def myrank_cmd(ctx, match_type: str = "1v1"):
            """Minhas estatísticas"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            embed = await self.ranking_system.get_player_stats_embed(str(ctx.guild.id), str(ctx.author.id), ctx.author)
            await ctx.send(embed=embed)

        @self.bot.command(name="matches")
        async def matches_cmd(ctx):
            """Lista partidas ativas"""
            matches = get_active_matches(str(ctx.guild.id), False)
            betting = get_active_matches(str(ctx.guild.id), True)
            
            if not matches and not betting:
                await ctx.send("📭 Nenhuma partida ativa!")
                return
            
            embed = discord.Embed(title="🎮 Partidas Ativas", color=0x00ff00, timestamp=datetime.utcnow())
            
            for m in matches[:5]:
                embed.add_field(
                    name=f"🏆 RANKED - {m['_id'][:6]}",
                    value=f"**Tipo:** {m['match_type']}\n**Mapa:** {m['map']}\n**Jogadores:** {len(m.get('players', []))}/{self.match_system.match_types[m['match_type']]['max_players']}",
                    inline=False
                )
            
            for m in betting[:5]:
                embed.add_field(
                    name=f"💰 APOSTADO - {m['_id'][:6]}",
                    value=f"**Tipo:** {m['match_type']}\n**Aposta:** {m.get('bet_amount', 0)} moedas\n**Jogadores:** {len(m.get('players', []))}/{self.match_system.match_types[m['match_type']]['max_players']}",
                    inline=False
                )
            
            await ctx.send(embed=embed)

        # ============================================================
        # CRIAÇÃO DE PARTIDAS
        # ============================================================

        @self.bot.command(name="ranked")
        @commands.has_permissions(administrator=True)
        async def ranked_cmd(ctx, match_type: str, map_name: str = "Arena"):
            """Cria partida RANKED"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            result = await self.match_system.create_lobby(
                str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id),
                match_type, map_name, False, 0
            )
            
            if "error" in result:
                await ctx.send(result["error"])
                return
            
            await ctx.send(f"✅ Partida RANKED criada! ID: `{result['match_id'][:6]}`")

        @self.bot.command(name="apostado")
        @commands.has_permissions(administrator=True)
        async def apostado_cmd(ctx, match_type: str, bet_amount: int, map_name: str = "Arena"):
            """Cria partida APOSTADO"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            if bet_amount <= 0:
                await ctx.send("❌ Aposta deve ser positiva!")
                return
            
            result = await self.match_system.create_lobby(
                str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id),
                match_type, map_name, True, bet_amount
            )
            
            if "error" in result:
                await ctx.send(result["error"])
                return
            
            await ctx.send(f"✅ Partida APOSTADO criada! ID: `{result['match_id'][:6]}`")

        # ============================================================
        # ENTRAR EM PARTIDA
        # ============================================================

        @self.bot.command(name="join")
        async def join_cmd(ctx, match_id: str, team: Optional[str] = None):
            """Entra em uma partida"""
            if team and team not in ["team1", "team2"]:
                await ctx.send("❌ Times: team1 ou team2")
                return
            
            result = await self.match_system.join_lobby(match_id, str(ctx.author.id), team)
            
            if "error" in result:
                await ctx.send(result["error"])
                return
            
            if result.get("match_started"):
                await ctx.send("✅ Partida cheia! Ticket sendo aberto...")
            else:
                await ctx.send(f"✅ Entrou na partida! ({result.get('player_count', 0)} jogadores)")

        # ============================================================
        # CONFIGURAÇÃO
        # ============================================================

        @self.bot.command(name="config")
        @commands.has_permissions(administrator=True)
        async def config_cmd(ctx):
            """Mostra configurações atuais"""
            settings = get_guild_settings(str(ctx.guild.id))
            
            embed = discord.Embed(
                title="⚙️ CONFIGURAÇÕES",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            
            # Moeda
            currency = settings.get("currency", {})
            embed.add_field(
                name="💰 Moeda",
                value=f"**Nome:** {currency.get('name', 'Moedas')}\n**Símbolo:** {currency.get('symbol', '💰')}",
                inline=False
            )
            
            # RANKED
            ranked = settings.get("ranked", {})
            embed.add_field(
                name="🏆 RANKED",
                value=f"**Bônus Vitória:** +{ranked.get('win_bonus', 50)}\n**Penalidade Derrota:** -{ranked.get('loss_penalty', 10)}\n**Taxa Entrada:** {ranked.get('entry_fee', 0)}",
                inline=False
            )
            
            # BETTING
            betting = settings.get("betting", {})
            embed.add_field(
                name="💰 APOSTADO",
                value=f"**Mínimo:** {betting.get('min_bet', 100)}\n**Máximo:** {betting.get('max_bet', 10000)}\n**Multiplicador:** x{betting.get('win_multiplier', 2.0)}\n**Taxa:** {betting.get('tax_percent', 5.0)}%",
                inline=False
            )
            
            # Mediadores
            mediator_roles = get_mediator_roles(str(ctx.guild.id))
            embed.add_field(
                name="👑 Mediadores",
                value=", ".join([f"<@&{r}>" for r in mediator_roles]) if mediator_roles else "❌ Nenhum",
                inline=False
            )
            
            embed.set_footer(text="Use !setconfig para alterar")
            await ctx.send(embed=embed)

        @self.bot.command(name="setconfig")
        @commands.has_permissions(administrator=True)
        async def setconfig_cmd(ctx, key: str, *, value: str):
            """Configura qualquer opção"""
            valid_keys = [
                "currency.name", "currency.symbol",
                "ranked.win_bonus", "ranked.loss_penalty", "ranked.entry_fee",
                "betting.min_bet", "betting.max_bet", "betting.win_multiplier", "betting.tax_percent"
            ]
            
            if key not in valid_keys:
                await ctx.send(f"❌ Chaves válidas:\n{chr(10).join(valid_keys)}")
                return
            
            # Converter valor
            if value.lower() in ["true", "false", "on", "off"]:
                value = value.lower() in ["true", "on"]
            elif value.isdigit():
                value = int(value)
            elif value.replace(".", "").isdigit():
                value = float(value)
            
            update_guild_settings(str(ctx.guild.id), key, value)
            await ctx.send(f"✅ `{key}` = `{value}`")

        @self.bot.command(name="setmediator")
        @commands.has_permissions(administrator=True)
        async def setmediator_cmd(ctx, role: discord.Role):
            """Define cargo mediador"""
            set_mediator_role(str(ctx.guild.id), role.id)
            await ctx.send(f"✅ {role.mention} agora é cargo mediador!")

        # ============================================================
        # ADMINISTRAÇÃO DE VITÓRIAS
        # ============================================================

        @self.bot.command(name="addwins")
        @commands.has_permissions(administrator=True)
        async def addwins_cmd(ctx, member: discord.Member, amount: int, match_type: str = "1v1"):
            """Adiciona vitórias a um jogador"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            if amount <= 0:
                await ctx.send("❌ Valor positivo!")
                return
            
            for _ in range(amount):
                update_player_stats(str(ctx.guild.id), str(member.id), match_type, "win")
            
            await ctx.send(f"✅ +{amount} vitórias para {member.mention} no {match_type}!")

        @self.bot.command(name="removewins")
        @commands.has_permissions(administrator=True)
        async def removewins_cmd(ctx, member: discord.Member, amount: int, match_type: str = "1v1"):
            """Remove vitórias de um jogador"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            if amount <= 0:
                await ctx.send("❌ Valor positivo!")
                return
            
            stats = get_player_stats(str(ctx.guild.id), str(member.id))
            current_wins = stats.get("stats", {}).get(match_type, {}).get("wins", 0)
            
            if current_wins < amount:
                await ctx.send(f"❌ {member.mention} tem apenas {current_wins} vitórias no {match_type}")
                return
            
            for _ in range(amount):
                update_player_stats(str(ctx.guild.id), str(member.id), match_type, "loss")
            
            await ctx.send(f"✅ -{amount} vitórias de {member.mention} no {match_type}!")

        @self.bot.command(name="setwins")
        @commands.has_permissions(administrator=True)
        async def setwins_cmd(ctx, member: discord.Member, amount: int, match_type: str = "1v1"):
            """Define o número exato de vitórias de um jogador"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            if amount < 0:
                await ctx.send("❌ Valor deve ser positivo!")
                return
            
            stats = get_player_stats(str(ctx.guild.id), str(member.id))
            current_wins = stats.get("stats", {}).get(match_type, {}).get("wins", 0)
            
            diff = amount - current_wins
            
            if diff > 0:
                for _ in range(diff):
                    update_player_stats(str(ctx.guild.id), str(member.id), match_type, "win")
            elif diff < 0:
                for _ in range(-diff):
                    update_player_stats(str(ctx.guild.id), str(member.id), match_type, "loss")
            
            await ctx.send(f"✅ Vitórias de {member.mention} no {match_type} definidas para {amount}!")

        # ============================================================
        # PRÊMIOS
        # ============================================================

        @self.bot.command(name="distributetop")
        @commands.has_permissions(administrator=True)
        async def distributetop_cmd(ctx, match_type: str = "1v1"):
            """Distribui prêmios para o top 10"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            if not can_distribute_prizes(str(ctx.guild.id)):
                await ctx.send("⏳ Ainda não pode distribuir prêmios!")
                return
            
            result = distribute_top_prizes(str(ctx.guild.id), match_type)
            
            if not result["success"]:
                await ctx.send(f"❌ {result['message']}")
                return
            
            embed = discord.Embed(
                title="🏅 PRÊMIOS DISTRIBUÍDOS!",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            for pos, data in result["distributed"].items():
                try:
                    user = await self.bot.fetch_user(int(data["user_id"]))
                    embed.add_field(
                        name=f"#{pos} {user.display_name}",
                        value=f"💰 {data['amount']} moedas",
                        inline=False
                    )
                except:
                    pass
            
            await ctx.send(embed=embed)

        # ============================================================
        # ECONOMIA (ADMIN)
        # ============================================================

        @self.bot.command(name="ecogive")
        @commands.has_permissions(administrator=True)
        async def ecogive_cmd(ctx, member: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            if amount <= 0:
                await ctx.send("❌ Valor positivo!")
                return
            add_player_balance(ctx.guild.id, member.id, amount, reason)
            await ctx.send(f"✅ {amount} moedas para {member.mention}!")

        @self.bot.command(name="ecoremove")
        @commands.has_permissions(administrator=True)
        async def ecoremove_cmd(ctx, member: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            if amount <= 0:
                await ctx.send("❌ Valor positivo!")
                return
            current = get_player_balance(ctx.guild.id, member.id)
            if current < amount:
                await ctx.send(f"❌ {member.mention} tem apenas {current} moedas!")
                return
            remove_player_balance(ctx.guild.id, member.id, amount, reason)
            await ctx.send(f"✅ {amount} moedas removidas de {member.mention}!")

        @self.bot.command(name="ecoset")
        @commands.has_permissions(administrator=True)
        async def ecoset_cmd(ctx, member: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            if amount < 0:
                await ctx.send("❌ Valor deve ser positivo!")
                return
            current = get_player_balance(ctx.guild.id, member.id)
            diff = amount - current
            if diff > 0:
                add_player_balance(ctx.guild.id, member.id, diff, reason)
            elif diff < 0:
                remove_player_balance(ctx.guild.id, member.id, -diff, reason)
            await ctx.send(f"✅ Saldo de {member.mention} definido para {amount}!")

        print("✅ Comandos admin registrados!")
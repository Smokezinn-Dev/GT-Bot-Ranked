# ============================================================
# ADMIN_COMMANDS.PY - COMANDOS 100% CUSTOMIZÁVEIS
# SISTEMA RANKED/APOSTADO - COMPLETO
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
    add_mediator_role, remove_mediator_role,
    distribute_top_prizes, can_distribute_prizes,
    get_active_matches, get_match, update_match,
    get_player_rank_stats, is_mediator
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
        # 1. RANKING E ESTATÍSTICAS
        # ============================================================

        @self.bot.command(name="rank")
        async def rank_cmd(ctx, match_type: str = "1v1"):
            """Mostra ranking - !rank [1v1|2v2|3v3]"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            embed = await self.ranking_system.generate_ranking_embed(str(ctx.guild.id), match_type)
            await ctx.send(embed=embed)

        @self.bot.command(name="myrank")
        async def myrank_cmd(ctx, match_type: str = "1v1"):
            """Minhas estatísticas - !myrank [1v1|2v2|3v3]"""
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
                max_players = self.match_system.match_types[m['match_type']]['max_players']
                embed.add_field(
                    name=f"🏆 RANKED - {m['_id'][:6]}",
                    value=f"**Tipo:** {m['match_type']}\n**Mapa:** {m['map']}\n**Jogadores:** {len(m.get('players', []))}/{max_players}",
                    inline=False
                )
            
            for m in betting[:5]:
                max_players = self.match_system.match_types[m['match_type']]['max_players']
                embed.add_field(
                    name=f"💰 APOSTADO - {m['_id'][:6]}",
                    value=f"**Tipo:** {m['match_type']}\n**Aposta:** {m.get('bet_amount', 0)} moedas\n**Jogadores:** {len(m.get('players', []))}/{max_players}",
                    inline=False
                )
            
            await ctx.send(embed=embed)

        # ============================================================
        # 2. CRIAÇÃO DE PARTIDAS
        # ============================================================

        @self.bot.command(name="ranked")
        @commands.has_permissions(administrator=True)
        async def ranked_cmd(ctx, match_type: str, map_name: str = "Arena"):
            """Cria partida RANKED - !ranked <tipo> [mapa]"""
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
            """Cria partida APOSTADO - !apostado <tipo> <aposta> [mapa]"""
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
        # 3. ENTRAR EM PARTIDA
        # ============================================================

        @self.bot.command(name="join")
        async def join_cmd(ctx, match_id: str, team: Optional[str] = None):
            """Entra em uma partida - !join <ID> [team1|team2]"""
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
        # 4. CONFIGURAÇÃO DO SERVIDOR
        # ============================================================

        @self.bot.command(name="config")
        @commands.has_permissions(administrator=True)
        async def config_cmd(ctx):
            """Mostra configurações atuais"""
            settings = get_guild_settings(str(ctx.guild.id))
            
            embed = discord.Embed(
                title="⚙️ CONFIGURAÇÕES DO SERVIDOR",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            
            # Moeda
            currency = settings.get("currency", {})
            embed.add_field(
                name="💰 MOEDA",
                value=f"**Nome:** {currency.get('name', 'Moedas')}\n**Símbolo:** {currency.get('symbol', '💰')}",
                inline=False
            )
            
            # RANKED
            ranked = settings.get("ranked", {})
            embed.add_field(
                name="🏆 RANKED",
                value=f"**Status:** {'✅ Ativo' if ranked.get('enabled', True) else '❌ Inativo'}\n"
                      f"**Bônus Vitória:** +{ranked.get('win_bonus', 50)}\n"
                      f"**Penalidade Derrota:** -{ranked.get('loss_penalty', 10)}\n"
                      f"**Taxa Entrada:** {ranked.get('entry_fee', 0)}\n"
                      f"**Máx Partidas:** {ranked.get('max_matches_per_user', 3)}",
                inline=False
            )
            
            # BETTING
            betting = settings.get("betting", {})
            embed.add_field(
                name="💰 APOSTADO",
                value=f"**Status:** {'✅ Ativo' if betting.get('enabled', True) else '❌ Inativo'}\n"
                      f"**Aposta Mín:** {betting.get('min_bet', 100)}\n"
                      f"**Aposta Máx:** {betting.get('max_bet', 10000)}\n"
                      f"**Multiplicador:** x{betting.get('win_multiplier', 2.0)}\n"
                      f"**Taxa:** {betting.get('tax_percent', 5.0)}%",
                inline=False
            )
            
            # PRÊMIOS
            prizes = settings.get("top_prizes", {})
            embed.add_field(
                name="🏅 PRÊMIOS",
                value=f"**Status:** {'✅ Ativo' if prizes.get('enabled', True) else '❌ Inativo'}\n"
                      f"**1º:** {prizes.get('prizes', {}).get('1', 10000)}\n"
                      f"**2º:** {prizes.get('prizes', {}).get('2', 5000)}\n"
                      f"**3º:** {prizes.get('prizes', {}).get('3', 2500)}\n"
                      f"**4º-10º:** {prizes.get('prizes', {}).get('4_10', 1000)}\n"
                      f"**Intervalo:** {prizes.get('interval_days', 7)} dias",
                inline=False
            )
            
            # MEDIADORES
            mediator_roles = get_mediator_roles(str(ctx.guild.id))
            embed.add_field(
                name="👑 MEDIADORES",
                value=", ".join([f"<@&{r}>" for r in mediator_roles]) if mediator_roles else "❌ Nenhum cargo definido",
                inline=False
            )
            
            embed.set_footer(text="Use !setconfig para alterar")
            await ctx.send(embed=embed)

        @self.bot.command(name="setconfig")
        @commands.has_permissions(administrator=True)
        async def setconfig_cmd(ctx, key: str, *, value: str):
            """Configura qualquer opção - !setconfig <chave> <valor>"""
            valid_keys = [
                "currency.name", "currency.symbol",
                "ranked.enabled", "ranked.win_bonus", "ranked.loss_penalty", "ranked.entry_fee",
                "ranked.max_matches_per_user",
                "betting.enabled", "betting.min_bet", "betting.max_bet", 
                "betting.win_multiplier", "betting.tax_percent",
                "top_prizes.enabled", "top_prizes.interval_days",
                "top_prizes.prizes.1", "top_prizes.prizes.2", "top_prizes.prizes.3", "top_prizes.prizes.4_10",
                "customization.embed_color", "customization.embed_footer",
                "customization.dm_notifications", "customization.ping_players"
            ]
            
            if key not in valid_keys:
                await ctx.send(f"❌ Chave inválida!\nChaves válidas:\n{chr(10).join(valid_keys)}")
                return
            
            # Converter valor
            if value.lower() in ["true", "false", "on", "off", "sim", "não"]:
                value = value.lower() in ["true", "on", "sim"]
            elif value.isdigit():
                value = int(value)
            elif value.replace(".", "").isdigit():
                value = float(value)
            
            update_guild_settings(str(ctx.guild.id), key, value)
            await ctx.send(f"✅ `{key}` = `{value}`")

        @self.bot.command(name="setranked")
        @commands.has_permissions(administrator=True)
        async def setranked_cmd(ctx, option: str, value: str):
            """Configura RANKED - !setranked <opção> <valor>"""
            mapping = {
                "win_bonus": "ranked.win_bonus",
                "loss_penalty": "ranked.loss_penalty",
                "entry_fee": "ranked.entry_fee",
                "max_matches": "ranked.max_matches_per_user"
            }
            if option not in mapping:
                await ctx.send(f"❌ Opções: {', '.join(mapping.keys())}")
                return
            await setconfig_cmd(ctx, mapping[option], value)

        @self.bot.command(name="setbetting")
        @commands.has_permissions(administrator=True)
        async def setbetting_cmd(ctx, option: str, value: str):
            """Configura APOSTADO - !setbetting <opção> <valor>"""
            mapping = {
                "min_bet": "betting.min_bet",
                "max_bet": "betting.max_bet",
                "win_multiplier": "betting.win_multiplier",
                "tax": "betting.tax_percent"
            }
            if option not in mapping:
                await ctx.send(f"❌ Opções: {', '.join(mapping.keys())}")
                return
            await setconfig_cmd(ctx, mapping[option], value)

        @self.bot.command(name="setprizes")
        @commands.has_permissions(administrator=True)
        async def setprizes_cmd(ctx, position: str, amount: int):
            """Configura prêmios - !setprizes <posição> <valor>"""
            if position not in ["1", "2", "3", "4_10"]:
                await ctx.send("❌ Posições: 1, 2, 3, 4_10")
                return
            await setconfig_cmd(ctx, f"top_prizes.prizes.{position}", str(amount))

        @self.bot.command(name="setcurrency")
        @commands.has_permissions(administrator=True)
        async def setcurrency_cmd(ctx, option: str, *, value: str):
            """Configura moeda - !setcurrency <opção> <valor>"""
            mapping = {
                "name": "currency.name", 
                "symbol": "currency.symbol", 
                "bonus": "currency.daily_bonus"
            }
            if option not in mapping:
                await ctx.send(f"❌ Opções: {', '.join(mapping.keys())}")
                return
            await setconfig_cmd(ctx, mapping[option], value)

        # ============================================================
        # 5. MEDIADORES
        # ============================================================

        @self.bot.command(name="setmediator")
        @commands.has_permissions(administrator=True)
        async def setmediator_cmd(ctx, role: discord.Role):
            """Define cargo mediador - !setmediator @cargo"""
            set_mediator_role(str(ctx.guild.id), role.id)
            await ctx.send(f"✅ {role.mention} agora é cargo mediador!")

        @self.bot.command(name="addmediator")
        @commands.has_permissions(administrator=True)
        async def addmediator_cmd(ctx, role: discord.Role):
            """Adiciona cargo mediador - !addmediator @cargo"""
            result = add_mediator_role(str(ctx.guild.id), role.id)
            if result:
                await ctx.send(f"✅ {role.mention} adicionado como mediador!")
            else:
                await ctx.send(f"⚠️ {role.mention} já é mediador!")

        @self.bot.command(name="removemediator")
        @commands.has_permissions(administrator=True)
        async def removemediator_cmd(ctx, role: discord.Role):
            """Remove cargo mediador - !removemediator @cargo"""
            result = remove_mediator_role(str(ctx.guild.id), role.id)
            if result:
                await ctx.send(f"✅ {role.mention} removido dos mediadores!")
            else:
                await ctx.send(f"⚠️ {role.mention} não é mediador!")

        @self.bot.command(name="mediators")
        @commands.has_permissions(administrator=True)
        async def mediators_cmd(ctx):
            """Lista cargos mediadores"""
            roles = get_mediator_roles(str(ctx.guild.id))
            if not roles:
                await ctx.send("❌ Nenhum cargo mediador definido!")
                return
            
            embed = discord.Embed(
                title="👑 CARGOS MEDIADORES",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            
            for role_id in roles:
                role = ctx.guild.get_role(role_id)
                if role:
                    embed.add_field(name="📌 Cargo", value=role.mention, inline=False)
            
            await ctx.send(embed=embed)

        # ============================================================
        # 6. ADMINISTRAÇÃO DE VITÓRIAS
        # ============================================================

        @self.bot.command(name="addwins")
        @commands.has_permissions(administrator=True)
        async def addwins_cmd(ctx, member: discord.Member, amount: int, match_type: str = "1v1"):
            """Adiciona vitórias - !addwins @user <quantidade> [tipo]"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            if amount <= 0:
                await ctx.send("❌ Valor deve ser positivo!")
                return
            
            for _ in range(amount):
                update_player_stats(str(ctx.guild.id), str(member.id), match_type, "win")
            
            await ctx.send(f"✅ +{amount} vitórias para {member.mention} no {match_type}!")

        @self.bot.command(name="removewins")
        @commands.has_permissions(administrator=True)
        async def removewins_cmd(ctx, member: discord.Member, amount: int, match_type: str = "1v1"):
            """Remove vitórias - !removewins @user <quantidade> [tipo]"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            if amount <= 0:
                await ctx.send("❌ Valor deve ser positivo!")
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
            """Define vitórias - !setwins @user <quantidade> [tipo]"""
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
        # 7. PRÊMIOS
        # ============================================================

        @self.bot.command(name="distributetop")
        @commands.has_permissions(administrator=True)
        async def distributetop_cmd(ctx, match_type: str = "1v1"):
            """Distribui prêmios para o top 10 - !distributetop [tipo]"""
            if match_type not in ["1v1", "2v2", "3v3"]:
                await ctx.send("❌ Tipos: 1v1, 2v2, 3v3")
                return
            
            if not can_distribute_prizes(str(ctx.guild.id)):
                await ctx.send("⏳ Ainda não pode distribuir prêmios! Aguarde o intervalo.")
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

        @self.bot.command(name="topinfo")
        async def topinfo_cmd(ctx):
            """Mostra informações sobre prêmios"""
            settings = get_guild_settings(str(ctx.guild.id))
            prizes = settings.get("top_prizes", {})
            
            embed = discord.Embed(
                title="🏅 INFORMAÇÕES DOS PRÊMIOS",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="📋 Prêmios",
                value=f"**1º:** {prizes.get('prizes', {}).get('1', 10000)}\n"
                      f"**2º:** {prizes.get('prizes', {}).get('2', 5000)}\n"
                      f"**3º:** {prizes.get('prizes', {}).get('3', 2500)}\n"
                      f"**4º-10º:** {prizes.get('prizes', {}).get('4_10', 1000)}",
                inline=False
            )
            
            last_dist = prizes.get("last_distribution")
            if last_dist:
                interval = prizes.get("interval_days", 7)
                next_dist = last_dist + timedelta(days=interval)
                embed.add_field(
                    name="⏳ Próxima Distribuição",
                    value=f"<t:{int(next_dist.timestamp())}:R>",
                    inline=False
                )
            else:
                embed.add_field(name="⏳ Próxima Distribuição", value="Disponível agora!", inline=False)
            
            embed.set_footer(text="Use !distributetop para distribuir")
            await ctx.send(embed=embed)

        # ============================================================
        # 8. ECONOMIA (ADMIN)
        # ============================================================

        @self.bot.command(name="ecogive")
        @commands.has_permissions(administrator=True)
        async def ecogive_cmd(ctx, member: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            """Dá moedas - !ecogive @user <valor> [motivo]"""
            if amount <= 0:
                await ctx.send("❌ Valor deve ser positivo!")
                return
            add_player_balance(ctx.guild.id, member.id, amount, reason)
            await ctx.send(f"✅ {amount} moedas para {member.mention}!\n**Motivo:** {reason}")

        @self.bot.command(name="ecoremove")
        @commands.has_permissions(administrator=True)
        async def ecoremove_cmd(ctx, member: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            """Remove moedas - !ecoremove @user <valor> [motivo]"""
            if amount <= 0:
                await ctx.send("❌ Valor deve ser positivo!")
                return
            current = get_player_balance(ctx.guild.id, member.id)
            if current < amount:
                await ctx.send(f"❌ {member.mention} tem apenas {current} moedas!")
                return
            remove_player_balance(ctx.guild.id, member.id, amount, reason)
            await ctx.send(f"✅ {amount} moedas removidas de {member.mention}!\n**Motivo:** {reason}")

        @self.bot.command(name="ecoset")
        @commands.has_permissions(administrator=True)
        async def ecoset_cmd(ctx, member: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            """Define saldo - !ecoset @user <valor> [motivo]"""
            if amount < 0:
                await ctx.send("❌ Valor deve ser positivo!")
                return
            current = get_player_balance(ctx.guild.id, member.id)
            diff = amount - current
            if diff > 0:
                add_player_balance(ctx.guild.id, member.id, diff, reason)
            elif diff < 0:
                remove_player_balance(ctx.guild.id, member.id, -diff, reason)
            await ctx.send(f"✅ Saldo de {member.mention} definido para {amount}!\n**Motivo:** {reason}")

        # ============================================================
        # 9. UTILITÁRIOS ADMIN
        # ============================================================

        @self.bot.command(name="cachestats")
        @commands.has_permissions(administrator=True)
        async def cache_stats_cmd(ctx):
            """Mostra estatísticas do cache"""
            ranking_stats = self.ranking_system.get_cache_stats()
            match_stats = self.match_system.get_cache_stats()
            
            embed = discord.Embed(
                title="📊 ESTATÍSTICAS DO CACHE",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="🏆 Ranking System",
                value=f"**Cache Hit Rate:** {ranking_stats['hit_rate']}\n"
                      f"**Cache Size:** {ranking_stats['cache_size']}\n"
                      f"**Hits:** {ranking_stats['hits']}\n"
                      f"**Misses:** {ranking_stats['misses']}",
                inline=False
            )
            
            embed.add_field(
                name="🎮 Match System",
                value=f"**Lobbies Ativos:** {match_stats['total']}\n"
                      f"**Aguardando:** {match_stats['waiting']}\n"
                      f"**Iniciados:** {match_stats['started']}\n"
                      f"**Apostados:** {match_stats['betting']}",
                inline=False
            )
            
            await ctx.send(embed=embed)

        @self.bot.command(name="clearcache")
        @commands.has_permissions(administrator=True)
        async def clear_cache_cmd(ctx):
            """Limpa o cache do sistema"""
            self.ranking_system.clear_cache()
            await ctx.send("🧹 Cache limpo com sucesso!")

        @self.bot.command(name="matchinfo")
        @commands.has_permissions(administrator=True)
        async def match_info_cmd(ctx, match_id: str):
            """Mostra informações de uma partida - !matchinfo <ID>"""
            match_data = get_match(match_id, False)
            if not match_data:
                match_data = get_match(match_id, True)
            
            if not match_data:
                await ctx.send(f"❌ Partida `{match_id}` não encontrada!")
                return
            
            embed = discord.Embed(
                title=f"📋 INFORMAÇÕES DA PARTIDA",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(name="🆔 ID", value=match_data['_id'][:6], inline=True)
            embed.add_field(name="🎯 Tipo", value=match_data['match_type'], inline=True)
            embed.add_field(name="🗺️ Mapa", value=match_data['map'], inline=True)
            embed.add_field(name="📊 Status", value=match_data['status'], inline=True)
            embed.add_field(name="💰 Aposta", value=match_data.get('bet_amount', 0), inline=True)
            embed.add_field(name="👥 Jogadores", value=f"{len(match_data.get('players', []))}", inline=True)
            
            if match_data.get('players'):
                players_text = "\n".join([f"👤 <@{p}>" for p in match_data['players']])
                embed.add_field(name="📋 Jogadores", value=players_text, inline=False)
            
            await ctx.send(embed=embed)

        @self.bot.command(name="cancelmatch")
        @commands.has_permissions(administrator=True)
        async def cancel_match_cmd(ctx, match_id: str):
            """Cancela uma partida - !cancelmatch <ID>"""
            result = await self.match_system.cancel_match(match_id)
            if result:
                await ctx.send(f"✅ Partida `{match_id[:6]}` cancelada com sucesso!")
            else:
                await ctx.send(f"❌ Partida `{match_id}` não encontrada!")

        # ============================================================
        # 10. SISTEMA DE MAPAS
        # ============================================================

        @self.bot.command(name="addmap")
        @commands.has_permissions(administrator=True)
        async def add_map_cmd(ctx, *, map_name: str):
            """Adiciona um mapa ao servidor - !addmap <nome>"""
            settings = get_guild_settings(str(ctx.guild.id))
            maps = settings.get("ranked", {}).get("maps", [])
            
            if map_name in maps:
                await ctx.send(f"⚠️ Mapa `{map_name}` já existe!")
                return
            
            maps.append(map_name)
            update_guild_settings(str(ctx.guild.id), "ranked.maps", maps)
            await ctx.send(f"✅ Mapa `{map_name}` adicionado!")

        @self.bot.command(name="removemap")
        @commands.has_permissions(administrator=True)
        async def remove_map_cmd(ctx, *, map_name: str):
            """Remove um mapa do servidor - !removemap <nome>"""
            settings = get_guild_settings(str(ctx.guild.id))
            maps = settings.get("ranked", {}).get("maps", [])
            
            if map_name not in maps:
                await ctx.send(f"⚠️ Mapa `{map_name}` não encontrado!")
                return
            
            maps.remove(map_name)
            update_guild_settings(str(ctx.guild.id), "ranked.maps", maps)
            await ctx.send(f"✅ Mapa `{map_name}` removido!")

        @self.bot.command(name="maps")
        @commands.has_permissions(administrator=True)
        async def list_maps_cmd(ctx):
            """Lista mapas disponíveis"""
            settings = get_guild_settings(str(ctx.guild.id))
            maps = settings.get("ranked", {}).get("maps", [])
            
            if not maps:
                await ctx.send("❌ Nenhum mapa cadastrado!")
                return
            
            embed = discord.Embed(
                title="🗺️ MAPAS DISPONÍVEIS",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            
            for i, map_name in enumerate(maps, 1):
                embed.add_field(name=f"#{i}", value=map_name, inline=True)
            
            await ctx.send(embed=embed)

        print("✅ Comandos admin registrados!")

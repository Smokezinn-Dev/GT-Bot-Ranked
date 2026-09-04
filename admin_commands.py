# ============================================================
# ADMIN_COMMANDS.PY - COMANDOS 100% CUSTOMIZÁVEIS
# ============================================================

import discord
from discord.ext import commands
from typing import Optional
from datetime import datetime

from database import (
    get_guild_settings,
    update_guild_settings,
    get_player_balance,
    add_player_balance,
    remove_player_balance,
    get_rankings,
    distribute_top_prizes,
    can_distribute_prizes
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
        # COMANDOS PÚBLICOS
        # ============================================================

        @self.bot.command(name='rank')
        async def rank_cmd(ctx, match_type: str = '1v1'):
            """Ranking RANKED"""
            if match_type not in self.config.MATCH_TYPES:
                await ctx.send(f"❌ Tipos: {', '.join(self.config.MATCH_TYPES)}")
                return
            embed = await self.ranking_system.generate_ranking_embed(str(ctx.guild.id), match_type)
            await ctx.send(embed=embed)

        @self.bot.command(name='myrank')
        async def myrank_cmd(ctx, match_type: str = '1v1'):
            """Minhas estatísticas"""
            if match_type not in self.config.MATCH_TYPES:
                await ctx.send(f"❌ Tipos: {', '.join(self.config.MATCH_TYPES)}")
                return
            embed = await self.ranking_system.get_player_stats_embed(str(ctx.guild.id), str(ctx.author.id), ctx.author)
            await ctx.send(embed=embed)

        @self.bot.command(name='matches')
        async def matches_cmd(ctx):
            """Lista partidas ativas"""
            if not self.match_system.active_lobbies:
                await ctx.send("📭 Nenhuma partida ativa!")
                return
            
            embed = discord.Embed(title="🎮 Partidas Ativas", color=self.config.EMBED_COLOR)
            for match_id, lobby in self.match_system.active_lobbies.items():
                if lobby['status'] == 'waiting':
                    categoria = "💰 APOSTADO" if lobby['is_betting'] else "🏆 RANKED"
                    match_data = get_match(match_id, lobby['is_betting'])
                    if match_data:
                        max_players = self.match_system.match_types[match_data['match_type']]['max_players']
                        embed.add_field(
                            name=f"{categoria} {match_id[:6]}",
                            value=f"**Tipo:** {match_data['match_type']}\n**Mapa:** {match_data['map']}\n**Jogadores:** {len(lobby['players'])}/{max_players}\n**Criador:** <@{match_data['creator_id']}>",
                            inline=False
                        )
            await ctx.send(embed=embed)

        @self.bot.command(name='join')
        async def join_cmd(ctx, match_id: str, team: Optional[str] = None):
            """Entra em uma partida"""
            if team and team not in ['team1', 'team2']:
                await ctx.send("❌ Times: team1 ou team2")
                return
            result = await self.match_system.join_lobby(match_id, str(ctx.author.id), team)
            if 'error' in result:
                await ctx.send(result['error'])
                return
            embed = discord.Embed(title="✅ Entrou!", description=f"Partida `{match_id}`\nJogadores: {result['player_count']}", color=0x00ff00)
            await ctx.send(embed=embed)

        # ============================================================
        # COMANDOS DE CRIAÇÃO (RANKED E APOSTADO)
        # ============================================================

        @self.bot.command(name='create')
        @commands.has_permissions(administrator=True)
        async def create_cmd(ctx, match_type: str, map_name: str = 'Mapa Padrão', bet_amount: int = 0):
            """Cria partida RANKED (sem aposta) ou APOSTADO (com aposta)"""
            if match_type not in self.config.MATCH_TYPES:
                await ctx.send(f"❌ Tipos: {', '.join(self.config.MATCH_TYPES)}")
                return
            
            is_betting = bet_amount > 0
            
            result = await self.match_system.create_lobby(
                str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id),
                match_type, map_name, is_betting, bet_amount
            )
            
            if 'error' in result:
                await ctx.send(result['error'])
                return
            
            categoria = "APOSTADO" if is_betting else "RANKED"
            embed = discord.Embed(
                title=f"🎮 Partida {categoria} Criada!",
                description=f"**Tipo:** {match_type}\n**Mapa:** {map_name}\n**Aposta:** {bet_amount if is_betting else 'N/A'}\n**ID:** `{result['match_id']}`",
                color=self.config.EMBED_COLOR
            )
            await ctx.send(embed=embed)

        @self.bot.command(name='ranked')
        @commands.has_permissions(administrator=True)
        async def ranked_cmd(ctx, match_type: str, map_name: str = 'Mapa Padrão'):
            """Cria partida RANKED (conta no ranking)"""
            await create_cmd(ctx, match_type, map_name, 0)

        @self.bot.command(name='apostado')
        @commands.has_permissions(administrator=True)
        async def apostado_cmd(ctx, match_type: str, bet_amount: int, map_name: str = 'Mapa Padrão'):
            """Cria partida APOSTADO (não conta no ranking)"""
            if bet_amount <= 0:
                await ctx.send("❌ Aposta deve ser positiva!")
                return
            await create_cmd(ctx, match_type, map_name, bet_amount)

        # ============================================================
        # COMANDOS DE CONFIGURAÇÃO (100% CUSTOMIZÁVEL)
        # ============================================================

        @self.bot.command(name='config')
        @commands.has_permissions(administrator=True)
        async def config_cmd(ctx):
            """Mostra configurações atuais"""
            settings = get_guild_settings(str(ctx.guild.id))
            
            embed = discord.Embed(
                title="⚙️ CONFIGURAÇÕES DO SERVIDOR",
                color=self.config.EMBED_COLOR,
                timestamp=datetime.utcnow()
            )
            
            # Moeda
            currency = settings.get('currency', {})
            embed.add_field(
                name="💰 Moeda",
                value=f"**Nome:** {currency.get('name', 'Moeda')}\n**Símbolo:** {currency.get('symbol', '💰')}\n**Bônus Diário:** {currency.get('daily_bonus', 100)}",
                inline=False
            )
            
            # RANKED
            ranked = settings.get('ranked', {})
            embed.add_field(
                name="🏆 RANKED",
                value=f"**Status:** {'✅ Ativo' if ranked.get('enabled', True) else '❌ Inativo'}\n**Bônus Vitória:** +{ranked.get('win_bonus', 50)}\n**Penalidade Derrota:** -{ranked.get('loss_penalty', 10)}\n**Taxa Entrada:** {ranked.get('entry_fee', 0)}\n**Máx Partidas:** {ranked.get('max_matches_per_user', 3)}",
                inline=False
            )
            
            # BETTING
            betting = settings.get('betting', {})
            embed.add_field(
                name="💰 APOSTADO",
                value=f"**Status:** {'✅ Ativo' if betting.get('enabled', True) else '❌ Inativo'}\n**Aposta Mín:** {betting.get('min_bet', 100)}\n**Aposta Máx:** {betting.get('max_bet', 10000)}\n**Multiplicador:** x{betting.get('win_multiplier', 2.0)}\n**Taxa:** {betting.get('tax_percent', 5.0)}%",
                inline=False
            )
            
            # TOP PRIZES
            prizes = settings.get('top_prizes', {})
            embed.add_field(
                name="🏅 PRÊMIOS POR TOP",
                value=f"**Status:** {'✅ Ativo' if prizes.get('enabled', True) else '❌ Inativo'}\n**1º:** {prizes.get('prizes', {}).get('1', 10000)}\n**2º:** {prizes.get('prizes', {}).get('2', 5000)}\n**3º:** {prizes.get('prizes', {}).get('3', 2500)}\n**4º-10º:** {prizes.get('prizes', {}).get('4_10', 1000)}\n**Intervalo:** {prizes.get('interval_days', 7)} dias",
                inline=False
            )
            
            embed.set_footer(text=self.config.EMBED_FOOTER)
            await ctx.send(embed=embed)

        @self.bot.command(name='setconfig')
        @commands.has_permissions(administrator=True)
        async def setconfig_cmd(ctx, key: str, *, value: str):
            """Configura qualquer opção! Ex: !setconfig ranked.win_bonus 100"""
            valid_paths = [
                'currency.name', 'currency.symbol', 'currency.daily_bonus', 'currency.bonus_multiplier',
                'ranked.enabled', 'ranked.win_bonus', 'ranked.loss_penalty', 'ranked.entry_fee',
                'ranked.max_matches_per_user', 'ranked.allowed_roles',
                'betting.enabled', 'betting.min_bet', 'betting.max_bet', 'betting.win_multiplier',
                'betting.tax_percent', 'betting.max_players', 'betting.allowed_roles',
                'top_prizes.enabled', 'top_prizes.interval_days',
                'top_prizes.prizes.1', 'top_prizes.prizes.2', 'top_prizes.prizes.3', 'top_prizes.prizes.4_10',
                'match_settings.auto_ticket', 'match_settings.ticket_name_template',
                'match_settings.timeout_minutes', 'match_settings.lobby_timeout',
                'customization.embed_color', 'customization.embed_footer',
                'customization.dm_notifications', 'customization.ping_players'
            ]
            
            if key not in valid_paths:
                await ctx.send(f"❌ Chaves válidas:\n{chr(10).join(valid_paths[:15])}\n...")
                return
            
            # Converter valor
            if value.lower() in ['true', 'false', 'on', 'off', 'sim', 'não']:
                value = value.lower() in ['true', 'on', 'sim']
            elif value.isdigit():
                value = int(value)
            elif value.replace('.', '').isdigit():
                value = float(value)
            
            update_guild_settings(str(ctx.guild.id), key, value)
            
            embed = discord.Embed(
                title="✅ Configuração Atualizada!",
                description=f"**{key}** = `{value}`",
                color=0x00ff00
            )
            await ctx.send(embed=embed)

        @self.bot.command(name='setranked')
        @commands.has_permissions(administrator=True)
        async def setranked_cmd(ctx, option: str, value: str):
            """Configura RANKED: win_bonus, loss_penalty, entry_fee, max_matches"""
            mapping = {
                'win_bonus': 'ranked.win_bonus',
                'loss_penalty': 'ranked.loss_penalty',
                'entry_fee': 'ranked.entry_fee',
                'max_matches': 'ranked.max_matches_per_user'
            }
            if option not in mapping:
                await ctx.send(f"❌ Opções: {', '.join(mapping.keys())}")
                return
            await setconfig_cmd(ctx, mapping[option], value)

        @self.bot.command(name='setbetting')
        @commands.has_permissions(administrator=True)
        async def setbetting_cmd(ctx, option: str, value: str):
            """Configura APOSTADO: min_bet, max_bet, win_multiplier, tax_percent"""
            mapping = {
                'min_bet': 'betting.min_bet',
                'max_bet': 'betting.max_bet',
                'win_multiplier': 'betting.win_multiplier',
                'tax': 'betting.tax_percent'
            }
            if option not in mapping:
                await ctx.send(f"❌ Opções: {', '.join(mapping.keys())}")
                return
            await setconfig_cmd(ctx, mapping[option], value)

        @self.bot.command(name='setprizes')
        @commands.has_permissions(administrator=True)
        async def setprizes_cmd(ctx, position: str, amount: int):
            """Configura prêmios por top: 1, 2, 3, 4_10"""
            if position not in ['1', '2', '3', '4_10']:
                await ctx.send("❌ Posições: 1, 2, 3, 4_10")
                return
            await setconfig_cmd(ctx, f'top_prizes.prizes.{position}', str(amount))

        @self.bot.command(name='setcurrency')
        @commands.has_permissions(administrator=True)
        async def setcurrency_cmd(ctx, option: str, *, value: str):
            """Configura moeda: name, symbol, daily_bonus"""
            mapping = {'name': 'currency.name', 'symbol': 'currency.symbol', 'bonus': 'currency.daily_bonus'}
            if option not in mapping:
                await ctx.send(f"❌ Opções: {', '.join(mapping.keys())}")
                return
            await setconfig_cmd(ctx, mapping[option], value)

        # ============================================================
        # COMANDOS DE PRÊMIOS
        # ============================================================

        @self.bot.command(name='distributetop')
        @commands.has_permissions(administrator=True)
        async def distributetop_cmd(ctx, match_type: str = '1v1'):
            """Distribui prêmios para o top 10 (adm define valores)"""
            if match_type not in self.config.MATCH_TYPES:
                await ctx.send(f"❌ Tipos: {', '.join(self.config.MATCH_TYPES)}")
                return
            
            if not can_distribute_prizes(str(ctx.guild.id)):
                await ctx.send("⏳ Ainda não pode distribuir prêmios! Aguarde o intervalo.")
                return
            
            result = distribute_top_prizes(str(ctx.guild.id), match_type)
            
            if not result['success']:
                await ctx.send(f"❌ {result['message']}")
                return
            
            embed = discord.Embed(
                title="🏅 PRÊMIOS DISTRIBUÍDOS!",
                description=f"**{result['count']} jogadores premiados no {match_type}**",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            for pos, data in result['distributed'].items():
                try:
                    user = await self.bot.fetch_user(int(data['user_id']))
                    embed.add_field(
                        name=f"#{pos} {user.display_name}",
                        value=f"💰 {data['amount']} moedas",
                        inline=False
                    )
                except:
                    pass
            
            await ctx.send(embed=embed)

        @self.bot.command(name='topinfo')
        async def topinfo_cmd(ctx):
            """Mostra informações sobre prêmios"""
            settings = get_guild_settings(str(ctx.guild.id))
            prizes = settings.get('top_prizes', {})
            
            embed = discord.Embed(
                title="🏅 INFORMAÇÕES DOS PRÊMIOS",
                color=discord.Color.gold()
            )
            
            embed.add_field(
                name="📋 Prêmios",
                value=f"**1º:** {prizes.get('prizes', {}).get('1', 10000)}\n**2º:** {prizes.get('prizes', {}).get('2', 5000)}\n**3º:** {prizes.get('prizes', {}).get('3', 2500)}\n**4º-10º:** {prizes.get('prizes', {}).get('4_10', 1000)}",
                inline=False
            )
            
            last_dist = prizes.get('last_distribution')
            if last_dist:
                next_dist = last_dist + timedelta(days=prizes.get('interval_days', 7))
                embed.add_field(
                    name="⏳ Próxima Distribuição",
                    value=f"<t:{int(next_dist.timestamp())}:R>",
                    inline=False
                )
            else:
                embed.add_field(name="⏳ Próxima Distribuição", value="Disponível agora!", inline=False)
            
            await ctx.send(embed=embed)

        # ============================================================
        # COMANDOS DE ECONOMIA (ADMIN)
        # ============================================================

        @self.bot.command(name='ecogive')
        @commands.has_permissions(administrator=True)
        async def ecogive_cmd(ctx, user: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            if amount <= 0:
                await ctx.send("❌ Valor positivo!")
                return
            add_player_balance(ctx.guild.id, user.id, amount, reason)
            embed = discord.Embed(title="✅ Moedas Adicionadas", description=f"{amount} para {user.mention}", color=0x00ff00)
            await ctx.send(embed=embed)

        @self.bot.command(name='ecoremove')
        @commands.has_permissions(administrator=True)
        async def ecoremove_cmd(ctx, user: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            if amount <= 0:
                await ctx.send("❌ Valor positivo!")
                return
            current = get_player_balance(ctx.guild.id, user.id)
            if current < amount:
                await ctx.send(f"❌ {user.mention} tem apenas {current} moedas!")
                return
            remove_player_balance(ctx.guild.id, user.id, amount, reason)
            embed = discord.Embed(title="✅ Moedas Removidas", description=f"{amount} de {user.mention}", color=0xffaa00)
            await ctx.send(embed=embed)

        @self.bot.command(name='ecoset')
        @commands.has_permissions(administrator=True)
        async def ecoset_cmd(ctx, user: discord.Member, amount: int, *, reason: str = "Ajuste admin"):
            if amount < 0:
                await ctx.send("❌ Valor deve ser positivo!")
                return
            current = get_player_balance(ctx.guild.id, user.id)
            diff = amount - current
            if diff > 0:
                add_player_balance(ctx.guild.id, user.id, diff, reason)
            elif diff < 0:
                remove_player_balance(ctx.guild.id, user.id, -diff, reason)
            embed = discord.Embed(title="✅ Saldo Definido", description=f"{user.mention} agora tem {amount} moedas", color=0x00ff00)
            await ctx.send(embed=embed)

        print("✅ Comandos registrados!")
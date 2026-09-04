# ============================================================
# MATCH_SYSTEM.PY - RANKED E APOSTADO (100% CUSTOMIZÁVEL)
# ============================================================

import discord
from discord.ui import Button, View, Select
from typing import Dict, List, Optional, Tuple
import asyncio
from datetime import datetime
import random

from database import (
    get_guild_settings,
    update_guild_settings,
    get_player_balance,
    add_player_balance,
    remove_player_balance,
    create_match,
    get_match,
    update_match,
    get_player_stats,
    update_player_stats,
    get_rankings,
    create_ticket,
    get_ticket,
    close_ticket,
    distribute_top_prizes,
    can_distribute_prizes
)

class MatchSystem:
    """Sistema de partidas com RANKED e APOSTADO"""
    
    def __init__(self, db, config, bot):
        self.db = db
        self.config = config
        self.bot = bot
        self.active_lobbies = {}
        
        self.match_types = {
            '1v1': {'max_players': 2, 'teams': False},
            '2v2': {'max_players': 4, 'teams': True},
            '3v3': {'max_players': 6, 'teams': True}
        }

    async def create_lobby(self, guild_id: str, channel_id: str, 
                           author_id: str, match_type: str, map_name: str,
                           is_betting: bool = False, bet_amount: int = 0) -> Dict:
        """Cria lobby (RANKED ou APOSTADO)"""
        settings = get_guild_settings(guild_id)
        
        # Verificar permissões
        if not await self._check_permissions(guild_id, author_id, settings, is_betting):
            return {'error': '❌ Você não tem permissão para criar partidas!'}
        
        # Verificar limite (apenas para RANKED)
        if not is_betting:
            max_matches = settings.get('ranked', {}).get('max_matches_per_user', 3)
            if max_matches > 0:
                active = await self._count_user_matches(guild_id, author_id, is_betting)
                if active >= max_matches:
                    return {'error': f'❌ Você já está em {active} partidas RANKED ativas!'}
        
        # Verificar aposta (apenas BETTING)
        if is_betting:
            betting_config = settings.get('betting', {})
            if not betting_config.get('enabled', True):
                return {'error': '❌ Apostas estão desativadas!'}
            
            min_bet = betting_config.get('min_bet', 100)
            max_bet = betting_config.get('max_bet', 10000)
            
            if bet_amount < min_bet:
                return {'error': f'❌ Aposta mínima: {min_bet} moedas'}
            if bet_amount > max_bet:
                return {'error': f'❌ Aposta máxima: {max_bet} moedas'}
            
            balance = get_player_balance(int(guild_id), int(author_id))
            if balance < bet_amount:
                return {'error': f'❌ Saldo insuficiente! Você tem {balance} moedas'}
        
        # Verificar taxa de entrada (apenas RANKED)
        if not is_betting:
            entry_fee = settings.get('ranked', {}).get('entry_fee', 0)
            if entry_fee > 0:
                balance = get_player_balance(int(guild_id), int(author_id))
                if balance < entry_fee:
                    return {'error': f'❌ Taxa de entrada: {entry_fee} moedas'}
        
        # Criar partida
        match_data = {
            'guild_id': guild_id,
            'channel_id': channel_id,
            'creator_id': author_id,
            'match_type': match_type,
            'map': map_name,
            'is_betting': is_betting,
            'bet_amount': bet_amount,
            'entry_fee': settings.get('ranked', {}).get('entry_fee', 0) if not is_betting else 0,
            'status': 'waiting',
            'players': [],
            'teams': {}
        }
        
        match_id = create_match(match_data, is_betting)
        
        # Cobrar taxa/aposta
        if is_betting:
            remove_player_balance(
                int(guild_id),
                int(author_id),
                bet_amount,
                f"Aposta na partida {match_id[:6]}"
            )
        else:
            entry_fee = settings.get('ranked', {}).get('entry_fee', 0)
            if entry_fee > 0:
                remove_player_balance(
                    int(guild_id),
                    int(author_id),
                    entry_fee,
                    f"Taxa de entrada RANKED {match_id[:6]}"
                )
        
        # Inicializar lobby
        self.active_lobbies[match_id] = {
            'id': match_id,
            'players': [author_id],
            'teams': {},
            'status': 'waiting',
            'is_betting': is_betting,
            'bet_amount': bet_amount,
            'created_at': datetime.utcnow()
        }
        
        return {'match_id': match_id, 'success': True}

    async def join_lobby(self, match_id: str, user_id: str, 
                         team: Optional[str] = None) -> Dict:
        """Entra no lobby"""
        lobby = self.active_lobbies.get(match_id)
        if not lobby:
            return {'error': '❌ Partida não encontrada!'}
        
        if lobby['status'] != 'waiting':
            return {'error': '❌ Partida já está em andamento!'}
        
        if user_id in lobby['players']:
            return {'error': '❌ Você já está na partida!'}
        
        match_data = get_match(match_id, lobby['is_betting'])
        if not match_data:
            return {'error': '❌ Partida não encontrada!'}
        
        settings = get_guild_settings(match_data['guild_id'])
        max_players = self.match_types[match_data['match_type']]['max_players']
        
        if len(lobby['players']) >= max_players:
            return {'error': '❌ Partida cheia!'}
        
        # Verificar time
        if match_data['match_type'] != '1v1':
            if not team:
                return {'error': '❌ Escolha um time! Use: team1 ou team2'}
            team_count = sum(1 for t in lobby['teams'].values() if t == team)
            if team_count >= max_players // 2:
                return {'error': f'❌ Time {team} está cheio!'}
        
        # Verificar saldo (BETTING)
        if lobby['is_betting']:
            bet_amount = lobby.get('bet_amount', 0)
            if bet_amount > 0:
                balance = get_player_balance(int(match_data['guild_id']), int(user_id))
                if balance < bet_amount:
                    return {'error': f'❌ Saldo insuficiente para aposta de {bet_amount} moedas!'}
                remove_player_balance(
                    int(match_data['guild_id']),
                    int(user_id),
                    bet_amount,
                    f"Aposta na partida {match_id[:6]}"
                )
        
        # Verificar taxa (RANKED)
        if not lobby['is_betting']:
            entry_fee = settings.get('ranked', {}).get('entry_fee', 0)
            if entry_fee > 0:
                balance = get_player_balance(int(match_data['guild_id']), int(user_id))
                if balance < entry_fee:
                    return {'error': f'❌ Saldo insuficiente para taxa de {entry_fee} moedas!'}
                remove_player_balance(
                    int(match_data['guild_id']),
                    int(user_id),
                    entry_fee,
                    f"Taxa de entrada RANKED {match_id[:6]}"
                )
        
        # Adicionar jogador
        lobby['players'].append(user_id)
        if team:
            lobby['teams'][user_id] = team
        
        update_match(match_id, {
            'players': lobby['players'],
            'teams': lobby['teams']
        }, lobby['is_betting'])
        
        if len(lobby['players']) >= max_players:
            await self._start_match(match_id)
        
        return {'success': True, 'player_count': len(lobby['players'])}

    async def _start_match(self, match_id: str):
        """Inicia partida e cria ticket"""
        lobby = self.active_lobbies.get(match_id)
        if not lobby:
            return
        
        match_data = get_match(match_id, lobby['is_betting'])
        if not match_data:
            return
        
        settings = get_guild_settings(match_data['guild_id'])
        
        if settings['match_settings']['auto_ticket']:
            ticket_id = await self._create_ticket(match_data, lobby, settings)
            update_match(match_id, {'ticket_id': ticket_id}, lobby['is_betting'])
        
        lobby['status'] = 'started'
        await self._notify_players(match_data, lobby, settings)

    async def _create_ticket(self, match_data: Dict, lobby: Dict, 
                             settings: Dict) -> str:
        """Cria ticket"""
        guild = self.bot.get_guild(int(match_data['guild_id']))
        if not guild:
            return None
        
        categoria = "APOSTADO" if lobby['is_betting'] else "RANKED"
        
        category = None
        if settings['match_settings']['ticket_category']:
            category = guild.get_channel(int(settings['match_settings']['ticket_category']))
        
        overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False)}
        
        for player_id in lobby['players']:
            member = guild.get_member(int(player_id))
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, view_channel=True
                )
        
        for role_id in settings['permissions']['mediator_roles']:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, view_channel=True
                )
        
        channel_name = settings['match_settings']['ticket_name_template'].format(
            tipo=categoria,
            match_id=match_data['_id'][:6]
        )
        
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites
        )
        
        ticket_data = {
            'guild_id': match_data['guild_id'],
            'channel_id': str(channel.id),
            'match_id': match_data['_id'],
            'players': lobby['players'],
            'is_betting': lobby['is_betting'],
            'mediators': [],
            'status': 'active'
        }
        
        ticket_id = create_ticket(ticket_data)
        await self._send_ticket_embed(channel, match_data, lobby, settings)
        
        return ticket_id

    async def _send_ticket_embed(self, channel: discord.TextChannel, 
                                 match_data: Dict, lobby: Dict, 
                                 settings: Dict):
        """Embed do ticket"""
        categoria = "💰 APOSTADO" if lobby['is_betting'] else "🏆 RANKED"
        bet_amount = lobby.get('bet_amount', 0)
        
        embed = discord.Embed(
            title=f"🎯 {categoria}",
            description=f"**Tipo:** {match_data['match_type']}\n"
                       f"**Mapa:** {match_data['map']}",
            color=settings['customization']['embed_color'],
            timestamp=datetime.utcnow()
        )
        
        if bet_amount > 0:
            embed.add_field(name="💰 Aposta", value=f"{bet_amount} moedas", inline=False)
        
        entry_fee = settings.get('ranked', {}).get('entry_fee', 0)
        if not lobby['is_betting'] and entry_fee > 0:
            embed.add_field(name="🎫 Taxa", value=f"{entry_fee} moedas", inline=False)
        
        if match_data['match_type'] == '1v1':
            players_text = "\n".join([f"👤 <@{p}>" for p in lobby['players']])
            embed.add_field(name="👥 Jogadores", value=players_text, inline=False)
        else:
            team1 = [p for p, t in lobby['teams'].items() if t == 'team1']
            team2 = [p for p, t in lobby['teams'].items() if t == 'team2']
            embed.add_field(name="🔴 Time 1", value="\n".join([f"👤 <@{p}>" for p in team1]) or "Vazio", inline=True)
            embed.add_field(name="🔵 Time 2", value="\n".join([f"👤 <@{p}>" for p in team2]) or "Vazio", inline=True)
        
        embed.set_footer(text=settings['customization']['embed_footer'])
        
        view = MediatorView(self.db, match_data['_id'], match_data['match_type'], 
                           lobby['is_betting'], self.config, self.bot)
        await channel.send(embed=embed, view=view)

    async def _notify_players(self, match_data: Dict, lobby: Dict, settings: Dict):
        if not settings['customization']['dm_notifications']:
            return
        for player_id in lobby['players']:
            try:
                user = await self.bot.fetch_user(int(player_id))
                categoria = "APOSTADO" if lobby['is_betting'] else "RANKED"
                await user.send(
                    f"🎯 Partida {categoria} começou!\n"
                    f"**Tipo:** {match_data['match_type']}\n"
                    f"**Mapa:** {match_data['map']}"
                )
            except:
                pass

    async def _check_permissions(self, guild_id: str, user_id: str, 
                                 settings: Dict, is_betting: bool) -> bool:
        if is_betting:
            allowed = settings.get('betting', {}).get('allowed_roles', [])
        else:
            allowed = settings.get('ranked', {}).get('allowed_roles', [])
        
        if not allowed:
            return True
        
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return False
        
        member = guild.get_member(int(user_id))
        if not member:
            return False
        
        for role in member.roles:
            if role.id in allowed:
                return True
        
        return False

    async def _count_user_matches(self, guild_id: str, user_id: str, is_betting: bool) -> int:
        count = 0
        for lobby in self.active_lobbies.values():
            if lobby['is_betting'] == is_betting:
                if user_id in lobby['players'] and lobby['status'] == 'waiting':
                    count += 1
        return count

    async def cancel_match(self, match_id: str) -> bool:
        lobby = self.active_lobbies.get(match_id)
        if not lobby:
            return False
        
        # Devolver apostas/taxas
        bet_amount = lobby.get('bet_amount', 0)
        if bet_amount > 0:
            for player_id in lobby['players']:
                add_player_balance(
                    int(lobby.get('guild_id', 0)),
                    int(player_id),
                    bet_amount,
                    f"Reembolso da partida {match_id[:6]}"
                )
        
        lobby['status'] = 'cancelled'
        update_match(match_id, {'status': 'cancelled'}, lobby['is_betting'])
        
        for player_id in lobby['players']:
            try:
                user = await self.bot.fetch_user(int(player_id))
                await user.send(f"❌ Partida cancelada! Reembolso realizado.")
            except:
                pass
        
        del self.active_lobbies[match_id]
        return True

class MediatorView(View):
    def __init__(self, db, match_id: str, match_type: str, is_betting: bool, config, bot):
        super().__init__(timeout=None)
        self.db = db
        self.match_id = match_id
        self.match_type = match_type
        self.is_betting = is_betting
        self.config = config
        self.bot = bot

    @discord.ui.button(label="🔴 Time 1 Venceu", style=discord.ButtonStyle.success)
    async def team1_win(self, interaction: discord.Interaction, button: Button):
        await self._declare_winner(interaction, 'team1')

    @discord.ui.button(label="🔵 Time 2 Venceu", style=discord.ButtonStyle.success)
    async def team2_win(self, interaction: discord.Interaction, button: Button):
        await self._declare_winner(interaction, 'team2')

    @discord.ui.button(label="⚖️ Empate", style=discord.ButtonStyle.secondary)
    async def draw(self, interaction: discord.Interaction, button: Button):
        await self._declare_winner(interaction, None)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await self._cancel_match(interaction)

    async def _declare_winner(self, interaction: discord.Interaction, winner: Optional[str]):
        from database import get_guild_settings, get_match, add_player_balance, update_player_stats
        
        settings = get_guild_settings(str(interaction.guild.id))
        mediator_roles = settings['permissions']['mediator_roles']
        
        is_mediator = False
        for role in interaction.user.roles:
            if role.id in mediator_roles:
                is_mediator = True
                break
        
        if not is_mediator:
            await interaction.response.send_message("❌ Você não é mediador!", ephemeral=True)
            return
        
        match = get_match(self.match_id, self.is_betting)
        if not match:
            await interaction.response.send_message("❌ Partida não encontrada!", ephemeral=True)
            return
        
        # Determinar vencedores
        winning_players = []
        losing_players = []
        
        if self.match_type == '1v1':
            for player_id in match['players']:
                if player_id == winner:
                    winning_players.append(player_id)
                else:
                    losing_players.append(player_id)
        else:
            for player_id, team in match['teams'].items():
                if team == winner:
                    winning_players.append(player_id)
                else:
                    losing_players.append(player_id)
        
        # ===== PROCESSAR APOSTA (BETTING) =====
        if self.is_betting:
            bet_amount = match.get('bet_amount', 0)
            if bet_amount > 0 and winner:
                betting_config = settings.get('betting', {})
                multiplier = betting_config.get('win_multiplier', 2.0)
                tax = betting_config.get('tax_percent', 5.0)
                
                total_pot = bet_amount * len(match['players'])
                prize = int(total_pot * multiplier)
                
                # Aplicar taxa
                tax_amount = int(prize * (tax / 100))
                prize -= tax_amount
                
                prize_per_player = prize // len(winning_players) if winning_players else 0
                
                for player_id in winning_players:
                    add_player_balance(
                        int(match['guild_id']),
                        int(player_id),
                        prize_per_player,
                        f"🏆 Prêmio da aposta {self.match_id[:6]}"
                    )
        
        # ===== PROCESSAR RANKED =====
        if not self.is_betting:
            for player_id in winning_players:
                # Bônus de vitória RANKED
                win_bonus = settings.get('ranked', {}).get('win_bonus', 50)
                add_player_balance(
                    int(match['guild_id']),
                    int(player_id),
                    win_bonus,
                    f"🏆 Bônus vitória RANKED {self.match_id[:6]}"
                )
                update_player_stats(match['guild_id'], player_id, self.match_type, 'win')
            
            for player_id in losing_players:
                loss_penalty = settings.get('ranked', {}).get('loss_penalty', 10)
                remove_player_balance(
                    int(match['guild_id']),
                    int(player_id),
                    loss_penalty,
                    f"💔 Penalidade derrota RANKED {self.match_id[:6]}"
                )
                update_player_stats(match['guild_id'], player_id, self.match_type, 'loss')
        
        # Finalizar partida
        update_match(self.match_id, {
            'status': 'finished',
            'winner': winner,
            'finished_at': datetime.utcnow()
        }, self.is_betting)
        
        # Atualizar embed
        embed = interaction.message.embeds[0]
        embed.color = 0x00ff00 if winner else 0xffaa00
        embed.add_field(
            name="🏆 Resultado",
            value=f"**Vencedor:** {winner or 'Empate'}\n**Declarado por:** {interaction.user.mention}",
            inline=False
        )
        
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Notificar
        for player_id in match['players']:
            try:
                user = await self.bot.fetch_user(int(player_id))
                categoria = "APOSTADO" if self.is_betting else "RANKED"
                await user.send(f"🏆 Partida {categoria} finalizada! Vencedor: {winner or 'Empate'}")
            except:
                pass

    async def _cancel_match(self, interaction: discord.Interaction):
        settings = get_guild_settings(str(interaction.guild.id))
        mediator_roles = settings['permissions']['mediator_roles']
        
        is_mediator = False
        for role in interaction.user.roles:
            if role.id in mediator_roles:
                is_mediator = True
                break
        
        if not is_mediator:
            await interaction.response.send_message("❌ Você não é mediador!", ephemeral=True)
            return
        
        match_system = self.bot.match_system
        await match_system.cancel_match(self.match_id)
        
        embed = interaction.message.embeds[0]
        embed.color = 0xff0000
        embed.add_field(name="❌ Cancelada", value=f"Por: {interaction.user.mention}", inline=False)
        
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
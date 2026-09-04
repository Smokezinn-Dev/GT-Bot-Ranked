# ============================================================
# MATCH_SYSTEM.PY - SISTEMA DE PARTIDAS COM FILAS
# CORRIGIDO - SEM LOOP NO __INIT__
# ============================================================

import discord
from discord.ui import Button, View
import asyncio
from datetime import datetime, timedelta
import random
from typing import Dict, List, Optional

from database import (
    get_guild_settings, update_guild_settings,
    get_player_balance, add_player_balance, remove_player_balance,
    get_match, update_match, create_match,
    get_player_stats, update_player_stats,
    create_ticket, get_ticket, close_ticket,
    get_rankings, get_mediator_roles, is_mediator
)

class MatchSystem:
    """Sistema de partidas RANKED/APOSTADO com FILAS"""
    
    def __init__(self, db, config, bot):
        self.db = db
        self.config = config
        self.bot = bot
        self.active_lobbies = {}
        self._cleanup_task = None
        self._matchmaking_task = None
        
        self.queues = {
            "1v1": {"players": [], "min": 2, "max": 2},
            "2v2": {"players": [], "min": 4, "max": 4},
            "3v3": {"players": [], "min": 6, "max": 6}
        }
        
        self.match_types = {
            "1v1": {"max_players": 2, "teams": False, "min_players": 2},
            "2v2": {"max_players": 4, "teams": True, "min_players": 4},
            "3v3": {"max_players": 6, "teams": True, "min_players": 6}
        }

    def start_tasks(self):
        """Inicia as tasks de background (chamado no on_ready)"""
        if self.bot:
            if not self._cleanup_task:
                self._cleanup_task = self.bot.loop.create_task(self._cleanup_loop())
            if not self._matchmaking_task:
                self._matchmaking_task = self.bot.loop.create_task(self._matchmaking_loop())
            print("✅ Tasks de matchmaking e limpeza iniciadas!")

    async def _matchmaking_loop(self):
        """Loop principal de matchmaking - verifica filas automaticamente"""
        while True:
            try:
                await asyncio.sleep(5)  # Verifica a cada 5 segundos
                
                for match_type, queue_data in self.queues.items():
                    players = queue_data["players"]
                    min_players = self.match_types[match_type]["min_players"]
                    
                    if len(players) >= min_players:
                        selected = players[:min_players]
                        for player in selected:
                            players.remove(player)
                        
                        guild_id = None
                        if self.bot and self.bot.guilds:
                            guild_id = str(self.bot.guilds[0].id)
                        
                        if guild_id:
                            await self._create_match_from_queue(
                                match_type, 
                                selected,
                                guild_id
                            )
                            
            except Exception as e:
                print(f"⚠️ Erro no matchmaking: {e}")

    async def _create_match_from_queue(self, match_type: str, players: List[str], guild_id: str):
        """Cria partida a partir da fila"""
        if not guild_id:
            return
        
        settings = get_guild_settings(guild_id)
        
        teams = {}
        team_names = {}
        
        if match_type == "1v1":
            teams = {players[0]: "team1", players[1]: "team2"}
            team_names = {"team1": "Jogador 1", "team2": "Jogador 2"}
        else:
            half = len(players) // 2
            for i, player in enumerate(players[:half]):
                teams[player] = "team1"
            for i, player in enumerate(players[half:]):
                teams[player] = "team2"
            team_names = {"team1": "Time 1", "team2": "Time 2"}
        
        maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto", "Vulcão"])
        map_name = random.choice(maps)
        
        # Verificar se tem canal para anunciar
        channel_id = None
        if self.bot and self.bot.guilds:
            guild = self.bot.get_guild(int(guild_id))
            if guild:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        channel_id = str(ch.id)
                        break
        
        if not channel_id:
            channel_id = "0"
        
        match_data = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "creator_id": players[0],
            "match_type": match_type,
            "map": map_name,
            "is_betting": False,
            "bet_amount": 0,
            "team1_name": team_names.get("team1", "Time 1"),
            "team2_name": team_names.get("team2", "Time 2"),
            "players": players,
            "teams": teams,
            "team_names": team_names
        }
        
        match_id = create_match(match_data, False)
        
        self.active_lobbies[match_id] = {
            "id": match_id,
            "players": players,
            "teams": teams,
            "status": "waiting",
            "is_betting": False,
            "bet_amount": 0,
            "created_at": datetime.utcnow(),
            "guild_id": guild_id,
            "from_queue": True
        }
        
        await self._announce_match_from_queue(match_id, match_data, players)
        await self._start_match(match_id)

    async def _announce_match_from_queue(self, match_id: str, match_data: Dict, players: List[str]):
        """Anuncia partida criada pela fila"""
        guild = self.bot.get_guild(int(match_data["guild_id"]))
        if not guild:
            return
        
        channel = self.bot.get_channel(int(match_data["channel_id"]))
        if not channel:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        
        if not channel:
            return
        
        categoria = "🏆 RANKED"
        max_players = self.match_types[match_data["match_type"]]["max_players"]
        
        embed = discord.Embed(
            title=f"🎯 PARTIDA ENCONTRADA!",
            description=f"**{categoria} - {match_data['match_type']}**\n**Mapa:** {match_data['map']}",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        if match_data["match_type"] == "1v1":
            embed.add_field(
                name="👥 Jogadores",
                value=f"🔴 <@{players[0]}> vs 🔵 <@{players[1]}>",
                inline=False
            )
        else:
            half = len(players) // 2
            team1 = players[:half]
            team2 = players[half:]
            embed.add_field(
                name=f"🔴 {match_data.get('team1_name', 'Time 1')}",
                value="\n".join([f"👤 <@{p}>" for p in team1]),
                inline=True
            )
            embed.add_field(
                name=f"🔵 {match_data.get('team2_name', 'Time 2')}",
                value="\n".join([f"👤 <@{p}>" for p in team2]),
                inline=True
            )
        
        embed.add_field(
            name="📌 Próximos passos",
            value=f"Um ticket será aberto para a partida!\nAguarde o mediador.",
            inline=False
        )
        
        embed.set_footer(text=f"ID: {match_id[:6]}")
        
        await channel.send(embed=embed)
        
        for player_id in players:
            try:
                user = await self.bot.fetch_user(int(player_id))
                await user.send(
                    f"🎯 Partida RANKED encontrada!\n"
                    f"**Tipo:** {match_data['match_type']}\n"
                    f"**Mapa:** {match_data['map']}\n"
                    f"**ID:** {match_id[:6]}"
                )
            except:
                pass

    async def add_to_queue(self, guild_id: str, user_id: str, match_type: str) -> Dict:
        """Adiciona jogador à fila"""
        if match_type not in self.queues:
            return {"error": f"❌ Tipos: 1v1, 2v2, 3v3"}
        
        for q_type, q_data in self.queues.items():
            if user_id in q_data["players"]:
                return {"error": f"❌ Você já está na fila de {q_type}!"}
        
        for lobby in self.active_lobbies.values():
            if user_id in lobby["players"] and lobby["status"] == "waiting":
                return {"error": "❌ Você já está em uma partida!"}
        
        self.queues[match_type]["players"].append(user_id)
        
        return {"success": True, "match_type": match_type, "position": len(self.queues[match_type]["players"])}

    async def remove_from_queue(self, guild_id: str, user_id: str) -> Dict:
        """Remove jogador de todas as filas"""
        removed = False
        for q_type, q_data in self.queues.items():
            if user_id in q_data["players"]:
                q_data["players"].remove(user_id)
                removed = True
        
        if removed:
            return {"success": True}
        return {"error": "❌ Você não está em nenhuma fila!"}

    def get_queue_status(self) -> Dict:
        """Retorna status de todas as filas"""
        status = {}
        for match_type, q_data in self.queues.items():
            players = q_data["players"]
            min_players = self.match_types[match_type]["min_players"]
            max_players = self.match_types[match_type]["max_players"]
            
            status[match_type] = {
                "count": len(players),
                "min": min_players,
                "max": max_players,
                "ready": len(players) >= min_players,
                "players": players[:10]
            }
        
        return status

    async def _cleanup_loop(self):
        """Limpa lobbies expirados"""
        while True:
            try:
                await asyncio.sleep(300)
                now = datetime.utcnow()
                to_remove = []
                
                for match_id, lobby in self.active_lobbies.items():
                    if lobby.get('status') == 'waiting':
                        created = lobby.get('created_at', now)
                        if (now - created).seconds > 600:
                            to_remove.append(match_id)
                
                for match_id in to_remove:
                    await self.cancel_match(match_id)
            except Exception as e:
                print(f"⚠️ Erro na limpeza: {e}")

    async def create_lobby(self, guild_id: str, channel_id: str, author_id: str,
                          match_type: str, map_name: str, is_betting: bool = False,
                          bet_amount: int = 0, team1_name: str = "Time 1", 
                          team2_name: str = "Time 2") -> Dict:
        """Cria lobby de partida (manual)"""
        settings = get_guild_settings(guild_id)
        
        if match_type not in self.match_types:
            return {"error": f"❌ Tipos: {', '.join(self.match_types.keys())}"}
        
        if is_betting:
            betting_config = settings.get("betting", {})
            if not betting_config.get("enabled", True):
                return {"error": "❌ Apostas desativadas!"}
            
            min_bet = betting_config.get("min_bet", 100)
            max_bet = betting_config.get("max_bet", 10000)
            
            if bet_amount < min_bet:
                return {"error": f"❌ Aposta mínima: {min_bet}"}
            if bet_amount > max_bet:
                return {"error": f"❌ Aposta máxima: {max_bet}"}
            
            balance = get_player_balance(int(guild_id), int(author_id))
            if balance < bet_amount:
                return {"error": f"❌ Saldo insuficiente! Você tem {balance}"}
        else:
            entry_fee = settings.get("ranked", {}).get("entry_fee", 0)
            if entry_fee > 0:
                balance = get_player_balance(int(guild_id), int(author_id))
                if balance < entry_fee:
                    return {"error": f"❌ Taxa de entrada: {entry_fee}"}
        
        match_data = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "creator_id": author_id,
            "match_type": match_type,
            "map": map_name or "Arena",
            "is_betting": is_betting,
            "bet_amount": bet_amount,
            "team1_name": team1_name,
            "team2_name": team2_name,
            "players": [author_id],
            "teams": {},
            "team_names": {}
        }
        
        match_id = create_match(match_data, is_betting)
        
        if is_betting:
            remove_player_balance(int(guild_id), int(author_id), bet_amount, f"Aposta {match_id[:6]}")
        else:
            entry_fee = settings.get("ranked", {}).get("entry_fee", 0)
            if entry_fee > 0:
                remove_player_balance(int(guild_id), int(author_id), entry_fee, f"Taxa RANKED {match_id[:6]}")
        
        self.active_lobbies[match_id] = {
            "id": match_id,
            "players": [author_id],
            "teams": {},
            "status": "waiting",
            "is_betting": is_betting,
            "bet_amount": bet_amount,
            "created_at": datetime.utcnow(),
            "guild_id": guild_id
        }
        
        await self._announce_match(channel_id, match_id, match_data)
        
        return {"match_id": match_id, "success": True}

    async def _announce_match(self, channel_id: str, match_id: str, match_data: Dict):
        """Anuncia partida criada"""
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return
        
        categoria = "💰 APOSTADO" if match_data["is_betting"] else "🏆 RANKED"
        max_players = self.match_types[match_data["match_type"]]["max_players"]
        
        embed = discord.Embed(
            title=f"🎮 {categoria} - {match_data['match_type']}",
            description=f"**Mapa:** {match_data['map']}\n**Criador:** <@{match_data['creator_id']}>",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        if match_data.get("bet_amount", 0) > 0:
            embed.add_field(name="💰 Aposta", value=f"{match_data['bet_amount']} moedas", inline=True)
        
        embed.add_field(name="👥 Jogadores", value=f"1/{max_players}", inline=True)
        embed.add_field(
            name="📌 Como entrar",
            value=f"Use `%join {match_id[:6]}` para entrar!\n"
                  f"**OU** use `%queue {match_data['match_type']}` para entrar na fila!",
            inline=False
        )
        embed.set_footer(text=f"ID: {match_id[:6]}")
        
        await channel.send(embed=embed)

    async def join_lobby(self, match_id: str, user_id: str, team: Optional[str] = None) -> Dict:
        """Entra no lobby manual"""
        lobby = None
        full_match_id = None
        
        for mid, data in self.active_lobbies.items():
            if mid.startswith(match_id) or mid == match_id:
                lobby = data
                full_match_id = mid
                break
        
        if not lobby:
            return {"error": "❌ Partida não encontrada!"}
        
        if lobby["status"] != "waiting":
            return {"error": "❌ Partida já em andamento!"}
        
        if user_id in lobby["players"]:
            return {"error": "❌ Você já está na partida!"}
        
        match_data = get_match(full_match_id, lobby["is_betting"])
        if not match_data:
            return {"error": "❌ Partida não encontrada!"}
        
        settings = get_guild_settings(match_data["guild_id"])
        max_players = self.match_types[match_data["match_type"]]["max_players"]
        
        if len(lobby["players"]) >= max_players:
            return {"error": "❌ Partida cheia!"}
        
        if match_data["match_type"] != "1v1":
            if not team or team not in ["team1", "team2"]:
                return {"error": "❌ Escolha um time: team1 ou team2"}
            
            team_count = sum(1 for t in lobby["teams"].values() if t == team)
            if team_count >= max_players // 2:
                return {"error": f"❌ Time {team} está cheio!"}
        
        if lobby["is_betting"]:
            bet_amount = lobby.get("bet_amount", 0)
            if bet_amount > 0:
                balance = get_player_balance(int(match_data["guild_id"]), int(user_id))
                if balance < bet_amount:
                    return {"error": f"❌ Saldo insuficiente para aposta de {bet_amount}!"}
                remove_player_balance(int(match_data["guild_id"]), int(user_id), bet_amount, f"Aposta {full_match_id[:6]}")
        
        if not lobby["is_betting"]:
            entry_fee = settings.get("ranked", {}).get("entry_fee", 0)
            if entry_fee > 0:
                balance = get_player_balance(int(match_data["guild_id"]), int(user_id))
                if balance < entry_fee:
                    return {"error": f"❌ Saldo insuficiente para taxa de {entry_fee}!"}
                remove_player_balance(int(match_data["guild_id"]), int(user_id), entry_fee, f"Taxa RANKED {full_match_id[:6]}")
        
        lobby["players"].append(user_id)
        if team:
            lobby["teams"][user_id] = team
        
        update_match(full_match_id, {
            "players": lobby["players"],
            "teams": lobby["teams"]
        }, lobby["is_betting"])
        
        if len(lobby["players"]) >= max_players:
            await self._start_match(full_match_id)
            return {"success": True, "match_started": True}
        
        return {"success": True, "player_count": len(lobby["players"])}

    async def _start_match(self, match_id: str):
        """Inicia partida e abre ticket"""
        lobby = self.active_lobbies.get(match_id)
        if not lobby:
            return
        
        match_data = get_match(match_id, lobby["is_betting"])
        if not match_data:
            return
        
        settings = get_guild_settings(match_data["guild_id"])
        
        if settings.get("match_settings", {}).get("auto_ticket", True):
            ticket_id = await self._create_ticket(match_data, lobby, settings)
            if ticket_id:
                update_match(match_id, {"ticket_id": ticket_id}, lobby["is_betting"])
        
        lobby["status"] = "started"
        
        await self._notify_players(match_data, lobby, settings)

    async def _create_ticket(self, match_data: Dict, lobby: Dict, settings: Dict) -> Optional[str]:
        """Cria ticket (canal privado)"""
        guild = self.bot.get_guild(int(match_data["guild_id"]))
        if not guild:
            return None
        
        categoria = "APOSTADO" if lobby["is_betting"] else "RANKED"
        
        category = None
        ticket_cat = settings.get("match_settings", {}).get("ticket_category")
        if ticket_cat:
            category = guild.get_channel(int(ticket_cat))
        
        overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False)}
        
        for player_id in lobby["players"]:
            member = guild.get_member(int(player_id))
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, view_channel=True
                )
        
        mediator_role_ids = get_mediator_roles(match_data["guild_id"])
        for role_id in mediator_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, view_channel=True
                )
        
        template = settings.get("match_settings", {}).get("ticket_name_template", "🎮-{tipo}-{match_id}")
        channel_name = template.format(tipo=categoria, match_id=match_id[:6])
        
        try:
            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Partida {categoria} - {match_id[:6]}"
            )
        except Exception as e:
            print(f"❌ Erro ao criar ticket: {e}")
            return None
        
        embed = await self._create_ticket_embed(match_data, lobby, settings)
        view = MediatorView(self.db, match_id, match_data["match_type"], lobby["is_betting"], self.config, self.bot)
        await channel.send(embed=embed, view=view)
        
        for role_id in mediator_role_ids:
            role = guild.get_role(role_id)
            if role:
                try:
                    await channel.send(f"🔔 {role.mention} - Partida aguardando mediador!")
                except:
                    pass
        
        ticket_data = {
            "guild_id": match_data["guild_id"],
            "channel_id": str(channel.id),
            "match_id": match_id,
            "players": lobby["players"],
            "is_betting": lobby["is_betting"],
            "mediators": [],
            "status": "active"
        }
        
        return create_ticket(ticket_data)

    async def _create_ticket_embed(self, match_data: Dict, lobby: Dict, settings: Dict) -> discord.Embed:
        """Cria embed do ticket"""
        categoria = "💰 APOSTADO" if lobby["is_betting"] else "🏆 RANKED"
        bet_amount = lobby.get("bet_amount", 0)
        
        embed = discord.Embed(
            title=f"🎯 {categoria} - {match_data['match_type']}",
            description=f"**Mapa:** {match_data['map']}",
            color=settings.get("customization", {}).get("embed_color", 0x00ff00),
            timestamp=datetime.utcnow()
        )
        
        if bet_amount > 0:
            embed.add_field(name="💰 Aposta", value=f"{bet_amount} moedas", inline=False)
        
        entry_fee = settings.get("ranked", {}).get("entry_fee", 0)
        if not lobby["is_betting"] and entry_fee > 0:
            embed.add_field(name="🎫 Taxa", value=f"{entry_fee} moedas", inline=False)
        
        if match_data["match_type"] == "1v1":
            players_text = "\n".join([f"👤 <@{p}>" for p in lobby["players"]])
            embed.add_field(name="👥 Jogadores", value=players_text, inline=False)
        else:
            team1 = [p for p, t in lobby["teams"].items() if t == "team1"]
            team2 = [p for p, t in lobby["teams"].items() if t == "team2"]
            embed.add_field(
                name=f"🔴 {match_data.get('team1_name', 'Time 1')}",
                value="\n".join([f"👤 <@{p}>" for p in team1]) or "Vazio",
                inline=True
            )
            embed.add_field(
                name=f"🔵 {match_data.get('team2_name', 'Time 2')}",
                value="\n".join([f"👤 <@{p}>" for p in team2]) or "Vazio",
                inline=True
            )
        
        footer = settings.get("customization", {}).get("embed_footer", "Rank System v3.0")
        embed.set_footer(text=footer)
        return embed

    async def _notify_players(self, match_data: Dict, lobby: Dict, settings: Dict):
        """Notifica jogadores"""
        if not settings.get("customization", {}).get("dm_notifications", True):
            return
        
        categoria = "APOSTADO" if lobby["is_betting"] else "RANKED"
        
        for player_id in lobby["players"]:
            try:
                user = await self.bot.fetch_user(int(player_id))
                await user.send(
                    f"🎯 Partida {categoria} começou!\n"
                    f"**Tipo:** {match_data['match_type']}\n"
                    f"**Mapa:** {match_data['map']}"
                )
            except:
                pass

    async def cancel_match(self, match_id: str) -> bool:
        """Cancela partida e devolve valores"""
        lobby = self.active_lobbies.get(match_id)
        if not lobby:
            return False
        
        bet_amount = lobby.get("bet_amount", 0)
        guild_id = int(lobby.get("guild_id", 0))
        
        if bet_amount > 0:
            for player_id in lobby["players"]:
                add_player_balance(
                    guild_id,
                    int(player_id),
                    bet_amount,
                    f"Reembolso da partida {match_id[:6]}"
                )
        
        lobby["status"] = "cancelled"
        update_match(match_id, {"status": "cancelled"}, lobby["is_betting"])
        
        for player_id in lobby["players"]:
            try:
                user = await self.bot.fetch_user(int(player_id))
                await user.send(f"❌ Partida cancelada! Reembolso realizado.")
            except:
                pass
        
        del self.active_lobbies[match_id]
        return True

    def get_match_info(self, match_id: str) -> Optional[Dict]:
        """Obtém informações de uma partida"""
        for mid, lobby in self.active_lobbies.items():
            if mid.startswith(match_id):
                return lobby
        return None

    def get_cache_stats(self) -> Dict:
        """Retorna estatísticas"""
        waiting = sum(1 for l in self.active_lobbies.values() if l.get('status') == 'waiting')
        started = sum(1 for l in self.active_lobbies.values() if l.get('status') == 'started')
        
        return {
            "total": len(self.active_lobbies),
            "waiting": waiting,
            "started": started,
            "betting": sum(1 for l in self.active_lobbies.values() if l.get('is_betting', False))
        }


# ============================================================
# MEDIATOR VIEW
# ============================================================

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
        await self._declare_winner(interaction, "team1")

    @discord.ui.button(label="🔵 Time 2 Venceu", style=discord.ButtonStyle.success)
    async def team2_win(self, interaction: discord.Interaction, button: Button):
        await self._declare_winner(interaction, "team2")

    @discord.ui.button(label="⚖️ Empate", style=discord.ButtonStyle.secondary)
    async def draw(self, interaction: discord.Interaction, button: Button):
        await self._declare_winner(interaction, None)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await self._cancel_match(interaction)

    async def _declare_winner(self, interaction: discord.Interaction, winner: Optional[str]):
        from database import get_guild_settings, get_match, add_player_balance, remove_player_balance, update_player_stats
        
        if not is_mediator(interaction.user):
            await interaction.response.send_message("❌ Você não é mediador!", ephemeral=True)
            return
        
        match = get_match(self.match_id, self.is_betting)
        if not match:
            await interaction.response.send_message("❌ Partida não encontrada!", ephemeral=True)
            return
        
        settings = get_guild_settings(match["guild_id"])
        
        winning_players = []
        losing_players = []
        
        if self.match_type == "1v1":
            for player_id in match["players"]:
                if player_id == winner:
                    winning_players.append(player_id)
                else:
                    losing_players.append(player_id)
        else:
            for player_id, team in match["teams"].items():
                if team == winner:
                    winning_players.append(player_id)
                else:
                    losing_players.append(player_id)
        
        if self.is_betting:
            bet_amount = match.get("bet_amount", 0)
            if bet_amount > 0 and winner:
                betting_config = settings.get("betting", {})
                multiplier = betting_config.get("win_multiplier", 2.0)
                tax = betting_config.get("tax_percent", 5.0)
                
                total_pot = bet_amount * len(match["players"])
                prize = int(total_pot * multiplier)
                tax_amount = int(prize * (tax / 100))
                prize -= tax_amount
                
                prize_per_player = prize // len(winning_players) if winning_players else 0
                
                for player_id in winning_players:
                    add_player_balance(
                        int(match["guild_id"]),
                        int(player_id),
                        prize_per_player,
                        f"🏆 Prêmio aposta {self.match_id[:6]}"
                    )
        
        if not self.is_betting:
            for player_id in winning_players:
                win_bonus = settings.get("ranked", {}).get("win_bonus", 50)
                add_player_balance(
                    int(match["guild_id"]),
                    int(player_id),
                    win_bonus,
                    f"🏆 Bônus vitória RANKED {self.match_id[:6]}"
                )
                update_player_stats(match["guild_id"], player_id, self.match_type, "win")
            
            for player_id in losing_players:
                loss_penalty = settings.get("ranked", {}).get("loss_penalty", 10)
                remove_player_balance(
                    int(match["guild_id"]),
                    int(player_id),
                    loss_penalty,
                    f"💔 Penalidade derrota RANKED {self.match_id[:6]}"
                )
                update_player_stats(match["guild_id"], player_id, self.match_type, "loss")
        
        update_match(self.match_id, {
            "status": "finished",
            "winner": winner,
            "finished_at": datetime.utcnow()
        }, self.is_betting)
        
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
        
        for player_id in match["players"]:
            try:
                user = await self.bot.fetch_user(int(player_id))
                categoria = "APOSTADO" if self.is_betting else "RANKED"
                await user.send(f"🏆 Partida {categoria} finalizada! Vencedor: {winner or 'Empate'}")
            except:
                pass

    async def _cancel_match(self, interaction: discord.Interaction):
        if not is_mediator(interaction.user):
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

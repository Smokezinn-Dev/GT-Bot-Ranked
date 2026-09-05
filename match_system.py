# ============================================================
# MATCH_SYSTEM.PY - CORRIGIDO (DROPDOWN COM OPÇÕES)
# ============================================================

import discord
from discord.ui import Button, View, Select
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from database import (
    get_guild_settings,
    get_player_balance, add_player_balance, remove_player_balance,
    get_match, update_match, create_match,
    update_player_stats,
    create_ticket,
    get_mediator_roles,
)

_MAX_LOBBIES = 40
_LOBBY_TTL = 900


class MapSelectView(View):
    """View com dropdown de mapas + contador atualizado"""
    def __init__(self, match_system, guild_id: str, channel_id: str, author_id: str, match_type: str, is_betting: bool = False, bet_amount: int = 0):
        super().__init__(timeout=120)
        self.match_system = match_system
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.author_id = author_id
        self.match_type = match_type
        self.is_betting = is_betting
        self.bet_amount = bet_amount
        self.selected_map = None
        self.message = None
        
        # CRIA AS OPÇÕES DO DROPDOWN AQUI (NÃO DINÂMICO)
        self._create_options()

    def _create_options(self):
        """Cria as opções do dropdown com contadores"""
        settings = get_guild_settings(self.guild_id)
        maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
        
        emojis = {
            "Arena": "🏰", "Castelo": "🏯", "Floresta": "🌲", "Deserto": "🏜️",
            "Vulcão": "🌋", "Tundra": "❄️", "Cidade": "🌃", "Ilha": "🏝️"
        }
        
        options = []
        for map_name in maps:
            count = self.match_system.get_queue_count(self.guild_id, map_name, self.match_type)
            emoji = emojis.get(map_name, "🗺️")
            options.append(
                discord.SelectOption(
                    label=f"{map_name}",
                    value=map_name,
                    description=f"👥 {count} jogador(es) na fila",
                    emoji=emoji
                )
            )
        
        # Atualiza o select com as opções
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.options = options
                child.placeholder = f"🗺️ Selecione o mapa... ({self.match_type})"
                break

    @discord.ui.select(
        placeholder="🗺️ Selecione o mapa...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Carregando...", value="loading", description="Aguarde")
        ]
    )
    async def map_select(self, interaction: discord.Interaction, select: Select):
        if select.values[0] == "loading":
            return await interaction.response.send_message("⏳ Carregando opções...", ephemeral=True)
        
        self.selected_map = select.values[0]
        
        queue_count = self.match_system.get_queue_count(self.guild_id, self.selected_map, self.match_type)
        
        embed = discord.Embed(
            title="🗺️ Mapa Selecionado!",
            description=f"**Mapa:** {self.selected_map}\n**Tipo:** {self.match_type}\n**Na fila:** {queue_count} jogadores\n**Aposta:** {self.bet_amount if self.is_betting else 'Ranked'}",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Clique em '✅ Confirmar' para criar a partida")
        
        for child in self.children:
            child.disabled = True
        
        confirm_view = ConfirmMapView(
            match_system=self.match_system,
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            author_id=self.author_id,
            match_type=self.match_type,
            map_name=self.selected_map,
            is_betting=self.is_betting,
            bet_amount=self.bet_amount
        )
        
        await interaction.response.edit_message(embed=embed, view=confirm_view)


class ConfirmMapView(View):
    """View de confirmação após selecionar o mapa"""
    def __init__(self, match_system, guild_id: str, channel_id: str, author_id: str, match_type: str, map_name: str, is_betting: bool, bet_amount: int):
        super().__init__(timeout=60)
        self.match_system = match_system
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.author_id = author_id
        self.match_type = match_type
        self.map_name = map_name
        self.is_betting = is_betting
        self.bet_amount = bet_amount

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        result = await self.match_system.create_lobby(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            author_id=self.author_id,
            match_type=self.match_type,
            map_name=self.map_name,
            is_betting=self.is_betting,
            bet_amount=self.bet_amount,
        )
        
        if result.get("error"):
            embed = discord.Embed(
                title="❌ Erro",
                description=result["error"],
                color=0xff0000
            )
            return await interaction.response.edit_message(embed=embed, view=None)
        
        embed = discord.Embed(
            title="✅ Partida Criada!",
            description=f"**ID:** `{result['match_id'][:6]}`\n**Tipo:** {self.match_type}\n**Mapa:** {self.map_name}\n**Aposta:** {self.bet_amount if self.is_betting else 'Ranked'}",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Use !join {result['match_id'][:6]} para entrar")
        
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="❌ Cancelado",
            description="Criação da partida cancelada.",
            color=0xff0000
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)


class LobbyView(View):
    """View com botões para entrar na partida"""
    def __init__(self, match_id: str, match_type: str, max_players: int, is_betting: bool, bot, match_system):
        super().__init__(timeout=1800)
        self.match_id = match_id
        self.match_type = match_type
        self.max_players = max_players
        self.is_betting = is_betting
        self.bot = bot
        self.match_system = match_system
        self.message = None

    @discord.ui.button(label="✅ Entrar", style=discord.ButtonStyle.success, emoji="🎮")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        result = await self.match_system.join_lobby(self.match_id, str(interaction.user.id), None)
        
        if result.get("error"):
            return await interaction.response.send_message(result["error"], ephemeral=True)
        
        lobby = self.match_system.active_lobbies.get(self.match_id)
        if lobby:
            embed = self.match_system._create_lobby_embed(lobby)
            await interaction.response.edit_message(embed=embed, view=self)
            
            if result.get("match_started"):
                for child in self.children:
                    child.disabled = True
                await interaction.followup.edit_message(self.message.id, view=self)

    @discord.ui.button(label="🚪 Sair", style=discord.ButtonStyle.secondary, emoji="❌")
    async def leave_button(self, interaction: discord.Interaction, button: Button):
        lobby = self.match_system.active_lobbies.get(self.match_id)
        if not lobby:
            return await interaction.response.send_message("❌ Partida não encontrada!", ephemeral=True)
        
        if str(interaction.user.id) not in lobby["players"]:
            return await interaction.response.send_message("❌ Você não está nesta partida!", ephemeral=True)
        
        lobby["players"].remove(str(interaction.user.id))
        update_match(self.match_id, {"players": lobby["players"]}, self.is_betting)
        
        embed = self.match_system._create_lobby_embed(lobby)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("✅ Você saiu da partida.", ephemeral=True)

    @discord.ui.button(label="🔴 Time 1", style=discord.ButtonStyle.primary, emoji="🔴")
    async def team1_button(self, interaction: discord.Interaction, button: Button):
        await self._join_team(interaction, "team1")

    @discord.ui.button(label="🔵 Time 2", style=discord.ButtonStyle.primary, emoji="🔵")
    async def team2_button(self, interaction: discord.Interaction, button: Button):
        await self._join_team(interaction, "team2")

    async def _join_team(self, interaction: discord.Interaction, team: str):
        if self.match_type == "1v1":
            return await interaction.response.send_message("❌ 1v1 não tem times!", ephemeral=True)
        
        result = await self.match_system.join_lobby(self.match_id, str(interaction.user.id), team)
        
        if result.get("error"):
            return await interaction.response.send_message(result["error"], ephemeral=True)
        
        lobby = self.match_system.active_lobbies.get(self.match_id)
        if lobby:
            embed = self.match_system._create_lobby_embed(lobby)
            await interaction.response.edit_message(embed=embed, view=self)
            
            if result.get("match_started"):
                for child in self.children:
                    child.disabled = True
                await interaction.followup.edit_message(self.message.id, view=self)


class TicketPanelView(View):
    """View do painel de tickets para mediadores"""
    def __init__(self, ticket_system, guild_id: str):
        super().__init__(timeout=None)
        self.ticket_system = ticket_system
        self.guild_id = guild_id

    @discord.ui.button(label="🎫 Abrir Ticket", style=discord.ButtonStyle.primary, emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        if not self.ticket_system._is_mediator(interaction.user, self.guild_id):
            return await interaction.response.send_message("❌ Apenas mediadores podem abrir tickets!", ephemeral=True)
        
        # Cria um embed simples com instruções
        embed = discord.Embed(
            title="🎫 Criar Nova Partida",
            description="Use o comando `%criar` para criar uma partida com dropdown de mapas.",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MatchSystem:
    __slots__ = ("db", "config", "bot", "active_lobbies", "match_types", "_last_purge", "lobby_messages", "map_queues")

    def __init__(self, db, config, bot):
        self.db = db
        self.config = config
        self.bot = bot
        self.active_lobbies: Dict[str, dict] = {}
        self.lobby_messages: Dict[str, int] = {}
        self.map_queues: Dict[str, Dict[str, Dict[str, List[str]]]] = {}
        self._last_purge = 0.0
        self.match_types = {
            "1v1": {"max_players": 2, "teams": False},
            "2v2": {"max_players": 4, "teams": True},
            "3v3": {"max_players": 6, "teams": True},
        }

    def _purge_stale(self):
        now = time.monotonic()
        if now - self._last_purge < 60:
            return
        self._last_purge = now
        dead = [
            mid for mid, lob in self.active_lobbies.items()
            if now - lob.get("_ts", now) > _LOBBY_TTL
            or lob.get("status") in ("finished", "cancelled")
        ]
        for mid in dead:
            self.active_lobbies.pop(mid, None)
            self.lobby_messages.pop(mid, None)
        if len(self.active_lobbies) > _MAX_LOBBIES:
            oldest = sorted(
                self.active_lobbies.items(),
                key=lambda x: x[1].get("_ts", 0)
            )
            for mid, _ in oldest[: len(self.active_lobbies) - _MAX_LOBBIES]:
                self.active_lobbies.pop(mid, None)
                self.lobby_messages.pop(mid, None)

    def get_queue_count(self, guild_id: str, map_name: str, match_type: str = None) -> int:
        guild_queues = self.map_queues.get(guild_id, {})
        map_queue = guild_queues.get(map_name, {})
        
        if match_type:
            return len(map_queue.get(match_type, []))
        
        total = 0
        for players in map_queue.values():
            total += len(players)
        return total

    def get_all_map_counts(self, guild_id: str, match_type: str = None) -> Dict[str, int]:
        settings = get_guild_settings(guild_id)
        maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
        
        result = {}
        for map_name in maps:
            result[map_name] = self.get_queue_count(guild_id, map_name, match_type)
        return result

    def add_to_queue(self, guild_id: str, map_name: str, match_type: str, user_id: str):
        if guild_id not in self.map_queues:
            self.map_queues[guild_id] = {}
        if map_name not in self.map_queues[guild_id]:
            self.map_queues[guild_id][map_name] = {}
        if match_type not in self.map_queues[guild_id][map_name]:
            self.map_queues[guild_id][map_name][match_type] = []
        
        if user_id not in self.map_queues[guild_id][map_name][match_type]:
            self.map_queues[guild_id][map_name][match_type].append(user_id)

    def remove_from_queue(self, guild_id: str, map_name: str, match_type: str, user_id: str):
        try:
            self.map_queues[guild_id][map_name][match_type].remove(user_id)
            return True
        except (KeyError, ValueError):
            return False

    def _create_lobby_embed(self, lobby: dict) -> discord.Embed:
        settings = get_guild_settings(lobby["guild_id"])
        custom = settings.get("customization", {})
        color = custom.get("embed_color", 0x00ff00)
        footer = custom.get("embed_footer", "Rank System v3.0")
        thumbnail = custom.get("lobby_thumbnail", "https://i.imgur.com/8XxJt7z.png")
        
        match_type = lobby["match_type"]
        max_p = self.match_types[match_type]["max_players"]
        current_p = len(lobby["players"])
        
        if lobby.get("is_betting"):
            title = "💰 PARTIDA APOSTADA"
            color = 0xffd700
            icon = "💰"
        else:
            title = "🏆 PARTIDA RANKED"
            color = 0x00ff00
            icon = "🏆"
        
        embed = discord.Embed(
            title=f"{icon} {title}",
            description=f"**Modo:** {match_type}\n**Mapa:** {lobby.get('map', 'Arena')}",
            color=color,
            timestamp=datetime.utcnow()
        )
        
        progress = int((current_p / max_p) * 10)
        bar = "█" * progress + "░" * (10 - progress)
        status_text = "✅ PRONTO!" if current_p >= max_p else f"⏳ Aguardando ({current_p}/{max_p})"
        
        embed.add_field(
            name="👥 Jogadores",
            value=f"`{bar}` **{current_p}/{max_p}** - {status_text}",
            inline=False
        )
        
        if match_type == "1v1":
            players_str = "\n".join(f"👤 <@{p}>" for p in lobby["players"]) or "Aguardando..."
            embed.add_field(name="🎯 Jogadores", value=players_str, inline=False)
        else:
            teams = lobby.get("teams", {})
            t1 = [p for p, t in teams.items() if t == "team1"]
            t2 = [p for p, t in teams.items() if t == "team2"]
            
            embed.add_field(
                name=f"🔴 {lobby.get('team1_name', 'Time 1')}",
                value="\n".join(f"👤 <@{p}>" for p in t1) or "Vazio",
                inline=True
            )
            embed.add_field(
                name=f"🔵 {lobby.get('team2_name', 'Time 2')}",
                value="\n".join(f"👤 <@{p}>" for p in t2) or "Vazio",
                inline=True
            )
        
        if lobby.get("is_betting") and lobby.get("bet_amount"):
            embed.add_field(
                name="💰 Aposta",
                value=f"**{lobby['bet_amount']}** por jogador",
                inline=False
            )
        
        embed.add_field(
            name="👑 Criador",
            value=f"<@{lobby.get('creator_id')}>",
            inline=True
        )
        
        embed.set_footer(text=f"{footer} • ID: {lobby['id'][:6]}")
        embed.set_thumbnail(url=thumbnail)
        
        return embed

    async def _announce_match(self, channel_id: str, match_id: str, lobby: dict):
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        embed = self._create_lobby_embed(lobby)
        
        max_p = self.match_types[lobby["match_type"]]["max_players"]
        view = LobbyView(
            match_id=match_id,
            match_type=lobby["match_type"],
            max_players=max_p,
            is_betting=lobby.get("is_betting", False),
            bot=self.bot,
            match_system=self
        )
        
        try:
            msg = await channel.send(embed=embed, view=view)
            view.message = msg
            self.lobby_messages[match_id] = msg.id
            
            if len(lobby["players"]) >= max_p:
                for child in view.children:
                    child.disabled = True
                await msg.edit(view=view)
                await self._start_match(match_id)
        except Exception as e:
            print(f"Erro ao enviar lobby: {e}")

    async def create_lobby(
        self,
        guild_id: str,
        channel_id: str,
        author_id: str,
        match_type: str,
        map_name: str,
        is_betting: bool = False,
        bet_amount: int = 0,
        team1_name: str = "Time 1",
        team2_name: str = "Time 2",
    ) -> dict:
        self._purge_stale()

        settings = get_guild_settings(guild_id)

        if not await self._check_permissions(guild_id, author_id, settings, is_betting):
            return {"error": "❌ Você não tem permissão!"}

        if match_type not in self.match_types:
            return {"error": f"❌ Tipos: {', '.join(self.match_types)}"}

        gid, uid = int(guild_id), int(author_id)

        if is_betting:
            betting = settings.get("betting", {})
            if not betting.get("enabled", True):
                return {"error": "❌ Apostas desativadas!"}
            min_bet = int(betting.get("min_bet", 100))
            max_bet = int(betting.get("max_bet", 10000))
            if bet_amount < min_bet:
                return {"error": f"❌ Aposta mínima: {min_bet}"}
            if bet_amount > max_bet:
                return {"error": f"❌ Aposta máxima: {max_bet}"}
            if get_player_balance(gid, uid) < bet_amount:
                return {"error": f"❌ Saldo insuficiente! Você tem {get_player_balance(gid, uid)}"}
        else:
            entry_fee = int(settings.get("ranked", {}).get("entry_fee", 0))
            if entry_fee > 0 and get_player_balance(gid, uid) < entry_fee:
                return {"error": f"❌ Taxa de entrada: {entry_fee}"}

        match_data = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "creator_id": author_id,
            "match_type": match_type,
            "map": map_name or "Arena",
            "is_betting": is_betting,
            "bet_amount": bet_amount if is_betting else 0,
            "team1_name": team1_name,
            "team2_name": team2_name,
            "status": "waiting",
            "players": [author_id],
            "teams": {},
        }

        match_id = create_match(match_data, is_betting)

        if is_betting and bet_amount > 0:
            if not remove_player_balance(gid, uid, bet_amount, f"Aposta {match_id[:6]}"):
                return {"error": "❌ Falha ao cobrar aposta."}
        else:
            entry_fee = int(settings.get("ranked", {}).get("entry_fee", 0))
            if entry_fee > 0:
                if not remove_player_balance(gid, uid, entry_fee, f"Taxa RANKED {match_id[:6]}"):
                    return {"error": "❌ Falha ao cobrar taxa."}

        self.active_lobbies[match_id] = {
            "id": match_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "players": [author_id],
            "teams": {},
            "status": "waiting",
            "is_betting": is_betting,
            "bet_amount": bet_amount if is_betting else 0,
            "match_type": match_type,
            "map": map_name or "Arena",
            "team1_name": team1_name,
            "team2_name": team2_name,
            "creator_id": author_id,
            "_ts": time.monotonic(),
        }

        await self._announce_match(channel_id, match_id, self.active_lobbies[match_id])
        return {"match_id": match_id, "success": True}

    async def join_lobby(self, match_id: str, user_id: str, team: Optional[str] = None) -> dict:
        self._purge_stale()

        full_id = None
        lobby = None
        for mid, data in self.active_lobbies.items():
            if mid.startswith(match_id) or mid == match_id:
                full_id, lobby = mid, data
                break

        if not lobby:
            return {"error": "❌ Partida não encontrada!"}
        if lobby["status"] != "waiting":
            return {"error": "❌ Partida já em andamento!"}
        if user_id in lobby["players"]:
            return {"error": "❌ Você já está na partida!"}

        match_data = get_match(full_id, lobby["is_betting"])
        if not match_data:
            return {"error": "❌ Partida não encontrada no banco!"}

        settings = get_guild_settings(match_data["guild_id"])
        max_p = self.match_types[match_data["match_type"]]["max_players"]

        if len(lobby["players"]) >= max_p:
            return {"error": "❌ Partida cheia!"}

        if match_data["match_type"] != "1v1":
            if not team or team not in ("team1", "team2"):
                return {"error": "❌ Escolha time: team1 ou team2"}
            team_count = sum(1 for t in lobby["teams"].values() if t == team)
            if team_count >= max_p // 2:
                return {"error": f"❌ Time {team} está cheio!"}

        gid, uid = int(match_data["guild_id"]), int(user_id)

        if lobby["is_betting"]:
            bet = int(lobby.get("bet_amount", 0))
            if bet > 0:
                if get_player_balance(gid, uid) < bet:
                    return {"error": f"❌ Saldo insuficiente para aposta de {bet}!"}
                if not remove_player_balance(gid, uid, bet, f"Aposta {full_id[:6]}"):
                    return {"error": "❌ Falha ao cobrar aposta."}
        else:
            fee = int(settings.get("ranked", {}).get("entry_fee", 0))
            if fee > 0:
                if get_player_balance(gid, uid) < fee:
                    return {"error": f"❌ Taxa de entrada: {fee}"}
                if not remove_player_balance(gid, uid, fee, f"Taxa RANKED {full_id[:6]}"):
                    return {"error": "❌ Falha ao cobrar taxa."}

        lobby["players"].append(user_id)
        if team:
            lobby["teams"][user_id] = team
        lobby["_ts"] = time.monotonic()

        update_match(full_id, {
            "players": lobby["players"],
            "teams": lobby["teams"],
        }, lobby["is_betting"])

        if len(lobby["players"]) >= max_p:
            await self._start_match(full_id)
            return {"success": True, "match_started": True}

        return {"success": True, "player_count": len(lobby["players"])}

    async def _start_match(self, match_id: str):
        lobby = self.active_lobbies.get(match_id)
        if not lobby:
            return

        match_data = get_match(match_id, lobby["is_betting"])
        if not match_data:
            return

        settings = get_guild_settings(match_data["guild_id"])
        lobby["status"] = "started"
        update_match(match_id, {"status": "started"}, lobby["is_betting"])

        if settings.get("match_settings", {}).get("auto_ticket", True):
            ticket_id = await self._create_ticket(match_data, lobby, settings)
            if ticket_id:
                update_match(match_id, {"ticket_id": ticket_id}, lobby["is_betting"])

        await self._notify_players(match_data, lobby, settings)

    async def _create_ticket(self, match_data: dict, lobby: dict, settings: dict) -> Optional[str]:
        guild = self.bot.get_guild(int(match_data["guild_id"]))
        if not guild:
            return None

        cat_name = "APOSTADO" if lobby["is_betting"] else "RANKED"
        ms = settings.get("match_settings", {})
        category = None
        if ms.get("ticket_category"):
            try:
                category = guild.get_channel(int(ms["ticket_category"]))
            except Exception:
                pass

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }
        for pid in lobby["players"]:
            member = guild.get_member(int(pid))
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, view_channel=True
                )

        for role_id in get_mediator_roles(match_data["guild_id"]):
            role = guild.get_role(int(role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, view_channel=True
                )

        tpl = ms.get("ticket_name_template", "🎮-{tipo}-{match_id}")
        channel_name = tpl.format(tipo=cat_name, match_id=match_data["_id"][:6])[:90]

        try:
            channel = await guild.create_text_channel(
                channel_name, category=category, overwrites=overwrites,
                reason=f"Partida {cat_name}"
            )
        except Exception:
            return None

        embed = self._ticket_embed(match_data, lobby, settings)
        view = MediatorView(
            match_id=match_data["_id"],
            match_type=match_data["match_type"],
            is_betting=lobby["is_betting"],
            bot=self.bot,
            match_system=self,
        )
        try:
            await channel.send(embed=embed, view=view)
            for role_id in get_mediator_roles(match_data["guild_id"]):
                role = guild.get_role(int(role_id))
                if role:
                    await channel.send(f"🔔 {role.mention} — partida aguardando mediador!")
                    break
        except Exception:
            pass

        return create_ticket({
            "guild_id": match_data["guild_id"],
            "channel_id": str(channel.id),
            "match_id": match_data["_id"],
            "players": lobby["players"],
            "is_betting": lobby["is_betting"],
            "status": "active",
        })

    def _ticket_embed(self, match_data: dict, lobby: dict, settings: dict) -> discord.Embed:
        cat = "💰 APOSTADO" if lobby["is_betting"] else "🏆 RANKED"
        color = settings.get("customization", {}).get("embed_color", 0x00ff00)
        footer = settings.get("customization", {}).get("embed_footer", "Rank System v3.0")
        
        embed = discord.Embed(
            title=f"🎯 {cat} - {match_data['match_type']}",
            description=f"**Mapa:** {match_data['map']}",
            color=color,
            timestamp=datetime.utcnow(),
        )
        if lobby.get("bet_amount"):
            embed.add_field(name="💰 Aposta", value=str(lobby["bet_amount"]), inline=True)

        if match_data["match_type"] == "1v1":
            embed.add_field(
                name="👥 Jogadores",
                value="\n".join(f"👤 <@{p}>" for p in lobby["players"]),
                inline=False,
            )
        else:
            t1 = [p for p, t in lobby["teams"].items() if t == "team1"]
            t2 = [p for p, t in lobby["teams"].items() if t == "team2"]
            embed.add_field(
                name=f"🔴 {match_data.get('team1_name', 'Time 1')}",
                value="\n".join(f"👤 <@{p}>" for p in t1) or "Vazio",
                inline=True,
            )
            embed.add_field(
                name=f"🔵 {match_data.get('team2_name', 'Time 2')}",
                value="\n".join(f"👤 <@{p}>" for p in t2) or "Vazio",
                inline=True,
            )
        
        embed.set_footer(text=footer)
        embed.set_thumbnail(url=settings.get("customization", {}).get("lobby_thumbnail", "https://i.imgur.com/8XxJt7z.png"))
        return embed

    async def _notify_players(self, match_data: dict, lobby: dict, settings: dict):
        if not settings.get("customization", {}).get("dm_notifications", True):
            return
        cat = "APOSTADO" if lobby["is_betting"] else "RANKED"
        text = f"🎯 Partida {cat} começou!\n**Tipo:** {match_data['match_type']}\n**Mapa:** {match_data['map']}"
        for pid in lobby["players"]:
            try:
                user = await self.bot.fetch_user(int(pid))
                await user.send(text)
            except Exception:
                pass

    async def _check_permissions(self, guild_id: str, user_id: str, settings: dict, is_betting: bool) -> bool:
        key = "betting" if is_betting else "ranked"
        allowed = settings.get(key, {}).get("allowed_roles", [])
        if not allowed:
            return True
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return False
        member = guild.get_member(int(user_id))
        if not member:
            return False
        if member.guild_permissions.administrator:
            return True
        allowed_set = set(int(r) for r in allowed)
        return any(role.id in allowed_set for role in member.roles)

    async def cancel_match(self, match_id: str) -> bool:
        lobby = self.active_lobbies.get(match_id)
        if not lobby:
            for mid, data in list(self.active_lobbies.items()):
                if mid.startswith(match_id):
                    match_id, lobby = mid, data
                    break
        if not lobby:
            return False

        guild_id = lobby.get("guild_id")
        if not guild_id:
            m = get_match(match_id, lobby.get("is_betting", False))
            guild_id = m.get("guild_id") if m else None

        if guild_id and lobby.get("is_betting"):
            bet = int(lobby.get("bet_amount", 0))
            if bet > 0:
                for pid in lobby.get("players", []):
                    try:
                        add_player_balance(int(guild_id), int(pid), bet, f"Reembolso {match_id[:6]}")
                    except Exception:
                        pass
        elif guild_id:
            settings = get_guild_settings(str(guild_id))
            fee = int(settings.get("ranked", {}).get("entry_fee", 0))
            if fee > 0:
                for pid in lobby.get("players", []):
                    try:
                        add_player_balance(int(guild_id), int(pid), fee, f"Reembolso taxa {match_id[:6]}")
                    except Exception:
                        pass

        lobby["status"] = "cancelled"
        update_match(match_id, {"status": "cancelled"}, lobby.get("is_betting", False))

        for pid in lobby.get("players", []):
            try:
                user = await self.bot.fetch_user(int(pid))
                await user.send("❌ Partida cancelada! Valores reembolsados.")
            except Exception:
                pass

        self.active_lobbies.pop(match_id, None)
        return True

    async def get_match_info(self, match_id: str) -> Optional[dict]:
        for mid, lobby in self.active_lobbies.items():
            if mid.startswith(match_id) or mid == match_id:
                return lobby
        return None

    def _is_mediator(self, user: discord.User, guild_id: str) -> bool:
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return False
        member = guild.get_member(user.id)
        if not member:
            return False
        if member.guild_permissions.administrator:
            return True
        roles = get_mediator_roles(guild_id)
        if not roles:
            return False
        user_role_ids = {r.id for r in member.roles}
        return bool(user_role_ids & set(int(x) for x in roles))


class MediatorView(View):
    def __init__(self, match_id: str, match_type: str, is_betting: bool, bot, match_system):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.match_type = match_type
        self.is_betting = is_betting
        self.bot = bot
        self.match_system = match_system

    async def _is_mediator(self, interaction: discord.Interaction) -> bool:
        roles = get_mediator_roles(str(interaction.guild.id))
        if not roles:
            return interaction.user.guild_permissions.administrator
        user_role_ids = {r.id for r in interaction.user.roles}
        return bool(user_role_ids & set(int(x) for x in roles)) or interaction.user.guild_permissions.administrator

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
        if not await self._is_mediator(interaction):
            return await interaction.response.send_message("❌ Você não é mediador!", ephemeral=True)
        await self.match_system.cancel_match(self.match_id)
        for child in self.children:
            child.disabled = True
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0xff0000
        embed.add_field(name="❌ Cancelada", value=f"Por: {interaction.user.mention}", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _declare_winner(self, interaction: discord.Interaction, winner: Optional[str]):
        if not await self._is_mediator(interaction):
            return await interaction.response.send_message("❌ Você não é mediador!", ephemeral=True)

        match = get_match(self.match_id, self.is_betting)
        if not match:
            return await interaction.response.send_message("❌ Partida não encontrada!", ephemeral=True)

        settings = get_guild_settings(str(interaction.guild.id))
        players = match.get("players", [])
        teams = match.get("teams", {})

        winning_players: List[str] = []
        losing_players: List[str] = []

        if self.match_type == "1v1":
            if len(players) >= 2:
                if winner == "team1":
                    winning_players = [players[0]]
                    losing_players = [players[1]]
                elif winner == "team2":
                    winning_players = [players[1]]
                    losing_players = [players[0]]
            elif len(players) == 1 and winner:
                winning_players = [players[0]]
        else:
            for pid, team in teams.items():
                if winner and team == winner:
                    winning_players.append(pid)
                elif winner:
                    losing_players.append(pid)

        guild_id = int(match["guild_id"])

        if self.is_betting and winner and winning_players:
            bet = int(match.get("bet_amount", 0))
            if bet > 0:
                betting = settings.get("betting", {})
                mult = float(betting.get("win_multiplier", 1.9))
                tax = float(betting.get("tax_percent", 5.0))
                total_pot = bet * len(players)
                prize = int(total_pot * mult)
                tax_amt = int(prize * tax / 100)
                prize -= tax_amt
                per = prize // len(winning_players) if winning_players else 0
                for pid in winning_players:
                    add_player_balance(guild_id, int(pid), per, f"Prêmio aposta {self.match_id[:6]}")

        if not self.is_betting:
            win_bonus = int(settings.get("ranked", {}).get("win_bonus", 50))
            loss_pen = int(settings.get("ranked", {}).get("loss_penalty", 10))
            for pid in winning_players:
                if win_bonus > 0:
                    add_player_balance(guild_id, int(pid), win_bonus, f"Vitória RANKED {self.match_id[:6]}")
                update_player_stats(str(guild_id), str(pid), self.match_type, "win")
            for pid in losing_players:
                if loss_pen > 0:
                    remove_player_balance(guild_id, int(pid), loss_pen, f"Derrota RANKED {self.match_id[:6]}")
                update_player_stats(str(guild_id), str(pid), self.match_type, "loss")

        update_match(self.match_id, {
            "status": "finished",
            "winner": winner,
            "finished_at": datetime.utcnow(),
        }, self.is_betting)

        self.match_system.active_lobbies.pop(self.match_id, None)

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0x00ff00 if winner else 0xffaa00
        embed.add_field(
            name="🏆 Resultado",
            value=f"**Vencedor:** {winner or 'Empate'}\n**Por:** {interaction.user.mention}",
            inline=False,
        )
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

        for pid in players:
            try:
                user = await self.bot.fetch_user(int(pid))
                cat = "APOSTADO" if self.is_betting else "RANKED"
                await user.send(f"🏆 Partida {cat} finalizada! Resultado: {winner or 'Empate'}")
            except Exception:
                pass
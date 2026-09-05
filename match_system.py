# ============================================================
# MATCH_SYSTEM.PY - COM SELEÇÃO DE MEMBROS E TIMES + OTIMIZAÇÕES
# ============================================================

import discord
from discord.ui import Button, View, Select, Modal, TextInput
import asyncio
import time
import gc
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
from asyncio import Semaphore

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

# ============================================================
# RATE LIMITER
# ============================================================

class _RateLimiter:
    """Rate limiter para evitar spam de comandos"""
    __slots__ = ("_limits", "_lock")
    
    def __init__(self):
        self._limits = defaultdict(lambda: {'count': 0, 'reset': 0})
        self._lock = asyncio.Lock()
    
    async def check_and_increment(self, key: str, max_per_second: int = 5) -> bool:
        """Verifica se pode executar a ação"""
        async with self._lock:
            now = time.monotonic()
            data = self._limits[key]
            if now > data['reset']:
                data['count'] = 0
                data['reset'] = now + 1
            
            if data['count'] >= max_per_second:
                return False
            
            data['count'] += 1
            return True

_rate_limiter = _RateLimiter()

# ============================================================
# MODAL - SELEÇÃO DE MAPA (FORMULÁRIO)
# ============================================================

class MapSelectModal(Modal):
    def __init__(self, match_system, guild_id: str, channel_id: str, author_id: str, match_type: str, is_betting: bool = False, bet_amount: int = 0):
        super().__init__(title="🗺️ Selecione o Mapa", timeout=120)
        self.match_system = match_system
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.author_id = author_id
        self.match_type = match_type
        self.is_betting = is_betting
        self.bet_amount = bet_amount
        
        settings = get_guild_settings(guild_id)
        maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
        
        self.map_input = TextInput(
            label="Digite o nome do mapa",
            placeholder=f"Mapas disponíveis: {', '.join(maps)}",
            style=discord.TextStyle.short,
            max_length=50,
            required=True
        )
        self.add_item(self.map_input)

    async def on_submit(self, interaction: discord.Interaction):
        map_name = self.map_input.value.strip()
        
        settings = get_guild_settings(self.guild_id)
        maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
        
        if map_name not in maps:
            return await interaction.response.send_message(
                f"❌ Mapa '{map_name}' não encontrado! Mapas disponíveis: {', '.join(maps)}",
                ephemeral=True
            )
        
        view = TeamSelectView(
            match_system=self.match_system,
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            author_id=self.author_id,
            match_type=self.match_type,
            map_name=map_name,
            is_betting=self.is_betting,
            bet_amount=self.bet_amount
        )
        
        embed = discord.Embed(
            title="👥 Seleção de Times",
            description=f"**Mapa:** {map_name}\n**Modo:** {self.match_type}\n\nSelecione os membros para cada time:",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        max_players = self.match_system.match_types[self.match_type]["max_players"]
        embed.add_field(
            name="📋 Instruções",
            value=f"Selecione **{max_players}** jogadores no total.\nTime A: {max_players//2} jogadores\nTime B: {max_players//2} jogadores",
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed, view=view, content=None)


# ============================================================
# VIEW - SELEÇÃO DE TIMES (COM MEMBROS DO SERVER)
# ============================================================

class TeamSelectView(View):
    def __init__(self, match_system, guild_id: str, channel_id: str, author_id: str, match_type: str, map_name: str, is_betting: bool = False, bet_amount: int = 0):
        super().__init__(timeout=300)
        self.match_system = match_system
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.author_id = author_id
        self.match_type = match_type
        self.map_name = map_name
        self.is_betting = is_betting
        self.bet_amount = bet_amount
        self.team_a = []
        self.team_b = []
        self.max_players = match_system.match_types[match_type]["max_players"]
        self.players_per_team = self.max_players // 2
        self.selected_team = "A"
        self.message = None
        self.guild = None
        
        self.guild = match_system.bot.get_guild(int(guild_id))

    @discord.ui.select(
        placeholder="👤 Selecione um membro para adicionar ao time",
        min_values=1,
        max_values=1,
        options=[]
    )
    async def select_member(self, interaction: discord.Interaction, select: Select):
        if not select.values:
            return
        
        member_id = int(select.values[0])
        member = self.guild.get_member(member_id)
        if not member:
            return await interaction.response.send_message("❌ Membro não encontrado!", ephemeral=True)
        
        if member_id in self.team_a or member_id in self.team_b:
            return await interaction.response.send_message(f"❌ {member.display_name} já está em um time!", ephemeral=True)
        
        if self.selected_team == "A":
            if len(self.team_a) >= self.players_per_team:
                return await interaction.response.send_message(f"❌ Time A já está completo! ({self.players_per_team}/{self.players_per_team})", ephemeral=True)
            self.team_a.append(member_id)
            await interaction.response.send_message(f"✅ {member.display_name} adicionado ao **Time A**!", ephemeral=True)
        else:
            if len(self.team_b) >= self.players_per_team:
                return await interaction.response.send_message(f"❌ Time B já está completo! ({self.players_per_team}/{self.players_per_team})", ephemeral=True)
            self.team_b.append(member_id)
            await interaction.response.send_message(f"✅ {member.display_name} adicionado ao **Time B**!", ephemeral=True)
        
        await self.update_display(interaction)
        
        if len(self.team_a) >= self.players_per_team and len(self.team_b) >= self.players_per_team:
            await self.start_match(interaction)

    @discord.ui.button(label="🔴 Time A", style=discord.ButtonStyle.primary, emoji="🔴")
    async def select_team_a(self, interaction: discord.Interaction, button: Button):
        self.selected_team = "A"
        await interaction.response.send_message("🔴 Agora você está adicionando ao **Time A**!", ephemeral=True)
        await self.update_display(interaction)

    @discord.ui.button(label="🔵 Time B", style=discord.ButtonStyle.primary, emoji="🔵")
    async def select_team_b(self, interaction: discord.Interaction, button: Button):
        self.selected_team = "B"
        await interaction.response.send_message("🔵 Agora você está adicionando ao **Time B**!", ephemeral=True)
        await self.update_display(interaction)

    @discord.ui.button(label="🗑️ Limpar Time A", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def clear_team_a(self, interaction: discord.Interaction, button: Button):
        self.team_a = []
        await interaction.response.send_message("🗑️ Time A limpo!", ephemeral=True)
        await self.update_display(interaction)

    @discord.ui.button(label="🗑️ Limpar Time B", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def clear_team_b(self, interaction: discord.Interaction, button: Button):
        self.team_b = []
        await interaction.response.send_message("🗑️ Time B limpo!", ephemeral=True)
        await self.update_display(interaction)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.stop()
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="❌ Cancelado",
            description="Criação da partida cancelada.",
            color=0xff0000
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def update_display(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="👥 Seleção de Times",
            description=f"**Mapa:** {self.map_name}\n**Modo:** {self.match_type}",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        team_a_names = []
        for uid in self.team_a:
            member = self.guild.get_member(uid)
            team_a_names.append(f"👤 {member.display_name if member else f'ID:{uid}'}")
        
        embed.add_field(
            name=f"🔴 Time A ({len(self.team_a)}/{self.players_per_team})",
            value="\n".join(team_a_names) or "Vazio",
            inline=True
        )
        
        team_b_names = []
        for uid in self.team_b:
            member = self.guild.get_member(uid)
            team_b_names.append(f"👤 {member.display_name if member else f'ID:{uid}'}")
        
        embed.add_field(
            name=f"🔵 Time B ({len(self.team_b)}/{self.players_per_team})",
            value="\n".join(team_b_names) or "Vazio",
            inline=True
        )
        
        total = len(self.team_a) + len(self.team_b)
        status = "✅ COMPLETO!" if total >= self.max_players else f"⏳ Aguardando ({total}/{self.max_players})"
        embed.add_field(
            name="📊 Status",
            value=f"**Total:** {total}/{self.max_players}\n**Selecionando:** Time {self.selected_team}\n{status}",
            inline=False
        )
        
        embed.set_footer(text=f"Selecione membros para o Time {self.selected_team}")
        
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                options = []
                for member in self.guild.members:
                    if member.bot:
                        continue
                    if member.id in self.team_a or member.id in self.team_b:
                        continue
                    options.append(
                        discord.SelectOption(
                            label=member.display_name[:50],
                            value=str(member.id),
                            emoji="👤"
                        )
                    )
                    if len(options) >= 25:
                        break
                
                if options:
                    child.options = options
                    child.placeholder = f"👤 Selecione um membro para o Time {self.selected_team}"
                else:
                    child.options = [
                        discord.SelectOption(
                            label="Nenhum membro disponível",
                            value="none",
                            emoji="❌"
                        )
                    ]
                    child.placeholder = "👤 Nenhum membro disponível"
                break
        
        await interaction.message.edit(embed=embed, view=self)

    async def start_match(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        
        all_players = self.team_a + self.team_b
        teams = {}
        for uid in self.team_a:
            teams[str(uid)] = "team1"
        for uid in self.team_b:
            teams[str(uid)] = "team2"
        
        result = await self.match_system.create_lobby_with_teams(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            author_id=self.author_id,
            match_type=self.match_type,
            map_name=self.map_name,
            players=all_players,
            teams=teams,
            is_betting=self.is_betting,
            bet_amount=self.bet_amount
        )
        
        if result.get("error"):
            embed = discord.Embed(
                title="❌ Erro",
                description=result["error"],
                color=0xff0000
            )
            return await interaction.response.edit_message(embed=embed, view=self)
        
        embed = discord.Embed(
            title="✅ Partida Criada!",
            description=f"**ID:** `{result['match_id'][:6]}`\n**Mapa:** {self.map_name}\n**Modo:** {self.match_type}",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        team_a_names = []
        for uid in self.team_a:
            member = self.guild.get_member(uid)
            team_a_names.append(f"👤 {member.display_name if member else f'ID:{uid}'}")
        
        team_b_names = []
        for uid in self.team_b:
            member = self.guild.get_member(uid)
            team_b_names.append(f"👤 {member.display_name if member else f'ID:{uid}'}")
        
        embed.add_field(
            name="🔴 Time A",
            value="\n".join(team_a_names),
            inline=True
        )
        embed.add_field(
            name="🔵 Time B",
            value="\n".join(team_b_names),
            inline=True
        )
        
        embed.set_footer(text=f"Use !join {result['match_id'][:6]} para entrar")
        
        await interaction.response.edit_message(embed=embed, view=self)


# ============================================================
# VIEW - PAINEL DO MEDIADOR NO TICKET
# ============================================================

class MediatorMatchView(View):
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

    @discord.ui.button(label="🔴 Time A Venceu", style=discord.ButtonStyle.success, emoji="🏆")
    async def team_a_win(self, interaction: discord.Interaction, button: Button):
        await self._declare_winner(interaction, "team1")

    @discord.ui.button(label="🔵 Time B Venceu", style=discord.ButtonStyle.success, emoji="🏆")
    async def team_b_win(self, interaction: discord.Interaction, button: Button):
        await self._declare_winner(interaction, "team2")

    @discord.ui.button(label="⚖️ Empate", style=discord.ButtonStyle.secondary, emoji="🤝")
    async def draw(self, interaction: discord.Interaction, button: Button):
        await self._declare_winner(interaction, None)

    @discord.ui.button(label="❌ Cancelar Partida", style=discord.ButtonStyle.danger, emoji="❌")
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

        team_a_players = [p for p, t in teams.items() if t == "team1"]
        team_b_players = [p for p, t in teams.items() if t == "team2"]

        winning_players = []
        losing_players = []

        if winner == "team1":
            winning_players = team_a_players
            losing_players = team_b_players
            winner_name = "🔴 Time A"
        elif winner == "team2":
            winning_players = team_b_players
            losing_players = team_a_players
            winner_name = "🔵 Time B"
        else:
            winner_name = "🤝 Empate"

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
        
        result_text = f"**Vencedor:** {winner_name}\n**Por:** {interaction.user.mention}"
        if winning_players:
            winners = []
            for pid in winning_players:
                member = interaction.guild.get_member(int(pid))
                winners.append(f"👤 {member.display_name if member else f'ID:{pid}'}")
            result_text += f"\n\n**🏆 Campeões:**\n" + "\n".join(winners)
        
        embed.add_field(name="📊 Resultado Final", value=result_text, inline=False)
        
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

        for pid in players:
            try:
                user = await self.bot.fetch_user(int(pid))
                cat = "APOSTADO" if self.is_betting else "RANKED"
                await user.send(f"🏆 Partida {cat} finalizada!\nResultado: {winner_name}")
            except Exception:
                pass


# ============================================================
# MATCH SYSTEM PRINCIPAL (ATUALIZADO)
# ============================================================

class MatchSystem:
    __slots__ = ("db", "config", "bot", "active_lobbies", "match_types", "_last_purge", "lobby_messages", "_semaphore", "_batch_queue", "_batch_lock", "_batch_task")

    def __init__(self, db, config, bot):
        self.db = db
        self.config = config
        self.bot = bot
        self.active_lobbies: Dict[str, dict] = {}
        self.lobby_messages: Dict[str, int] = {}
        self._last_purge = 0.0
        self.match_types = {
            "1v1": {"max_players": 2, "teams": False},
            "2v2": {"max_players": 4, "teams": True},
            "3v3": {"max_players": 6, "teams": True},
            "4v4": {"max_players": 8, "teams": True},
        }
        self._semaphore = Semaphore(3)
        self._batch_queue = []
        self._batch_lock = asyncio.Lock()
        self._batch_task = None

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
        if dead:
            gc.collect()

    async def _batch_update_stats(self, updates: List[dict]):
        """Atualiza stats em batch - reduz queries"""
        if not updates:
            return
        
        async with self._batch_lock:
            self._batch_queue.extend(updates)
            if len(self._batch_queue) >= 5:
                await self._flush_batch()
    
    async def _flush_batch(self):
        """Executa batch de updates"""
        if not self._batch_queue:
            return
        
        updates = self._batch_queue.copy()
        self._batch_queue.clear()
        
        for update in updates:
            try:
                update_player_stats(**update)
            except Exception:
                pass
        
        if len(updates) > 3:
            gc.collect()

    async def create_lobby_with_teams(
        self,
        guild_id: str,
        channel_id: str,
        author_id: str,
        match_type: str,
        map_name: str,
        players: List[int],
        teams: Dict[str, str],
        is_betting: bool = False,
        bet_amount: int = 0,
        team1_name: str = "Time A",
        team2_name: str = "Time B",
    ) -> dict:
        """Cria lobby com times já definidos"""
        if not await _rate_limiter.check_and_increment(f"lobby:{author_id}"):
            return {"error": "⏳ Muitas partidas criadas. Aguarde um momento."}
        
        self._purge_stale()

        settings = get_guild_settings(guild_id)

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
            
            for pid in players:
                if get_player_balance(gid, int(pid)) < bet_amount:
                    return {"error": f"❌ <@{pid}> não tem saldo suficiente!"}

        players_str = [str(p) for p in players]
        teams_str = {str(k): v for k, v in teams.items()}

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
            "players": players_str,
            "teams": teams_str,
        }

        match_id = create_match(match_data, is_betting)

        if is_betting and bet_amount > 0:
            for pid in players_str:
                if not remove_player_balance(int(guild_id), int(pid), bet_amount, f"Aposta {match_id[:6]}"):
                    for refund_pid in players_str:
                        if refund_pid != pid:
                            add_player_balance(int(guild_id), int(refund_pid), bet_amount, f"Reembolso {match_id[:6]}")
                    return {"error": f"❌ Jogador <@{pid}> não tem saldo suficiente!"}

        self.active_lobbies[match_id] = {
            "id": match_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "players": players_str,
            "teams": teams_str,
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

        await self._start_match(match_id)
        
        return {"match_id": match_id, "success": True}

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
        view = MediatorMatchView(
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
                    await channel.send(f"🔔 {role.mention} — Partida pronta para ser iniciada!")
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
            timestamp=datetime.utcnow()
        )
        
        if lobby.get("bet_amount"):
            embed.add_field(name="💰 Aposta", value=str(lobby["bet_amount"]), inline=True)

        teams = lobby.get("teams", {})
        team1_name = match_data.get("team1_name", "🔴 Time A")
        team2_name = match_data.get("team2_name", "🔵 Time B")
        
        team_a_players = [p for p, t in teams.items() if t == "team1"]
        team_b_players = [p for p, t in teams.items() if t == "team2"]
        
        embed.add_field(
            name=f"🔴 {team1_name}",
            value="\n".join(f"👤 <@{p}>" for p in team_a_players) or "Vazio",
            inline=True
        )
        embed.add_field(
            name=f"🔵 {team2_name}",
            value="\n".join(f"👤 <@{p}>" for p in team_b_players) or "Vazio",
            inline=True
        )
        
        embed.add_field(
            name="📋 Instruções",
            value="Clique no botão do time vencedor abaixo para finalizar a partida.",
            inline=False
        )
        
        embed.set_footer(text=footer)
        embed.set_thumbnail(url=settings.get("customization", {}).get("lobby_thumbnail", "https://i.imgur.com/8XxJt7z.png"))
        
        return embed

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

        ticket_id = await self._create_ticket(match_data, lobby, settings)
        if ticket_id:
            update_match(match_id, {"ticket_id": ticket_id}, lobby["is_betting"])

        await self._notify_players(match_data, lobby, settings)

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

        if guild_id and lobby.get("is_betting"):
            bet = int(lobby.get("bet_amount", 0))
            if bet > 0:
                for pid in lobby.get("players", []):
                    try:
                        add_player_balance(int(guild_id), int(pid), bet, f"Reembolso {match_id[:6]}")
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
        await self._flush_batch()
        gc.collect()
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
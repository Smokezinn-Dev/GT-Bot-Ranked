# ============================================================
# MATCH_SYSTEM.PY - CORRIGIDO E OTIMIZADO
# ============================================================

import discord
from discord.ui import Button, View, Select, Modal, TextInput
import asyncio
import time
import gc
import random
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from asyncio import Semaphore
import hashlib

from database import (
    get_guild_settings,
    get_player_balance, add_player_balance, remove_player_balance,
    get_match, update_match, create_match,
    update_player_stats,
    create_ticket,
    get_mediator_roles,
    safe_object_id,
    clear_user_cache,
)

_MAX_LOBBIES = 40
_LOBBY_TTL = 900

# ============================================================
# RATE LIMITER POR USUÁRIO (CORRIGIDO)
# ============================================================

class _UserRateLimiter:
    """Rate limiter por usuário + ação para evitar spam"""
    __slots__ = ("_limits", "_max_per_second", "_lock")
    
    def __init__(self, max_per_second: int = 5):
        self._limits: Dict[str, Dict] = {}
        self._max_per_second = max_per_second
        self._lock = asyncio.Lock()
    
    async def check(self, user_id: str, action: str) -> bool:
        key = f"{user_id}:{action}"
        async with self._lock:
            now = time.monotonic()
            data = self._limits.get(key, {'count': 0, 'reset': 0, 'total': 0})
            
            if now > data['reset']:
                data['count'] = 0
                data['reset'] = now + 1
            
            if data['count'] >= self._max_per_second:
                return False
            
            data['count'] += 1
            data['total'] += 1
            self._limits[key] = data
            
            # Limpeza periódica
            if len(self._limits) > 1000:
                old_keys = [k for k, v in self._limits.items() if now > v['reset'] + 60]
                for k in old_keys:
                    self._limits.pop(k, None)
            
            return True

_rate_limiter = _UserRateLimiter(max_per_second=4)

# ============================================================
# MODAL - SELEÇÃO DE MAPA
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
# VIEW - SELEÇÃO DE TIMES (OTIMIZADA)
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
        self._finished = False
        self._refresh_lock = False
        
        self.guild = match_system.bot.get_guild(int(guild_id))

    async def _safe_refresh(self, interaction: discord.Interaction):
        """Refresh com lock para evitar múltiplas edições simultâneas"""
        if self._refresh_lock:
            return
        self._refresh_lock = True
        try:
            await self.update_display(interaction)
        finally:
            self._refresh_lock = False

    @discord.ui.select(
        placeholder="👤 Selecione um membro para adicionar ao time",
        min_values=1,
        max_values=1,
        options=[]
    )
    async def select_member(self, interaction: discord.Interaction, select: Select):
        if self._finished:
            return await interaction.response.send_message("❌ Partida já foi iniciada!", ephemeral=True)
        
        if not select.values or select.values[0] == "none":
            return
        
        try:
            member_id = int(select.values[0])
        except (ValueError, TypeError):
            return
        
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
        
        await self._safe_refresh(interaction)
        
        if len(self.team_a) >= self.players_per_team and len(self.team_b) >= self.players_per_team:
            await self.start_match(interaction)

    @discord.ui.button(label="🔴 Time A", style=discord.ButtonStyle.primary, emoji="🔴")
    async def select_team_a(self, interaction: discord.Interaction, button: Button):
        if self._finished:
            return
        self.selected_team = "A"
        await interaction.response.send_message("🔴 Agora você está adicionando ao **Time A**!", ephemeral=True)
        await self._safe_refresh(interaction)

    @discord.ui.button(label="🔵 Time B", style=discord.ButtonStyle.primary, emoji="🔵")
    async def select_team_b(self, interaction: discord.Interaction, button: Button):
        if self._finished:
            return
        self.selected_team = "B"
        await interaction.response.send_message("🔵 Agora você está adicionando ao **Time B**!", ephemeral=True)
        await self._safe_refresh(interaction)

    @discord.ui.button(label="🗑️ Limpar Time A", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def clear_team_a(self, interaction: discord.Interaction, button: Button):
        if self._finished:
            return
        self.team_a = []
        await interaction.response.send_message("🗑️ Time A limpo!", ephemeral=True)
        await self._safe_refresh(interaction)

    @discord.ui.button(label="🗑️ Limpar Time B", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def clear_team_b(self, interaction: discord.Interaction, button: Button):
        if self._finished:
            return
        self.team_b = []
        await interaction.response.send_message("🗑️ Time B limpo!", ephemeral=True)
        await self._safe_refresh(interaction)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.stop()
        self._finished = True
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="❌ Cancelado",
            description="Criação da partida cancelada.",
            color=0xff0000
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def update_display(self, interaction: discord.Interaction):
        if self._finished:
            return
        
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
        
        # Atualizar select com membros disponíveis
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                options = []
                available_members = []
                
                # Coletar membros disponíveis (não bots, não já selecionados)
                for member in self.guild.members:
                    if member.bot:
                        continue
                    if member.id in self.team_a or member.id in self.team_b:
                        continue
                    available_members.append(member)
                
                # Limitar a 25 opções por segurança
                for member in available_members[:25]:
                    options.append(
                        discord.SelectOption(
                            label=member.display_name[:50],
                            value=str(member.id),
                            emoji="👤"
                        )
                    )
                
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
        
        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

    async def start_match(self, interaction: discord.Interaction):
        if self._finished:
            return
        
        self._finished = True
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
        
        embed = discord.Embed(
            title="✅ Partida Criada!" if not result.get("error") else "❌ Erro",
            description=result.get("error") or f"**ID:** `{result['match_id'][:6]}`\n**Mapa:** {self.map_name}\n**Modo:** {self.match_type}",
            color=0xff0000 if result.get("error") else 0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        if not result.get("error"):
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
                value="\n".join(team_a_names) or "Vazio",
                inline=True
            )
            embed.add_field(
                name="🔵 Time B",
                value="\n".join(team_b_names) or "Vazio",
                inline=True
            )
            
            embed.set_footer(text=f"Use !join {result['match_id'][:6]} para entrar")
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)


# ============================================================
# VIEW - PAINEL DO MEDIADOR (COM VALIDAÇÃO SEGURA)
# ============================================================

class MediatorMatchView(View):
    def __init__(self, match_id: str, match_type: str, is_betting: bool, bot, match_system):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.match_type = match_type
        self.is_betting = is_betting
        self.bot = bot
        self.match_system = match_system
        self._declared = False

    async def _is_mediator(self, interaction: discord.Interaction) -> bool:
        roles = get_mediator_roles(str(interaction.guild.id))
        if not roles:
            return interaction.user.guild_permissions.administrator
        user_role_ids = {r.id for r in interaction.user.roles}
        return bool(user_role_ids & set(int(x) for x in roles)) or interaction.user.guild_permissions.administrator

    async def _mediation_block_reason(self, interaction: discord.Interaction) -> Optional[str]:
        if interaction.user.guild_permissions.administrator:
            return None
        if not await self._is_mediator(interaction):
            return "❌ Você não é mediador!"

        match = get_match(self.match_id, self.is_betting)
        players = set(str(p) for p in (match or {}).get("players", []))
        if not players:
            lobby = self.match_system.active_lobbies.get(self.match_id)
            if lobby:
                players = set(str(p) for p in lobby.get("players", []))

        if str(interaction.user.id) in players:
            return (
                "❌ Você é jogador dessa partida e por isso **não pode mediá-la** "
                "(evita favorecimento). Peça para um mediador que não esteja jogando."
            )
        return None

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
        if self._declared:
            return await interaction.response.send_message("❌ Esta partida já foi finalizada!", ephemeral=True)
        
        reason = await self._mediation_block_reason(interaction)
        if reason:
            return await interaction.response.send_message(reason, ephemeral=True)
        
        self._declared = True
        await self.match_system.cancel_match(self.match_id)
        
        for child in self.children:
            child.disabled = True
        
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0xff0000
        embed.add_field(name="❌ Cancelada", value=f"Por: {interaction.user.mention}", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _declare_winner(self, interaction: discord.Interaction, winner: Optional[str]):
        if self._declared:
            return await interaction.response.send_message("❌ Esta partida já foi finalizada!", ephemeral=True)
        
        reason = await self._mediation_block_reason(interaction)
        if reason:
            return await interaction.response.send_message(reason, ephemeral=True)

        self._declared = True
        
        match = get_match(self.match_id, self.is_betting)
        if not match:
            self._declared = False
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

        try:
            guild_id = int(match["guild_id"])
        except (ValueError, TypeError):
            guild_id = 0

        if self.is_betting and winner and winning_players and guild_id:
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
                if per > 0:
                    for pid in winning_players:
                        try:
                            add_player_balance(guild_id, int(pid), per, f"Prêmio aposta {self.match_id[:6]}")
                        except (ValueError, TypeError):
                            continue

        if not self.is_betting and guild_id:
            win_bonus = int(settings.get("ranked", {}).get("win_bonus", 50))
            loss_pen = int(settings.get("ranked", {}).get("loss_penalty", 10))
            
            for pid in winning_players:
                try:
                    uid_int = int(pid)
                    if win_bonus > 0:
                        add_player_balance(guild_id, uid_int, win_bonus, f"Vitória RANKED {self.match_id[:6]}")
                    update_player_stats(str(guild_id), str(uid_int), self.match_type, "win")
                except (ValueError, TypeError):
                    continue
            
            for pid in losing_players:
                try:
                    uid_int = int(pid)
                    if loss_pen > 0:
                        remove_player_balance(guild_id, uid_int, loss_pen, f"Derrota RANKED {self.match_id[:6]}")
                    update_player_stats(str(guild_id), str(uid_int), self.match_type, "loss")
                except (ValueError, TypeError):
                    continue

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
                member = interaction.guild.get_member(int(pid)) if pid else None
                winners.append(f"👤 {member.display_name if member else f'ID:{pid}'}")
            result_text += f"\n\n**🏆 Campeões:**\n" + "\n".join(winners)
        
        embed.add_field(name="📊 Resultado Final", value=result_text, inline=False)
        
        for child in self.children:
            child.disabled = True

        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

        # Notificar jogadores em background
        for pid in players:
            try:
                user = await self.bot.fetch_user(int(pid))
                cat = "APOSTADO" if self.is_betting else "RANKED"
                await user.send(f"🏆 Partida {cat} finalizada!\nResultado: {winner_name}")
            except Exception:
                pass


# ============================================================
# VIEW - SELEÇÃO DE TIME PELOS PRÓPRIOS JOGADORES
# ============================================================

class SelfTeamSelectView(View):
    def __init__(self, match_system, guild_id: str, channel_id: str, match_type: str, map_name: str, players: List[str], timeout: int = 180):
        super().__init__(timeout=timeout)
        self.match_system = match_system
        self.guild_id = str(guild_id)
        self.channel_id = str(channel_id)
        self.match_type = match_type
        self.map_name = map_name
        self.players = [str(p) for p in players]
        self.max_players = match_system.match_types[match_type]["max_players"]
        self.per_team = self.max_players // 2
        self.team_a: List[str] = []
        self.team_b: List[str] = []
        self.message: Optional[discord.Message] = None
        self._finished = False
        self._timeout_task: Optional[asyncio.Task] = None

    def _display_name(self, uid: str) -> str:
        guild = self.match_system.bot.get_guild(int(self.guild_id))
        member = guild.get_member(int(uid)) if guild else None
        return member.display_name if member else f"<@{uid}>"

    def build_embed(self) -> discord.Embed:
        pending = [p for p in self.players if p not in self.team_a and p not in self.team_b]
        embed = discord.Embed(
            title="👥 Fila completa — escolham o time!",
            description=(
                f"**Mapa:** {self.map_name}\n**Modo:** {self.match_type}\n\n"
                "Cada jogador escolhe seu próprio time clicando em um dos botões abaixo."
            ),
            color=0x5865F2,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(
            name=f"🔴 Time A ({len(self.team_a)}/{self.per_team})",
            value="\n".join(f"👤 {self._display_name(p)}" for p in self.team_a) or "Vazio",
            inline=True
        )
        embed.add_field(
            name=f"🔵 Time B ({len(self.team_b)}/{self.per_team})",
            value="\n".join(f"👤 {self._display_name(p)}" for p in self.team_b) or "Vazio",
            inline=True
        )
        if pending:
            embed.add_field(
                name="⏳ Aguardando escolha",
                value=", ".join(f"<@{p}>" for p in pending[:10]),
                inline=False
            )
        return embed

    async def _pick(self, interaction: discord.Interaction, team_list: List[str], label: str):
        if self._finished:
            return await interaction.response.send_message("❌ A partida já foi criada!", ephemeral=True)
        
        uid = str(interaction.user.id)
        if uid not in self.players:
            return await interaction.response.send_message("❌ Você não faz parte dessa fila!", ephemeral=True)
        if uid in self.team_a or uid in self.team_b:
            return await interaction.response.send_message("❌ Você já escolheu um time!", ephemeral=True)
        if len(team_list) >= self.per_team:
            return await interaction.response.send_message(f"❌ Time {label} já está completo!", ephemeral=True)

        team_list.append(uid)

        if len(self.team_a) >= self.per_team and len(self.team_b) >= self.per_team:
            await self._finish(interaction)
        else:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Time A", style=discord.ButtonStyle.danger, emoji="🔴")
    async def pick_a(self, interaction: discord.Interaction, button: Button):
        await self._pick(interaction, self.team_a, "A")

    @discord.ui.button(label="Time B", style=discord.ButtonStyle.primary, emoji="🔵")
    async def pick_b(self, interaction: discord.Interaction, button: Button):
        await self._pick(interaction, self.team_b, "B")

    async def _finish(self, interaction: Optional[discord.Interaction] = None):
        if self._finished:
            return
        
        self._finished = True
        self.stop()
        
        # Cancelar timeout task se existir
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None
        
        for child in self.children:
            child.disabled = True

        teams = {p: "team1" for p in self.team_a}
        teams.update({p: "team2" for p in self.team_b})
        
        result = await self.match_system.create_lobby_with_teams(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            author_id=self.team_a[0] if self.team_a else self.players[0],
            match_type=self.match_type,
            map_name=self.map_name,
            players=[int(p) for p in (self.team_a + self.team_b)],
            teams=teams,
        )

        embed = self.build_embed()
        if result.get("error"):
            embed.add_field(name="❌ Erro ao criar partida", value=result["error"], inline=False)
        else:
            embed.add_field(
                name="✅ Times definidos!",
                value=f"Partida `{result['match_id'][:6]}` criada — confira o ticket que foi aberto.",
                inline=False
            )

        try:
            if interaction is not None:
                await interaction.response.edit_message(embed=embed, view=self)
            elif self.message:
                await self.message.edit(embed=embed, view=self)
        except Exception:
            pass

    async def on_timeout(self):
        """Balanceia automaticamente se alguém demorar"""
        if self._finished:
            return
        
        pending = [p for p in self.players if p not in self.team_a and p not in self.team_b]
        if pending:
            random.shuffle(pending)
            for p in pending:
                if len(self.team_a) <= len(self.team_b):
                    self.team_a.append(p)
                else:
                    self.team_b.append(p)
        
        await self._finish(None)

    async def on_error(self, error: Exception, item: Any, interaction: discord.Interaction):
        """Tratamento de erro da view"""
        self._finished = True
        self.stop()


# ============================================================
# MATCH SYSTEM PRINCIPAL (OTIMIZADO)
# ============================================================

class MatchSystem:
    __slots__ = (
        "db", "config", "bot", "active_lobbies", "match_types", "_last_purge", "lobby_messages",
        "_semaphore", "_batch_queue", "_batch_lock", "_batch_task",
        "queues", "queued_players", "_last_queue_purge",
        "_lobby_creation_lock", "_pending_cleanup",
    )

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
        self._lobby_creation_lock = asyncio.Lock()
        self._pending_cleanup = False

        # Sistema de filas
        self.queues: Dict[str, dict] = {}
        self.queued_players: Dict[str, str] = {}
        self._last_queue_purge = 0.0

    # ============================================================
    # SISTEMA DE FILAS (SIMULTÂNEAS)
    # ============================================================

    @staticmethod
    def _queue_key(guild_id: str, channel_id: str, match_type: str, map_name: str) -> str:
        return f"{guild_id}:{channel_id}:{match_type}:{map_name}"

    def _purge_stale_queues(self):
        now = time.monotonic()
        if now - self._last_queue_purge < 120:
            return
        self._last_queue_purge = now
        
        dead = []
        for k, q in self.queues.items():
            if not q["players"] and now - q.get("_ts", now) > 1800:
                dead.append(k)
        
        for k in dead:
            self.queues.pop(k, None)
            
            # Limpar jogadores órfãos
            orphaned = [pkey for pkey, qkey in self.queued_players.items() if qkey == k]
            for pkey in orphaned:
                self.queued_players.pop(pkey, None)

    def get_queue_status(self, guild_id: str, channel_id: str, match_type: str, map_name: str) -> dict:
        key = self._queue_key(guild_id, channel_id, match_type, map_name)
        queue = self.queues.get(key)
        max_players = self.match_types.get(match_type, {}).get("max_players", 2)
        return {"count": len(queue["players"]) if queue else 0, "max": max_players}

    def is_player_busy(self, guild_id: str, user_id: str) -> bool:
        pkey = f"{guild_id}:{user_id}"
        if pkey in self.queued_players:
            return True
        
        uid = str(user_id)
        for lobby in self.active_lobbies.values():
            if (
                lobby.get("guild_id") == str(guild_id)
                and uid in lobby.get("players", [])
                and lobby.get("status") not in ("finished", "cancelled")
            ):
                return True
        return False

    async def join_queue(self, guild_id: str, channel_id: str, match_type: str, map_name: str, user_id: int) -> dict:
        self._purge_stale_queues()

        if match_type not in self.match_types:
            return {"error": "❌ Modo inválido."}

        uid = str(user_id)
        pkey = f"{guild_id}:{uid}"
        key = self._queue_key(guild_id, channel_id, match_type, map_name)

        if self.queued_players.get(pkey) == key:
            return {"error": "⏳ Você já está na fila desse mapa!"}

        # Verificar se está em partida ativa
        for lobby in self.active_lobbies.values():
            if (
                lobby.get("guild_id") == str(guild_id)
                and uid in lobby.get("players", [])
                and lobby.get("status") not in ("finished", "cancelled")
            ):
                return {"error": "❌ Você já está em uma partida em andamento!"}

        # Remover de fila antiga se existir
        old_key = self.queued_players.get(pkey)
        if old_key:
            old_queue = self.queues.get(old_key)
            if old_queue and uid in old_queue["players"]:
                old_queue["players"].remove(uid)
                if not old_queue["players"]:
                    old_queue["_ts"] = time.monotonic()

        queue = self.queues.setdefault(key, {
            "players": [], "_ts": time.monotonic(),
            "guild_id": str(guild_id), "channel_id": str(channel_id),
            "match_type": match_type, "map": map_name,
        })
        queue["players"].append(uid)
        queue["_ts"] = time.monotonic()
        self.queued_players[pkey] = key

        max_players = self.match_types[match_type]["max_players"]
        count = len(queue["players"])

        if count >= max_players:
            players = queue["players"][:max_players]
            queue["players"] = queue["players"][max_players:]
            for p in players:
                if self.queued_players.get(f"{guild_id}:{p}") == key:
                    self.queued_players.pop(f"{guild_id}:{p}", None)

            await self._pop_and_start(guild_id, channel_id, match_type, map_name, players)
            return {"joined": True, "popped": True, "count": len(queue["players"]), "max": max_players}

        return {"joined": True, "popped": False, "count": count, "max": max_players}

    async def leave_queue(self, guild_id: str, channel_id: str, match_type: str, map_name: str, user_id: int) -> dict:
        uid = str(user_id)
        pkey = f"{guild_id}:{uid}"
        key = self._queue_key(guild_id, channel_id, match_type, map_name)
        queue = self.queues.get(key)

        if not queue or uid not in queue["players"]:
            return {"error": "❌ Você não está na fila desse mapa."}

        queue["players"].remove(uid)
        if self.queued_players.get(pkey) == key:
            self.queued_players.pop(pkey, None)

        max_players = self.match_types.get(match_type, {}).get("max_players", 2)
        return {"left": True, "count": len(queue["players"]), "max": max_players}

    async def _pop_and_start(self, guild_id: str, channel_id: str, match_type: str, map_name: str, players: List[str]):
        if not self.match_types[match_type]["teams"]:
            teams = {players[0]: "team1", players[1]: "team2"}
            await self.create_lobby_with_teams(
                guild_id=guild_id,
                channel_id=channel_id,
                author_id=players[0],
                match_type=match_type,
                map_name=map_name,
                players=[int(p) for p in players],
                teams=teams,
            )
            return

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                channel = None

        settings = get_guild_settings(guild_id)
        timeout = int(settings.get("match_settings", {}).get("team_select_timeout", 180))

        view = SelfTeamSelectView(
            match_system=self,
            guild_id=guild_id,
            channel_id=channel_id,
            match_type=match_type,
            map_name=map_name,
            players=players,
            timeout=timeout,
        )
        embed = view.build_embed()

        if channel:
            try:
                msg = await channel.send(
                    content=" ".join(f"<@{p}>" for p in players[:10]),
                    embed=embed,
                    view=view,
                )
                view.message = msg
            except Exception:
                pass

    async def check_rate_limit(self, key: str, max_per_second: int = 4) -> bool:
        return await _rate_limiter.check(key, "queue_action")

    # ============================================================
    # LIMPEZA DE LOBBIES
    # ============================================================

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

    # ============================================================
    # BATCH UPDATES (CORRIGIDO)
    # ============================================================

    async def _batch_update_stats(self, updates: List[dict]):
        if not updates:
            return
        
        async with self._batch_lock:
            self._batch_queue.extend(updates)
            if len(self._batch_queue) >= 10:
                await self._flush_batch()
    
    async def _flush_batch(self):
        """Processa batch de updates fora do lock"""
        if not self._batch_queue:
            return
        
        # Copiar e limpar dentro do lock
        async with self._batch_lock:
            updates = self._batch_queue.copy()
            self._batch_queue.clear()
        
        # Processar fora do lock
        for update in updates:
            try:
                update_player_stats(**update)
            except Exception:
                pass
        
        if len(updates) > 3:
            gc.collect()

    # ============================================================
    # CRIAÇÃO DE LOBBY (COM LOCK PARA EVITAR CONCORRÊNCIA)
    # ============================================================

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
        # Rate limit por criador
        if not await _rate_limiter.check(str(author_id), "create_lobby"):
            return {"error": "⏳ Muitas partidas criadas. Aguarde um momento."}
        
        # Lock para evitar criação simultânea do mesmo lobby
        async with self._lobby_creation_lock:
            self._purge_stale()

            settings = get_guild_settings(guild_id)

            if match_type not in self.match_types:
                return {"error": f"❌ Tipos: {', '.join(self.match_types)}"}

            try:
                gid = int(guild_id)
            except (ValueError, TypeError):
                return {"error": "❌ Guild ID inválido"}

            # Validar apostas
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
                
                # Validar saldo de todos os jogadores
                for pid in players:
                    try:
                        if get_player_balance(gid, int(pid)) < bet_amount:
                            return {"error": f"❌ <@{pid}> não tem saldo suficiente!"}
                    except (ValueError, TypeError):
                        return {"error": f"❌ Jogador inválido: {pid}"}

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
            if not match_id:
                return {"error": "❌ Erro ao criar partida no banco"}

            # Deduzir apostas
            if is_betting and bet_amount > 0:
                for pid in players_str:
                    try:
                        uid = int(pid)
                        if not remove_player_balance(gid, uid, bet_amount, f"Aposta {match_id[:6]}"):
                            # Reembolsar todos
                            for refund_pid in players_str:
                                if refund_pid != pid:
                                    try:
                                        add_player_balance(gid, int(refund_pid), bet_amount, f"Reembolso {match_id[:6]}")
                                    except Exception:
                                        pass
                            return {"error": f"❌ Jogador <@{pid}> não tem saldo suficiente!"}
                    except (ValueError, TypeError):
                        for refund_pid in players_str:
                            try:
                                add_player_balance(gid, int(refund_pid), bet_amount, f"Reembolso {match_id[:6]}")
                            except Exception:
                                pass
                        return {"error": f"❌ Jogador inválido: {pid}"}

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

    # ============================================================
    # TICKET E NOTIFICAÇÕES
    # ============================================================

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
            try:
                member = guild.get_member(int(pid))
                if member:
                    overwrites[member] = discord.PermissionOverwrite(
                        read_messages=True, send_messages=True, view_channel=True
                    )
            except (ValueError, TypeError):
                continue

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
            await self._notify_free_mediators(guild, channel, match_data["guild_id"], lobby["players"])
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

    async def _notify_free_mediators(self, guild: discord.Guild, channel: discord.TextChannel, guild_id: str, players: List[str]):
        players_set = set(str(p) for p in players)
        role_ids = get_mediator_roles(guild_id)

        if not role_ids:
            await channel.send("⚠️ Nenhum cargo de mediador configurado! Use o comando de configuração para definir um.")
            return

        free_members = []
        mentioned_roles = []
        for role_id in role_ids:
            try:
                role = guild.get_role(int(role_id))
                if not role:
                    continue
                mentioned_roles.append(role)
                for member in role.members:
                    if str(member.id) not in players_set and member not in free_members:
                        free_members.append(member)
            except (ValueError, TypeError):
                continue

        if mentioned_roles:
            role_mentions = " ".join(r.mention for r in mentioned_roles[:5])
            await channel.send(
                f"🔔 {role_mentions} — Partida pronta! "
                "(mediadores que estão jogando não podem atuar aqui)"
            )

        if not free_members:
            await channel.send(
                "⚠️ Todos os mediadores disponíveis estão jogando. "
                "Peça a um administrador para mediar."
            )
            return

        for member in free_members[:10]:
            try:
                await member.send(
                    f"🎫 Nova partida para mediar em {guild.name}: {channel.mention}"
                )
            except Exception:
                pass

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
            value="\n".join(f"👤 <@{p}>" for p in team_a_players[:10]) or "Vazio",
            inline=True
        )
        embed.add_field(
            name=f"🔵 {team2_name}",
            value="\n".join(f"👤 <@{p}>" for p in team_b_players[:10]) or "Vazio",
            inline=True
        )
        
        embed.add_field(
            name="📋 Instruções",
            value="Clique no botão do time vencedor abaixo para finalizar.",
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
        
        for pid in lobby["players"][:20]:
            try:
                user = await self.bot.fetch_user(int(pid))
                await user.send(text)
            except Exception:
                pass

    # ============================================================
    # CANCELAMENTO DE MATCH
    # ============================================================

    async def cancel_match(self, match_id: str) -> bool:
        lobby = self.active_lobbies.get(match_id)
        if not lobby:
            for mid, data in list(self.active_lobbies.items()):
                if mid.startswith(match_id) or mid == match_id:
                    match_id, lobby = mid, data
                    break
        if not lobby:
            return False

        guild_id = lobby.get("guild_id")

        if guild_id and lobby.get("is_betting"):
            bet = int(lobby.get("bet_amount", 0))
            if bet > 0:
                try:
                    gid = int(guild_id)
                    for pid in lobby.get("players", []):
                        try:
                            add_player_balance(gid, int(pid), bet, f"Reembolso {match_id[:6]}")
                        except (ValueError, TypeError):
                            continue
                except (ValueError, TypeError):
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
        
        # Tentar buscar do banco
        match = get_match(match_id, False)
        if match:
            return match
        match = get_match(match_id, True)
        return match

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
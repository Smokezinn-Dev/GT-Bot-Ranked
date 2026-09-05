# ============================================================
# MAIN.PY - GT BOT RANKED (COMPLETO - SEM DUPLICATAS)
# ============================================================

import discord
from discord.ext import commands
import asyncio
import logging
import sys
import gc
from datetime import datetime

from config import DISCORD_TOKEN, PREFIX, EMBED_COLOR, EMBED_FOOTER, MATCH_TYPES, GUILD_ID
from database import init_db, get_connection, get_player_rank_stats, get_guild_settings
from match_system import MatchSystem, MapSelectView, TicketPanelView
from ranking_system import RankingSystem, RankingView
from admin_commands import AdminCommands

logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("GTRanked")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True


class RankedBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )
        self.start_time = datetime.utcnow()
        self.match_system = None
        self.ranking_system = None

    async def setup_hook(self):
        db = init_db()

        self.match_system = MatchSystem(db, sys.modules["config"], self)
        self.ranking_system = RankingSystem(db, sys.modules["config"], self)

        if self.get_cog("AdminCommands") is None:
            await self.add_cog(AdminCommands(self, self.match_system, self.ranking_system))

        try:
            if GUILD_ID:
                await self.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
            else:
                await self.tree.sync()
        except Exception as e:
            logger.error(f"Sync: {e}")

        gc.collect()

    async def on_ready(self):
        logger.info(f"✅ {self.user} | Guilds: {len(self.guilds)}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{PREFIX}help | Ranked"
            )
        )
        gc.collect()


bot = RankedBot()


# ============================================================
# COMANDO: CRIAR PARTIDA RANKED COM DROPDOWN
# ============================================================

@bot.command(name="criar")
async def criar_cmd(ctx, match_type: str = "1v1"):
    """Cria uma partida com dropdown de mapas. Ex: %criar 1v1"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    
    settings = get_guild_settings(str(ctx.guild.id))
    maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
    
    map_list = []
    for map_name in maps:
        count = bot.match_system.get_queue_count(str(ctx.guild.id), map_name, match_type)
        emojis = {
            "Arena": "🏰", "Castelo": "🏯", "Floresta": "🌲", "Deserto": "🏜️",
            "Vulcão": "🌋", "Tundra": "❄️", "Cidade": "🌃", "Ilha": "🏝️"
        }
        emoji = emojis.get(map_name, "🗺️")
        map_list.append(f"{emoji} `{map_name}` — 👥 **{count}** jogador(es) na fila")
    
    embed = discord.Embed(
        title="🗺️ Criar Nova Partida",
        description=f"**Tipo:** {match_type}\n**Modo:** Ranked",
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="📊 Mapas Disponíveis (filas por mapa)",
        value="\n".join(map_list) or "Nenhum mapa disponível",
        inline=False
    )
    
    embed.add_field(
        name="📋 Como funciona",
        value="1. Selecione o mapa no dropdown abaixo\n2. Confirme a criação\n3. Compartilhe o ID com outros jogadores",
        inline=False
    )
    embed.set_footer(text=f"Use {PREFIX}join <ID> para entrar na partida")
    
    view = MapSelectView(
        match_system=bot.match_system,
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=match_type,
        is_betting=False,
        bet_amount=0
    )
    
    await ctx.send(embed=embed, view=view)


# ============================================================
# COMANDO: CRIAR PARTIDA APOSTADA COM DROPDOWN
# ============================================================

@bot.command(name="criaraposta")
async def criar_aposta_cmd(ctx, match_type: str = "1v1", bet: int = 100):
    """Cria uma partida apostada com dropdown de mapas. Ex: %criaraposta 1v1 500"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    if bet < 1:
        return await ctx.send("❌ Aposta inválida.")
    
    settings = get_guild_settings(str(ctx.guild.id))
    maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
    
    map_list = []
    for map_name in maps:
        count = bot.match_system.get_queue_count(str(ctx.guild.id), map_name, match_type)
        emojis = {
            "Arena": "🏰", "Castelo": "🏯", "Floresta": "🌲", "Deserto": "🏜️",
            "Vulcão": "🌋", "Tundra": "❄️", "Cidade": "🌃", "Ilha": "🏝️"
        }
        emoji = emojis.get(map_name, "🗺️")
        map_list.append(f"{emoji} `{map_name}` — 👥 **{count}** jogador(es) na fila")
    
    embed = discord.Embed(
        title="💰 Criar Partida Apostada",
        description=f"**Tipo:** {match_type}\n**Aposta:** {bet}",
        color=0xffd700,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="📊 Mapas Disponíveis (filas por mapa)",
        value="\n".join(map_list) or "Nenhum mapa disponível",
        inline=False
    )
    
    embed.add_field(
        name="📋 Como funciona",
        value="1. Selecione o mapa no dropdown abaixo\n2. Confirme a criação\n3. Compartilhe o ID com outros jogadores",
        inline=False
    )
    embed.set_footer(text=f"Use {PREFIX}join <ID> para entrar na partida")
    
    view = MapSelectView(
        match_system=bot.match_system,
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=match_type,
        is_betting=True,
        bet_amount=bet
    )
    
    await ctx.send(embed=embed, view=view)


# ============================================================
# COMANDO: RANKING COM BOTÃO ATUALIZAR
# ============================================================

@bot.command(name="rank")
async def rank_cmd(ctx, match_type: str = "1v1"):
    """Mostra ranking com botão de atualizar. Ex: %rank 1v1"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    
    embed = await bot.ranking_system.generate_ranking_embed(str(ctx.guild.id), match_type)
    view = RankingView(bot.ranking_system, str(ctx.guild.id), match_type)
    await ctx.send(embed=embed, view=view)


# ============================================================
# COMANDO: ESTATÍSTICAS DO JOGADOR
# ============================================================

@bot.command(name="stats", aliases=["mystats", "perfil"])
async def stats_cmd(ctx, member: discord.Member = None):
    """Estatísticas de um jogador."""
    member = member or ctx.author
    embed = await bot.ranking_system.get_player_stats_embed(
        str(ctx.guild.id), str(member.id), member
    )
    await ctx.send(embed=embed)


# ============================================================
# COMANDO: FILA
# ============================================================

@bot.command(name="queue", aliases=["fila"])
async def queue_cmd(ctx, action: str = "status", match_type: str = "1v1"):
    """Sistema de fila com embed. %queue 1v1 | %queue status"""
    if action.lower() in ("status", "s"):
        settings = get_guild_settings(str(ctx.guild.id))
        maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
        
        embed = discord.Embed(
            title="📋 Filas por Mapa",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        for map_name in maps:
            count = bot.match_system.get_queue_count(str(ctx.guild.id), map_name)
            emojis = {
                "Arena": "🏰", "Castelo": "🏯", "Floresta": "🌲", "Deserto": "🏜️",
                "Vulcão": "🌋", "Tundra": "❄️", "Cidade": "🌃", "Ilha": "🏝️"
            }
            emoji = emojis.get(map_name, "🗺️")
            embed.add_field(
                name=f"{emoji} {map_name}",
                value=f"👥 **{count}** jogador(es) na fila",
                inline=True
            )
        
        embed.set_footer(text=f"Use {PREFIX}criar 1v1 para entrar na fila")
        return await ctx.send(embed=embed)

    mt = action if action in MATCH_TYPES else match_type
    if mt not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")

    settings = get_guild_settings(str(ctx.guild.id))
    maps = settings.get("ranked", {}).get("maps", ["Arena"])
    map_name = maps[0] if maps else "Arena"

    result = await bot.match_system.create_lobby(
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=mt,
        map_name=map_name,
        is_betting=False,
    )
    if result.get("error"):
        return await ctx.send(result["error"])
    
    embed = discord.Embed(
        title="✅ Lobby Criado!",
        description=f"**ID:** `{result['match_id'][:6]}`\n**Tipo:** {mt}\n**Mapa:** {map_name}",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text=f"Use {PREFIX}join {result['match_id'][:6]} para entrar")
    await ctx.send(embed=embed)


# ============================================================
# COMANDO: ENTRAR NA PARTIDA
# ============================================================

@bot.command(name="join")
async def join_cmd(ctx, match_id: str, team: str = None):
    """Entra em uma partida. Ex: %join abc123"""
    result = await bot.match_system.join_lobby(match_id, str(ctx.author.id), team)
    if result.get("error"):
        return await ctx.send(result["error"])
    if result.get("match_started"):
        embed = discord.Embed(
            title="🎯 Partida Iniciada!",
            description="Ticket criado para os mediadores.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        return await ctx.send(embed=embed)
    
    embed = discord.Embed(
        description=f"✅ Você entrou! Jogadores: {result.get('player_count')}",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


# ============================================================
# COMANDOS ADMIN
# ============================================================

@bot.command(name="ranked")
@commands.has_permissions(administrator=True)
async def ranked_create(ctx, match_type: str = "1v1", map_name: str = "Arena"):
    """Cria RANKED (admin). Ex: %ranked 1v1 Arena"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    result = await bot.match_system.create_lobby(
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=match_type,
        map_name=map_name,
        is_betting=False,
    )
    if result.get("error"):
        return await ctx.send(result["error"])
    embed = discord.Embed(
        title="🏆 Partida Ranked Criada!",
        description=f"**ID:** `{result['match_id'][:6]}`\n**Tipo:** {match_type}\n**Mapa:** {map_name}",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    await ctx.send(embed=embed)


@bot.command(name="apostado")
@commands.has_permissions(administrator=True)
async def apostado_create(ctx, match_type: str = "1v1", bet: int = 100, map_name: str = "Arena"):
    """Cria APOSTADO (admin). Ex: %apostado 1v1 500 Arena"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    if bet < 1:
        return await ctx.send("❌ Aposta inválida.")
    result = await bot.match_system.create_lobby(
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=match_type,
        map_name=map_name,
        is_betting=True,
        bet_amount=bet,
    )
    if result.get("error"):
        return await ctx.send(result["error"])
    embed = discord.Embed(
        title="💰 Partida Apostada Criada!",
        description=f"**ID:** `{result['match_id'][:6]}`\n**Tipo:** {match_type}\n**Mapa:** {map_name}\n**Aposta:** {bet}",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    await ctx.send(embed=embed)


@bot.command(name="ticketpanel")
@commands.has_permissions(administrator=True)
async def ticket_panel(ctx):
    """Cria um painel de tickets para mediadores"""
    settings = get_guild_settings(str(ctx.guild.id))
    maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
    
    map_list = []
    for map_name in maps:
        count = bot.match_system.get_queue_count(str(ctx.guild.id), map_name)
        emojis = {
            "Arena": "🏰", "Castelo": "🏯", "Floresta": "🌲", "Deserto": "🏜️",
            "Vulcão": "🌋", "Tundra": "❄️", "Cidade": "🌃", "Ilha": "🏝️"
        }
        emoji = emojis.get(map_name, "🗺️")
        map_list.append(f"{emoji} `{map_name}` — 👥 **{count}** jogador(es) na fila")
    
    embed = discord.Embed(
        title="🎫 Painel de Tickets - GT Ranked",
        description=(
            "**Bem-vindo ao sistema de tickets!**\n\n"
            "Clique no botão abaixo para criar uma nova partida.\n"
            "Você poderá selecionar:\n"
            "• 🗺️ O mapa da partida\n"
            "• 🎮 O tipo de partida (1v1, 2v2, 3v3)\n"
            "• 💰 Se é Ranked ou Apostado\n"
            "• 💵 O valor da aposta (se apostado)"
        ),
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name="📊 Filas por Mapa",
        value="\n".join(map_list) or "Nenhum mapa disponível",
        inline=False
    )
    embed.add_field(
        name="📋 Requisitos",
        value="• Apenas **mediadores** podem abrir tickets\n• A partida será criada no canal atual",
        inline=False
    )
    embed.set_footer(text="GT Ranked System v3.0")
    
    view = TicketPanelView(bot.match_system, str(ctx.guild.id))
    await ctx.send(embed=embed, view=view)


# ============================================================
# COMANDOS ÚTEIS
# ============================================================

@bot.command(name="ping")
async def ping_cmd(ctx):
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"**Latência:** {round(bot.latency * 1000, 1)}ms",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    await ctx.send(embed=embed)


@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="📖 GT Bot Ranked — Comandos",
        description="Sistema completo de partidas rankeadas e apostadas!",
        color=EMBED_COLOR,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="🎮 Jogador",
        value=(
            f"`{PREFIX}rank [1v1|2v2|3v3]` — Ranking com botão atualizar\n"
            f"`{PREFIX}stats [@user]` — Estatísticas do jogador\n"
            f"`{PREFIX}queue 1v1` — Entrar na fila\n"
            f"`{PREFIX}queue status` — Status das filas por mapa\n"
            f"`{PREFIX}join <id> [team1|team2]` — Entrar na partida\n"
            f"`{PREFIX}bal` — Ver saldo\n"
            f"`{PREFIX}criar 1v1` — Criar partida com dropdown de mapas 🆕\n"
            f"`{PREFIX}criaraposta 1v1 500` — Criar apostada com dropdown 🆕"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Admin",
        value=(
            f"`{PREFIX}ranked 1v1 Arena` — Criar partida ranked\n"
            f"`{PREFIX}apostado 1v1 500` — Criar partida apostada\n"
            f"`{PREFIX}ticketpanel` — Painel de tickets para mediadores 🆕\n"
            f"`{PREFIX}config` — Configurações do servidor\n"
            f"`{PREFIX}config ranked maps [...]` — Configurar mapas 🆕\n"
            f"`{PREFIX}config customization embed_color 0xff6b00` — Configurar cores 🆕\n"
            f"`{PREFIX}setmediator @cargo` — Definir mediador\n"
            f"`{PREFIX}give / take / setbalance` — Gerenciar economia\n"
            f"`{PREFIX}cancelmatch <id>` — Cancelar partida\n"
            f"`{PREFIX}distributetop 1v1` — Distribuir prêmios top"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📊 Filas por Mapa",
        value=(
            f"O sistema mantém filas separadas por **cada mapa**!\n"
            f"Use `{PREFIX}queue status` para ver quantos jogadores estão em cada mapa.\n"
            f"Os mapas são **100% personalizáveis** via `{PREFIX}config`"
        ),
        inline=False
    )
    
    embed.set_footer(text=EMBED_FOOTER)
    await ctx.send(embed=embed)


# ============================================================
# START
# ============================================================

async def main():
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN não definido!")
        sys.exit(1)
    try:
        async with bot:
            await bot.start(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("❌ Token inválido!")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERRO FATAL: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

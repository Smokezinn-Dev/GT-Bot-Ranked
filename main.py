# ============================================================
# MAIN.PY - GT BOT RANKED (COMPLETO + OTIMIZAÇÕES)
# ============================================================

import discord
from discord.ext import commands
import asyncio
import logging
import sys
import gc
import os
import signal
from datetime import datetime

from config import DISCORD_TOKEN, PREFIX, EMBED_COLOR, EMBED_FOOTER, MATCH_TYPES, GUILD_ID
from database import init_db, get_connection, get_player_rank_stats, get_guild_settings, clear_all_caches, check_db_health, get_cache_stats
from match_system import MatchSystem, MapSelectModal, TeamSelectView, MediatorMatchView
from ranking_system import RankingSystem, RankingView
from admin_commands import AdminCommands
from optimizer import start_optimizer, stop_optimizer, force_gc

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("GTRanked")

# ============================================================
# EVENT LOOP OTIMIZADO
# ============================================================

class OptimizedEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """Policy otimizada para Railway"""
    def get_event_loop(self):
        loop = super().get_event_loop()
        if hasattr(loop, 'set_debug'):
            loop.set_debug(False)
        if hasattr(loop, 'slow_callback_duration'):
            loop.slow_callback_duration = 0.5
        return loop

asyncio.set_event_loop_policy(OptimizedEventLoopPolicy())

# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# ============================================================
# BOT PRINCIPAL
# ============================================================

class RankedBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            max_messages=1000,
        )
        self.start_time = datetime.utcnow()
        self.match_system = None
        self.ranking_system = None
        self._cleanup_task = None
        self._memory_task = None
        self._gc_threshold = (700, 10, 10)
        gc.set_threshold(*self._gc_threshold)
        self._memory_limit_mb = 450

    async def setup_hook(self):
        db = init_db()

        self.match_system = MatchSystem(db, sys.modules["config"], self)
        self.ranking_system = RankingSystem(db, sys.modules["config"], self)

        if self.get_cog("AdminCommands") is None:
            await self.add_cog(AdminCommands(self, self.match_system, self.ranking_system))

        if GUILD_ID and os.getenv("RAILWAY_ENVIRONMENT") == "production":
            try:
                await self.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
                logger.info("✅ Slash commands synced")
            except Exception as e:
                logger.error(f"Sync: {e}")

        self._cleanup_task = self.loop.create_task(self._cleanup_loop())
        self._memory_task = self.loop.create_task(self._memory_monitor())
        await start_optimizer()

        gc.collect()

    async def _cleanup_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(300)
            try:
                clear_all_caches()
                gc.collect()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    async def _memory_monitor(self):
        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(60)
            try:
                import psutil
                mem = psutil.Process().memory_info()
                mem_mb = mem.rss / 1024 / 1024
                if mem_mb > self._memory_limit_mb:
                    gc.collect()
                    gc.collect()
                    await asyncio.sleep(0.1)
                    clear_all_caches()
                    logger.warning(f"🧹 Memory cleanup forced: {mem_mb:.1f}MB")
            except Exception:
                pass

    async def on_ready(self):
        logger.info(f"✅ {self.user} | Guilds: {len(self.guilds)}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{PREFIX}help | Ranked"
            )
        )
        gc.collect()

    async def on_error(self, event, *args, **kwargs):
        pass

    async def close(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._memory_task:
            self._memory_task.cancel()
        await stop_optimizer()
        await super().close()

bot = RankedBot()

# ============================================================
# COMANDOS PRINCIPAIS
# ============================================================

@bot.command(name="criar")
async def criar_cmd(ctx, match_type: str = "1v1"):
    """Cria uma partida com seleção de mapa e times. Ex: %criar 1v1"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    
    settings = get_guild_settings(str(ctx.guild.id))
    maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
    
    embed = discord.Embed(
        title="🗺️ Criar Nova Partida",
        description=f"**Tipo:** {match_type}\n**Modo:** Ranked\n\nDigite o nome do mapa no formulário abaixo.",
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="📋 Mapas Disponíveis",
        value="\n".join([f"• {m}" for m in maps]),
        inline=False
    )
    
    embed.add_field(
        name="📌 Como funciona",
        value="1. Digite o nome do mapa\n2. Selecione os membros para cada time\n3. A partida será criada automaticamente",
        inline=False
    )
    
    modal = MapSelectModal(
        match_system=bot.match_system,
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=match_type,
        is_betting=False,
        bet_amount=0
    )
    
    await ctx.send(embed=embed)
    await ctx.send("📝 Por favor, digite o nome do mapa no formulário abaixo:", view=None)
    await ctx.author.send(modal)


@bot.command(name="criaraposta")
async def criar_aposta_cmd(ctx, match_type: str = "1v1", bet: int = 100):
    """Cria uma partida apostada com seleção de mapa e times. Ex: %criaraposta 1v1 500"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    if bet < 1:
        return await ctx.send("❌ Aposta inválida.")
    
    settings = get_guild_settings(str(ctx.guild.id))
    maps = settings.get("ranked", {}).get("maps", ["Arena", "Castelo", "Floresta", "Deserto"])
    
    embed = discord.Embed(
        title="💰 Criar Partida Apostada",
        description=f"**Tipo:** {match_type}\n**Aposta:** {bet}\n\nDigite o nome do mapa no formulário abaixo.",
        color=0xffd700,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="📋 Mapas Disponíveis",
        value="\n".join([f"• {m}" for m in maps]),
        inline=False
    )
    
    embed.add_field(
        name="📌 Como funciona",
        value="1. Digite o nome do mapa\n2. Selecione os membros para cada time\n3. A partida será criada automaticamente",
        inline=False
    )
    
    modal = MapSelectModal(
        match_system=bot.match_system,
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=match_type,
        is_betting=True,
        bet_amount=bet
    )
    
    await ctx.send(embed=embed)
    await ctx.send("📝 Por favor, digite o nome do mapa no formulário abaixo:")
    await ctx.author.send(modal)


@bot.command(name="rank")
async def rank_cmd(ctx, match_type: str = "1v1"):
    """Mostra ranking com botão de atualizar. Ex: %rank 1v1"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    
    embed = await bot.ranking_system.generate_ranking_embed(str(ctx.guild.id), match_type)
    view = RankingView(bot.ranking_system, str(ctx.guild.id), match_type)
    await ctx.send(embed=embed, view=view)


@bot.command(name="stats", aliases=["mystats", "perfil"])
async def stats_cmd(ctx, member: discord.Member = None):
    """Estatísticas de um jogador."""
    member = member or ctx.author
    embed = await bot.ranking_system.get_player_stats_embed(
        str(ctx.guild.id), str(member.id), member
    )
    await ctx.send(embed=embed)


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


@bot.command(name="bal", aliases=["saldo"])
async def bal_cmd(ctx, member: discord.Member = None):
    """Ver saldo de um jogador."""
    from database import get_player_balance
    member = member or ctx.author
    bal = get_player_balance(ctx.guild.id, member.id)
    embed = discord.Embed(
        description=f"💰 {member.display_name}: **{bal}**",
        color=0x00ff00
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
    
    view = TeamSelectView(
        match_system=bot.match_system,
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=match_type,
        map_name=map_name,
        is_betting=False,
        bet_amount=0
    )
    
    embed = discord.Embed(
        title="👥 Seleção de Times",
        description=f"**Mapa:** {map_name}\n**Modo:** {match_type}\n\nSelecione os membros para cada time:",
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    
    max_players = bot.match_system.match_types[match_type]["max_players"]
    embed.add_field(
        name="📋 Instruções",
        value=f"Selecione **{max_players}** jogadores no total.\nTime A: {max_players//2} jogadores\nTime B: {max_players//2} jogadores",
        inline=False
    )
    
    await ctx.send(embed=embed, view=view)


@bot.command(name="apostado")
@commands.has_permissions(administrator=True)
async def apostado_create(ctx, match_type: str = "1v1", bet: int = 100, map_name: str = "Arena"):
    """Cria APOSTADO (admin). Ex: %apostado 1v1 500 Arena"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    if bet < 1:
        return await ctx.send("❌ Aposta inválida.")
    
    view = TeamSelectView(
        match_system=bot.match_system,
        guild_id=str(ctx.guild.id),
        channel_id=str(ctx.channel.id),
        author_id=str(ctx.author.id),
        match_type=match_type,
        map_name=map_name,
        is_betting=True,
        bet_amount=bet
    )
    
    embed = discord.Embed(
        title="💰 Seleção de Times - Apostado",
        description=f"**Mapa:** {map_name}\n**Modo:** {match_type}\n**Aposta:** {bet}\n\nSelecione os membros para cada time:",
        color=0xffd700,
        timestamp=datetime.utcnow()
    )
    
    max_players = bot.match_system.match_types[match_type]["max_players"]
    embed.add_field(
        name="📋 Instruções",
        value=f"Selecione **{max_players}** jogadores no total.\nTime A: {max_players//2} jogadores\nTime B: {max_players//2} jogadores",
        inline=False
    )
    
    await ctx.send(embed=embed, view=view)


@bot.command(name="ticketpanel")
@commands.has_permissions(administrator=True)
async def ticket_panel(ctx):
    """Cria um painel de tickets para mediadores"""
    embed = discord.Embed(
        title="🎫 Painel de Tickets - GT Ranked",
        description=(
            "**Bem-vindo ao sistema de tickets!**\n\n"
            "Use o comando `%criar` para criar uma nova partida.\n"
            "O sistema vai guiar você por:\n"
            "• 🗺️ Seleção do mapa\n"
            "• 👥 Seleção dos times\n"
            "• 🎫 Ticket automático para mediadores"
        ),
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name="📋 Comandos Rápidos",
        value=f"`{PREFIX}criar 1v1` — Criar partida ranked\n`{PREFIX}criaraposta 1v1 500` — Criar partida apostada",
        inline=False
    )
    embed.set_footer(text="GT Ranked System v3.0")
    
    await ctx.send(embed=embed)


# ============================================================
# COMANDOS DE OTIMIZAÇÃO
# ============================================================

@bot.command(name="health")
@commands.is_owner()
async def health_cmd(ctx):
    """Health check para Railway"""
    import psutil
    import os
    
    mem = psutil.Process(os.getpid()).memory_info()
    cache_stats = get_cache_stats()
    
    embed = discord.Embed(
        title="🩺 Health Check",
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name="📊 Memória",
        value=f"**RSS:** {mem.rss / 1024 / 1024:.1f} MB\n**VMS:** {mem.vms / 1024 / 1024:.1f} MB",
        inline=True
    )
    embed.add_field(
        name="⏱️ Uptime",
        value=f"{(datetime.utcnow() - bot.start_time).total_seconds() / 3600:.1f}h",
        inline=True
    )
    embed.add_field(
        name="🔄 GC",
        value=f"**Contagem:** {gc.get_count()}",
        inline=True
    )
    embed.add_field(
        name="📦 Cache Stats",
        value=f"**Settings:** {cache_stats['settings']['size']}\n**Balance:** {cache_stats['balance']['size']}\n**Stats:** {cache_stats['stats']['size']}",
        inline=False
    )
    embed.add_field(
        name="📈 Cache Hit Rate",
        value=f"**Settings:** {cache_stats['settings']['hit_rate']}\n**Balance:** {cache_stats['balance']['hit_rate']}\n**Stats:** {cache_stats['stats']['hit_rate']}",
        inline=False
    )
    await ctx.send(embed=embed)


@bot.command(name="gc")
@commands.is_owner()
async def force_gc_cmd(ctx):
    """Força garbage collection"""
    before = gc.get_count()
    force_gc()
    after = gc.get_count()
    await ctx.send(f"🧹 GC executado!\nAntes: {before}\nDepois: {after}")


@bot.command(name="mem")
@commands.is_owner()
async def memory_cmd(ctx):
    """Mostra uso de memória detalhado"""
    import psutil
    import os
    
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    gc_stats = gc.get_stats()
    cache_stats = get_cache_stats()
    
    embed = discord.Embed(
        title="📊 Uso de Memória",
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name="🧠 RAM",
        value=f"**RSS:** {mem.rss / 1024 / 1024:.1f} MB\n**VMS:** {mem.vms / 1024 / 1024:.1f} MB\n**USS:** {mem.uss / 1024 / 1024:.1f} MB",
        inline=True
    )
    embed.add_field(
        name="🔄 Garbage Collector",
        value=f"**Contagem:** {gc.get_count()}\n**Coleções:** {sum(g['collections'] for g in gc_stats)}",
        inline=True
    )
    embed.add_field(
        name="📦 Cache",
        value=f"**Settings:** {cache_stats['settings']['size']}\n**Balance:** {cache_stats['balance']['size']}\n**Stats:** {cache_stats['stats']['size']}",
        inline=True
    )
    embed.add_field(
        name="📈 Hit Rate",
        value=f"**Settings:** {cache_stats['settings']['hit_rate']}\n**Balance:** {cache_stats['balance']['hit_rate']}\n**Stats:** {cache_stats['stats']['hit_rate']}",
        inline=True
    )
    embed.add_field(
        name="🏓 Lobbies",
        value=f"**Ativos:** {len(bot.match_system.active_lobbies)}",
        inline=True
    )
    await ctx.send(embed=embed)


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
            f"`{PREFIX}rank [1v1|2v2|3v3|4v4]` — Ranking com botão atualizar\n"
            f"`{PREFIX}stats [@user]` — Estatísticas do jogador\n"
            f"`{PREFIX}join <id>` — Entrar na partida\n"
            f"`{PREFIX}bal` — Ver saldo"
        ),
        inline=False
    )
    
    embed.add_field(
        name="👥 Criar Partida (com seleção de times)",
        value=(
            f"`{PREFIX}criar 1v1` — Criar partida ranked\n"
            f"`{PREFIX}criar 2v2` — Criar partida ranked em duplas\n"
            f"`{PREFIX}criar 3v3` — Criar partida ranked em trio\n"
            f"`{PREFIX}criar 4v4` — Criar partida ranked em quarteto\n"
            f"`{PREFIX}criaraposta 1v1 500` — Criar partida apostada"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Admin",
        value=(
            f"`{PREFIX}ranked 1v1 Arena` — Criar ranked direto\n"
            f"`{PREFIX}apostado 1v1 500 Arena` — Criar apostado direto\n"
            f"`{PREFIX}ticketpanel` — Painel de informações\n"
            f"`{PREFIX}config` — Configurações do servidor\n"
            f"`{PREFIX}config ranked maps [...]` — Configurar mapas\n"
            f"`{PREFIX}setmediator @cargo` — Definir mediador\n"
            f"`{PREFIX}give / take / setbalance` — Gerenciar economia"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔧 Otimização",
        value=(
            f"`{PREFIX}health` — Health check\n"
            f"`{PREFIX}mem` — Uso de memória\n"
            f"`{PREFIX}gc` — Forçar GC"
        ),
        inline=False
    )
    
    embed.set_footer(text=EMBED_FOOTER)
    await ctx.send(embed=embed)


# ============================================================
# START - COM SIGNAL HANDLER
# ============================================================

async def main():
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN não definido!")
        sys.exit(1)
    
    def signal_handler(sig, frame):
        asyncio.create_task(bot.close())
        print("\n🛑 Shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
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
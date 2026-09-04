# ============================================================
# MAIN.PY - SISTEMA RANKED/APOSTADO (ATUALIZADO)
# ============================================================

import discord
from discord.ext import commands
import asyncio
import logging
import sys
import gc
import time
from datetime import datetime

try:
    from config import DISCORD_TOKEN, EMBED_COLOR, EMBED_FOOTER
except ImportError:
    DISCORD_TOKEN = "MTU0NTM5NDAzMjQyMTYzNDA4MQ.G50Z0a.Dc-PkgeAOQgpHYK4zhYph_VkuiEyUdtbIBlf7k"
    EMBED_COLOR = 0x00ff00
    EMBED_FOOTER = "Rank System v3.0"

from database import init_db
from match_system import MatchSystem
from ranking_system import RankingSystem
from admin_commands import AdminCommands

# ============================================================
# LOGGING MÍNIMO
# ============================================================

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("RankBot")

# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# ============================================================
# BOT
# ============================================================

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============================================================
# INICIALIZAÇÃO
# ============================================================

print("🚀 Inicializando sistemas...")
db = init_db()
match_system = MatchSystem(db, None, bot)
ranking_system = RankingSystem(db, None, bot)
admin_commands = AdminCommands(bot, db, None, match_system, ranking_system)

# ============================================================
# EVENTOS
# ============================================================

@bot.event
async def on_ready():
    print("="*60)
    print(f"✅ BOT CONECTADO: {bot.user}")
    print(f"📡 ID: {bot.user.id}")
    print(f"📊 SERVIDORES: {len(bot.guilds)}")
    print("="*60)
    
    # Inicia a task de limpeza do match_system
    match_system.start_cleanup_task()
    
    await ranking_system.initialize_rankings()
    
    gc.collect()
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
            name=f"!help | {len(bot.guilds)} servidores"
        )
    )
    
    print("✅ SISTEMA INICIALIZADO!")
    print("="*60)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Sem permissão!", delete_after=5)
        return
    print(f"❌ ERRO: {error}")
    await ctx.send(f"❌ Erro: {str(error)[:100]}", delete_after=10)

# ============================================================
# COMANDO HELP
# ============================================================

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="🎯 RANK BOT - HELP",
        description="Sistema de RANKED e APOSTADO",
        color=EMBED_COLOR,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="📊 COMANDOS PÚBLICOS",
        value=(
            "`!rank [1v1|2v2|3v3]` - Ver ranking\n"
            "`!myrank [1v1|2v2|3v3]` - Suas estatísticas\n"
            "`!matches` - Partidas ativas\n"
            "`!join <ID> [team1|team2]` - Entrar na partida"
        ),
        inline=False
    )
    
    if ctx.author.guild_permissions.administrator:
        embed.add_field(
            name="🔧 COMANDOS ADMIN",
            value=(
                "`!ranked <tipo> [mapa]` - Criar partida RANKED\n"
                "`!apostado <tipo> <aposta> [mapa]` - Criar APOSTADO\n"
                "`!config` - Ver configurações\n"
                "`!setconfig <chave> <valor>` - Configurar\n"
                "`!setmediator @cargo` - Definir cargo mediador\n"
                "`!addwins @user <quantidade> [tipo]` - Adicionar vitórias\n"
                "`!removewins @user <quantidade> [tipo]` - Remover vitórias\n"
                "`!setwins @user <quantidade> [tipo]` - Definir vitórias\n"
                "`!distributetop [tipo]` - Distribuir prêmios\n"
                "`!ecogive/remove/set @user <valor>` - Economia"
            ),
            inline=False
        )
    
    embed.set_footer(text=EMBED_FOOTER)
    await ctx.send(embed=embed)

# ============================================================
# REGISTRAR COMANDOS
# ============================================================

async def load_commands():
    admin_commands.register_commands()
    print("✅ Comandos registrados!")

# ============================================================
# MAIN
# ============================================================

async def main():
    try:
        print("🚀 INICIANDO RANK BOT...")
        await load_commands()
        await bot.start(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("❌ Token inválido!")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERRO FATAL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

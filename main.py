# ============================================================
# MAIN.PY - SISTEMA RANKED/APOSTADO (COM VOZ DESABILITADA)
# ============================================================

import discord
from discord.ext import commands
import asyncio
import logging
import sys
from datetime import datetime

from config import DISCORD_TOKEN, EMBED_COLOR, EMBED_FOOTER, MATCH_TYPES
from database import init_db, get_connection
from match_system import MatchSystem
from ranking_system import RankingSystem
from admin_commands import AdminCommands

# ============================================================
# LOGGING
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
# NÃO ative voice_states se não for usar voz

# ============================================================
# DESABILITAR MÓDULO DE VOZ (PYTHON 3.13 COMPATIBILIDADE)
# ============================================================

# ==== COLOQUE AQUI O CÓDIGO PARA DESABILITAR VOZ ====
try:
    # Método 1: Tentar desabilitar o módulo de voz
    discord.voice_client.VoiceClient = None
except AttributeError:
    pass

# Método 2: Monkey patch para evitar erro
import discord.voice_client
if hasattr(discord.voice_client, 'VoiceClient'):
    discord.voice_client.VoiceClient = None

print("🔇 Módulo de voz desabilitado (Python 3.13 compatível)")
# ============================================================

# ============================================================
# BOT
# ============================================================

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ============================================================
# INICIALIZAÇÃO
# ============================================================

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
    
    await ranking_system.initialize_rankings()
    
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

@bot.command(name='help')
async def help_cmd(ctx):
    embed = discord.Embed(
        title="🤖 RANK BOT",
        description="Sistema de RANKED e APOSTADO",
        color=EMBED_COLOR,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="📊 Públicos",
        value=(
            "`!rank [1v1|2v2|3v3]` - Ranking\n"
            "`!myrank [tipo]` - Minhas stats\n"
            "`!matches` - Partidas ativas\n"
            "`!join <ID> [team]` - Entrar"
        ),
        inline=False
    )
    
    if ctx.author.guild_permissions.administrator:
        embed.add_field(
            name="🔧 Admin",
            value=(
                "`!ranked <tipo> <mapa>` - Cria RANKED\n"
                "`!apostado <tipo> <aposta> <mapa>` - Cria APOSTADO\n"
                "`!config` - Ver configurações\n"
                "`!setconfig <chave> <valor>` - Configurar\n"
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

# ============================================================
# MAIN.PY - SISTEMA RANKED/APOSTADO (ATUALIZADO)
# ============================================================

import discord
from discord.ext import commands
import asyncio
import logging
import sys
import gc
import os
from datetime import datetime

from config import DISCORD_TOKEN, EMBED_COLOR, EMBED_FOOTER
from database import init_db
from match_system import MatchSystem
from ranking_system import RankingSystem
from admin_commands import AdminCommands

# ============================================================
# CONFIGURAÇÃO DO PREFIXO
# ============================================================

BOT_PREFIX = "%"  # <--- MUDE PARA O PREFIXO QUE QUISER

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

# ============================================================
# BOT
# ============================================================

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)

# ============================================================
# INICIALIZAÇÃO
# ============================================================

print("🚀 Inicializando sistemas...")
print(f"🔧 Prefixo: {BOT_PREFIX}")
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
    print(f"🔧 Prefixo: {BOT_PREFIX}")
    print("="*60)
    
    # INICIA AS TASKS DE BACKGROUND
    match_system.start_tasks()
    
    await ranking_system.initialize_rankings()
    gc.collect()
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
            name=f"{BOT_PREFIX}help | {len(bot.guilds)} servidores"
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
        title=f"🎯 RANK BOT - HELP",
        description=f"Sistema de RANKED e APOSTADO\n**Prefixo:** `{BOT_PREFIX}`",
        color=EMBED_COLOR,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="📊 COMANDOS PÚBLICOS",
        value=(
            f"`{BOT_PREFIX}rank [1v1|2v2|3v3]` - Ver ranking\n"
            f"`{BOT_PREFIX}myrank [1v1|2v2|3v3]` - Suas estatísticas\n"
            f"`{BOT_PREFIX}matches` - Partidas ativas\n"
            f"`{BOT_PREFIX}queue [1v1|2v2|3v3]` - Entrar na fila\n"
            f"`{BOT_PREFIX}queue status` - Status das filas\n"
            f"`{BOT_PREFIX}queue list` - Listar jogadores na fila\n"
            f"`{BOT_PREFIX}leave` - Sair da fila\n"
            f"`{BOT_PREFIX}join <ID> [team1|team2]` - Entrar na partida"
        ),
        inline=False
    )
    
    if ctx.author.guild_permissions.administrator:
        embed.add_field(
            name="🔧 COMANDOS ADMIN",
            value=(
                f"`{BOT_PREFIX}ranked <tipo> [mapa]` - Criar partida RANKED\n"
                f"`{BOT_PREFIX}apostado <tipo> <aposta> [mapa]` - Criar APOSTADO\n"
                f"`{BOT_PREFIX}config` - Ver configurações\n"
                f"`{BOT_PREFIX}setconfig <chave> <valor>` - Configurar\n"
                f"`{BOT_PREFIX}setmediator @cargo` - Definir cargo mediador\n"
                f"`{BOT_PREFIX}addwins @user <quantidade> [tipo]` - Adicionar vitórias\n"
                f"`{BOT_PREFIX}removewins @user <quantidade> [tipo]` - Remover vitórias\n"
                f"`{BOT_PREFIX}setwins @user <quantidade> [tipo]` - Definir vitórias\n"
                f"`{BOT_PREFIX}distributetop [tipo]` - Distribuir prêmios\n"
                f"`{BOT_PREFIX}ecogive/remove/set @user <valor>` - Economia\n"
                f"`{BOT_PREFIX}queueadmin clear <tipo>` - Limpar fila\n"
                f"`{BOT_PREFIX}queueadmin remove @user` - Remover da fila"
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
        print(f"🚀 INICIANDO RANK BOT (prefixo: {BOT_PREFIX})...")
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

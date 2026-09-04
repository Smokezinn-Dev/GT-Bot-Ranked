# ============================================================
# BOT.PY - ARQUIVO PRINCIPAL
# ============================================================

import os
import sys
import asyncio
import logging
from datetime import datetime
import discord.py
from discord.ext import commands

from config import config, init_config, DiscloudHealth
from database import init_db, get_connection, get_guild_settings, cleanup_expired_matches
from match_system import MatchSystem
from ranking_system import RankingSystem
from admin_commands import AdminCommands

config = init_config()

if config.LOG_LEVEL == 'ERROR':
    logging.getLogger('discord').setLevel(logging.CRITICAL)
    logging.getLogger('motor').setLevel(logging.CRITICAL)
    logging.getLogger('pymongo').setLevel(logging.CRITICAL)
    logging.getLogger('asyncio').setLevel(logging.CRITICAL)

db = init_db()
TOKEN = config.DISCORD_TOKEN

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

match_system = MatchSystem(db, config, bot)
ranking_system = RankingSystem(db, config, bot)
admin_commands = AdminCommands(bot, db, config, match_system, ranking_system)

startup_time = datetime.utcnow()

@bot.event
async def on_ready():
    global startup_time
    print("\n" + "="*60)
    print(f"✅ BOT CONECTADO: {bot.user}")
    print(f"📡 ID: {bot.user.id}")
    print(f"📊 SERVIDORES: {len(bot.guilds)}")
    print(f"💾 RAM: {DiscloudHealth.get_ram_usage()}MB")
    print("="*60)
    
    await ranking_system.initialize_rankings()
    cleanup_expired_matches(24)
    await bot.tree.sync()
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
            name=f"!help | {len(bot.guilds)} servidores"
        )
    )
    
    print("✅ SISTEMA INICIALIZADO!")
    print(f"⏱️ TEMPO: {(datetime.utcnow() - startup_time).seconds}s")
    print("="*60)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Sem permissão!", delete_after=5)
        return
    print(f"❌ ERRO: {error}")
    await ctx.send("❌ Erro ao executar comando!", delete_after=10)

@bot.command(name='help')
async def help_cmd(ctx):
    settings = get_guild_settings(str(ctx.guild.id))
    
    embed = discord.Embed(
        title="🤖 RANK BOT",
        description="Sistema de RANKED e APOSTADO",
        color=config.EMBED_COLOR,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="📊 Públicos",
        value="`!rank [1v1|2v2|3v3]` - Ranking\n`!myrank [tipo]` - Minhas stats\n`!matches` - Partidas ativas\n`!join <ID> [team]` - Entrar",
        inline=False
    )
    
    if ctx.author.guild_permissions.administrator:
        embed.add_field(
            name="🔧 Admin",
            value="`!ranked <tipo> <mapa>` - Cria RANKED\n`!apostado <tipo> <aposta> <mapa>` - Cria APOSTADO\n`!config` - Ver configurações\n`!setconfig <chave> <valor>` - Configurar\n`!setranked <opção> <valor>` - Configurar RANKED\n`!setbetting <opção> <valor>` - Configurar APOSTADO\n`!setprizes <posição> <valor>` - Prêmios\n`!distributetop [tipo]` - Distribuir prêmios\n`!ecogive/remove/set @user <valor>` - Economia",
            inline=False
        )
    
    embed.set_footer(text=config.EMBED_FOOTER)
    await ctx.send(embed=embed)

async def load_commands():
    admin_commands.register_commands()
    print("✅ Comandos registrados!")

async def main():
    try:
        print("🚀 INICIANDO BOT...")
        print(f"💰 Economia: {'✅ Ativa' if config.ECONOMY_ENABLED else '❌ Inativa'}")
        await load_commands()
        await bot.start(TOKEN)
    except discord.LoginFailure:
        print("❌ Token inválido!")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERRO FATAL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

# ============================================================
# MAIN.PY - GT BOT RANKED (OTIMIZADO EXTREMO)
# ============================================================
# - Poucos objetos em memória
# - Load único de sistemas
# - Sem double-cog
# - Sync slash com tratamento de 429
# - Prefixo %
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
from match_system import MatchSystem
from ranking_system import RankingSystem
from admin_commands import AdminCommands

# Logging leve
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

        # Sistemas (1x)
        self.match_system = MatchSystem(db, sys.modules["config"], self)
        self.ranking_system = RankingSystem(db, sys.modules["config"], self)

        # Admin cog (só se não existir)
        if self.get_cog("AdminCommands") is None:
            await self.add_cog(AdminCommands(self, self.match_system, self.ranking_system))

        # Sync slash — trata 429
        try:
            if GUILD_ID:
                await self.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
            else:
                await self.tree.sync()
        except discord.HTTPException as e:
            if e.status == 429:
                logger.warning("Slash sync rate-limited (429) — ok")
            else:
                logger.error(f"Sync: {e}")
        except Exception as e:
            logger.error(f"Sync: {e}")

        gc.collect()

    async def on_ready(self):
        logger.info(f"✅ {self.user} | Guilds: {len(self.guilds)}")
        try:
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{PREFIX}help | Ranked"
                )
            )
        except Exception:
            pass
        # pré-aquece ranking só se tiver poucas guilds
        if self.ranking_system and len(self.guilds) <= 10:
            try:
                await self.ranking_system.initialize_rankings()
            except Exception:
                pass
        gc.collect()

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("❌ Sem permissão.", delete_after=6)
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"❌ Falta: `{error.param.name}`", delete_after=6)
        if isinstance(error, commands.BadArgument):
            return await ctx.send("❌ Argumento inválido.", delete_after=6)
        logger.error(f"{ctx.command}: {error}")


# ============================================================
# COMANDOS DE JOGADOR (prefixo %)
# ============================================================

bot = RankedBot()


@bot.command(name="rank")
async def rank_cmd(ctx, match_type: str = "1v1"):
    """Mostra ranking. Ex: %rank 1v1"""
    if match_type not in MATCH_TYPES:
        return await ctx.send(f"❌ Tipos: {', '.join(MATCH_TYPES)}")
    embed = await bot.ranking_system.generate_ranking_embed(str(ctx.guild.id), match_type)
    await ctx.send(embed=embed)


@bot.command(name="stats", aliases=["mystats", "perfil"])
async def stats_cmd(ctx, member: discord.Member = None):
    """Estatísticas de um jogador."""
    member = member or ctx.author
    embed = await bot.ranking_system.get_player_stats_embed(
        str(ctx.guild.id), str(member.id), member
    )
    await ctx.send(embed=embed)


@bot.command(name="queue", aliases=["fila"])
async def queue_cmd(ctx, action: str = "status", match_type: str = "1v1"):
    """
    Sistema de fila simples.
    %queue 1v1          → entra na fila (cria lobby se necessário)
    %queue status       → status
    """
    # Status
    if action.lower() in ("status", "s"):
        lobbies = [
            lob for lob in bot.match_system.active_lobbies.values()
            if lob.get("guild_id") == str(ctx.guild.id) and lob.get("status") == "waiting"
        ]
        if not lobbies:
            return await ctx.send("📋 Nenhuma fila ativa.")
        lines = []
        for lob in lobbies[:8]:
            mt = lob.get("match_type", "?")
            n = len(lob.get("players", []))
            mid = lob.get("id", "")[:6]
            lines.append(f"`{mid}` {mt} — {n} jogador(es)")
        return await ctx.send("📋 Filas ativas:\n" + "\n".join(lines))

    # Entrar / criar
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
    await ctx.send(f"✅ Lobby RANKED `{result['match_id'][:6]}` criado! Use `%join {result['match_id'][:6]}`")


@bot.command(name="join")
async def join_cmd(ctx, match_id: str, team: str = None):
    """Entra em uma partida. Ex: %join abc123  |  %join abc123 team1"""
    result = await bot.match_system.join_lobby(match_id, str(ctx.author.id), team)
    if result.get("error"):
        return await ctx.send(result["error"])
    if result.get("match_started"):
        return await ctx.send("🎯 Partida completa! Ticket criado.")
    await ctx.send(f"✅ Você entrou! Jogadores: {result.get('player_count')}")


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
    await ctx.send(f"✅ RANKED `{result['match_id'][:6]}` criado.")


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
    await ctx.send(f"✅ APOSTADO `{result['match_id'][:6]}` | Aposta: **{bet}**")


@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send(f"🏓 {round(bot.latency * 1000, 1)}ms")


@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="📖 GT Bot Ranked — Comandos",
        color=EMBED_COLOR,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(
        name="🎮 Jogador",
        value=(
            f"`{PREFIX}rank [1v1|2v2|3v3]` — ranking\n"
            f"`{PREFIX}stats [@user]` — estatísticas\n"
            f"`{PREFIX}queue 1v1` — criar/entrar fila\n"
            f"`{PREFIX}queue status` — status das filas\n"
            f"`{PREFIX}join <id> [team1|team2]` — entrar\n"
            f"`{PREFIX}bal` — saldo"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚙️ Admin",
        value=(
            f"`{PREFIX}ranked 1v1 Arena` — criar RANKED\n"
            f"`{PREFIX}apostado 1v1 500` — criar APOSTADO\n"
            f"`{PREFIX}config` — configurações\n"
            f"`{PREFIX}setmediator @cargo` — mediador\n"
            f"`{PREFIX}give / take / setbalance` — economia\n"
            f"`{PREFIX}cancelmatch <id>` — cancelar\n"
            f"`{PREFIX}distributetop 1v1` — prêmios top"
        ),
        inline=False,
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

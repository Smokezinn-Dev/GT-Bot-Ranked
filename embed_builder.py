# ============================================================
# EMBED_BUILDER.PY - PAINEL MODERNO v11.0 (COMPLETO)
# ============================================================
# ✅ Slash Command /upload
# ✅ Botão copiar URL
# ✅ Upload de arquivo
# ✅ URL direta
# ✅ Suporte a emojis customizados (:nome: ou <:nome:ID>)
# ✅ EMOJIS DO GITHUB (auto-sync)
# ✅ Pool de sessões HTTP
# ✅ Cache LRU com TTL
# ✅ Otimização extrema
# ✅ CORRIGIDO: InteractionResponded no select
# ============================================================

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View, Select, Modal, TextInput
from discord import ButtonStyle, SelectOption
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any
import copy
import asyncio
import re
import time
import gc
import json
import os
import aiohttp
from asyncio import Semaphore

from database import get_guild_settings, update_guild_settings


# ============================================================
# CONFIGURAÇÃO
# ============================================================

# 🔥 MUDE AQUI: Seu repositório GitHub
GITHUB_USER = "seu-user"  # Seu nome de usuário do GitHub
GITHUB_REPO = "seu-repo"  # Nome do repositório
GITHUB_BRANCH = "main"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"

# URL da pasta de emojis
EMOJI_FOLDER_URL = f"{GITHUB_RAW_URL}/emojis"
EMOJI_CONFIG_URL = f"{GITHUB_RAW_URL}/emojis_config.json"

# 🔥 MUDE AQUI: ID do servidor onde os emojis serão armazenados
EMOJI_SERVER_ID = None  # Deixe None para usar o servidor atual, ou coloque o ID

# Estrutura de emojis (fallback se o config.json não existir)
DEFAULT_EMOJIS = [
    {"name": "blockdash", "file": "blockdash.png", "emoji": "🏃", "map_name": "Block Dash"},
    {"name": "blockdash_legendary", "file": "blockdash_legendary.png", "emoji": "⭐", "map_name": "Block Dash Legendary"},
    {"name": "rush_hour", "file": "rush_hour.png", "emoji": "🚗", "map_name": "Rush Hour"},
    {"name": "laser_tracer", "file": "laser_tracer.png", "emoji": "🔫", "map_name": "Laser Tracer"},
    {"name": "laser_dash", "file": "laser_dash.png", "emoji": "⚡", "map_name": "Laser Dash"},
    {"name": "lava_land", "file": "lava_land.png", "emoji": "🌋", "map_name": "Lava Land"},
    {"name": "bot_bash", "file": "bot_bash.png", "emoji": "🤖", "map_name": "Bot Bash"},
    {"name": "honey_drop", "file": "honey_drop.png", "emoji": "🍯", "map_name": "Honey Drop"},
    {"name": "sharkmuda", "file": "sharkmuda.png", "emoji": "🦈", "map_name": "Sharkmuda"},
    {"name": "the_other_side", "file": "the_other_side.png", "emoji": "🌌", "map_name": "The Other Side"},
]

# ============================================================
# CONSTANTES
# ============================================================

MODERN_COLORS = [
    {"name": "Blurple", "emoji": "💜", "value": 0x5865F2},
    {"name": "Verde Esmeralda", "emoji": "💚", "value": 0x2ECC71},
    {"name": "Vermelho Rubi", "emoji": "❤️", "value": 0xE74C3C},
    {"name": "Dourado", "emoji": "🌟", "value": 0xF1C40F},
    {"name": "Roxo Real", "emoji": "👾", "value": 0x9B59B6},
    {"name": "Rosa Choque", "emoji": "🌸", "value": 0xE91E63},
    {"name": "Laranja Fogo", "emoji": "🔥", "value": 0xE67E22},
    {"name": "Ciano Neon", "emoji": "🩵", "value": 0x1ABC9C},
    {"name": "Preto Elegante", "emoji": "🖤", "value": 0x23272A},
    {"name": "Branco Perolado", "emoji": "🤍", "value": 0xFFFFFF},
    {"name": "Azul Céu", "emoji": "☀️", "value": 0x3498DB},
    {"name": "Rosa Antigo", "emoji": "🎀", "value": 0xF8A4B8},
]

ICONS = {
    "title": "📌", "description": "📝", "thumbnail": "🖼️", "color": "🎨",
    "maps": "🗺️", "mode": "🎮", "publish": "📤", "preview": "👁️",
    "cancel": "❌", "back": "🔙", "add": "➕", "remove": "🗑️",
    "edit": "✏️", "save": "💾", "stumble": "🎲", "clear": "🧹",
    "loading": "⏳", "success": "✅", "error": "❌", "info": "ℹ️",
    "settings": "⚙️", "image": "🖼️", "link": "🔗", "url": "🌐",
    "embed": "📎", "upload": "📤", "copy": "📋", "sync": "🔄",
}

MODE_NAMES = {"1v1": "⚔️ Duelo", "2v2": "👥 Duplas", "3v3": "👨‍👩‍👦 Trio", "4v4": "👨‍👩‍👧‍👦 Quarteto"}

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.tiff', '.ico', '.avif'}

TRUSTED_DOMAINS = {
    'i.imgur.com': 'Imgur',
    'cdn.discordapp.com': 'Discord CDN',
    'media.discordapp.net': 'Discord Media',
    'i.pinimg.com': 'Pinterest',
    'cdn.discord.com': 'Discord CDN',
}


# ============================================================
# EMOJI MANAGER COM GITHUB
# ============================================================

class GitHubEmojiManager:
    """
    Gerencia emojis carregados do GitHub.
    Baixa as imagens e cria os emojis automaticamente no servidor central.
    """
    __slots__ = ("bot", "_emoji_server_id", "_cache", "_config", "_session", "_lock", "_emoji_map")
    
    def __init__(self, bot, emoji_server_id: Optional[int] = None):
        self.bot = bot
        self._emoji_server_id = emoji_server_id
        self._cache: Dict[str, discord.Emoji] = {}
        self._config: List[Dict] = []
        self._emoji_map: Dict[str, str] = {}  # nome do emoji -> string do emoji
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        
        # Carrega configuração inicial
        self._load_default_config()
    
    def _load_default_config(self):
        """Carrega a configuração padrão de emojis"""
        self._config = copy.deepcopy(DEFAULT_EMOJIS)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def fetch_config(self) -> bool:
        """Busca a configuração de emojis do GitHub"""
        try:
            session = await self._get_session()
            async with session.get(EMOJI_CONFIG_URL, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._config = data.get("emojis", DEFAULT_EMOJIS)
                    return True
                else:
                    print(f"⚠️ Config não encontrada no GitHub, usando padrão")
                    self._config = DEFAULT_EMOJIS
                    return True
        except Exception as e:
            print(f"⚠️ Erro ao buscar config: {e}, usando padrão")
            self._config = DEFAULT_EMOJIS
            return True
    
    async def download_emoji_image(self, filename: str) -> Optional[bytes]:
        """Baixa a imagem do emoji do GitHub"""
        url = f"{EMOJI_FOLDER_URL}/{filename}"
        try:
            session = await self._get_session()
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    return await resp.read()
                print(f"⚠️ Imagem não encontrada: {filename}")
                return None
        except Exception as e:
            print(f"⚠️ Erro ao baixar {filename}: {e}")
            return None
    
    async def _get_target_guild(self) -> Optional[discord.Guild]:
        """Retorna o servidor alvo para os emojis"""
        if self._emoji_server_id:
            guild = self.bot.get_guild(self._emoji_server_id)
            if guild:
                return guild
            try:
                guild = await self.bot.fetch_guild(self._emoji_server_id)
                return guild
            except:
                pass
        
        # Fallback: usa o primeiro servidor disponível
        if self.bot.guilds:
            return self.bot.guilds[0]
        return None
    
    async def create_emoji(self, guild: discord.Guild, name: str, image_data: bytes) -> Optional[discord.Emoji]:
        """Cria um emoji no servidor"""
        try:
            # Verifica se já existe
            existing = discord.utils.get(guild.emojis, name=name)
            if existing:
                return existing
            
            # Cria o emoji
            emoji = await guild.create_custom_emoji(
                name=name,
                image=image_data,
                reason=f"Emoji sincronizado do GitHub: {name}"
            )
            return emoji
        except discord.HTTPException as e:
            if "Maximum number of emojis" in str(e):
                print(f"⚠️ Limite de emojis atingido! Não foi possível criar: {name}")
            else:
                print(f"❌ Erro ao criar emoji {name}: {e}")
            return None
        except Exception as e:
            print(f"❌ Erro ao criar emoji {name}: {e}")
            return None
    
    async def sync_all_emojis(self) -> Dict[str, bool]:
        """Sincroniza todos os emojis do GitHub para o servidor"""
        results = {}
        
        # Busca a configuração
        await self.fetch_config()
        
        # Pega o servidor alvo
        guild = await self._get_target_guild()
        if not guild:
            return {"error": "Servidor não encontrado! Certifique-se de que o bot está em um servidor."}
        
        # Para cada emoji na configuração
        for emoji_config in self._config:
            name = emoji_config.get("name")
            filename = emoji_config.get("file")
            
            if not name or not filename:
                continue
            
            # Baixa a imagem
            image_data = await self.download_emoji_image(filename)
            if not image_data:
                results[name] = False
                continue
            
            # Cria o emoji
            emoji = await self.create_emoji(guild, name, image_data)
            if emoji:
                async with self._lock:
                    self._cache[name] = emoji
                    self._emoji_map[name] = str(emoji)
                results[name] = True
            else:
                results[name] = False
        
        return results
    
    async def get_emoji(self, name: str) -> Optional[str]:
        """
        Retorna o emoji como string (para usar em selects).
        Busca no cache, no servidor, ou no GitHub.
        """
        if not name:
            return None
        
        name = name.strip()
        
        # Remove : se tiver
        if name.startswith(':') and name.endswith(':'):
            name = name[1:-1]
        
        # Verifica cache
        async with self._lock:
            if name in self._emoji_map:
                return self._emoji_map[name]
            
            if name in self._cache:
                emoji_str = str(self._cache[name])
                self._emoji_map[name] = emoji_str
                return emoji_str
        
        # Busca no servidor
        guild = await self._get_target_guild()
        if guild:
            for emoji in guild.emojis:
                if emoji.name == name:
                    async with self._lock:
                        self._cache[name] = emoji
                        self._emoji_map[name] = str(emoji)
                    return str(emoji)
        
        # Tenta baixar do GitHub e criar
        await self.fetch_config()
        for emoji_config in self._config:
            if emoji_config.get("name") == name:
                filename = emoji_config.get("file")
                if filename:
                    image_data = await self.download_emoji_image(filename)
                    if image_data and guild:
                        emoji = await self.create_emoji(guild, name, image_data)
                        if emoji:
                            async with self._lock:
                                self._cache[name] = emoji
                                self._emoji_map[name] = str(emoji)
                            return str(emoji)
                break
        
        return None
    
    async def get_emoji_by_map_name(self, map_name: str) -> Optional[str]:
        """Busca o emoji pelo nome do mapa"""
        await self.fetch_config()
        for emoji_config in self._config:
            if emoji_config.get("map_name", "").lower() == map_name.lower():
                return await self.get_emoji(emoji_config.get("name"))
        return None
    
    async def ensure_emojis(self) -> bool:
        """Garante que todos os emojis estão criados"""
        # Busca config
        await self.fetch_config()
        
        # Pega o servidor
        guild = await self._get_target_guild()
        if not guild:
            return False
        
        # Verifica quais emojis faltam
        missing = []
        for emoji_config in self._config:
            name = emoji_config.get("name")
            if not name:
                continue
            existing = discord.utils.get(guild.emojis, name=name)
            if not existing:
                missing.append(emoji_config)
        
        # Cria os que faltam
        if missing:
            for emoji_config in missing:
                name = emoji_config.get("name")
                filename = emoji_config.get("file")
                if name and filename:
                    image_data = await self.download_emoji_image(filename)
                    if image_data:
                        await self.create_emoji(guild, name, image_data)
        
        return True
    
    async def get_all_emojis(self) -> Dict[str, str]:
        """Retorna todos os emojis como dict {nome: string_emoji}"""
        await self.ensure_emojis()
        
        result = {}
        for emoji_config in self._config:
            name = emoji_config.get("name")
            if name:
                emoji_str = await self.get_emoji(name)
                if emoji_str:
                    result[name] = emoji_str
        
        return result
    
    async def get_map_emojis(self) -> List[Dict]:
        """Retorna lista de mapas com emojis para usar no painel"""
        await self.ensure_emojis()
        
        mapas = []
        for emoji_config in self._config:
            name = emoji_config.get("name")
            map_name = emoji_config.get("map_name", name)
            emoji_str = await self.get_emoji(name)
            
            mapas.append({
                "name": map_name,
                "emoji": emoji_str or emoji_config.get("emoji", "🗺️"),
                "image": None,  # Pode adicionar URL da imagem aqui se quiser
                "service": "GitHub Emoji"
            })
        
        return mapas
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ============================================================
# POOL DE SESSÕES HTTP
# ============================================================

class _ImageSessionPool:
    __slots__ = ("_sessions", "_max_size", "_lock", "_semaphore")
    
    def __init__(self, max_size: int = 2):
        self._sessions: List[aiohttp.ClientSession] = []
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._semaphore = Semaphore(max_size * 2)
    
    async def get(self) -> aiohttp.ClientSession:
        async with self._lock:
            if self._sessions:
                session = self._sessions.pop()
                if not session.closed:
                    return session
        
        connector = aiohttp.TCPConnector(
            limit=2,
            limit_per_host=1,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            force_close=False,
        )
        timeout = aiohttp.ClientTimeout(total=3, connect=2)
        return aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'GTBot/2.0', 'Accept': 'image/*'},
        )
    
    async def release(self, session: aiohttp.ClientSession):
        if session.closed:
            return
        async with self._lock:
            if len(self._sessions) < self._max_size:
                self._sessions.append(session)
            else:
                await session.close()
    
    async def close_all(self):
        async with self._lock:
            for session in self._sessions:
                try:
                    await session.close()
                except:
                    pass
            self._sessions.clear()
            gc.collect()


_pool = _ImageSessionPool(max_size=2)


# ============================================================
# CACHE DE IMAGENS
# ============================================================

class _ImageCache:
    __slots__ = ("_data", "_maxsize", "_ttl", "_lock", "_hits", "_misses")
    
    def __init__(self, maxsize: int = 32, ttl: int = 3600):
        self._data: Dict[str, Tuple[str, float]] = {}
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
    
    async def get(self, url: str) -> Optional[str]:
        async with self._lock:
            if url in self._data:
                image_url, ts = self._data[url]
                if time.monotonic() - ts < self._ttl:
                    self._hits += 1
                    return image_url
                del self._data[url]
            self._misses += 1
            return None
    
    async def set(self, url: str, image_url: str):
        async with self._lock:
            self._data[url] = (image_url, time.monotonic())
            if len(self._data) > self._maxsize:
                oldest = min(self._data.items(), key=lambda x: x[1][1])
                del self._data[oldest[0]]
    
    async def clear(self):
        async with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0
            gc.collect()


_cache = _ImageCache(maxsize=32, ttl=3600)


# ============================================================
# VALIDADOR DE IMAGENS
# ============================================================

class _ImageValidator:
    __slots__ = ()
    
    @staticmethod
    def _has_image_extension(url: str) -> bool:
        url_lower = url.lower()
        return any(url_lower.endswith(ext) for ext in IMAGE_EXTENSIONS)
    
    @staticmethod
    def _is_trusted_domain(url: str) -> Optional[str]:
        url_lower = url.lower()
        for domain, name in TRUSTED_DOMAINS.items():
            if domain in url_lower:
                return name
        return None
    
    @staticmethod
    async def _quick_head_check(url: str) -> bool:
        if not url.startswith(('http://', 'https://')):
            return False
        
        async with _pool._semaphore:
            session = await _pool.get()
            try:
                async with session.head(url, allow_redirects=True, timeout=2) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get('Content-Type', '').lower()
                        return content_type.startswith('image/')
                    return False
            except:
                return False
            finally:
                await _pool.release(session)
    
    @classmethod
    async def validate_url(cls, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        if not url or not isinstance(url, str):
            return False, None, "❌ URL vazia."
        
        url = url.strip()
        
        cached = await _cache.get(url)
        if cached:
            return True, cached, None
        
        if cls._has_image_extension(url):
            await _cache.set(url, url)
            return True, url, None
        
        service = cls._is_trusted_domain(url)
        if service:
            await _cache.set(url, url)
            return True, url, None
        
        if await cls._quick_head_check(url):
            await _cache.set(url, url)
            return True, url, None
        
        return False, None, (
            "❌ URL inválida.\n\n"
            "✅ **Use UMA destas opções:**\n"
            "1️⃣ URL direta: https://i.imgur.com/xxxxx.jpg\n"
            "2️⃣ Discord CDN: cdn.discordapp.com/...\n"
            "3️⃣ Pinterest: i.pinimg.com/...\n"
            "4️⃣ Comando `/upload` (anexe a imagem)\n\n"
            "❌ **Não funcionam:** Instagram, Facebook, TikTok, YouTube"
        )
    
    @classmethod
    async def validate_attachment(cls, attachment) -> Tuple[bool, Optional[str], Optional[str]]:
        if not attachment:
            return False, None, "❌ Nenhum arquivo."
        
        if not attachment.content_type or not attachment.content_type.startswith('image/'):
            return False, None, f"❌ Não é imagem. Tipo: {attachment.content_type}"
        
        if attachment.size > 5 * 1024 * 1024:
            return False, None, "❌ Máx 5MB."
        
        url = attachment.url
        await _cache.set(url, url)
        return True, url, None


# ============================================================
# VIEW - COPIAR URL
# ============================================================

class CopyUrlView(View):
    __slots__ = ("url",)
    
    def __init__(self, url: str):
        super().__init__(timeout=300)
        self.url = url
    
    @discord.ui.button(label="📋 Copiar URL", style=ButtonStyle.primary, emoji="📋")
    async def copy_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            f"📋 **URL da imagem:**\n```\n{self.url}\n```\n\n"
            "✅ Clique com o botão direito e selecione **Copiar**",
            ephemeral=True
        )
    
    @discord.ui.button(label="🔗 Abrir Imagem", style=ButtonStyle.secondary, emoji="🔗")
    async def open_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            f"🔗 **Abra a imagem no navegador:**\n```\n{self.url}\n```",
            ephemeral=True
        )


# ============================================================
# FUNÇÕES DE EMOJI
# ============================================================

def is_custom_emoji(text: str) -> bool:
    """Verifica se é um emoji customizado: <:nome:ID> ou <a:nome:ID>"""
    if not text:
        return False
    return bool(re.match(r'^<a?:[a-zA-Z0-9_]+:[0-9]+>$', text.strip()))

def is_emoji_code(text: str) -> bool:
    """Verifica se é um código :nome:"""
    if not text:
        return False
    return bool(re.match(r'^:[a-zA-Z0-9_]+:$', text.strip()))

def is_simple_name(text: str) -> bool:
    """Verifica se é um nome simples (sem : e sem <>)"""
    if not text:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_]+$', text.strip()))

def extract_emoji_id(text: str) -> Optional[int]:
    """Extrai o ID do emoji customizado"""
    match = re.search(r':([0-9]+)>$', text)
    if match:
        try:
            return int(match.group(1))
        except:
            return None
    return None

def get_emoji_display(emoji: str) -> str:
    """Retorna uma versão legível do emoji para exibição"""
    if not emoji:
        return "🗺️"
    if is_custom_emoji(emoji):
        match = re.search(r':([a-zA-Z0-9_]+):', emoji)
        if match:
            return f":{match.group(1)}:"
        return emoji
    return emoji


# ============================================================
# MODAL - MAPA COM IMAGEM (COM EMOJI DO GITHUB)
# ============================================================

class MapWithImageModal(Modal):
    __slots__ = ("panel_view", "option_index", "emoji_manager")
    
    def __init__(self, panel_view, option_index: Optional[int] = None, 
                 current_name: str = "", current_emoji: str = "", current_image: str = ""):
        super().__init__(title="🗺️ Configurar Mapa", timeout=300)
        self.panel_view = panel_view
        self.option_index = option_index
        self.emoji_manager = panel_view.emoji_manager
        
        self.name_input = TextInput(
            label="📝 Nome do Mapa",
            placeholder="Ex: Block Dash, Arena, Castelo...",
            default=current_name,
            style=discord.TextStyle.short,
            max_length=50,
            required=True
        )
        self.add_item(self.name_input)
        
        self.emoji_input = TextInput(
            label="🎨 Emoji ou Código (ex: :blockdash:)",
            placeholder="Use :nome: ou nome do emoji (ex: blockdash)",
            default=current_emoji,
            style=discord.TextStyle.short,
            max_length=100,
            required=False
        )
        self.add_item(self.emoji_input)
        
        self.image_input = TextInput(
            label="🌐 URL da Imagem (ou use /upload)",
            placeholder="URL direta da imagem (ex: https://i.imgur.com/xxxxx.jpg)",
            default=current_image,
            style=discord.TextStyle.short,
            max_length=500,
            required=False
        )
        self.add_item(self.image_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()
        emoji_input = self.emoji_input.value.strip()
        image_url = self.image_input.value.strip()
        
        if not name:
            return await interaction.response.send_message("❌ Nome é obrigatório!", ephemeral=True)
        
        # 🔥 CONVERTE EMOJI (COM SUPORTE GITHUB)
        emoji = None
        
        if emoji_input:
            # Tenta converter via GitHub
            emoji = await self.emoji_manager.get_emoji(emoji_input)
            
            # Se não achou, tenta como código :nome:
            if not emoji and is_emoji_code(emoji_input):
                name_clean = emoji_input[1:-1]
                emoji = await self.emoji_manager.get_emoji(name_clean)
            
            # Se não achou, tenta como nome simples
            if not emoji and is_simple_name(emoji_input):
                emoji = await self.emoji_manager.get_emoji(emoji_input)
            
            # Se ainda não achou, tenta pelo nome do mapa
            if not emoji:
                emoji = await self.emoji_manager.get_emoji_by_map_name(name)
            
            # Se não achou, usa o que o usuário digitou (pode ser Unicode)
            if not emoji:
                emoji = emoji_input
        
        # Se não tem emoji, usa padrão
        if not emoji:
            emoji = "🗺️"
        
        option_data = {"name": name, "emoji": emoji}
        
        if image_url:
            success, validated_url, error_msg = await _ImageValidator.validate_url(image_url)
            if not success:
                return await interaction.response.send_message(
                    f"{error_msg}\n\n💡 **Alternativa:** Use o comando `/upload` para enviar a imagem!",
                    ephemeral=True
                )
            option_data["image"] = validated_url
            service = "URL direta"
            if 'imgur.com' in validated_url.lower():
                service = "Imgur"
            elif 'discord' in validated_url.lower():
                service = "Discord CDN"
            elif 'pinimg.com' in validated_url.lower():
                service = "Pinterest"
            option_data["service"] = service
        
        if self.option_index is not None:
            self.panel_view.options[self.option_index] = option_data
            await interaction.response.send_message(f"✅ Mapa **{name}** atualizado! Emoji: {get_emoji_display(emoji)}", ephemeral=True)
        else:
            self.panel_view.options.append(option_data)
            await interaction.response.send_message(f"✅ Mapa **{name}** adicionado! Emoji: {get_emoji_display(emoji)}", ephemeral=True)
        
        await self.panel_view.save_options(interaction.guild.id)
        await self.panel_view.refresh_main_panel(interaction)


# ============================================================
# MODAL - THUMBNAIL
# ============================================================

class ThumbnailModal(Modal):
    __slots__ = ("builder",)
    
    def __init__(self, builder, current_url: str = ""):
        super().__init__(title="🖼️ Editar Thumbnail", timeout=300)
        self.builder = builder
        
        self.url_input = TextInput(
            label="🌐 URL da Imagem (ou use /upload)",
            placeholder="URL direta da imagem (ex: https://i.imgur.com/xxxxx.jpg)",
            default=current_url,
            style=discord.TextStyle.short,
            max_length=500,
            required=False
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value.strip()
        
        if url:
            success, validated_url, error_msg = await _ImageValidator.validate_url(url)
            if not success:
                return await interaction.response.send_message(
                    f"{error_msg}\n\n💡 **Alternativa:** Use o comando `/upload` para enviar a imagem!",
                    ephemeral=True
                )
            self.builder.embed_data["thumbnail"] = validated_url
            service = "URL direta"
            if 'imgur.com' in validated_url.lower():
                service = "Imgur"
            elif 'discord' in validated_url.lower():
                service = "Discord CDN"
            elif 'pinimg.com' in validated_url.lower():
                service = "Pinterest"
            await interaction.response.send_message(f"✅ Thumbnail atualizada! ({service})", ephemeral=True)
        else:
            self.builder.embed_data["thumbnail"] = None
            await interaction.response.send_message("✅ Thumbnail removida!", ephemeral=True)
        
        await interaction.response.defer()
        embed = self.builder.build_final_embed()
        await interaction.edit_original_response(embed=embed, view=self.builder)


# ============================================================
# MODAL - AÇÃO DO MAPA
# ============================================================

class MapActionModal(Modal):
    __slots__ = ("parent_view", "option_index", "emoji_manager")
    
    def __init__(self, parent_view, option_index: int, 
                 current_name: str, current_emoji: str, current_image: str = ""):
        super().__init__(title="⚙️ Editar Mapa", timeout=300)
        self.parent_view = parent_view
        self.option_index = option_index
        self.emoji_manager = parent_view.emoji_manager
        
        self.name_input = TextInput(
            label="📝 Nome do Mapa",
            default=current_name,
            style=discord.TextStyle.short,
            max_length=50,
            required=True
        )
        self.add_item(self.name_input)
        
        self.emoji_input = TextInput(
            label="🎨 Emoji ou Código (ex: :blockdash:)",
            default=current_emoji or "🗺️",
            placeholder="Use :nome: ou nome do emoji",
            style=discord.TextStyle.short,
            max_length=100,
            required=False
        )
        self.add_item(self.emoji_input)
        
        self.image_input = TextInput(
            label="🌐 URL da Imagem (ou deixe vazio)",
            default=current_image or "",
            placeholder="URL direta da imagem (ex: https://i.imgur.com/xxxxx.jpg)",
            style=discord.TextStyle.short,
            max_length=500,
            required=False
        )
        self.add_item(self.image_input)
        
        self.action_input = TextInput(
            label="⚙️ Ação (digite 'salvar' ou 'remover')",
            placeholder="salvar / remover",
            style=discord.TextStyle.short,
            max_length=10,
            required=True
        )
        self.add_item(self.action_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        action = self.action_input.value.lower().strip()
        name = self.name_input.value.strip()
        emoji_input = self.emoji_input.value.strip()
        image_url = self.image_input.value.strip()
        
        if action == "salvar":
            if not name:
                return await interaction.response.send_message("❌ Nome é obrigatório!", ephemeral=True)
            
            # 🔥 CONVERTE EMOJI
            emoji = None
            
            if emoji_input:
                emoji = await self.emoji_manager.get_emoji(emoji_input)
                if not emoji and is_emoji_code(emoji_input):
                    name_clean = emoji_input[1:-1]
                    emoji = await self.emoji_manager.get_emoji(name_clean)
                if not emoji and is_simple_name(emoji_input):
                    emoji = await self.emoji_manager.get_emoji(emoji_input)
                if not emoji:
                    emoji = await self.emoji_manager.get_emoji_by_map_name(name)
            
            if not emoji:
                emoji = "🗺️"
            
            option_data = {"name": name, "emoji": emoji}
            
            if image_url:
                success, validated_url, error_msg = await _ImageValidator.validate_url(image_url)
                if not success:
                    return await interaction.response.send_message(
                        f"{error_msg}\n\n💡 **Alternativa:** Use o comando `/upload` para enviar a imagem!",
                        ephemeral=True
                    )
                option_data["image"] = validated_url
                service = "URL direta"
                if 'imgur.com' in validated_url.lower():
                    service = "Imgur"
                elif 'discord' in validated_url.lower():
                    service = "Discord CDN"
                elif 'pinimg.com' in validated_url.lower():
                    service = "Pinterest"
                option_data["service"] = service
            
            self.parent_view.options[self.option_index] = option_data
            await self.parent_view.save_options(interaction.guild.id)
            
            await interaction.response.defer()
            embed = self.parent_view.build_options_embed()
            new_view = OptionsPanelView(self.parent_view)
            await interaction.edit_original_response(embed=embed, view=new_view)
            await interaction.followup.send(f"✅ Mapa **{name}** salvo! Emoji: {get_emoji_display(emoji)}", ephemeral=True)
            
        elif action == "remover":
            removed = self.parent_view.options.pop(self.option_index)
            await self.parent_view.save_options(interaction.guild.id)
            
            await interaction.response.defer()
            embed = self.parent_view.build_options_embed()
            new_view = OptionsPanelView(self.parent_view)
            await interaction.edit_original_response(embed=embed, view=new_view)
            await interaction.followup.send(f"🗑️ Mapa **{removed.get('name')}** removido!", ephemeral=True)
            
        else:
            await interaction.response.send_message("❌ Ação inválida! Use 'salvar' ou 'remover'", ephemeral=True)


# ============================================================
# MODAIS - TÍTULO, DESCRIÇÃO
# ============================================================

class TitleModal(Modal):
    __slots__ = ("builder",)
    
    def __init__(self, builder, current_title: str = ""):
        super().__init__(title="✏️ Editar Título", timeout=300)
        self.builder = builder
        self.title_input = TextInput(
            label="Título do Embed",
            placeholder="Ex: 🏆 Partida Ranked",
            default=current_title,
            style=discord.TextStyle.short,
            max_length=256,
            required=True
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.builder.embed_data["title"] = self.title_input.value
        await interaction.response.defer()
        embed = self.builder.build_final_embed()
        await interaction.edit_original_response(embed=embed, view=self.builder)
        await interaction.followup.send(f"✅ Título atualizado para: **{self.title_input.value}**", ephemeral=True)


class DescriptionModal(Modal):
    __slots__ = ("builder",)
    
    def __init__(self, builder, current_desc: str = ""):
        super().__init__(title="✏️ Editar Descrição", timeout=300)
        self.builder = builder
        self.desc_input = TextInput(
            label="Descrição do Embed",
            placeholder="Ex: Escolha um mapa no menu abaixo...",
            default=current_desc,
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True
        )
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.builder.embed_data["description"] = self.desc_input.value
        await interaction.response.defer()
        embed = self.builder.build_final_embed()
        await interaction.edit_original_response(embed=embed, view=self.builder)
        await interaction.followup.send(f"✅ Descrição atualizada!", ephemeral=True)


# ============================================================
# VIEW - SELETOR DE COR
# ============================================================

class ColorPickerView(View):
    __slots__ = ("parent_view",)
    
    def __init__(self, parent_view):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        self._add_color_buttons()

    def _add_color_buttons(self):
        for i in range(0, len(MODERN_COLORS), 4):
            row_colors = MODERN_COLORS[i:i+4]
            for color in row_colors:
                button = Button(
                    label=color["name"],
                    style=ButtonStyle.primary,
                    emoji=color["emoji"],
                    custom_id=f"color_{color['value']}"
                )
                button.callback = self._make_color_callback(color["value"])
                self.add_item(button)

    def _make_color_callback(self, color_value):
        async def callback(interaction: discord.Interaction):
            self.parent_view.embed_data["color"] = color_value
            embed = self.parent_view.build_final_embed()
            await interaction.response.edit_message(embed=embed, view=self.parent_view)
            await interaction.followup.send(f"✅ Cor atualizada para `#{color_value:06X}`!", ephemeral=True)
        return callback

    @discord.ui.button(label="Cor Customizada (Hex)", style=ButtonStyle.secondary, emoji="🖊️", row=4)
    async def custom_color(self, interaction: discord.Interaction, button: Button):
        modal = HexColorModal(self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Voltar", style=ButtonStyle.secondary, emoji="🔙", row=4)
    async def back(self, interaction: discord.Interaction, button: Button):
        embed = self.parent_view.build_final_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class HexColorModal(Modal):
    __slots__ = ("panel_view",)
    
    def __init__(self, panel_view):
        super().__init__(title="🎨 Cor Customizada", timeout=300)
        self.panel_view = panel_view
        self.hex_input = TextInput(
            label="Código Hex da cor",
            placeholder="Ex: #FF5733 ou FF5733",
            default=self._hex_str(panel_view.embed_data.get("color", 0x5865F2)),
            style=discord.TextStyle.short,
            max_length=7,
            required=True
        )
        self.add_item(self.hex_input)

    def _hex_str(self, color: int) -> str:
        return f"#{color:06X}"

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.hex_input.value.strip().lstrip("#")
        if len(raw) != 6 or any(c not in "0123456789abcdefABCDEF" for c in raw):
            return await interaction.response.send_message(
                "❌ Cor inválida! Use um hex de 6 dígitos, ex: `#5865F2`.",
                ephemeral=True
            )
        color = int(raw, 16)
        self.panel_view.embed_data["color"] = color
        await interaction.response.defer()
        embed = self.panel_view.build_final_embed()
        await interaction.edit_original_response(embed=embed, view=self.panel_view)
        await interaction.followup.send(f"✅ Cor atualizada para `{self._hex_str(color)}`!", ephemeral=True)


# ============================================================
# VIEW - PUBLISH
# ============================================================

class QueuePublishView(View):
    __slots__ = ("bot", "match_system", "guild_id", "channel_id", "match_type", 
                 "options", "embed_data", "message", "_refresh_pending")
    
    def __init__(self, bot, match_system, guild_id: str, channel_id: str, 
                 match_type: str, options: List[dict], embed_data: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.match_system = match_system
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.match_type = match_type
        self.options = options or []
        self.embed_data = embed_data or {}
        self.message: Optional[discord.Message] = None
        self._refresh_pending = False

    def update_select_options(self):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                opts = []
                if self.options:
                    for opt in self.options[:25]:
                        label = opt.get("name", "Mapa")[:45]
                        emoji = opt.get("emoji", "🗺️")
                        opts.append(SelectOption(
                            label=label,
                            value=opt.get("name", "Mapa"),
                            emoji=emoji
                        ))
                else:
                    opts.append(SelectOption(label="Nenhum mapa disponível", value="none", emoji="❌"))
                child.options = opts
                child.placeholder = "🗺️ Selecione um mapa para entrar na fila"

    def build_publish_embed(self) -> discord.Embed:
        color = self.embed_data.get("color", 0x5865F2)
        title = self.embed_data.get("title", "🏆 Nova Partida")
        if not title.startswith(("🏆", "🎮", "⚔️", "👥", "🎯", "💀", "🔥", "⭐")):
            title = f"🎮 {title}"
        
        embed = discord.Embed(
            title=title,
            description=self.embed_data.get("description", "Escolha um mapa no menu abaixo."),
            color=color,
            timestamp=datetime.utcnow()
        )
        
        if self.embed_data.get("thumbnail"):
            embed.set_thumbnail(url=self.embed_data["thumbnail"])
        
        embed.add_field(name="🎮 Modo", value=MODE_NAMES.get(self.match_type, self.match_type), inline=True)
        
        if self.options and self.match_system:
            map_lines = []
            for opt in self.options[:25]:
                name = opt.get("name", "Mapa")
                emoji = opt.get("emoji", "🗺️")
                status = self.match_system.get_queue_status(
                    self.guild_id, self.channel_id, self.match_type, name
                )
                has_image = "🖼️" if opt.get("image") else ""
                map_lines.append(f"{emoji} **{name}** {has_image}— `{status['count']}/{status['max']}` na fila")
            embed.add_field(name="🗺️ Mapas e Filas", value="\n".join(map_lines), inline=False)
        else:
            embed.add_field(name="🗺️ Mapas", value="*Nenhum mapa configurado*", inline=False)
        
        embed.add_field(
            name="📋 Como Participar",
            value="1️⃣ Selecione um mapa no menu abaixo\n2️⃣ Clique em **Entrar na Fila**\n3️⃣ Aguarde a partida começar!",
            inline=False
        )
        
        bot_name = self.bot.user.name if self.bot.user else "GT Ranked"
        bot_icon = self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty
        embed.set_footer(text=f"✨ {bot_name} • Partida {self.match_type}", icon_url=bot_icon)
        return embed

    async def _refresh(self, interaction: Optional[discord.Interaction] = None):
        if self._refresh_pending:
            return
        self._refresh_pending = True
        async def _do():
            await asyncio.sleep(0.7)
            self._refresh_pending = False
            if not self.message:
                return
            try:
                await self.message.edit(embed=self.build_publish_embed(), view=self)
            except Exception:
                pass
        asyncio.create_task(_do())

    @discord.ui.select(placeholder="🗺️ Selecione um mapa para entrar na fila", min_values=1, max_values=1, options=[])
    async def select_map(self, interaction: discord.Interaction, select: Select):
        if not self.match_system:
            return await interaction.response.send_message("❌ Sistema indisponível.", ephemeral=True)
        if select.values[0] == "none":
            return await interaction.response.send_message("❌ Nenhum mapa disponível!", ephemeral=True)
        
        map_name = select.values[0]
        
        embed = self.build_publish_embed()
        for opt in self.options:
            if opt.get("name") == map_name and opt.get("image"):
                embed.set_thumbnail(url=opt["image"])
                break
        
        result = await self.match_system.join_queue(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            match_type=self.match_type,
            map_name=map_name,
            user_id=interaction.user.id,
        )
        
        if result.get("error"):
            return await interaction.response.send_message(result["error"], ephemeral=True)
        
        if result.get("popped"):
            await interaction.response.send_message(
                f"✅ Fila de **{map_name}** completou! Partida sendo criada.",
                ephemeral=True
            )
            await self._refresh(None)
        else:
            await interaction.response.send_message(
                f"✅ Você entrou na fila de **{map_name}**! (`{result['count']}/{result['max']}`)",
                ephemeral=True
            )
            await self._refresh(None)

    @discord.ui.button(label="🚪 Sair da Fila", style=ButtonStyle.danger, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: Button):
        if not self.match_system:
            return await interaction.response.send_message("❌ Sistema indisponível.", ephemeral=True)
        pkey = f"{self.guild_id}:{interaction.user.id}"
        key = self.match_system.queued_players.get(pkey)
        if not key or not key.startswith(f"{self.guild_id}:{self.channel_id}:{self.match_type}:"):
            return await interaction.response.send_message("❌ Você não está em nenhuma fila desse painel.", ephemeral=True)
        map_name = key.split(":", 3)[3]
        result = await self.match_system.leave_queue(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            match_type=self.match_type,
            map_name=map_name,
            user_id=interaction.user.id,
        )
        if result.get("error"):
            return await interaction.response.send_message(result["error"], ephemeral=True)
        await interaction.response.send_message(f"🚪 Você saiu da fila de **{map_name}**.", ephemeral=True)
        await self._refresh(None)


# ============================================================
# VIEW - PAINEL DE OPÇÕES
# ============================================================

class OptionsPanelView(View):
    __slots__ = ("parent_view", "_loading", "emoji_manager")
    
    def __init__(self, parent_view):
        super().__init__(timeout=600)
        self.parent_view = parent_view
        self._loading = False
        self.emoji_manager = parent_view.emoji_manager
        self._update_select_options()

    def _update_select_options(self):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                options = []
                if self.parent_view.options:
                    for i, opt in enumerate(self.parent_view.options):
                        name = opt.get("name", f"Mapa {i+1}")
                        emoji = opt.get("emoji", "🗺️")
                        has_image = "🖼️" if opt.get("image") else "📝"
                        service = opt.get("service", "")
                        desc = service if service else "Sem imagem"
                        options.append(SelectOption(
                            label=f"{name[:35]}",
                            value=str(i),
                            emoji=emoji,
                            description=f"{has_image} {desc[:40]}"
                        ))
                        if len(options) >= 25:
                            break
                else:
                    options.append(SelectOption(label="Nenhum mapa disponível", value="none", emoji="❌"))
                child.options = options
                child.placeholder = "📋 Selecione um mapa para editar/remover"

    @discord.ui.button(label="🎲 Mapas Stumble", style=ButtonStyle.primary, emoji="🎲", row=0)
    async def add_stumble_maps(self, interaction: discord.Interaction, button: Button):
        if self._loading:
            return await interaction.response.send_message("⏳ Carregando...", ephemeral=True)
        self._loading = True
        try:
            await interaction.response.defer()
            
            # 🔥 PEGA EMOJIS DO GITHUB PARA OS MAPAS STUMBLE
            map_emojis = await self.emoji_manager.get_map_emojis()
            if map_emojis:
                self.parent_view.options = map_emojis
            else:
                # Fallback: usa os mapas padrão
                self.parent_view.options = copy.deepcopy(STUMBLE_MAPS)
            
            await self.parent_view.save_options(interaction.guild.id)
            embed = self.parent_view.build_options_embed()
            new_view = OptionsPanelView(self.parent_view)
            await interaction.edit_original_response(embed=embed, view=new_view)
            await interaction.followup.send(f"✅ {len(self.parent_view.options)} mapas sincronizados do GitHub!", ephemeral=True)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Erro: {e}", ephemeral=True)
            except:
                pass
        finally:
            self._loading = False

    @discord.ui.button(label="📤 Upload", style=ButtonStyle.success, emoji="📤", row=0)
    async def upload_image(self, interaction: discord.Interaction, button: Button):
        modal = UploadImageModal(self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="➕ Adicionar Mapa", style=ButtonStyle.primary, emoji="➕", row=0)
    async def add_option(self, interaction: discord.Interaction, button: Button):
        modal = MapWithImageModal(self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.select(placeholder="📋 Selecione um mapa para editar/remover", min_values=1, max_values=1, row=1, options=[
        SelectOption(label="Nenhum mapa disponível", value="none", emoji="❌")
    ])
    async def select_option(self, interaction: discord.Interaction, select: Select):
        if not select.values or select.values[0] == "none":
            return await interaction.response.send_message("❌ Selecione um mapa válido!", ephemeral=True)
        
        index = int(select.values[0])
        if index >= len(self.parent_view.options):
            return await interaction.response.send_message("❌ Mapa não encontrado!", ephemeral=True)
        
        option = self.parent_view.options[index]
        
        modal = MapActionModal(
            self.parent_view, index,
            option.get("name", ""),
            option.get("emoji", ""),
            option.get("image", "")
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🧹 Limpar Tudo", style=ButtonStyle.danger, emoji="🧹", row=2)
    async def clear_all(self, interaction: discord.Interaction, button: Button):
        self.parent_view.options = []
        await self.parent_view.save_options(interaction.guild.id)
        await interaction.response.defer()
        embed = self.parent_view.build_options_embed()
        new_view = OptionsPanelView(self.parent_view)
        await interaction.edit_original_response(embed=embed, view=new_view)
        await interaction.followup.send("🧹 Todos os mapas removidos!", ephemeral=True)

    @discord.ui.button(label="🔙 Voltar", style=ButtonStyle.secondary, emoji="🔙", row=2)
    async def back_to_main(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        embed = self.parent_view.build_final_embed()
        new_view = EmbedBuilderView(self.parent_view.bot, self.parent_view.embed_data)
        new_view.options = self.parent_view.options
        new_view.guild_id = self.parent_view.guild_id
        new_view.channel_id = self.parent_view.channel_id
        new_view.author_id = self.parent_view.author_id
        new_view.emoji_manager = self.emoji_manager
        await interaction.edit_original_response(embed=embed, view=new_view)


# ============================================================
# MODAL - UPLOAD DE IMAGEM
# ============================================================

class UploadImageModal(Modal):
    __slots__ = ("parent_view", "target", "map_index")
    
    def __init__(self, parent_view, target: str = "mapa", map_index: Optional[int] = None):
        super().__init__(title="📤 Upload de Imagem", timeout=300)
        self.parent_view = parent_view
        self.target = target
        self.map_index = map_index
        
        self.instruction = TextInput(
            label="📌 Instruções",
            placeholder="Use /upload para enviar a imagem",
            style=discord.TextStyle.paragraph,
            default="📌 Como fazer upload:\n1. Digite `/upload` no chat\n2. Anexe a imagem\n3. Copie a URL gerada\n4. Cole aqui!",
            required=False
        )
        self.add_item(self.instruction)
        
        self.image_url = TextInput(
            label="🌐 URL da imagem (após fazer upload)",
            placeholder="Cole a URL gerada pelo /upload aqui",
            style=discord.TextStyle.short,
            max_length=500,
            required=True
        )
        self.add_item(self.image_url)
    
    async def on_submit(self, interaction: discord.Interaction):
        url = self.image_url.value.strip()
        if not url:
            return await interaction.response.send_message("❌ URL vazia!", ephemeral=True)
        
        success, validated_url, error_msg = await _ImageValidator.validate_url(url)
        if not success:
            return await interaction.response.send_message(
                f"❌ URL inválida. Certifique-se de usar a URL do `/upload`.\n\n{error_msg}",
                ephemeral=True
            )
        
        if self.target == "thumbnail":
            self.parent_view.embed_data["thumbnail"] = validated_url
            await interaction.response.send_message("✅ Thumbnail atualizada!", ephemeral=True)
            await interaction.response.defer()
            embed = self.parent_view.build_final_embed()
            await interaction.edit_original_response(embed=embed, view=self.parent_view)
        
        elif self.target == "mapa" and self.map_index is not None:
            option = self.parent_view.options[self.map_index]
            option["image"] = validated_url
            option["service"] = "Upload"
            await self.parent_view.save_options(interaction.guild.id)
            await interaction.response.send_message(f"✅ Imagem do mapa **{option.get('name')}** atualizada!", ephemeral=True)
            await interaction.response.defer()
            embed = self.parent_view.build_options_embed()
            new_view = OptionsPanelView(self.parent_view)
            await interaction.edit_original_response(embed=embed, view=new_view)
        else:
            await interaction.response.send_message("✅ Imagem registrada!", ephemeral=True)


# ============================================================
# VIEW PRINCIPAL - EMBED BUILDER
# ============================================================

class EmbedBuilderView(View):
    __slots__ = ("bot", "match_system", "embed_data", "options", "guild_id", 
                 "channel_id", "author_id", "current_view", "message", "_loading",
                 "emoji_manager")
    
    def __init__(self, bot, embed_data: dict = None, match_type: str = "1v1"):
        super().__init__(timeout=600)
        self.bot = bot
        self.match_system = bot.match_system if hasattr(bot, 'match_system') else None
        
        self.embed_data = embed_data or {
            "title": "🏆 Nova Partida",
            "description": "**Escolha um mapa no menu abaixo para entrar na partida.**\n**Quando encher, a partida é criada automaticamente.**",
            "thumbnail": None,
            "color": 0x5865F2,
            "match_type": "1v1"
        }
        
        self.options = []
        self.guild_id = None
        self.channel_id = None
        self.author_id = None
        self.current_view = "main"
        self.message = None
        self._loading = False
        
        # 🔥 INICIALIZA GERENCIADOR DE EMOJIS DO GITHUB
        self.emoji_manager = GitHubEmojiManager(bot, EMOJI_SERVER_ID)
    
    def set_context(self, guild_id: str, channel_id: str, author_id: str):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.author_id = author_id
        if guild_id:
            settings = get_guild_settings(guild_id)
            saved_options = settings.get("ranked", {}).get("maps_options", [])
            if saved_options:
                self.options = saved_options
    
    async def save_options(self, guild_id: str):
        if guild_id:
            update_guild_settings(str(guild_id), "ranked.maps_options", self.options)
    
    async def refresh_main_panel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = self.build_final_embed()
        new_view = EmbedBuilderView(self.bot, self.embed_data)
        new_view.options = self.options
        new_view.guild_id = self.guild_id
        new_view.channel_id = self.channel_id
        new_view.author_id = self.author_id
        new_view.emoji_manager = self.emoji_manager
        await interaction.edit_original_response(embed=embed, view=new_view)
    
    def build_options_embed(self) -> discord.Embed:
        color = self.embed_data.get("color", 0x5865F2)
        embed = discord.Embed(
            title="🗺️ Gerenciar Mapas",
            description=(
                "🎨 Adicione mapas com **emoji** e opcionalmente uma **imagem**.\n\n"
                "**📌 EMOJIS DO GITHUB:**\n"
                "• Os emojis são sincronizados automaticamente do GitHub!\n"
                "• Use `:nome_do_emoji:` (ex: `:blockdash:`)\n"
                "• Funciona em QUALQUER servidor!\n\n"
                "**📌 Como adicionar imagem:**\n"
                "1️⃣ **URL direta:** Copie a URL da imagem\n"
                "2️⃣ **Upload:** Use o comando `/upload` ou **📤 Upload**\n\n"
                "✅ **URLs que funcionam:** Imgur, Discord, Pinterest\n"
                "❌ **Não funcionam:** Instagram, Facebook, TikTok"
            ),
            color=color,
            timestamp=datetime.utcnow()
        )
        
        if self.options:
            map_text = []
            for i, opt in enumerate(self.options, 1):
                name = opt.get("name", f"Mapa {i}")
                emoji = opt.get("emoji", "🗺️")
                has_image = "🖼️" if opt.get("image") else "📝"
                service = opt.get("service", "")
                service_text = f"({service})" if service else ""
                display_emoji = emoji if emoji else "🗺️"
                map_text.append(f"`{i:02d}` {display_emoji} **{name}** {has_image} {service_text}")
            embed.add_field(
                name=f"📋 Mapas Configurados ({len(self.options)}/25)",
                value="\n".join(map_text[:25]),
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Mapas Configurados (0/25)",
                value="*Nenhum mapa adicionado ainda*",
                inline=False
            )
        
        embed.set_footer(text="Clique em ➕ Adicionar Mapa para criar um novo")
        return embed

    def build_final_embed(self) -> discord.Embed:
        color = self.embed_data.get("color", 0x5865F2)
        match_type = self.embed_data.get("match_type", "1v1")
        
        title = self.embed_data.get("title", "🏆 Nova Partida")
        if not title.startswith(("🏆", "🎮", "⚔️", "👥", "🎯", "💀", "🔥", "⭐")):
            title = f"🎮 {title}"
        
        embed = discord.Embed(
            title=title,
            description=self.embed_data.get("description", "Escolha um mapa no menu abaixo."),
            color=color,
            timestamp=datetime.utcnow()
        )
        
        if self.embed_data.get("thumbnail"):
            embed.set_thumbnail(url=self.embed_data["thumbnail"])
        
        embed.add_field(name="🎮 Modo", value=MODE_NAMES.get(match_type, match_type), inline=True)
        embed.add_field(name="🗺️ Mapas Disponíveis", value=f"**{len(self.options)}** mapas configurados", inline=True)
        
        if self.options:
            map_lines = []
            for i, opt in enumerate(self.options[:8], 1):
                name = opt.get("name", f"Mapa {i}")
                emoji = opt.get("emoji", "🗺️")
                image = opt.get("image")
                if image:
                    map_lines.append(f"{emoji} **{name}** 🖼️")
                else:
                    map_lines.append(f"{emoji} `{name}`")
            embed.add_field(
                name="📋 Mapas",
                value="\n".join(map_lines) + (f"\n*+ {len(self.options)-8} outros*" if len(self.options) > 8 else ""),
                inline=False
            )
        else:
            embed.add_field(name="📋 Mapas", value="*Nenhum mapa configurado — use o botão 🗺️ Mapas*", inline=False)
        
        bot_name = self.bot.user.name if self.bot.user else "GT Ranked"
        bot_icon = self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty
        embed.set_footer(text=f"✨ {bot_name} • Partida {match_type}", icon_url=bot_icon)
        return embed

    # ============================================================
    # BOTÕES DO PAINEL
    # ============================================================

    @discord.ui.button(label="Título", style=ButtonStyle.primary, emoji="📌", row=0)
    async def edit_title(self, interaction: discord.Interaction, button: Button):
        modal = TitleModal(self, self.embed_data.get("title", ""))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Descrição", style=ButtonStyle.primary, emoji="📝", row=0)
    async def edit_description(self, interaction: discord.Interaction, button: Button):
        modal = DescriptionModal(self, self.embed_data.get("description", ""))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Thumbnail", style=ButtonStyle.primary, emoji="🖼️", row=0)
    async def edit_thumbnail(self, interaction: discord.Interaction, button: Button):
        modal = ThumbnailModal(self, self.embed_data.get("thumbnail", ""))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Cor", style=ButtonStyle.primary, emoji="🎨", row=0)
    async def edit_color(self, interaction: discord.Interaction, button: Button):
        view = ColorPickerView(self)
        await interaction.response.edit_message(embed=view.parent_view.build_final_embed(), view=view)
    
    @discord.ui.button(label="Mapas", style=ButtonStyle.success, emoji="🗺️", row=1)
    async def open_options(self, interaction: discord.Interaction, button: Button):
        if self._loading:
            return await interaction.response.send_message("⏳ Carregando...", ephemeral=True)
        self._loading = True
        try:
            await interaction.response.defer()
            embed = self.build_options_embed()
            view = OptionsPanelView(self)
            await interaction.edit_original_response(embed=embed, view=view)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Erro: {e}", ephemeral=True)
            except:
                pass
        finally:
            self._loading = False
    
    @discord.ui.select(
        placeholder="🎮 Selecione o modo de jogo",
        min_values=1,
        max_values=1,
        row=2,
        options=[
            SelectOption(label="⚔️ 1v1", value="1v1", description="Duelo individual", emoji="⚔️"),
            SelectOption(label="👥 2v2", value="2v2", description="Duplas", emoji="👥"),
            SelectOption(label="👨‍👩‍👦 3v3", value="3v3", description="Times completos", emoji="👨‍👩‍👦"),
            SelectOption(label="👨‍👩‍👧‍👦 4v4", value="4v4", description="Times grandes", emoji="👨‍👩‍👧‍👦"),
        ]
    )
    async def select_mode(self, interaction: discord.Interaction, select: Select):
        self.embed_data["match_type"] = select.values[0]
        embed = self.build_final_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ Modo alterado para: **{select.values[0]}**", ephemeral=True)
    
    @discord.ui.button(label="Publicar", style=ButtonStyle.success, emoji="📤", row=3)
    async def publish(self, interaction: discord.Interaction, button: Button):
        match_type = self.embed_data.get("match_type", "1v1")
        view = QueuePublishView(
            bot=self.bot,
            match_system=self.match_system,
            guild_id=str(interaction.guild.id),
            channel_id=str(interaction.channel.id),
            match_type=match_type,
            options=copy.deepcopy(self.options),
            embed_data=copy.deepcopy(self.embed_data),
        )
        view.update_select_options()
        embed = view.build_publish_embed()
        msg = await interaction.channel.send(embed=embed, view=view)
        view.message = msg
        await interaction.response.send_message("✅ Partida publicada com sucesso!", ephemeral=True)
    
    @discord.ui.button(label="Preview", style=ButtonStyle.secondary, emoji="👁️", row=3)
    async def preview(self, interaction: discord.Interaction, button: Button):
        embed = self.build_final_embed()
        await interaction.response.send_message("👁️ **Preview da partida:**", ephemeral=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Cancelar", style=ButtonStyle.danger, emoji="❌", row=3)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.stop()
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(title="❌ Cancelado", description="Criação cancelada!", color=0xff0000)
        await interaction.response.edit_message(embed=embed, view=self)


# ============================================================
# COMANDOS (PREFIXO + SLASH)
# ============================================================

# STUMBLE_MAPS padrão para fallback
STUMBLE_MAPS = [
    {"name": "Block Dash", "emoji": "🏃", "image": "https://i.imgur.com/8XxJt7z.png", "service": "Imgur"},
    {"name": "Block Dash Legendary", "emoji": "⭐", "image": "https://i.imgur.com/8XxJt7z.png", "service": "Imgur"},
    {"name": "Rush Hour", "emoji": "🚗"},
    {"name": "Laser Tracer", "emoji": "🔫"},
    {"name": "Laser Dash", "emoji": "⚡"},
    {"name": "Lava Land", "emoji": "🌋"},
    {"name": "Bot Bash", "emoji": "🤖"},
    {"name": "Honey Drop", "emoji": "🍯"},
    {"name": "Sharkmuda", "emoji": "🦈"},
    {"name": "The Other Side", "emoji": "🌌"},
]

def setup_embed_builder(bot):
    
    # ============================================================
    # COMANDO PREFIXO - SYNC EMOJIS
    # ============================================================
    
    @bot.command(name="syncemojis")
    @commands.has_permissions(administrator=True)
    async def sync_emojis_cmd(ctx):
        """Sincroniza emojis do GitHub com o servidor"""
        
        embed = discord.Embed(
            title="🔄 Sincronizando Emojis",
            description="⏳ Baixando emojis do GitHub...",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        msg = await ctx.send(embed=embed)
        
        # Cria o gerenciador
        manager = GitHubEmojiManager(bot, EMOJI_SERVER_ID)
        
        # Sincroniza
        results = await manager.sync_all_emojis()
        await manager.close()
        
        if "error" in results:
            return await msg.edit(
                embed=discord.Embed(
                    title="❌ Erro",
                    description=results["error"],
                    color=0xff0000
                )
            )
        
        # Mostra resultados
        success = [k for k, v in results.items() if v]
        failed = [k for k, v in results.items() if not v]
        
        embed = discord.Embed(
            title="✅ Sincronização Concluída!",
            description=(
                f"**✅ Sucesso:** {len(success)} emojis\n"
                f"**❌ Falhas:** {len(failed)} emojis"
            ),
            color=0x00ff00 if not failed else 0xffaa00,
            timestamp=datetime.utcnow()
        )
        
        if success:
            embed.add_field(
                name="✅ Emojis criados/sincronizados",
                value="\n".join([f":{e}:" for e in success[:20]]),
                inline=False
            )
        
        if failed:
            embed.add_field(
                name="❌ Emojis com falha",
                value="\n".join(failed[:20]) or "Nenhum",
                inline=False
            )
        
        await msg.edit(embed=embed)
    
    # ============================================================
    # COMANDO PREFIXO - EMOJI INFO
    # ============================================================
    
    @bot.command(name="emojis")
    async def emojis_cmd(ctx):
        """Mostra todos os emojis disponíveis do GitHub"""
        
        manager = GitHubEmojiManager(bot, EMOJI_SERVER_ID)
        await manager.fetch_config()
        
        embed = discord.Embed(
            title="📋 Emojis do GitHub",
            description="Emojis disponíveis para usar nos mapas:",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        guild = await manager._get_target_guild()
        
        for emoji_config in manager._config:
            name = emoji_config.get("name")
            map_name = emoji_config.get("map_name", name)
            filename = emoji_config.get("file", "")
            
            # Verifica se existe no servidor
            exists = False
            emoji_str = "❌"
            if guild:
                emoji = discord.utils.get(guild.emojis, name=name)
                if emoji:
                    exists = True
                    emoji_str = str(emoji)
            
            status = "✅" if exists else "❌"
            embed.add_field(
                name=f"{status} :{name}:",
                value=f"**Mapa:** {map_name}\n**Arquivo:** {filename}\n**Emoji:** {emoji_str}",
                inline=True
            )
        
        await manager.close()
        await ctx.send(embed=embed)
    
    # ============================================================
    # COMANDO PREFIXO - UPLOAD
    # ============================================================
    
    @bot.command(name="upload")
    async def prefix_upload(ctx):
        """Faz upload de imagem e retorna a URL com botão copiar"""
        if not ctx.message.attachments:
            return await ctx.send(
                "❌ Nenhum arquivo enviado!\n\n"
                "**Como usar:**\n"
                "1. Digite `%upload`\n"
                "2. Anexe a imagem na mensagem\n"
                "3. Envie!\n\n"
                "📌 A URL da imagem será gerada para você usar no painel."
            )
        
        attachment = ctx.message.attachments[0]
        success, url, error_msg = await _ImageValidator.validate_attachment(attachment)
        
        if not success:
            return await ctx.send(error_msg)
        
        embed = discord.Embed(
            title="📤 Upload Concluído!",
            description=(
                "✅ **Imagem enviada com sucesso!**\n\n"
                "**📋 URL da imagem:**\n"
                f"```\n{url}\n```\n\n"
                "**📌 Como usar:**\n"
                "• Clique em **📋 Copiar URL** para copiar\n"
                "• Volte ao painel e cole a URL"
            ),
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        embed.set_image(url=url)
        embed.set_footer(text="Copie a URL e cole no painel!")
        
        view = CopyUrlView(url)
        await ctx.send(embed=embed, view=view)
    
    # ============================================================
    # SLASH COMMAND - UPLOAD
    # ============================================================
    
    @bot.tree.command(name="upload", description="📤 Faça upload de uma imagem para usar no painel")
    @app_commands.describe(imagem="Anexe a imagem que deseja fazer upload")
    async def slash_upload(interaction: discord.Interaction, imagem: discord.Attachment = None):
        """Slash command para upload de imagem"""
        
        if not imagem:
            embed = discord.Embed(
                title="📤 Upload de Imagem",
                description=(
                    "❌ **Nenhuma imagem anexada!**\n\n"
                    "**Como usar:**\n"
                    "1. Digite `/upload`\n"
                    "2. Selecione a opção **imagem**\n"
                    "3. Anexe o arquivo\n"
                    "4. Envie!\n\n"
                    "📌 **Limites:**\n"
                    "• Máximo 5MB\n"
                    "• Formatos: JPG, PNG, GIF, WEBP, BMP, SVG"
                ),
                color=0xff0000,
                timestamp=datetime.utcnow()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        success, url, error_msg = await _ImageValidator.validate_attachment(imagem)
        
        if not success:
            embed = discord.Embed(
                title="❌ Upload Falhou",
                description=error_msg,
                color=0xff0000,
                timestamp=datetime.utcnow()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        embed = discord.Embed(
            title="📤 Upload Concluído!",
            description=(
                "✅ **Imagem enviada com sucesso!**\n\n"
                "**📋 URL da imagem:**\n"
                f"```\n{url}\n```\n\n"
                "**📌 Como usar:**\n"
                "• Clique em **📋 Copiar URL** para copiar\n"
                "• Volte ao painel e cole a URL"
            ),
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        embed.set_image(url=url)
        embed.set_footer(text="Copie a URL e cole no painel!")
        
        view = CopyUrlView(url)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    # ============================================================
    # COMANDO PREFIXO - EMBED
    # ============================================================
    
    @bot.command(name="embed")
    @commands.has_permissions(administrator=True)
    async def embed_cmd(ctx):
        view = EmbedBuilderView(bot)
        view.set_context(str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id))
        embed = view.build_final_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
    
    # ============================================================
    # COMANDO PREFIXO - PAINEL
    # ============================================================
    
    @bot.command(name="painel")
    async def painel_cmd(ctx):
        view = EmbedBuilderView(bot)
        view.set_context(str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id))
        
        embed = discord.Embed(
            title="🎫 Painel de Partidas",
            description=(
                "**Crie partidas personalizadas com estilo!**\n\n"
                "Use os botões abaixo para configurar todos os detalhes:\n"
                "📌 **Título** — Altere o título do embed\n"
                "📝 **Descrição** — Personalize a descrição\n"
                "🖼️ **Thumbnail** — Adicione uma imagem (URL ou upload!)\n"
                "🎨 **Cor** — Escolha a cor do embed\n"
                "🗺️ **Mapas** — Adicione mapas com emojis e imagens\n"
                "🎮 **Modo** — Selecione 1v1, 2v2, 3v3 ou 4v4\n\n"
                "Quando estiver pronto, clique em **📤 Publicar**!"
            ),
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📌 Como adicionar imagens e emojis (GITHUB!)",
            value=(
                "**1️⃣ URL Direta:**\n"
                "• Clique com **botão direito** na imagem\n"
                "• Selecione **'Abrir imagem em nova guia'**\n"
                "• Copie a URL (termina com .jpg, .png, .gif, .webp)\n"
                "• Cole no campo URL\n\n"
                "**2️⃣ Upload de Arquivo:**\n"
                "• Digite **`/upload`** ou **`%upload`** no chat\n"
                "• Anexe a imagem\n"
                "• Copie a URL gerada (botão **📋 Copiar URL**)\n"
                "• Cole no campo URL\n\n"
                "**3️⃣ Emojis do GitHub (CRUZAM SERVIDORES!):**\n"
                "• As imagens estão no repositório do GitHub\n"
                "• Use `:nome_do_emoji:` no campo emoji\n"
                "• Exemplo: `:blockdash:` ou `:arena:`\n"
                "• ✅ Funciona em QUALQUER servidor!\n"
                "• 🔄 Use `%syncemojis` para sincronizar\n\n"
                "✅ **URLs que funcionam:** Imgur, Discord, Pinterest\n"
                "❌ **Não funcionam:** Instagram, Facebook, TikTok"
            ),
            inline=False
        )
        
        bot_name = bot.user.name if bot.user else "GT Ranked"
        bot_icon = bot.user.display_avatar.url if bot.user else discord.Embed.Empty
        embed.set_footer(text=f"✨ {bot_name} • Sistema de Partidas", icon_url=bot_icon)
        
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


# ============================================================
# LIMPEZA (CHAMAR NO SHUTDOWN)
# ============================================================

async def cleanup_embed_builder():
    """Fecha conexões HTTP e limpa cache"""
    await _pool.close_all()
    await _cache.clear()
    gc.collect()
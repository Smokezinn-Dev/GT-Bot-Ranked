# ============================================================
# EMBED_BUILDER.PY - PAINEL MODERNO v6.0 (OTIMIZADO)
# ============================================================

import discord
from discord.ext import commands
from discord.ui import Button, View, Select, Modal, TextInput
from discord import ButtonStyle, SelectOption
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any
import copy
import asyncio
import re
import time
import gc
from urllib.parse import urlparse
import aiohttp
from asyncio import Semaphore

from database import get_guild_settings, update_guild_settings


# ============================================================
# CORES MODERNAS
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
    "title": "📌",
    "description": "📝",
    "thumbnail": "🖼️",
    "color": "🎨",
    "maps": "🗺️",
    "mode": "🎮",
    "publish": "📤",
    "preview": "👁️",
    "cancel": "❌",
    "back": "🔙",
    "add": "➕",
    "remove": "🗑️",
    "edit": "✏️",
    "save": "💾",
    "stumble": "🎲",
    "clear": "🧹",
    "loading": "⏳",
    "success": "✅",
    "error": "❌",
    "info": "ℹ️",
    "settings": "⚙️",
    "image": "🖼️",
    "link": "🔗",
    "url": "🌐",
    "embed": "📎",
}


# ============================================================
# SISTEMA DE IMAGENS OTIMIZADO (v2 - REALISTA)
# ============================================================

class ImageSessionPool:
    """Pool de sessões HTTP reutilizáveis"""
    __slots__ = ("_sessions", "_max_size", "_lock", "_semaphore")
    
    def __init__(self, max_size: int = 3):
        self._sessions: List[aiohttp.ClientSession] = []
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._semaphore = Semaphore(max_size * 2)
    
    async def get(self) -> aiohttp.ClientSession:
        async with self._lock:
            if self._sessions:
                return self._sessions.pop()
        
        connector = aiohttp.TCPConnector(
            limit=5,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=8, connect=5)
        return aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'image/webp,image/*,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9',
                'Cache-Control': 'no-cache',
            }
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


class ImageCache:
    """Cache LRU com TTL para URLs de imagem"""
    __slots__ = ("_data", "_maxsize", "_ttl", "_lock", "_hits", "_misses")
    
    def __init__(self, maxsize: int = 64, ttl: int = 3600):
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
    
    async def invalidate(self, url: str):
        async with self._lock:
            self._data.pop(url, None)
    
    async def clear(self):
        async with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0
            gc.collect()
    
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._data),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "0%"
        }


# Singleton
_pool = ImageSessionPool(max_size=3)
_cache = ImageCache(maxsize=64, ttl=3600)


class ImageValidator:
    """Validador realista de imagens - sem mágica"""
    
    # Extensões de imagem suportadas
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.tiff', '.ico', '.avif', '.heic'}
    
    # Serviços que SABEMOS que funcionam com URL direta
    KNOWN_SERVICES = {
        'i.imgur.com': {'name': 'Imgur', 'type': 'direct'},
        'imgur.com': {'name': 'Imgur', 'type': 'page'},
        'cdn.discordapp.com': {'name': 'Discord CDN', 'type': 'direct'},
        'media.discordapp.net': {'name': 'Discord Media', 'type': 'direct'},
        'cdn.discord.com': {'name': 'Discord CDN', 'type': 'direct'},
        'i.pinimg.com': {'name': 'Pinterest Direct', 'type': 'direct'},
    }
    
    @classmethod
    def _clean_url(cls, url: str) -> str:
        """Limpa URL de parâmetros problemáticos"""
        url = url.strip()
        # Remove parâmetros de rastreamento
        if '?' in url:
            # Mantém apenas parâmetros importantes para imagens
            parsed = urlparse(url)
            if parsed.path.lower().endswith(tuple(cls.IMAGE_EXTENSIONS)):
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return url
    
    @classmethod
    def _has_image_extension(cls, url: str) -> bool:
        """Verifica se a URL termina com extensão de imagem"""
        url_lower = url.lower()
        return any(url_lower.endswith(ext) for ext in cls.IMAGE_EXTENSIONS)
    
    @classmethod
    def _detect_service(cls, url: str) -> Optional[dict]:
        """Detecta serviço conhecido"""
        url_lower = url.lower()
        for domain, info in cls.KNOWN_SERVICES.items():
            if domain in url_lower:
                return info
        return None
    
    @classmethod
    async def _check_headers(cls, session: aiohttp.ClientSession, url: str) -> Tuple[bool, Optional[str]]:
        """Verifica headers com HEAD request"""
        try:
            async with session.head(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get('Content-Type', '').lower()
                    if content_type.startswith('image/'):
                        return True, url
                    if content_type.startswith('text/html'):
                        return False, None
                return False, None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False, None
    
    @classmethod
    async def _extract_imgur(cls, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Extrai URL direta do Imgur"""
        # Extrai ID
        match = re.search(r'(?:imgur\.com/)([a-zA-Z0-9]+)', url)
        if not match:
            return None
        
        image_id = match.group(1)
        # Tenta diferentes extensões
        for ext in ['.jpg', '.png', '.gif']:
            direct_url = f'https://i.imgur.com/{image_id}{ext}'
            success, _ = await cls._check_headers(session, direct_url)
            if success:
                return direct_url
        return None
    
    @classmethod
    async def validate(cls, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Valida e extrai URL de imagem.
        Retorna: (sucesso, url_imagem, mensagem_erro)
        """
        if not url or not isinstance(url, str):
            return False, None, "❌ URL vazia ou inválida."
        
        url = cls._clean_url(url)
        
        # 1. Verificar cache
        cached = await _cache.get(url)
        if cached:
            return True, cached, None
        
        # 2. Verificar se é URL direta de imagem (por extensão)
        if cls._has_image_extension(url):
            # Validação rápida com HEAD
            session = await _pool.get()
            try:
                success, _ = await cls._check_headers(session, url)
                if success:
                    await _cache.set(url, url)
                    return True, url, None
            finally:
                await _pool.release(session)
            # Se HEAD falhou, mas tem extensão, tenta mesmo assim
            await _cache.set(url, url)
            return True, url, None
        
        # 3. Serviços conhecidos
        service = cls._detect_service(url)
        if service:
            session = await _pool.get()
            try:
                # Imgur
                if 'imgur.com' in url.lower():
                    direct = await cls._extract_imgur(session, url)
                    if direct:
                        await _cache.set(url, direct)
                        return True, direct, None
                    return False, None, "❌ Não foi possível extrair a imagem do Imgur. Tente a URL direta da imagem."
                
                # Discord CDN - sempre funciona
                if 'discord' in url.lower():
                    await _cache.set(url, url)
                    return True, url, None
                
                # URL com extensão de imagem
                if cls._has_image_extension(url):
                    await _cache.set(url, url)
                    return True, url, None
            finally:
                await _pool.release(session)
        
        # 4. Tentativa genérica (apenas se for URL completa)
        if url.startswith(('http://', 'https://')):
            session = await _pool.get()
            try:
                success, validated_url = await cls._check_headers(session, url)
                if success and validated_url:
                    await _cache.set(url, validated_url)
                    return True, validated_url, None
            finally:
                await _pool.release(session)
        
        # 5. Se falhou tudo
        return False, None, (
            "❌ Não foi possível validar esta URL como imagem.\n\n"
            "**📌 Como obter uma URL direta de imagem:**\n"
            "1. Clique com o **botão direito** na imagem\n"
            "2. Selecione **'Abrir imagem em nova guia'**\n"
            "3. Copie a URL do navegador (termina com .jpg, .png, .gif, etc)\n"
            "4. Cole aqui!\n\n"
            "**✅ Serviços que funcionam:**\n"
            "• URLs diretas de imagem (.jpg, .png, .gif, .webp)\n"
            "• Imgur (URL da página ou direta)\n"
            "• Discord CDN (qualquer link do Discord)\n"
            "• Pinterest (APENAS URL direta i.pinimg.com)\n\n"
            "**❌ Não funcionam:**\n"
            "• Instagram, Facebook, TikTok, YouTube\n"
            "• Páginas com JavaScript/Cloudflare"
        )


# ============================================================
# MODAL - MAPA COM IMAGEM (OTIMIZADO)
# ============================================================

class MapWithImageModal(Modal):
    """Modal para adicionar/editar mapa com imagem"""
    
    def __init__(self, panel_view, option_index: Optional[int] = None, 
                 current_name: str = "", current_emoji: str = "", current_image: str = ""):
        super().__init__(title="🗺️ Configurar Mapa", timeout=300)
        self.panel_view = panel_view
        self.option_index = option_index
        self._validated_image = None
        
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
            label="🎨 Emoji do Mapa",
            placeholder="Ex: 🏃 ou ⭐",
            default=current_emoji,
            style=discord.TextStyle.short,
            max_length=10,
            required=False
        )
        self.add_item(self.emoji_input)
        
        self.image_input = TextInput(
            label="🖼️ URL da Imagem",
            placeholder="URL direta da imagem (termina com .jpg, .png, .gif, .webp)",
            default=current_image,
            style=discord.TextStyle.short,
            max_length=500,
            required=False
        )
        self.add_item(self.image_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()
        emoji = self.emoji_input.value.strip() or "🗺️"
        image_url = self.image_input.value.strip()
        
        if not name:
            return await interaction.response.send_message("❌ Nome é obrigatório!", ephemeral=True)
        
        option_data = {"name": name, "emoji": emoji}
        
        if image_url:
            # Validar imagem
            success, validated_url, error_msg = await ImageValidator.validate(image_url)
            
            if not success:
                return await interaction.response.send_message(error_msg, ephemeral=True)
            
            option_data["image"] = validated_url
            # Detecta serviço para exibição
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
            await interaction.response.send_message(f"✅ Mapa **{name}** atualizado!", ephemeral=True)
        else:
            self.panel_view.options.append(option_data)
            await interaction.response.send_message(f"✅ Mapa **{name}** adicionado!", ephemeral=True)
        
        await self.panel_view.save_options(interaction.guild.id)
        await self.panel_view.refresh_main_panel(interaction)


# ============================================================
# MODAL - THUMBNAIL (OTIMIZADO)
# ============================================================

class ThumbnailModal(Modal):
    def __init__(self, builder, current_url: str = ""):
        super().__init__(title="🖼️ Editar Thumbnail", timeout=300)
        self.builder = builder
        
        self.url_input = TextInput(
            label="URL da Imagem",
            placeholder="URL direta da imagem (termina com .jpg, .png, .gif, .webp)",
            default=current_url,
            style=discord.TextStyle.short,
            max_length=500,
            required=False
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value.strip()
        
        if url:
            success, validated_url, error_msg = await ImageValidator.validate(url)
            
            if not success:
                return await interaction.response.send_message(error_msg, ephemeral=True)
            
            self.builder.embed_data["thumbnail"] = validated_url
            
            # Mensagem de confirmação com serviço detectado
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
# MODAL - AÇÃO DO MAPA (OTIMIZADO)
# ============================================================

class MapActionModal(Modal):
    def __init__(self, parent_view, option_index: int, 
                 current_name: str, current_emoji: str, current_image: str = ""):
        super().__init__(title="⚙️ Editar Mapa", timeout=300)
        self.parent_view = parent_view
        self.option_index = option_index
        
        self.name_input = TextInput(
            label="📝 Nome do Mapa",
            default=current_name,
            style=discord.TextStyle.short,
            max_length=50,
            required=True
        )
        self.add_item(self.name_input)
        
        self.emoji_input = TextInput(
            label="🎨 Emoji",
            default=current_emoji or "🗺️",
            style=discord.TextStyle.short,
            max_length=10,
            required=False
        )
        self.add_item(self.emoji_input)
        
        self.image_input = TextInput(
            label="🖼️ URL da Imagem",
            default=current_image or "",
            placeholder="URL direta da imagem (termina com .jpg, .png, .gif, .webp)",
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
        emoji = self.emoji_input.value.strip() or "🗺️"
        image_url = self.image_input.value.strip()
        
        if action == "salvar":
            if not name:
                return await interaction.response.send_message("❌ Nome é obrigatório!", ephemeral=True)
            
            option_data = {"name": name, "emoji": emoji}
            
            if image_url:
                success, validated_url, error_msg = await ImageValidator.validate(image_url)
                
                if not success:
                    return await interaction.response.send_message(error_msg, ephemeral=True)
                
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
            await interaction.followup.send(f"✅ Mapa **{name}** salvo!", ephemeral=True)
            
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
# VIEW - SELETOR DE COR (OTIMIZADO)
# ============================================================

class ColorPickerView(View):
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
            await interaction.followup.send(
                f"✅ Cor atualizada para `#{color_value:06X}`!",
                ephemeral=True
            )
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
# VIEW - PUBLISH (OTIMIZADO)
# ============================================================

class QueuePublishView(View):
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
                    opts.append(SelectOption(
                        label="Nenhum mapa disponível",
                        value="none",
                        emoji="❌"
                    ))
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
        
        mode_names = {"1v1": "⚔️ Duelo", "2v2": "👥 Duplas", "3v3": "👨‍👩‍👦 Trio", "4v4": "👨‍👩‍👧‍👦 Quarteto"}
        embed.add_field(
            name="🎮 Modo",
            value=mode_names.get(self.match_type, self.match_type),
            inline=True
        )
        
        if self.options and self.match_system:
            map_lines = []
            for opt in self.options[:25]:
                name = opt.get("name", "Mapa")
                emoji = opt.get("emoji", "🗺️")
                status = self.match_system.get_queue_status(
                    self.guild_id, self.channel_id, self.match_type, name
                )
                # Mostra se tem imagem
                has_image = "🖼️" if opt.get("image") else ""
                map_lines.append(
                    f"{emoji} **{name}** {has_image}— `{status['count']}/{status['max']}` na fila"
                )
            embed.add_field(
                name="🗺️ Mapas e Filas",
                value="\n".join(map_lines),
                inline=False
            )
        else:
            embed.add_field(
                name="🗺️ Mapas",
                value="*Nenhum mapa configurado*",
                inline=False
            )
        
        embed.add_field(
            name="📋 Como Participar",
            value="1️⃣ Selecione um mapa no menu abaixo\n2️⃣ Clique em **Entrar na Fila**\n3️⃣ Aguarde a partida começar!",
            inline=False
        )
        
        bot_name = self.bot.user.name if self.bot.user else "GT Ranked"
        bot_icon = self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty
        embed.set_footer(
            text=f"✨ {bot_name} • Partida {self.match_type}",
            icon_url=bot_icon
        )
        
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

    @discord.ui.select(
        placeholder="🗺️ Selecione um mapa para entrar na fila",
        min_values=1,
        max_values=1,
        options=[]
    )
    async def select_map(self, interaction: discord.Interaction, select: Select):
        if not self.match_system:
            return await interaction.response.send_message("❌ Sistema indisponível.", ephemeral=True)

        if select.values[0] == "none":
            return await interaction.response.send_message("❌ Nenhum mapa disponível!", ephemeral=True)

        map_name = select.values[0]
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
# VIEW - PAINEL DE OPÇÕES (OTIMIZADO)
# ============================================================

class OptionsPanelView(View):
    def __init__(self, parent_view):
        super().__init__(timeout=600)
        self.parent_view = parent_view
        self._loading = False
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
                        options.append(
                            SelectOption(
                                label=f"{name[:35]}",
                                value=str(i),
                                emoji=emoji,
                                description=f"{has_image} {desc[:40]}"
                            )
                        )
                        if len(options) >= 25:
                            break
                else:
                    options.append(
                        SelectOption(
                            label="Nenhum mapa disponível",
                            value="none",
                            emoji="❌"
                        )
                    )
                child.options = options
                child.placeholder = "📋 Selecione um mapa para editar/remover"

    @discord.ui.button(label="🎲 Mapas Stumble", style=ButtonStyle.primary, emoji="🎲", row=0)
    async def add_stumble_maps(self, interaction: discord.Interaction, button: Button):
        if self._loading:
            return await interaction.response.send_message("⏳ Carregando...", ephemeral=True)
        
        self._loading = True
        try:
            await interaction.response.defer()
            
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
            
            self.parent_view.options = copy.deepcopy(STUMBLE_MAPS)
            await self.parent_view.save_options(interaction.guild.id)
            
            embed = self.parent_view.build_options_embed()
            new_view = OptionsPanelView(self.parent_view)
            await interaction.edit_original_response(embed=embed, view=new_view)
            await interaction.followup.send(f"✅ {len(STUMBLE_MAPS)} mapas do Stumble Guys adicionados!", ephemeral=True)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Erro: {e}", ephemeral=True)
            except:
                pass
        finally:
            self._loading = False

    @discord.ui.button(label="➕ Adicionar Mapa", style=ButtonStyle.success, emoji="➕", row=0)
    async def add_option(self, interaction: discord.Interaction, button: Button):
        modal = MapWithImageModal(self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.select(
        placeholder="📋 Selecione um mapa para editar/remover",
        min_values=1,
        max_values=1,
        row=1,
        options=[
            SelectOption(
                label="Nenhum mapa disponível",
                value="none",
                emoji="❌"
            )
        ]
    )
    async def select_option(self, interaction: discord.Interaction, select: Select):
        if not select.values or select.values[0] == "none":
            return await interaction.response.send_message("❌ Selecione um mapa válido!", ephemeral=True)
        
        index = int(select.values[0])
        if index >= len(self.parent_view.options):
            return await interaction.response.send_message("❌ Mapa não encontrado!", ephemeral=True)
        
        option = self.parent_view.options[index]
        
        modal = MapActionModal(
            self.parent_view,
            index,
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
        await interaction.edit_original_response(embed=embed, view=new_view)


# ============================================================
# VIEW PRINCIPAL - EMBED BUILDER (OTIMIZADO)
# ============================================================

class EmbedBuilderView(View):
    """View principal do construtor de embeds - Interface Moderna v6.0"""
    
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
    
    def build_options_embed(self) -> discord.Embed:
        color = self.embed_data.get("color", 0x5865F2)
        
        embed = discord.Embed(
            title="🗺️ Gerenciar Mapas",
            description=(
                "🎨 Adicione mapas com **emoji** e opcionalmente uma **imagem**.\n\n"
                "📌 **Como obter uma URL de imagem:**\n"
                "• Clique com **botão direito** na imagem\n"
                "• Selecione **'Abrir imagem em nova guia'**\n"
                "• Copie a URL (termina com .jpg, .png, .gif, .webp)\n\n"
                "✅ **Serviços que funcionam:**\n"
                "• URLs diretas de imagem\n"
                "• Imgur (URL da página ou direta)\n"
                "• Discord CDN (qualquer link do Discord)\n"
                "• Pinterest (APENAS URL direta i.pinimg.com)\n\n"
                "❌ **Não funcionam:**\n"
                "• Instagram, Facebook, TikTok, YouTube\n"
                "• Páginas com JavaScript/Cloudflare"
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
                map_text.append(f"`{i:02d}` {emoji} **{name}** {has_image} {service_text}")
            
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
        
        mode_names = {"1v1": "⚔️ Duelo", "2v2": "👥 Duplas", "3v3": "👨‍👩‍👦 Trio", "4v4": "👨‍👩‍👧‍👦 Quarteto"}
        embed.add_field(
            name="🎮 Modo",
            value=mode_names.get(match_type, match_type),
            inline=True
        )
        
        map_count = len(self.options)
        embed.add_field(
            name="🗺️ Mapas Disponíveis",
            value=f"**{map_count}** mapas configurados",
            inline=True
        )
        
        if self.options:
            map_lines = []
            for i, opt in enumerate(self.options[:8], 1):
                name = opt.get("name", f"Mapa {i}")
                emoji = opt.get("emoji", "🗺️")
                image = opt.get("image")
                service = opt.get("service", "")
                
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
            embed.add_field(
                name="📋 Mapas",
                value="*Nenhum mapa configurado — use o botão 🗺️ Mapas*",
                inline=False
            )
        
        bot_name = self.bot.user.name if self.bot.user else "GT Ranked"
        bot_icon = self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty
        embed.set_footer(
            text=f"✨ {bot_name} • Partida {match_type}",
            icon_url=bot_icon
        )
        
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
        embed = discord.Embed(
            title="❌ Cancelado",
            description="Criação cancelada!",
            color=0xff0000
        )
        await interaction.response.edit_message(embed=embed, view=self)


# ============================================================
# COMANDO - CRIAR PAINEL
# ============================================================

def setup_embed_builder(bot):
    @bot.command(name="embed")
    @commands.has_permissions(administrator=True)
    async def embed_cmd(ctx):
        view = EmbedBuilderView(bot)
        view.set_context(str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id))
        embed = view.build_final_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
    
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
                "🖼️ **Thumbnail** — Adicione uma imagem (URL direta!)\n"
                "🎨 **Cor** — Escolha a cor do embed\n"
                "🗺️ **Mapas** — Adicione mapas com emojis e imagens\n"
                "🎮 **Modo** — Selecione 1v1, 2v2, 3v3 ou 4v4\n\n"
                "Quando estiver pronto, clique em **📤 Publicar**!"
            ),
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📌 Como obter uma URL de imagem",
            value=(
                "1. Clique com **botão direito** na imagem\n"
                "2. Selecione **'Abrir imagem em nova guia'**\n"
                "3. Copie a URL (termina com .jpg, .png, .gif, .webp)\n"
                "4. Cole aqui!\n\n"
                "✅ **Funciona:** Imgur, Discord CDN, URLs diretas\n"
                "❌ **Não funciona:** Instagram, Facebook, TikTok, YouTube"
            ),
            inline=False
        )
        
        bot_name = bot.user.name if bot.user else "GT Ranked"
        bot_icon = bot.user.display_avatar.url if bot.user else discord.Embed.Empty
        embed.set_footer(text=f"✨ {bot_name} • Sistema de Partidas", icon_url=bot_icon)
        
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
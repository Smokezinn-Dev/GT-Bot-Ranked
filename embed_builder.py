# ============================================================
# EMBED_BUILDER.PY - PAINEL MODERNO v5.3
# ============================================================

import discord
from discord.ext import commands
from discord.ui import Button, View, Select, Modal, TextInput
from discord import ButtonStyle, SelectOption
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import copy
import asyncio
import re
import aiohttp
import io
import json
import time
from urllib.parse import urlparse, unquote, quote

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
    {"name": "Lavanda", "emoji": "🪻", "value": 0xB39DDB},
    {"name": "Marrom Café", "emoji": "☕", "value": 0x6D4C41},
]


# ============================================================
# ICONES E EMOJIS
# ============================================================

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
    "external": "🔗",
    "embed": "📎",
}


# ============================================================
# VALIDAÇÃO RÁPIDA DE URL DE IMAGEM
# ============================================================

# Padrões de URL de imagem (suporta TODOS os serviços)
IMAGE_URL_PATTERNS = [
    # Extensões comuns
    r'\.(png|jpg|jpeg|gif|webp|bmp|svg|ico|tiff|tif|heic|heif)(\?.*)?$',
    r'\.(png|jpg|jpeg|gif|webp|bmp|svg|ico|tiff|tif|heic|heif)/',
    # Serviços de imagem
    r'pinimg\.com',           # Pinterest
    r'imgur\.com',            # Imgur
    r'i\.imgur\.com',         # Imgur direto
    r'cdn\.discordapp\.com',  # Discord CDN
    r'media\.discordapp\.net',# Discord media
    r'gyazo\.com',            # Gyazo
    r'cdn\.cloudflare\.com',  # Cloudflare
    r'githubusercontent\.com',# GitHub
    r'ibb\.co',               # ImgBB
    r'postimg\.cc',           # PostImage
    r'images\.cdn\.',         # Vários CDNs
    r'cdn\.',                 # Qualquer CDN
    r'upload\.wikimedia\.org',# Wikimedia
    r'i\.redd\.it',          # Reddit
    r'preview\.redd\.it',     # Reddit preview
    r'cdn\.steamstatic\.com', # Steam
    r'cloudfront\.net',       # AWS CloudFront
    r's3\.amazonaws\.com',    # AWS S3
    r'drive\.google\.com',    # Google Drive
    r'dropbox\.com',          # Dropbox
    r'dropboxusercontent\.com', # Dropbox direto
    r'instagram\.com',        # Instagram
    r'cdninstagram\.com',     # Instagram CDN
    r'twimg\.com',            # Twitter/X
    r'pbs\.twimg\.com',       # Twitter CDN
    r'fbcdn\.net',            # Facebook
    r'cdn\.fbcdn\.com',       # Facebook CDN
    r'giphy\.com',            # Giphy
    r'cdn\.giphy\.com',       # Giphy CDN
    r'media\.giphy\.com',     # Giphy media
    r'tenor\.com',            # Tenor
    r'media\.tenor\.com',     # Tenor media
    r'tiktok\.com',           # TikTok
    r'tiktokcdn\.com',        # TikTok CDN
    r'ytimg\.com',            # YouTube
    r'ggpht\.com',            # Google Photos
    r'lh3\.googleusercontent\.com', # Google Photos
    r'googleusercontent\.com', # Google
    r'blogger\.com',          # Blogger
    r'blogspot\.com',         # Blogspot
    r'wordpress\.com',        # WordPress
    r'wp\.com',               # WordPress
    r'medium\.com',           # Medium
    r'cdn\.medium\.com',      # Medium CDN
    r'dev\.to',               # Dev.to
    r'res\.cloudinary\.com',  # Cloudinary
    r'cdn\.pixabay\.com',     # Pixabay
    r'cdn\.pexels\.com',      # Pexels
    r'images\.unsplash\.com', # Unsplash
    r'cdn\.wikimedia\.org',   # Wikimedia
    r'static\.wikimedia\.org',# Wikimedia
    r'commons\.wikimedia\.org', # Wikimedia Commons
    r'upload\.wikimedia\.org', # Wikimedia
    r'media\.cdn\.',          # Media CDN
    r'cdn\.discord\.',        # Discord
    r'cdn\.steam\.',          # Steam
    r'steamcdn\.',            # Steam CDN
    r'cdn\.twitch\.tv',       # Twitch
    r'static-cdn\.',          # Static CDN
]

def is_valid_image_url_quick(url: str) -> bool:
    """Validação rápida de URL de imagem"""
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower().strip()
    
    # Verifica padrões
    for pattern in IMAGE_URL_PATTERNS:
        if re.search(pattern, url_lower, re.IGNORECASE):
            return True
    
    return False


# ============================================================
# EXTRATOR UNIVERSAL DE IMAGENS
# ============================================================

class UniversalImageExtractor:
    """
    Extrator universal de imagens - suporta QUALQUER serviço!
    Extrai a URL da imagem de qualquer página que contenha uma imagem.
    """
    
    # Cache de URLs convertidas
    _cache: Dict[str, Dict] = {}  # {url: {"image_url": str, "timestamp": float}}
    _cache_ttl: int = 3600  # 1 hora
    
    # Serviços conhecidos
    SERVICES = {
        'pinterest.com': {'name': 'Pinterest', 'icon': '📌'},
        'pin.it': {'name': 'Pinterest', 'icon': '📌'},
        'imgur.com': {'name': 'Imgur', 'icon': '🖼️'},
        'i.imgur.com': {'name': 'Imgur', 'icon': '🖼️'},
        'instagram.com': {'name': 'Instagram', 'icon': '📸'},
        'cdninstagram.com': {'name': 'Instagram', 'icon': '📸'},
        'twitter.com': {'name': 'Twitter/X', 'icon': '🐦'},
        'x.com': {'name': 'Twitter/X', 'icon': '🐦'},
        'twimg.com': {'name': 'Twitter/X', 'icon': '🐦'},
        'facebook.com': {'name': 'Facebook', 'icon': '📘'},
        'fbcdn.net': {'name': 'Facebook', 'icon': '📘'},
        'tiktok.com': {'name': 'TikTok', 'icon': '🎵'},
        'youtube.com': {'name': 'YouTube', 'icon': '▶️'},
        'youtu.be': {'name': 'YouTube', 'icon': '▶️'},
        'ytimg.com': {'name': 'YouTube', 'icon': '▶️'},
        'ggpht.com': {'name': 'Google Photos', 'icon': '📷'},
        'drive.google.com': {'name': 'Google Drive', 'icon': '☁️'},
        'dropbox.com': {'name': 'Dropbox', 'icon': '📦'},
        'giphy.com': {'name': 'Giphy', 'icon': '🎬'},
        'tenor.com': {'name': 'Tenor', 'icon': '🎬'},
        'reddit.com': {'name': 'Reddit', 'icon': '🤖'},
        'redd.it': {'name': 'Reddit', 'icon': '🤖'},
        'github.com': {'name': 'GitHub', 'icon': '🐙'},
        'githubusercontent.com': {'name': 'GitHub', 'icon': '🐙'},
        'medium.com': {'name': 'Medium', 'icon': '✍️'},
        'dev.to': {'name': 'Dev.to', 'icon': '💻'},
        'unsplash.com': {'name': 'Unsplash', 'icon': '📷'},
        'pexels.com': {'name': 'Pexels', 'icon': '📷'},
        'pixabay.com': {'name': 'Pixabay', 'icon': '📷'},
        'cloudinary.com': {'name': 'Cloudinary', 'icon': '☁️'},
        'cloudflare.com': {'name': 'Cloudflare', 'icon': '☁️'},
        'wikimedia.org': {'name': 'Wikimedia', 'icon': '📚'},
        'blogger.com': {'name': 'Blogger', 'icon': '📝'},
        'blogspot.com': {'name': 'Blogspot', 'icon': '📝'},
        'wordpress.com': {'name': 'WordPress', 'icon': '📝'},
        'gyazo.com': {'name': 'Gyazo', 'icon': '🎯'},
        'ibb.co': {'name': 'ImgBB', 'icon': '🖼️'},
        'postimg.cc': {'name': 'PostImage', 'icon': '🖼️'},
        'steamstatic.com': {'name': 'Steam', 'icon': '🎮'},
        'twitch.tv': {'name': 'Twitch', 'icon': '🎮'},
        'cdn.twitch.tv': {'name': 'Twitch', 'icon': '🎮'},
    }
    
    @classmethod
    def _detect_service(cls, url: str) -> dict:
        """Detecta o serviço pela URL"""
        url_lower = url.lower()
        for domain, info in cls.SERVICES.items():
            if domain in url_lower:
                return info
        return {'name': 'Desconhecido', 'icon': '🔗'}
    
    @classmethod
    def _get_image_from_metadata(cls, html: str) -> Optional[str]:
        """Extrai URL da imagem de metadados do HTML"""
        patterns = [
            # Open Graph
            r'<meta property="og:image" content="([^"]+)"',
            r'<meta property="og:image:secure_url" content="([^"]+)"',
            r'<meta property="og:image:url" content="([^"]+)"',
            # Twitter Cards
            r'<meta name="twitter:image" content="([^"]+)"',
            r'<meta name="twitter:image:src" content="([^"]+)"',
            # Schema.org
            r'<meta itemprop="image" content="([^"]+)"',
            r'<meta itemprop="thumbnailUrl" content="([^"]+)"',
            # Outros
            r'"image":"([^"]+)"',
            r'"image_url":"([^"]+)"',
            r'"images":\["([^"]+)"',
            r'"imgUrl":"([^"]+)"',
            r'"thumbnail":"([^"]+)"',
            r'"thumbnailUrl":"([^"]+)"',
            r'"poster":"([^"]+)"',
            r'"cover":"([^"]+)"',
            r'"avatar":"([^"]+)"',
            r'"profileImage":"([^"]+)"',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                # Decodificar caracteres especiais
                url = unquote(url)
                # Limpar parâmetros problemáticos
                if '?' in url:
                    url = url.split('?')[0]
                if url and not url.startswith('data:'):
                    return url
        
        return None
    
    @classmethod
    def _get_image_from_json_ld(cls, html: str) -> Optional[str]:
        """Extrai URL da imagem de JSON-LD"""
        json_pattern = r'<script type="application/ld\+json">(.*?)</script>'
        for match in re.finditer(json_pattern, html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(match.group(1))
                
                def find_image(obj):
                    if isinstance(obj, dict):
                        # Verificar campos comuns
                        for key in ['image', 'thumbnail', 'thumbnailUrl', 'contentUrl', 'url', 'src']:
                            if key in obj:
                                val = obj[key]
                                if isinstance(val, str):
                                    if val.startswith('http') and not val.startswith('data:'):
                                        return val
                                if isinstance(val, dict) and 'url' in val:
                                    url = val['url']
                                    if url.startswith('http') and not url.startswith('data:'):
                                        return url
                                if isinstance(val, list) and val:
                                    first = val[0]
                                    if isinstance(first, str) and first.startswith('http'):
                                        return first
                                    if isinstance(first, dict) and 'url' in first:
                                        url = first['url']
                                        if url.startswith('http'):
                                            return url
                        # Procurar em @graph
                        if '@graph' in obj:
                            for item in obj['@graph']:
                                result = find_image(item)
                                if result:
                                    return result
                    return None
                
                result = find_image(data)
                if result:
                    return result
            except:
                pass
        
        return None
    
    @classmethod
    def _get_image_from_html(cls, html: str) -> Optional[str]:
        """Extrai URL da imagem do HTML"""
        # Procurar por tags de imagem
        img_patterns = [
            r'<img[^>]+src="([^"]+)"',
            r"<img[^>]+src='([^']+)'",
            r'<img[^>]+src=([^"\'\s>]+)',
        ]
        
        for pattern in img_patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for match in matches:
                url = match.group(1)
                if url and url.startswith('http') and not url.startswith('data:'):
                    # Verificar se é uma imagem válida
                    url_lower = url.lower()
                    if any(ext in url_lower for ext in ['.jpg', '.png', '.jpeg', '.gif', '.webp', '.svg']):
                        return url
        
        return None
    
    @classmethod
    def _get_image_from_style(cls, html: str) -> Optional[str]:
        """Extrai URL da imagem de CSS inline"""
        patterns = [
            r'background-image:\s*url\(["\']?([^"\')]+)["\']?\)',
            r'background:\s*url\(["\']?([^"\')]+)["\']?\)',
            r'content:\s*url\(["\']?([^"\')]+)["\']?\)',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for match in matches:
                url = match.group(1)
                if url and url.startswith('http') and not url.startswith('data:'):
                    return url
        
        return None
    
    @classmethod
    async def extract_image_url(cls, url: str, timeout: int = 10) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Extrai a URL da imagem de QUALQUER URL
        Retorna: (sucesso, url_imagem, mensagem_erro)
        """
        if not url:
            return False, None, "URL vazia"
        
        url = url.strip()
        
        # Verificar cache
        cache_key = url
        if cache_key in cls._cache:
            cache_data = cls._cache[cache_key]
            if time.time() - cache_data.get('timestamp', 0) < cls._cache_ttl:
                image_url = cache_data.get('image_url')
                if image_url:
                    return True, image_url, None
        
        # Detectar serviço
        service_info = cls._detect_service(url)
        service_name = service_info.get('name', 'Desconhecido')
        
        # Caso 1: URL já é uma imagem direta
        if is_valid_image_url_quick(url):
            cls._cache[cache_key] = {'image_url': url, 'timestamp': time.time(), 'service': service_name}
            return True, url, None
        
        # Caso 2: URL de página que contém imagem
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as response:
                    if response.status != 200:
                        return False, None, f"❌ Página não acessível (status {response.status})"
                    
                    html = await response.text()
                    
                    # Tentar extrair imagem de várias fontes
                    image_url = None
                    
                    # 1. Metadados (og:image, twitter:image, etc)
                    image_url = cls._get_image_from_metadata(html)
                    
                    # 2. JSON-LD
                    if not image_url:
                        image_url = cls._get_image_from_json_ld(html)
                    
                    # 3. HTML <img> tags
                    if not image_url:
                        image_url = cls._get_image_from_html(html)
                    
                    # 4. CSS inline
                    if not image_url:
                        image_url = cls._get_image_from_style(html)
                    
                    if image_url:
                        # Normalizar URL (se for relativa, completar)
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        elif image_url.startswith('/'):
                            parsed = urlparse(url)
                            image_url = f"{parsed.scheme}://{parsed.netloc}{image_url}"
                        
                        # Verificar se a URL é válida
                        if is_valid_image_url_quick(image_url):
                            cls._cache[cache_key] = {'image_url': image_url, 'timestamp': time.time(), 'service': service_name}
                            return True, image_url, None
                        
                        # Tentar fazer HEAD request para verificar
                        try:
                            async with session.head(image_url, allow_redirects=True) as img_response:
                                if img_response.status == 200:
                                    content_type = img_response.headers.get('Content-Type', '')
                                    if content_type.startswith(('image/', 'image')):
                                        cls._cache[cache_key] = {'image_url': image_url, 'timestamp': time.time(), 'service': service_name}
                                        return True, image_url, None
                        except:
                            pass
        
        except asyncio.TimeoutError:
            return False, None, f"⏳ Tempo esgotado ao acessar {service_name}"
        except aiohttp.ClientError as e:
            return False, None, f"❌ Erro ao acessar {service_name}: {str(e)[:100]}"
        except Exception as e:
            return False, None, f"❌ Erro inesperado: {str(e)[:100]}"
        
        # Se não conseguiu extrair
        return False, None, (
            f"❌ Não foi possível extrair a imagem do **{service_name}**.\n\n"
            "**Soluções:**\n"
            "1. Clique com o botão direito na imagem → 'Abrir imagem em nova guia'\n"
            "2. Copie a URL da imagem (termina com .jpg, .png, .gif, .webp, etc)\n"
            "3. Cole a URL da imagem diretamente\n\n"
            "**Ou tente uma das URLs abaixo:**\n"
            "• URL direta da imagem (ex: https://i.imgur.com/xxxxx.jpg)\n"
            "• URL do serviço (ex: https://instagram.com/p/xxxxx)\n"
            "• URL de qualquer página com imagem"
        )
    
    @classmethod
    def get_service_info(cls, url: str) -> dict:
        """Retorna informações do serviço de uma URL"""
        return cls._detect_service(url)


# ============================================================
# VALIDAÇÃO UNIVERSAL DE URL
# ============================================================

async def validate_and_extract_image(url: str, timeout: int = 10) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Valida e extrai URL de imagem de QUALQUER fonte
    Retorna: (sucesso, url_imagem, mensagem_erro)
    """
    if not url:
        return False, None, "URL vazia"
    
    # Usar o extrator universal
    return await UniversalImageExtractor.extract_image_url(url, timeout)


def get_service_name(url: str) -> str:
    """Retorna o nome do serviço da URL"""
    info = UniversalImageExtractor.get_service_info(url)
    return info.get('name', 'Desconhecido')


# ============================================================
# MODAL - MAPA COM IMAGEM (ATUALIZADO)
# ============================================================

class MapWithImageModal(Modal):
    """Modal para adicionar/editar mapa com imagem"""
    def __init__(self, panel_view, option_index: Optional[int] = None, 
                 current_name: str = "", current_emoji: str = "", current_image: str = ""):
        super().__init__(title="🗺️ Configurar Mapa", timeout=300)
        self.panel_view = panel_view
        self.option_index = option_index
        
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
            label="🖼️ URL da Imagem (QUALQUER serviço!)",
            placeholder="Ex: https://pinimg.com/... ou https://instagram.com/p/...",
            default=current_image,
            style=discord.TextStyle.short,
            max_length=500,
            required=False
        )
        self.add_item(self.image_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()
        emoji = self.emoji_input.value.strip() or "🗺️"
        image = self.image_input.value.strip() or None
        
        if not name:
            return await interaction.response.send_message("❌ Nome é obrigatório!", ephemeral=True)
        
        # Validação UNIVERSAL de imagem
        if image:
            success, extracted_url, error_msg = await validate_and_extract_image(image)
            
            if not success:
                return await interaction.response.send_message(error_msg, ephemeral=True)
            
            image = extracted_url
            service = get_service_name(image)
        else:
            service = None
        
        option_data = {"name": name, "emoji": emoji}
        if image:
            option_data["image"] = image
            if service:
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
# MODAL - THUMBNAIL (ATUALIZADO)
# ============================================================

class ThumbnailModal(Modal):
    def __init__(self, builder, current_url: str = ""):
        super().__init__(title="🖼️ Editar Thumbnail", timeout=300)
        self.builder = builder
        
        self.url_input = TextInput(
            label="URL da Imagem (QUALQUER serviço!)",
            placeholder="https://pinimg.com/... ou https://instagram.com/p/...",
            default=current_url,
            style=discord.TextStyle.short,
            max_length=500,
            required=False
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value.strip() or None
        if url:
            success, extracted_url, error_msg = await validate_and_extract_image(url)
            
            if not success:
                return await interaction.response.send_message(error_msg, ephemeral=True)
            
            url = extracted_url
            service = get_service_name(url)
            
            await interaction.response.send_message(
                f"✅ Imagem extraída do **{service}**!",
                ephemeral=True
            )
        
        self.builder.embed_data["thumbnail"] = url
        
        await interaction.response.defer()
        embed = self.builder.build_final_embed()
        await interaction.edit_original_response(embed=embed, view=self.builder)
        await interaction.followup.send(f"✅ Thumbnail atualizada!" if url else "✅ Thumbnail removida!", ephemeral=True)


# ============================================================
# MODAL - AÇÃO DO MAPA (ATUALIZADO)
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
            label="🖼️ URL da Imagem (QUALQUER serviço!)",
            default=current_image or "",
            placeholder="https://pinimg.com/... ou https://instagram.com/p/...",
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
        image = self.image_input.value.strip() or None
        
        if action == "salvar":
            option_data = {"name": name, "emoji": emoji}
            
            if image:
                success, extracted_url, error_msg = await validate_and_extract_image(image)
                
                if not success:
                    return await interaction.response.send_message(error_msg, ephemeral=True)
                
                image = extracted_url
                service = get_service_name(image)
                option_data["image"] = image
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
# VIEW - PAINEL DE OPÇÕES (ATUALIZADO)
# ============================================================

class OptionsPanelView(View):
    def __init__(self, parent_view: EmbedBuilderView):
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
# VIEW PRINCIPAL - EMBED BUILDER (COM SUPORTE UNIVERSAL)
# ============================================================

class EmbedBuilderView(View):
    """View principal do construtor de embeds - Interface Moderna"""
    
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
                "🎨 Adicione mapas com **emoji** e opcionalmente uma **imagem**.\n"
                "Mapas com imagem aparecem com destaque no painel!\n\n"
                "📌 **Suporte UNIVERSAL a QUALQUER serviço!**\n"
                "Pinterest, Instagram, Facebook, Twitter/X, TikTok, YouTube, "
                "Google Drive, Dropbox, Imgur, Giphy, Tenor, Reddit, GitHub, "
                "Cloudinary, e qualquer site com imagem!"
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
# VIEW - PUBLISH
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
                map_lines.append(
                    f"{emoji} **{name}** — `{status['count']}/{status['max']}` na fila"
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
# VIEW - SELETOR DE COR
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
                "🖼️ **Thumbnail** — Adicione uma imagem (QUALQUER serviço!)\n"
                "🎨 **Cor** — Escolha a cor do embed\n"
                "🗺️ **Mapas** — Adicione mapas com emojis e imagens\n"
                "🎮 **Modo** — Selecione 1v1, 2v2, 3v3 ou 4v4\n\n"
                "Quando estiver pronto, clique em **📤 Publicar**!"
            ),
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="✨ Suporte Universal a Imagens",
            value="Pinterest, Instagram, Facebook, Twitter/X, TikTok, YouTube, "
                  "Google Drive, Dropbox, Imgur, Giphy, Tenor, Reddit, GitHub, "
                  "Cloudinary, e **qualquer site com imagem**!",
            inline=False
        )
        
        bot_name = bot.user.name if bot.user else "GT Ranked"
        bot_icon = bot.user.display_avatar.url if bot.user else discord.Embed.Empty
        embed.set_footer(text=f"✨ {bot_name} • Sistema de Partidas", icon_url=bot_icon)
        
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
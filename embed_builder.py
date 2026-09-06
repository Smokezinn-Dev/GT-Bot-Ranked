# ============================================================
# EMBED_BUILDER.PY - PAINEL COMPLETO COM OPÇÕES/MAPAS
# ============================================================

import discord
from discord.ext import commands
from discord.ui import Button, View, Select, Modal, TextInput
from discord import ButtonStyle, SelectOption
from datetime import datetime
from typing import Optional, List, Dict
import copy

from database import get_guild_settings, update_guild_settings


# ============================================================
# MAPAS PADRÃO (STUMBLE GUYS)
# ============================================================

STUMBLE_MAPS = [
    {"name": "Block Dash", "emoji": "<:map_block_dash:1532553223213285568>"},
    {"name": "Block Dash Legendary", "emoji": "<:map_block_dash_legendary:1532553225499050134>"},
    {"name": "Rush Hour", "emoji": "<:map_rush_hour:1532553238279356547>"},
    {"name": "Laser Tracer", "emoji": "<:map_laser_tracer:1532553234261086361>"},
    {"name": "Laser Dash", "emoji": "<:map_laser_dash:1532553231807414273>"},
    {"name": "Lava Land", "emoji": "<:map_lava_land:1532553236555366571>"},
    {"name": "Bot Bash", "emoji": "<:map_bot_bash:1532553227885613106>"},
    {"name": "Honey Drop", "emoji": "<:map_honey_drop:1532553229987221554>"},
    {"name": "Sharkmuda", "emoji": "<:map_sharkmuda:1532553241257316512>"},
    {"name": "The Other Side", "emoji": "<:map_the_other_side:1532553243568115783>"},
]


# ============================================================
# MODAL - FORMULÁRIO DE OPÇÃO
# ============================================================

class OptionModal(Modal):
    """Modal para adicionar/editar opções"""
    def __init__(self, panel_view, option_index: Optional[int] = None, current_name: str = "", current_emoji: str = ""):
        super().__init__(title="✏️ Configurar Opção", timeout=300)
        self.panel_view = panel_view
        self.option_index = option_index
        
        self.name_input = TextInput(
            label="📝 Nome da Opção",
            placeholder="Ex: Block Dash, Arena, Castelo...",
            default=current_name,
            style=discord.TextStyle.short,
            max_length=50,
            required=True
        )
        self.add_item(self.name_input)
        
        self.emoji_input = TextInput(
            label="🎨 Emoji da Opção",
            placeholder="Ex: 🏰 ou <:map_block_dash:1532553223213285568>",
            default=current_emoji,
            style=discord.TextStyle.short,
            max_length=50,
            required=True
        )
        self.add_item(self.emoji_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()
        emoji = self.emoji_input.value.strip()
        
        if not name or not emoji:
            return await interaction.response.send_message("❌ Nome e emoji são obrigatórios!", ephemeral=True)
        
        if self.option_index is not None:
            self.panel_view.options[self.option_index] = {"name": name, "emoji": emoji}
            await interaction.response.send_message(f"✅ Opção **{name}** atualizada!", ephemeral=True)
        else:
            self.panel_view.options.append({"name": name, "emoji": emoji})
            await interaction.response.send_message(f"✅ Opção **{name}** adicionada!", ephemeral=True)
        
        await self.panel_view.save_options(interaction.guild.id)
        await self.panel_view.update_display(interaction)


# ============================================================
# PAINEL PRINCIPAL - VIEW
# ============================================================

class EmbedBuilderView(View):
    """View principal do construtor de embeds"""
    
    def __init__(self, bot, embed_data: dict = None, match_type: str = "1v1"):
        super().__init__(timeout=None)
        self.bot = bot
        self.match_system = bot.match_system if hasattr(bot, 'match_system') else None
        
        # Dados do embed
        self.embed_data = embed_data or {
            "title": "🏆 Nova Partida",
            "description": "**Escolha um mapa no menu abaixo para entrar na partida.**\n**Quando encher, a partida é criada automaticamente.**",
            "thumbnail": None,
            "color": 0x5865f2,
            "match_type": "1v1"
        }
        
        # Opções/Mapas
        self.options = []
        self.guild_id = None
        self.channel_id = None
        self.author_id = None
        
        # Estado
        self.current_view = "main"  # main, options
    
    def set_context(self, guild_id: str, channel_id: str, author_id: str):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.author_id = author_id
        
        # Carrega opções salvas do servidor
        if guild_id:
            settings = get_guild_settings(guild_id)
            saved_options = settings.get("ranked", {}).get("maps_options", [])
            if saved_options:
                self.options = saved_options
    
    async def save_options(self, guild_id: str):
        """Salva as opções no banco"""
        if guild_id:
            update_guild_settings(str(guild_id), "ranked.maps_options", self.options)
    
    # ============================================================
    # BOTÕES - MENU PRINCIPAL
    # ============================================================
    
    @discord.ui.button(label="✏️ Título", style=ButtonStyle.primary, emoji="✏️")
    async def edit_title(self, interaction: discord.Interaction, button: Button):
        modal = TitleModal(self, self.embed_data.get("title", ""))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📝 Descrição", style=ButtonStyle.primary, emoji="📝")
    async def edit_description(self, interaction: discord.Interaction, button: Button):
        modal = DescriptionModal(self, self.embed_data.get("description", ""))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🖼️ Thumbnail", style=ButtonStyle.primary, emoji="🖼️")
    async def edit_thumbnail(self, interaction: discord.Interaction, button: Button):
        modal = ThumbnailModal(self, self.embed_data.get("thumbnail", ""))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🗺️ Opções/Mapas", style=ButtonStyle.success, emoji="🗺️")
    async def open_options(self, interaction: discord.Interaction, button: Button):
        """Abre o painel de opções/mapas"""
        self.current_view = "options"
        await self.show_options_panel(interaction)
    
    # ============================================================
    # SELECT - MODO DE JOGO
    # ============================================================
    
    @discord.ui.select(
        placeholder="🎮 Selecione o modo de jogo",
        min_values=1,
        max_values=1,
        options=[
            SelectOption(label="⚔️ 1v1", value="1v1", description="Duelo individual", emoji="⚔️"),
            SelectOption(label="👥 2v2", value="2v2", description="Duplas", emoji="👥"),
            SelectOption(label="👨‍👩‍👦 3v3", value="3v3", description="Times completos", emoji="👨‍👩‍👦"),
            SelectOption(label="👨‍👩‍👧‍👦 4v4", value="4v4", description="Times grandes", emoji="👨‍👩‍👧‍👦"),
        ]
    )
    async def select_mode(self, interaction: discord.Interaction, select: Select):
        self.embed_data["match_type"] = select.values[0]
        await self.update_display(interaction)
        await interaction.response.send_message(f"✅ Modo alterado para: **{select.values[0]}**", ephemeral=True)
    
    # ============================================================
    # BOTÕES - AÇÕES FINAIS
    # ============================================================
    
    @discord.ui.button(label="📤 Publicar", style=ButtonStyle.success, emoji="📤")
    async def publish(self, interaction: discord.Interaction, button: Button):
        embed = self.build_embed()
        
        # Se tiver match_system, cria a partida
        if self.match_system and self.guild_id:
            await interaction.response.send_message("✅ Partida publicada! Use `%join` para entrar.", ephemeral=True)
            await interaction.channel.send(embed=embed)
        else:
            await interaction.channel.send(embed=embed)
            await interaction.response.send_message("✅ Embed publicado com sucesso!", ephemeral=True)
    
    @discord.ui.button(label="👁️ Preview", style=ButtonStyle.secondary, emoji="👁️")
    async def preview(self, interaction: discord.Interaction, button: Button):
        embed = self.build_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="❌ Cancelar", style=ButtonStyle.danger, emoji="❌")
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
    # MÉTODOS DO PAINEL DE OPÇÕES
    # ============================================================
    
    async def show_options_panel(self, interaction: discord.Interaction):
        """Mostra o painel de opções/mapas"""
        embed = self.build_options_embed()
        view = OptionsPanelView(self)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send("🗺️ Abriu o painel de opções!", ephemeral=True)
    
    def build_options_embed(self) -> discord.Embed:
        """Constrói o embed do painel de opções"""
        embed = discord.Embed(
            title="<:p_swords:1532553604911726682> Opções / Mapas",
            description="Cada opção precisa de **nome + emoji** para ficar bonita no painel.",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        if self.options:
            options_text = []
            for i, opt in enumerate(self.options, 1):
                name = opt.get("name", f"Opção {i}")
                emoji = opt.get("emoji", "📌")
                options_text.append(f"`{i}.` {emoji} **{name}**")
            
            embed.add_field(
                name="📋 Opções Configuradas",
                value="\n".join(options_text[:25]),
                inline=False
            )
            embed.add_field(
                name="📊 Total",
                value=f"**{len(self.options)}** opções",
                inline=True
            )
        else:
            embed.add_field(
                name="📋 Opções Configuradas",
                value="*Nenhuma opção adicionada ainda*",
                inline=False
            )
        
        embed.add_field(
            name="📌 Máximo",
            value="**25** opções",
            inline=True
        )
        
        embed.set_footer(text="Botify · Components V2 · efêmero")
        return embed
    
    # ============================================================
    # MÉTODOS DO EMBED PRINCIPAL
    # ============================================================
    
    def build_embed(self) -> discord.Embed:
        """Constrói o embed principal"""
        color = self.embed_data.get("color", 0x5865f2)
        match_type = self.embed_data.get("match_type", "1v1")
        
        embed = discord.Embed(
            title=self.embed_data.get("title", "🏆 Nova Partida"),
            description=self.embed_data.get("description", "Configure tudo e publique a partida no canal."),
            color=color,
            timestamp=datetime.utcnow()
        )
        
        # Thumbnail
        if self.embed_data.get("thumbnail"):
            embed.set_thumbnail(url=self.embed_data["thumbnail"])
        
        # Identidade
        embed.add_field(
            name="<:p_receipt:1532553542710329589> Identidade",
            value=(
                f"• **Título:** {self.embed_data.get('title', 'Nova Partida')}\n"
                f"• **Descrição:** {self.embed_data.get('description', '')[:100]}...\n"
                f"• **Thumbnail:** {self.embed_data.get('thumbnail', '_nenhuma_')}\n"
                f"• **Cor:** `#{color:06x}`"
            ),
            inline=False
        )
        
        # Modo
        embed.add_field(
            name="<:p_controller:1532553310005887060> Modo & entrada",
            value=(
                f"• **{match_type}** (time 1)\n"
                f"• Entrada: **select**"
            ),
            inline=False
        )
        
        # Opções
        if self.options:
            options_text = []
            for i, opt in enumerate(self.options[:10], 1):
                name = opt.get("name", f"Opção {i}")
                emoji = opt.get("emoji", "📌")
                options_text.append(f"{emoji} `{name}`")
            embed.add_field(
                name="<:p_swords:1532553604911726682> Opções",
                value="\n".join(options_text) or "*Nenhuma*",
                inline=False
            )
            embed.add_field(
                name="📊 Total",
                value=f"**{len(self.options)}** opções disponíveis",
                inline=True
            )
        else:
            embed.add_field(
                name="<:p_swords:1532553604911726682> Opções",
                value=f"_Nenhuma opção. Use <:p_plus:1532553526126055498> **Mapas Stumble** ou **Add opção**._",
                inline=False
            )
        
        embed.set_footer(text="Botify · Components V2 · efêmero")
        return embed
    
    async def update_display(self, interaction: discord.Interaction):
        """Atualiza o display do menu principal"""
        embed = self.build_embed()
        await interaction.message.edit(embed=embed, view=self)


# ============================================================
# PAINEL DE OPÇÕES - VIEW
# ============================================================

class OptionsPanelView(View):
    """View do painel de opções/mapas"""
    
    def __init__(self, parent_view: EmbedBuilderView):
        super().__init__(timeout=None)
        self.parent_view = parent_view
    
    # ============================================================
    # BOTÃO - MAPAS STUMBLE
    # ============================================================
    
    @discord.ui.button(label="🎲 Mapas Stumble", style=ButtonStyle.primary, emoji="🎲")
    async def add_stumble_maps(self, interaction: discord.Interaction, button: Button):
        """Adiciona os mapas do Stumble Guys"""
        self.parent_view.options = copy.deepcopy(STUMBLE_MAPS)
        await self.parent_view.save_options(interaction.guild.id)
        await self.parent_view.show_options_panel(interaction)
        await interaction.response.send_message(f"✅ {len(STUMBLE_MAPS)} mapas do Stumble Guys adicionados!", ephemeral=True)
    
    # ============================================================
    # BOTÃO - ADICIONAR OPÇÃO (ABRE FORMULÁRIO)
    # ============================================================
    
    @discord.ui.button(label="➕ Adicionar Opção", style=ButtonStyle.success, emoji="➕")
    async def add_option(self, interaction: discord.Interaction, button: Button):
        """Abre o formulário para adicionar opção"""
        modal = OptionModal(self.parent_view)
        await interaction.response.send_modal(modal)
    
    # ============================================================
    # SELECT - EDITAR/REMOVER OPÇÃO
    # ============================================================
    
    @discord.ui.select(
        placeholder="📋 Selecione uma opção para editar/remover",
        min_values=1,
        max_values=1,
        options=[]
    )
    async def select_option(self, interaction: discord.Interaction, select: Select):
        if not select.values or select.values[0] == "none":
            return await interaction.response.send_message("❌ Selecione uma opção válida!", ephemeral=True)
        
        index = int(select.values[0])
        if index >= len(self.parent_view.options):
            return await interaction.response.send_message("❌ Opção não encontrada!", ephemeral=True)
        
        option = self.parent_view.options[index]
        
        # Abre modal de ação (editar/remover)
        modal = OptionActionModal(
            self.parent_view,
            index,
            option.get("name", ""),
            option.get("emoji", "")
        )
        await interaction.response.send_modal(modal)
    
    # ============================================================
    # BOTÃO - LIMPAR TUDO
    # ============================================================
    
    @discord.ui.button(label="🧹 Limpar Tudo", style=ButtonStyle.danger, emoji="🧹")
    async def clear_all(self, interaction: discord.Interaction, button: Button):
        """Remove todas as opções"""
        self.parent_view.options = []
        await self.parent_view.save_options(interaction.guild.id)
        await self.parent_view.show_options_panel(interaction)
        await interaction.response.send_message("🧹 Todas as opções removidas!", ephemeral=True)
    
    # ============================================================
    # BOTÃO - VOLTAR
    # ============================================================
    
    @discord.ui.button(label="🔙 Voltar", style=ButtonStyle.secondary, emoji="🔙")
    async def back_to_main(self, interaction: discord.Interaction, button: Button):
        """Volta para o menu principal"""
        self.parent_view.current_view = "main"
        embed = self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
    
    # ============================================================
    # MÉTODOS AUXILIARES
    # ============================================================
    
    async def update_options_select(self):
        """Atualiza as opções do select"""
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                options = []
                for i, opt in enumerate(self.parent_view.options):
                    name = opt.get("name", f"Opção {i+1}")
                    emoji = opt.get("emoji", "📌")
                    options.append(
                        SelectOption(
                            label=f"{name[:45]}",
                            value=str(i),
                            emoji=emoji[:10] if emoji else None
                        )
                    )
                    if len(options) >= 25:
                        break
                
                if options:
                    child.options = options
                    child.placeholder = "📋 Selecione uma opção para editar/remover"
                else:
                    child.options = [
                        SelectOption(
                            label="Nenhuma opção disponível",
                            value="none",
                            emoji="❌"
                        )
                    ]
                    child.placeholder = "📋 Nenhuma opção disponível"


# ============================================================
# MODAL - AÇÃO DA OPÇÃO (EDITAR/REMOVER)
# ============================================================

class OptionActionModal(Modal):
    """Modal para editar ou remover uma opção"""
    
    def __init__(self, parent_view, option_index: int, current_name: str, current_emoji: str):
        super().__init__(title="⚙️ Ação da Opção", timeout=300)
        self.parent_view = parent_view
        self.option_index = option_index
        
        self.name_input = TextInput(
            label="📝 Nome da Opção",
            default=current_name,
            style=discord.TextStyle.short,
            max_length=50,
            required=True
        )
        self.add_item(self.name_input)
        
        self.emoji_input = TextInput(
            label="🎨 Emoji da Opção",
            default=current_emoji,
            style=discord.TextStyle.short,
            max_length=50,
            required=True
        )
        self.add_item(self.emoji_input)
        
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
        emoji = self.emoji_input.value.strip()
        
        if action == "salvar":
            self.parent_view.options[self.option_index] = {"name": name, "emoji": emoji}
            await self.parent_view.save_options(interaction.guild.id)
            await self.parent_view.show_options_panel(interaction)
            await interaction.response.send_message(f"✅ Opção **{name}** salva!", ephemeral=True)
            
        elif action == "remover":
            removed = self.parent_view.options.pop(self.option_index)
            await self.parent_view.save_options(interaction.guild.id)
            await self.parent_view.show_options_panel(interaction)
            await interaction.response.send_message(f"🗑️ Opção **{removed.get('name')}** removida!", ephemeral=True)
            
        else:
            await interaction.response.send_message("❌ Ação inválida! Use 'salvar' ou 'remover'", ephemeral=True)


# ============================================================
# MODAIS - TÍTULO, DESCRIÇÃO, THUMBNAIL
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
        await self.builder.update_display(interaction)
        await interaction.response.send_message(f"✅ Título atualizado para: **{self.title_input.value}**", ephemeral=True)


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
        await self.builder.update_display(interaction)
        await interaction.response.send_message(f"✅ Descrição atualizada!", ephemeral=True)


class ThumbnailModal(Modal):
    def __init__(self, builder, current_url: str = ""):
        super().__init__(title="🖼️ Editar Thumbnail", timeout=300)
        self.builder = builder
        
        self.url_input = TextInput(
            label="URL da Imagem",
            placeholder="https://exemplo.com/imagem.png",
            default=current_url,
            style=discord.TextStyle.short,
            max_length=500,
            required=False
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.builder.embed_data["thumbnail"] = self.url_input.value if self.url_input.value else None
        await self.builder.update_display(interaction)
        await interaction.response.send_message(f"✅ Thumbnail atualizada!" if self.url_input.value else "✅ Thumbnail removida!", ephemeral=True)


# ============================================================
# COMANDO - CRIAR PAINEL
# ============================================================

def setup_embed_builder(bot):
    """Configura o comando do painel"""
    
    @bot.command(name="embed")
    @commands.has_permissions(administrator=True)
    async def embed_cmd(ctx):
        """Cria o painel de construção de embeds"""
        view = EmbedBuilderView(bot)
        view.set_context(str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id))
        
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view)
    
    @bot.command(name="painel")
    async def painel_cmd(ctx):
        """Cria o painel de partidas (versão simplificada)"""
        view = EmbedBuilderView(bot)
        view.set_context(str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id))
        
        embed = discord.Embed(
            title="🎫 Painel de Partidas",
            description="Clique nos botões abaixo para configurar e criar sua partida.",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="📋 Como usar",
            value=(
                "1. ✏️ **Título** — Altere o título\n"
                "2. 📝 **Descrição** — Altere a descrição\n"
                "3. 🖼️ **Thumbnail** — Adicione uma imagem\n"
                "4. 🗺️ **Opções/Mapas** — Adicione mapas\n"
                "5. 🎮 **Modo** — Selecione 1v1, 2v2, 3v3\n"
                "6. 📤 **Publicar** — Envia a partida"
            ),
            inline=False
        )
        embed.set_footer(text="GT Ranked System v3.0")
        
        await ctx.send(embed=embed, view=view)
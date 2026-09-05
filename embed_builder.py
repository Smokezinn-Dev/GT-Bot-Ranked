# ============================================================
# EMBED_BUILDER.PY - CONSTRUTOR DE EMBED COMPLETO
# ============================================================

import discord
from discord.ui import Button, View, Modal, TextInput, Select
from datetime import datetime
from typing import Dict, List, Optional, Any

from database import get_guild_settings, update_guild_settings


# ============================================================
# DADOS DOS MAPAS (STUMBLE GUYS)
# ============================================================

STUMBLE_MAPS = [
    {"name": "Arena", "emoji": "🏰"},
    {"name": "Floresta", "emoji": "🌲"},
    {"name": "Castelo", "emoji": "🏯"},
    {"name": "Deserto", "emoji": "🏜️"},
    {"name": "Vulcão", "emoji": "🌋"},
    {"name": "Tundra", "emoji": "❄️"},
    {"name": "Cidade", "emoji": "🌃"},
    {"name": "Ilha", "emoji": "🏝️"},
    {"name": "Labirinto", "emoji": "🌀"},
    {"name": "Caverna", "emoji": "🕳️"},
]

MATCH_TYPES = ["1v1", "2v2", "3v3", "4v4"]


# ============================================================
# MODAL - FORMULÁRIO DE TÍTULO
# ============================================================

class TitleModal(Modal):
    def __init__(self, builder, current_title: str = ""):
        super().__init__(title="✏️ Editar Título", timeout=120)
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
        await self.builder.update_embed(interaction)
        await interaction.response.send_message(f"✅ Título atualizado para: **{self.title_input.value}**", ephemeral=True)


# ============================================================
# MODAL - FORMULÁRIO DE DESCRIÇÃO
# ============================================================

class DescriptionModal(Modal):
    def __init__(self, builder, current_desc: str = ""):
        super().__init__(title="✏️ Editar Descrição", timeout=120)
        self.builder = builder
        
        self.desc_input = TextInput(
            label="Descrição do Embed",
            placeholder="Ex: Configure tudo e publique neste canal!",
            default=current_desc,
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True
        )
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.builder.embed_data["description"] = self.desc_input.value
        await self.builder.update_embed(interaction)
        await interaction.response.send_message(f"✅ Descrição atualizada!", ephemeral=True)


# ============================================================
# MODAL - FORMULÁRIO DE THUMBNAIL
# ============================================================

class ThumbnailModal(Modal):
    def __init__(self, builder, current_url: str = ""):
        super().__init__(title="🖼️ Editar Thumbnail", timeout=120)
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
        await self.builder.update_embed(interaction)
        await interaction.response.send_message(f"✅ Thumbnail atualizada!" if self.url_input.value else "✅ Thumbnail removida!", ephemeral=True)


# ============================================================
# MODAL - ADICIONAR/EDITAR OPÇÃO
# ============================================================

class OptionModal(Modal):
    def __init__(self, builder, option_index: int = None, current_name: str = "", current_emoji: str = ""):
        super().__init__(title="✏️ Configurar Opção", timeout=120)
        self.builder = builder
        self.option_index = option_index
        
        self.name_input = TextInput(
            label="Nome da Opção",
            placeholder="Ex: Arena",
            default=current_name,
            style=discord.TextStyle.short,
            max_length=100,
            required=True
        )
        self.add_item(self.name_input)
        
        self.emoji_input = TextInput(
            label="Emoji da Opção (OBRIGATÓRIO)",
            placeholder="Ex: 🏰",
            default=current_emoji,
            style=discord.TextStyle.short,
            max_length=10,
            required=True
        )
        self.add_item(self.emoji_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.option_index is not None:
            # Editando opção existente
            self.builder.embed_data["options"][self.option_index] = {
                "name": self.name_input.value,
                "emoji": self.emoji_input.value
            }
            await self.builder.update_embed(interaction)
            await interaction.response.send_message(f"✅ Opção **{self.name_input.value}** atualizada!", ephemeral=True)
        else:
            # Nova opção
            self.builder.embed_data["options"].append({
                "name": self.name_input.value,
                "emoji": self.emoji_input.value
            })
            await self.builder.update_embed(interaction)
            await interaction.response.send_message(f"✅ Opção **{self.name_input.value}** adicionada!", ephemeral=True)


# ============================================================
# MODAL - AÇÃO (SALVAR/REMOVER)
# ============================================================

class ActionModal(Modal):
    def __init__(self, builder, option_index: int, current_name: str, current_emoji: str):
        super().__init__(title="⚙️ Ação da Opção", timeout=120)
        self.builder = builder
        self.option_index = option_index
        
        self.name_input = TextInput(
            label="Nome da Opção",
            default=current_name,
            style=discord.TextStyle.short,
            max_length=100,
            required=True
        )
        self.add_item(self.name_input)
        
        self.emoji_input = TextInput(
            label="Emoji da Opção",
            default=current_emoji,
            style=discord.TextStyle.short,
            max_length=10,
            required=True
        )
        self.add_item(self.emoji_input)
        
        self.action_input = TextInput(
            label="Ação (digite 'salvar' ou 'remover')",
            placeholder="salvar / remover",
            style=discord.TextStyle.short,
            max_length=10,
            required=True
        )
        self.add_item(self.action_input)

    async def on_submit(self, interaction: discord.Interaction):
        action = self.action_input.value.lower()
        
        if action == "salvar":
            self.builder.embed_data["options"][self.option_index] = {
                "name": self.name_input.value,
                "emoji": self.emoji_input.value
            }
            await self.builder.update_embed(interaction)
            await interaction.response.send_message(f"✅ Opção **{self.name_input.value}** salva!", ephemeral=True)
            
        elif action == "remover":
            removed = self.builder.embed_data["options"].pop(self.option_index)
            await self.builder.update_embed(interaction)
            await interaction.response.send_message(f"🗑️ Opção **{removed['name']}** removida!", ephemeral=True)
            
        else:
            await interaction.response.send_message("❌ Ação inválida! Use 'salvar' ou 'remover'", ephemeral=True)


# ============================================================
# VIEW - MENU PRINCIPAL
# ============================================================

class EmbedBuilderView(View):
    def __init__(self, builder, embed_data: dict, match_type: str = "1v1"):
        super().__init__(timeout=1800)
        self.builder = builder
        self.embed_data = embed_data
        self.match_type = match_type
        self.current_view = "main"  # main, options
        
        # Garante que os campos existem
        self.embed_data.setdefault("title", "🏆 Nova Partida")
        self.embed_data.setdefault("description", "Configure tudo e publique neste canal!")
        self.embed_data.setdefault("thumbnail", None)
        self.embed_data.setdefault("options", [])
        self.embed_data.setdefault("color", 0x00ff00)

    # ============================================================
    # BOTÕES - MENU PRINCIPAL
    # ============================================================

    @discord.ui.button(label="✏️ Título", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_title(self, interaction: discord.Interaction, button: Button):
        modal = TitleModal(self, self.embed_data.get("title", ""))
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📝 Descrição", style=discord.ButtonStyle.primary, emoji="📝")
    async def edit_description(self, interaction: discord.Interaction, button: Button):
        modal = DescriptionModal(self, self.embed_data.get("description", ""))
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🖼️ Thumbnail", style=discord.ButtonStyle.primary, emoji="🖼️")
    async def edit_thumbnail(self, interaction: discord.Interaction, button: Button):
        modal = ThumbnailModal(self, self.embed_data.get("thumbnail", ""))
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🗺️ Opções/Mapas", style=discord.ButtonStyle.success, emoji="🗺️")
    async def open_options(self, interaction: discord.Interaction, button: Button):
        self.current_view = "options"
        await self.builder.show_options_panel(interaction)

    # ============================================================
    # BOTÃO - MODO DE JOGO
    # ============================================================

    @discord.ui.select(
        placeholder="🎮 Selecione o modo de jogo",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="⚔️ 1v1", value="1v1", description="Duelo individual"),
            discord.SelectOption(label="👥 2v2", value="2v2", description="Duplas"),
            discord.SelectOption(label="👨‍👩‍👦 3v3", value="3v3", description="Times completos"),
            discord.SelectOption(label="👨‍👩‍👧‍👦 4v4", value="4v4", description="Times grandes"),
        ]
    )
    async def select_mode(self, interaction: discord.Interaction, select: Select):
        self.match_type = select.values[0]
        self.embed_data["match_type"] = self.match_type
        await self.builder.update_embed(interaction)
        await interaction.response.send_message(f"✅ Modo alterado para: **{self.match_type}**", ephemeral=True)

    # ============================================================
    # BOTÕES - AÇÕES FINAIS
    # ============================================================

    @discord.ui.button(label="📤 Publicar", style=discord.ButtonStyle.success, emoji="📤")
    async def publish(self, interaction: discord.Interaction, button: Button):
        embed = self.builder.build_embed()
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Embed publicado com sucesso!", ephemeral=True)

    @discord.ui.button(label="👁️ Preview", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def preview(self, interaction: discord.Interaction, button: Button):
        embed = self.builder.build_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Criação cancelada!", embed=None, view=self)

    # ============================================================
    # ATUALIZAR EMBED
    # ============================================================

    async def update_embed(self, interaction: discord.Interaction):
        embed = self.builder.build_embed()
        await interaction.message.edit(embed=embed, view=self)


# ============================================================
# VIEW - PAINEL DE OPÇÕES/MAPAS
# ============================================================

class OptionsPanelView(View):
    def __init__(self, builder, embed_data: dict):
        super().__init__(timeout=1800)
        self.builder = builder
        self.embed_data = embed_data
        self.embed_data.setdefault("options", [])

    # ============================================================
    # BOTÕES - OPÇÕES
    # ============================================================

    @discord.ui.button(label="🎲 Mapas Stumble", style=discord.ButtonStyle.primary, emoji="🎲")
    async def add_stumble_maps(self, interaction: discord.Interaction, button: Button):
        self.embed_data["options"] = STUMBLE_MAPS.copy()
        await self.builder.update_options_panel(interaction)
        await interaction.response.send_message(f"✅ {len(STUMBLE_MAPS)} mapas do Stumble Guys adicionados!", ephemeral=True)

    @discord.ui.button(label="➕ Adicionar Opção", style=discord.ButtonStyle.success, emoji="➕")
    async def add_option(self, interaction: discord.Interaction, button: Button):
        modal = OptionModal(self.builder)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🧹 Limpar", style=discord.ButtonStyle.danger, emoji="🧹")
    async def clear_options(self, interaction: discord.Interaction, button: Button):
        self.embed_data["options"] = []
        await self.builder.update_options_panel(interaction)
        await interaction.response.send_message("✅ Todas as opções removidas!", ephemeral=True)

    @discord.ui.button(label="🔙 Voltar", style=discord.ButtonStyle.secondary, emoji="🔙")
    async def back_to_main(self, interaction: discord.Interaction, button: Button):
        await self.builder.show_main_panel(interaction)

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
        if not select.values:
            return
        
        index = int(select.values[0])
        option = self.embed_data["options"][index]
        
        modal = ActionModal(
            self.builder,
            index,
            option.get("name", ""),
            option.get("emoji", "")
        )
        await interaction.response.send_modal(modal)

    async def update_options(self):
        """Atualiza as opções do select"""
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                options = []
                for i, opt in enumerate(self.embed_data.get("options", [])):
                    name = opt.get("name", f"Opção {i+1}")
                    emoji = opt.get("emoji", "📌")
                    options.append(
                        discord.SelectOption(
                            label=f"{name[:50]}",
                            value=str(i),
                            emoji=emoji
                        )
                    )
                if options:
                    child.options = options
                    child.placeholder = "📋 Selecione uma opção para editar/remover"
                else:
                    child.options = [
                        discord.SelectOption(
                            label="Nenhuma opção disponível",
                            value="none",
                            description="Adicione opções usando os botões acima"
                        )
                    ]
                    child.placeholder = "📋 Nenhuma opção disponível"


# ============================================================
# CLASSE PRINCIPAL - EMBED BUILDER
# ============================================================

class EmbedBuilder:
    def __init__(self, bot, embed_data: dict = None, message_id: str = None):
        self.bot = bot
        self.embed_data = embed_data or {
            "title": "🏆 Nova Partida",
            "description": "Configure tudo e publique neste canal!",
            "thumbnail": None,
            "options": [],
            "color": 0x00ff00,
            "match_type": "1v1"
        }
        self.message_id = message_id
        self.original_message = None
        self.main_view = None
        self.options_view = None

    def build_embed(self) -> discord.Embed:
        """Constrói o embed com os dados atuais"""
        color = self.embed_data.get("color", 0x00ff00)
        
        embed = discord.Embed(
            title=self.embed_data.get("title", "🏆 Nova Partida"),
            description=self.embed_data.get("description", "Configure tudo e publique neste canal!"),
            color=color,
            timestamp=datetime.utcnow()
        )
        
        # Thumbnail
        if self.embed_data.get("thumbnail"):
            embed.set_thumbnail(url=self.embed_data["thumbnail"])
        
        # Opções/Mapas
        options = self.embed_data.get("options", [])
        if options:
            options_text = "\n".join([
                f"{opt.get('emoji', '📌')} `{opt.get('name', 'Opção')}`"
                for opt in options[:20]
            ])
            embed.add_field(
                name="🗺️ Mapas Disponíveis",
                value=options_text,
                inline=False
            )
        
        # Modo de jogo
        match_type = self.embed_data.get("match_type", "1v1")
        embed.add_field(
            name="🎮 Modo",
            value=f"**{match_type}**",
            inline=True
        )
        
        # Contador de opções
        embed.add_field(
            name="📊 Total de Opções",
            value=f"**{len(options)}** mapas disponíveis",
            inline=True
        )
        
        embed.set_footer(text="Clique nos botões abaixo para configurar")
        
        return embed

    async def update_embed(self, interaction: discord.Interaction):
        """Atualiza o embed no menu principal"""
        embed = self.build_embed()
        view = self.main_view or EmbedBuilderView(self, self.embed_data)
        view.embed_data = self.embed_data
        await interaction.message.edit(embed=embed, view=view)

    async def update_options_panel(self, interaction: discord.Interaction):
        """Atualiza o painel de opções"""
        embed = self.build_options_embed()
        view = OptionsPanelView(self, self.embed_data)
        await view.update_options()
        self.options_view = view
        await interaction.message.edit(embed=embed, view=view)

    def build_options_embed(self) -> discord.Embed:
        """Constrói o embed do painel de opções"""
        options = self.embed_data.get("options", [])
        
        embed = discord.Embed(
            title="🗺️ Opções/Mapas",
            description="Cada opção deve conter um nome e um emoji para ficar bonito no painel!",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        # Preview das opções
        if options:
            preview = "\n".join([
                f"{opt.get('emoji', '📌')} `{opt.get('name', f'Opção {i+1}')}`"
                for i, opt in enumerate(options[:20])
            ])
            embed.add_field(
                name="📋 Preview das Opções",
                value=preview,
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Preview das Opções",
                value="*Nenhuma opção adicionada ainda*",
                inline=False
            )
        
        embed.add_field(
            name="📊 Estatísticas",
            value=f"**{len(options)}** opções configuradas",
            inline=True
        )
        
        embed.set_footer(text="Use os botões abaixo para gerenciar as opções")
        
        return embed

    async def show_main_panel(self, interaction: discord.Interaction):
        """Mostra o menu principal"""
        embed = self.build_embed()
        view = EmbedBuilderView(self, self.embed_data)
        self.main_view = view
        await interaction.message.edit(embed=embed, view=view)
        await interaction.response.send_message("🔙 Voltou ao menu principal!", ephemeral=True)

    async def show_options_panel(self, interaction: discord.Interaction):
        """Mostra o painel de opções"""
        embed = self.build_options_embed()
        view = OptionsPanelView(self, self.embed_data)
        await view.update_options()
        self.options_view = view
        await interaction.message.edit(embed=embed, view=view)
        await interaction.response.send_message("🗺️ Abriu o painel de opções!", ephemeral=True)


# ============================================================
# COMANDOS PARA ADICIONAR NO MAIN.PY
# ============================================================

# Estes comandos devem ser adicionados no main.py

async def setup(bot):
    """Setup do cog - não usado diretamente"""
    pass
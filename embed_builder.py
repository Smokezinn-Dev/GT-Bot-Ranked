# ============================================================
# EMBED_BUILDER.PY - PAINEL COMPLETO (FLUXO CORRIGIDO)
# ============================================================

import discord
from discord.ext import commands
from discord.ui import Button, View, Select, Modal, TextInput
from discord import ButtonStyle, SelectOption
from datetime import datetime
from typing import Optional, List, Dict
import copy
import asyncio

from database import get_guild_settings, update_guild_settings


# ============================================================
# MAPAS PADRÃO (STUMBLE GUYS) - EMOJIS NORMATIZADOS
# ============================================================

STUMBLE_MAPS = [
    {"name": "Block Dash", "emoji": "🏃"},
    {"name": "Block Dash Legendary", "emoji": "⭐"},
    {"name": "Rush Hour", "emoji": "🚗"},
    {"name": "Laser Tracer", "emoji": "🔫"},
    {"name": "Laser Dash", "emoji": "⚡"},
    {"name": "Lava Land", "emoji": "🌋"},
    {"name": "Bot Bash", "emoji": "🤖"},
    {"name": "Honey Drop", "emoji": "🍯"},
    {"name": "Sharkmuda", "emoji": "🦈"},
    {"name": "The Other Side", "emoji": "🌌"},
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
            placeholder="Ex: 🏰 ou ⭐",
            default=current_emoji,
            style=discord.TextStyle.short,
            max_length=10,
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
        # Recria a mensagem inteira
        await self.panel_view.refresh_main_panel(interaction)


# ============================================================
# PAINEL PRINCIPAL - VIEW
# ============================================================

class EmbedBuilderView(View):
    """View principal do construtor de embeds"""
    
    def __init__(self, bot, embed_data: dict = None, match_type: str = "1v1"):
        super().__init__(timeout=600)
        self.bot = bot
        self.match_system = bot.match_system if hasattr(bot, 'match_system') else None
        
        self.embed_data = embed_data or {
            "title": "🏆 Nova Partida",
            "description": "**Escolha um mapa no menu abaixo para entrar na partida.**\n**Quando encher, a partida é criada automaticamente.**",
            "thumbnail": None,
            "color": 0x5865f2,
            "match_type": "1v1"
        }
        
        self.options = []
        self.guild_id = None
        self.channel_id = None
        self.author_id = None
        self.current_view = "main"
        self._loading = False
        self.message = None  # Guarda referência da mensagem
    
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
        if self._loading:
            return await interaction.response.send_message("⏳ Carregando...", ephemeral=True)
        
        self._loading = True
        try:
            embed = self.build_options_embed()
            view = OptionsPanelView(self)
            
            # Edita a mensagem atual com o novo embed e view
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            # Fallback: se falhar, tenta enviar uma nova mensagem
            try:
                await interaction.response.send_message("❌ Erro ao abrir opções. Tente novamente.", ephemeral=True)
            except:
                pass
        finally:
            self._loading = False
    
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
        embed = self.build_final_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ Modo alterado para: **{select.values[0]}**", ephemeral=True)
    
    # ============================================================
    # BOTÕES - AÇÕES FINAIS
    # ============================================================
    
    @discord.ui.button(label="📤 Publicar", style=ButtonStyle.success, emoji="📤")
    async def publish(self, interaction: discord.Interaction, button: Button):
        """PUBLICA - só o embed final"""
        embed = self.build_final_embed()
        view = PublishView(self)
        
        # Atualiza o select do publish view com os mapas
        await view.update_map_select(self.options)
        
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Partida publicada com sucesso!", ephemeral=True)
    
    @discord.ui.button(label="👁️ Preview", style=ButtonStyle.secondary, emoji="👁️")
    async def preview(self, interaction: discord.Interaction, button: Button):
        """PREVIEW - mostra como vai ficar"""
        embed = self.build_final_embed()
        await interaction.response.send_message("👁️ **Preview da partida:**", ephemeral=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
    
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
    # MÉTODOS DE REFRESH
    # ============================================================
    
    async def refresh_main_panel(self, interaction: discord.Interaction):
        """Recria o painel principal após alterações"""
        embed = self.build_final_embed()
        # Recria a view principal
        new_view = EmbedBuilderView(self.bot, self.embed_data)
        new_view.options = self.options
        new_view.guild_id = self.guild_id
        new_view.channel_id = self.channel_id
        new_view.author_id = self.author_id
        
        # Se tiver uma mensagem salva, edita ela
        if self.message:
            try:
                await self.message.edit(embed=embed, view=new_view)
                return
            except:
                pass
        
        # Fallback: envia nova mensagem
        await interaction.edit_original_response(embed=embed, view=new_view)
    
    # ============================================================
    # MÉTODOS DO EMBED - VERSÃO FINAL
    # ============================================================
    
    def build_final_embed(self) -> discord.Embed:
        """Constrói o embed FINAL (o que vai ser publicado)"""
        color = self.embed_data.get("color", 0x5865f2)
        match_type = self.embed_data.get("match_type", "1v1")
        
        embed = discord.Embed(
            title=self.embed_data.get("title", "🏆 Nova Partida"),
            description=self.embed_data.get("description", "Escolha um mapa no menu abaixo para entrar na partida."),
            color=color,
            timestamp=datetime.utcnow()
        )
        
        if self.embed_data.get("thumbnail"):
            embed.set_thumbnail(url=self.embed_data["thumbnail"])
        
        embed.add_field(
            name="🎮 Modo",
            value=f"**{match_type}**",
            inline=True
        )
        
        if self.options:
            options_text = []
            for i, opt in enumerate(self.options[:10], 1):
                name = opt.get("name", f"Opção {i}")
                emoji = opt.get("emoji", "📌")
                options_text.append(f"{emoji} `{name}`")
            embed.add_field(
                name="🗺️ Mapas Disponíveis",
                value="\n".join(options_text) or "*Nenhum*",
                inline=False
            )
        else:
            embed.add_field(
                name="🗺️ Mapas Disponíveis",
                value="*Nenhum mapa configurado*",
                inline=False
            )
        
        bot_name = self.bot.user.name if self.bot.user else "GT Ranked"
        embed.set_footer(text=f"{bot_name} • Partida {match_type}")
        
        return embed
    
    def build_options_embed(self) -> discord.Embed:
        """Constrói o embed do painel de opções"""
        embed = discord.Embed(
            title="🗺️ Opções / Mapas",
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
        
        bot_name = self.bot.user.name if self.bot.user else "GT Ranked"
        embed.set_footer(text=f"{bot_name} • Gerenciamento de Mapas")
        
        return embed


# ============================================================
# VIEW - PUBLISH (APENAS SELECT + ENTRAR)
# ============================================================

class PublishView(View):
    """View que aparece na partida publicada"""
    
    def __init__(self, parent_view: EmbedBuilderView):
        super().__init__(timeout=None)
        self.parent_view = parent_view
    
    async def update_map_select(self, options: List[dict]):
        """Atualiza as opções do select"""
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                opts = []
                if options:
                    for opt in options[:25]:
                        opts.append(
                            SelectOption(
                                label=opt.get("name", "Mapa")[:45],
                                value=opt.get("name", "Mapa"),
                                emoji=opt.get("emoji", "🗺️")
                            )
                        )
                else:
                    opts.append(
                        SelectOption(
                            label="Nenhum mapa disponível",
                            value="none",
                            emoji="❌"
                        )
                    )
                child.options = opts
                child.placeholder = "🗺️ Selecione um mapa"
    
    @discord.ui.select(
        placeholder="🗺️ Selecione um mapa",
        min_values=1,
        max_values=1,
        options=[]
    )
    async def select_map(self, interaction: discord.Interaction, select: Select):
        if select.values[0] == "none":
            return await interaction.response.send_message("❌ Nenhum mapa disponível!", ephemeral=True)
        
        map_name = select.values[0]
        await interaction.response.send_message(f"✅ Mapa selecionado: **{map_name}**", ephemeral=True)
    
    @discord.ui.button(label="🎮 Entrar na Partida", style=ButtonStyle.success, emoji="🎮")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("✅ Você entrou na partida! Aguarde os outros jogadores.", ephemeral=True)


# ============================================================
# PAINEL DE OPÇÕES - VIEW
# ============================================================

class OptionsPanelView(View):
    """View do painel de opções/mapas"""
    
    def __init__(self, parent_view: EmbedBuilderView):
        super().__init__(timeout=600)
        self.parent_view = parent_view
        self._loading = False
    
    # ============================================================
    # BOTÃO - MAPAS STUMBLE
    # ============================================================
    
    @discord.ui.button(label="🎲 Mapas Stumble", style=ButtonStyle.primary, emoji="🎲")
    async def add_stumble_maps(self, interaction: discord.Interaction, button: Button):
        """Adiciona os mapas do Stumble Guys"""
        if self._loading:
            return await interaction.response.send_message("⏳ Carregando...", ephemeral=True)
        
        self._loading = True
        try:
            self.parent_view.options = copy.deepcopy(STUMBLE_MAPS)
            await self.parent_view.save_options(interaction.guild.id)
            
            embed = self.parent_view.build_options_embed()
            new_view = OptionsPanelView(self.parent_view)
            await interaction.response.edit_message(embed=embed, view=new_view)
            await interaction.followup.send(f"✅ {len(STUMBLE_MAPS)} mapas do Stumble Guys adicionados!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)
        finally:
            self._loading = False
    
    # ============================================================
    # BOTÃO - ADICIONAR OPÇÃO
    # ============================================================
    
    @discord.ui.button(label="➕ Adicionar Opção", style=ButtonStyle.success, emoji="➕")
    async def add_option(self, interaction: discord.Interaction, button: Button):
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
        self.parent_view.options = []
        await self.parent_view.save_options(interaction.guild.id)
        
        embed = self.parent_view.build_options_embed()
        new_view = OptionsPanelView(self.parent_view)
        await interaction.response.edit_message(embed=embed, view=new_view)
        await interaction.followup.send("🧹 Todas as opções removidas!", ephemeral=True)
    
    # ============================================================
    # BOTÃO - VOLTAR
    # ============================================================
    
    @discord.ui.button(label="🔙 Voltar", style=ButtonStyle.secondary, emoji="🔙")
    async def back_to_main(self, interaction: discord.Interaction, button: Button):
        """Volta para o menu principal"""
        embed = self.parent_view.build_final_embed()
        
        # Recria a view principal com os dados atuais
        new_view = EmbedBuilderView(self.parent_view.bot, self.parent_view.embed_data)
        new_view.options = self.parent_view.options
        new_view.guild_id = self.parent_view.guild_id
        new_view.channel_id = self.parent_view.channel_id
        new_view.author_id = self.parent_view.author_id
        
        await interaction.response.edit_message(embed=embed, view=new_view)
    
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
# MODAL - AÇÃO DA OPÇÃO
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
            max_length=10,
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
            
            embed = self.parent_view.build_options_embed()
            new_view = OptionsPanelView(self.parent_view)
            await interaction.response.edit_message(embed=embed, view=new_view)
            await interaction.followup.send(f"✅ Opção **{name}** salva!", ephemeral=True)
            
        elif action == "remover":
            removed = self.parent_view.options.pop(self.option_index)
            await self.parent_view.save_options(interaction.guild.id)
            
            embed = self.parent_view.build_options_embed()
            new_view = OptionsPanelView(self.parent_view)
            await interaction.response.edit_message(embed=embed, view=new_view)
            await interaction.followup.send(f"🗑️ Opção **{removed.get('name')}** removida!", ephemeral=True)
            
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
        embed = self.builder.build_final_embed()
        await interaction.response.edit_message(embed=embed, view=self.builder)
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
        embed = self.builder.build_final_embed()
        await interaction.response.edit_message(embed=embed, view=self.builder)
        await interaction.followup.send(f"✅ Descrição atualizada!", ephemeral=True)


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
        embed = self.builder.build_final_embed()
        await interaction.response.edit_message(embed=embed, view=self.builder)
        await interaction.followup.send(f"✅ Thumbnail atualizada!" if self.url_input.value else "✅ Thumbnail removida!", ephemeral=True)


# ============================================================
# COMANDO - CRIAR PAINEL
# ============================================================

def setup_embed_builder(bot):
    """Configura os comandos do painel"""
    
    @bot.command(name="embed")
    @commands.has_permissions(administrator=True)
    async def embed_cmd(ctx):
        """Cria o painel de construção de embeds"""
        view = EmbedBuilderView(bot)
        view.set_context(str(ctx.guild.id), str(ctx.channel.id), str(ctx.author.id))
        
        embed = view.build_final_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg  # Guarda referência
    
    @bot.command(name="painel")
    async def painel_cmd(ctx):
        """Cria o painel de partidas interativo"""
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
        bot_name = bot.user.name if bot.user else "GT Ranked"
        embed.set_footer(text=f"{bot_name} • Sistema de Partidas")
        
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
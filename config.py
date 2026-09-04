# ============================================================
# CONFIG.PY - CONFIGURAÇÃO COMPLETA COM CUSTOMIZAÇÃO TOTAL
# ============================================================

import os
from typing import Dict, Any, Optional, List
from datetime import datetime

class Config:
    """Sistema de configuração centralizado 100% customizável"""
    
    @staticmethod
    def get_env(key: str, default: Any = None) -> Any:
        return os.getenv(key, default)
    
    # ===== DISCORD =====
    @property
    def DISCORD_TOKEN(self) -> str:
        return self.get_env('DISCORD_TOKEN', 'MTQ1NjMxMTk2MTI3NjEyNTIwNg.GC3uIV.VQRu36MVjIWsXQ40QEZ2tX_GlKah49ZF7soD80')
    
    # ===== MONGODB =====
    @property
    def MONGODB_URI(self) -> str:
        return self.get_env(
            'MONGODB_URI',
            'mongodb+srv://gleicyferreira899_db_user:Q57eSQXyzUoWQxw4@cluster0.xhwrpcd.mongodb.net/?appName=Cluster0'
        )
    
    @property
    def DB_NAME(self) -> str:
        return self.get_env('DB_NAME', 'gt_bot')
    
    # ===== ECONOMIA (100% CUSTOMIZÁVEL) =====
    @property
    def ECONOMY_ENABLED(self) -> bool:
        return self.get_env('ECONOMY_ENABLED', 'true').lower() == 'true'
    
    @property
    def CURRENCY_NAME(self) -> str:
        return self.get_env('CURRENCY_NAME', 'Moedas')
    
    @property
    def CURRENCY_SYMBOL(self) -> str:
        return self.get_env('CURRENCY_SYMBOL', '💰')
    
    # ===== RANKED (CONTA PARA RANKING) =====
    @property
    def RANKED_WIN_BONUS(self) -> int:
        """Bônus por vitória no RANKED"""
        return int(self.get_env('RANKED_WIN_BONUS', '50'))
    
    @property
    def RANKED_LOSS_PENALTY(self) -> int:
        """Penalidade por derrota no RANKED"""
        return int(self.get_env('RANKED_LOSS_PENALTY', '10'))
    
    # ===== APOSTADO (NÃO CONTA PARA RANKING) =====
    @property
    def BETTING_ENABLED(self) -> bool:
        return self.get_env('BETTING_ENABLED', 'true').lower() == 'true'
    
    @property
    def BETTING_MIN_BET(self) -> int:
        """Aposta mínima (adm pode mudar via comando)"""
        return int(self.get_env('BETTING_MIN_BET', '100'))
    
    @property
    def BETTING_MAX_BET(self) -> int:
        """Aposta máxima (adm pode mudar via comando)"""
        return int(self.get_env('BETTING_MAX_BET', '10000'))
    
    @property
    def BETTING_WIN_MULTIPLIER(self) -> float:
        """Multiplicador do prêmio (ex: 2x = dobra a aposta)"""
        return float(self.get_env('BETTING_WIN_MULTIPLIER', '2.0'))
    
    @property
    def BETTING_TAX_PERCENT(self) -> float:
        """Taxa percentual sobre o prêmio (vai para o servidor)"""
        return float(self.get_env('BETTING_TAX_PERCENT', '5.0'))
    
    # ===== PRÊMIOS POR TOP =====
    @property
    def TOP_PRIZE_ENABLED(self) -> bool:
        return self.get_env('TOP_PRIZE_ENABLED', 'true').lower() == 'true'
    
    @property
    def TOP_1_PRIZE(self) -> int:
        """Prêmio para o 1º lugar"""
        return int(self.get_env('TOP_1_PRIZE', '10000'))
    
    @property
    def TOP_2_PRIZE(self) -> int:
        """Prêmio para o 2º lugar"""
        return int(self.get_env('TOP_2_PRIZE', '5000'))
    
    @property
    def TOP_3_PRIZE(self) -> int:
        """Prêmio para o 3º lugar"""
        return int(self.get_env('TOP_3_PRIZE', '2500'))
    
    @property
    def TOP_4_10_PRIZE(self) -> int:
        """Prêmio para o 4º ao 10º lugar"""
        return int(self.get_env('TOP_4_10_PRIZE', '1000'))
    
    @property
    def TOP_PRIZE_INTERVAL(self) -> int:
        """Intervalo em dias para distribuir prêmios"""
        return int(self.get_env('TOP_PRIZE_INTERVAL', '7'))
    
    # ===== SISTEMA DE RANK =====
    @property
    def MAX_PLAYERS(self) -> int:
        return int(self.get_env('MAX_PLAYERS', '6'))
    
    @property
    def MATCH_TYPES(self) -> List[str]:
        types = self.get_env('MATCH_TYPES', '1v1,2v2,3v3')
        return [t.strip() for t in types.split(',')]
    
    @property
    def MATCH_MAX_PLAYERS(self) -> Dict[str, int]:
        return {
            '1v1': 2,
            '2v2': 4,
            '3v3': 6
        }
    
    @property
    def MAX_MATCHES_PER_USER(self) -> int:
        return int(self.get_env('MAX_MATCHES_PER_USER', '3'))
    
    @property
    def LOBBY_TIMEOUT(self) -> int:
        return int(self.get_env('LOBBY_TIMEOUT', '600'))
    
    # ===== CACHE =====
    @property
    def CACHE_TTL(self) -> int:
        return int(self.get_env('CACHE_TTL', '60'))
    
    @property
    def DB_POOL_SIZE(self) -> int:
        return int(self.get_env('DB_POOL_SIZE', '5'))
    
    # ===== SEGURANÇA =====
    @property
    def ANTI_SPAM(self) -> bool:
        return self.get_env('ANTI_SPAM', 'true').lower() == 'true'
    
    @property
    def COOLDOWN_SECONDS(self) -> int:
        return int(self.get_env('COOLDOWN_SECONDS', '3'))
    
    @property
    def DM_NOTIFICATIONS(self) -> bool:
        return self.get_env('DM_NOTIFICATIONS', 'true').lower() == 'true'
    
    # ===== CUSTOMIZAÇÃO =====
    @property
    def EMBED_COLOR(self) -> int:
        return int(self.get_env('EMBED_COLOR', '0x00ff00'), 16)
    
    @property
    def EMBED_FOOTER(self) -> str:
        return self.get_env('EMBED_FOOTER', 'Rank System v3.0')
    
    @property
    def LOCALE(self) -> str:
        return self.get_env('LOCALE', 'pt-BR')
    
    @property
    def TICKET_NAME_TEMPLATE(self) -> str:
        return self.get_env('TICKET_NAME_TEMPLATE', '🎮-{tipo}-{match_id}')
    
    # ===== DISCLOUD =====
    @property
    def DISCLOUD_MODE(self) -> bool:
        return self.get_env('DISCLOUD', 'false').lower() == 'true'
    
    @property
    def RAM_LIMIT_MB(self) -> int:
        return int(self.get_env('RAM_LIMIT_MB', '100'))
    
    # ============================================================
    # MÉTODOS UTILITÁRIOS
    # ============================================================
    
    def get_all_configs(self) -> Dict[str, Any]:
        return {
            'discord_token': self.DISCORD_TOKEN[:10] + '...' if self.DISCORD_TOKEN != 'SEU_TOKEN_AQUI' else 'NÃO CONFIGURADO',
            'mongodb_uri': self.MONGODB_URI.split('@')[0] + '@...' if '@' in self.MONGODB_URI else 'NÃO CONFIGURADO',
            'db_name': self.DB_NAME,
            'currency_name': self.CURRENCY_NAME,
            'currency_symbol': self.CURRENCY_SYMBOL,
            'ranked_win_bonus': self.RANKED_WIN_BONUS,
            'ranked_loss_penalty': self.RANKED_LOSS_PENALTY,
            'betting_enabled': self.BETTING_ENABLED,
            'betting_min': self.BETTING_MIN_BET,
            'betting_max': self.BETTING_MAX_BET,
            'betting_multiplier': self.BETTING_WIN_MULTIPLIER,
            'betting_tax': self.BETTING_TAX_PERCENT,
            'top_prize_enabled': self.TOP_PRIZE_ENABLED,
            'top_1_prize': self.TOP_1_PRIZE,
            'top_2_prize': self.TOP_2_PRIZE,
            'top_3_prize': self.TOP_3_PRIZE,
            'top_4_10_prize': self.TOP_4_10_PRIZE,
            'top_prize_interval': self.TOP_PRIZE_INTERVAL,
            'match_types': self.MATCH_TYPES,
            'max_players': self.MAX_PLAYERS,
            'cache_ttl': self.CACHE_TTL,
            'embed_color': self.EMBED_COLOR,
            'embed_footer': self.EMBED_FOOTER,
            'discloud_mode': self.DISCLOUD_MODE,
            'ram_limit_mb': self.RAM_LIMIT_MB
        }
    
    def validate(self) -> bool:
        errors = []
        if not self.DISCORD_TOKEN or self.DISCORD_TOKEN == 'SEU_TOKEN_AQUI':
            errors.append("❌ DISCORD_TOKEN não configurado!")
        if errors:
            for error in errors:
                print(error)
            return False
        print("✅ Configurações validadas com sucesso!")
        return True
    
    def print_config_summary(self):
        print("\n" + "="*50)
        print("📋 RESUMO DE CONFIGURAÇÕES")
        print("="*50)
        configs = self.get_all_configs()
        for key, value in configs.items():
            print(f"• {key.replace('_', ' ').title()}: {value}")
        print("="*50)
        print(f"🔧 Modo: {'Discloud' if self.DISCLOUD_MODE else 'Local'}")
        print(f"💾 RAM: {self.RAM_LIMIT_MB}MB")
        print("="*50)

config = Config()

def init_config():
    print("🚀 INICIALIZANDO CONFIGURAÇÃO...")
    if config.DISCLOUD_MODE:
        print("✅ Modo Discloud detectado!")
    if not config.validate():
        raise ValueError("❌ Configuração inválida!")
    config.print_config_summary()
    return config

class DiscloudHealth:
    @staticmethod
    def get_ram_usage() -> int:
        try:
            import psutil
            return psutil.Process().memory_info().rss // 1024 // 1024
        except:
            return 0
    
    @staticmethod
    def is_healthy(ram_limit: int = 100) -> bool:
        ram_usage = DiscloudHealth.get_ram_usage()
        if ram_usage > ram_limit * 0.85:
            print(f"⚠️ ALERTA: Uso de RAM alto: {ram_usage}MB")
            return False
        return True
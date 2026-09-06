# ============================================================
# OPTIMIZER.PY - OTIMIZAÇÕES GLOBAIS
# ============================================================

import gc
import time
import asyncio
import logging
from typing import Optional

_logger = logging.getLogger("Optimizer")

class GlobalOptimizer:
    """Gerenciador de otimizações globais"""
    __slots__ = ("_running", "_interval", "_task", "_last_gc", "_last_cache_clean")
    
    def __init__(self, interval: int = 300):
        self._running = False
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._last_gc = 0
        self._last_cache_clean = 0
    
    async def start(self):
        """Inicia o otimizador"""
        if self._running:
            return

        # Aplica o threshold de GC configurado (reduz frequência de coletas
        # menores, que são o que mais pesa em bots com muitos objetos vivos)
        try:
            from config import GC_THRESHOLD
            gc.set_threshold(*GC_THRESHOLD)
        except Exception:
            pass

        # Congela os objetos já carregados no import/startup (discord.py,
        # pymongo, etc). Eles ficam de fora das coletas de geração 0/1 pro
        # resto da vida do processo, então o GC passa a varrer muito menos
        # objeto por ciclo. Só vale a pena fazer isso UMA vez, no boot.
        gc.collect()
        gc.freeze()

        self._running = True
        self._task = asyncio.create_task(self._run())
        _logger.info("✅ Optimizer started")
    
    async def stop(self):
        """Para o otimizador"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _logger.info("⏹️ Optimizer stopped")
    
    async def _run(self):
        """Loop principal do otimizador"""
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._optimize()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _logger.error(f"Optimizer error: {e}")
    
    async def _optimize(self):
        """Executa otimizações"""
        now = time.monotonic()
        
        # 1. Garbage Collection (a cada 5 min)
        if now - self._last_gc > 300:
            gc.collect()
            gc.collect()
            self._last_gc = now
            _logger.debug("🧹 GC executed")
        
        # 2. Limpa caches do database (a cada 10 min)
        if now - self._last_cache_clean > 600:
            try:
                from database import clear_all_caches
                clear_all_caches()
                self._last_cache_clean = now
                _logger.debug("🧹 Cache cleaned")
            except Exception:
                pass
        
        # 3. Fecha a conexão com o Mongo se estiver ociosa há muito tempo
        #    (libera as threads internas do driver; reconecta sozinho depois)
        try:
            from database import cleanup_idle_connection
            cleanup_idle_connection()
        except Exception:
            pass

        # 4. Verifica saúde do banco (só loga, não força reconexão)
        try:
            from database import check_db_health
            if not check_db_health():
                _logger.warning("⚠️ DB health check failed")
        except Exception:
            pass

        # 5. Yield para o event loop
        await asyncio.sleep(0)

# Singleton
_optimizer = GlobalOptimizer()

async def start_optimizer():
    await _optimizer.start()

async def stop_optimizer():
    await _optimizer.stop()

def force_gc():
    """Força garbage collection imediata"""
    gc.collect()
    gc.collect()
    try:
        from database import clear_all_caches
        clear_all_caches()
    except Exception:
        pass
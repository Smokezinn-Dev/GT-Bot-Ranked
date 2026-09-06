# ============================================================
# OPTIMIZER.PY - OTIMIZAÇÕES GLOBAIS (EXTREMO)
# ============================================================

import gc
import time
import asyncio
import logging
from typing import Optional
import sys

_logger = logging.getLogger("Optimizer")

class GlobalOptimizer:
    """Gerenciador de otimizações globais com monitoramento inteligente"""
    __slots__ = ("_running", "_interval", "_task", "_last_gc", "_last_cache_clean", "_last_memory_check", "_last_db_check")
    
    def __init__(self, interval: int = 300):
        self._running = False
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._last_gc = 0
        self._last_cache_clean = 0
        self._last_memory_check = 0
        self._last_db_check = 0
    
    async def start(self):
        if self._running:
            return

        # Aplica threshold de GC otimizado
        try:
            from config import GC_THRESHOLD
            gc.set_threshold(*GC_THRESHOLD)
        except Exception:
            gc.set_threshold(700, 10, 10)

        # Congela objetos do import
        gc.collect()
        gc.freeze()

        self._running = True
        self._task = asyncio.create_task(self._run())
        _logger.info("✅ Optimizer started")
    
    async def stop(self):
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
        """Loop principal com intervalo adaptativo"""
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._optimize()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _logger.error(f"Optimizer error: {e}")
                await asyncio.sleep(10)
    
    async def _optimize(self):
        now = time.monotonic()
        
        # 1. GC a cada 5 min (ou se threshold for atingido)
        if now - self._last_gc > 300 or gc.get_count()[0] > 700:
            gc.collect()
            gc.collect()
            self._last_gc = now
            _logger.debug("🧹 GC executed")
        
        # 2. Limpa caches a cada 10 min
        if now - self._last_cache_clean > 600:
            try:
                from database import clear_all_caches
                clear_all_caches()
                self._last_cache_clean = now
                _logger.debug("🧹 Cache cleaned")
            except Exception:
                pass
        
        # 3. Fecha conexão idle do Mongo
        try:
            from database import cleanup_idle_connection
            cleanup_idle_connection()
        except Exception:
            pass
        
        # 4. Health check do DB a cada 30 min
        if now - self._last_db_check > 1800:
            try:
                from database import check_db_health
                if not check_db_health():
                    _logger.warning("⚠️ DB health check failed")
                self._last_db_check = now
            except Exception:
                pass
        
        # 5. Monitor de memória (mais frequente)
        if now - self._last_memory_check > 300:
            try:
                import psutil
                mem = psutil.Process().memory_info()
                mem_mb = mem.rss / 1024 / 1024
                if mem_mb > 450:
                    gc.collect()
                    gc.collect()
                    _logger.warning(f"🧹 Memory forced: {mem_mb:.1f}MB")
                self._last_memory_check = now
            except Exception:
                pass
        
        # 6. Yield para event loop
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
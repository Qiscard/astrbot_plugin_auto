"""
简化的定时任务调度器
"""
import asyncio
import time
from typing import Callable
from astrbot import logger


class SimpleScheduler:
    """简单的定时任务调度器"""

    def __init__(self):
        self.task: asyncio.Task | None = None
        self.func: Callable | None = None
        self.interval: int = 60
        self.enabled: bool = False
        self.hourly_mode: bool = False

    def set_task(self, func: Callable, interval: int, enabled: bool = True, hourly_mode: bool = False):
        """设置定时任务

        Args:
            func: 要执行的函数
            interval: 间隔秒数
            enabled: 是否启用
            hourly_mode: 整点模式，在满足条件的第0秒执行
        """
        self.func = func
        self.interval = interval
        self.enabled = enabled
        self.hourly_mode = hourly_mode

    def start(self):
        """启动定时任务"""
        if not self.enabled or not self.func:
            return

        if self.task:
            self.task.cancel()

        async def run_task():
            # 整点模式：首次立即执行，之后每次循环对齐整点
            first_run = True
            while True:
                try:
                    await self.func()
                    if self.hourly_mode:
                        now = time.time()
                        wait_time = self.interval - (now % self.interval)
                        if wait_time < 0.1:
                            wait_time = self.interval
                        if first_run:
                            first_run = False
                            logger.info(f"整点模式已启用，将在 {wait_time:.1f} 秒后对齐整点")
                        await asyncio.sleep(wait_time)
                    else:
                        await asyncio.sleep(self.interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"定时任务执行失败: {e}")
                    await asyncio.sleep(self.interval)

        self.task = asyncio.create_task(run_task())
        mode_text = "整点模式" if self.hourly_mode else "即时模式"
        logger.info(f"定时任务已启动，间隔 {self.interval} 秒（{mode_text}）")

    def stop(self):
        """停止定时任务"""
        if self.task:
            self.task.cancel()
            self.task = None
            logger.info("定时任务已停止")

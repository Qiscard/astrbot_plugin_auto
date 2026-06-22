# Copyright (C) 2025-2026 Qiscard
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import random
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Dict

import aiohttp
import psutil
from astrbot import logger

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

MAX_CARD_LEN = 55  # 安全截断长度


class DataSource(ABC):
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    @abstractmethod
    async def get_data(self) -> str:
        pass


# ── 系统信息类 ─────────────────────────────────────────

class SystemMemorySource(DataSource):
    async def get_data(self) -> str:
        mem = psutil.virtual_memory()
        t = self.config.get("template", "内存 {u:.1f}G/{t:.1f}G ({p:.1f}%)")
        return t.format(u=mem.used / 1024**3, t=mem.total / 1024**3, p=mem.percent)


class SystemCPUSource(DataSource):
    async def get_data(self) -> str:
        t = self.config.get("template", "CPU {p:.1f}%")
        return t.format(p=psutil.cpu_percent(interval=0.1))


class SystemDiskSource(DataSource):
    async def get_data(self) -> str:
        d = psutil.disk_usage("/")
        t = self.config.get("template", "磁盘 {u:.1f}G/{t:.1f}G ({p:.1f}%)")
        return t.format(u=d.used / 1024**3, t=d.total / 1024**3, p=d.percent)


class SystemInfoSource(DataSource):
    async def get_data(self) -> str:
        t = self.config.get("template", "CPU {cpu:.1f}% | 内存 {mem:.1f}%")
        return t.format(cpu=psutil.cpu_percent(interval=0.1), mem=psutil.virtual_memory().percent)


class CurrentTimeSource(DataSource):
    async def get_data(self) -> str:
        n = datetime.now()
        t = self.config.get("template", "{datetime}")
        return t.format(time=n.strftime("%H:%M:%S"), date=n.strftime("%Y-%m-%d"),
                        datetime=n.strftime("%Y-%m-%d %H:%M:%S"),
                        hour=n.hour, minute=n.minute, second=n.second)


# ── 倒计时 ─────────────────────────────────────────────

class CountdownSource(DataSource):
    async def get_data(self) -> str:
        ts = self.config.get("target_date")
        ev = self.config.get("event_name", "目标日期")
        if not ts:
            return "未配置倒计时日期"
        try:
            f = "%Y-%m-%d %H:%M:%S" if " " in ts else "%Y-%m-%d"
            delta = datetime.strptime(ts, f) - datetime.now()
            if delta.total_seconds() < 0:
                return f"{ev}已过去{abs(delta.days)}天"
            s = delta.seconds
            t = self.config.get("template", "距{ev}还有{d}天{h}时{m}分")
            return t.format(ev=ev, d=delta.days, h=s // 3600, m=(s % 3600) // 60)
        except Exception as e:
            return "倒计时格式错误"


class CountUpSource(DataSource):
    async def get_data(self) -> str:
        ts = self.config.get("target_date")
        ev = self.config.get("event_name", "目标日期")
        if not ts:
            return "未配置正计时日期"
        try:
            f = "%Y-%m-%d %H:%M:%S" if " " in ts else "%Y-%m-%d"
            start = datetime.strptime(ts, f)
            delta = datetime.now() - start
            if delta.total_seconds() < 0:
                return f"{ev}还未到来"
            total_days = delta.days
            years = total_days // 365
            months = (total_days % 365) // 30
            days = (total_days % 365) % 30
            t = self.config.get("template", "已经过了{y}年{m}月{d}天")
            return t.format(ev=ev, y=years, m=months, d=days)
        except Exception as e:
            return "正计时格式错误"


# ── 自定义文本 ─────────────────────────────────────────

class CustomTextSource(DataSource):
    async def get_data(self) -> str:
        t = self.config.get("text", "")
        n = datetime.now()
        t = t.replace("{time}", n.strftime("%H:%M:%S")).replace("{date}", n.strftime("%Y-%m-%d"))
        t = t.replace("{datetime}", n.strftime("%Y-%m-%d %H:%M:%S"))
        return t[:MAX_CARD_LEN]


# ── 聚合 API（317ak.cn） + ALAPI 兜底 ──────────────────

class _JuheSource(DataSource):
    """317ak.cn 聚合 API 基类，ckey 不足时降级 ALAPI"""
    _MSG = ""  # 子类覆盖：随机一言 / 毒鸡汤 / 英汉语录 ...

    async def get_data(self) -> str:
        ckey = self.config.get("juhe_ckey", "")
        if ckey:
            try:
                async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as s:
                    url = f"https://api.317ak.cn/api/wz/juhe?ckey={ckey}&msg={self._MSG}&type=json"
                    async with s.get(url, timeout=aiohttp.ClientTimeout(10)) as r:
                        d = await r.json()
                        if d.get("code") == 200:
                            txt = d.get("data", "")
                            if isinstance(txt, dict):
                                txt = txt.get("content", "") or txt.get("text", "") or str(txt)
                            if txt:
                                return txt[:MAX_CARD_LEN]
            except Exception as e:
                logger.debug(f"[{self._MSG}] 317ak 失败，尝试 ALAPI: {e}")

        # 降级：ALAPI
        token = self.config.get("token", "")
        if token:
            return await self._alapi_fallback(token)
        return f"{self._MSG}: 未配置 API Key"


class HitokotoSource(_JuheSource):
    _MSG = "随机一言"

    async def _alapi_fallback(self, token: str) -> str:
        try:
            async with aiohttp.ClientSession() as s:
                url = f"https://v3.alapi.cn/api/hitokoto?token={token}"
                cat = self.config.get("category", "")
                if cat: url += f"&c={cat}"
                async with s.get(url, timeout=aiohttp.ClientTimeout(10)) as r:
                    d = await r.json()
                    if d.get("code") == 200:
                        return (d.get("data", {}).get("hitokoto", "") or "")[:MAX_CARD_LEN]
        except Exception:
            pass
        return "一言获取失败"


class SoulSource(_JuheSource):
    _MSG = "毒鸡汤"

    async def _alapi_fallback(self, token: str) -> str:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://v3.alapi.cn/api/soul?token={token}", timeout=aiohttp.ClientTimeout(10)) as r:
                    d = await r.json()
                    if d.get("code") == 200:
                        txt = d.get("data", {}).get("soul", "") or d.get("data", {}).get("content", "")
                        if txt: return f"毒鸡汤: {txt[:50]}"
        except Exception:
            pass
        return "毒鸡汤获取失败"


class MingYanSource(_JuheSource):
    _MSG = "经典语录"

    async def _alapi_fallback(self, token: str) -> str:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://v3.alapi.cn/api/mingyan?token={token}&format=json", timeout=aiohttp.ClientTimeout(10)) as r:
                    d = await r.json()
                    if d.get("code") == 200:
                        dd = d.get("data", {})
                        c = dd.get("content", "") or dd.get("mingyan", "")
                        a = dd.get("author", "")
                        if c: return f"{c[:50]} ——{a[:8]}" if a else c[:MAX_CARD_LEN]
        except Exception:
            pass
        return "名言获取失败"


# ── 热搜（每日缓存 + 随机抽取） ───────────────────────

class _HotSearchSource(DataSource):
    """热搜基类：每日缓存一次，超限剔除，随机抽取"""
    _API_ID = ""  # 子类覆盖：weibo / douyin / bilibili-hot-search

    def _cache_file(self) -> str:
        d = os.path.dirname(self.config.get("token", ""))  # 取不到就 fallback
        d = d or os.path.join(os.path.dirname(__file__), "..", "..", "temp")
        os.makedirs(d, exist_ok=True)
        # 实在不行用系统临时目录
        return os.path.join(d, f"hot_{self._API_ID.replace('-','_')}_{date.today().isoformat()}.json")

    def _load_cache(self) -> list | None:
        p = self._cache_file()
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _save_cache(self, items: list):
        try:
            with open(self._cache_file(), "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"[{self._API_ID}] 缓存写入失败: {e}")

    async def fetch_items(self) -> list:
        """子类实现：从 API 获取原始条目列表"""
        return []

    def filter_items(self, items: list) -> list:
        """保留标题不超过限制的条目"""
        return [i for i in items if len(i.get("title", "")) <= MAX_CARD_LEN]

    async def get_data(self) -> str:
        items = self._load_cache()
        if not items:
            raw = await self.fetch_items()
            items = self.filter_items(raw)
            if items:
                self._save_cache(items)
        if not items:
            return f"{self._API_ID} 获取失败"
        item = random.choice(items)
        return item['title'][:MAX_CARD_LEN]


class WeiboHotSource(_HotSearchSource):
    _API_ID = "weibo"

    async def fetch_items(self) -> list:
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as s:
                async with s.get("https://newsnow.busiyi.world/api/s?id=weibo", timeout=aiohttp.ClientTimeout(10)) as r:
                    d = await r.json()
                    if d.get("status") in ("success", "cache"):
                        return d.get("items", [])
        except Exception as e:
            logger.debug(f"[weibo] 主 API 失败: {e}")
        # 兜底：ALAPI
        token = self.config.get("token", "")
        if token:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"https://v3.alapi.cn/api/weibo?token={token}", timeout=aiohttp.ClientTimeout(10)) as r:
                        d = await r.json()
                        if d.get("code") == 200:
                            return [{"title": i.get("title", "")} for i in (d.get("data") or [])]
            except Exception:
                pass
        return []


class DouyinHotSource(_HotSearchSource):
    _API_ID = "douyin"

    async def fetch_items(self) -> list:
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as s:
                async with s.get("https://newsnow.busiyi.world/api/s?id=douyin", timeout=aiohttp.ClientTimeout(10)) as r:
                    d = await r.json()
                    if d.get("status") in ("success", "cache"):
                        return d.get("items", [])
        except Exception as e:
            logger.debug(f"[douyin] 主 API 失败: {e}")
        token = self.config.get("token", "")
        if token:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"https://v3.alapi.cn/api/douyin?token={token}", timeout=aiohttp.ClientTimeout(10)) as r:
                        d = await r.json()
                        if d.get("code") == 200:
                            return [{"title": i.get("title", "")} for i in (d.get("data") or [])]
            except Exception:
                pass
        return []


class BiliBiliHotSource(_HotSearchSource):
    _API_ID = "bilibili-hot-search"

    async def fetch_items(self) -> list:
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as s:
                async with s.get("https://newsnow.busiyi.world/api/s?id=bilibili-hot-search", timeout=aiohttp.ClientTimeout(10)) as r:
                    d = await r.json()
                    if d.get("status") in ("success", "cache"):
                        return d.get("items", [])
        except Exception as e:
            logger.debug(f"[bilibili] 主 API 失败: {e}")
        return []


class BaiduHotSource(_HotSearchSource):
    _API_ID = "baidu"

    async def fetch_items(self) -> list:
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as s:
                async with s.get("https://newsnow.busiyi.world/api/s?id=baidu", timeout=aiohttp.ClientTimeout(10)) as r:
                    d = await r.json()
                    if d.get("status") in ("success", "cache"):
                        return d.get("items", [])
        except Exception as e:
            logger.debug(f"[baidu] 主 API 失败: {e}")
        token = self.config.get("token", "")
        if token:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"https://v3.alapi.cn/api/baidu?token={token}", timeout=aiohttp.ClientTimeout(10)) as r:
                        d = await r.json()
                        if d.get("code") == 200:
                            return [{"title": i.get("title", "")} for i in (d.get("data") or [])]
            except Exception:
                pass
        return []


# ── 管理器 ─────────────────────────────────────────────

class DataSourceManager:
    _sources = {
        "system_memory": SystemMemorySource,
        "system_cpu": SystemCPUSource,
        "system_disk": SystemDiskSource,
        "system_info": SystemInfoSource,
        "countdown": CountdownSource,
        "countup": CountUpSource,
        "hitokoto": HitokotoSource,
        "soul": SoulSource,
        "mingyan": MingYanSource,
        "weibo_hot": WeiboHotSource,
        "baidu_hot": BaiduHotSource,
        "douyin_hot": DouyinHotSource,
        "bilibili_hot": BiliBiliHotSource,
        "custom_text": CustomTextSource,
        "current_time": CurrentTimeSource,
    }

    @classmethod
    def create_source(cls, source_type: str, config: Dict[str, Any] = None) -> DataSource:
        src = cls._sources.get(source_type)
        if not src:
            raise ValueError(f"未知的信息源类型: {source_type}")
        return src(config or {})

    @classmethod
    def get_available_sources(cls) -> list:
        return list(cls._sources.keys())

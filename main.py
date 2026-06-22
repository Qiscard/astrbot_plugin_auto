# Copyright (C) 2025-2026 Qiscard
# SPDX-License-Identifier: GPL-3.0-or-later
#
# 插件框架: https://github.com/Zhalslar/astrbot_plugin_qqprofile
# 灵感来源: https://github.com/Nwflower/auto-plugin

import asyncio
import json
import os
import random

from astrbot import logger
from astrbot.api.event import filter
from astrbot.api.event.filter import on_platform_loaded
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType

from .data_sources import DataSourceManager
from .scheduler import SimpleScheduler

GROUPS_CACHE_FILENAME = "astrbot_plugin_auto_groups_cache.json"


class AutoGroupCardPlugin(Star):
    """自动群名片插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.context = context
        self.bot_instance = None
        self.bot_self_id = None

        self.data_source_manager = DataSourceManager()

        self.card_scheduler = SimpleScheduler()
        self.signature_scheduler = SimpleScheduler()

        # 循环不重复状态
        self._card_cyclic_list = []
        self._card_cyclic_idx = 0
        self._sig_cyclic_list = []
        self._sig_cyclic_idx = 0

        self.initialized = False

    async def initialize(self):
        await self._try_auto_initialize()

    async def terminate(self):
        logger.info("自动群名片插件终止中...")
        self.card_scheduler.stop()
        self.signature_scheduler.stop()
        self.initialized = False
        logger.info("自动群名片插件已停止所有定时任务")

    @on_platform_loaded()
    async def on_platform_loaded_event(self, event=None):
        logger.info("[auto-group-card] 平台加载事件触发，尝试自动初始化...")
        await self._try_auto_initialize()

    async def _try_auto_initialize(self):
        if self.initialized:
            return
        try:
            self._refresh_config()
            platforms = self.context.platform_manager.get_insts()
            for p in platforms:
                name = p.__class__.__name__.lower()
                if "aiocqhttp" in name or "cqhttp" in name:
                    self.bot_instance = p.get_client()
                    try:
                        info = await self.bot_instance.call_action("get_login_info")
                        self.bot_self_id = str(info["user_id"])
                        logger.info(f"[auto-group-card] 机器人 QQ: {self.bot_self_id}")
                    except Exception as e:
                        logger.warning(f"[auto-group-card] 获取 QQ 失败，等待首次消息: {e}")
                    break
            if self.bot_instance:
                await self._initialize_task()
                self.initialized = True
                try:
                    await self._cache_groups()
                except Exception:
                    pass
                logger.info("=" * 50)
                logger.info("自动群名片插件配置:")
                logger.info(f"  群名片: {self.conf.get('enabled', False)}, 签名: {self.conf.get('signature_enabled', False)}")
                logger.info(f"  信息源: {self.conf.get('sources', [])}, 目标群: {self.conf.get('target_groups', [])}")
                logger.info("=" * 50)
            else:
                logger.info("[auto-group-card] 未找到平台实例，等待首次消息")
        except Exception as e:
            logger.warning(f"[auto-group-card] 自动初始化失败: {e}")

    def _refresh_config(self):
        try:
            path = self.conf.config_path
            if path and os.path.exists(path):
                with open(path, encoding="utf-8-sig") as f:
                    c = f.read()
                    if c.startswith("﻿"):
                        c = c[1:]
                    self.conf.clear()
                    self.conf.update(json.loads(c))
        except Exception as e:
            logger.warning(f"[auto-group-card] 刷新配置失败: {e}")

    def _save_config(self):
        try:
            self.conf.save_config()
        except Exception as e:
            logger.warning(f"[auto-group-card] 保存配置失败: {e}")

    def _cache_path(self):
        return os.path.join(os.path.dirname(self.conf.config_path), GROUPS_CACHE_FILENAME)

    async def _cache_groups(self):
        if not self.bot_instance:
            return []
        try:
            gl = await self.bot_instance.call_action("get_group_list")
        except Exception:
            return self._get_cached_groups()
        groups = [{"group_id": str(g.get("group_id", "")), "group_name": g.get("group_name", "未命名")} for g in (gl or [])]
        try:
            with open(self._cache_path(), "w", encoding="utf-8") as f:
                json.dump(groups, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[auto-group-card] 写入群缓存失败: {e}")
        self._update_schema(groups)
        return groups

    def _get_cached_groups(self) -> list:
        try:
            p = self._cache_path()
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _update_schema(self, groups: list):
        try:
            sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_conf_schema.json")
            if not os.path.exists(sp):
                return
            with open(sp, encoding="utf-8-sig") as f:
                schema = json.load(f)
            tgt = schema.get("target_groups", {})
            if not tgt:
                return
            opts, labels = [], []
            for g in groups:
                gid = g.get("group_id", "")
                if gid:
                    opts.append(gid)
                    labels.append(f"{g.get('group_name', '未命名')} ({gid})")
            if opts:
                tgt["options"] = opts
                tgt["labels"] = labels
                with open(sp, "w", encoding="utf-8") as f:
                    json.dump(schema, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.warning(f"[auto-group-card] 更新 schema 失败: {e}")

    async def _ensure_bot_initialized(self, event: AiocqhttpMessageEvent):
        if not self.bot_instance or not self.bot_self_id:
            self.bot_instance = event.bot
            self.bot_self_id = event.get_self_id()
        if not self.initialized:
            self._refresh_config()
            await self._initialize_task()
            self.initialized = True

    async def _initialize_task(self):
        await self._initialize_card_task()
        await self._initialize_signature_task()

    async def _initialize_card_task(self):
        enabled = self.conf.get("enabled", False)
        if not enabled:
            return
        sources = self.conf.get("sources", ["system_info"])
        interval = self.conf.get("interval", 60)
        target_groups = self.conf.get("target_groups", [])
        hourly_mode = self.conf.get("hourly_mode", False)
        if not isinstance(sources, list):
            sources = [sources] if sources else ["system_info"]
        if not isinstance(target_groups, list):
            target_groups = []
        if not target_groups:
            logger.warning("自动群名片已启用，但未配置目标群"); return
        if not sources:
            logger.warning("自动群名片已启用，但未选择信息源"); return

        update_mode = int(self.conf.get("update_mode", "1"))
        mode_labels = {0: "快速(100ms)", 1: "普通(250ms)", 2: "超慢速(逐群)"}
        logger.info(f"群名片: {len(sources)}个信息源, {len(target_groups)}个目标群, {interval}秒, 模式{mode_labels.get(update_mode, '?')}")

        async def update_card():
            if not self.bot_instance or not self.bot_self_id:
                return
            self._refresh_config()
            tg = self.conf.get("target_groups", [])
            sc = self.conf.get("sources", ["system_info"])
            if not isinstance(sc, list): sc = [sc] if sc else ["system_info"]
            if not isinstance(tg, list): tg = []
            if not tg or not sc:
                return
            expanded = self._build_expanded(sc)
            if not expanded:
                return
            rand = self.conf.get("random_mode", True)
            um = int(self.conf.get("update_mode", "1"))
            delay = {0: 0.15, 1: 0.35, 2: 0.75}.get(um, 0.1)
            label = {0: "快速", 1: "普通", 2: "超慢速"}.get(um, "?")
            src, cfg, self._card_cyclic_list, self._card_cyclic_idx = self._pick(
                expanded, self._card_cyclic_list, self._card_cyclic_idx, rand)
            ds = self.data_source_manager.create_source(src, cfg)
            card = await ds.get_data()
            ok = 0
            for i, gid in enumerate(tg):
                if i > 0: await asyncio.sleep(delay)
                try:
                    await self.bot_instance.call_action("set_group_card", group_id=int(gid), user_id=int(self.bot_self_id), card=card)
                    ok += 1
                except Exception as e:
                    logger.error(f"[群名片] 更新群 {gid} 失败: {e}")
            logger.info(f"[群名片] ✅ {label}: {card} ({src}, {ok}/{len(tg)})")

        self.card_scheduler.set_task(update_card, interval, enabled=True, hourly_mode=hourly_mode)
        self.card_scheduler.start()

    async def _initialize_signature_task(self):
        enabled = self.conf.get("signature_enabled", False)
        if not enabled:
            return
        sources = self.conf.get("signature_sources", ["hitokoto"])
        interval = self.conf.get("signature_interval", 3600)
        hourly_mode = self.conf.get("signature_hourly_mode", False)
        if not isinstance(sources, list):
            sources = [sources] if sources else ["hitokoto"]
        if not sources:
            return

        logger.info(f"签名: {len(sources)}个信息源, {interval}秒")

        async def update_signature():
            if not self.bot_instance:
                return
            self._refresh_config()
            ss = self.conf.get("signature_sources", ["hitokoto"])
            if not isinstance(ss, list): ss = [ss] if ss else ["hitokoto"]
            if not ss:
                return
            expanded = self._build_expanded(ss)
            if not expanded:
                return
            rand = self.conf.get("random_mode", True)
            src, cfg, self._sig_cyclic_list, self._sig_cyclic_idx = \
                self._pick(expanded, self._sig_cyclic_list, self._sig_cyclic_idx, rand)
            try:
                ds = self.data_source_manager.create_source(src, cfg)
                sig = await ds.get_data()
                await self.bot_instance.set_self_longnick(longNick=sig)
                logger.info(f"[签名] ✅ {sig} ({src})")
            except Exception as e:
                logger.error(f"[签名] ❌ 失败: {e}", exc_info=True)

        self.signature_scheduler.set_task(update_signature, interval, enabled=True, hourly_mode=hourly_mode)
        self.signature_scheduler.start()

    def _build_expanded(self, sources: list) -> list:
        alapi = self.conf.get("alapi_token", "")
        juhe = self.conf.get("juhe_ckey", "")
        cfgs = self.conf.get("source_configs", [])
        cmap = {}
        for sc in cfgs:
            k = sc.get("__template_key")
            if k:
                cfg = {k: v for k, v in sc.items() if k != "__template_key"}
                if alapi: cfg["token"] = alapi
                cmap.setdefault(k, []).append(cfg)
        r = []
        for src in sources:
            inject = {}
            if alapi: inject["token"] = alapi
            if juhe: inject["juhe_ckey"] = juhe
            if src in cmap:
                for cfg in cmap[src]:
                    cfg.update(inject)
                    r.append((src, cfg))
            else:
                r.append((src, inject))
        return r

    @staticmethod
    def _pick(expanded: list, clist: list, cidx: int, rand: bool) -> tuple:
        if not expanded:
            return "", {}, [], 0
        if rand:
            src, cfg = random.choice(expanded)
            return src, cfg, clist, cidx
        if cidx >= len(clist):
            clist = expanded.copy()
            random.shuffle(clist)
            cidx = 0
        src, cfg = clist[cidx]
        return src, cfg, clist, cidx + 1

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("查看群名片状态")
    async def show_status(self, event: AiocqhttpMessageEvent):
        await self._ensure_bot_initialized(event)
        card_enabled = self.conf.get("enabled", False)
        card_sources = self.conf.get("sources", ["system_info"])
        card_interval = self.conf.get("interval", 60)
        target_groups = self.conf.get("target_groups", [])
        sig_enabled = self.conf.get("signature_enabled", False)
        sig_sources = self.conf.get("signature_sources", ["hitokoto"])
        sig_interval = self.conf.get("signature_interval", 3600)
        if not isinstance(card_sources, list): card_sources = [card_sources] if card_sources else []
        if not isinstance(sig_sources, list): sig_sources = [sig_sources] if sig_sources else []
        if not isinstance(target_groups, list): target_groups = []

        names = {"system_memory":"系统内存","system_cpu":"系统CPU","system_info":"系统综合信息","system_disk":"系统磁盘","countdown":"倒计时","hitokoto":"一言","weibo_hot":"微博热搜","baidu_hot":"百度热搜","douyin_hot":"抖音热搜","current_time":"当前时间","custom_text":"自定义文本"}
        s = "【自动群名片状态】\n\n"
        s += f"━━━ 群名片 ━━━\n启用: {'✅' if card_enabled else '❌'} | 间隔: {card_interval}秒 | 目标: {len(target_groups)}个 | 信息源: {len(card_sources)}个\n"
        if card_sources:
            s += "\n信息源:\n"
            for src, cfg in self._build_expanded(card_sources):
                n = names.get(src, src)
                if cfg and "event_name" in cfg: n += f"「{cfg['event_name']}」"
                elif cfg and "text" in cfg: n += f"「{cfg['text'][:20]}」"
                s += f"  • {n}\n"
        if target_groups:
            s += f"\n目标群:\n" + "\n".join(f"  - {g}" for g in target_groups[:5])
            if len(target_groups) > 5: s += f"\n  ... 还有{len(target_groups)-5}个"
        s += f"\n\n━━━ 个性签名 ━━━\n启用: {'✅' if sig_enabled else '❌'} | 间隔: {sig_interval}秒 | 信息源: {len(sig_sources)}个\n"
        if sig_sources:
            s += "\n信息源:\n"
            for src, cfg in self._build_expanded(sig_sources):
                n = names.get(src, src)
                if cfg and "event_name" in cfg: n += f"「{cfg['event_name']}」"
                s += f"  • {n}\n"
        yield event.plain_result(s.strip())

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("手动更新群名片")
    async def manual_update(self, event: AiocqhttpMessageEvent):
        await self._ensure_bot_initialized(event)
        if not hasattr(event, 'group_id') or not event.group_id:
            yield event.plain_result("请在群聊中使用此命令"); return
        sources = self.conf.get("sources", ["system_info"])
        if not isinstance(sources, list): sources = [sources] if sources else []
        if not sources: yield event.plain_result("未配置信息源"); return
        expanded = self._build_expanded(sources)
        if not expanded: yield event.plain_result("未配置信息源"); return
        rand = self.conf.get("random_mode", True)
        src, cfg, self._card_cyclic_list, self._card_cyclic_idx = \
            self._pick(expanded, self._card_cyclic_list, self._card_cyclic_idx, rand)
        try:
            ds = self.data_source_manager.create_source(src, cfg)
            card = await ds.get_data()
            await event.bot.call_action("set_group_card", group_id=int(event.group_id), user_id=int(event.get_self_id()), card=card)
            logger.info(f"[手动更新] ✅ {card}")
            yield event.plain_result(f"✅ 已更新: {card}")
        except Exception as e:
            logger.error(f"[手动更新] ❌ 失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 更新失败: {e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("查看所有群聊")
    async def list_groups(self, event: AiocqhttpMessageEvent):
        await self._ensure_bot_initialized(event)
        groups = self._get_cached_groups()
        if not groups:
            try:
                groups = await self._cache_groups()
            except Exception as e:
                yield event.plain_result(f"❌ 获取群列表失败: {e}"); return
        if not groups: yield event.plain_result("机器人未加入任何群聊"); return
        targets = self.conf.get("target_groups", [])
        if not isinstance(targets, list): targets = []
        msg = f"📋 {len(groups)} 个群聊：\n" + "━" * 20 + "\n"
        for i, g in enumerate(groups, 1):
            flag = " ✅" if g.get("group_id") in targets else ""
            msg += f"{i}. {g.get('group_name', '?')} ({g.get('group_id', '?')}){flag}\n"
        msg += "\n💡 可用命令：\n  • 缓存所有群聊\n  • 一键添加所有群聊到目标\n  • 添加目标群 <关键词>"
        yield event.plain_result(msg.strip())

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("缓存所有群聊")
    async def cache_groups_cmd(self, event: AiocqhttpMessageEvent):
        await self._ensure_bot_initialized(event)
        groups = await self._cache_groups()
        if not groups: yield event.plain_result("❌ 未获取到群列表"); return
        yield event.plain_result(f"✅ 已缓存 {len(groups)} 个群聊，WebUI 配置页可直接下拉选择")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("一键添加所有群聊到目标")
    async def add_all_groups(self, event: AiocqhttpMessageEvent):
        await self._ensure_bot_initialized(event)
        groups = self._get_cached_groups()
        if not groups: groups = await self._cache_groups()
        if not groups: yield event.plain_result("❌ 未获取到群列表，先用「缓存所有群聊」"); return
        current = self.conf.get("target_groups", [])
        if not isinstance(current, list): current = []
        cur_set = set(current)
        added = [g for g in groups if g.get("group_id") and g["group_id"] not in cur_set]
        if added:
            current.extend(g["group_id"] for g in added)
            self.conf["target_groups"] = current
            self._save_config()
            self._refresh_config()
        yield event.plain_result(f"✅ 已添加 {len(added)} 个新群，当前共 {len(current)} 个目标群")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("添加目标群")
    async def add_target_group(self, event: AiocqhttpMessageEvent, keyword: str = ""):
        await self._ensure_bot_initialized(event)
        if not keyword: yield event.plain_result("❌ 请指定关键词，例如：添加目标群 测试群"); return
        groups = self._get_cached_groups()
        if not groups: groups = await self._cache_groups()
        if not groups: yield event.plain_result("❌ 未获取到群列表"); return
        matches = [g for g in groups if keyword in g.get("group_id","") or keyword in g.get("group_name","")]
        if not matches: yield event.plain_result(f"❌ 未找到包含「{keyword}」的群"); return
        current = self.conf.get("target_groups", [])
        if not isinstance(current, list): current = []
        cur_set = set(current)
        added = [g for g in matches if g.get("group_id") and g["group_id"] not in cur_set]
        if added:
            current.extend(g["group_id"] for g in added)
            self.conf["target_groups"] = current
            self._save_config()
            self._refresh_config()
        detail = "\n".join(f"  • {g['group_name']} ({g['group_id']})" for g in added) if added else "（都已存在）"
        yield event.plain_result(f"✅ 已添加 {len(added)} 个群\n{detail}\n当前共 {len(current)} 个目标群")

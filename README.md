# 自动群名片插件

自动更新群名片和个性签名，支持多信息源随机/循环切换。

## 特性

- 📊 **个性化信息源** — 系统监控、一言、毒鸡汤、名人名言、B站/微博/百度/抖音热搜、倒计时等
- 🎨 **自动缓存群组** — 缓存后直接在webui中框选即可，麻麻再也不用担心手动一个个输入群号啦

## 信息源

| 类型 | 说明 |
|---|---|
| system_memory | 系统内存 |
| system_cpu | 系统CPU |
| system_info | 系统综合信息 |
| system_disk | 系统磁盘 |
| countdown | 倒计时（可配置多个） |
| countup | 正计时（已过时间） |
| current_time | 当前时间 |
| custom_text | 自定义文本 |
| weibo_hot | 微博热搜 |
| douyin_hot | 抖音热搜 |
| bilibili_hot | B站热搜 |
| baidu_hot | 百度热搜 |
| hitokoto | 一言（需 API Key） |
| soul | 毒鸡汤（需 API Key） |
| mingyan | 名人名言（需 API Key） |

## 命令（需管理员权限）

- `查看群名片状态` — 查看配置和运行状态
- `手动更新群名片` — 手动触发一次更新
- `查看所有群聊` — 列出 bot 的所有群聊（标记已添加的）
- `缓存所有群聊` — 刷新群缓存（WebUI 配置页即可下拉选择）
- `一键添加所有群聊到目标` — 全部加入更新列表
- `添加目标群 <关键词>` — 按名称或群号搜索添加

## 首次使用

1. WebUI → 插件管理 → 自动群名片 → 启用并配置
2. 重启 AstrBot 或重载插件（自动初始化）
3. 发送 `/缓存所有群聊` → 重载后WebUI 目标群列表出现下拉选项
4. 选择目标群 → 保存 → 自动开始更新

## 配置项

| 字段 | 说明 | 默认 |
|------|------|------|
| enabled | 启用群名片 | false |
| target_groups | 目标群列表 | [] |
| sources | 群名片信息源 | [system_info] |
| interval | 更新间隔（秒） | 60 |
| hourly_mode | 整点模式 | false |
| random_mode | 随机模式（开=完全随机，关=不重复循环） | true |
| alapi_token | ALAPI Token（兜底，免费版每日限100次） | "" |
| juhe_ckey | 聚合 API Key（主方案，一言/毒鸡汤/名言） | "" |
| update_mode | 更新模式（0=快速150ms, 1=普通350ms, 2=超慢速750ms） | "1" |
| signature_enabled | 启用签名 | false |
| signature_sources | 签名信息源 | [hitokoto] |
| signature_interval | 签名更新间隔（秒） | 3600 |
| source_configs | 信息源配置（如倒计时/正计时日期） | [] |

### 模板变量

| 信息源 | 可用变量 | 说明 |
|--------|----------|------|
| countdown / countup | `{ev}` `{y}` `{m}` `{d}` `{h}` `{m}` `{H}` `{M}` `{day}` | 事件名称、年、月、日、时、分、总时、总分、总天数 |

## API Key 配置

### juhe_ckey

一言、毒鸡汤、名人名言使用 [https://api.317ak.cn](https://api.317ak.cn) 聚合接口，需注册获取 Key：

1. 前往 [https://api.317ak.cn](https://api.317ak.cn) 注册获取 `ckey`
2. 填入插件配置的 `juhe_ckey` 字段

### alapi_token

当 `juhe_ckey` 未配置时，同上述功能降级为 ALAPI（每日仅 100 次免费调用）。
同时作为百度热搜的接口源。

1. 前往 [https://www.alapi.cn](https://www.alapi.cn) 注册获取 Token
2. 填入插件配置的 `alapi_token` 字段

## 更新模式

- **快速(0)** 150ms / **普通(1)** 350ms / **超慢速(2)** 750ms

## 随机模式

- **开启** — 每次展示的信息完全独立随机
- **关闭** — 洗牌后依次取完再洗牌，实现不重复循环

## 许可

本项目基于 [GNU General Public License v3.0](LICENSE) 发布。


## 致谢

- **插件框架** — [astrbot_plugin_qqprofile](https://github.com/Zhalslar/astrbot_plugin_qqprofile) by [Zhalslar](https://github.com/Zhalslar)
- **灵感来源** — [auto-plugin](https://github.com/Nwflower/auto-plugin) by [Nwflower](https://github.com/Nwflower)
- **AI 辅助** — 插件主体代码由 AI 生成（Claude Opus 4.8（好像掺水了） / DeepSeek V4 Flash）

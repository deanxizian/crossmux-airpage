# 新闻 API 接入

本项目读取“新浪快讯兼容 API”，不内置私人 NewsTick 服务地址。
准备一个把你获准使用的新闻源转换为以下 JSON 格式的 HTTP 服务，
将其地址填入 Docker `.env` 的 `NEWS_API_BASE_URL` 或同名 GitHub Secret 即可。
不需要先准备新闻服务也能用 `python -m app.cli --demo --json` 完整离线预览。

## 请求

假设配置为 `https://news.example.invalid/api/v1/news`，客户端发出：

```http
GET /api/v1/news/latest?category=all&limit=4
Accept: application/json
User-Agent: CrossMux-AirPage/0.1
```

若配置地址已经以 `/latest` 结尾，不再重复追加路径。
`category` 支持 `all` 或 `0`–`8`，`limit` 为 `1`–`4`。
栏目：`0` A 股、`1` 宏观、`2` 公司、`3` 数据、`4` 市场、`5` 国际、
`6` 观点、`7` 央行、`8` 其他。适配服务应先过滤栏目，再返回最新条目。

## 响应

```json
{
  "source": "sina_7x24",
  "stale": false,
  "items": [
    {
      "content": "【离线示例标题】这里是虚构的示例正文。",
      "published_at": "2026-09-05T01:00:00Z"
    }
  ]
}
```

| 字段 | 要求 | 客户端处理 |
|---|---|---|
| `items` | 必须为数组 | 按返回顺序展示，适配服务应按发布时间降序返回 |
| `items[].content` | 非空字符串 | 提取开头 `【标题】`，否则使用正文；整理空白、去重并裁剪显示长度 |
| `items[].published_at` | 可选，含时区的 ISO 8601 字符串 | 保留真实发布时间；缺失时不会凭空推断 |
| `stale` | 可选布尔值，默认 `false` | `true` 时保留内容并显示“缓存”，不会报告为新数据 |
| `source` | 可选 | 描述字段，不影响解析 |

无有效条目、错误类型、非法时间戳、非 JSON 或非 2xx HTTP 响应均视为采集失败。
本地有效缓存可用于回退；超过 `NEWS_MAX_AGE_SECONDS` 后停止显示旧内容。
该有效期衡量最近一次有效 HTTP 响应的年龄，不是新闻发布时间；上游返回
`stale=true` 的内容即使响应刚收到，也始终标为缓存。

## 最小本地示例服务

仓库提供 [虚构新闻响应](examples/news/latest)，路径与客户端请求一致。
在项目根目录运行：

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory docs/examples
```

另一终端运行：

```bash
NEWS_API_BASE_URL=http://127.0.0.1:8765/news \
OUTPUT_DIR=data AIRPAGE_ENABLED=false python -m app.cli --json
```

这个静态示例只验证接口形状，不处理栏目过滤，也不产生真实新闻；天气和行情仍会请求真实接口。
完全断网测试请使用 `--demo`。正式部署需将示例服务替换成持续更新的适配服务。
本项目只将归一化后的标题、时间、缓存状态和配置指纹写入数据卷，不保存新闻 URL 或设备链接。

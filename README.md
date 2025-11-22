
# 🚨 RadarFlow — 轻量级舆情监测新闻流水线

**RadarFlow** 是一个面向 *舆情监测 / 行业情报 / 竞品追踪* 的自动化新闻管道系统。
从抓取 → 过滤 → AI 摘要 → 去重入库 → 多渠道推送，全流程开箱即用。

---

## ✨ 为什么用 RadarFlow？

✅ **不用搭 Elasticsearch / Kafka / 大模型推理集群**  
✅ **10 分钟完成配置即可运行**  
✅ **支持关键词过滤 + AI 语义双重过滤**  
✅ **自动摘要 / 情绪 / 主题结构化输出**  
✅ **推送到飞书 / 钉钉 / 企业微信 / Telegram / 邮箱**  
✅ **SQLite 去重持久化，不重复推送**  
✅ **可扩展新闻源，只需返回一个 `NewsRecord`**  

---

## 🧩 核心流程

```
[ Fetch ] → [ Keyword Filter ] → [ AI Summary + Emotion + Topic ]
     → [ Dedup + Store ] → [ Multi-channel Notification ]
```

---

## 🚀 3 分钟快速开始

### 1) 安装依赖并复制配置

```bash
pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml
```

### 2) 填写配置（最小示例）

`config/config.yaml` 里只需关注三个部分：AI、过滤、通知。示例：

```yaml
ai:
  enabled: true
  base_url: "https://api.openai-compatible.com/v1"
  model: "gpt-4o-mini"
  api_key: "sk-your-key"

filters:
  enabled: true
  rules:
    - name: "中国and(美国or日本)"
      all_of: ["中国"]
      any_of: ["美国", "日本"]

notification:
  enable: true
  display_summary: true
  wechat_work:
    webhook_url: "https://qyapi.weixin.qq.com/..."
    msgtype: "markdown"
  telegram:
    bot_token: "123:abcd"
    chat_id: "-100xxxx"
```

> 建议直接复制 `config/config.example.yaml` 后修改

### 3) 手动运行

```bash
python main.py
```

### 4) 启用定时调度

```bash
python scheduler.py
```

---

## 🧪 示例推送效果

```
[中国and(美国or日本)]

📰 偷中国游客现金，日本机场一安检员被捕
🌍 关键词：日本成田机场, 安检员盗窃, 中国游客, 64万日元, 治安提醒
🕒 2025-11-22 22:11 | 🏷 澎湃要闻
情绪：消极🟥｜等级：中｜指数：-3
实体: 近藤幸雄(人物)、中国73岁老人(人物)、64万日元(金额)

📰 中方致函联合国秘书长阐明立场有何深意？
🌍 关键词：傅聪, 古特雷斯, 高市早苗, 涉台错误言论, 联合国宪章, 自卫权, 抗战胜利80周年, 台海局势
🕒 2025-11-22 15:51 | 🏷 澎湃要闻
情绪：消极🟥｜等级：高｜指数：-7
实体: 傅聪(人物)、古特雷斯(人物)、高市早苗(人物)

📰 港媒：香港特区政府教育局证实，取消一师生代表团赴日交流
🌍 关键词：香港教育局, 赴日交流取消, 高市早苗涉台言论, 21世纪东亚青少年大交流计划, 中日关系, 中国公民在日安全, 香港中学交流调整
🕒 2025-11-22 14:37 | 🏷 澎湃要闻
情绪：消极🟥｜等级：高｜指数：-7
实体: 高市早苗(人物)、香港特区政府教育局(机构)、21世纪东亚青少年大交流计划(项目)

📰 日媒：中国拒绝明年1月举行日中韩首脑会谈
🌍 关键词：日中韩首脑会谈, 高市早苗, 台湾有事, 外交拒绝, 中日关系
🕒 2025-11-22 22:43 | 🏷 联合早报·即时
情绪：消极🟥｜等级：中｜指数：-3
实体: 高市早苗(人物)、日中韩首脑会谈(事件)、共同社(机构)
```

![telegram bot_测试示例.png](docs/telegram_demo.png)



![wechat bot_测试示例.png](docs/wechat_demo.png)
可关闭摘要，仅展示标题：

```
notification.display_summary=false
```

---

## 🧱 项目结构

| 目录/文件              | 作用                               |
| ------------------ | -------------------------------- |
| `fetcher/`         | 多新闻源抓取器，统一返回 `NewsRecord`        |
| `filters.py`       | 关键词 AND / OR / NOT 过滤规则          |
| `ai/`              | 摘要 / 情绪 / 主题生成与过滤                |
| `notifications.py` | 飞书 / 钉钉 / 企业微信 / Telegram / 邮箱推送 |
| `state/`           | SQLite 去重与持久化数据                  |
| `scheduler.py`     | Cron 式调度执行                       |

---

## 🔌 扩展一个新的新闻源只需要 20 行代码

```python
from fetcher.base import NewsRecord

def fetch():
    return [
        NewsRecord(
            title="示例标题",
            url="https://example.com",
            published_at="2025-01-01",
            source="Example",
            content="正文文本"
        )
    ]
```

---

## 🐳 Docker 部署

```bash
docker build -t radarflow .
docker run --rm \
  -v "$(pwd)/config:/app/config" \
  -v "$(pwd)/state:/app/state" \
  radarflow
```

---

## 🗺️ 典型使用场景

| 场景   | RadarFlow 能做什么 |
| ---- | -------------- |
| 舆情监控 | 第一时间推送敏感关键词新闻  |
| 竞品监测 | 企业名 / 产品名触发提醒  |
| 行业研究 | AI 摘要节省阅读成本    |
| 危机应对 | 多渠道同步通知关键事件    |
| 媒体日报 | 自动生成内容流        |

---

## 🧭 路线图 Roadmap

* ✅ 多源抓取
* ✅ AI 摘要 / 情绪 / 主题
* ✅ 多渠道推送
* ⏳ Web 控制台
* ⏳ 规则可视化编辑
* ⏳ RSS + 社媒来源
* ⏳ 自定义模板推送

---

## ⭐ 如果这个项目对你有帮助……

👉 **欢迎 Star！你的支持决定后续更新节奏**
👉 也欢迎提 Issue / PR / 新源适配

---

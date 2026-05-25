# Movie SKILL — Mac mini 影视机顶盒

> 把 Mac mini 变成电视盒子。自然语言点播，全自动搜片、下片、播片。

## 核心用途

围绕 **Mac mini 接入电视当机顶盒** 这个场景设计：

- **点播模式**：说出想看的剧名和集数，自动搜索磁力、调用迅雷下载、IINA 全屏播放
- **资源收集模式**：搜索并导出磁力链接，可跨站点聚合去重，按清晰度排序

## 功能概览

```
你说 "分步看权力的游戏第三季第五集"
     ↓
  movie-crawl 多站点搜索 → 展示结果让你选
     ↓
  movie-dl 调用迅雷下载你选的磁力
     ↓
  movie-play 调起 IINA 全屏播放
```

四个 CLI 工具：

| 命令 | 作用 |
|------|------|
| `movie-crawl` | 多站搜索磁力链接 |
| `movie-dl` | 迅雷下载 + 队列管理 |
| `movie-play` | IINA/VLC/mpv 全屏播放 |
| `movie-skill` | 统一入口，支持自然语言路由 |

## 支持的站点

| 站点 | 类型 |
|------|------|
| clm34.top | 磁力搜索引擎 |
| dygod.vip | 帝国CMS 影视站 |

> 更多站点可通过 `~/.movie_skill/sites.yaml` 配置扩展，支持自定义 CSS/XPath 选择器。

## 安装

```bash
cd /Users/beiluo/代码/movie-skill-openclaw
python3.14 -m venv /tmp/movie-venv
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib /tmp/movie-venv/bin/pip install -e .
mkdir -p ~/.movie_skill
# 配置站点见 docs/sites.yaml 样例
```

## OpenClaw 集成

将 `movie-skill` 注册为 OpenClaw Skill 后，在电视前说：

- `爬取权力的游戏` → 搜索
- `分步看权力的游戏` → 分步确认全流程
- `自动下载权力的游戏` → 全自动下载
- `播放列表` → 列出已下载资源

## 环境要求

- macOS (Apple Silicon / Intel)
- 迅雷 Mac 版
- IINA 播放器
- Python 3.14+

## 免责声明

**本项目仅供学习交流使用，禁止用于任何商业用途。**

本工具仅提供技术实现参考，不提供任何影视资源。用户应对自己的使用行为负责，遵守当地法律法规。

---

*Made for Mac mini × TV × OpenClaw*

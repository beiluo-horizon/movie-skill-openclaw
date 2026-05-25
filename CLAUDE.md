# Movie SKILL

影视资源 CLI 工具链 — 爬虫 → 下载（迅雷） → 播放（IINA）

## 命令路由 (MANDATORY)

当用户说以下内容时，**直接执行**，不回复确认文字：

| 用户说 | 执行命令 |
|--------|---------|
| 爬取/搜索/找 XXX | `movie-skill "爬取XXX"` |
| 下载 XXX | `movie-skill "分步下载XXX"` |
| 播放/看 XXX | `movie-skill "分步看XXX"` |
| 播放列表/已下载 | `movie-skill "播放列表"` |

环境变量: `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib`

## 四个 CLI

| 命令 | 功能 |
|------|------|
| `movie-crawl` | 搜索磁力链接 |
| `movie-dl` | 迅雷下载 |
| `movie-play` | 播放本地文件 |
| `movie-skill` | 统一入口（含交互模式） |

## 技术栈

- Python 3.14, venv: `/tmp/movie-venv`
- 站点配置: `~/.movie_skill/sites.yaml`
- 输出目录: `.magnet/` → `.download/` → `.player/`
- 播放器: IINA (--mpv-fs=yes 全屏)

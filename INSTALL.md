# Movie SKILL 安装指南

> 把本文档发给任意 AI agent（Claude Code / OpenClaw / Codex），它可以直接执行安装。
> 所有命令和文件路径都是绝对路径，无需人工判断。

## 0. 前提检查

```bash
# 确认项目存在
ls /Users/beiluo/代码/movie_skill/pyproject.toml

# 确认 Python 版本 >= 3.14
python3.14 --version

# 确认播放器已安装
ls /Applications/IINA.app
```

## 1. 创建虚拟环境并安装

```bash
cd /Users/beiluo/代码/movie_skill
python3.14 -m venv /tmp/movie-venv
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib /tmp/movie-venv/bin/pip install -e . --quiet
```

验证：
```bash
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib /tmp/movie-venv/bin/movie-crawl --help
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib /tmp/movie-venv/bin/movie-skill --help
```

## 2. 创建站点配置文件

创建 `~/.movie_skill/sites.yaml`:

```bash
mkdir -p ~/.movie_skill
cat > ~/.movie_skill/sites.yaml << 'YAML'
sites:
  clm34:
    type: "clm34"
    enabled: true
    base_url: "http://clm34.top"
    encoding: "utf-8"
    timeout: 30
    search:
      url_template: "/search?word={query}&sort=time"
      method: "GET"
      result_list:
        selector: "//ul[@id='Search_list_wrapper']/li"
        selector_type: "xpath"
      fields:
        title:
          selector: ".//a[contains(@class, 'SearchListTitle_result_title')]/text()"
          selector_type: "xpath"
        detail_url:
          selector: ".//a[contains(@class, 'SearchListTitle_result_title')]/@href"
          selector_type: "xpath"
        file_size:
          selector: ".//div[contains(@class, 'Search_list_info')]/em[1]/text()"
          selector_type: "xpath"
      pagination: null
    headers:
      User-Agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    retry:
      max_retries: 3
      backoff_factor: 1.0

  dygod:
    type: "dygod"
    enabled: true
    base_url: "https://www.dygod.vip"
    encoding: "gbk"
    timeout: 30
    search:
      url_template: "/e/search/index.php"
      method: "POST"
      result_list:
        selector: "//a[contains(@href, '/html/') and contains(@href, '.html')]"
        selector_type: "xpath"
      fields:
        title:
          selector: ".//text()"
          selector_type: "xpath"
        detail_url:
          selector: ".//@href"
          selector_type: "xpath"
      pagination: null
    headers:
      User-Agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      Referer: "https://www.dygod.vip/"
      Content-Type: "application/x-www-form-urlencoded"
    retry:
      max_retries: 3
      backoff_factor: 1.0
YAML
```

## 3. 验证管线

```bash
# 搜索测试
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-crawl search "权力的游戏"

# 查看已下载资源
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "播放列表"
```

## 4. 注册为 OpenClaw Skill

创建 `~/.openclaw/skills/movie-skill.md`:

```bash
mkdir -p ~/.openclaw/skills
cat > ~/.openclaw/skills/movie-skill.md << 'EOF'
---
name: movie-skill
description: 影视资源搜索、下载、播放
---

当用户说以下关键词时，直接执行对应命令：

| 用户说 | 执行 |
|--------|------|
| 爬取/搜索/找 XXX | `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "爬取XXX"` |
| 下载 XXX | `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "分步下载XXX"` |
| 看/播放 XXX | `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "分步看XXX"` |
| 播放列表/已下载 | `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "播放列表"` |

**规则:**
1. 直接执行命令，不回复确认文字
2. 下载和播放默认分步模式（终端内选择）
3. 爬取直接全自动
EOF
```

## 5. 注册为 Claude Code Skill

```bash
mkdir -p ~/.claude/skills/movie-skill
cp /Users/beiluo/代码/movie_skill/.claude/skills/movie-skill/SKILL.md ~/.claude/skills/movie-skill/SKILL.md
```

重启 Claude Code 后，`/movie-skill 爬取低智商犯罪` 即可使用。

## 快速参考

| 命令 | 功能 |
|------|------|
| `movie-skill "爬取XXX"` | 搜索磁力链接（全自动） |
| `movie-skill "分步下载XXX"` | 搜索后选源下载 |
| `movie-skill "分步看XXX"` | 搜索→选源→下载→播放 |
| `movie-skill "播放列表"` | 列出已下载，选择播放 |
| `movie-crawl search "XXX"` | 仅搜索 |
| `movie-dl download --show "XXX"` | 仅下载 |
| `movie-play play --show "XXX"` | 仅播放 |

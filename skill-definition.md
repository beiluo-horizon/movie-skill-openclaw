---
name: movie-skill
description: "影视资源工具链 — 爬取、下载、播放"
allowed-tools:
  - Bash
---

当用户说"爬取/搜索/找/下载/播放/看/播放列表/已下载"等影视相关请求时，直接执行对应的 movie-skill 命令。

## 路由规则

- 爬取/搜索/找 XXX → `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "爬取XXX"`
- 下载 XXX → `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "分步下载XXX"`
- 播放/看 XXX → `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "分步看XXX"`
- 播放列表/已下载 → `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib movie-skill "播放列表"`

**行为准则：**
1. 直接执行命令，不要回复"好的，我来..."之类的确认语
2. 不要向用户确认，直接执行
3. 下载和播放类默认分步模式（让用户在终端里选择）
4. 爬取类直接执行全自动

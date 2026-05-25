# IINA 全屏播放经验

## 结论

IINA 的全屏标志是 `--mpv-fs=yes`，不能用 `--fs` 或 `--fullscreen`。

## 踩过的坑

| 标志 | 结果 | 原因 |
|------|------|------|
| `--fullscreen` | 无效 | IINA 不认这个标志 |
| `--fs` | 无效 | mpv 原生标志，但 IINA 需要 `--mpv-` 前缀 |
| `open -a IINA` | 弹出中间窗口 | open 命令会触发 IINA 的启动界面 |
| `--mpv-fs=yes` | ✓ 正确全屏 | IINA 官方支持的 mpv 选项透传方式 |

## 正确的调用方式

**直接调用 IINA 二进制**（不是 `open -a`）：

```bash
/Applications/IINA.app/Contents/MacOS/iina "/path/to/video.mkv" --mpv-fs=yes --mpv-keep-open=no
```

参数说明：
- `--mpv-fs=yes`：全屏播放
- `--mpv-keep-open=no`：播放完自动退出（不回菜单）

## 为什么不能用 `open -a`

`open -a IINA file.mkv` 会触发 IINA 的启动流程，可能弹出窗口或中间界面。

直接调用 `/Applications/IINA.app/Contents/MacOS/iina` 二进制文件，IINA 直接进入播放模式，无中间步骤。

## 检测 IINA 是否安装

```python
import shutil
from pathlib import Path

# 方式1: 检查二进制
iina_bin = shutil.which("iina")
if iina_bin:
    print("IINA on PATH:", iina_bin)

# 方式2: 检查 .app bundle
app_path = Path("/Applications/IINA.app/Contents/MacOS/iina")
if app_path.exists():
    print("IINA app found:", app_path)
```

## 播放器优先级

当前项目的播放器检测优先级：**IINA > VLC > mpv > open**

如果 IINA 未安装，会自动 fallback 到下一个可用播放器。

## 代码位置

播放器逻辑在 `src/movie_skill/player/player.py`：
- `_get_player_binary("iina")` → 返回 IINA 二进制路径
- `build_player_args("iina", ...)` → 构建 CLI 参数（含 `--mpv-fs=yes`）
- `play_best(file_path)` → 自动检测并选择最佳播放器

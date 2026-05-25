"""Interactive site configuration wizard using questionary.

Per D-02: User does not know CSS/XPath selectors. This wizard
provides a guided, step-by-step process to create a valid sites.yaml
config. Users paste URLs and describe elements in plain language;
the wizard provides sensible defaults and templates for common
Chinese media site patterns.

The wizard writes to ~/.movie_skill/sites.yaml by default.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import yaml


# Template for common Chinese movie/TV site structures
COMMON_TEMPLATES = {
    "通用搜索站点 (Generic Search)": {
        "encoding": "utf-8",
        "url_template": "https://example.com/search?keyword={query}",
        "result_list_selector": "//div[contains(@class, 'search-item')]",
        "title_selector": ".//h3/a/text()",
        "magnet_selector": ".//a[contains(@href, 'magnet:')]/@href",
    },
    "磁力搜索站 (Magnet Search Engine)": {
        "encoding": "utf-8",
        "url_template": "https://example.com/s?q={query}",
        "result_list_selector": "//div[@class='result-item']",
        "title_selector": ".//a[@class='title']/text()",
        "magnet_selector": ".//a[contains(@href, 'magnet:')]/@href",
    },
    "论坛/BBS 资源站 (Forum Style)": {
        "encoding": "gbk",
        "url_template": "https://example.com/search.php?keyword={query}",
        "result_list_selector": "//table[@id='threadlist']/tr",
        "title_selector": ".//a[@class='subject']/text()",
        "magnet_selector": ".//a[contains(@href, 'magnet:')]/@href",
    },
}


def run_wizard(sites_path: str = "~/.movie_skill/sites.yaml") -> None:
    """Run the interactive site configuration wizard.

    Guides the user through:
    1. Choosing a template or starting from scratch
    2. Entering site URL and name
    3. Customizing selectors (with plain language hints)
    4. Testing the configuration (basic URL validation)
    5. Saving to sites.yaml

    Args:
        sites_path: Path to the output sites.yaml file.

    Raises:
        ImportError: If questionary is not installed.
        SystemExit: On user cancellation.
    """
    try:
        import questionary
        from questionary import Choice
    except ImportError:
        raise ImportError(
            "questionary is required for the interactive wizard. "
            "Install with: pip install movie-skill[wizard]"
        )

    print("")
    print("=" * 60)
    print("  Movie SKILL - 站点配置向导")
    print("  指导您一步步创建站点配置文件")
    print("=" * 60)
    print("")

    # Load existing config if it exists
    config_path = Path(os.path.expanduser(sites_path))
    existing_config: dict = {"sites": {}}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict) and "sites" in loaded:
                    existing_config = loaded
            print(f"[green]已发现现有配置文件: {config_path}[/]")
        except Exception:
            print(f"[yellow]现有配置文件读取失败，将创建新文件[/]")

    # Main loop: add sites until user finishes
    while True:
        add_site = questionary.confirm(
            "是否添加一个搜索站点?",
            default=True,
        ).ask()

        if not add_site:
            break

        site = _collect_site_info()
        if site:
            site_name = site.pop("name")
            existing_config["sites"][site_name] = site
            print(f"[green]已添加站点: {site_name}[/]")

    # Preview and save
    if existing_config["sites"]:
        print("")
        print(f"将保存 {len(existing_config['sites'])} 个站点到: {config_path}")
        print(yaml.dump(existing_config, default_flow_style=False, allow_unicode=True))

        confirm = questionary.confirm("确认保存?", default=True).ask()
        if confirm:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(existing_config, f, default_flow_style=False, allow_unicode=True)
            print(f"[green]配置文件已保存到: {config_path}[/]")
            print("[green]现在可以运行 movie-crawl search 来测试了![/]")
        else:
            print("[yellow]未保存，配置未更改[/]")
    else:
        print("[yellow]未添加任何站点，配置文件未更改[/]")

    print("")


def _collect_site_info() -> Optional[dict]:
    """Interactively collect information for one site."""
    import questionary
    from questionary import Choice

    # Use template or create from scratch
    use_template = questionary.confirm(
        "是否使用预设模板? (推荐，可修改选择器)",
        default=True,
    ).ask()

    if not isinstance(use_template, bool):
        return None

    template = None
    if use_template:
        template_name = questionary.select(
            "选择站点类型模板:",
            choices=[
                Choice(title=name, value=name)
                for name in COMMON_TEMPLATES.keys()
            ],
        ).ask()
        if template_name and template_name in COMMON_TEMPLATES:
            template = COMMON_TEMPLATES[template_name]

    # Basic info
    site_name = questionary.text(
        "站点名称 (英文/拼音，如 dytt, btbtt):",
        default="mysite",
    ).ask()

    if not site_name:
        return None

    base_url = questionary.text(
        "站点基础 URL (如 https://example.com):",
        default=template.get("base_url", "https://") if template else "https://",
        validate=lambda x: x.startswith("http"),
    ).ask()

    if not base_url:
        return None

    encoding = questionary.select(
        "页面编码:",
        choices=[
            Choice(title="UTF-8 (大部分站点)", value="utf-8"),
            Choice(title="GBK/GB2312 (部分中文站点)", value="gbk"),
        ],
        default="utf-8" if not template or template["encoding"] == "utf-8" else "gbk",
    ).ask()

    if not encoding:
        return None

    # Search URL template
    url_template = questionary.text(
        "搜索 URL 模板 (用 {query} 代替搜索词):",
        default=template["url_template"] if template else "https://example.com/search?q={query}",
        validate=lambda x: "{query}" in x,
    ).ask()

    if not url_template:
        return None

    # Selectors (with defaults from template)
    result_selector = questionary.text(
        "搜索结果列表的 XPath 选择器:\n  提示: 右键页面中的搜索结果区域 → 检查 → 复制 XPath",
        default=template["result_list_selector"] if template else "//div[contains(@class, 'result')]",
    ).ask()

    if not result_selector:
        return None

    title_selector = questionary.text(
        "标题元素的 XPath 选择器 (相对于每个结果元素):\n  提示: 查找包含视频名称的元素，如 <h3> 或 <a>",
        default=template["title_selector"] if template else ".//h3/a/text()",
    ).ask()

    if not title_selector:
        return None

    magnet_selector = questionary.text(
        "磁力链接的 XPath 选择器:\n  提示: 链接通常 href 中包含 'magnet:'",
        default=template["magnet_selector"] if template else ".//a[contains(@href, 'magnet:')]/@href",
    ).ask()

    if not magnet_selector:
        return None

    # Optional fields
    timeout = questionary.text(
        "请求超时 (秒):",
        default="30",
        validate=lambda x: x.isdigit() and int(x) > 0,
    ).ask()

    if not timeout:
        return None

    has_size_field = questionary.confirm("搜索结果中是否包含文件大小?", default=True).ask()

    size_selector = None
    if has_size_field:
        size_selector = questionary.text(
            "文件大小的 XPath 选择器:",
            default=".//span[@class='size']/text()",
        ).ask()

    has_seeders = questionary.confirm("搜索结果中是否包含种子数?", default=False).ask()

    seeder_selector = None
    if has_seeders:
        seeder_selector = questionary.text(
            "种子数的 XPath 选择器:",
            default=".//span[@class='seed']/text()",
        ).ask()

    # Build site config
    site_config: dict = {
        "enabled": True,
        "base_url": base_url.rstrip("/"),
        "encoding": encoding,
        "timeout": int(timeout),
        "search": {
            "url_template": url_template,
            "method": "GET",
            "result_list": {
                "selector": result_selector,
                "selector_type": "xpath",
            },
            "fields": {
                "title": {
                    "selector": title_selector,
                    "selector_type": "xpath",
                },
                "magnet_link": {
                    "selector": magnet_selector,
                    "selector_type": "xpath",
                },
            },
        },
        "headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": base_url.rstrip("/") + "/",
        },
    }

    if size_selector:
        site_config["search"]["fields"]["size"] = {
            "selector": size_selector,
            "selector_type": "xpath",
        }

    if seeder_selector:
        site_config["search"]["fields"]["seeders"] = {
            "selector": seeder_selector,
            "selector_type": "xpath",
        }

    return {
        "name": site_name,
        **site_config,
    }

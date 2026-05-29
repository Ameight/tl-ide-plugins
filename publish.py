#!/usr/bin/env python3
"""
publish.py — генерирует registry.json из всех плагинов в репозитории.

Использование:
    python publish.py
    python publish.py --base-url https://raw.githubusercontent.com/org/repo/master

Конфиг (publish.yaml):
    base_url: https://raw.githubusercontent.com/Ameight/tl-ide-plugins/master
    output: registry.json
"""

import argparse
import json
import pathlib
import sys

try:
    import yaml
    def _load_yaml(path: pathlib.Path) -> dict:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
except ImportError:
    def _load_yaml(path: pathlib.Path) -> dict:
        return {}

DEFAULT_BASE_URL = "https://raw.githubusercontent.com/Ameight/tl-ide-plugins/master"
CONFIG_FILE = pathlib.Path("publish.yaml")
REGISTRY_FILE = pathlib.Path("registry.json")
SKIP_DIRS = {"__pycache__", ".git", ".github"}


def _resolve_base_url(override: str | None) -> str:
    if override:
        return override.rstrip("/")
    if CONFIG_FILE.exists():
        cfg = _load_yaml(CONFIG_FILE)
        if cfg.get("base_url"):
            return cfg["base_url"].rstrip("/")
    return DEFAULT_BASE_URL


def _resolve_output(cfg_output: str | None) -> pathlib.Path:
    if cfg_output:
        return pathlib.Path(cfg_output)
    if CONFIG_FILE.exists():
        cfg = _load_yaml(CONFIG_FILE)
        if cfg.get("output"):
            return pathlib.Path(cfg["output"])
    return REGISTRY_FILE


def load_manifest(manifest_path: pathlib.Path) -> dict | None:
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  Ошибка чтения {manifest_path}: {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate registry.json for TL IDE Marketplace")
    parser.add_argument("--base-url", default=None, metavar="URL",
                        help="Base raw URL (overrides publish.yaml)")
    parser.add_argument("--output", default=None, metavar="FILE")
    args = parser.parse_args()

    base_url = _resolve_base_url(args.base_url)
    output = _resolve_output(args.output)

    registry = []

    for manifest_path in sorted(pathlib.Path(".").rglob("manifest.json")):
        parts = manifest_path.parts
        if len(parts) != 3:
            continue
        if any(p in SKIP_DIRS for p in parts):
            continue

        category_dir, plugin_dir, _ = parts
        plugin_py = manifest_path.parent / "plugin.py"

        if not plugin_py.exists():
            print(f"  ⚠️  Нет plugin.py рядом с {manifest_path}, пропускаю")
            continue

        manifest = load_manifest(manifest_path)
        if not manifest:
            continue

        plugin_id = f"{category_dir}/{plugin_dir}"
        entry = {
            "id": plugin_id,
            "raw_url": f"{base_url}/{plugin_id}/plugin.py",
            **manifest,
        }
        registry.append(entry)
        print(f"  ✅  {plugin_id}  ({manifest.get('name', '?')}  v{manifest.get('version', '?')})")

    output.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n📦 {output}: {len(registry)} плагин(ов)")
    print(f"   base_url: {base_url}")


if __name__ == "__main__":
    main()

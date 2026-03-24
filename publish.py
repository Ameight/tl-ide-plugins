#!/usr/bin/env python3
"""
Генерирует registry.json из всех плагинов в репозитории.

Использование:
    python publish.py

Для каждого плагина должны быть:
    <category>/<plugin_name>/plugin.py
    <category>/<plugin_name>/manifest.json
"""

import json
from pathlib import Path

REPO_RAW_BASE = "https://raw.githubusercontent.com/Ameight/tl-ide-plugins/master"
REGISTRY_FILE = Path("registry.json")
SKIP_DIRS = {"__pycache__", ".git", ".github"}


def load_manifest(manifest_path: Path) -> dict | None:
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  Ошибка чтения {manifest_path}: {e}")
        return None


def main():
    registry = []

    for manifest_path in sorted(Path(".").rglob("manifest.json")):
        parts = manifest_path.parts
        # Ожидаем: <category>/<plugin_name>/manifest.json
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
            "path": plugin_id,
            "raw_url": f"{REPO_RAW_BASE}/{plugin_id}/plugin.py",
            **manifest,
        }
        registry.append(entry)
        print(f"  ✅ {plugin_id}  ({manifest.get('name', '?')})")

    REGISTRY_FILE.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n📦 registry.json обновлён — {len(registry)} плагинов")


if __name__ == "__main__":
    main()

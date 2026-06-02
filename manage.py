#!/usr/bin/env python3
"""
TL IDE Marketplace Manager — единая точка управления маркетплейсом.

Интерактивное меню:
    python manage.py

CLI-режим (для CI/CD):
    python manage.py publish   — обновить registry.json
    python manage.py lint      — проверить плагины (exit 1 при ошибках)
    python manage.py init      — инициализировать конфигурацию
"""

from __future__ import annotations
import json
import pathlib
import re
import shutil
import sys
from urllib.parse import urlparse

# ── YAML (опционально) ────────────────────────────────────────────────────────
try:
    import yaml
    def _yaml_load(text: str) -> dict: return yaml.safe_load(text) or {}
    def _yaml_dump(d: dict) -> str:
        return yaml.dump(d, allow_unicode=True, sort_keys=False, default_flow_style=False)
except ImportError:
    def _yaml_load(text: str) -> dict:
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip().strip('"').strip("'")
        return result
    def _yaml_dump(d: dict) -> str:
        return "\n".join(
            f'{k}: "{v}"' if isinstance(v, str) else f'{k}: {v}'
            for k, v in d.items()
        ) + "\n"

# ── ANSI ──────────────────────────────────────────────────────────────────────
_NO_COLOR = not sys.stdout.isatty()

def _c(t: str, *codes: int) -> str:
    return t if _NO_COLOR else f"\033[{';'.join(map(str, codes))}m{t}\033[0m"

def green(t):  return _c(t, 32)
def yellow(t): return _c(t, 33)
def red(t):    return _c(t, 31)
def bold(t):   return _c(t, 1)
def dim(t):    return _c(t, 2)
def cyan(t):   return _c(t, 36)

# ── Константы ─────────────────────────────────────────────────────────────────
ROOT         = pathlib.Path(".")
CONFIG_FILE  = ROOT / "publish.yaml"
REGISTRY_OUT = ROOT / "registry.json"
SKIP_DIRS    = {"__pycache__", ".git", ".github", "versions"}
REQUIRED_FIELDS = {"name", "category", "description", "author", "version"}
SEMVER_RE    = re.compile(r"^\d+\.\d+\.\d+$")

# ── Конфиг ────────────────────────────────────────────────────────────────────
def load_config() -> dict:
    return _yaml_load(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}

def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(_yaml_dump(cfg), encoding="utf-8")

# ── Модель плагина ────────────────────────────────────────────────────────────
class PluginInfo:
    def __init__(self, category: str, name: str, path: pathlib.Path):
        self.category   = category
        self.name       = name
        self.path       = path
        self.plugin_id  = f"{category}/{name}"
        self.plugin_py  = path / "plugin.py"
        self.manifest_path = path / "manifest.json"
        self.versions_dir  = path / "versions"
        self._manifest: dict | None = None

    @property
    def manifest(self) -> dict:
        if self._manifest is None:
            try:
                self._manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception:
                self._manifest = {}
        return self._manifest

    @property
    def display_name(self) -> str:
        return self.manifest.get("name", self.name)

    @property
    def version(self) -> str:
        return self.manifest.get("version", "?")

    @property
    def old_versions(self) -> list[str]:
        if not self.versions_dir.is_dir():
            return []
        return sorted(p.stem for p in self.versions_dir.glob("*.py"))


def scan_plugins() -> list[PluginInfo]:
    plugins = []
    for mp in sorted(ROOT.rglob("manifest.json")):
        parts = mp.parts
        if len(parts) != 3 or any(p in SKIP_DIRS for p in parts):
            continue
        category, name, _ = parts
        plugins.append(PluginInfo(category, name, mp.parent))
    return plugins

# ── Lint ──────────────────────────────────────────────────────────────────────
class LintResult:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.errors:   list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors


def lint_plugin(p: PluginInfo) -> LintResult:
    r = LintResult(p.plugin_id)

    if not p.manifest_path.exists():
        r.errors.append("manifest.json не найден")
        return r

    try:
        manifest = json.loads(p.manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.errors.append(f"manifest.json: невалидный JSON — {e}")
        return r

    for field in REQUIRED_FIELDS:
        val = manifest.get(field)
        if not val:
            r.errors.append(f"manifest.json: поле «{field}» отсутствует или пустое")
        elif not isinstance(val, str):
            r.errors.append(f"manifest.json: поле «{field}» должно быть строкой")

    ver = manifest.get("version", "")
    if ver and not SEMVER_RE.match(ver):
        r.errors.append(f"manifest.json: version «{ver}» не semver (нужно X.Y.Z)")

    if not p.plugin_py.exists():
        r.errors.append("plugin.py не найден")
    else:
        src = p.plugin_py.read_text(encoding="utf-8")
        try:
            compile(src, str(p.plugin_py), "exec")
        except SyntaxError as e:
            r.errors.append(f"plugin.py: синтаксическая ошибка — {e}")
        if "PluginInterface" not in src:
            r.errors.append("plugin.py: нет ссылки на PluginInterface")
        if "def run(" not in src:
            r.errors.append("plugin.py: нет метода run()")
        if "def get_display_name(" not in src:
            r.warnings.append("plugin.py: нет get_display_name() — будет имя класса")

    changelogs: dict = manifest.get("changelogs", {})
    if p.versions_dir.is_dir():
        for vf in sorted(p.versions_dir.glob("*.py")):
            vname = vf.stem
            if not SEMVER_RE.match(vname):
                r.warnings.append(f"versions/{vf.name}: имя файла — не semver")
            if vname not in changelogs:
                r.warnings.append(f"versions/{vname}.py: нет записи в changelogs")

    if changelogs and ver and ver not in changelogs:
        r.warnings.append(f"changelogs: нет описания для текущей версии {ver}")

    return r


def cmd_lint(plugins: list[PluginInfo] | None = None) -> bool:
    if plugins is None:
        plugins = scan_plugins()
    if not plugins:
        print(yellow("  Плагины не найдены."))
        return True

    all_ok = True
    for p in plugins:
        result = lint_plugin(p)
        icon = green("✅") if result.ok else red("❌")
        warn = yellow(f"  ({len(result.warnings)} предупр.)") if result.warnings else ""
        print(f"  {icon}  {bold(p.plugin_id)}{warn}")
        for e in result.errors:
            print(f"       {red('✗')} {e}")
        for w in result.warnings:
            print(f"       {yellow('⚠')} {w}")
        if not result.ok:
            all_ok = False
    return all_ok

# ── Публикация ────────────────────────────────────────────────────────────────
def _build_versions_list(p: PluginInfo, base_url: str) -> list[dict]:
    manifest     = p.manifest
    changelogs   = manifest.get("changelogs", {})
    current_ver  = manifest.get("version", "")
    entries: list[dict] = []

    if p.versions_dir.is_dir():
        for vf in sorted(p.versions_dir.glob("*.py")):
            ver = vf.stem
            entry: dict = {"version": ver, "raw_url": f"{base_url}/{p.plugin_id}/versions/{vf.name}"}
            if cl := changelogs.get(ver):
                entry["changelog"] = cl
            entries.append(entry)

    current: dict = {"version": current_ver, "raw_url": f"{base_url}/{p.plugin_id}/plugin.py"}
    if cl := changelogs.get(current_ver):
        current["changelog"] = cl
    entries.append(current)
    return entries if len(entries) > 1 else []


def cmd_publish() -> None:
    cfg      = load_config()
    base_url = cfg.get("base_url", "").rstrip("/")
    if not base_url:
        print(red("  ❌ base_url не задан в publish.yaml. Сначала запусти: python manage.py init"))
        sys.exit(1)

    plugins = scan_plugins()
    if not plugins:
        print(yellow("  Плагины не найдены."))
        return

    print("  Проверяю плагины...\n")
    results     = [(p, lint_plugin(p)) for p in plugins]
    bad         = [(p, r) for p, r in results if not r.ok]

    for p, r in results:
        icon = green("✅") if r.ok else red("❌")
        warn = yellow(f"  ({len(r.warnings)} предупр.)") if r.warnings else ""
        print(f"  {icon}  {bold(p.plugin_id)}{warn}")
        for e in r.errors:
            print(f"       {red('✗')} {e}")
        for w in r.warnings:
            print(f"       {yellow('⚠')} {w}")

    print()
    if bad:
        if not sys.stdin.isatty():
            print(red("  Ошибки валидации. Публикация прервана."))
            sys.exit(1)
        ans = _prompt("  Есть ошибки. Продолжить публикацию?", "нет")
        if ans.lower() not in ("да", "yes", "y", "д"):
            print("  Отменено.")
            return
        print()

    output = pathlib.Path(cfg.get("output", "registry.json"))
    registry: list[dict] = []
    for p in plugins:
        manifest = {k: v for k, v in p.manifest.items() if k != "changelogs"}
        versions = _build_versions_list(p, base_url)
        entry    = {"id": p.plugin_id, "raw_url": f"{base_url}/{p.plugin_id}/plugin.py", **manifest}
        if versions:
            entry["versions"] = versions
        registry.append(entry)

    output.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for entry in registry:
        vi = dim(f"  [{len(entry['versions'])} vers.]") if entry.get("versions") else ""
        print(f"  {green('📦')}  {entry['id']}  {dim('v' + entry.get('version','?'))}{vi}")
    print(f"\n  {green('✅')} {output}  ({len(registry)} плагин(ов))")
    print(f"  {dim(base_url)}")

# ── Добавить плагин ───────────────────────────────────────────────────────────
_PLUGIN_TPL = '''\
from sdk.base_plugin import PluginInterface


class {class_name}(PluginInterface):

    def get_display_name(self) -> str:
        return "{display_name}"

    def get_description(self) -> str:
        return "{description}"

    def get_category(self) -> str:
        return "{category}"

    def get_config_schema(self) -> dict:
        return {{
            # config: True — задаётся один раз, раздел «Настройки плагина»
            # "base_url": {{
            #     "label": "URL сервиса",
            #     "type": "string",
            #     "default": "https://example.com",
            #     "config": True,
            # }},
            "input": {{
                "label": "Входные данные",
                "type": "string",   # string | textarea | int | bool | select_or_input
                "default": "",
            }},
        }}

    def run(self, inputs: dict) -> str:
        value = inputs.get("input", "")
        # TODO: реализовать логику
        return f"**Результат:** {{value}}"
'''

_MANIFEST_TPL = '''\
{{
  "name": "{display_name}",
  "category": "{category}",
  "description": "{description}",
  "author": "{author}",
  "version": "1.0.0",
  "min_app_version": "1.1.0",
  "requires": [],
  "changelogs": {{
    "1.0.0": "Первый релиз"
  }}
}}
'''


def cmd_add_plugin(plugins: list[PluginInfo]) -> None:
    cfg            = load_config()
    default_author = cfg.get("author", "")
    categories     = sorted({p.category for p in plugins})
    print()

    if categories:
        print("  Существующие категории:")
        for i, c in enumerate(categories, 1):
            print(f"    {i}. {cyan(c)}")
        print(f"    {len(categories)+1}. Создать новую")
        choice = _prompt(f"  Категория [1-{len(categories)+1}]", "1")
        try:
            idx = int(choice) - 1
            category = categories[idx] if idx < len(categories) else \
                _prompt("  Название новой категории").strip().lower().replace(" ", "_")
        except (ValueError, IndexError):
            category = choice.strip().lower()
    else:
        category = _prompt("  Категория", "general").strip().lower().replace(" ", "_")

    name = _prompt("  Имя плагина (snake_case)", "").strip().lower().replace(" ", "_")
    if not name:
        print(red("  Имя не может быть пустым.")); return

    plugin_dir = ROOT / category / name
    if plugin_dir.exists():
        print(red(f"  ❌ {plugin_dir} уже существует.")); return

    display_name = _prompt("  Название в UI", name.replace("_", " ").title())
    description  = _prompt("  Описание (одна строка)", f"Плагин {display_name}.")
    author       = _prompt("  Автор", default_author)
    class_name   = "".join(w.title() for w in name.split("_")) + "Plugin"

    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(
        _PLUGIN_TPL.format(class_name=class_name, display_name=display_name,
                           description=description, category=category.title()),
        encoding="utf-8",
    )
    (plugin_dir / "manifest.json").write_text(
        _MANIFEST_TPL.format(display_name=display_name, category=category.title(),
                             description=description, author=author),
        encoding="utf-8",
    )
    print(f"\n  {green('✅')} Создан {bold(f'{category}/{name}')}")
    print(f"  Отредактируй {bold(str(plugin_dir / 'plugin.py'))} и добавь логику.")

# ── Добавить версию ───────────────────────────────────────────────────────────
def _bump(version: str) -> str:
    parts = version.split(".")
    if len(parts) == 3:
        try:
            return f"{parts[0]}.{parts[1]}.{int(parts[2])+1}"
        except ValueError:
            pass
    return ""


def cmd_add_version(plugins: list[PluginInfo]) -> None:
    if not plugins:
        print(yellow("  Нет плагинов.")); return

    print()
    for i, p in enumerate(plugins, 1):
        vers   = p.old_versions
        v_info = dim(f" + {len(vers)}: {', '.join(vers)}") if vers else ""
        print(f"  {i}. {bold(p.plugin_id)}  v{cyan(p.version)}{v_info}")

    choice = _prompt(f"\n  Плагин [1-{len(plugins)}]", "1")
    try:
        p = plugins[int(choice) - 1]
    except (ValueError, IndexError):
        print(red("  Неверный выбор.")); return

    current_ver = p.version
    new_ver     = _prompt(f"  Новая версия (текущая: {current_ver})", _bump(current_ver))

    if not SEMVER_RE.match(new_ver):
        print(red(f"  ❌ «{new_ver}» — не semver.")); return
    if new_ver == current_ver:
        print(red("  ❌ Совпадает с текущей.")); return

    changelog_new = _prompt(f"  Changelog для {new_ver}", "")

    manifest    = dict(p.manifest)
    changelogs  = dict(manifest.get("changelogs", {}))

    if current_ver not in changelogs:
        cl_old = _prompt(f"  Changelog для {current_ver} (оставить пустым — пропустить)", "")
        if cl_old:
            changelogs[current_ver] = cl_old

    if changelog_new:
        changelogs[new_ver] = changelog_new

    # Сохраняем текущий plugin.py → versions/<current_ver>.py
    versions_dir = p.path / "versions"
    versions_dir.mkdir(exist_ok=True)
    dest = versions_dir / f"{current_ver}.py"
    if dest.exists():
        ans = _prompt(f"  versions/{current_ver}.py уже есть. Перезаписать?", "нет")
        if ans.lower() not in ("да", "yes", "y", "д"):
            print("  Отменено."); return
    shutil.copy(p.plugin_py, dest)

    manifest["version"] = new_ver
    if changelogs:
        manifest["changelogs"] = changelogs

    p.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n  {green('✅')} v{current_ver} → {bold(f'versions/{current_ver}.py')}")
    print(f"  Манифест: {current_ver} → {bold(new_ver)}")
    print(f"  Теперь отредактируй {bold('plugin.py')} с кодом версии {new_ver}.")

# ── Init ──────────────────────────────────────────────────────────────────────
def _detect_platform(host: str) -> str | None:
    if host == "github.com":                         return "github"
    if host == "gitlab.com" or "gitlab" in host:    return "gitlab"
    if host == "bitbucket.org":                      return "bitbucket"
    return None


def _build_raw_base(repo_url: str, branch: str) -> str:
    url    = repo_url.rstrip("/").removesuffix(".git")
    parsed = urlparse(url)
    host   = parsed.hostname or ""
    scheme = parsed.scheme or "https"
    path   = parsed.path.strip("/")

    platform = _detect_platform(host)
    if not platform:
        print(f"\n  Хост «{host}» не распознан автоматически.")
        platform = _prompt_choice(
            "  Платформа", ["gitlab", "gitea", "bitbucket", "custom"], "gitlab"
        )

    if platform == "github":
        return f"https://raw.githubusercontent.com/{path}/{branch}"
    if platform == "gitlab":
        return f"{scheme}://{host}/{path}/-/raw/{branch}"
    if platform == "gitea":
        return f"{scheme}://{host}/{path}/raw/branch/{branch}"
    if platform == "bitbucket":
        return f"https://bitbucket.org/{path}/raw/{branch}"
    return _prompt("  Base raw URL", f"https://{host}/{path}/raw/{branch}")


def cmd_init() -> None:
    existing = load_config()
    if existing.get("base_url"):
        print(f"\n  Уже инициализировано.")
        print(f"  base_url: {dim(existing['base_url'])}")
        if existing.get("author"):
            print(f"  author:   {dim(existing['author'])}")
        if _prompt("\n  Изменить конфигурацию?", "нет").lower() not in ("да", "yes", "y", "д"):
            return

    print()
    repo_url = _prompt("  URL репозитория", "https://github.com/your-org/your-plugins")
    branch   = _prompt("  Ветка", "master")
    author   = _prompt("  Автор по умолчанию (для шаблонов)", existing.get("author", ""))
    base_url = _build_raw_base(repo_url, branch)

    cfg: dict = {"base_url": base_url, "output": "registry.json"}
    if author:
        cfg["author"] = author
    save_config(cfg)

    if not (ROOT / ".gitignore").exists():
        (ROOT / ".gitignore").write_text("__pycache__/\n*.pyc\n.env\n", encoding="utf-8")
        print(f"  {green('✅')} Создан .gitignore")

    print(f"  {green('✅')} Создан publish.yaml")
    print(f"  base_url: {dim(base_url)}\n")

    if not scan_plugins():
        ans = _prompt("  Создать пример плагина hello_world?", "да")
        if ans.lower() not in ("нет", "no", "n", "н"):
            _scaffold_hello_world(author)


def _scaffold_hello_world(author: str) -> None:
    d = ROOT / "general" / "hello_world"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.py").write_text(
        _PLUGIN_TPL.format(class_name="HelloWorldPlugin", display_name="Hello World",
                           description="Пример плагина.", category="General"),
        encoding="utf-8",
    )
    (d / "manifest.json").write_text(
        _MANIFEST_TPL.format(display_name="Hello World", category="General",
                             description="Пример плагина.", author=author or "you"),
        encoding="utf-8",
    )
    print(f"  {green('✅')} Создан general/hello_world/")

# ── Статус ────────────────────────────────────────────────────────────────────
def _print_status(plugins: list[PluginInfo]) -> None:
    cfg      = load_config()
    base_url = cfg.get("base_url") or red("не задан — выбери «Инициализация»")
    n_vers   = sum(len(p.old_versions) + 1 for p in plugins)

    print(f"\n  {bold('base_url:')}  {dim(base_url) if cfg.get('base_url') else base_url}")
    print(f"  {bold('Плагинов:')}  {len(plugins)}  |  {bold('Версий:')} {n_vers}\n")

    for p in plugins:
        vers = p.old_versions
        v_str = f"v{cyan(p.version)}"
        if vers:
            v_str += dim(f"  (+ {len(vers)}: {', '.join(vers)})")
        print(f"    • {bold(p.plugin_id)}  {v_str}")

    if not plugins:
        print(f"    {dim('Плагинов пока нет.')}")
    print()

# ── Вспомогательные функции ввода ─────────────────────────────────────────────
def _prompt(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val = (input(f"{question}{hint}: ").strip()) or default
    # macOS/Windows sometimes inject lone surrogates via input(); strip them
    return val.encode("utf-8", errors="replace").decode("utf-8")


def _prompt_choice(question: str, choices: list[str], default: str) -> str:
    opts = " / ".join(choices)
    while True:
        val = (input(f"{question} ({opts}) [{default}]: ").strip().lower()) or default
        if val in choices:
            return val
        print(f"    Введи одно из: {opts}")

# ── Главное меню ──────────────────────────────────────────────────────────────
def _menu() -> None:
    while True:
        plugins = scan_plugins()

        print(bold("┌─────────────────────────────────────────────┐"))
        print(bold("│   TL IDE Marketplace Manager                │"))
        print(bold("└─────────────────────────────────────────────┘"))
        _print_status(plugins)

        is_init = bool(load_config().get("base_url"))
        init_label = "Изменить конфигурацию" if is_init else "Инициализировать репозиторий"

        print(f"  {bold('1')}. Обновить registry.json")
        print(f"  {bold('2')}. Добавить новый плагин")
        print(f"  {bold('3')}. Добавить версию существующего плагина")
        print(f"  {bold('4')}. Проверить плагины (lint)")
        print(f"  {bold('5')}. {init_label}")
        print(f"  {bold('0')}. Выход\n")

        choice = input("  > ").strip()
        print()

        if   choice == "1": cmd_publish()
        elif choice == "2": cmd_add_plugin(plugins)
        elif choice == "3": cmd_add_version(plugins)
        elif choice == "4": cmd_lint(plugins)
        elif choice == "5": cmd_init()
        elif choice == "0": break
        else: print(yellow("  Неверный выбор."))

        print()
        input(f"  {dim('[ Enter — назад в меню ]')}")
        print("\n" * 2)

# ── Точка входа ───────────────────────────────────────────────────────────────
def main() -> None:
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if   cmd == "publish": cmd_publish()
        elif cmd == "lint":
            ok = cmd_lint()
            sys.exit(0 if ok else 1)
        elif cmd == "init":    cmd_init()
        else:
            print(f"Неизвестная команда: {cmd}")
            print("Доступно: publish | lint | init")
            sys.exit(1)
        return

    # Авто-инит при первом запуске
    if not load_config().get("base_url"):
        print(bold("\n╔══════════════════════════════════════════════╗"))
        print(bold("║   TL IDE Marketplace Manager                 ║"))
        print(bold("╚══════════════════════════════════════════════╝"))
        print(yellow("\n  publish.yaml не найден — первый запуск. Настроим репозиторий.\n"))
        cmd_init()
        print()

    _menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Выход.")
        sys.exit(0)

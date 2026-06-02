# tl-ide-plugins

Официальный реестр плагинов для [TL IDE](https://github.com/Ameight/mvp_inspector).

---

## Плагины

| Плагин | Категория | Описание |
|---|---|---|
| [IP Checker](general/ip_checker/) | General | Определяет публичный IP-адрес машины |
| [Example: все возможности](general/example_plugin/) | General | Демо всех типов полей и config-настроек |

---

## Структура репозитория

```
tl-ide-plugins/
  publish.py              ← генерирует registry.json
  registry.json           ← индекс всех плагинов (автогенерат)
  manifest.schema.json    ← схема для валидации manifest.json
  <category>/
    <plugin_name>/
      plugin.py           ← код плагина
      manifest.json       ← метаданные
```

---

## Как добавить плагин

### 1. Создай папку

```
general/my_plugin/
```

Имя папки первого уровня — категория (отображается в сайдбаре TL IDE).

### 2. Напиши `manifest.json`

```json
{
  "name": "My Plugin",
  "category": "General",
  "description": "Одна строка — что делает плагин.",
  "author": "твой_ник",
  "version": "1.0.0",
  "min_app_version": "1.1.0",
  "requires": ["requests"]
}
```

| Поле | Обязательно | Описание |
|---|:-:|---|
| `name` | ✅ | Название в сайдбаре |
| `category` | ✅ | Группа (`Jira`, `General`, `DevOps`…) |
| `description` | ✅ | Одна строка под заголовком |
| `author` | ✅ | GitHub ник |
| `version` | ✅ | SemVer: `1.0.0` |
| `min_app_version` | — | Минимальная версия TL IDE |
| `requires` | — | pip-зависимости: `["requests", "boto3"]` |
| `versions` | — | История версий для даунгрейда (см. ниже) |

### 3. Напиши `plugin.py`

```python
import os
from sdk.base_plugin import PluginInterface


class MyPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "My Plugin"

    def get_description(self) -> str:
        return "Одна строка — что делает плагин."

    def get_category(self) -> str:
        return "General"

    def get_config_key(self) -> str:
        # Ключ для config.yaml → plugins.<key>
        return "my_plugin"

    def get_required_env(self) -> dict:
        # Секреты: токены, пароли. TL IDE покажет диалог для ввода.
        return {
            "MY_TOKEN": {
                "label": "Токен сервиса",
                "description": "Получи на сайте → Settings → API",
                "secret": True,
            }
        }

    def get_config_schema(self) -> dict:
        return {
            # config: True → раздел «Настройки плагина», задаётся один раз
            "base_url": {
                "label": "URL сервиса",
                "type": "string",
                "default": "https://api.example.com",
                "config": True,
            },
            # без config → per-run поле, меняется каждый запуск
            "query": {
                "label": "Запрос",
                "type": "string",
                "default": "",
            },
        }

    def run(self, inputs: dict) -> str:
        token    = os.getenv("MY_TOKEN", "")
        base_url = inputs.get("base_url", "")
        query    = inputs.get("query", "")
        # ... реализация ...
        return f"**Результат:** {query}"
```

### 4. Сделай Pull Request

Открой PR в этот репозиторий. После мержа мейнтейнер запустит `publish.py` и `registry.json` обновится автоматически.

---

## Три уровня данных плагина

| Уровень | Где хранится у пользователя | Как объявить |
|---|---|---|
| **Секреты** (токены, пароли) | `.env` | `get_required_env()` |
| **Настройки** (URL, дефолты) | Форма → сохраняется между запусками | `get_config_schema()` + `"config": True` |
| **Per-run входные данные** | Форма → меняется каждый запуск | `get_config_schema()` без флага |

### Типы полей формы

| `type` | Виджет |
|---|---|
| `string` | Однострочный ввод |
| `textarea` | Многострочный ввод (код, промпты) |
| `int` | Числовой ввод |
| `bool` | Чекбокс |
| `select_or_input` | Выпадающий список + ручной ввод |

---

## История версий плагина

Храни старые версии прямо в репозитории — `publish.py` соберёт массив `versions[]` автоматически.

### Структура

```
general/my_plugin/
  plugin.py              ← текущая версия (всегда)
  manifest.json
  versions/
    1.0.0.py             ← старые версии как отдельные файлы
    1.1.0.py
```

### manifest.json

Добавь `changelogs` — описания для каждой версии:

```json
{
  "name": "My Plugin",
  "version": "1.2.0",
  "changelogs": {
    "1.0.0": "Первый релиз",
    "1.1.0": "Улучшена обработка ошибок",
    "1.2.0": "Поддержка нового API"
  }
}
```

`publish.py` автоматически:
1. Сканирует `versions/*.py` → строит записи со ссылками на эти файлы
2. Добавляет текущую версию (`plugin.py`) последней
3. Записывает итоговый массив `versions[]` в `registry.json`

В маркетплейсе TL IDE отобразит выпадающий список версий с возможностью даунгрейда.

---

## Инструмент управления — manage.py

Единая точка входа для всех операций с маркетплейсом.

### Интерактивное меню

```bash
python manage.py
```

Показывает текущее состояние (сколько плагинов, версий) и меню:

```
  1. Обновить registry.json
  2. Добавить новый плагин
  3. Добавить версию существующего плагина
  4. Проверить плагины (lint)
  5. Изменить конфигурацию
  0. Выход
```

При первом запуске автоматически запускает мастер инициализации.

### CLI-режим (для CI/CD)

```bash
python manage.py publish   # обновить registry.json (с валидацией)
python manage.py lint      # проверить плагины (exit 1 при ошибках)
python manage.py init      # настроить конфигурацию
```

`python publish.py` по-прежнему работает (тонкая обёртка над `manage.py publish`).

### Добавить новый плагин

`manage.py` спросит категорию (или предложит создать новую), имя, описание, автора и создаст готовый шаблон `plugin.py` + `manifest.json`.

### Добавить версию плагина

1. Выбираешь плагин из списка
2. Вводишь новый номер версии
3. Инструмент **автоматически**:
   - Копирует `plugin.py` → `versions/<текущая_версия>.py`
   - Обновляет `version` в `manifest.json`
   - Добавляет changelog-запись
4. Осталось только отредактировать `plugin.py` с новым кодом

### Валидация (lint)

Проверяет каждый плагин:
- `manifest.json` — наличие, корректный JSON, все обязательные поля, semver-формат версии
- `plugin.py` — наличие, синтаксис Python, наличие `PluginInterface` и метода `run()`
- `versions/` — semver-имена файлов, наличие changelog-записей

Ошибки блокируют публикацию; предупреждения показываются, но не блокируют.

### Автоматически через GitHub Actions

```yaml
# .github/workflows/publish.yml
name: Publish registry
on:
  push:
    branches: [master]
    paths: ["**/manifest.json", "**/plugin.py"]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: python manage.py publish
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: update registry"
          file_pattern: registry.json
```

---

## Совместимость

| `min_app_version` | Импорт |
|:-:|---|
| `1.1.0` и выше | `from sdk.base_plugin import PluginInterface` |
| ниже `1.1.0` | `from plugins.base_plugin import PluginInterface` |
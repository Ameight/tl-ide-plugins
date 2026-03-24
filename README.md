# tl-ide-plugins

Официальный реестр плагинов для [TL IDE](https://github.com/Ameight/mvp_inspector).

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

Каждый плагин живёт в папке `<категория>/<имя>/`. Категория определяет группу в сайдбаре приложения.

---

## Как добавить плагин

### 1. Создай папку

```
jira/my_new_plugin/
```

### 2. Напиши `manifest.json`

```json
{
  "name": "My New Plugin",
  "category": "Jira",
  "description": "Одна строка — что делает плагин.",
  "author": "твой_ник",
  "version": "1.0.0",
  "requires": ["requests"]
}
```

| Поле | Обязательно | Описание |
|------|:-----------:|----------|
| `name` | ✅ | Название в сайдбаре |
| `category` | ✅ | Группа (`Jira`, `General`, `DevOps`...) |
| `description` | ✅ | Одна строка под заголовком |
| `author` | ✅ | GitHub ник |
| `version` | ✅ | SemVer: `1.0.0` |
| `requires` | — | pip-зависимости: `["requests", "boto3"]` |

### 3. Напиши `plugin.py`

```python
import os
from plugins.base_plugin import PluginInterface


class MyNewPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "My New Plugin"

    def get_description(self) -> str:
        return "Одна строка — что делает плагин."

    def get_category(self) -> str:
        return "Jira"

    def get_config_schema(self) -> dict:
        return {
            "input": {
                "label": "Входные данные",
                "type": "string",   # string | textarea | int | bool | select_or_input
                "default": "",
            },
        }

    def run(self, inputs: dict) -> str:
        value = inputs.get("input", "")

        # Secrets (токены) — через .env пользователя:
        token = os.getenv("MY_TOKEN", "")

        # Не-секретный конфиг (URL и т.п.) — через config.yaml:
        base_url = self.config.get("base_url", "")

        return f"**Результат:** {value}"
```

### 4. Сделай Pull Request

Открой PR в этот репозиторий. После мержа мейнтейнер запустит `publish.py` и `registry.json` обновится.

---

## Как публиковать (для мейнтейнеров)

После мержа PR запусти в корне репозитория:

```bash
python publish.py
```

Скрипт обойдёт все папки с `manifest.json` + `plugin.py` и перезапишет `registry.json`. Закоммить результат:

```bash
git add registry.json
git commit -m "chore: update registry"
git push
```

---

## Как устроен `registry.json`

Генерируется автоматически. Пример записи:

```json
{
  "id": "jira/issue_info",
  "path": "jira/issue_info",
  "raw_url": "https://raw.githubusercontent.com/Ameight/tl-ide-plugins/main/jira/issue_info/plugin.py",
  "name": "Issue Info",
  "category": "Jira",
  "description": "Получить информацию по ключу задачи (PROJ-123).",
  "author": "Ameight",
  "version": "1.0.0",
  "requires": ["requests"]
}
```

`raw_url` — прямая ссылка, по которой TL IDE скачивает `plugin.py` при установке.

---

## Secrets и конфиг

Плагины **не хранят** секреты в коде. Соглашение:

- **Токены, пароли** → файл `.env` у пользователя → читать через `os.getenv("VAR_NAME")`
- **URL, настройки** → `config.yaml` у пользователя → читать через `self.config.get("key")`

Документируй нужные переменные в описании плагина.

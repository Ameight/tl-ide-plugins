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

---

## Как добавить плагин

### 1. Создай папку

```
general/my_new_plugin/
```

Имя папки первого уровня — категория (отображается в сайдбаре).

### 2. Напиши `manifest.json`

```json
{
  "name": "My New Plugin",
  "category": "General",
  "description": "Одна строка — что делает плагин.",
  "author": "твой_ник",
  "version": "1.0.0",
  "min_app_version": "1.1.0",
  "requires": ["requests"]
}
```

| Поле | Обязательно | Описание |
|------|:-----------:|----------|
| `name` | ✅ | Название в сайдбаре |
| `category` | ✅ | Группа (`Jira`, `General`, `DevOps`...) |
| `description` | ✅ | Одна строка под заголовком |
| `author` | ✅ | GitHub ник |
| `version` | ✅ | SemVer плагина: `1.0.0` |
| `min_app_version` | — | Минимальная версия TL IDE. Если не указано — плагин совместим со всеми версиями |
| `requires` | — | pip-зависимости: `["requests", "boto3"]` |
| `versions` | — | История версий для даунгрейда (см. ниже) |

### 3. Напиши `plugin.py`

```python
import os
from sdk.base_plugin import PluginInterface


class MyNewPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "My New Plugin"

    def get_description(self) -> str:
        return "Одна строка — что делает плагин."

    def get_category(self) -> str:
        return "General"

    def get_config_schema(self) -> dict:
        return {
            "input": {
                "label": "Входные данные",
                "type": "string",   # string | textarea | int | bool | select_or_input
                "default": "",
            },
        }

    def get_required_env(self) -> dict:
        return {
            "MY_TOKEN": {
                "label": "Токен сервиса",
                "description": "Получи на сайте сервиса → Settings → API",
                "secret": True,
            }
        }

    def run(self, inputs: dict) -> str:
        value = inputs.get("input", "")
        token = os.getenv("MY_TOKEN", "")
        base_url = self.config.get("base_url", "")
        return f"**Результат:** {value}"
```

> **Важно:** импорт всегда `from sdk.base_plugin import PluginInterface` (начиная с TL IDE 1.1.0).

### 4. Сделай Pull Request

Открой PR в этот репозиторий. После мержа мейнтейнер запустит `publish.py` и `registry.json` обновится.

---

## История версий плагина (versions)

Чтобы пользователи могли выбирать версию или откатиться назад, добавь в `manifest.json` поле `versions`:

```json
{
  "name": "My Plugin",
  "version": "1.2.0",
  "min_app_version": "1.1.0",
  "versions": [
    {
      "version": "1.0.0",
      "raw_url": "https://raw.githubusercontent.com/org/repo/v1.0.0/general/my_plugin/plugin.py",
      "changelog": "Первый релиз"
    },
    {
      "version": "1.1.0",
      "raw_url": "https://raw.githubusercontent.com/org/repo/v1.1.0/general/my_plugin/plugin.py",
      "changelog": "Улучшена обработка ошибок"
    },
    {
      "version": "1.2.0",
      "raw_url": "https://raw.githubusercontent.com/org/repo/master/general/my_plugin/plugin.py",
      "changelog": "Поддержка нового API"
    }
  ]
}
```

В маркетплейсе TL IDE отобразит выпадающий список версий с кнопкой «Установить».

---

## Как создать свой маркетплейс

Любой Git-репозиторий с `registry.json` может стать маркетплейсом. Это удобно для внутрикорпоративных плагинов.

### 1. Создай репозиторий

Структура та же: `<category>/<plugin_name>/plugin.py` + `manifest.json`.

### 2. Сгенерируй `registry.json`

Скопируй `publish.py` из этого репо и поправь `REPO_RAW_BASE`:

```python
REPO_RAW_BASE = "https://raw.githubusercontent.com/your-org/your-plugins/master"
```

Запусти:

```bash
python publish.py
```

Закоммить и запушить `registry.json`.

### 3. Подключи в TL IDE

В TL IDE → Настройки → Маркетплейсы → добавь URL до `registry.json`:

```
https://raw.githubusercontent.com/your-org/your-plugins/master/registry.json
```

> Для приватных репозиториев GitHub передаёт токен через заголовок при запросе `raw.githubusercontent.com` — или используй GitHub Pages / любой CDN.

### Автоматическая публикация через GitHub Actions

```yaml
# .github/workflows/publish.yml
name: Publish registry
on:
  push:
    branches: [master]
    paths:
      - '**/manifest.json'
      - '**/plugin.py'

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python publish.py
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: update registry"
          file_pattern: registry.json
```

После этого `registry.json` обновляется автоматически при каждом мерже в `master`.

---

## Как публиковать вручную (для мейнтейнеров)

```bash
python publish.py
git add registry.json
git commit -m "chore: update registry"
git push
```

---

## Формат `registry.json`

Генерируется автоматически из `manifest.json`. Пример записи:

```json
{
  "id": "jira/issue_info",
  "path": "jira/issue_info",
  "raw_url": "https://raw.githubusercontent.com/Ameight/tl-ide-plugins/master/jira/issue_info/plugin.py",
  "name": "Issue Info",
  "category": "Jira",
  "description": "Получить информацию по ключу задачи (PROJ-123).",
  "author": "Ameight",
  "version": "1.1.0",
  "min_app_version": "1.1.0",
  "requires": ["requests"]
}
```

`raw_url` — прямая ссылка, по которой TL IDE скачивает `plugin.py` при установке.

---

## Secrets и конфиг

Плагины **не хранят** секреты в коде. Соглашение:

| Что | Где хранить | Как читать |
|-----|-------------|------------|
| Токены, пароли | `.env` у пользователя | `os.getenv("VAR_NAME")` |
| URL, настройки | `config.yaml` у пользователя | `self.config.get("key")` |

Документируй нужные переменные через `get_required_env()` — TL IDE покажет предупреждение, если переменная не задана.

---

## Совместимость версий

| Версия плагина | `min_app_version` | Импорт |
|:-:|:-:|---|
| ≥ 1.1.0 | `1.1.0` | `from sdk.base_plugin import PluginInterface` |
| 1.0.x | не указывать | `from plugins.base_plugin import PluginInterface` |

Начиная с TL IDE 1.1.0 модуль `plugins` переименован в `sdk`. Плагины под старые версии приложения используют старый импорт.

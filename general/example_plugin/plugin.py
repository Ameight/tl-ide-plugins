"""
Демонстрационный плагин — показывает все возможности TL IDE.

Содержит:
  • все 5 типов полей формы
  • config-поля (задаются один раз, раздел «Настройки плагина»)
  • объявление env-переменной (секрет)
  • форматированный Markdown-вывод
"""
import os
from sdk.base_plugin import PluginInterface


class ExamplePlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "Example: все возможности"

    def get_description(self) -> str:
        return "Демонстрация всех типов полей, config-настроек и env-переменных."

    def get_category(self) -> str:
        return "General"

    def get_config_key(self) -> str:
        return "example_plugin"

    def get_required_env(self) -> dict:
        return {
            "EXAMPLE_TOKEN": {
                "label": "Demo Token",
                "description": (
                    "Задай любое значение — просто для проверки работы секретов. "
                    "Плагин не делает реальных запросов."
                ),
                "secret": True,
            }
        }

    def get_config_schema(self) -> dict:
        return {
            # ── config: True — задаётся один раз ──────────────────────────────
            # Отображается в разделе «Настройки плагина».
            # Значение передаётся в run() через inputs, как обычное поле.
            "service_url": {
                "label": "URL сервиса",
                "type": "string",
                "default": "https://example.com",
                "config": True,
            },
            "response_format": {
                "label": "Формат ответа",
                "type": "select_or_input",
                "options": ["markdown", "plain", "json"],
                "default": "markdown",
                "config": True,
            },

            # ── Per-run поля — меняются каждый запуск ─────────────────────────
            "title": {
                "label": "Заголовок  ·  string",
                "type": "string",
                "default": "Hello, TL IDE!",
            },
            "body": {
                "label": "Описание  ·  textarea",
                "type": "textarea",
                "default": "Поддерживает **Markdown**: *курсив*, `код`, списки.",
            },
            "repeat": {
                "label": "Повторений  ·  int",
                "type": "int",
                "default": 1,
            },
            "show_debug": {
                "label": "Показать отладку  ·  bool",
                "type": "bool",
                "default": False,
            },
            "priority": {
                "label": "Приоритет  ·  select_or_input",
                "type": "select_or_input",
                "options": ["Низкий", "Средний", "Высокий"],
                "default": "Средний",
            },
        }

    def run(self, inputs: dict) -> str:
        # config-поля
        service_url     = inputs.get("service_url", "")
        response_format = inputs.get("response_format", "markdown")

        # per-run поля
        title      = inputs.get("title", "")
        body       = inputs.get("body", "")
        repeat     = max(1, int(inputs.get("repeat") or 1))
        show_debug = bool(inputs.get("show_debug"))
        priority   = inputs.get("priority", "")

        # env-переменная
        token        = os.getenv("EXAMPLE_TOKEN", "")
        token_status = "✅ задан" if token else "❌ не задан"

        sections: list[str] = []

        sections.append(f"# {title}")

        if body:
            block = "\n\n".join([body] * repeat)
            sections.append(block)

        sections.append("---")
        sections.append("## Сводка")
        sections.append(
            "| Параметр | Значение |\n"
            "|---|---|\n"
            f"| Приоритет | {priority} |\n"
            f"| Формат ответа | `{response_format}` |\n"
            f"| URL сервиса | `{service_url}` |\n"
            f"| EXAMPLE_TOKEN | {token_status} |"
        )

        if show_debug:
            sections.append("---")
            sections.append("## Отладка: inputs")
            sections.append(f"```python\n{inputs!r}\n```")

        return "\n\n".join(sections)

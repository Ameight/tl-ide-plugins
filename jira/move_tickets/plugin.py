from sdk.base_plugin import PluginInterface
from jira import JIRA
import os


class MoveTicketsPlugin(PluginInterface):
    """
    Переносит закрытые задачи из одного эпика Jira в другой.

    Все значения, специфичные для конкретной Jira-инстанции (URL, имя поля
    Epic-Link для JQL, customfield ID, статусы) задаются через конфиг — в
    репозиторий они не зашиваются.
    """

    def get_display_name(self) -> str:
        return "Перемещение тикетов в Jira"

    def get_description(self) -> str:
        return (
            "Переносит закрытые задачи из исходного эпика в целевой. "
            "Ищет задачи по полю Epic-Link со статусами Closed / Done."
        )

    def get_category(self) -> str:
        return "Jira"

    def get_config_key(self) -> str:
        return "move_tickets"

    def get_required_env(self) -> dict:
        return {
            "JIRA_TOKEN": {
                "label": "Jira API Token",
                "description": "Токен из Jira → Profile → Security → API tokens",
                "secret": True,
            },
        }

    def get_config_schema(self) -> dict:
        return {
            "jira_url": {
                "label": "Jira URL",
                "type": "string",
                "default": self.config.get("jira_url", "https://jira.atlassian.net"),
                "description": "Адрес вашей Jira (сервер или cloud)",
                "config": True,
            },
            "epic_link_field": {
                "label": "Поле Epic-Link (имя для JQL)",
                "type": "string",
                "default": self.config.get("epic_link_field", "Epic Link"),
                "description": "Имя поля, по которому ищем задачи эпика в JQL "
                               "(может отличаться в локализованной Jira)",
                "config": True,
            },
            "epic_field": {
                "label": "Epic Custom Field ID",
                "type": "string",
                "default": self.config.get("epic_field", ""),
                "description": "ID кастомного поля Epic Link для обновления "
                               "(например, customfield_0000)",
                "config": True,
            },
            "statuses": {
                "label": "Статусы для отбора",
                "type": "string",
                "default": self.config.get("statuses", "Closed, Done"),
                "description": "Список статусов через запятую, которые считаем закрытыми",
                "config": True,
            },
            "source_ticket_key": {
                "label": "Исходный эпик",
                "type": "string",
                "default": "",
                "description": "Ключ эпика, из которого переносим задачи (например, PROJ-123)",
            },
            "dest_ticket_key": {
                "label": "Целевой эпик",
                "type": "string",
                "default": "",
                "description": "Ключ эпика, в который переносим задачи (например, PROJ-456)",
            },
        }

    def run(self, inputs: dict) -> str:
        jira_url = inputs.get("jira_url", self.config.get("jira_url", "https://jira.atlassian.net"))
        epic_link_field = inputs.get("epic_link_field", self.config.get("epic_link_field", "Epic Link")).strip()
        epic_field = inputs.get("epic_field", self.config.get("epic_field", "")).strip()
        statuses = inputs.get("statuses", self.config.get("statuses", "Closed, Done")).strip()
        source_key = inputs.get("source_ticket_key", "").strip()
        dest_key = inputs.get("dest_ticket_key", "").strip()

        # Проверка токена
        api_token = os.getenv("JIRA_TOKEN", "")
        if not api_token:
            return (
                "❌ **Ошибка:** JIRA_TOKEN не настроен.\n\n"
                "Открой ⚙ **Настройки** → **Переменные окружения**, "
                "найди плагин «Перемещение тикетов в Jira» и введи токен."
            )

        if not epic_link_field or not epic_field:
            return (
                "❌ **Ошибка:** не настроены поля Epic-Link.\n\n"
                "В **Настройки плагина** задай:\n"
                f"- Поле Epic-Link (JQL): `{epic_link_field or '—'}`\n"
                f"- Epic Custom Field ID: `{epic_field or '—'}`"
            )

        if not source_key or not dest_key:
            return "❌ **Ошибка:** Заполни оба поля — исходный и целевой эпик."

        if source_key == dest_key:
            return "⚠️ **Предупреждение:** Исходный и целевой эпик совпадают. Нечего переносить."

        # Инициализация Jira клиента
        try:
            jira_client = JIRA(server=jira_url, token_auth=api_token)
        except Exception as e:
            return f"❌ **Ошибка подключения к Jira:**\n```\n{e}\n```"

        # Поиск задач, относящихся к исходному эпику
        query = f'"{epic_link_field}" = "{source_key}" AND status in ({statuses})'
        self.log(f"Выполняю запрос: {query}", level="debug")

        try:
            issues = jira_client.search_issues(query, maxResults=1000)
        except Exception as e:
            return f"❌ **Ошибка поиска задач:**\n```\n{e}\n```"

        if not issues:
            return (
                f"ℹ️ **Ничего не найдено.**\n\n"
                f"Нет закрытых задач, привязанных к эпику **`{source_key}`**.\n"
                f"Проверь:\n"
                f"- ключ эпика (сейчас: `{source_key}`)\n"
                f"- поле Epic-Link (сейчас: `{epic_link_field}`)\n"
                f"- статусы (сейчас: `{statuses}`)"
            )

        # Перенос задач
        results = []
        errors = []
        for issue in issues:
            try:
                jira_client.issue(issue.key).update(fields={epic_field: dest_key})
                results.append(issue.key)
                self.log(f"{issue.key} → {dest_key}", level="info")
            except Exception as e:
                errors.append(f"{issue.key}: {e}")
                self.log(f"Ошибка при переносе {issue.key}: {e}", level="error")

        # Формирование результата
        parts = [
            "## Результат переноса",
            "",
            f"- **Исходный эпик:** `{source_key}`",
            f"- **Целевой эпик:** `{dest_key}`",
            f"- **Всего найдено:** {len(issues)} задач",
            f"- **Успешно перенесено:** {len(results)}",
            "",
        ]

        if results:
            parts.append("### ✅ Перенесённые задачи")
            parts.append("")
            for key in results:
                parts.append(f"- `{key}`")
            parts.append("")

        if errors:
            parts.append("### ❌ Ошибки")
            parts.append("")
            for err in errors:
                parts.append(f"- {err}")
            parts.append("")

        return "\n".join(parts)

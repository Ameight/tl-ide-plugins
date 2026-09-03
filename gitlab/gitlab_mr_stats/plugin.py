import os
import requests
from collections import defaultdict
from sdk.base_plugin import PluginInterface


MR_QUERY = """
query($fullPath: ID!, $state: MergeRequestState, $targetBranches: [String!],
      $createdAfter: Time, $createdBefore: Time, $after: String) {
  project(fullPath: $fullPath) {
    mergeRequests(
      state: $state
      targetBranches: $targetBranches
      createdAfter: $createdAfter
      createdBefore: $createdBefore
      first: 50
      after: $after
      sort: CREATED_DESC
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        iid
        approvedBy { nodes { username } }
        notes(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            system
            resolvable
            author { username }
            discussion { id }
          }
        }
      }
    }
  }
}
"""

NOTES_QUERY = """
query($fullPath: ID!, $iid: String!, $after: String) {
  project(fullPath: $fullPath) {
    mergeRequest(iid: $iid) {
      notes(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          system
          resolvable
          author { username }
          discussion { id }
        }
      }
    }
  }
}
"""

WHOAMI_QUERY = "{ currentUser { username name } }"


# ---------------------------------------------------------------------------
# Структура данных по одному проекту
# ---------------------------------------------------------------------------
class ProjectStats:
    def __init__(self, full_path: str):
        self.full_path = full_path
        self.mr_count = 0
        # user -> set of iid
        self.approvals: dict[str, set] = defaultdict(set)
        # user -> int
        self.comments: dict[str, int] = defaultdict(int)
        self.discussions_started: dict[str, int] = defaultdict(int)

    def all_users(self) -> set:
        return set(self.approvals) | set(self.comments) | set(self.discussions_started)

    def approvals_count(self, user: str) -> int:
        return len(self.approvals.get(user, set()))

    def comments_count(self, user: str) -> int:
        return self.comments.get(user, 0)

    def discussions_count(self, user: str) -> int:
        return self.discussions_started.get(user, 0)


def _table(rows: list[tuple], header: list[str]) -> list[str]:
    """Рендерит Markdown-таблицу. rows — список кортежей значений."""
    aligns = "|" + "|".join(
        "--:" if isinstance(r, (int, float)) else "---"
        for r in (rows[0] if rows else [""] * len(header))
    ) + "|"
    lines = [
        "| " + " | ".join(str(h) for h in header) + " |",
        aligns,
        ]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return lines


def _sort_users(users, stats_list: list[ProjectStats]) -> list[str]:
    """Сортирует пользователей по суммарным аппрувам desc, потом комментарии desc."""
    def key(u):
        a = sum(s.approvals_count(u) for s in stats_list)
        c = sum(s.comments_count(u) for s in stats_list)
        return (-a, -c)
    return sorted(users, key=key)


class GitlabMrStatsPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "GitLab MR Stats"

    def get_description(self) -> str:
        return (
            "Статистика по MR (GraphQL): аппрувы, комментарии, обсуждения. "
            "Сводка + разбивка по проектам или по пользователям."
        )

    def get_category(self) -> str:
        return "GitLab"

    def get_config_key(self) -> str:
        return "gitlab_mr_stats"

    def get_required_env(self) -> dict:
        return {
            "GITLAB_TOKEN": {
                "label": "GitLab Personal Access Token",
                "description": "Токен с правами read_api",
                "secret": True,
            }
        }

    def get_config_schema(self) -> dict:
        return {
            "gitlab_url": {
                "label": "GitLab базовый URL",
                "type": "string",
                "default": self.config.get("gitlab_url", "https://gitlab.com"),
                "config": True,
            },
            "project_ids": {
                "label": "Проекты — fullPath (namespace/project), по одному на строку",
                "type": "textarea",
                "default": "\n".join(self.config.get("project_ids", [])),
                "config": True,
            },
            "team_members": {
                "label": "Участники команды (username, по одному на строку; пусто = все)",
                "type": "textarea",
                "default": "\n".join(self.config.get("team_members", [])),
                "config": True,
            },
            "debug_connection": {
                "label": "🔌 Только проверить соединение",
                "type": "bool",
                "default": False,
            },
            "view": {
                "label": "Режим отчёта",
                "type": "select_or_input",
                "options": [
                    "summary",          # только сводная таблица
                    "by_project",       # сводная + таблица по каждому проекту
                    "by_user",          # сводная + таблица по каждому пользователю
                    "full",             # всё сразу
                ],
                "default": self.config.get("view", "summary"),
            },
            "state": {
                "label": "Статус MR",
                "type": "select_or_input",
                "options": ["merged", "opened", "closed", "all", "locked"],
                "default": self.config.get("state", "merged"),
            },
            "target_branch": {
                "label": "Целевая ветка (пусто = все)",
                "type": "string",
                "default": self.config.get("target_branch", ""),
            },
            "date_from": {
                "label": "Дата от (YYYY-MM-DD)",
                "type": "string",
                "default": self.config.get("date_from", ""),
            },
            "date_to": {
                "label": "Дата до (YYYY-MM-DD)",
                "type": "string",
                "default": self.config.get("date_to", ""),
            },
            "max_mrs_per_project": {
                "label": "Макс. MR на проект",
                "type": "int",
                "default": self.config.get("max_mrs_per_project", 500),
            },
        }

    # ------------------------------------------------------------------
    # HTTP / GraphQL
    # ------------------------------------------------------------------

    def _graphql_url(self, gitlab_url: str) -> str:
        base = gitlab_url.rstrip("/")
        for suffix in ("/api/graphql", "/api/v4", "/api"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        return base + "/api/graphql"

    def _gql(self, gql_url: str, query: str, variables: dict = None) -> dict:
        token = os.getenv("GITLAB_TOKEN", "")
        if not token:
            raise ValueError("Не задан GITLAB_TOKEN")
        resp = requests.post(
            gql_url,
            json={"query": query, "variables": variables or {}},
            headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
            timeout=60,
        )
        if resp.status_code == 401:
            raise RuntimeError(f"401 Unauthorized — токен не принят. URL: {gql_url}")
        if resp.status_code == 404:
            raise RuntimeError(f"404 Not Found — GraphQL не найден по адресу: {gql_url}")
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body:
            messages = "; ".join(e.get("message", str(e)) for e in body["errors"])
            raise RuntimeError(f"GraphQL ошибка: {messages}")
        return body.get("data", {})

    def _parse_lines(self, text: str) -> list:
        return [line.strip() for line in (text or "").splitlines() if line.strip()]

    # ------------------------------------------------------------------
    # Сбор данных
    # ------------------------------------------------------------------

    def _fetch_all_notes(self, gql_url, full_path, iid, first_notes, has_next, cursor):
        notes = list(first_notes)
        while has_next:
            data = self._gql(gql_url, NOTES_QUERY, {
                "fullPath": full_path, "iid": str(iid), "after": cursor,
            })
            page = data.get("project", {}).get("mergeRequest", {}).get("notes", {})
            notes.extend(page.get("nodes", []))
            pi = page.get("pageInfo", {})
            has_next = pi.get("hasNextPage", False)
            cursor = pi.get("endCursor", "")
        return notes

    def _process_notes(self, notes, filter_users, ps: ProjectStats):
        seen_disc: dict = {}
        for note in notes:
            if note.get("system"):
                continue
            author = (note.get("author") or {}).get("username", "unknown")
            disc_id = (note.get("discussion") or {}).get("id", "")
            resolvable = note.get("resolvable", False)

            if filter_users is None or author in filter_users:
                ps.comments[author] += 1

            if resolvable and disc_id and disc_id not in seen_disc:
                seen_disc[disc_id] = author
                if filter_users is None or author in filter_users:
                    ps.discussions_started[author] += 1

    def _collect(self, gql_url, full_path, gql_vars_base, max_mrs, filter_users) -> tuple[ProjectStats, list[str]]:
        ps = ProjectStats(full_path)
        errors = []
        cursor = None

        while ps.mr_count < max_mrs:
            variables = {**gql_vars_base, "fullPath": full_path, "after": cursor}
            try:
                data = self._gql(gql_url, MR_QUERY, variables)
            except Exception as e:
                errors.append(f"`{full_path}`: {e}")
                break

            project = data.get("project")
            if not project:
                errors.append(f"`{full_path}`: проект не найден или нет доступа")
                break

            mr_conn = project.get("mergeRequests", {})
            nodes = mr_conn.get("nodes", [])
            page_info = mr_conn.get("pageInfo", {})

            for mr in nodes:
                if ps.mr_count >= max_mrs:
                    break
                ps.mr_count += 1
                iid = mr["iid"]

                for approver in (mr.get("approvedBy") or {}).get("nodes", []):
                    username = approver.get("username", "unknown")
                    if filter_users is None or username in filter_users:
                        ps.approvals[username].add(iid)

                notes_conn = mr.get("notes", {})
                first_notes = notes_conn.get("nodes", [])
                notes_pi = notes_conn.get("pageInfo", {})
                try:
                    all_notes = self._fetch_all_notes(
                        gql_url, full_path, iid,
                        first_notes,
                        notes_pi.get("hasNextPage", False),
                        notes_pi.get("endCursor", ""),
                    )
                    self._process_notes(all_notes, filter_users, ps)
                except Exception as e:
                    errors.append(f"`{full_path}` MR!{iid} (notes): {e}")

            if not page_info.get("hasNextPage"):
                break
            cursor = page_info["endCursor"]

        return ps, errors

    # ------------------------------------------------------------------
    # Рендер отчётов
    # ------------------------------------------------------------------

    def _render_summary(self, all_users, project_stats: list[ProjectStats]) -> list[str]:
        """Сводная таблица: строки = пользователи, суммы по всем проектам."""
        users = _sort_users(all_users, project_stats)
        total_mrs = sum(ps.mr_count for ps in project_stats)
        rows = []
        for u in users:
            a = sum(ps.approvals_count(u) for ps in project_stats)
            c = sum(ps.comments_count(u) for ps in project_stats)
            d = sum(ps.discussions_count(u) for ps in project_stats)
            rows.append((f"`{u}`", a, c, d))

        # Итоговая строка
        rows.append((
            "**Итого**",
            sum(r[1] for r in rows),
            sum(r[2] for r in rows),
            sum(r[3] for r in rows),
        ))

        lines = [
            f"### 📊 Сводная таблица — {len(project_stats)} проект(ов), {total_mrs} MR",
            "",
        ]
        lines += _table(rows, ["Пользователь", "Аппрувов", "Комментариев", "Начато обсуждений"])
        return lines

    def _render_by_project(self, all_users, project_stats: list[ProjectStats]) -> list[str]:
        """Отдельная таблица на каждый проект: строки = пользователи."""
        lines = ["### 📁 Разбивка по проектам", ""]
        for ps in project_stats:
            users = _sort_users(all_users & ps.all_users() or all_users, [ps])
            rows = []
            for u in users:
                a = ps.approvals_count(u)
                c = ps.comments_count(u)
                d = ps.discussions_count(u)
                if a or c or d:
                    rows.append((f"`{u}`", a, c, d))
            short = ps.full_path.split("/")[-1]
            lines.append(f"#### `{ps.full_path}` — {ps.mr_count} MR")
            lines.append("")
            if rows:
                lines += _table(rows, ["Пользователь", "Аппрувов", "Комментариев", "Начато обсуждений"])
            else:
                lines.append("_Нет активности_")
            lines.append("")
        return lines

    def _render_by_user(self, all_users, project_stats: list[ProjectStats]) -> list[str]:
        """Отдельная таблица на каждого пользователя: строки = проекты."""
        users = _sort_users(all_users, project_stats)
        lines = ["### 👤 Разбивка по пользователям", ""]
        for u in users:
            rows = []
            for ps in project_stats:
                a = ps.approvals_count(u)
                c = ps.comments_count(u)
                d = ps.discussions_count(u)
                if a or c or d:
                    rows.append((f"`{ps.full_path}`", a, c, d))
            if not rows:
                continue
            # Итог по пользователю
            rows.append((
                "**Итого**",
                sum(r[1] for r in rows),
                sum(r[2] for r in rows),
                sum(r[3] for r in rows),
            ))
            lines.append(f"#### `{u}`")
            lines.append("")
            lines += _table(rows, ["Проект", "Аппрувов", "Комментариев", "Начато обсуждений"])
            lines.append("")
        return lines

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------

    def run(self, inputs: dict) -> str:
        gitlab_url = inputs.get("gitlab_url", self.config.get("gitlab_url", "https://gitlab.com"))
        gql_url = self._graphql_url(gitlab_url)

        # --- Debug ---
        if inputs.get("debug_connection"):
            lines = ["## 🔌 Проверка соединения", "", f"**URL:** `{gql_url}`", ""]
            try:
                data = self._gql(gql_url, WHOAMI_QUERY)
                user = data.get("currentUser") or {}
                if user:
                    lines += ["✅ **Успешно!**", "",
                              f"Авторизован как: **{user.get('name','?')}** (`{user.get('username','?')}`)"]
                else:
                    lines += ["⚠️ currentUser = null. Возможно нужен scope `read_user`."]
            except Exception as e:
                lines += [f"❌ **Ошибка:**\n\n```\n{e}\n```"]
            return "\n".join(lines)

        # --- Параметры ---
        project_ids  = self._parse_lines(inputs.get("project_ids", ""))
        team_members = self._parse_lines(inputs.get("team_members", ""))
        state        = (inputs.get("state") or "merged").strip()
        target_branch = (inputs.get("target_branch") or "").strip() or None
        date_from    = (inputs.get("date_from") or "").strip()
        date_to      = (inputs.get("date_to") or "").strip()
        max_mrs      = int(inputs.get("max_mrs_per_project") or 500)
        view         = (inputs.get("view") or "summary").strip()

        if not project_ids:
            return "❌ Укажите хотя бы один проект."

        filter_users = set(team_members) if team_members else None

        gql_vars_base = {
            "state": state,
            "targetBranches": [target_branch] if target_branch else None,
            "createdAfter":   f"{date_from}T00:00:00Z" if date_from else None,
            "createdBefore":  f"{date_to}T23:59:59Z"   if date_to   else None,
        }

        # --- Сбор данных ---
        all_project_stats: list[ProjectStats] = []
        all_errors: list[str] = []

        for pid in project_ids:
            ps, errs = self._collect(gql_url, pid, gql_vars_base, max_mrs, filter_users)
            all_project_stats.append(ps)
            all_errors.extend(errs)

        # Общий список пользователей
        if filter_users:
            all_users = set(filter_users)
        else:
            all_users = set()
            for ps in all_project_stats:
                all_users |= ps.all_users()

        # --- Шапка ---
        total_mrs = sum(ps.mr_count for ps in all_project_stats)
        lines = [
            "# 📊 GitLab MR Stats",
            "",
            f"**Проектов:** {len(project_ids)} | **MR:** {total_mrs} | **Статус:** {state}",
        ]
        if target_branch:
            lines.append(f"**Ветка:** `{target_branch}`")
        if date_from or date_to:
            lines.append(f"**Период:** {date_from or '∞'} → {date_to or '∞'}")
        if filter_users:
            lines.append(f"**Участников:** {len(filter_users)}")
        lines.append("")

        if all_errors:
            lines += ["### ⚠️ Ошибки", ""]
            for e in all_errors:
                lines.append(f"- {e}")
            lines.append("")

        if not all_users:
            lines.append("ℹ️ Активности не обнаружено.")
            return "\n".join(lines)

        # --- Отчёт по режиму ---
        # Сводная — всегда
        lines += self._render_summary(all_users, all_project_stats)
        lines.append("")

        if view in ("by_project", "full"):
            lines += self._render_by_project(all_users, all_project_stats)

        if view in ("by_user", "full"):
            lines += self._render_by_user(all_users, all_project_stats)

        lines += [
            "---",
            "_Аппрув уникален по MR в рамках проекта. "
            "Начатые обсуждения — resolvable thread-дискуссии, инициированные пользователем._",
        ]
        return "\n".join(lines)

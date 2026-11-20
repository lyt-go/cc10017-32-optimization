"""列表查询的统一写法：字段筛选、编号关键字、状态过滤与分页只保留这一份。

各业务模块的 list_entries 结构完全一致，只有"按哪个编号字段检索"不同；
原先十多个 service 各复制了一遍，这里收敛成唯一实现。
"""
from __future__ import annotations

from typing import Any

from app.store import store


def list_module_entries(
    module: str,
    keyword_field: str,
    *,
    filters: dict[str, str] | None = None,
    keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """按页面字段、编号关键字与状态过滤模块数据，并返回当前页与总数。"""
    rows = store.rows(module)
    for field, expected in (filters or {}).items():
        rows = [row for row in rows if expected.casefold() in str(row.get(field, "")).casefold()]
    if keyword:
        rows = [row for row in rows if keyword.casefold() in str(row.get(keyword_field, "")).casefold()]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    total = len(rows)
    start = (page - 1) * size
    return rows[start:start + size], total

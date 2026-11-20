"""导出共用逻辑：CSV 单元格转义与附件输出，各模块只保留这一份实现。

原先 flink_job / change_capture / backfill_stream / realtime_metrics / stream_lineage
各自复制了 csv_cell 与整段 CSV 拼装，这里收敛成唯一写法。
"""
from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from fastapi.responses import StreamingResponse


def csv_cell(value: Any) -> str:
    """转义单个 CSV 单元格，并中和以 = + - @ 开头的公式注入。"""
    text = str(value) if value is not None else ""
    if text and text[0] in "=+-@":
        text = "'" + text
    return '"' + text.replace('"', '""') + '"'


def csv_download(headers: list[str], rows: Iterable[Iterable[Any]], filename: str) -> StreamingResponse:
    """按给定表头与数据行输出 UTF-8 CSV 附件。"""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([csv_cell(value) for value in row])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


def csv_download_records(items: list[dict[str, Any]], filename: str) -> StreamingResponse:
    """按第一条记录的字段顺序输出记录型 CSV。"""
    headers = list(items[0].keys()) if items else ["id"]
    return csv_download(headers, ([item.get(key, "") for key in headers] for item in items), filename)

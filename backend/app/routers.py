import io
import os
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .models import RESOURCES

router = APIRouter(tags=["通用"])


def _search_filter(model, columns, keyword):
    if not keyword:
        return True
    cols = [getattr(model, col) for col, _ in columns]
    like = f"%{keyword}%"
    return or_(*[c.like(like) for c in cols])


@router.get("/meta/columns")
def get_meta():
    return {
        name: {
            "title": cfg["title"],
            "sheet": cfg["sheet"],
            "columns": cfg["columns"],
            "selects": cfg.get("selects", {}),
            "readonly": cfg.get("readonly", []),
            "readonly_hints": cfg.get("readonly_hints", {}),
            "hidden_in_table": cfg.get("hidden_in_table", []),
            "hidden_in_form": cfg.get("hidden_in_form", []),
            "date_fields": cfg.get("date_fields", []),
            "color_by": cfg.get("color_by", {}),
        }
        for name, cfg in RESOURCES.items()
    }


def _query_items(resource: str, keyword: str, db: Session):
    if resource not in RESOURCES:
        raise HTTPException(status_code=404, detail="未知资源")
    cfg = RESOURCES[resource]
    model = cfg["model"]
    q = db.query(model).filter(_search_filter(model, cfg["columns"], keyword))
    return cfg, q.order_by(model.id).all()


@router.get("/export/{resource}")
def export_items(
    resource: str,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    keyword: str = Query(None),
    db: Session = Depends(get_db),
):
    cfg, items = _query_items(resource, keyword, db)
    labels = [label for _, label in cfg["columns"]]
    data = []
    for it in items:
        data.append({label: (getattr(it, col) or "") for col, label in cfg["columns"]})
    df = pd.DataFrame(data, columns=labels)
    fname = f"{cfg['title']}_{pd.Timestamp.now():%Y%m%d_%H%M%S}"

    if format == "csv":
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        buf.seek(0)
        media = "text/csv; charset=utf-8"
        ext = "csv"
    else:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=cfg["sheet"])
        buf.seek(0)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"

    filename = f"{fname}.{ext}"
    ascii_name = fname.encode("ascii", "ignore").decode() or "export"
    quoted = ascii_name.replace('"', "%22")
    encoded = quote(filename.encode("utf-8"))
    return StreamingResponse(
        buf,
        media_type=media,
        headers={
            "Content-Disposition": f"attachment; filename=\"{quoted}.{ext}\"; filename*=UTF-8''{encoded}"
        },
    )


def _read_sheet(raw, sheet_name: str):
    try:
        df = pd.read_excel(io.BytesIO(raw), sheet_name=sheet_name, dtype=object)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取Excel失败: {e}")
    df = df.where(pd.notna(df), None)
    return df


@router.post("/import/{resource}")
async def import_items(
    resource: str,
    file: UploadFile = File(...),
    replace: bool = Query(True, description="true=清空后导入, false=追加"),
    db: Session = Depends(get_db),
):
    if resource not in RESOURCES:
        raise HTTPException(status_code=404, detail="未知资源")
    cfg = RESOURCES[resource]
    model = cfg["model"]
    sheet = cfg["sheet"]
    df = _read_sheet(await file.read(), sheet)
    if df.empty:
        raise HTTPException(status_code=400, detail="导入文件无数据")

    col_map = {label: col for col, label in cfg["columns"]}
    missing = [label for label in col_map if label not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Excel缺少列: {', '.join(missing)}（需要sheet「{sheet}」且表头一致）",
        )

    rows = []
    for _, r in df.iterrows():
        record = {}
        for label, col in col_map.items():
            v = r.get(label)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                record[col] = str(v) if not isinstance(v, str) else v
        rows.append(record)

    if replace:
        db.query(model).delete()
    db.bulk_insert_mappings(model, rows)
    db.commit()
    return {"ok": True, "imported": len(rows), "replace": replace}

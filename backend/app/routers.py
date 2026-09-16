import io
import os
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .models import RESOURCES, Batch, Device, IotCard

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
            "computed_columns": cfg.get("computed_columns", []),
        }
        for name, cfg in RESOURCES.items()
    }


def _query_items(resource: str, keyword: str, db: Session):
    if resource not in RESOURCES:
        raise HTTPException(status_code=404, detail="未知资源")
    cfg = RESOURCES[resource]
    model = cfg["model"]
    search_cols = [
        c for c in cfg["columns"] if c[0] not in cfg.get("computed_columns", [])
    ]
    q = db.query(model).filter(_search_filter(model, search_cols, keyword))
    return cfg, q.order_by(model.id).all()


@router.get("/export/{resource}")
def export_items(
    resource: str,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    keyword: str = Query(None),
    db: Session = Depends(get_db),
):
    cfg, items = _query_items(resource, keyword, db)
    cols = [c for c in cfg["columns"] if c[0] not in cfg.get("computed_columns", [])]
    labels = [label for _, label in cols]
    data = []
    for it in items:
        data.append({label: (getattr(it, col) or "") for col, label in cols})
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


# 导入模板中的示例值（帮助用户按正确格式填写）
_SAMPLE = {
    "入库时间": "2026-08-18",
    "出库时间": "2026-08-18",
    "设备类型": "CPE",
    "设备型号": "MA425W-716",
    "设备SN": "253900001",
    "SN": "253900001",
    "PN": "abc12345",
    "SSID": "WIFI-TEST",
    "ICCID1": "89860000000000000000",
    "ICCID2": "89860000000000000001",
    "客户": "自用",
    "门店": "示例门店",
    "门店地址": "示例地址",
    "出库历史": "示例",
    "设备状态": "空闲中",
    "卡1状态": "未激活",
    "卡2状态": "未激活",
    "iccid": "89860000000000000000",
    "运营商": "移动",
    "通讯类型": "4G",
    "设备sn": "253900001",
    "卡状态": "未激活",
    "客户名称": "示例客户",
    "联系人": "张三",
    "联系电话": "13800000000",
    "备注": "示例备注",
}


@router.get("/import/template/{resource}")
def import_template(resource: str):
    if resource not in RESOURCES:
        raise HTTPException(status_code=404, detail="未知资源")
    cfg = RESOURCES[resource]
    cols = [c for c in cfg["columns"] if c[0] not in cfg.get("computed_columns", [])]
    labels = [label for _, label in cols]
    sample = {label: _SAMPLE.get(label, "") for label in labels}
    df = pd.DataFrame([sample], columns=labels)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=cfg["sheet"])
    buf.seek(0)
    fname = f"{cfg['title']}导入模板"
    quoted = fname.encode("ascii", "ignore").decode() or "template"
    encoded = quote(f"{fname}.xlsx".encode("utf-8"))
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{quoted}.xlsx\"; filename*=UTF-8''{encoded}"
        },
    )


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

    col_map = {
        label: col
        for col, label in cfg["columns"]
        if col not in cfg.get("computed_columns", [])
    }
    matched = [label for label in col_map if label in df.columns]
    if not matched:
        raise HTTPException(
            status_code=400,
            detail=f"未识别到有效表头，请先下载导入模板（需sheet「{sheet}」且表头一致）",
        )

    rows = []
    for _, r in df.iterrows():
        record = {}
        for label in matched:
            col = col_map[label]
            v = r.get(label)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                record[col] = str(v) if not isinstance(v, str) else v
        rows.append(record)

    if replace:
        db.query(model).delete()
    db.bulk_insert_mappings(model, rows)
    db.commit()
    return {"ok": True, "imported": len(rows), "replace": replace}


@router.post("/batches/{batch_id}/import")
async def batch_import_items(
    batch_id: int,
    file: UploadFile = File(...),
    target: str = Query(..., description="目标台账: devices 或 edge_boxes"),
    db: Session = Depends(get_db),
):
    if target not in ("devices", "edge_boxes"):
        raise HTTPException(status_code=400, detail="target 必须为 devices 或 edge_boxes")
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    cfg = RESOURCES[target]
    model = cfg["model"]
    sheet = cfg["sheet"]
    raw = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(raw), sheet_name=sheet, dtype=object)
    except Exception:
        try:
            df = pd.read_excel(io.BytesIO(raw), sheet_name=0, dtype=object)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"读取Excel失败: {e}")
    df = df.where(pd.notna(df), None)
    if df.empty:
        raise HTTPException(status_code=400, detail="导入文件无数据")

    col_map = {label: col for col, label in cfg["columns"]}
    rows = []
    for _, r in df.iterrows():
        record = {}
        for label, col in col_map.items():
            if label in df.columns:
                v = r.get(label)
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    record[col] = str(v) if not isinstance(v, str) else v
        record["pn"] = batch.pn
        record["device_type"] = batch.device_type
        record["device_model"] = batch.device_model
        rows.append(record)

    if rows:
        db.bulk_insert_mappings(model, rows)
        db.commit()
    return {
        "ok": True,
        "imported": len(rows),
        "batch_pn": batch.pn,
        "target": target,
    }


@router.post("/iot_cards/sync-device-sn")
def sync_device_sn(db: Session = Depends(get_db)):
    """以设备台账为标准，反向同步物联网卡的设备SN字段"""
    devices = db.query(Device).all()
    iccid_to_sn = {}
    for d in devices:
        if d.iccid1:
            iccid_to_sn[d.iccid1] = d.device_sn
        if d.iccid2:
            iccid_to_sn[d.iccid2] = d.device_sn

    updated = 0
    for card in db.query(IotCard).all():
        dev_sn = iccid_to_sn.get(card.iccid)
        if dev_sn and card.device_sn != dev_sn:
            card.device_sn = dev_sn
            updated += 1
    db.commit()
    return {"ok": True, "updated": updated, "total_cards": db.query(IotCard).count()}
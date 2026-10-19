import io
import os
import re
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .models import RESOURCES, Batch, Device, EdgeBox, IotCard

router = APIRouter(tags=["通用"])


def _normalize_date(v):
    """将多种日期格式统一转换为 YYYY-MM-DD"""
    if v is None:
        return None
    if isinstance(v, (datetime,)):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    if not s:
        return None
    # YYYY-MM-DD 已是标准格式
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    # YYYYMMDD
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # YYYY.MM.DD 或 YYYY/MM/DD
    m = re.fullmatch(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s


def _search_filter(model, columns, keyword):
    if not keyword:
        return True
    cols = [getattr(model, col) for col, _ in columns]
    like = f"%{keyword}%"
    return or_(*[c.like(like) for c in cols])


def _sync_device_cards(obj, old_iccids, db: Session):
    """把设备当前 ICCID 同步到物联网卡台账：新卡绑定本设备SN，被替换的旧卡解绑"""
    new_set = {c for c in (obj.iccid1, obj.iccid2) if c}
    old_set = {c for c in old_iccids if c}
    for c in old_set - new_set:
        card = db.query(IotCard).filter(IotCard.iccid == c).first()
        if card:
            card.device_sn = None
    for c in new_set:
        card = db.query(IotCard).filter(IotCard.iccid == c).first()
        if card:
            card.device_sn = obj.device_sn


@router.post("/register")
def register_device(payload: dict, db: Session = Depends(get_db)):
    """边缘盒子自动注册接口：按 SN 合并进边缘盒子管理表。
    已登记则只刷新 ZT ID / IP地址 / 最后上报时间，其余字段保留；未登记则新建（空闲中）。"""
    sn = (payload.get("sn") or "").strip() if isinstance(payload, dict) else ""
    if not sn:
        raise HTTPException(status_code=422, detail="sn 不能为空")

    zt_id = (payload.get("zt_id") or "").strip() or None
    zt_addr = (payload.get("zt_addr") or "").strip() or None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    obj = db.query(EdgeBox).filter(EdgeBox.sn == sn).first()
    if obj:
        obj.zt_id = zt_id
        obj.zt_addr = zt_addr
        obj.last_seen = now
        db.commit()
        db.refresh(obj)
        return {"ok": True, "action": "updated", "target": "edge_boxes", "id": obj.id, "sn": sn}

    obj = EdgeBox(
        sn=sn,
        zt_id=zt_id,
        zt_addr=zt_addr,
        last_seen=now,
        device_status="空闲中",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"ok": True, "action": "created", "target": "edge_boxes", "id": obj.id, "sn": sn}


@router.post("/register/cpe")
def register_cpe(payload: dict, db: Session = Depends(get_db)):
    """CPE 设备自动注册接口：按设备SN合并进设备台账。

    上报字段 zt_id/zt_addr/ssid/lte1/lte2/last_seen 非空则刷新，空值保留原值；
    入库时间/PN/客户/门店/状态等手动字段一律保留；未登记则新建（空闲中）。"""
    if not isinstance(payload, dict):
        payload = {}
    sn = (payload.get("sn") or "").strip()
    if not sn:
        raise HTTPException(status_code=422, detail="sn 不能为空")

    zt_id = (payload.get("zt_id") or "").strip() or None
    zt_addr = (payload.get("zt_addr") or "").strip() or None
    ssid = (payload.get("ssid") or "").strip() or None
    lte1 = (payload.get("lte1") or "").strip() or None
    lte2 = (payload.get("lte2") or "").strip() or None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = db.query(Device).filter(Device.device_sn == sn).all()
    if rows:
        for obj in rows:
            old_iccids = (obj.iccid1, obj.iccid2)
            obj.zt_id = zt_id
            obj.zt_addr = zt_addr
            obj.last_seen = now
            if ssid:
                obj.ssid = ssid
            if lte1:
                obj.iccid1 = lte1
            if lte2:
                obj.iccid2 = lte2
            _sync_device_cards(obj, old_iccids, db)
        db.commit()
        return {"ok": True, "action": "updated", "target": "devices", "sn": sn, "updated": len(rows)}

    obj = Device(
        device_sn=sn,
        zt_id=zt_id,
        zt_addr=zt_addr,
        ssid=ssid,
        iccid1=lte1,
        iccid2=lte2,
        last_seen=now,
        device_status="空闲中",
    )
    db.add(obj)
    _sync_device_cards(obj, (), db)
    db.commit()
    db.refresh(obj)
    return {"ok": True, "action": "created", "target": "devices", "id": obj.id, "sn": sn}


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
    "ZT ID": "d0e1a198f6",
    "IP地址": "10.27.1.11",
    "最后上报时间": "2026-10-08 12:00:00",
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
    "联系手机号": "13800000000",
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
    date_cols = set(cfg.get("date_fields", []))
    for _, r in df.iterrows():
        record = {}
        for label in matched:
            col = col_map[label]
            v = r.get(label)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                if col in date_cols:
                    record[col] = _normalize_date(v)
                else:
                    record[col] = str(v) if not isinstance(v, str) else v
        rows.append(record)

    # 边缘盒子管理：与 /api/register 的按 SN 合并语义一致 —— 文件内重复的 SN 去重，
    # 追加导入（replace=false）时跳过库中已存在的 SN；清空导入（replace=true）不受库内影响
    if resource == "edge_boxes":
        existing = set() if replace else {s for s, in db.query(EdgeBox.sn).all()}
        seen, uniq = set(), []
        for r in rows:
            sn = (r.get("sn") or "").strip()
            if not sn or sn in seen or sn in existing:
                continue
            seen.add(sn)
            uniq.append(r)
        rows = uniq

    if replace:
        db.query(model).delete()
    if rows:
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
    date_cols = set(cfg.get("date_fields", []))
    rows = []
    for _, r in df.iterrows():
        record = {}
        for label, col in col_map.items():
            if label in df.columns:
                v = r.get(label)
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    if col in date_cols:
                        record[col] = _normalize_date(v)
                    else:
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
import random
import string

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .database import get_db
from .models import RESOURCES, Asset, Batch, Customer, Device, EdgeBox, IotCard


def _gen_pn(db: Session) -> str:
    while True:
        pn = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        if not db.query(Batch).filter(Batch.pn == pn).first():
            return pn


# ---------- 设备模块业务钩子 ----------
# ICCID 必须引用卡台账中的卡，卡状态自动从卡台账读取；
# 客户必须引用客户管理；PN 引用批次管理，按 PN 自动带出设备类型/型号。


def _resolve_pn_fields(payload: dict, db: Session, current_id=None):
    pn = (payload.get("pn") or "").strip()
    if pn:
        batch = db.query(Batch).filter(Batch.pn == pn).first()
        if not batch:
            raise HTTPException(
                status_code=422,
                detail=f"PN「{pn}」未在批次管理中登记，请先在「批次管理」创建该批次",
            )
        payload["device_type"] = batch.device_type
        payload["device_model"] = batch.device_model
    else:
        payload.pop("device_type", None)
        payload.pop("device_model", None)
    return payload


def _devices_before_save(payload: dict, db: Session, current_id=None):
    device_sn = (payload.get("device_sn") or "").strip() or None

    # 获取旧的ICCID（编辑时），用于处理换卡/解绑
    old_iccid1, old_iccid2 = None, None
    if current_id:
        old_dev = db.query(Device).filter(Device.id == current_id).first()
        if old_dev:
            old_iccid1 = old_dev.iccid1
            old_iccid2 = old_dev.iccid2

    for key, status_key in (("iccid1", "card1_status"), ("iccid2", "card2_status")):
        v = (payload.get(key) or "").strip()
        if v:
            card = db.query(IotCard).filter(IotCard.iccid == v).first()
            if not card:
                raise HTTPException(
                    status_code=422,
                    detail=f"{key} = {v} 未在物联网卡台账中登记，请先在「物联网卡台账」添加该卡后再引用",
                )
            payload[key] = card.iccid
            payload[status_key] = card.card_status
        else:
            payload[key] = None
            payload[status_key] = None

    cust = (payload.get("customer") or "").strip()
    if cust and not db.query(Customer).filter(Customer.name == cust).first():
        raise HTTPException(
            status_code=422,
            detail=f"客户「{cust}」未在客户管理中登记，请先在「客户管理」添加该客户后再引用",
        )

    result = _resolve_pn_fields(payload, db, current_id)

    # ---------- 自动同步：将设备SN写入对应物联网卡 ----------
    new_iccid1 = result.get("iccid1")
    new_iccid2 = result.get("iccid2")
    new_set = {c for c in (new_iccid1, new_iccid2) if c}
    old_set = {c for c in (old_iccid1, old_iccid2) if c}

    # 旧卡中不再被本设备引用的 → 清空 device_sn
    for old_iccid in old_set - new_set:
        card = db.query(IotCard).filter(IotCard.iccid == old_iccid).first()
        if card:
            card.device_sn = None

    # 新卡（含保留卡）→ 写入 device_sn
    for iccid in new_set:
        card = db.query(IotCard).filter(IotCard.iccid == iccid).first()
        if card:
            card.device_sn = device_sn

    return result


def _devices_enrich(items, db: Session):
    if not items:
        return
    iccids = set()
    for it in items:
        for key in ("iccid1", "iccid2"):
            v = getattr(it, key)
            if v:
                iccids.add(v)
    if not iccids:
        return
    cards = db.query(IotCard).filter(IotCard.iccid.in_(iccids)).all()
    status = {c.iccid: c.card_status for c in cards}
    for it in items:
        it.card1_status = status.get(it.iccid1)
        it.card2_status = status.get(it.iccid2)


def _devices_after_delete(items, db: Session):
    """设备删除后，清理其已绑定物联网卡的 device_sn"""
    for it in items:
        for iccid in (it.iccid1, it.iccid2):
            if iccid:
                card = db.query(IotCard).filter(IotCard.iccid == iccid).first()
                if card:
                    card.device_sn = None


def _edge_boxes_before_save(payload: dict, db: Session, current_id=None):
    cust = (payload.get("customer") or "").strip()
    if cust and not db.query(Customer).filter(Customer.name == cust).first():
        raise HTTPException(
            status_code=422,
            detail=f"客户「{cust}」未在客户管理中登记，请先在「客户管理」添加该客户后再引用",
        )
    return _resolve_pn_fields(payload, db, current_id)


def _iot_cards_before_save(payload: dict, db: Session, current_id=None):
    """物联网卡台账的 device_sn 由设备台账自动同步，禁止手动写入"""
    payload.pop("device_sn", None)
    return payload


def _batches_before_save(payload: dict, db: Session, current_id=None):
    payload["pn"] = _gen_pn(db)

    model_v = (payload.get("device_model") or "").strip()
    if model_v:
        asset = db.query(Asset).filter(Asset.asset_model == model_v).first()
        if not asset:
            raise HTTPException(
                status_code=422,
                detail=f"设备型号「{model_v}」未在型号管理中登记，请先在「型号管理」添加该型号后再引用",
            )
        payload["device_type"] = asset.asset_type
    else:
        payload["device_type"] = None
    return payload


def _batches_enrich(items, db: Session):
    if not items:
        return
    pns = [getattr(it, "pn") for it in items if getattr(it, "pn")]
    dev_counts = {}
    eb_counts = {}
    if pns:
        for pn, c in (
            db.query(Device.pn, func.count()).filter(Device.pn.in_(pns)).group_by(Device.pn).all()
        ):
            dev_counts[pn] = c
        for pn, c in (
            db.query(EdgeBox.pn, func.count()).filter(EdgeBox.pn.in_(pns)).group_by(EdgeBox.pn).all()
        ):
            eb_counts[pn] = c
    for it in items:
        pn = getattr(it, "pn")
        it.count = (dev_counts.get(pn, 0) + eb_counts.get(pn, 0)) or 0


HANDLERS = {
    "devices": {
        "before_save": _devices_before_save,
        "enrich": _devices_enrich,
        "after_delete": _devices_after_delete,
    },
    "iot_cards": {"before_save": _iot_cards_before_save},
    "edge_boxes": {"before_save": _edge_boxes_before_save},
    "batches": {"before_save": _batches_before_save, "enrich": _batches_enrich},
}


def build_router(resource: str):
    cfg = RESOURCES[resource]
    model = cfg["model"]
    handlers = HANDLERS.get(resource, {})
    computed_columns = cfg.get("computed_columns", [])

    router = APIRouter(prefix=f"/{resource}", tags=[cfg["title"]])

    def _search_filter(keyword: str = None):
        if not keyword:
            return True
        cols = [
            getattr(model, col)
            for col, _ in cfg["columns"]
            if col not in computed_columns
        ]
        like = f"%{keyword}%"
        return or_(*[c.like(like) for c in cols])

    def _customer_filter(customer: str = None):
        if not hasattr(model, "customer"):
            return None
        if not customer:
            return None
        if customer == "__none__":
            return or_(model.customer.is_(None), model.customer == "")
        return model.customer == customer

    def _to_dict(obj):
        return {col: getattr(obj, col) for col, _ in cfg["columns"]}

    def _apply_before_save(payload: dict, db: Session, current_id=None):
        if "before_save" in handlers:
            return handlers["before_save"](dict(payload), db, current_id)
        return payload

    def _apply_enrich(items, db: Session):
        if "enrich" in handlers:
            handlers["enrich"](items, db)

    def _apply_after_delete(items, db: Session):
        if "after_delete" in handlers:
            handlers["after_delete"](items, db)

    @router.get("")
    def list_items(
        keyword: str = Query(None, description="关键词，模糊搜索所有列"),
        customer: str = Query(None, description="按客户筛选，__none__ 表示未分配"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=500),
        db: Session = Depends(get_db),
    ):
        q = db.query(model).filter(_search_filter(keyword))
        cf = _customer_filter(customer)
        if cf is not None:
            q = q.filter(cf)
        total = q.count()
        items = (
            q.order_by(model.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        _apply_enrich(items, db)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [{"id": it.id, **_to_dict(it)} for it in items],
        }

    @router.get("/all")
    def list_all(keyword: str = Query(None), db: Session = Depends(get_db)):
        items = db.query(model).filter(_search_filter(keyword)).order_by(model.id).all()
        _apply_enrich(items, db)
        return {"total": len(items), "items": [{"id": it.id, **_to_dict(it)} for it in items]}

    @router.post("")
    def create_item(payload: dict, db: Session = Depends(get_db)):
        payload = _apply_before_save(payload, db)
        clean = {k: (v if v is not None else None) for k, v in payload.items() if k != "id"}
        obj = model(**clean)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        _apply_enrich([obj], db)
        return {"id": obj.id, **_to_dict(obj)}

    @router.put("/{item_id}")
    def update_item(item_id: int, payload: dict, db: Session = Depends(get_db)):
        obj = db.query(model).filter(model.id == item_id).first()
        if not obj:
            raise HTTPException(status_code=404, detail="记录不存在")
        payload = _apply_before_save(payload, db, current_id=item_id)
        for k, v in payload.items():
            if k != "id" and hasattr(obj, k):
                setattr(obj, k, v if v is not None else None)
        db.commit()
        db.refresh(obj)
        _apply_enrich([obj], db)
        return {"id": obj.id, **_to_dict(obj)}

    @router.delete("/{item_id}")
    def delete_item(item_id: int, db: Session = Depends(get_db)):
        obj = db.query(model).filter(model.id == item_id).first()
        if not obj:
            raise HTTPException(status_code=404, detail="记录不存在")
        _apply_after_delete([obj], db)
        db.delete(obj)
        db.commit()
        return {"ok": True}

    @router.delete("")
    def delete_items(ids: str = Query(...), db: Session = Depends(get_db)):
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=422, detail="ids 格式错误")
        if not id_list:
            raise HTTPException(status_code=422, detail="ids 不能为空")
        objs = db.query(model).filter(model.id.in_(id_list)).all()
        _apply_after_delete(objs, db)
        deleted = db.query(model).filter(model.id.in_(id_list)).delete(synchronize_session=False)
        db.commit()
        return {"ok": True, "deleted": deleted}

    return router
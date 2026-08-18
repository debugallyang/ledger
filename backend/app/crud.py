from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .models import RESOURCES, IotCard, Customer, Asset

# ---------- 设备模块业务钩子 ----------
# ICCID 必须引用卡台账中的卡，卡状态自动从卡台账读取；
# 客户必须引用客户管理；设备型号引用资产管理并按型号自动带出设备类型。


def _devices_before_save(payload: dict, db: Session):
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

    model = (payload.get("device_model") or "").strip()
    if model:
        asset = db.query(Asset).filter(Asset.asset_model == model).first()
        if not asset:
            raise HTTPException(
                status_code=422,
                detail=f"设备型号「{model}」未在资产管理中登记，请先在「资产管理」添加该型号后再引用",
            )
        payload["device_type"] = asset.asset_type
    else:
        payload["device_type"] = None
    return payload


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


def _edge_boxes_before_save(payload: dict, db: Session):
    cust = (payload.get("customer") or "").strip()
    if cust and not db.query(Customer).filter(Customer.name == cust).first():
        raise HTTPException(
            status_code=422,
            detail=f"客户「{cust}」未在客户管理中登记，请先在「客户管理」添加该客户后再引用",
        )
    return payload


HANDLERS = {
    "devices": {"before_save": _devices_before_save, "enrich": _devices_enrich},
    "edge_boxes": {"before_save": _edge_boxes_before_save},
}


def build_router(resource: str):
    cfg = RESOURCES[resource]
    model = cfg["model"]
    handlers = HANDLERS.get(resource, {})

    router = APIRouter(prefix=f"/{resource}", tags=[cfg["title"]])

    def _search_filter(keyword: str = None):
        if not keyword:
            return True
        cols = [getattr(model, col) for col, _ in cfg["columns"]]
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

    def _apply_before_save(payload: dict, db: Session):
        if "before_save" in handlers:
            return handlers["before_save"](dict(payload), db)
        return payload

    def _apply_enrich(items, db: Session):
        if "enrich" in handlers:
            handlers["enrich"](items, db)

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
        payload = _apply_before_save(payload, db)
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
        deleted = db.query(model).filter(model.id.in_(id_list)).delete(synchronize_session=False)
        db.commit()
        return {"ok": True, "deleted": deleted}

    return router

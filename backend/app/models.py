from sqlalchemy import Column, Integer, Text

from .database import Base


def text_column():
    return Column(Text, nullable=True, default=None)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    inbound_time = text_column()  # 入库时间
    device_type = text_column()   # 设备类型（引用资产管理，按型号自动带出）
    device_model = text_column()  # 设备型号（引用资产管理）
    device_sn = text_column()     # 设备SN
    ssid = text_column()          # SSID
    iccid1 = text_column()        # ICCID1（引用物联网卡台账）
    iccid2 = text_column()        # ICCID2（引用物联网卡台账）
    customer = text_column()      # 客户（引用客户管理）
    store = text_column()         # 门店（手动输入）
    store_address = text_column() # 门店地址
    city = text_column()          # 城市
    outbound_time = text_column() # 出库时间（日期）
    outbound_history = text_column()  # 出库历史
    device_status = text_column() # 设备状态（使用中/空闲中）
    card1_status = text_column()  # 卡1状态（自动引用卡台账，仅导出可见）
    card2_status = text_column()  # 卡2状态（自动引用卡台账，仅导出可见）


class IotCard(Base):
    __tablename__ = "iot_cards"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    inbound_time = text_column()  # 入库时间
    iccid = text_column()         # iccid
    operator = text_column()      # 运营商
    comm_type = text_column()     # 通讯类型
    device_sn = text_column()     # 设备sn
    card_status = text_column()   # 卡状态（激活/未激活/停用）


class EdgeBox(Base):
    __tablename__ = "edge_boxes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    inbound_time = text_column()  # 入库时间
    outbound_time = text_column()  # 出库时间（日期）
    sn = text_column()            # SN
    customer = text_column()      # 归属客户（引用客户管理）
    store = text_column()         # 归属门店（手动输入）
    store_address = text_column() # 门店地址
    city = text_column()          # 所在城市
    device_status = text_column() # 设备状态


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = text_column()      # 客户名称
    contact = text_column()   # 联系人
    phone = text_column()     # 联系电话
    remark = text_column()    # 备注


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    asset_type = text_column()   # 设备类型
    asset_model = text_column()  # 设备型号
    remark = text_column()       # 备注


# 每个资源对应的表和列配置
RESOURCES = {
    "devices": {
        "title": "设备台账",
        "sheet": "设备",
        "model": Device,
        "columns": [
            ("inbound_time", "入库时间"),
            ("device_type", "设备类型"),
            ("device_model", "设备型号"),
            ("device_sn", "设备SN"),
            ("ssid", "SSID"),
            ("iccid1", "ICCID1"),
            ("iccid2", "ICCID2"),
            ("customer", "客户"),
            ("store", "门店"),
            ("store_address", "门店地址"),
            ("outbound_time", "出库时间"),
            ("outbound_history", "出库历史"),
            ("device_status", "设备状态"),
            ("card1_status", "卡1状态"),
            ("card2_status", "卡2状态"),
        ],
        "selects": {
            "device_status": ["使用中", "空闲中", "损坏"],
            "device_model": {
                "from": "assets", "value": "asset_model",
                "linked": {"target": "device_type", "source": "asset_type"},
            },
            "customer": {"from": "customers", "value": "name"},
            "iccid1": {"from": "iot_cards", "value": "iccid"},
            "iccid2": {"from": "iot_cards", "value": "iccid"},
        },
        "readonly": ["device_type"],
        "readonly_hints": {"device_type": "从资产管理引用"},
        "hidden_in_table": ["card1_status", "card2_status"],
        "hidden_in_form": ["card1_status", "card2_status"],
        "date_fields": ["outbound_time"],
        "color_by": {"iccid1": "card1_status", "iccid2": "card2_status"},
    },
    "iot_cards": {
        "title": "物联网卡台账",
        "sheet": "物联网卡",
        "model": IotCard,
        "columns": [
            ("inbound_time", "入库时间"),
            ("iccid", "iccid"),
            ("operator", "运营商"),
            ("comm_type", "通讯类型"),
            ("device_sn", "设备sn"),
            ("card_status", "卡状态"),
        ],
        "selects": {"card_status": ["激活", "未激活", "停用"]},
        "readonly": [],
        "readonly_hints": {},
        "hidden_in_table": [],
        "hidden_in_form": [],
        "date_fields": [],
        "color_by": {},
    },
    "edge_boxes": {
        "title": "边缘盒子台账",
        "sheet": "边缘盒子",
        "model": EdgeBox,
        "columns": [
            ("inbound_time", "入库时间"),
            ("outbound_time", "出库时间"),
            ("sn", "SN"),
            ("customer", "归属客户"),
            ("store", "归属门店"),
            ("store_address", "门店地址"),
            ("device_status", "设备状态"),
        ],
        "selects": {
            "customer": {"from": "customers", "value": "name"},
            "device_status": ["使用中", "空闲中", "损坏"],
        },
        "readonly": [],
        "readonly_hints": {},
        "hidden_in_table": [],
        "hidden_in_form": [],
        "date_fields": ["outbound_time"],
        "color_by": {},
    },
    "customers": {
        "title": "客户管理",
        "sheet": "客户",
        "model": Customer,
        "columns": [
            ("name", "客户名称"),
            ("contact", "联系人"),
            ("phone", "联系电话"),
            ("remark", "备注"),
        ],
        "selects": {},
        "readonly": [],
        "readonly_hints": {},
        "hidden_in_table": [],
        "hidden_in_form": [],
        "date_fields": [],
        "color_by": {},
    },
    "assets": {
        "title": "资产管理",
        "sheet": "资产",
        "model": Asset,
        "columns": [
            ("asset_type", "设备类型"),
            ("asset_model", "设备型号"),
            ("remark", "备注"),
        ],
        "selects": {},
        "readonly": [],
        "readonly_hints": {},
        "hidden_in_table": [],
        "hidden_in_form": [],
        "date_fields": [],
        "color_by": {},
    },
}

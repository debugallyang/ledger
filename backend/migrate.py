"""数据库迁移：设备表 destination(去向) -> customer(客户) + store(门店)；
设备状态统一为 使用中/空闲中。幂等，可重复执行。"""
import sqlite3
import sys

DB = "/opt/ledger/data/ledger.db"


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(devices)").fetchall()]
    print("迁移前 devices 列:", cols)

    if "destination" in cols:
        cur.execute("ALTER TABLE devices ADD COLUMN customer TEXT")
        cur.execute("ALTER TABLE devices ADD COLUMN store TEXT")

        rows = cur.execute(
            "SELECT id, destination FROM devices WHERE destination IS NOT NULL AND trim(destination) != ''"
        ).fetchall()
        for rid, dest in rows:
            dest = str(dest).strip()
            if " - " in dest:
                customer, store = dest.split(" - ", 1)
            elif " -" in dest:
                customer, store = dest.split(" -", 1)
            else:
                customer, store = dest, ""
            cur.execute(
                "UPDATE devices SET customer=?, store=? WHERE id=?",
                (customer.strip(), store.strip(), rid),
            )

        # 设备状态映射：有客户=>使用中，否则空闲中；短路损坏归为空闲中
        cur.execute("UPDATE devices SET device_status='使用中' WHERE device_status IS NULL OR device_status=''")
        cur.execute("UPDATE devices SET device_status='空闲中' WHERE customer IS NULL OR trim(customer)=''")
        cur.execute("UPDATE devices SET device_status='空闲中' WHERE device_status='短路损坏'")

        cur.execute("ALTER TABLE devices DROP COLUMN destination")
        conn.commit()
        print("迁移完成：destination -> customer/store，设备状态映射完成")

    # 物联网卡卡状态统一枚举校验（仅提示，不做强改）
    bad = cur.execute(
        "SELECT DISTINCT card_status FROM iot_cards WHERE card_status IS NOT NULL AND card_status NOT IN ('激活','未激活','停用')"
    ).fetchall()
    if bad:
        print("注意：物联网卡存在非枚举状态值:", [b[0] for b in bad])

    # 设备卡状态改为由卡台账实时引用，清空存量值
    cur.execute("UPDATE devices SET card1_status=NULL, card2_status=NULL")
    conn.commit()

    cols = [r[1] for r in cur.execute("PRAGMA table_info(devices)").fetchall()]
    print("迁移后 devices 列:", cols)
    print("设备条数:", cur.execute("SELECT count(*) FROM devices").fetchone()[0])
    print("卡条数:", cur.execute("SELECT count(*) FROM iot_cards").fetchone()[0])
    print("设备状态分布:", cur.execute(
        "SELECT device_status, count(*) FROM devices GROUP BY device_status"
    ).fetchall())
    print("客户分布(有值):", cur.execute(
        "SELECT customer, count(*) FROM devices WHERE customer IS NOT NULL AND trim(customer)!='' GROUP BY customer"
    ).fetchall())
    conn.close()
    print("OK")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        DB = sys.argv[1]
    main()

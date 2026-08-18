"""迁移 v4：边缘盒子设备状态统一为 使用中/空闲中/损坏 枚举。
启用->使用中，未启用->空闲中。幂等。"""
import sqlite3

DB = "/opt/ledger/data/ledger.db"


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    before = c.execute("SELECT device_status, COUNT(*) FROM edge_boxes GROUP BY device_status").fetchall()
    print("迁移前:", before)
    c.execute("UPDATE edge_boxes SET device_status='使用中' WHERE device_status='启用'")
    c.execute("UPDATE edge_boxes SET device_status='空闲中' WHERE device_status='未启用'")
    conn.commit()
    after = c.execute("SELECT device_status, COUNT(*) FROM edge_boxes GROUP BY device_status").fetchall()
    print("迁移后:", after)
    bad = c.execute(
        "SELECT device_status, COUNT(*) FROM edge_boxes "
        "WHERE device_status IS NULL OR device_status NOT IN ('使用中','空闲中','损坏') GROUP BY device_status"
    ).fetchall()
    if bad:
        print("注意仍存在非枚举值:", bad)
    conn.close()
    print("OK")


if __name__ == "__main__":
    main()
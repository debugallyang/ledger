"""迁移 v3：保留客户名单 247FITNESS/加减健身/沙县/自用/量时光；
其它客户设备改为 自用，原客户值移动到门店列；客户管理表删除非保留客户。幂等。"""
import sqlite3

DB = "/opt/ledger/data/ledger.db"
KEEP = ("247FITNESS", "加减健身", "沙县", "自用", "量时光")


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    rows = c.execute(
        "SELECT id, customer FROM devices "
        "WHERE customer IS NOT NULL AND trim(customer) != '' "
        "AND customer NOT IN (?, ?, ?, ?, ?)",
        KEEP,
    ).fetchall()
    print("待转换设备:", rows)
    for rid, cust in rows:
        c.execute(
            "UPDATE devices SET customer='自用', store=? WHERE id=?",
            (cust, rid),
        )

    deleted = c.execute(
        "DELETE FROM customers WHERE name NOT IN (?, ?, ?, ?, ?)", KEEP
    ).rowcount
    conn.commit()

    print("删除客户管理记录:", deleted)
    print("customers 剩余:", [r[0] for r in c.execute("SELECT name FROM customers ORDER BY id")])
    print("devices 客户分布:", c.execute("SELECT customer, COUNT(*) FROM devices GROUP BY customer").fetchall())
    print("示例(自用+原客户在门店):", c.execute(
        "SELECT id, customer, store FROM devices WHERE customer='自用' AND store != '' ORDER BY id").fetchall())
    conn.close()
    print("OK")


if __name__ == "__main__":
    main()
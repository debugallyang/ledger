"""迁移 v2：新增 customers/assets 表并填充引用数据；devices 加 store_address/city 列。
幂等，可重复执行。"""
import sqlite3
import sys

DB = "/opt/ledger/data/ledger.db"


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 1) 建 customers 表并填充
    cur.execute(
        """CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, contact TEXT, phone TEXT, remark TEXT)"""
    )
    names = set()
    for t in ("devices", "edge_boxes"):
        for (v,) in cur.execute(
            f"SELECT customer FROM {t} WHERE customer IS NOT NULL AND trim(customer) != ''"
        ).fetchall():
            names.add(str(v).strip())
    existing = {r[0] for r in cur.execute("SELECT name FROM customers").fetchall()}
    added_c = 0
    for n in sorted(names):
        if n not in existing:
            cur.execute("INSERT INTO customers (name) VALUES (?)", (n,))
            added_c += 1
    print(f"客户表: 新增 {added_c} 条（共 {len(names)} 个去重客户）")

    # 2) 建 assets 表并填充（设备类型+设备型号 去重）
    cur.execute(
        """CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT, asset_model TEXT, remark TEXT)"""
    )
    pairs = set()
    for (t, m) in cur.execute(
        "SELECT device_type, device_model FROM devices WHERE device_model IS NOT NULL AND trim(device_model) != ''"
    ).fetchall():
        pairs.add((str(t).strip() if t else "", str(m).strip()))
    existing_pairs = {
        (r[0] or "", r[1]) for r in cur.execute("SELECT asset_type, asset_model FROM assets").fetchall()
    }
    added_a = 0
    for t, m in sorted(pairs):
        if (t, m) not in existing_pairs:
            cur.execute("INSERT INTO assets (asset_type, asset_model) VALUES (?, ?)", (t, m))
            added_a += 1
    print(f"资产表: 新增 {added_a} 条（共 {len(pairs)} 个型号）")

    # 3) devices 加 store_address / city 列
    cols = [r[1] for r in cur.execute("PRAGMA table_info(devices)").fetchall()]
    if "store_address" not in cols:
        cur.execute("ALTER TABLE devices ADD COLUMN store_address TEXT")
    if "city" not in cols:
        cur.execute("ALTER TABLE devices ADD COLUMN city TEXT")

    conn.commit()
    print("devices 列:", [r[1] for r in cur.execute("PRAGMA table_info(devices)").fetchall()])
    print("客户列表:", [r[0] for r in cur.execute("SELECT name FROM customers ORDER BY id").fetchall()])
    print("资产列表:", cur.execute("SELECT asset_type, asset_model FROM assets ORDER BY id").fetchall())
    conn.close()
    print("OK")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        DB = sys.argv[1]
    main()
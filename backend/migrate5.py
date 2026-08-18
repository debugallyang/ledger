"""迁移 v5：统一 devices / edge_boxes 出库时间格式为 YYYY-MM-DD。
支持：2025年11月3日 / 2026-01-08 00:00:00 / 20260416 等旧格式。幂等。"""
import re
import sqlite3

DB = "/opt/ledger/data/ledger.db"


def normalize(v):
    if not v:
        return v
    s = str(v).strip()
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$", s)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$", s)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return s


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    for t in ("devices", "edge_boxes"):
        rows = c.execute(
            f"SELECT id, outbound_time FROM {t} "
            f"WHERE outbound_time IS NOT NULL AND trim(outbound_time) != ''"
        ).fetchall()
        changed = 0
        for rid, v in rows:
            nv = normalize(v)
            if nv != str(v).strip():
                c.execute(f"UPDATE {t} SET outbound_time=? WHERE id=?", (nv, rid))
                changed += 1
        print(f"{t}: 共 {len(rows)} 条有出库时间，格式修正 {changed} 条")
    conn.commit()
    for t in ("devices", "edge_boxes"):
        print(f"{t} 修正后分布:")
        for r in c.execute(f"SELECT outbound_time, COUNT(*) FROM {t} GROUP BY outbound_time"):
            print("  ", r)
    conn.close()
    print("OK")


if __name__ == "__main__":
    main()
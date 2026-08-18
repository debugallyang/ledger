import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from app.database import SessionLocal, Base, engine
from app.models import RESOURCES

SRC = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None


def import_file(path: str, resource: str):
    cfg = RESOURCES[resource]
    df = pd.read_excel(path, sheet_name=cfg["sheet"], dtype=object)
    df = df.where(pd.notna(df), None)
    col_map = {label: col for col, label in cfg["columns"]}
    missing = [label for label in col_map if label not in df.columns]
    if missing:
        print(f"[{resource}] 缺少列: {missing}")
        return 0
    rows = []
    for _, r in df.iterrows():
        record = {}
        for label, col in col_map.items():
            v = r.get(label)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                record[col] = str(v) if not isinstance(v, str) else v
        rows.append(record)
    db = SessionLocal()
    try:
        db.query(cfg["model"]).delete()
        db.bulk_insert_mappings(cfg["model"], rows)
        db.commit()
    finally:
        db.close()
    print(f"[{resource}] 导入 {len(rows)} 条")
    return len(rows)


def main():
    Base.metadata.create_all(bind=engine)
    path = SRC or input("请输入台账Excel文件路径: ").strip()
    if not os.path.exists(path):
        print(f"文件不存在: {path}")
        sys.exit(1)
    for resource in RESOURCES:
        import_file(path, resource)
    print("导入完成")


if __name__ == "__main__":
    main()

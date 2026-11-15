#!/usr/bin/env python3
"""批量校验与首个失败定位验收探针。

契约：
  from schema.batch import check_many
  res = check_many(schema, [doc1, doc2])
  res.results  [{index, ok, error_path}]（通过时 error_path 为 None）
  res.failed   未通过的 index 列表
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
FAIL = 0


def probe(code, desc, fn):
    global FAIL
    try:
        fn()
        print(f"[PASS] {code} {desc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {code} {desc}\n        {type(exc).__name__}: {exc}")
        FAIL += 1


def main():
    try:
        from schema.batch import check_many  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] P0 导入 schema.batch 失败：{type(exc).__name__}: {exc}")
        print("-" * 60)
        print("探针汇总：0/4 通过")
        return 1

    import schema
    S = schema.Schema({"name": str, "age": int})

    def p1():
        res = check_many(S, [{"name": "x", "age": 3}])
        assert res.results[0]["ok"] is True and res.failed == [], res.results

    def p2():
        res = check_many(S, [{"name": "x", "age": "old"}])
        assert res.failed == [0], res.failed

    def p3():
        res = check_many(S, [{"name": 1, "age": 3}])
        path = res.results[0]["error_path"]
        assert "name" in str(path), path

    def p4():
        res = check_many(S, [{"name": "a", "age": 1}, {"age": 2}])
        assert res.failed == [1] and res.results[1]["ok"] is False, res.results

    probe("P1", "合法文档", p1)
    probe("P2", "失败下标", p2)
    probe("P3", "首个失败字段路径", p3)
    probe("P4", "多文档独立判定", p4)

    print("-" * 60)
    print(f"探针汇总：{4 - FAIL}/4 通过")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

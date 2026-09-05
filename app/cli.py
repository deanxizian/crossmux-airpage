from __future__ import annotations

import argparse
import json
import sys

from app.config import Settings
from app.service import AirPageService, error_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render and optionally push the CrossMux AirPage information page"
    )
    parser.add_argument(
        "--push", action="store_true", help="upload the rendered BMP to AirPage"
    )
    parser.add_argument(
        "--json", action="store_true", help="print a machine-readable result"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="render offline example data; cannot be pushed",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    service = AirPageService(Settings.from_env())
    try:
        result = service.run_once(push=args.push, demo=args.demo)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must return a clean error
        if args.json:
            print(
                json.dumps({"ok": False, "error": error_name(exc)}, ensure_ascii=False)
            )
        else:
            print(f"失败：{error_name(exc)}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        action = "已上传" if result["uploaded"] else "已渲染"
        print(f"{action}：{result['bmp']} ({result['bmp_bytes']} bytes)")
        if result.get("push", {}).get("manual_refresh"):
            print("图片已上传，自动刷新未触发；请按设备向下键手动刷新。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

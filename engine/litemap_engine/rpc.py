from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any

from .errors import EngineError
from .service import EngineService


def response(service: EngineService, request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "Invalid Request"}}
    if request_id is None:
        try:
            service.dispatch(request["method"], request.get("params"))
        except Exception:
            pass
        return None
    try:
        result = service.dispatch(request["method"], request.get("params"))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except EngineError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": str(exc)}}
    except (KeyError, TypeError, ValueError) as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": f"Invalid params: {exc}"}}
    except Exception as exc:
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": f"Internal error: {type(exc).__name__}"}}


def serve() -> int:
    service = EngineService()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = response(service, request)
        except json.JSONDecodeError:
            result = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if result is not None:
            sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="LiteMaptica persistent JSON-RPC engine")
    parser.add_argument("--serve", action="store_true", help="serve line-delimited JSON-RPC on stdin/stdout")
    args = parser.parse_args()
    if not args.serve:
        parser.error("--serve is required")
    raise SystemExit(serve())


if __name__ == "__main__":
    main()

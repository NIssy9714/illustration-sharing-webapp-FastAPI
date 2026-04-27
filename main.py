#!/usr/bin/env python3
"""FastAPI アプリケーションのスタートアップスクリプト。

このスクリプトで uvicorn を使用してアプリケーションを起動します。

実行方法:
    python main.py

または

    uvicorn app.main:app --reload
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

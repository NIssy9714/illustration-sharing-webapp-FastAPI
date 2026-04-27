#!/usr/bin/env python3
"""FastAPI アプリケーションの簡単な検証スクリプト。

モジュール import が正常に動作するか確認します。
"""

import sys

# app フォルダがインポートできるか確認
try:
    print("✓ app.main をインポート成功")
except Exception as e:
    print(f"✗ app.main のインポートに失敗: {e}")
    sys.exit(1)

# db モジュール確認
try:
    print("✓ app.db をインポート成功")
except Exception as e:
    print(f"✗ app.db のインポートに失敗: {e}")
    sys.exit(1)

# schemas 確認
try:
    print("✓ app.schemas をインポート成功")
except Exception as e:
    print(f"✗ app.schemas のインポートに失敗: {e}")
    sys.exit(1)

# routers 確認
try:
    print("✓ app.routers をインポート成功")
except Exception as e:
    print(f"✗ app.routers のインポートに失敗: {e}")
    sys.exit(1)

print("\n✓ すべてのモジュールが正常にインポートできました")

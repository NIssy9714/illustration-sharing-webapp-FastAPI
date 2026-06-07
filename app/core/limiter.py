"""slowapi のレートリミッタ共有インスタンス。

ルーター側で `from app.core.limiter import limiter` して
@limiter.limit デコレータで使う。
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# レート制限の有効/無効を環境変数で切り替える（既定: 有効）。
# E2E テストは同一 IP から短時間に多数の登録/ログインを行うため、
# 本番挙動（5/min 等）を維持したまま E2E 環境でだけ RATELIMIT_ENABLED=false で無効化する。
_RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() not in {"false", "0", "no"}


def rate_limit_exempt() -> bool:
    """各 @limiter.limit(..., exempt_when=rate_limit_exempt) から参照する免除判定。

    slowapi 0.1.9 では Limiter(enabled=False) を渡してもルート単位の
    @limiter.limit デコレータは無効化されない。確実に効くのは exempt_when の方で、
    True を返すとそのリクエストは制限対象から除外される。
    """
    return not _RATELIMIT_ENABLED


# IP アドレス（X-Forwarded-For を含む）でグルーピング
limiter = Limiter(key_func=get_remote_address, default_limits=[])

"""slowapi のレートリミッタ共有インスタンス。

ルーター側で `from app.core.limiter import limiter` して
@limiter.limit デコレータで使う。
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# IP アドレス（X-Forwarded-For を含む）でグルーピング
limiter = Limiter(key_func=get_remote_address, default_limits=[])

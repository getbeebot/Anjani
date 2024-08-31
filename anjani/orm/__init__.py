import os

from sqlalchemy.ext.asyncio import (  # noqa: F401
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from .tz_user import TzUser  # noqa: F401
from .tg_user_start_bot import TgUserStartBot  # noqa: F401


def init_engine():
    uri = os.getenv(
        "MYSQL_URI",
        "mysql+aiomysql://beebot:NFMQb!EY^8^N!9rja@192.168.101.100:3306/beebot?charset=utf8mb4",
    )
    return create_async_engine(
        uri,
        pool_size=10,
        pool_recycle=3600,
        pool_timeout=30,
    )

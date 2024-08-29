from datetime import datetime

from sqlalchemy import DateTime, String, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .base import ORMBase


class TgUserStartBot(ORMBase):
    __tablename__ = "tg_user_start_bot"

    """
CREATE TABLE `tg_user_start_bot` (
    `chat_id` varchar(255) COLLATE utf8mb4_general_ci NOT NULL,
    `bot_id` varchar(255) COLLATE utf8mb4_general_ci NOT NULL,
    `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`chat_id`,`bot_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
    """

    chat_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    create_at: Mapped[datetime] = mapped_column(
        DateTime(), name="create_time", default=datetime.now()
    )
    update_at: Mapped[datetime] = mapped_column(
        DateTime(), name="update_time", default=datetime.now()
    )

    def __init__(self, chat_id: int, bot_id: int):
        self.chat_id = str(chat_id)
        self.bot_id = str(bot_id)

    async def save(self, session: AsyncSession):
        async with session as cur:
            stmt = select(TgUserStartBot).where(
                TgUserStartBot.chat_id == self.chat_id,
                TgUserStartBot.bot_id == self.bot_id,
            )
            res = await cur.scalars(stmt)
            if not res.one_or_none():
                stmt = insert(TgUserStartBot).values(
                    chat_id=self.chat_id, bot_id=self.bot_id
                )
                await cur.execute(stmt)
                await cur.commit()

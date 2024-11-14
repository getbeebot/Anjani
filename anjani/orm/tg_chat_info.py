from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    SmallInteger,
    String,
    insert,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .base import ORMBase


class TgChatInfo(ORMBase):
    """
    CREATE TABLE `tz_user_tg_group` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '唯一标识符',
      `user_id` varchar(36) DEFAULT NULL COMMENT '用户ID',
      `chat_name` varchar(64) DEFAULT NULL COMMENT 'tg group name',
      `chat_id` bigint DEFAULT NULL COMMENT 'tg group id',
      `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
      `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      `chat_type` tinyint unsigned DEFAULT '0',
      `invite_link` varchar(100) DEFAULT NULL COMMENT 'group/channel 邀请链接',
      `bot_id` bigint NOT NULL COMMENT 'bot uid',
      `updated` tinyint NOT NULL DEFAULT '0' COMMENT '0 for not updated, 1 for updated',
      `deleted` tinyint DEFAULT '0',
      PRIMARY KEY (`id`),
      KEY `index_chatname_chatid` (`chat_id`,`chat_name`),
      KEY `bot_type_updated_idx` (`chat_type`,`bot_id`,`updated`)
    ) ENGINE=InnoDB AUTO_INCREMENT=4976 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户tg群组表'
    """

    __tablename__ = "tz_user_tg_group"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    chat_name: Mapped[str] = mapped_column(String(64), default=None)
    chat_type: Mapped[str] = mapped_column(SmallInteger, default=0)
    invite_link: Mapped[str] = mapped_column(String(100), default=None)
    bot_id: Mapped[str] = mapped_column(BigInteger)
    updated: Mapped[int] = mapped_column(SmallInteger, default=0)
    deleted: Mapped[int] = mapped_column(SmallInteger, default=0)
    create_at: Mapped[datetime] = mapped_column(DateTime(), name="create_time")
    update_at: Mapped[datetime] = mapped_column(DateTime(), name="update_time")

    def __init__(
        self,
        chat_id: int,
        chat_name: int,
        bot_id: int,
        chat_type: int = 0,
        invite_link: str = None,
        updated: int = 0,
        deleted: int = 0,
    ):
        self.chat_id = chat_id
        self.chat_name = chat_name
        self.bot_id = bot_id
        self.chat_type = chat_type
        self.invite_link = invite_link
        self.updated = updated
        self.deleted = deleted

    async def save(self, session: AsyncSession):
        values = {
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "chat_type": self.chat_type,
            "invite_link": self.invite_link,
            "bot_id": self.bot_id,
            "updated": self.updated,
            "deleted": self.deleted,
        }
        stmt = select(TgChatInfo).where(
            TgChatInfo.chat_id == self.chat_id,
            TgChatInfo.chat_type == self.chat_type,
            TgChatInfo.bot_id == self.bot_id,
        )

        res = await session.scalars(stmt)
        chat = res.one_or_none()

        if chat:
            stmt = (
                update(TgChatInfo)
                .where(
                    TgChatInfo.bot_id == self.bot_id,
                    TgChatInfo.chat_id == self.chat_id,
                    TgChatInfo.chat_type == self.chat_type,
                )
                .values(**values)
            )
        else:
            stmt = insert(TgChatInfo).values(**values)

        await session.execute(stmt)
        await session.commit()

    @classmethod
    async def get_all_chat(cls, session: AsyncSession, bot_id: int):
        async with session as cur:
            stmt = select(cls).where(cls.bot_id == bot_id)
            result = await cur.scalars(stmt)
            return result.fetchall()

    @classmethod
    async def get_chat(cls, session: AsyncSession, chat_id: int, bot_id: int):
        async with session as cur:
            stmt = select(cls).where(cls.chat_id == chat_id, cls.bot_id == bot_id)
            result = await cur.scalars(stmt)
            return result.one_or_none()

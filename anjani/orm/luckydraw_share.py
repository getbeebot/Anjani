from sqlalchemy import BigInteger, String, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import select
from sqlalchemy_json import MutableJson

from .base import ORMBase


class LuckydrawShare(ORMBase):
    __tablename__ = "luckydraw_share"

    project_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lang: Mapped[str] = mapped_column(String(255), primary_key=True)
    pics: Mapped[str] = mapped_column(String(255), default=None)
    btn_desc: Mapped[list[str]] = mapped_column(MutableJson, default=None)
    des: Mapped[str] = mapped_column(Text, default=None)

    @classmethod
    async def get_share_info(
        cls, session: AsyncSession, project_id: int, task_id: int, lang="en"
    ):
        async with session as cur:
            stmt = select(cls).where(
                cls.project_id == project_id, cls.task_id == task_id, cls.lang == lang
            )
            result = await cur.scalars(stmt)
            return result.one_or_none()

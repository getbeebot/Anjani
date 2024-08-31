from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class ORMBase(DeclarativeBase, AsyncAttrs):
    def __repr__(self) -> str:
        kvstr = ", ".join(
            [
                f"{k}={v!r}"
                for k, v in self.__dict__.items()
                if k != "_sa_instance_state"
            ]
        )
        return f"{type(self).__name__}({kvstr})"

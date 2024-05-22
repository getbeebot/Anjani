"""
For Telegram Web App share link generating
"""
import msgpack
import base58
import os
import logging

from anjani.util.db import AsyncMysqlClient

class TWA:
    log: logging.Logger
    mysql_client: AsyncMysqlClient

    TWA_LINK = os.getenv("TWA_LINK")

    def __init__(self):
        self.log = logging.getLogger("twa")
        self.mysql_client = AsyncMysqlClient.init_from_env()


    def generate_project_detail_link(self, project_id: int):
        args = msgpack.packb({
            "target": "projectDetail",
            "id": project_id,
        })
        args = base58.b58encode(args).decode("utf-8")
        return f"{self.TWA_LINK}={args}"

    @classmethod
    async def get_chat_project_link(cls, chat_id: int):
        twa = cls()
        try:
            await twa.mysql_client.connect()
            project_id = await twa.mysql_client.query_project_id_by_chat_id(chat_id)
            url = twa.generate_project_detail_link(project_id)
            return url
        except Exception as e:
            twa.log.error(str(e))
            return twa.TWA_LINK
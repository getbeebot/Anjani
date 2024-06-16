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

    TWA_LINK = os.getenv("TWA_LINK")

    def __init__(self):
        self.log = logging.getLogger("twa")


    def generate_project_detail_link(self, project_id: int):
        args = msgpack.packb({
            "target": "projectDetail",
            "id": project_id,
        })
        args = base58.b58encode(args).decode("utf-8")
        return f"{self.TWA_LINK}={args}"

    def generate_task_detail_link(self, project_id: int, task_id: int):
        args = msgpack.packb({
            "target": "taskShare",
            "id": project_id,
            "subid": task_id,
        })
        args = base58.b58encode(args).decode("utf-8")
        return f"{self.TWA_LINK}={args}"

    @classmethod
    async def get_chat_project_link(cls, mysql: AsyncMysqlClient, chat_id: int):
        twa = cls()
        try:
            project_id = await mysql.query_project_id_by_chat_id(chat_id)
            if project_id:
                url = twa.generate_project_detail_link(project_id)
            else:
                url = twa.TWA_LINK
        except Exception as e:
            twa.log.error(e)
            url = twa.TWA_LINK

        return url

    async def get_user_owned_groups(self, mysql: AsyncMysqlClient,user_id: int):
        try:
            rows = await mysql.query_user_owned_groups(user_id)
            return rows
        except Exception as e:
            self.log.error(e)

        return None

    async def get_chat_tasks(self, mysql: AsyncMysqlClient, chat_id: int) -> int:
        try:
            res = await mysql.query_project_tasks(chat_id)
            return res
        except Exception as e:
            self.log.error(e)

        return None

    async def get_chat_activity_participants(self, mysql: AsyncMysqlClient,chat_id: int) -> int:
        try:
            res = await mysql.query_project_participants(chat_id)
            return res
        except Exception as e:
            self.log.error(e)

        return None
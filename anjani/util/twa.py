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
    mysql: AsyncMysqlClient

    TWA_LINK = os.getenv("TWA_LINK")

    def __init__(self):
        self.log = logging.getLogger("twa")
        self.mysql= AsyncMysqlClient.init_from_env()


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
    async def get_chat_project_link(cls, chat_id: int):
        twa = cls()
        try:
            await twa.mysql.connect()
            project_id = await twa.mysql.query_project_id_by_chat_id(chat_id)
            if project_id:
                url = twa.generate_project_detail_link(project_id)
            else:
                url = twa.TWA_LINK
        except Exception as e:
            twa.log.error(e)
            url = twa.TWA_LINK
        finally:
            await twa.mysql.close()

        return url

    async def get_user_owned_groups(self, user_id: int):
        try:
            await self.mysql.connect()
            rows = await self.mysql.query_user_owned_groups(user_id)
            return rows
        except Exception as e:
            self.log.error(e)
        finally:
            await self.mysql.close()

        return None

    async def get_chat_tasks(self, chat_id: int) -> int:
        try:
            await self.mysql.connect()
            res = await self.mysql.query_project_tasks(chat_id)
            return res
        except Exception as e:
            self.log.error(e)
        finally:
            await self.mysql.close()

        return None

    async def get_chat_activity_participants(self, chat_id: int) -> int:
        try:
            await self.mysql.connect()
            res = await self.mysql.query_project_participants(chat_id)
            return res
        except Exception as e:
            self.log.error(e)
        finally:
            await self.mysql.close()

        return None
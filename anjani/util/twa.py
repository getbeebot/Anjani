"""
For Telegram Web App share link generating
"""
import msgpack
import base58
import os
import logging

from anjani.util.db import AsyncRedisClient
from anjani.util.db.mysql import MysqlPoolClient

class TWA:
    log: logging.Logger

    TWA_LINK = os.getenv("TWA_LINK")
    API_PREFIX = os.getenv("API_URL")
    # mysql: AsyncMysqlClient
    mysql: MysqlPoolClient
    redis: AsyncRedisClient

    def __init__(self, mysql: MysqlPoolClient, redis: AsyncRedisClient):
        self.log = logging.getLogger("TWA")
        self.mysql = mysql
        self.redis = redis

    @classmethod
    def init_from_env(cls):
        return cls(MysqlPoolClient.init_from_env(), AsyncRedisClient.init_from_env())

    def generate_project_detail_link(self, project_id: int, bot_id: int):
        args = msgpack.packb({
            "target": "projectDetail",
            "id": project_id,
            "botid": bot_id
        })
        args = base58.b58encode(args).decode("utf-8")
        return f"{self.TWA_LINK}={args}"

    def generate_task_detail_link(self, project_id: int, task_id: int, bot_id: int):
        args = msgpack.packb({
            "target": "taskShare",
            "id": project_id,
            "subid": task_id,
            "botid": bot_id,
        })
        args = base58.b58encode(args).decode("utf-8")
        return f"{self.TWA_LINK}={args}"

    def generate_project_leaderboard_link(self, project_id: int, bot_id: int):
        args = msgpack.packb({
            "target": "leaderBoard",
            "id": project_id,
            "botid": bot_id,
        })
        args = base58.b58encode(args).decode("utf-8")
        return f"{self.TWA_LINK}={args}"

    async def clean_up(self):
        await self.mysql.close()
        await self.redis.close()

    async def get_chat_project_link(self, chat_id: int, bot_id: int):
        url = self.TWA_LINK
        try:
            project_id = await self.mysql.query_project_id_by_chat_id(chat_id)
            if project_id:
                url = self.generate_project_detail_link(project_id, bot_id)
        except Exception as e:
            self.log.error("Get chat project link error: %s", e)

        return url

    async def get_user_owned_groups(self, user_id: int, bot_id: int):
        rows = None
        try:
            rows = await self.mysql.query_user_owned_groups(user_id, bot_id)
        except Exception as e:
            self.log.error("Get user owned groups error: %s", e)

        return rows

    async def get_chat_tasks(self, chat_id: int) -> int:
        res = None
        try:
            res = await self.mysql.query_project_tasks(chat_id)
        except Exception as e:
            self.log.error("Get chat tasks error: %s", e)

        return res

    async def get_chat_activity_participants(self, chat_id: int) -> int:
        res = None
        try:
            res = await self.mysql.query_project_participants(chat_id)
        except Exception as e:
            self.log.error("Get chat activity participants error: %s", e)

        return res

    async def get_chat_project_id(self, chat_id: int) -> int:
        res = None
        try:
            res = await self.mysql.query_project_id_by_chat_id(chat_id)
        except Exception as e:
            self.log.error("Get chat projec id error: %s", e)

        return res

    async def get_group_id_with_project(self, bot_id: int):
        res = None
        try:
            res = await self.mysql.retrieve_group_id_with_project(bot_id)
        except Exception as e:
            self.log.error("Get group id with projects error: %s", e)

        return res

    async def save_notify_record(self, chat_id: int, message_id: int):
        try:
            await self.redis.set(f"notify_{chat_id}", message_id)
        except Exception as e:
            self.log.error(f"save notify record error: {e}")

    async def get_previous_notify_record(self, chat_id: int):
        try:
            res = await self.redis.get(f"notify_{chat_id}")
        except Exception as e:
            self.log.error("Get previous notify record error: %s", e)

        return res

    async def get_chat_checkin_keyword(self, chat_id: int):
        res = None
        try:
            res = await self.redis.get(f"checkin_{chat_id}")
        except Exception as e:
            self.log.error("Get checking keywords error: %s", e)

        return res

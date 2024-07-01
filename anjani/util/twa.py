"""
For Telegram Web App share link generating
"""
import msgpack
import base58
import os
import logging

from anjani.util.db import AsyncMysqlClient, AsyncRedisClient

class TWA:
    log: logging.Logger

    TWA_LINK = os.getenv("TWA_LINK")
    API_PREFIX = os.getenv("API_URL")
    mysql: AsyncMysqlClient
    redis: AsyncRedisClient

    def __init__(self):
        self.log = logging.getLogger("twa")
        self.mysql = AsyncMysqlClient.init_from_env()
        self.redis = AsyncRedisClient.init_from_env()

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

    @classmethod
    async def get_chat_project_link(cls, chat_id: int, bot_id: int):
        twa = cls()
        try:
            await twa.mysql.connect()
            project_id = await twa.mysql.query_project_id_by_chat_id(chat_id)
            if project_id:
                url = twa.generate_project_detail_link(project_id, bot_id)
            else:
                url = twa.TWA_LINK
        except Exception as e:
            twa.log.error(e)
            url = twa.TWA_LINK
        finally:
            await twa.mysql.close()

        return url

    async def get_user_owned_groups(self, user_id: int, bot_id: int):
        rows = None
        try:
            await self.mysql.connect()
            rows = await self.mysql.query_user_owned_groups(user_id, bot_id)
        except Exception as e:
            self.log.error(e)
        finally:
            await self.mysql.close()

        return rows

    async def get_chat_tasks(self, chat_id: int) -> int:
        res = None
        try:
            await self.mysql.connect()
            res = await self.mysql.query_project_tasks(chat_id)
        except Exception as e:
            self.log.error(e)
        finally:
            await self.mysql.close()

        return res

    async def get_chat_activity_participants(self, chat_id: int) -> int:
        res = None
        try:
            await self.mysql.connect()
            res = await self.mysql.query_project_participants(chat_id)
        except Exception as e:
            self.log.error(e)
        finally:
            await self.mysql.close()

        return res

    async def get_chat_project_id(self, chat_id: int) -> int:
        res = None
        try:
            await self.mysql.connect()
            res = await self.mysql.query_project_id_by_chat_id(chat_id)
        except Exception as e:
            self.log.error(e)
        finally:
            await self.mysql.close()

        return res

    async def get_group_id_with_project(self, bot_id: int):
        try:
            await self.mysql.connect()
            res = await self.mysql.retrieve_group_id_with_project(bot_id)
        except Exception as e:
            self.log.error(f"retriving group id with projects error: {e}")
            res = None
        finally:
            await self.mysql.close()
            return res

    async def save_notify_record(self, chat_id: int, message_id: int):
        try:
            await self.redis.connect()
            await self.redis.set(f"notify_{chat_id}", message_id)
        except Exception as e:
            self.log.error(f"save notify record error: {e}")
        finally:
            await self.redis.close()

    async def get_previous_notify_record(self, chat_id: int):
        try:
            await self.redis.connect()
            res = await self.redis.get(f"notify_{chat_id}")
        except Exception as e:
            self.log.error(f"get previous notify record error: {e}")
        finally:
            await self.redis.close()
        return res

    async def get_chat_checkin_keyword(self, chat_id: int):
        try:
            await self.redis.connect()
            res = await self.redis.get(f"checkin_{chat_id}")
        except Exception as e:
            self.log.error(f"Get checking keywords error: {e}")
        finally:
            await self.redis.close()
        return res

class TWA_V2:
    log: logging.Logger

    TWA_LINK = os.getenv("TWA_LINK")
    API_PREFIX = os.getenv("API_URL")
    mysql: AsyncMysqlClient
    redis: AsyncRedisClient

    def __init__(self, mysql: AsyncMysqlClient, redis: AsyncRedisClient):
        self.log = logging.getLogger("TWA")
        self.mysql = mysql
        self.redis = redis

    @classmethod
    def init_from_env(cls):
        return cls(AsyncMysqlClient.init_from_env(), AsyncRedisClient.init_from_env())

    async def _ensure_connected(self):
        if not self.mysql.conn:
            await self.mysql.connect()

        if not self.redis.connection:
            await self.redis.connect()

    async def ensure_db_closed(self):
        if self.mysql.conn:
            await self.mysql.close()

        if self.redis.connection:
            await self.redis.close()

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

    async def get_chat_project_link(self, chat_id: int, bot_id: int):
        url = self.TWA_LINK
        try:
            await self._ensure_connected()

            project_id = await self.mysql.query_project_id_by_chat_id(chat_id)
            if project_id:
                url = self.generate_project_detail_link(project_id, bot_id)
        except Exception as e:
            self.log.error("Get chat project link error: %s", e)

        return url

    async def get_user_owned_groups(self, user_id: int, bot_id: int):
        rows = None
        try:
            await self._ensure_connected()
            rows = await self.mysql.query_user_owned_groups(user_id, bot_id)
        except Exception as e:
            self.log.error("Get user owned groups error: %s", e)

        return rows

    async def get_chat_tasks(self, chat_id: int) -> int:
        res = None
        try:
            await self._ensure_connected()
            res = await self.mysql.query_project_tasks(chat_id)
        except Exception as e:
            self.log.error("Get chat tasks error: %s", e)

        return res

    async def get_chat_activity_participants(self, chat_id: int) -> int:
        res = None
        try:
            await self._ensure_connected()
            res = await self.mysql.query_project_participants(chat_id)
        except Exception as e:
            self.log.error("Get chat activity participants error: %s", e)

        return res

    async def get_chat_project_id(self, chat_id: int) -> int:
        res = None
        try:
            await self._ensure_connected()
            res = await self.mysql.query_project_id_by_chat_id(chat_id)
        except Exception as e:
            self.log.error("Get chat projec id error: %s", e)

        return res

    async def get_group_id_with_project(self, bot_id: int):
        res = None
        try:
            await self._ensure_connected()
            res = await self.mysql.retrieve_group_id_with_project(bot_id)
        except Exception as e:
            self.log.error("Get group id with projects error: %s", e)

        return res

    async def save_notify_record(self, chat_id: int, message_id: int):
        try:
            await self._ensure_connected()
            await self.redis.set(f"notify_{chat_id}", message_id)
        except Exception as e:
            self.log.error(f"save notify record error: {e}")

    async def get_previous_notify_record(self, chat_id: int):
        try:
            await self._ensure_connected()
            res = await self.redis.get(f"notify_{chat_id}")
        except Exception as e:
            self.log.error("Get previous notify record error: %s", e)

        return res

    async def get_chat_checkin_keyword(self, chat_id: int):
        res = None
        try:
            await self.redis.connect()
            res = await self.redis.get(f"checkin_{chat_id}")
        except Exception as e:
            self.log.error("Get checking keywords error: %s", e)

        return res

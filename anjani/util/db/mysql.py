import asyncio
import logging
from enum import Enum
from os import getenv
from typing import Optional

import aiomysql


class QueryType(Enum):
    EXECUTEMANY = "executemany"
    FETCHONE = "fetchone"
    FETCHALL = "fetchall"


class MysqlPoolClient:
    def __init__(
        self, host: str, port: int, username: str, password: str, database: str
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self._pool: Optional[aiomysql.Pool] = None
        self.log = logging.getLogger("MySQL")

    @classmethod
    def init_from_env(cls):
        host = getenv("MYSQL_HOST")
        port = int(getenv("MYSQL_PORT"))
        user = getenv("MYSQL_USER")
        password = getenv("MYSQL_PASS")
        database = getenv("MYSQL_DB")
        return cls(host, port, user, password, database)

    async def connect(self):
        if not self._pool:
            self._pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                db=self.database,
                autocommit=True,
                maxsize=10,
                loop=asyncio.get_running_loop(),
            )

    async def execute(self, sql, values, method: QueryType = None):
        if not self._pool:
            await self.connect()

        if not self._pool:
            raise Exception("Can not connect to MySQL DB")

        res = None
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    self.log.debug(
                        "Executing mysql query %s with values %s", sql, values
                    )
                    if method == QueryType.EXECUTEMANY:
                        await cur.executemany(sql, values)
                        return
                    if values:
                        await cur.execute(sql, values)
                    else:
                        await cur.execute(sql)

                    if method:
                        query_func = getattr(cur, method.value)
                        res = await query_func()
        except Exception as e:
            self.log.error(
                "MySQL execute query %s with values %s failed, error: %s",
                sql,
                values,
                e,
            )
        return res

    async def close(self):
        if self._pool and not self._pool.closed:
            self._pool.close()
            await self._pool.wait_closed()

    async def query(self, sql: str, values=()):
        return await self.execute(sql, values, method=QueryType.FETCHALL)

    async def query_one(self, sql, values=()):
        return await self.execute(sql, values, method=QueryType.FETCHONE)

    async def update(self, sql, values=()):
        res = await self.execute(sql, values)
        if not res:
            return "Error"

    async def update_many(self, sql, values=[]):
        await self.execute(sql, values, QueryType.EXECUTEMANY)

    async def update_chat_info(self, data):
        chat_type = int(data.get("chat_type"))
        chat_name = data.get("chat_name")
        chat_id = int(data.get("chat_id"))
        invite_link = data.get("invite_link")
        bot_id = int(data.get("bot_id"))
        sql = f"SELECT * FROM tz_user_tg_group WHERE chat_id = {chat_id} AND user_id = 1 AND bot_id = {bot_id}"
        res = await self.query_one(sql)

        if res is None:
            sql = "INSERT INTO tz_user_tg_group (user_id, chat_name, chat_id, chat_type, invite_link, bot_id) VALUES (%s, %s, %s, %s, %s, %s)"
            values = (1, chat_name, chat_id, chat_type, invite_link, bot_id)
            await self.update(sql, values)
        else:
            sql = "UPDATE tz_user_tg_group SET chat_name=%s, chat_type=%s, invite_link=%s WHERE chat_id=%s AND user_id=1 AND bot_id=%s"
            values = (chat_name, chat_type, invite_link, chat_id, bot_id)
            await self.update(sql, values)

    async def update_user_info(self, **data):
        tg_user_id = int(data.get("tg_user_id"))
        username = data.get("username", "")
        nickname = data.get("nickname")
        avatar = data.get("avatar")

        sql = f"SELECT user_id FROM tz_app_connect WHERE biz_user_id = {tg_user_id}"
        (user_id,) = await self.query_one(sql)

        if user_id is not None:
            sql = (
                "UPDATE tz_user SET user_name=%s, nick_name=%s, pic=%s WHERE user_id=%s"
            )
            values = (username, nickname, avatar, user_id)
            await self.update(sql, values)

    async def get_chat_project_id(self, chat_id: int, bot_id: int) -> int:
        sql = "SELECT bp.id FROM bot_project AS bp JOIN bot_tenant AS bt ON bp.tenant_id = bt.id WHERE bp.target_id = %s AND bp.deleted = 0 AND bt.bot_id = %s"
        res = await self.query_one(sql, (chat_id, bot_id))
        return res[0] if res else None

    async def get_project_ids(self, bot_id: int):
        sql = "SELECT DISTINCT bp.id, bp.target_id FROM bot_project AS bp JOIN beebot.tz_user_tg_group AS tutg ON bp.target_id = tutg.chat_id WHERE bp.target_id IS NOT NULL AND bp.deleted = 0 AND tutg.chat_type = 0 AND tutg.bot_id=%s"
        res = await self.query(sql, (bot_id,))
        return res

    async def get_user_projects(self, user_id: int, bot_id: int):
        sql = "SELECT DISTINCT bp.id AS project_id, bp.name FROM bot_project AS bp JOIN tz_app_connect AS tac ON bp.owner_id = tac.user_id JOIN tz_user_tg_group AS tutg on bp.target_id = tutg.chat_id WHERE biz_user_id = %s AND bp.deleted = 0 AND tutg.bot_id = %s"
        values = (user_id, bot_id)
        res = await self.query(sql, values)
        return res

    async def get_project_tasks(self, project_id: int):
        sql = "SELECT COUNT(*) FROM beebot.bot_task WHERE project_id = %s AND deleted <> 1"
        (count,) = await self.query_one(sql, (project_id,))
        return count

    async def get_project_participants(self, project_id: int):
        sql = "SELECT COUNT(*) FROM beebot.bot_user_action WHERE project_id = %s"
        (count,) = await self.query_one(sql, (project_id,))
        return count

    async def get_project_brief(self, project_id: int):
        sql = "SELECT name, description FROM beebot.bot_project WHERE id = %s"
        res = await self.query_one(sql, (project_id,))
        return res

    async def save_start_record(self, chat_id: int, bot_id: int):
        # query before insert
        sql = "SELECT * FROM tg_user_start_bot WHERE chat_id = %s AND bot_id = %s"
        values = (chat_id, bot_id)
        res = await self.query_one(sql, values)
        if not res:
            sql = "INSERT INTO tg_user_start_bot (chat_id, bot_id) VALUES (%s, %s)"
            await self.update(sql, values)

    async def get_user_id(self, chat_id: int):
        sql = "SELECT user_id FROM tz_app_connect WHERE biz_user_id = %s AND app_id = 1"
        res = await self.query_one(sql, (chat_id,))
        return res[0] if res else None

    async def update_user_avatar(self, user_id: str, avatar: str):
        sql = "UPDATE tz_user SET pic = %s WHERE user_id = %s"
        values = (avatar, user_id)
        await self.update(sql, values)

    async def update_project_info(
        self, tenant_id: int, project_id: int, avatar: str, slogan: str
    ):
        sql = "UPDATE bot_project SET slogan = %s, logo_url = %s WHERE id = %s AND tenant_id = %s"
        values = (slogan, avatar, project_id, tenant_id)
        await self.update(sql, values)

    async def save_new_member(
        self, chat_id: int, chat_type: int, tg_user_id: int, bot_id: int, joined_date
    ):
        sql = "SELECT id FROM chat_user_join_record WHERE chat_id = %s AND chat_type = %s AND tg_user_id = %s AND bot_id = %s"
        res = await self.query_one(sql, (chat_id, chat_type, tg_user_id, bot_id))
        if not res:
            sql = "INSERT INTO chat_user_join_record(chat_id, chat_type, tg_user_id, bot_id, joined_time) VALUES(%s, %s, %s, %s, %s)"
            values = (chat_id, chat_type, tg_user_id, bot_id, joined_date)
            await self.update(sql, values)

        return None

    async def get_chats(self, bot_id: int):
        sql = "SELECT chat_id, chat_type FROM tz_user_tg_group WHERE bot_id = %s AND chat_type <> 2 AND updated = 0"
        res = await self.query(sql, (bot_id,))
        return res

    async def update_chat_status(self, bot_id: int, chat_id: int, chat_type: int):
        sql = "UPDATE tz_user_tg_group SET updated = 1 WHERE bot_id = %s AND chat_id = %s AND chat_type = %s"
        await self.update(sql, (bot_id, chat_id, chat_type))

    async def get_tag_id_by_name(self, name: str):
        sql = "SELECT tag_id FROM tags WHERE tag_name = %s"
        return await self.query_one(sql, (name,))

    async def get_admins(self):
        sql = "SELECT DISTINCT tu.user_id FROM tz_user AS tu LEFT JOIN bot_project AS bp on tu.user_id = bp.owner_id LEFT JOIN bot_project_admin AS bpa ON tu.user_id = bpa.user_id WHERE (bp.owner_id IS NOT NULL OR bpa.user_id IS NOT NULL) AND tu.user_id IS NOT NULL"
        return await self.query(sql)

    async def get_admins_with_notag(self):
        sql = "SELECT DISTINCT tu.user_id FROM tz_user AS tu LEFT JOIN bot_project AS bp on tu.user_id = bp.owner_id LEFT JOIN bot_project_admin AS bpa ON tu.user_id = bpa.user_id LEFT JOIN user_tags AS ut ON tu.user_id = ut.user_id WHERE (bp.owner_id IS NOT NULL OR bpa.user_id IS NOT NULL AND ut.user_id IS NULL) AND tu.user_id IS NOT NULL"
        return await self.query(sql)

    async def update_admins(self, admins):
        sql = "INSERT INTO user_tags(user_id, tag_id) VALUES (%s, %s)"
        await self.update_many(sql, admins)

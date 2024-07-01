from os import getenv
import logging
from typing import Any, Dict, Sequence

from mysql.connector.aio import connect


class AsyncMysqlClient:
    def __init__(self, host: str, port: int, user: str, password: str, database: str) -> None:
        self.conn = None
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.log = logging.getLogger("mysql")

    @classmethod
    def init_from_env(cls):
        host = getenv("MYSQL_HOST")
        port = int(getenv("MYSQL_PORT"))
        user = getenv("MYSQL_USER")
        password = getenv("MYSQL_PASS")
        database = getenv("MYSQL_DB")

        client = cls(host, port, user, password, database)
        return client

    async def connect(self):
        try:
            self.conn = await connect(
                host=self.host, port=self.port,
                user=self.user, password=self.password,
                database=self.database,
                auth_plugin="mysql_native_password")

        except Exception as e:
            self.log.error("Error connecting to MySQL: %s", e)
            self.conn = None

        return self.conn

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def query(self, sql: str, values: Sequence[Any] | Dict[str, Any] = ()):
        if not self.conn:
            await self.connect()

        if not self.conn:
            return None

        try:
            cursor = await self.conn.cursor()
            if values:
                await cursor.execute(sql, values)
            else:
                await cursor.execute(sql)
            rows = await cursor.fetchall()
            return rows
        except Exception as e:
            self.log.error("Error executing query %s: %s", sql, e)
            return None
        finally:
            await cursor.close()

    async def query_one(self, sql: str, values: Sequence[Any] | Dict[str, Any] = ()):
        if not self.conn:
            await self.connect()
        if not self.conn:
            return None

        try:
            cursor = await self.conn.cursor()
            if values:
                await cursor.execute(sql, values)
            else:
                await cursor.execute(sql)
            return await cursor.fetchone()
        except Exception as e:
            self.log.error("Error executing query %s: %s", sql, e)
            return None
        finally:
            await cursor.close()

    async def update(self, sql: str, values: Sequence[Any] | Dict[str, Any] = ()):
        if not self.conn:
            await self.connect()

        if not self.conn:
            return None

        try:
            cursor = await self.conn.cursor()
            if values:
                await cursor.execute(sql, values)
            else:
                await cursor.execute(sql)
            await self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            self.log.error("Error modifing data: %s", e)
            return None
        finally:
            await cursor.close()

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
        (user_id, ) = await self.query_one(sql)

        if user_id is not None:
            sql = "UPDATE tz_user SET user_name=%s, nick_name=%s, pic=%s WHERE user_id=%s"
            values = (username, nickname, avatar, user_id)
            await self.update(sql, values)

    async def query_project_id_by_chat_id(self, chat_id: int) -> int:
        sql = "SELECT id FROM bot_project WHERE target_id=%s"
        row = await self.query_one(sql, (chat_id, ))
        if row:
            (project_id, ) =  row
            return project_id
        else:
            return None

    async def retrieve_group_id_with_project(self, bot_id: int):
        sql = "SELECT DISTINCT bp.id, bp.target_id FROM bot_project AS bp JOIN beebot.tz_user_tg_group AS tutg ON bp.target_id = bp.target_id WHERE bp.target_id IS NOT NULL AND tutg.bot_id=%s"
        res = await self.query(sql, (bot_id, ))
        return res

    async def query_user_owned_groups(self, user_id: int, bot_id: int):
        sql = "SELECT DISTINCT bp.id AS project_id, bp.name FROM bot_project AS bp JOIN tz_app_connect AS tac ON bp.owner_id = tac.user_id JOIN tz_user_tg_group AS tutg on bp.target_id = tutg.chat_id WHERE biz_user_id = %s AND bp.deleted = 0 AND tutg.bot_id = %s"
        values = (user_id, bot_id)
        res = await self.query(sql, values)
        return res

    async def query_project_tasks(self, chat_id: int):
        project_id = await self.query_project_id_by_chat_id(chat_id)
        sql = "SELECT COUNT(*) FROM beebot.bot_task WHERE project_id = %s AND deleted <> 1"
        (count, )= await self.query_one(sql, (project_id, ))
        return count

    async def query_project_participants(self, chat_id: int):
        project_id = await self.query_project_id_by_chat_id(chat_id)
        sql = "SELECT COUNT(*) FROM beebot.bot_user_action WHERE project_id = %s"
        (count, ) = await self.query_one(sql, (project_id, ))
        return count

import aiomysql
from typing import Optional

class MysqlPoolClient:
    def __init__(self, host: str, port: int, username: str, password: str, database: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self._pool: Optional[aiomysql.Pool] = None
        self.log = logging.getLogger("MySQL")

    async def connect(self):
        if not self._pool:
            self._pool = await aiomysql.create_pool(
                host=self.host, port=self.port,
                user=self.username, password=self.password,
                db=self.database, autocommit=True,
            )
        self.log.info("Connected to MySQL database")

    async def get_cursor(self) -> aiomysql.Cursor:
        if not self._pool:
            await self.connect()

        if not self._pool:
            self.log.error("MySQL connection is not available")

        async with self._pool.acquire() as conn:
            return await conn.cursor()

    async def close(self):
        if self._pool:
            await self._pool.close()
            self.log.info("Closed MySQL connection pool")

    async def query(self, sql: str, values = ()):
        try:
            cursor = await self.get_cursor()
            if values:
                await cursor.execute(sql, values)
            else:
                await cursor.execute(sql)
            return await cursor.fetchall()
        except Exception as e:
            self.log.error("MySQL query %s error: %s", sql, e)

    async def query_one(self, sql, values=()):
        try:
            cursor = await self.get_cursor()
            if values:
                await cursor.execute(sql, values)
            else:
                await cursor.execute(sql)
            return await cursor.fetchone()
        except Exception as e:
            self.log.error("MySQL query %s, error: %s", sql, e)

    async def update(self, sql, values=()):
        try:
            cursor = await self.get_cursor()
            if values:
                await cursor.execute(sql, values)
            else:
                await cursor.execute(sql)
        except Exception as e:
            self.log.error("MySQL query %s, error: %s", sql, e)

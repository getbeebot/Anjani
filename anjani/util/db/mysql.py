from os import getenv
from pathlib import Path
import logging

from dotenv import load_dotenv
from mysql.connector.aio import connect

from anjani import DEFAULT_CONFIG_PATH

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

    async def query(self, sql:str):
        if not self.conn:
            await self.connect()

        if not self.conn:
            return None

        try:
            cursor = await self.conn.cursor()
            await cursor.execute(sql)
            rows = await cursor.fetchall()
            return rows
        except Exception as e:
            self.log.error("Error executing query %s: %s", sql, e)
            return None
        finally:
            await cursor.close()

    async def query_one(self, sql: str):
        if not self.conn:
            await self.connect()
        if not self.conn:
            return None

        try:
            cursor = await self.conn.cursor()
            await cursor.execute(sql)
            return await cursor.fetchone()
        except Exception as e:
            self.log.error("Error executing query %s: %s", sql, e)
            return None
        finally:
            await cursor.close()

    async def update(self, sql: str):
        if not self.conn:
            await self.connect()

        if not self.conn:
            return None

        try:
            cursor = await self.conn.cursor()
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
            sql = f"INSERT INTO tz_user_tg_group (user_id, chat_name, chat_id, chat_type, invite_link, bot_id) VALUES (1, '{chat_name}', {chat_id}, '{chat_type}', '{invite_link}', {bot_id})"
            await self.update(sql)
        else:
            sql = f"UPDATE tz_user_tg_group SET chat_name='{chat_name}', chat_type={chat_type}, invite_link='{invite_link}' WHERE chat_id={chat_id} AND user_id=1 AND bot_id={bot_id}"
            await self.update(sql)

    async def update_user_info(self, **data):
        tg_user_id = int(data.get("tg_user_id"))
        username = data.get("username", "")
        nickname = data.get("nickname")
        avatar = data.get("avatar")

        sql = f"SELECT user_id FROM tz_app_connect WHERE biz_user_id = {tg_user_id}"
        (user_id, ) = await self.query_one(sql)

        if user_id is not None:
            sql = f"UPDATE tz_user SET user_name='{username}', nick_name='{nickname}', pic='{avatar}' WHERE user_id='{user_id}'"
            await self.update(sql)

    async def query_project_id_by_chat_id(self, chat_id: int) -> int:
        sql = f"SELECT id FROM bot_project WHERE target_id={chat_id}"
        row = await self.query_one(sql)
        if row:
            (project_id, ) =  row
            return project_id
        else:
            return None

    async def retrieve_group_id_with_project(self):
        sql = "SELECT id, target_id FROM bot_project WHERE target_id IS NOT NULL AND target_type = 0"
        res = await self.query(sql)
        return res

    async def query_user_owned_groups(self, user_id: int, bot_id: int):
        sql = f"""
SELECT
  DISTINCT bp.id AS project_id, bp.name
FROM bot_project AS bp
JOIN tz_app_connect AS tac ON bp.owner_id = tac.user_id
JOIN tz_user_tg_group AS tutg on bp.target_id = tutg.chat_id
WHERE biz_user_id = '{user_id}' AND bp.deleted = 0 AND tutg.bot_id = {bot_id}
"""
        res = await self.query(sql)
        return res

    async def query_project_tasks(self, chat_id: int):
        project_id = await self.query_project_id_by_chat_id(chat_id)
        sql = f"SELECT COUNT(*) FROM beebot.bot_task WHERE project_id = '{project_id}' AND deleted <> 1"
        (count, )= await self.query_one(sql)
        return count

    async def query_project_participants(self, chat_id: int):
        project_id = await self.query_project_id_by_chat_id(chat_id)
        sql = f"SELECT COUNT(*) FROM beebot.bot_user_action WHERE project_id = '{project_id}'"
        (count, ) = await self.query_one(sql)
        return count
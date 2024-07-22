import logging
import aiomysql

from os import getenv
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
        try:
            if self._pool and not self._pool.closed:
                await self._pool.close()
                self.log.info("Closed MySQL connection pool")
        except Exception:
            pass

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

    async def get_chat_project_id(self, chat_id: int) -> int:
        sql = "SELECT id FROM bot_project WHERE target_id=%s"
        row = await self.query_one(sql, (chat_id, ))
        try:
            if row:
                (project_id, ) =  row
                return project_id
            else:
                return None
        except Exception as e:
            self.log.warn("Get chat %s project id error: %s", chat_id, e)
            return None

    async def get_project_ids(self, bot_id: int):
        sql = "SELECT DISTINCT bp.id, bp.target_id FROM bot_project AS bp JOIN beebot.tz_user_tg_group AS tutg ON bp.target_id = tutg.chat_id WHERE bp.target_id IS NOT NULL AND bp.deleted = 0 AND tutg.chat_type = 0 AND tutg.bot_id=%s"
        res = await self.query(sql, (bot_id, ))
        return res

    async def get_user_projects(self, user_id: int, bot_id: int):
        sql = "SELECT DISTINCT bp.id AS project_id, bp.name FROM bot_project AS bp JOIN tz_app_connect AS tac ON bp.owner_id = tac.user_id JOIN tz_user_tg_group AS tutg on bp.target_id = tutg.chat_id WHERE biz_user_id = %s AND bp.deleted = 0 AND tutg.bot_id = %s"
        values = (user_id, bot_id)
        res = await self.query(sql, values)
        return res

    async def get_project_tasks(self, project_id: int):
        sql = "SELECT COUNT(*) FROM beebot.bot_task WHERE project_id = %s AND deleted <> 1"
        (count, )= await self.query_one(sql, (project_id, ))
        return count

    async def get_project_participants(self, project_id: int):
        sql = "SELECT COUNT(*) FROM beebot.bot_user_action WHERE project_id = %s"
        (count, ) = await self.query_one(sql, (project_id, ))
        return count

    async def get_project_brief(self, project_id: int):
        sql = "SELECT name, description FROM beebot.bot_project WHERE id = %s"
        res = await self.query_one(sql, (project_id, ))
        return res

    async def save_start_record(self, chat_id: int, bot_id: int):
        # query before insert
        sql = "SELECT * FROM tg_user_start_bot WHERE chat_id = %s AND bot_id = %s"
        values = (chat_id, bot_id)
        res = await self.query_one(sql, values)
        if not res:
            sql = "INSERT INTO tg_user_start_bot (chat_id, bot_id) VALUES (%s, %s)"
            await self.update(sql, values)
from os import getenv
from pathlib import Path

from dotenv import load_dotenv
from mysql.connector.aio import connect

from anjani import DEFAULT_CONFIG_PATH


def get_config():
    config_path = Path(DEFAULT_CONFIG_PATH)
    if config_path.is_file():
        load_dotenv(config_path)
    host = getenv("MYSQL_HOST")
    port = getenv("MYSQL_PORT")
    user = getenv("MYSQL_USER")
    password = getenv("MYSQL_PASS")
    database = getenv("MYSQL_DB")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


async def insert_data(data):
    config = get_config()
    async with await connect(**config) as conn:
        async with await conn.cursor() as cursor:
            group_name = data.group_name
            group_id = data.group_id
            query_sql = f"SELECT * FROM tz_user_tg_group WHERE group_name = {group_name} AND group_id = {group_id}"
            await cursor.execute(query_sql)
            res = await cursor.fetchone()

            if res is None:
                insert_sql = f"INSERT INTO tz_user_tg_group (user_id, group_name, group_id) VALUES (1, {group_name}, {group_id})"
                await cursor.execute(insert_sql)
                await conn.commit()

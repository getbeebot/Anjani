from os import getenv
import logging

from aioredis import Redis

class AsyncRedisClient:
    def __init__(self, host, port=6379, username='default', password=None, db=0):
        self.host = host
        self.port = port
        self.db = db
        self.username = username
        self.password = password
        self.connection = None
        self.log = logging.getLogger("redis")

    @classmethod
    def init_from_env(cls):
        host = getenv("REDIS_HOST")
        port = int(getenv("REDIS_PORT"))
        username = getenv("REDIS_USERNAME")
        password = getenv("REDIS_PASSWORD")
        db = int(getenv("REDIS_DATABASE"))
        client = cls(host, port, username, password, db)
        return client

    async def connect(self):
        try:
            self.connection = await Redis(
                host=self.host, port=self.port, db=self.db,
                username=self.username, password=self.password)
        except Exception as e:
            self.log.error(e)
            self.connection = None

    async def get(self, key):
        if not self.connection:
            await self.connect()

        if self.connection:
            return await self.connection.get(key)
        else:
            self.log.error("Not connected to Redis server!")
            return None

    async def set(self, key, value, ttl: int = None):
        if not self.connection:
            await self.connect()

        if self.connection:
            if not ttl:
                await self.connection.set(key, value)
            else:
                await self.connection.set(key, value, ex=ttl)
        else:
            self.log.error("Not connected to Redis server!")

    async def delete(self, key):
        if not self.connection:
            await self.connect()

        if self.connection:
            try:
                return await self.connection.delete(key)
            except Exception as e:
                self.log.error(e)
                return 0
        else:
            self.log.error("Not connected to Redis server!")
            return 0

    async def close(self):
        if self.connection:
            try:
                await self.connection.close()
            except Exception as e:
                self.log.error(e)
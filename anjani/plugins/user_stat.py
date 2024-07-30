import os

import asyncio

from typing import ClassVar

from anjani import plugin, util

class UserStats(plugin.Plugin):
    name: ClassVar[str] = "User Stats"
    helpable: ClassVar[bool] = False

    mysql: util.db.MysqlPoolClient

    async def on_load(self) -> None:
        self.mysql = util.db.MysqlPoolClient.init_from_env()

    async def on_start(self, _: int) -> None:
        scraping_p = os.getenv("IS_SCRAPING", False)
        if not scraping_p:
            return

        chats = await self.mysql.get_chats(self.bot.uid)
        if not chats:
            return None

        loop = asyncio.get_running_loop()
        for chat in chats:
            (chat_id, chat_type) = chat
            loop.create_task(self.update_chat_member_join_record(chat_id, chat_type))

    async def update_chat_member_join_record(self, chat_id: int, chat_type: int) -> None:
        try:
            mysql_client = util.db.MysqlPoolClient.init_from_env()
            async for member in self.bot.client.get_chat_members(chat_id):
                if member.joined_date:
                    await mysql_client.save_new_member(chat_id, chat_type, member.user.id, self.bot.uid, member.joined_date)
        except Exception as e:
            self.log.warn("Update chat member join record for %s failed: %s", chat_id, e)
        finally:
            del mysql_client

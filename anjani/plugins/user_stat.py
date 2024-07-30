import asyncio

from typing import ClassVar

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from anjani import plugin, util

class UserStats(plugin.Plugin):
    name: ClassVar[str] = "User Stats"
    helpable: ClassVar[bool] = False

    mysql: util.db.MysqlPoolClient

    async def on_load(self) -> None:
        self.mysql = util.db.MysqlPoolClient.init_from_env()

    async def on_start(self, _: int) -> None:
        scheduler = AsyncIOScheduler()
        trigger = IntervalTrigger(hours=7)
        scheduler.add_job(self.run_update, trigger=trigger)
        scheduler.start()
        self.log.info("Starting update chat member join records")

    async def on_stop(self) -> None:
        await self.mysql.close()

    async def run_update(self) -> None:
        chats = await self.mysql.get_chats(self.bot.uid)
        if not chats:
            self.log.warn("No chats need to update")
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
            await mysql_client.update_chat_status(self.bot.uid, chat_id, chat_type)
            await mysql_client.close()
            del mysql_client

import json
from datetime import datetime, timezone

from typing import ClassVar

from pyrogram.types import Message

from anjani import plugin, listener, filters

class MessageStats(plugin.Plugin):
    name: ClassVar[str] = "Message Stats"
    helpable: ClassVar[bool] = False

    @listener.filters(filters.group)
    async def on_message(self, message: Message) -> None:
        chat = message.chat
        stat_key = f"chat_stats_{chat.id}"
        stat_p = await self.bot.redis.get(stat_key)

        from_user = message.from_user

        if not from_user or from_user.is_bot:
            self.log.debug("No from user field or from user is bot, %s", from_user)
            return

        if not stat_p:
            self.log.debug("Not set group statistics task")
            return

        # 1. decode bytes from redis
        chat_stat = json.loads(stat_p.decode("utf-8"))

        # 2. get the count of from user, if none, set to 0
        count = chat_stat.get(from_user.id) or 0

        # 3. increase the from user count
        count += 1

        # 4. encode stat data
        chat_stat.update({from_user.id: count})
        chat_stat_v = json.dumps(chat_stat)

        # 5. calculate ttl and write stat data back to redis
        today = datetime.today()
        expiry = datetime(year=today.year, month=today.month, day=today.day, hour=23, minute=59, second=59)
        delta = expiry - datetime.now()
        ttl = delta.total_seconds()

        await self.bot.redis.set(stat_key, chat_stat_v, ttl=ttl)
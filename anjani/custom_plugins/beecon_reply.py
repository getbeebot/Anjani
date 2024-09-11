from typing import ClassVar

from pyrogram import filters
from pyrogram.types import Message

from anjani import listener, plugin


class BeeconReply(plugin.Plugin):
    name: ClassVar[str] = "Beecon Reply Plugin"
    helpable: ClassVar[bool] = False

    @listener.filters(filters.private)
    async def on_message(self, message: Message) -> None:
        if message.command:
            self.log.info("Receiving command %s", message.command)
            return None
        await message.reply(
            "Subscribe @daily_gifts_en and @airdrophub_great to earn more."
        )

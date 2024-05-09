from os import getenv
from typing import ClassVar

from pyrogram import filters
from pyrogram.types import Message

from anjani import command, listener, plugin


class RepeaterPlugin(plugin.Plugin):
    name: ClassVar[str] = "Repeater Plugin"
    helpable: ClassVar[bool] = True

    java_api = getenv("JAVA_API")

    async def cmd_hi(self, ctx: command.Context) -> None:
        await ctx.respond("hola")

    @listener.filters(filters.group | filters.channel)
    async def on_message(self, message: Message) -> None:
        payloads = "".join(str(message).split())
        self.log.debug(f"Receiving message: {payloads}")

        async with self.bot.http.post(
            base_url=self.java_api,
            # headers={},
            json=payloads,
        ) as r:
            res = await r.json()
            self.log.debug(f"Java api response: {res}")

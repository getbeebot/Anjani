import json
import os
from datetime import datetime, timezone

import aiofiles
from typing import ClassVar

from pyrogram import filters
from pyrogram.types import Message

from anjani import command, listener, plugin


class RepeaterPlugin(plugin.Plugin):
    name: ClassVar[str] = "Repeater Plugin"
    helpable: ClassVar[bool] = True

    async def cmd_hi(self, ctx: command.Context) -> None:
        await ctx.respond("hola")

    @listener.filters(filters.group | filters.channel)
    async def on_message(self, message: Message) -> None:
        payloads = "".join(str(message).split())
        self.log.debug(f"Receiving message: {payloads}")
        payloads = json.loads(payloads)
        await self.save_message(payloads)

    async def save_message(self, message) -> None:
        target_dir = "messages"
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        now = int(datetime.now(timezone.utc).timestamp())
        async with aiofiles.open(f"{target_dir}/{now}.json", mode="w") as f:
            for line in json.dumps(message, indent=4).splitlines(True):
                await f.write(line)

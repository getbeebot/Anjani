import json
import os
from datetime import datetime, timezone

import aiofiles
from typing import ClassVar

from pyrogram import filters
from pyrogram.types import Message

from anjani import command, listener, plugin


class BeeconPlugin(plugin.Plugin):
    name: ClassVar[str] = "Beecon Plugin"
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
        # TODO: saving in every single 10MiB file classified with group id
        target_dir = "messages"
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        now = int(datetime.now(timezone.utc).timestamp())
        async with aiofiles.open(f"{target_dir}/{now}.json", mode="w") as f:
            for line in json.dumps(message, indent=4).splitlines(True):
                await f.write(line)

    @listener.filters(filters.group)
    async def on_chat_action(self, message: Message) -> None:
        # TODO: create project when bot join the group
        pass
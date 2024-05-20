import json
from datetime import datetime, timezone

import aiofiles
import aiofiles.os as aio_os
from os.path import join
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
        target_dir = "messages"
        await self.create_if_not_exist(target_dir)

        chat_id = message.get("chat").get("id", "-0")
        chat_dir_name = str(chat_id)[1:]
        chat_path = join(target_dir, chat_dir_name)
        await self.create_if_not_exist(chat_path)

        target_file = await self.get_target_file(chat_path)
        if not target_file:
            ts = int(datetime.now(timezone.utc).timestamp())
            target_file = join(chat_path, f"{str(ts)}.json")

        async with aiofiles.open(target_file, mode="a") as f:
            for line in json.dumps(message, indent=4).splitlines(True):
                await f.write(line)
            f.write("\n")

    async def create_if_not_exist(self, path):
        result = await aio_os.path.exists(path)
        if not result:
            await aio_os.mkdir(path)

    async def get_target_file(self, directory):
        try:
            dirs = await aio_os.listdir(directory)
            for file in dirs:
                filepath = join(directory, file)
                size = await aio_os.path.getsize(filepath)
                if size and size <= 20 * 1024 * 1024:
                    return filepath
        except Exception:
            return None

    @listener.filters(filters.group)
    async def on_chat_action(self, message: Message) -> None:
        # TODO: create project when bot join the group
        pass
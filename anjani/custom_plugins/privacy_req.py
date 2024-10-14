from typing import ClassVar, Optional

from pyrogram import filters
from pyrogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from anjani import command, listener, plugin


class PrivacyRequest(plugin.Plugin):
    name: ClassVar[str] = "Privacy Request Plugin"
    helpable: ClassVar[bool] = False

    @listener.filters(filters.private)
    async def on_message(self, message: Message) -> None:
        pass
        # if message.command:
        #     self.log.info("Receiving command %s", message.command)
        #     return None

    @command.filters(filters.private)
    async def cmd_yukit(self, ctx: command.Context) -> Optional[str]:
        try:
            btn = KeyboardButton(text="request locaction", request_location=True)
            kb = ReplyKeyboardMarkup([[btn]])
            await ctx.respond("Hello", reply_markup=kb)
        except Exception as e:
            self.log.error("Testing command error: %s", e)

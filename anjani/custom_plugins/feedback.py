import asyncio
from typing import ClassVar, Optional

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pyrogram.errors import MessageDeleteForbidden


from anjani import command, listener, plugin, util


class BeeconFeedback(plugin.Plugin):
    name: ClassVar[str] = "Beecon Feedback Plugin"
    helpable: ClassVar[bool] = False

    mysql: util.db.MysqlPoolClient

    async def on_load(self) -> None:
        self.mysql = util.db.MysqlPoolClient.init_from_env()

    async def on_stop(self) -> None:
        await self.mysql.close()

    async def on_start(self, _: int) -> None:
        await self.mysql.connect()

    @listener.filters(filters.regex(r"fb_usdt_(.*)"))
    async def on_callback_query(self, query: CallbackQuery) -> None:
        match = query.matches[0].group(1)
        if match.isdigit():
            # save to db
            await self.mysql.save_fb_usdt(query.message.chat.id, match)
        try:
            await query.message.delete()
        except MessageDeleteForbidden:
            pass
        await self.bot.client.send_message(
            query.message.chat.id,
            "Thank you for your feedback. We values every single user and will make progress based on your option.",
        )

    @command.filters(filters.private)
    async def cmd_usdtfb(self, ctx: command.Context) -> Optional[str]:
        chat_id = ctx.chat.id
        if not util.misc.is_whitelist(chat_id):
            self.log.warning("Not admin for yukix")
            return None

        users = await self.mysql.get_og_user()
        self.log.debug("OG users: %s", users)
        msg = """
We've received feedback from some of you regarding the issue of small amounts of USDT that cannot be withdrawn. We have the following options for you to choose from! Please select your preferred solution:

1. **Auto-Yield Service**: We can offer a service that allows your balance to grow over time, with an annual yield potentially exceeding 10%. You'll also have the option to deposit more funds to earn interest.
2. **Lottery-Style Game**: Participate in a fun game where you can place bets to win more prizes (but be aware that there's a chance of losing too).
3. **Virtual Goods**: We'll support the purchase of virtual items, such as TG Stars, Telegram Premium memberships, or gift cards.

We will seriously consider all your feedback.
        """
        option1 = "1. Auto-Yield Service"
        option2 = "2. Lottery-Style Game"
        option3 = "3. Virtual Goods"
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(option1, callback_data="fb_usdt_1"),
                ],
                [
                    InlineKeyboardButton(option2, callback_data="fb_usdt_2"),
                ],
                [
                    InlineKeyboardButton(option3, callback_data="fb_usdt_3"),
                ],
            ]
        )
        for u in users:
            await asyncio.sleep(1)
            user_chat_id = int(u[0])
            if user_chat_id == chat_id:
                await self.bot.client.send_message(
                    user_chat_id, msg, reply_markup=buttons
                )

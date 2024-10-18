import asyncio
from typing import ClassVar, Optional

from pyrogram import filters
from pyrogram.errors import MessageDeleteForbidden
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

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
            "Thank you for your feedback. We value every single user and will make progress based on your options.",
        )

    @command.filters(filters.private)
    async def cmd_usdtfb(self, ctx: command.Context) -> Optional[str]:
        chat_id = ctx.chat.id
        if not util.misc.is_whitelist(chat_id):
            self.log.warning("Not admin for yukix")
            return None

        # users = await self.mysql.get_og_user()
        users = await self.mysql.get_og_user2()
        self.log.debug("OG users: %s", users)
        msg = """
We've received feedback from some of you regarding the issue of small amounts of USDT that cannot be withdrawn. We have the following options for you to choose from! Please select your preferred solution:

1. **Virtual Goods**: We'll support the purchase of virtual items, such as TG Stars, Telegram Premium memberships, or gift cards.
2. **Lottery-Style Game**: Participate in a fun game where you can place bets to win more prizes (but be aware that there's a chance of losing too).
3. **Auto-Yield Service**: We can offer a service that allows your balance to grow over time, with an annual yield potentially exceeding 10%. You'll also have the option to deposit more funds to earn interest.

We will seriously consider all your feedback.
        """
        option3 = "1. Virtual Goods"
        option2 = "2. Lottery-Style Game"
        option1 = "3. Auto-Yield Service"
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(option3, callback_data="fb_usdt_3"),
                ],
                [
                    InlineKeyboardButton(option2, callback_data="fb_usdt_2"),
                ],
                [
                    InlineKeyboardButton(option1, callback_data="fb_usdt_1"),
                ],
            ]
        )
        for u in users:
            await asyncio.sleep(1)
            try:
                user_chat_id = int(u[0])
                await self.bot.client.send_message(
                    user_chat_id, msg, reply_markup=buttons
                )
                self.log.info("Sent usdt feedback message to user %s", user_chat_id)
            except Exception:
                pass

    @command.filters(filters.private)
    async def cmd_grayt(self, ctx: command.Context) -> Optional[str]:
        chat_id = ctx.chat.id
        if not util.misc.is_whitelist(chat_id):
            self.log.warning("Not admin for yukix")
            return None

        users = await self.mysql.get_passive_user()
        pic = "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/C-1002427123635.jpg"
        msg = """
🎁  A prize pool of 100 USDT, with a 100% chance of winning! Everyone wins, no one misses out!  🎉🎉


🔥 Don't miss this opportunity, join us now! 🚀✨


🌟 The rules are simple, and participating is easy! Invite your friends to join and discover even bigger surprises! 💃🕺


📅 This event is for a limited time only, so act fast! For more details, stay tuned to our channel! 📢🔔

👇Click below to open 🌈 ⬇️
"""
        url = "https://t.me/beecon_bot/app?startapp=Yqn7Gcpa6DBV1HyfBMfEZAHSykWXYWoHia6R3HV1mgeNMiZqgK2w7neWz4fhkEeoJ575bT9"
        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎁 Open 100 USDT 🎁", url=url)]]
        )
        self.log.debug("users: %s", users)
        for u in users:
            try:
                user_chat_id = int(u[0])
                # for testing
                if user_chat_id != 6812515288:
                    continue
                await self.bot.client.send_photo(
                    chat_id=user_chat_id, photo=pic, caption=msg, reply_markup=buttons
                )
                self.log.info("Sent gray test to user %s", user_chat_id)
            except Exception as e:
                self.log.warning("Sent gray test to user %s error %s", e)

import json
from typing import ClassVar, Optional, Union

from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from anjani import command, listener, plugin, util


def is_whitelist(chat_id) -> Optional[bool]:
    whitelist = [
        6812515288,
        1821086162,
        7465037644,
        2113937194,
        7037181285,
        1013334686,
        6303440178,
        7054195491,
    ]
    if chat_id in whitelist:
        return True

    return False


class BeeconCMDPlugin(plugin.Plugin):
    name: ClassVar[str] = "Beecon Admin command plugin"
    helpable: ClassVar[bool] = False

    redis: util.db.AsyncRedisClient

    async def on_load(self) -> None:
        self.redis = util.db.AsyncRedisClient.init_from_env()

    async def on_stop(self) -> None:
        await self.redis.close()

    async def on_start(self, _: int) -> None:
        await self.redis.connect()

    @listener.filters(filters.regex(r"notify_(.*)"))
    async def on_callback_query(self, query: CallbackQuery) -> None:
        match = query.matches[0].group()
        # TODO:
        if match == "admin":
            pass
        elif match == "user":
            pass
        elif match == "all":
            pass
        else:
            pass

    async def send_notify(self, cate: str) -> None:
        # step 1: query chat ids based on cate

        # step 2: create seperate task to send notify
        # self.bot.loop.create_task()
        pass

    async def get_msg(self, chat_id: int) -> Optional[dict]:
        # retrieve message from redis
        key = f"notify_msg_{chat_id}"
        values = await self.redis.get(key)
        if values:
            return json.loads(values.decode("utf-8"))

    async def save_msg(self, chat_id: int, msg: dict) -> None:
        key = f"notify_msg_{chat_id}"
        values = json.dumps(msg).encode("utf-8")
        await self.redis.set(key, values)

    async def msg_check(self, msg: Optional[dict]) -> Union[str, bool]:
        if not msg:
            return "You havn't set the message, please use /setpic, /setdesc, /setbtn to set message context"
        if not msg.get("desc"):
            return "The message is missing content, please /setdesc to set it."
        return True

    @command.filters(filters.private)
    async def cmd_notify(self, ctx: command.Context) -> Optional[str]:
        cate = ctx.input
        supported_cate = ["admin", "user", "all"]
        if cate not in supported_cate:
            return f"Only support one of {supported_cate} notify"
        # retrieve current message
        msg = await self.get_msg(ctx.chat.id)
        # checking the saved message integrity
        res = await self.msg_check(msg)
        if isinstance(res, str):
            return res
        msg_text = msg.get("desc")
        pic = msg.get("pic")
        btn = msg.get("btn")  # dict {"text": <text-value>, "url": <button-url>}

        btns = []
        if btn:
            btns.append([InlineKeyboardButton(**btn)])
        btns.append(
            [InlineKeyboardButton(text="Confirmed", callback_data=f"notify_{cate}")]
        )
        keyboard = InlineKeyboardMarkup(btns)
        if pic:
            await ctx.respond(photo=pic, caption=msg_text, reply_markup=keyboard)
            return
        await ctx.respond(text=msg_text, reply_markup=keyboard)

    @command.filters(filters.private)
    async def cmd_setpic(self, ctx: command.Context):
        msg = await self.get_msg()

    @command.filters(filters.private)
    async def cmd_setbtn(self, ctx: command.Context):
        msg = await self.get_msg()

    @command.filters(filters.private)
    async def cmd_setdesc(self, ctx: command.Context):
        msg = await self.get_msg()

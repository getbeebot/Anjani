import asyncio
import json
from typing import ClassVar, Optional, Union

import numpy as np
import validators
from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from anjani import command, listener, plugin, util

CHUNK_SIZE: int = 60 * 60 / 2


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


def remove_duplicate(lst: list) -> list:
    return list(dict.fromkeys(lst))


class BeeconCMDPlugin(plugin.Plugin):
    name: ClassVar[str] = "Beecon Admin Plugin"
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
        match = query.matches[0].group(1)
        msg = await self.get_msg(query.from_user.id)
        if not msg:
            await self.bot.client.send_messsage(
                query.from_user.id, "Message not set, hahahaha"
            )
            return None
        if match not in ["admin", "user", "all"]:
            self.log.warn("Cate %s not supported", match)
            return None
        await self.send_notify(msg, match)

    async def send_notify(self, msg: dict, cate: str) -> None:
        self.log.debug("Sending message to %s with %s", cate, msg)
        mysql_client = util.db.MysqlPoolClient.init_from_env()
        await mysql_client.connect()
        try:
            res = None
            if cate == "all":
                sql = "SELECT DISTINCT biz_user_id FROM tz_app_connect WHERE user_id IS NOT NULL AND biz_user_id IS NOT NULL"
                res = await mysql_client.query(sql)
            elif cate == "user":
                sql = "SELECT DISTINCT tac.biz_user_id FROM tz_app_connect AS tac LEFT JOIN bot_project AS bp ON tac.user_id = bp.owner_id LEFT JOIN bot_project_admin AS bpa ON tac.user_id  = bpa.user_id WHERE bp.owner_id IS NULL AND bpa.user_id IS NULL AND tac.biz_user_id IS NOT NULL"
                res = await mysql_client.query(sql)
            elif cate == "admin":
                sql = "SELECT DISTINCT tac.biz_user_id FROM tz_app_connect AS tac LEFT JOIN bot_project AS bp ON tac.user_id = bp.owner_id LEFT JOIN bot_project_admin AS bpa ON tac.user_id = bpa.user_id WHERE (bp.owner_id IS NOT NULL OR bpa.user_id IS NOT NULL) AND tac.biz_user_id IS NOT NULL"
                res = await mysql_client.query(sql)
            else:
                return
        except Exception:
            pass
        finally:
            await mysql_client.close()
            del mysql_client

        self.log.debug("MySQL DB results: %s", res)

        if not res:
            return

        chat_ids = remove_duplicate([int(r[0]) for r in res])
        chat_chunks = np.array_split(np.array(chat_ids), CHUNK_SIZE)

        btn = msg.get("btn")
        keyboard = None
        if btn and isinstance(btn, dict):
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(**btn)]])

        msg_text = msg.get("desc")
        pic = msg.get("pic")
        if not pic:
            for chats in chat_chunks:
                for chat_id in chats:
                    try:
                        await self.bot.client.send_message(
                            chat_id=int(chat_id), text=msg_text, reply_markup=keyboard
                        )
                    except Exception as e:
                        self.log.warn("Push notification to %s error: %s", chat_id, e)
                await asyncio.sleep(1)
            return None

        for chats in chat_chunks:
            for chat_id in chats:
                try:
                    await self.bot.client.send_photo(
                        chat_id=int(chat_id),
                        photo=pic,
                        caption=msg_text,
                        reply_markup=keyboard,
                    )
                except Exception as e:
                    self.log.warn("Push notification to %s error: %s", chat_id, e)
            await asyncio.sleep(1)

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
        self.log.debug("Notify %s, %s", msg_text, btn)
        if pic:
            await ctx.respond(msg_text, photo=pic, reply_markup=keyboard)
            return
        await ctx.respond(msg_text, reply_markup=keyboard)

    @command.filters(filters.private)
    async def cmd_setpic(self, ctx: command.Context):
        arg = ctx.input
        if not validators.url(arg):
            await ctx.respond("Please make sure the url of pic is validate")
            return
        msg = await self.get_msg(ctx.chat.id)
        self.log.debug("Message %s", msg)
        if not msg:
            msg = {}
        msg.update({"pic": arg})
        await self.save_msg(ctx.chat.id, msg)
        await ctx.respond("Message image set successfully.")

    @command.filters(filters.private)
    async def cmd_setbtn(self, ctx: command.Context):
        args = ctx.input.strip().split(" ")
        if len(args) != 2:
            await ctx.respond(
                "Please make sure the args is similar like /setbtn <btn-text> <btn-url>"
            )
            return
        if not validators.url(args[1]):
            await ctx.respond("Please make sure the url is validate")
            return

        btn = {"text": args[0], "url": args[1]}
        msg = await self.get_msg(ctx.chat.id)
        self.log.debug("Message %s", msg)
        if not msg:
            msg = {}
        msg.update({"btn": btn})
        await self.save_msg(ctx.chat.id, msg)
        await ctx.respond("Message button set successfully.")

    @command.filters(filters.private)
    async def cmd_setdesc(self, ctx: command.Context):
        msg = await self.get_msg(ctx.chat.id)
        self.log.debug("Message %s", msg)
        if not msg:
            msg = {}
        msg.update({"is_desc": 1})
        await self.save_msg(ctx.chat.id, msg)
        await ctx.respond("Please reply send me the text you want to push to")

    @listener.filters(filters.private)
    async def on_message(self, message: Message) -> None:
        msg = await self.get_msg(message.chat.id)
        self.log.debug("Message %s", msg)
        if not msg:
            return
        if not msg.get("is_desc"):
            return

        if message.text.startswith("/"):
            return

        # TODO: need to check with message.text length to for message with pic
        msg.update({"desc": message.text, "is_desc": 0})
        await self.save_msg(message.chat.id, msg)
        await self.bot.client.send_message(
            message.chat.id, "Message content set successfully."
        )

    @command.filters(filters.private)
    async def cmd_genurl(self, ctx: command.Context) -> Optional[str]:
        args = ctx.input.split(" ")
        if len(args) == 1:  # project
            return util.misc.generate_project_detail_link(int(args[0]), self.bot.uid)
        elif len(args) == 2:  # task
            return util.misc.generate_luckydraw_link(
                int(args[0]), int(args[1]), self.bot.uid
            )

    @command.filters(filters.private)
    async def cmd_yukisp(self, ctx: command.Context) -> Optional[str]:
        chat_id = ctx.chat.id
        if not is_whitelist(chat_id):
            self.log.warning("Not admin for yukix")
            return None

        msg = await self.bot.client.send_poll(
            chat_id, "Is this a poll question?", ["Yes", "No", "Maybe"]
        )
        self.log.debug("Poll answer msg: %s", msg)

    @command.filters(filters.private)
    async def cmd_yukiep(self, ctx: command.Context) -> Optional[str]:
        chat_id = ctx.chat.id
        if not is_whitelist(chat_id):
            self.log.warning("Not admin for yukix")
            return None
        msg_id = ctx.input
        poll = await self.bot.client.stop_poll(chat_id, int(msg_id))
        self.log.debug("Poll result in stop: %s", poll)

        return str(poll)

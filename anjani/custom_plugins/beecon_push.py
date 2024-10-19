from typing import ClassVar

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from anjani import command, orm, plugin, util


class BeeconPushPlugin(plugin.Plugin):
    name: ClassVar[str] = "Beecon Message Push Plugin"
    helpable: ClassVar[bool] = False

    mysql: util.db.MysqlPoolClient
    mydb: orm.AsyncSession

    async def on_load(self) -> None:
        self.mysql = util.db.MysqlPoolClient.init_from_env()
        self.mydb = orm.AsyncSession(self.bot.myengine)

    async def on_stop(self) -> None:
        await self.mysql.close()

    async def on_start(self, _: int) -> None:
        await self.mysql.connect()
        await self.mydb.flush()

    @command.filters(filters.private)
    async def cmd_grayt(self, ctx: command.Context) -> str | None:
        chat_id = ctx.chat.id
        if not util.misc.is_whitelist(chat_id):
            self.log.warning("Not admin for gray test command")
            return None
        if not ctx.input:
            self.log.warning("No args for grayt")
            return None
        (pid, tid, lang) = ctx.input.split(" ")
        users = await self.mysql.get_passive_user()
        if not users:
            self.log.warning("No passive user found")
            return None

        luckydraw_share = await orm.LuckydrawShare.get_share_info(
            self.mydb, pid, tid, lang
        )

        if not luckydraw_share:
            self.log.warning("Not luckydraw share info found for %s", ctx.input)
            return None

        pic = luckydraw_share.pics
        msg = luckydraw_share.des
        btn_txt = luckydraw_share.btn_desc[0]["text"]
        url = util.misc.generate_luckydraw_link(int(pid), int(tid), self.bot.uid)
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton(text=btn_txt, url=url)]])

        self.log.debug("graytest luckydraw info: %s", luckydraw_share)

        for u in users:
            try:
                user_chat_id = int(u[0])
                await self.bot.client.send_photo(
                    chat_id=user_chat_id, photo=pic, caption=msg, reply_markup=buttons
                )
                self.log.inof("Sent gray test to user %s", user_chat_id)
            except Exception as e:
                self.log.warning("Sent gray test to user %s error: %s", user_chat_id, e)

    @command.filters(filters.private)
    async def cmd_pushxbind(self, ctx: command.Context) -> str | None:
        chat_id = ctx.chat.id
        if not util.misc.is_whitelist(chat_id):
            self.log.warning("Not admin for pushxbind command")
            return None
        if not ctx.input:
            self.log.warning("No args for pushxbind")
            return None

        (pid, tid, lang) = ctx.input.split(" ")
        luckydraw_share = await orm.LuckydrawShare.get_share_info(
            self.mydb, int(pid), int(tid), lang
        )
        self.log.debug("pushxbind command luckydraw share: %s", luckydraw_share)

        if not luckydraw_share:
            self.log.warning("No luckydraw share info for %s", ctx.input)
            return None

        pic = luckydraw_share.pics
        msg = luckydraw_share.des
        btn_txt = luckydraw_share.btn_desc["text"]
        btn_url = util.misc.generate_luckydraw_link(pid, tid, self.bot.uid)
        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=btn_txt, url=btn_url)]]
        )

        users = await self.mysql.get_x_users()
        self.log.debug("pushxbind: users %s", users)

        if not users:
            self.log.warning("No x users")
            return None

        for u in users:
            try:
                tg_id = int(u[0])
                # for test purpose
                if tg_id != 6812515288:
                    continue
                await self.bot.send_photo(
                    chat_id=tg_id, photo=pic, caption=msg, reply_markup=buttons
                )
                self.log.info("Sent message to x binder %s", tg_id)
            except Exception as e:
                self.log.warning("Sent to x binder %s info failed: %s", tg_id, e)

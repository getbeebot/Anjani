""" Main Anjani plugins """
# Copyright (C) 2020 - 2023  UserbotIndo Team, <https://github.com/userbotindo.git>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import asyncio
import re
from hashlib import sha256
from typing import TYPE_CHECKING, Any, ClassVar, List, Optional

from functools import partial
from pymongo.errors import PyMongoError

from aiopath import AsyncPath
from bson.binary import Binary
from pyrogram.enums.chat_type import ChatType
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    MessageDeleteForbidden,
    MessageNotModified,
)
from pyrogram.raw.functions.updates.get_state import GetState
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from anjani import command, filters, listener, plugin, util
from anjani.util.twa import TWA
from .language import LANG_FLAG

if TYPE_CHECKING:
    from .rules import Rules


class Main(plugin.Plugin):
    """Bot main Commands"""

    name: ClassVar[str] = "Main"

    bot_name: str
    db: util.db.AsyncCollection
    lang_db: util.db.AsyncCollection
    _db_stream: asyncio.Task[None]

    def _start_db_stream(self) -> None:
        try:
            if not self._db_stream.done():
                self._db_stream.cancel()
        except AttributeError:
            pass
        self._db_stream = self.bot.loop.create_task(self.db_stream())
        self._db_stream.add_done_callback(
            partial(self.bot.loop.call_soon_threadsafe, self._db_stream_callback)
        )

    def _db_stream_callback(self, future: asyncio.Future) -> None:
        try:
            future.result()
        except asyncio.CancelledError:
            pass
        except PyMongoError as e:
            self.log.error("MongoDB error:", exc_info=e)
            self._start_db_stream()

    async def db_stream(self) -> None:
        async with self.lang_db.watch(full_document="updateLookup") as cursor:
            async for change in cursor:
                document = change["fullDocument"]
                self.bot.chats_languages[document["chat_id"]] = document["language"]

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection("SESSION")
        self.lang_db = self.bot.db.get_collection("LANGUAGE")
        self._start_db_stream()

    async def on_start(self, _: int) -> None:
        self.bot_name = (
            self.bot.user.first_name + self.bot.user.last_name
            if self.bot.user.last_name
            else self.bot.user.first_name
        )

        restart = await self.db.find_one({"_id": 5})
        if restart is not None:
            rs_time: Optional[int] = restart.get("time")
            rs_chat_id: Optional[int] = restart.get("status_chat_id")
            rs_message_id: Optional[int] = restart.get("status_message_id")

            # Delete data first in case message editing fails
            await self.db.delete_one({"_id": 5})

            # Bail out if we're missing necessary values
            if rs_chat_id is None or rs_message_id is None or rs_time is None:
                return

            duration = util.time.usec() - rs_time
            duration_str = util.time.format_duration_us(duration)
            __, status_msg = await asyncio.gather(
                self.bot.log_stat("downtime", value=duration),
                self.bot.client.get_messages(rs_chat_id, rs_message_id),
            )
            if isinstance(status_msg, List):
                status_msg = status_msg[0]

            self.bot.log.info(f"Bot downtime {duration_str}")
            await self.send_to_log(
                f"Bot downtime {duration_str}.", reply_to_message_id=status_msg.id
            )
            try:
                await status_msg.delete()
            except MessageDeleteForbidden:
                pass
        else:
            await self.send_to_log("Starting system...")

    async def on_stop(self) -> None:
        async with asyncio.Lock():
            file = AsyncPath("anjani/anjani.session")
            if not await file.exists():
                return

            data = await self.bot.client.invoke(GetState())
            await self.db.update_one(
                {"_id": sha256(self.bot.config.BOT_TOKEN.encode()).hexdigest()},
                {
                    "$set": {
                        "session": Binary(await file.read_bytes()),
                        "date": data.date,
                        "pts": data.pts,
                        "qts": data.qts,
                        "seq": data.seq,
                    }
                },
                upsert=True,
            )

            status_msg = await self.send_to_log("Shutdowning system...")
            self.bot.log.info("Preparing to shutdown...")
            if not status_msg:
                return

            await self.db.update_one(
                {"_id": 5},
                {
                    "$set": {
                        "status_chat_id": status_msg.chat.id,
                        "status_message_id": status_msg.id,
                        "time": util.time.usec(),
                    }
                },
                upsert=True,
            )
            # for language db
            self._db_stream.cancel()

    async def send_to_log(self, text: str, *args: Any, **kwargs: Any) -> Optional[Message]:
        if not self.bot.config.LOG_CHANNEL:
            return
        return await self.bot.client.send_message(
            int(self.bot.config.LOG_CHANNEL), text, *args, **kwargs
        )

    async def help_builder(self, chat_id: int) -> List[List[InlineKeyboardButton]]:
        """Build the help button"""
        plugins: List[InlineKeyboardButton] = []
        for plug in list(self.bot.plugins.values()):
            if plug.helpable:
                plugins.append(
                    InlineKeyboardButton(
                        await self.text(chat_id, f"{plug.name.lower()}-button"),
                        callback_data=f"help_plugin({plug.name.lower()})",
                    )
                )
        plugins.sort(key=lambda kb: kb.text)

        pairs = [plugins[i * 3 : (i + 1) * 3] for i in range((len(plugins) + 3 - 1) // 3)]
        pairs.append([InlineKeyboardButton("✗ Close", callback_data="help_close")])

        return pairs

    @listener.filters(filters.regex(r"help_(.*)"))
    async def on_callback_query(self, query: CallbackQuery) -> None:
        """Bot helper button"""
        match = query.matches[0].group(1)
        chat = query.message.chat

        if match == "back":
            keyboard = await self.help_builder(chat.id)
            try:
                await query.edit_message_text(
                    await self.text(chat.id, "help-pm", self.bot_name),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except MessageNotModified:
                pass
        elif match == "close":
            try:
                await query.message.delete()
            except MessageDeleteForbidden:
                await query.answer("I can't delete the message")
        elif match:
            plug = re.compile(r"plugin\((\w+)\)").match(match)
            if not plug:
                raise ValueError("Unable to find plugin name")

            text_lang = await self.text(
                chat.id, f"{plug.group(1)}-help", username=self.bot.user.username
            )
            text = (
                f"Here is the help for the **{plug.group(1).capitalize()}** "
                f"plugin:\n\n{text_lang}"
            )
            try:
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    await self.text(chat.id, "back-button"),
                                    callback_data="help_back",
                                )
                            ]
                        ]
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except MessageNotModified:
                pass

    async def cmd_start(self, ctx: command.Context) -> Optional[str]:
        """Bot start command"""
        chat = ctx.chat

        if chat.type == ChatType.PRIVATE:  # only send in PM's
            if ctx.input and ctx.input == "help":
                keyboard = await self.help_builder(chat.id)
                await ctx.respond(
                    await self.text(chat.id, "help-pm", self.bot_name),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return None

            if ctx.input and ctx.input == "language":
                lang = self.bot.chats_languages.get(chat.id, "en")
                if lang == "en":
                    await asyncio.gather(
                        self.switch_lang(chat.id, "zh"),
                        ctx.respond(await self.text(chat.id, "language-set-succes", LANG_FLAG["zh"])),
                    )
                else:
                    await asyncio.gather(
                        self.switch_lang(chat.id, "en"),
                        ctx.respond(await self.text(chat.id, "language-set-succes", LANG_FLAG["en"])),
                    )

            if ctx.input:
                rules_re = re.compile(r"rules_(.*)")
                if rules_re.search(ctx.input):
                    plug: "Rules" = self.bot.plugins["Rules"]  # type: ignore
                    try:
                        return await plug.start_rules(ctx)
                    except (ChannelInvalid, ChannelPrivate):
                        return await self.text(chat.id, "rules-channel-invalid")

                help_re = re.compile(r"help_(.*)").match(ctx.input)
                if help_re:
                    text_lang = await self.text(chat.id, f"{help_re.group(1)}-help")
                    text = (
                        f"Here is the help for the **{ctx.input.capitalize().replace('help_', '')}** "
                        f"plugin:\n\n{text_lang}"
                    )
                    await ctx.respond(
                        text,
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        await self.text(chat.id, "back-button"),
                                        callback_data="help_back",
                                    )
                                ]
                            ]
                        ),
                        disable_web_page_preview=True,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return


            buttons: List[InlineKeyboardButton] = []

            group_buttons = []
            twa = TWA()
            group_projects = await twa.get_user_owned_groups(chat.id)
            if not group_projects:
                pass
            else:
                line_buttons = []
                for row in group_projects:
                    (project_id, group_name) = row
                    project_link = twa.generate_project_detail_link(project_id)
                    group_button = InlineKeyboardButton(
                        text=group_name,
                        url=project_link
                    )
                    line_buttons.append(group_button)
                # Two group button one line
                group_buttons = [line_buttons[i * 2: (i+1) * 2] for i in range((len(line_buttons) + 2 - 1) // 2)]

            buttons.extend(group_buttons)

            # permission = [
            #     # "change_info",
            #     "post_messages",
            #     "edit_messages",
            #     "delete_messages",
            #     "restrict_members",
            #     "invite_users",
            #     "pin_messages",
            #     # "promote_members",
            #     "manage_video_chats",
            #     "manage_chat",
            # ]

            faq_link = os.getenv("FAQ", "beecon.me")
            channel_link = os.getenv("CHANNEL", "beecon.me")

            buttons.extend([
                [
                    InlineKeyboardButton(  # Add bot as Admin button
                        text=await self.text(chat.id, "add-to-group-button"),
                        url=f"t.me/{self.bot.user.username}?startgroup=true",
                    ),
                ],
                [
                    InlineKeyboardButton(  # FAQ button
                        text = await self.text(chat.id, "faq-button"),
                        url=faq_link,
                    ),
                    InlineKeyboardButton(
                        text=await self.text(chat.id, "channel-button"),
                        url=channel_link,
                    )

                ],
                [
                    InlineKeyboardButton(
                        text=await self.text(chat.id, "language-button"),
                        url=f"t.me/{self.bot.user.username}?start=language",
                    ),
                ],
            ])
            if "Canonical" in self.bot.plugins:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=await self.text(chat.id, "status-page-button"),
                            url="https://status.userbotindo.com",
                        ),
                        InlineKeyboardButton(
                            text=await self.text(chat.id, "dashboard-button"),
                            url="https://userbotindo.com/dashboard",
                        ),
                    ]
                )

            await ctx.respond(
                await self.text(chat.id, "start-pm", self.bot_name),
                reply_markup=InlineKeyboardMarkup(buttons),
                disable_web_page_preview=False,
                parse_mode=ParseMode.MARKDOWN,
            )
            return None

        # group start message
        project_link = await TWA.get_chat_project_link(chat.id)

        if (project_link == TWA.TWA_LINK ):
            return None

        buttons = [
            [
                InlineKeyboardButton(
                    text=await self.text(chat.id, "create-project-button"),
                    url=project_link
                )
            ]
        ]

        twa = TWA()
        tasks = await twa.get_chat_tasks(chat.id)
        participants = await twa.get_chat_activity_participants(chat.id)
        if tasks and participants:
            group_context = await self.text(chat.id, "group-start", noformat=True)
            group_start_msg = group_context.format(tasks=tasks, participants=participants)

        else:
            group_start_msg = "We just initiate, just give us some time..."

        await ctx.respond(
            group_start_msg,
            photo="https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )
        return None

    async def switch_lang(self, chat_id: int, language: str) -> None:
        await self.lang_db.update_one(
            {"chat_id": int(chat_id)},
            {"$set": {"language": language}},
            upsert=True,
        )

    async def cmd_help(self, ctx: command.Context) -> None:
        """Bot plugins helper"""
        chat = ctx.chat

        if chat.type != ChatType.PRIVATE:  # only send in PM's
            await ctx.respond(
                await self.text(chat.id, "help-chat"),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text=await self.text(chat.id, "help-chat-button"),
                                url=f"t.me/{self.bot.user.username}?start=help",
                            )
                        ]
                    ]
                ),
            )
            return

        keyboard = await self.help_builder(chat.id)
        await ctx.respond(
            await self.text(chat.id, "help-pm", self.bot_name),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # async def cmd_donate(self, ctx: command.Context) -> None:
    #     """Bot donate command"""
    #     await ctx.respond(
    #         await self.text(ctx.chat.id, "donate"),
    #         disable_web_page_preview=True,
    #     )

    async def cmd_markdownhelp(self, ctx: command.Context) -> None:
        """Send markdown helper."""
        await ctx.respond(
            await self.text(ctx.chat.id, "markdown-helper", self.bot_name),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    @command.filters(aliases=["fillinghelp"])
    async def cmd_formathelp(self, ctx: command.Context) -> None:
        """Send markdown help."""
        await ctx.respond(
            await self.text(ctx.chat.id, "filling-format-helper", noformat=True),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

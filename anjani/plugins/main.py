"""Main Anjani plugins"""
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

import asyncio
import json
import os
import re
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar, List, Optional

from pymongo.errors import PyMongoError
from pyrogram.enums.chat_type import ChatType
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    MessageDeleteForbidden,
    MessageNotModified,
)
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from anjani import command, filters, listener, orm, plugin, util
from anjani.util.project_config import BotNotificationConfig

from .language import LANG_FLAG

if TYPE_CHECKING:
    from .rules import Rules


class Main(plugin.Plugin):
    """Bot main Commands"""

    name: ClassVar[str] = "Main"

    mysql: util.db.MysqlPoolClient
    mydb: orm.AsyncSession

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
        self.mysql = util.db.MysqlPoolClient.init_from_env()
        await self.mysql.connect()

        self.mydb = orm.AsyncSession(self.bot.myengine)

        self.db = self.bot.db.get_collection("SESSION")
        self.lang_db = self.bot.db.get_collection("LANGUAGE")
        self._start_db_stream()

    async def on_start(self, _: int) -> None:
        self.bot_name = (
            self.bot.user.first_name + self.bot.user.last_name
            if self.bot.user.last_name
            else self.bot.user.first_name
        )

        await self.mydb.flush()

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

            await self.mysql.close()

    async def send_to_log(
        self, text: str, *args: Any, **kwargs: Any
    ) -> Optional[Message]:
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

        pairs = [
            plugins[i * 3 : (i + 1) * 3] for i in range((len(plugins) + 3 - 1) // 3)
        ]
        pairs.append([InlineKeyboardButton("✗ Close", callback_data="help_close")])

        return pairs

    async def project_builder(
        self, chat_id: int, is_link: bool = False
    ) -> List[List[InlineKeyboardButton]]:
        projects: List[List[InlineKeyboardButton]] = []
        user_id = await self.mysql.get_user_id(chat_id)
        if not user_id:
            return
        payloads = {
            "botId": self.bot.uid,
            "user_id": user_id,
        }
        try:
            user_projects = await self.bot.apiclient.get_user_projects(payloads)
        except Exception as e:
            self.log.warning("Get user %s projects error %s", user_id, e)

        if not user_projects:
            return
        buttons = []
        for project in user_projects:
            (project_id, project_name) = project
            if is_link:
                project_link = util.misc.generate_project_detail_link(
                    project_id, self.bot.uid
                )
                project_button = InlineKeyboardButton(
                    text=project_name, url=project_link
                )
            else:
                project_button = InlineKeyboardButton(
                    text=project_name, callback_data=f"help_project_{project_id}"
                )
            buttons.append(project_button)
        projects = [
            buttons[i * 2 : (i + 1) * 2] for i in range((len(buttons) + 2 - 1) // 2)
        ]
        return projects

    async def project_config_builder(
        self, project_id: int
    ) -> List[List[InlineKeyboardButton]]:
        configs: List[List[InlineKeyboardButton]] = []

        project_config = await self.get_project_config(project_id)
        # if there's no redis cache, query mysql db
        if not project_config:
            project_config = await BotNotificationConfig.get_project_config(project_id)

        buttons: List[InlineKeyboardButton] = []
        for k, v in project_config.__dict__.items():
            # ignore project_id, ovduration attribute
            if k == "project_id" or k == "ovduration" or k == "verify" or k == "nourl":
                continue

            btn_text = await self.text(None, f"{k}-{v}-button")
            btn = InlineKeyboardButton(
                text=btn_text, callback_data=f"help_config_{project_id}_{k}_{v}"
            )
            buttons.append(btn)

        # ensure the config saved to redis
        await self.update_project_config(project_config)

        configs = [
            buttons[i * 2 : (i + 1) * 2] for i in range((len(buttons) + 2 - 1) // 2)
        ]
        return configs

    async def duration_config_builder(
        self, project_id: int
    ) -> List[List[InlineKeyboardButton]]:
        project_config = await self.get_project_config(project_id)
        if not project_config:
            project_config = BotNotificationConfig(project_id)

        one_hour = 3600
        durations = [one_hour * i for i in range(1, 25)]
        btns: List[InlineKeyboardButton] = []
        for hr, secs in enumerate(durations):
            btn_text = ""
            if secs == project_config.ovduration:
                btn_text += "✔️ "
            btn_text += str(hr + 1)
            btn = InlineKeyboardButton(
                text=btn_text,
                callback_data=f"help_config_{project_id}_ovduration_{secs}",
            )
            btns.append(btn)

        return [btns[i * 3 : (i + 1) * 3] for i in range((len(btns) + 3 - 1) // 3)]

    async def get_project_config(self, project_id: int):
        query_key = f"project_config_{project_id}"
        json_data = await self.bot.redis.get(query_key)
        if json_data:
            return BotNotificationConfig.from_json(json_data.decode("utf-8"))

    async def update_project_config(self, config: BotNotificationConfig):
        query_key = f"project_config_{config.project_id}"
        value = json.dumps(config.__dict__).encode("utf-8")
        await self.bot.redis.set(query_key, value)

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
        elif match == "addme":
            group_btn_text = await self.text(None, "add-me-to-group", noformat=True)
            channel_btn_text = await self.text(None, "add-me-to-channel", noformat=True)
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=group_btn_text,
                            url=f"t.me/{self.bot.user.username}?startgroup=true",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=channel_btn_text,
                            url=f"t.me/{self.bot.user.username}?startchannel=true",
                        )
                    ],
                ]
            )
            group_or_channel = await self.text(None, "group-or-channel", noformat=True)
            await self.bot.client.send_message(
                chat.id,
                group_or_channel,
                reply_markup=buttons,
                parse_mode=ParseMode.MARKDOWN,
            )
        elif match == "forkme":
            btn_text = await self.text(None, "forkme-contact-button", noformat=True)
            btn_link = await self.text(None, "forkme-contact-link", noformat=True)
            forkme_desc = await self.text(None, "forkme-description", noformat=True)

            button = InlineKeyboardMarkup(
                [[InlineKeyboardButton(text=btn_text, url=btn_link)]]
            )

            await self.bot.client.send_message(
                chat.id,
                forkme_desc,
                reply_markup=button,
                parse_mode=ParseMode.MARKDOWN,
            )
        elif match.startswith("project"):
            project = re.compile(r"project_([0-9]+|overview)").match(match)
            if not project:
                raise ValueError("Unable to find project")

            match_p = project.group(1)
            if match_p == "overview":
                user_id = query.from_user.id
                project_btns = await self.project_builder(user_id)
                start_btns = await self.build_start_button()
                if start_btns:
                    project_btns.extend(start_btns)

                keyboard = InlineKeyboardMarkup(project_btns)
                try:
                    await query.edit_message_text(
                        text=await self.text(None, "start-pm", self.bot.user.username),
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except MessageNotModified:
                    pass
            elif match_p.isdigit():
                project_id = int(project.group(1))
                project_link = util.misc.generate_project_detail_link(
                    project_id, self.bot.uid
                )

                (project_name, project_desc) = await self.mysql.get_project_brief(
                    project_id
                )

                text = f"**Community**: {project_name}\n"
                if project_desc:
                    text += f"**Description**: {project_desc}"

                keyboard = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(text="Edit", url=project_link),
                            InlineKeyboardButton(
                                text="Bot Notification",
                                callback_data=f"help_config_{project_id}",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                text=await self.text(None, "back-button"),
                                callback_data="help_project_overview",
                            )
                        ],
                    ]
                )
                try:
                    # sync project config to db every time go to project breif page
                    project_config = await self.get_project_config(project_id)
                    if project_config:
                        await project_config.update_or_create()
                    await query.edit_message_text(
                        text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
                    )
                except MessageNotModified:
                    pass
            else:
                raise ValueError("Unable to find project")
        elif match.startswith("config"):
            c_match = re.compile(r"config_(\d+)_?([a-zA-Z]+)?_?(\d+)?").match(match)
            if not c_match:
                raise ValueError("Unable to find project config")

            project_id = int(c_match.group(1))

            project_config = await self.get_project_config(project_id)
            if not project_config:
                project_config = BotNotificationConfig(project_id)
                await self.update_project_config(project_config)

            self.log.debug("Debugging config: %s", c_match)

            if c_match.group(2) and c_match.group(3):
                attr_key = c_match.group(2)

                if attr_key == "ovduration":
                    ovduration = c_match.group(3)
                    setattr(project_config, attr_key, int(ovduration))
                    await self.update_project_config(project_config)

                    duration_btns = await self.duration_config_builder(project_id)
                    duration_btns.append(
                        [
                            InlineKeyboardButton(
                                text=await self.text(None, "back-button"),
                                callback_data=f"help_config_{project_id}",
                            )
                        ]
                    )
                    try:
                        text = "Please choose duration:"
                        keyboard = InlineKeyboardMarkup(duration_btns)
                        await query.edit_message_text(text=text, reply_markup=keyboard)
                        return
                    except Exception as e:
                        self.log.error(
                            "Duration button callback: %s error: %s", c_match, e
                        )

                cur_value = getattr(project_config, attr_key)

                setattr(project_config, attr_key, cur_value ^ 1)

                await self.update_project_config(project_config)

            config_btns = await self.project_config_builder(project_id)
            try:
                config_btns.append(
                    [
                        InlineKeyboardButton(
                            text=await self.text(None, "back-button"),
                            callback_data=f"help_project_{project_id}",
                        )
                    ]
                )

                (project_name, project_desc) = await self.mysql.get_project_brief(
                    project_id
                )

                text = f"**Community**: {project_name}\n"
                if project_desc:
                    text += f"**Description**: {project_desc}"

                keyboard = InlineKeyboardMarkup(config_btns)
                await query.edit_message_text(text=text, reply_markup=keyboard)
            except Exception as e:
                self.log.error("Config callback error: %s", e)

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
                                    text=await self.text(None, "back-button"),
                                    callback_data="help_back",
                                )
                            ]
                        ]
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except MessageNotModified:
                pass

    async def build_start_button(self) -> List[List[InlineKeyboardButton]]:
        btns = []
        btns.append(
            [
                InlineKeyboardButton(
                    text=await self.text(None, "add-to-group-button"),
                    callback_data="help_addme",
                )
            ]
        )

        daily_gifts_link = os.getenv("DAILY_GIFTS")
        if daily_gifts_link:
            gift_btns = [
                InlineKeyboardButton(
                    text=await self.text(None, "daily-gifts-button"),
                    url=daily_gifts_link,
                )
            ]
            airdrop_link = os.getenv("AIRDROP_HUB")
            if airdrop_link:
                gift_btns.append(
                    InlineKeyboardButton(text="🪂 Airdrop Hub", url=airdrop_link)
                )
                pass
            btns.append(gift_btns)

        social_btns = []
        faq_link = os.getenv("FAQ")
        if faq_link:
            social_btns.append(
                InlineKeyboardButton(
                    text=await self.text(None, "faq-button"), url=faq_link
                )
            )

        channel_link = os.getenv("CHANNEL")
        if channel_link:
            social_btns.append(
                InlineKeyboardButton(
                    text=await self.text(None, "channel-button"), url=channel_link
                )
            )

        x_username = os.getenv("X_USERNAME")
        if x_username:
            social_btns.append(
                InlineKeyboardButton(text="𝕏", url=f"https://x.com/{x_username}")
            )

        if social_btns:
            btns.append(social_btns)

        white_list_bot = [7152140916, 6802454608, 6872924441]
        if self.bot.uid in white_list_bot:
            btns.append(
                [
                    InlineKeyboardButton(
                        text=await self.text(None, "forkme-button"),
                        callback_data="help_forkme",
                    ),
                    InlineKeyboardButton(
                        text=await self.text(None, "ad-svc-button"),
                        url=await self.text(None, "forkme-contact-link"),
                    ),
                ]
            )
        return btns

    async def cmd_start(self, ctx: command.Context) -> Optional[str]:
        """Bot start command"""
        chat = ctx.chat

        guide_img_link = os.getenv(
            "GUIDE_IMG",
            "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/guide2.png",
        )
        engage_img_link = os.getenv(
            "ENGAGE_IMG",
            "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png",
        )

        if chat.type == ChatType.PRIVATE:  # only send in PM's
            # for start bot task
            try:
                start_record = orm.TgUserStartBot(chat_id=chat.id, bot_id=self.bot.uid)
                await start_record.save(self.mydb)
            except Exception as e:
                self.log.warning("Saving start bot records error: %s", e)

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
                        ctx.respond(
                            await self.text(
                                chat.id, "language-set-succes", LANG_FLAG["zh"]
                            )
                        ),
                    )
                else:
                    await asyncio.gather(
                        self.switch_lang(chat.id, "en"),
                        ctx.respond(
                            await self.text(
                                chat.id, "language-set-succes", LANG_FLAG["en"]
                            )
                        ),
                    )

            if ctx.input and ctx.input == "drawguide":
                self.log.info("Input: %s", ctx.input)
                await ctx.respond(text=await self.text(None, "draw-guide"))
                return None

            if ctx.input and ctx.input != "true":
                self.log.info("Start inputs %s", ctx.input)
                try:
                    args = util.misc.decode_args(ctx.input)
                except Exception:
                    self.log.warning("args not able to decode")
                    args = None

                if isinstance(args, list):
                    claim_reply = await self.text(None, "claim-reply", noformat=True)
                    await ctx.respond(claim_reply)
                    group_id = args[0]
                    invite_link = args[1]
                    bot_id = self.bot.uid
                    payloads = {
                        "chatId": group_id,
                        "tgUserId": chat.id,
                        "inviteLink": invite_link,
                        "botId": bot_id,
                    }

                    awards = await self.bot.apiclient.distribute_join_rewards(payloads)
                    if awards:
                        reward_btn_text = await self.text(
                            None, "rewards-msg-button", noformat=True
                        )
                        project_id = await self.mysql.get_chat_project_id(
                            group_id, bot_id
                        )
                        project_url = util.misc.generate_project_detail_link(
                            project_id, bot_id
                        )

                        project_btn = InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        text=reward_btn_text, url=project_url
                                    )
                                ]
                            ]
                        )
                        reply_text = await self.text(
                            None,
                            "rewards-claimed",
                            mention=ctx.author.mention,
                            rewards=awards,
                        )
                        await self.bot.client.send_message(
                            chat_id=group_id,
                            text=reply_text,
                            reply_markup=project_btn,
                            parse_mode=ParseMode.MARKDOWN,
                        )
                        return None

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

            keyboard = []
            project_buttons = await self.project_builder(chat.id)
            if project_buttons:
                keyboard.extend(project_buttons)

            start_btns = await self.build_start_button()
            if start_btns:
                keyboard.extend(start_btns)

            try:
                await ctx.respond(
                    await self.text(chat.id, "start-pm", self.bot.user.username),
                    photo=guide_img_link,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                self.log.error("/start command not respond correctly: %s", e)
                await util.alert.send_alert(
                    f"/start in private chat({chat.id}) not respond", str(e), "critical"
                )
            return None

        # group start message
        bot_id = self.bot.uid
        is_exist = await self.mysql.get_chat_project_id(chat.id, bot_id)

        project_id = is_exist
        counter = 0
        while counter < 5 and not project_id:
            await asyncio.sleep(1)
            counter += 1
            project_id = await self.mysql.get_chat_project_id(chat.id, bot_id)

        # no project for group, error exception
        if not project_id:
            return None

        project_link = util.misc.generate_project_detail_link(project_id, self.bot.uid)

        buttons = [
            [
                InlineKeyboardButton(
                    text=await self.text(chat.id, "create-project-button"),
                    url=project_link,
                )
            ]
        ]
        try:
            mysql_client = util.db.MysqlPoolClient.init_from_env()
            tasks = await mysql_client.get_project_tasks(project_id)
            participants = await mysql_client.get_project_participants(project_id)
        except Exception:
            pass
        finally:
            await mysql_client.close()
            del mysql_client

        self.log.debug(
            "In start command, project %s has %s tasks and %s participants",
            project_id,
            tasks,
            participants,
        )

        if tasks and participants:
            group_context = await self.text(chat.id, "group-start-pm", noformat=True)
            group_start_msg = group_context.format(
                tasks=tasks, participants=participants
            )
        elif tasks:
            group_start_msg = await self.text(
                chat.id, "group-no-participant-exception", tasks
            )
            pass
        else:
            group_start_msg = await self.text(
                chat.id, "group-no-task-exception", noformat=True
            )
            await ctx.respond(group_start_msg)
            return

        try:
            await ctx.respond(
                group_start_msg,
                photo=engage_img_link,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            self.log.error("/start command in group not response: %s", e)
            await util.alert.send_alert(
                f"/start in group({chat.id}) not respond", str(e), "critical"
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

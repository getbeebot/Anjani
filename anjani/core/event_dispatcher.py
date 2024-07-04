"""Anjani event dispatcher"""

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
import bisect
from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Any, MutableMapping, MutableSequence, Optional, Tuple

import aiofiles.os as aio_os
import json

from pyrogram import raw
from pyrogram.filters import Filter
from pyrogram.raw import functions
from pyrogram.types import (
    CallbackQuery, InlineQuery,
    Message, InlineKeyboardButton,
    InlineKeyboardMarkup,
    Chat, ChatMemberUpdated, User
)
from pyrogram.enums import ChatType
from pyrogram.enums.parse_mode import ParseMode

from anjani import plugin, util
from anjani.error import EventDispatchError
from anjani.listener import Listener, ListenerFunc
from anjani.util.misc import StopPropagation

from anjani.language import get_template

import boto3

import websockets
from websockets import client

from .anjani_mixin_base import MixinBase
from .metrics import EventCount, EventLatencySecond, UnhandledError

if TYPE_CHECKING:
    from .anjani_bot import Anjani

EventType = (
    CallbackQuery,
    InlineQuery,
    Message,
)


def _get_event_data(event: Any) -> MutableMapping[str, Any]:
    if isinstance(event, Message):
        return {
            "chat_title": event.chat.title,
            "chat_id": event.chat.id,
            "user_name": event.from_user.first_name
            if event.from_user
            else event.sender_chat.title,
            "user_id": event.from_user.id if event.from_user else event.sender_chat.id,
            "input": event.text,
        }
    if isinstance(event, CallbackQuery):
        return {
            "chat_title": event.message.chat.title,
            "chat_id": event.message.chat.id,
            "user_name": event.from_user.first_name,
            "user_id": event.from_user.id,
            "input": event.data,
        }
    if isinstance(event, InlineQuery):
        return {
            "user_name": event.from_user.first_name,
            "user_id": event.from_user.id,
            "input": event.query,
        }
    return {}


def _unpack_args(args: Tuple[Any, ...]) -> str:
    """Unpack arguments into a string for logging purposes."""
    return ", ".join([str(arg) for arg in args])


class EventDispatcher(MixinBase):
    # Initialized during instantiation
    listeners: MutableMapping[str, MutableSequence[Listener]]
    api_prefix: str = os.getenv("API_URL", "https://api.getbeebot.com")

    def __init__(self: "Anjani", **kwargs: Any) -> None:
        # Initialize listener map
        self.listeners = {}

        # Propagate initialization to other mixins
        super().__init__(**kwargs)

    def register_listener(
        self: "Anjani",
        plug: plugin.Plugin,
        event: str,
        func: ListenerFunc,
        *,
        priority: int = 100,
        filters: Optional[Filter] = None,
    ) -> None:
        if (
            event in {"load", "start", "started", "stop", "stopped"}
            and filters is not None
        ):
            self.log.warning("Built-in Listener can't be use with filters. Removing...")
            filters = None

        if getattr(func, "_cmd_filters", None):
            self.log.warning(
                "@command.filters decorator only for CommandFunc. Filters will be ignored..."
            )

        if filters:
            self.log.debug(
                "Registering filter '%s' into '%s'", type(filters).__name__, event
            )

        listener = Listener(event, func, plug, priority, filters)

        if event in self.listeners:
            bisect.insort(self.listeners[event], listener)
        else:
            self.listeners[event] = [listener]

        self.update_plugin_events()

    def unregister_listener(self: "Anjani", listener: Listener) -> None:
        self.listeners[listener.event].remove(listener)
        # Remove list if empty
        if not self.listeners[listener.event]:
            del self.listeners[listener.event]

        self.update_plugin_events()

    def register_listeners(self: "Anjani", plug: plugin.Plugin) -> None:
        for event, func in util.misc.find_prefixed_funcs(plug, "on_"):
            done = True
            try:
                self.register_listener(
                    plug,
                    event,
                    func,
                    priority=getattr(func, "_listener_priority", 100),
                    filters=getattr(func, "_listener_filters", None),
                )
                done = True
            finally:
                if not done:
                    self.unregister_listeners(plug)

    def unregister_listeners(self: "Anjani", plug: plugin.Plugin) -> None:
        for lst in list(self.listeners.values()):
            for listener in lst:
                if listener.plugin == plug:
                    self.unregister_listener(listener)

    async def get_chat_link(self: "Anjani", chat: Chat) -> Optional[str]:
        link = ""
        try:
            if chat.username:
                link = f"https://t.me/{chat.username}"
            else:
                invite_link = await self.client.create_chat_invite_link(chat.id)
                link = invite_link.invite_link
        except Exception as e:
            self.log.warning("Can not link of chat %s (%s)", chat.title, chat.id)

        return link

    async def save_chat_info(self: "Anjani", chat: Chat) -> None:
        try:
            chat_link = await self.get_chat_link(chat)
            chat_type = 0
            if chat.type == ChatType.CHANNEL:
                chat_type = 1
            chat_id = chat.id
            chat_name = chat.title
            chat_info = {
                "chat_type": chat_type,
                "chat_id": chat_id,
                "chat_name": chat_name,
                "invite_link": chat_link,
                "bot_id": self.uid
            }
            self.log.info(f"Bot joining {chat.type} {chat_name}({chat_id}) {chat_link}")
            await self.mysql.update_chat_info(chat_info)
        except Exception as e:
            self.log.error("Update chat info error: %s", e)

    async def create_project_on_join(self: "Anjani", updated: ChatMemberUpdated) -> None:
        new_member = updated.new_chat_member
        chat = updated.chat

        if not new_member:
            return None

        if not chat:
            return None


        async def get_avatar_link(chat_id: int, file_id: str) -> Optional[str]:
            try:
                filename = f"C{chat_id}.jpg"
                filepath = os.path.join("downloads", filename)

                await self.client.download_media(file_id, file_name=f"../downloads/{filename}")
                s3 = boto3.client("s3", aws_access_key_id=self.config.AWS_AK, aws_secret_access_key=self.config.AWS_SK)
                s3.upload_file(filepath, self.config.AWS_S3_BUCKET, filename, ExtraArgs={"ContentType": "image/jpeg"})
                await aio_os.remove(filepath)
                return f"https://{self.config.AWS_S3_BUCKET}.s3.ap-southeast-1.amazonaws.com/{filename}"
            except Exception as e:
                self.log.error("Retrieving chat pic failed: %s", e)

        async def get_chat_description(chat_id) -> Optional[str]:
            try:
                chat = await self.client.get_chat(chat_id)
                if chat.description:
                    return chat.description
            except Exception as e:
                self.log.error("Retrieve chat (%s) description error: %s", chat_id, e)

        async def construct_payloads(user: User) -> dict:
            payloads = {}
            user_id = user.id
            user_name= user.username or None
            first_name = user.first_name
            last_name = user.last_name
            nick_name = first_name + ' ' + last_name if last_name else first_name

            avatar = None
            try:
                avatar = await get_avatar_link(user_id, user.photo.big_file_id)
            except Exception as e:
                self.log.warning("User %s (%s) does not have avatar: %s", first_name, user_id, e)

            payloads.update({
                "firstName": first_name,
                "lastName": last_name,
                "nickName": nick_name,
                "userName": user_name,
                "pic": avatar,
                "tgUserId": user_id,
                "botId": self.uid
            })
            return payloads

        # default is group type: 0 for group, 1 for channel
        chat_type = 0
        if chat.type == ChatType.CHANNEL:
            chat_type = 1

        guide_img_link = await get_template("guide-img")
        add_me_btn_text = await get_template("add-to-group-button")
        usage_guide = await get_template("usage-guide")
        usage_guide = usage_guide.format(add_me_btn_text)

        start_me_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("Start me", url=f"t.me/{self.user.username}?start")
        ]])

        group_id = chat.id

        if not str(group_id).startswith("-100"):
            err_msg = await get_template("group-abnormal-exception")
            err_msg += usage_guide
            await self.client.send_photo(
                chat_id=group_id,
                photo=guide_img_link,
                caption=err_msg,
                reply_markup=start_me_btn,
                parse_mode=ParseMode.MARKDOWN,
            )
            return None

        admin = new_member.promoted_by
        if not admin:
            self.log.error("Bot join group error, not by admin")
            err_msg = await get_template("group-invite-exception")
            err_msg += usage_guide
            await self.client.send_photo(
                chat_id=group_id,
                photo=guide_img_link,
                caption=err_msg,
                reply_markup=start_me_btn,
                parse_mode=ParseMode.MARKDOWN
            )
            return None

        payloads = await construct_payloads(admin)

        share_link = await self.get_chat_link(chat)
        slogan = await get_chat_description(chat.id)
        logo_url = None
        if chat.photo:
            file_id = chat.photo.big_file_id
            logo_url = await get_avatar_link(chat.id, file_id)

        payloads.update({
            "name": chat.title,
            "ownerTgId": admin.id,
            "shareLink": share_link,
            "status": 1,
            "targetId": group_id,
            "targetType": chat_type,
            "slogan": slogan,
            "logoUrl": logo_url,
        })

        payloads = json.loads(json.dumps(payloads))

        project_id = await self.apiclient.create_project(payloads)

        if not project_id:
            err_msg = await get_template("group-init-failed")
            err_msg += usage_guide
            await self.client.send_photo(
                chat_id=admin.id,
                photo=guide_img_link,
                caption=err_msg,
                reply_markup=start_me_btn,
                parse_mode=ParseMode.MARKDOWN,
            )
            await self.client.send_photo(
                chat_id=group_id,
                photo=guide_img_link,
                caption=err_msg,
                reply_markup=start_me_btn,
                parse_mode=ParseMode.MARKDOWN,
            )
        url = util.misc.generate_project_detail_link(project_id, self.uid)
        msg_text = await get_template("create-project")
        msg_text = msg_text.format(group_name=chat.title)
        btn_text = await get_template("create-project-button")
        button = util.tg.build_button([(btn_text, url, False)])

        await self.client.send_message(admin.id, msg_text, reply_markup=button)

        if project_id:
            notify_msg = json.dumps({
                "project_id": project_id,
                "owner_tg_id": admin.id,
                "bot_id": self.uid,
            })

            async with client.connect("ws://127.0.0.1:8080/ws") as ws:
                try:
                    await ws.send(notify_msg)
                    msg = await ws.recv()
                    self.log.info("Project create notify: %s", msg)
                except websockets.ConnectionClosed:
                    pass

            project_config = util.project_config.BotNotificationConfig(project_id)
            await util.project_config.BotNotificationConfig.update_or_create_project_config(self.mysql, project_config)

    async def dispatch_event(
        self: "Anjani",
        event: str,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[Tuple[Any, ...]]:
        results = []

        try:
            listeners = self.listeners[event]
        except KeyError:
            return None

        if not listeners:
            return None

        self.log.debug("Dispatching event '%s' with data %s", event, args)

        if event == "message":
            event_data = args[0]
            if event_data.new_chat_title:
                chat = event_data.chat
                chat.title = event_data.new_chat_title
                await self.save_chat_info(chat)

        # storing group info when bot joined
        if event == "chat_member_update":
            updated = args[0]
            chat = updated.chat

            # only for bot join group
            if updated.new_chat_member and updated.new_chat_member.user.id == self.uid:
                await self.save_chat_info(chat)
                await self.create_project_on_join(updated)

            if updated.new_chat_member and updated.invite_link:
                from_user = updated.from_user
                invite_link = updated.invite_link

                project_id = await self.mysql.get_chat_project_id(chat.id)
                config = await util.project_config.BotNotificationConfig.get_project_config(self.mysql, project_id)

                self.log.debug("Chat %s(%s) project config: %s", chat.title, chat.id, config)

                if config.enable_rewards_verify:
                    payloads = [chat.id, invite_link.invite_link]

                    verify_args = util.misc.encode_args(payloads)

                    btn_text = await get_template("rewards-to-claim-button")
                    button = InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            btn_text,
                            url=f"t.me/{self.user.username}?start={verify_args}"
                        )
                    ]])
                    reply_text = await get_template("rewards-to-claim")
                    reply_text = reply_text.format(from_user.mention)
                    if chat.type == ChatType.CHANNEL:
                        try:
                            await self.client.send_message(
                                chat_id=from_user.id,
                                text=reply_text,
                                reply_markup=button
                            )
                        except Exception as e:
                            self.log.warn("Unable to push notification %s to user %s, error: %s", reply_text, from_user, e)
                    else:
                        await self.client.send_message(
                            chat_id=chat.id,
                            text=reply_text,
                            reply_markup=button
                        )
                else:
                    payloads = {
                        "chatId": chat.id,
                        "tgUserId": from_user.id,
                        "inviteLink": invite_link.invite_link,
                        "botId": self.uid,
                    }

                    btn_text = await get_template("rewards-msg-button")
                    project_link = util.misc.generate_project_detail_link(project_id, self.uid)
                    button = InlineKeyboardMarkup([
                        [InlineKeyboardButton(text=btn_text, url=project_link)]
                    ])

                    rewards = await self.apiclient.distribute_join_rewards(payloads)
                    reply_text = await get_template("rewards-claimed")
                    if rewards:
                        reply_text = reply_text.format(rewards=rewards, mention=from_user.mention)
                        if chat.type == ChatType.CHANNEL:
                            try:
                                await self.client.send_message(
                                    chat_id=from_user.id,
                                    text=reply_text,
                                    reply_markup=button
                                )
                            except Exception as e:
                                self.log.warn("Unable to push notification %s to user %s, error: %s", reply_text, from_user, e)
                        else:
                            await self.client.send_message(
                                chat_id=chat.id,
                                text=reply_text,
                                reply_markup=button
                            )

        EventCount.labels(event).inc()
        with EventLatencySecond.labels(event).time():
            match = None
            index = None
            is_tg_event = False
            for lst in listeners:
                if lst.filters:
                    for idx, arg in enumerate(args):
                        is_tg_event = isinstance(arg, EventType)
                        if is_tg_event:
                            if not await lst.filters(self.client, arg):
                                continue

                            match = arg.matches
                            index = idx
                            break

                        self.log.error(f"'{type(arg)}' can't be used with filters.")
                    else:
                        continue

                if match and index is not None:
                    args[index].matches = match

                result = None
                try:
                    result = await lst.func(*args, **kwargs)
                except KeyError:
                    continue
                except StopPropagation:
                    break
                except Exception as err:  # skipcq: PYL-W0703
                    UnhandledError.labels("command").inc()
                    dispatcher_error = EventDispatchError(
                        f"raised from {type(err).__name__}: {str(err)}"
                    ).with_traceback(err.__traceback__)
                    if is_tg_event and args[0] is not None:
                        data = _get_event_data(args[0])
                        self.log.error(
                            "Error dispatching event '%s' on %s\n"
                            "  Data:\n"
                            "    • Chat    -> %s (%d)\n"
                            "    • Invoker -> %s (%d)\n"
                            "    • Input   -> %s",
                            event,
                            lst.func.__qualname__,
                            data.get("chat_title", "Unknown"),
                            data.get("chat_id", -1),
                            data.get("user_name", "Unknown"),
                            data.get("user_id", -1),
                            data.get("input"),
                            exc_info=dispatcher_error,
                        )
                        await self.dispatch_alert(
                            f"Event __{event}__ on `{lst.func.__qualname__}`",
                            dispatcher_error,
                            data.get("chat_id"),
                        )
                    else:
                        self.log.error(
                            "Error dispatching event '%s' on %s with data\n%s",
                            event,
                            lst.func.__qualname__,
                            _unpack_args(args),
                            exc_info=dispatcher_error,
                        )
                        await self.dispatch_alert(
                            f"Event __{event}__ on `{lst.func.__qualname__}`",
                            dispatcher_error,
                        )
                    continue
                finally:
                    if result:
                        results.append(result)

                    match = None
                    index = None
                    result = None

            return tuple(results)

    async def dispatch_missed_events(self: "Anjani") -> None:
        if not self.loaded or self._TelegramBot__running:
            return

        collection = self.db.get_collection("SESSION")

        data = await collection.find_one(
            {"_id": sha256(self.config.BOT_TOKEN.encode()).hexdigest()}
        )
        if not data:
            return

        pts, date = data.get("pts"), data.get("date")
        if not pts or not date:
            return

        async def send_missed_message(
            messages: list[raw.base.message.Message],
            users: MutableMapping[int, Any],
            chats: MutableMapping[int, Any],
        ) -> None:
            for message in messages:
                self.log.debug("Sending missed message with data '%s'", message)
                await self.client.dispatcher.updates_queue.put(
                    (
                        raw.types.update_new_message.UpdateNewMessage(
                            message=message, pts=0, pts_count=0
                        ),
                        users,
                        chats,
                    )
                )

        async def send_missed_update(
            updates: list[raw.base.update.Update],
            users: MutableMapping[int, Any],
            chats: MutableMapping[int, Any],
        ) -> None:
            for update in updates:
                self.log.debug("Sending missed update with data '%s'", update)
                await self.client.dispatcher.updates_queue.put((update, users, chats))

        try:
            while True:
                # TO-DO
                # 1. Change qts to 0, because we want to get all missed events
                #    so we have a proper loop going on until DifferenceEmpty
                diff = await self.client.invoke(
                    functions.updates.get_difference.GetDifference(
                        pts=pts, date=date, qts=-1
                    )
                )
                if isinstance(
                    diff,
                    (
                        raw.types.updates.difference.Difference,
                        raw.types.updates.difference_slice.DifferenceSlice,
                    ),
                ):
                    if isinstance(diff, raw.types.updates.difference.Difference):
                        state: Any = diff.state
                    else:
                        state: Any = diff.intermediate_state

                    pts, date = state.pts, state.date
                    users = {u.id: u for u in diff.users}  # type: ignore
                    chats = {c.id: c for c in diff.chats}  # type: ignore

                    await asyncio.wait(
                        (
                            self.loop.create_task(
                                send_missed_message(diff.new_messages, users, chats)
                            ),
                            self.loop.create_task(
                                send_missed_update(diff.other_updates, users, chats)
                            ),
                        )
                    )
                elif isinstance(
                    diff, raw.types.updates.difference_empty.DifferenceEmpty
                ):
                    self.log.info("Missed event exhausted, you are up to date.")
                    date = diff.date
                    break
                elif isinstance(
                    diff, raw.types.updates.difference_too_long.DifferenceTooLong
                ):
                    pts = diff.pts
                    continue
                else:
                    break
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            # Unset after we finished to avoid sending the same pts and date,
            # If GetState() doesn't executed on stop event
            await collection.update_one(
                {"_id": sha256(self.config.BOT_TOKEN.encode()).hexdigest()},
                {"$unset": {"pts": "", "date": "", "qts": "", "seq": ""}},
            )

    async def dispatch_alert(
        self: "Anjani",
        invoker: str,
        exc: BaseException,
        chat_id: Optional[int] = None,
    ) -> None:
        """Dispatches an alert to the configured alert log."""
        if not self.config.ALERT_LOG:
            return

        log_chat = self.config.ALERT_LOG.split("#")
        log_thread_id = None
        log_chat_id = int(log_chat[0])
        if len(log_chat) == 2:
            log_thread_id = int(log_chat[1])

        alert = f"""🔴 **Anjani ERROR ALERT**

  - **Alert by:** {invoker}
  - **Chat ID:** {chat_id}
  - **Time (UTC):** {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}

**ERROR**
```python
{util.error.format_exception(exc)}
```
        """
        await self.client.send_message(
            log_chat_id,
            alert,
            message_thread_id=log_thread_id,  # type: ignore
        )

    async def log_stat(self: "Anjani", stat: str, *, value: int = 1) -> None:
        await self.dispatch_event("stat_listen", stat, value)

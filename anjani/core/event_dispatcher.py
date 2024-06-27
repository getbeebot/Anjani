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

from pyrogram import raw
from pyrogram.filters import Filter
from pyrogram.raw import functions
from pyrogram.types import CallbackQuery, InlineQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatType

from anjani import plugin, util
from anjani.error import EventDispatchError
from anjani.listener import Listener, ListenerFunc
from anjani.util.misc import StopPropagation

from anjani.language import get_template

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
                try:
                    chat = event_data.chat
                    group_name = event_data.new_chat_title
                    group_id = chat.id
                    group_username = chat.username
                    if group_username:
                        invite_link = f"https://t.me/{group_username}"
                    else:
                        try:
                            invite_link = await self.client.export_chat_invite_link(group_id)
                        except Exception as e:
                            self.log.error("export invite link error: %s", e)
                            invite_link = ""

                    mysql = util.db.AsyncMysqlClient.init_from_env()
                    await mysql.connect()
                    await mysql.update_chat_info({
                        "chat_type": 0,
                        "chat_id": group_id,
                        "chat_name": group_name,
                        "invite_link": invite_link,
                        "bot_id": self.uid,
                    })

                    self.log.info(f"Update group info {group_name}, {group_id}, {invite_link}")
                except Exception as e:
                    self.log.error("update group info error: %s", e)
                finally:
                    await mysql.close()

        # storing group info when bot joined
        if event == "chat_member_update":
            event_data = args[0]
            chat_id = event_data.chat.id
            chat_name = event_data.chat.title
            chat_username = event_data.chat.username
            ctype = event_data.chat.type

            if ctype == ChatType.CHANNEL:
                chat_type = 1

            if ctype == ChatType.GROUP or ctype == ChatType.SUPERGROUP:
                chat_type = 0

            # only for bot join group
            if event_data.new_chat_member and event_data.new_chat_member.user.id == self.uid:
                try:
                    if chat_username:
                        invite_link = f"https://t.me/{chat_username}"
                    else:
                        invite_link = await self.client.export_chat_invite_link(chat_id)
                except Exception as e:
                    self.log.error(e)
                    invite_link = ""

                try:
                    mysql = util.db.AsyncMysqlClient.init_from_env()
                    await mysql.connect()
                    await mysql.update_chat_info({
                        "chat_type": chat_type,
                        "chat_id": chat_id,
                        "chat_name": chat_name,
                        "invite_link": invite_link,
                        "bot_id": self.uid,
                    })

                    self.log.info(f"Bot joining {chat_type} {chat_name}({chat_id}) {invite_link}")
                except Exception as e:
                    self.log.error("Inserting group record error: %s", e)
                finally:
                    await mysql.close()


            if event_data.new_chat_member and event_data.invite_link:
                chat = event_data.chat
                from_user = event_data.from_user
                invite_link = event_data.invite_link
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

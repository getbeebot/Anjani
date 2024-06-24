import logging
from datetime import datetime, timezone

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import PeerIdInvalid

import aiohttp
import aiohttp.web as web
from aiohttp import web_response
from aiohttp.web import Response, BaseRequest

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
# from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .util.config import Config
from .util.twa import TWA
from .language import get_template

from .server.tgclient import TGClient
from .server.notification import (
    build_lottery_create_msg,
    build_lottery_end_msg,
    build_lottery_join_msg,
)

# Sun Jun 04 2034 01:00:00 GMT+0000
EXPIRE_TS: int = 2032995600

config = Config()

tgclient = TGClient(config)

log = logging.getLogger("web-server")


async def start_tgclient(app) -> None:
    await tgclient.start()

async def stop_tgclient(app) -> None:
    await tgclient.stop()

async def stop_scheduler(app) -> None:
    scheduler = app['scheduler']
    if scheduler:
        await scheduler.shutdown()


async def web_server() -> None:
    await start_server()


async def start_server() -> None:
    app = web.Application()

    member_check_router = web.post("/is_member", member_check_handler)
    update_user_router = web.get("/update_user", get_user_info_handler)
    send_message_router = web.post("/sendmsg", send_message_handler)
    get_invite_link_router = web.post("/get_invite_link", create_invite_link_handler)


    check_bot_privilege_router = web.post("/check_bot_privilege", check_bot_privilege)

    ws_router = web.get("/ws", community_creation_notify)

    routers = [
        member_check_router, send_message_router, update_user_router,
        get_invite_link_router, check_bot_privilege_router, ws_router,
    ]

    app.add_routes(routers)

    # start pyrogram client with web server start
    app.on_startup.append(start_tgclient)

    app.on_cleanup.append(stop_scheduler)
    app.on_cleanup.append(stop_tgclient)

    runner = web.AppRunner(app)

    await runner.setup()

    host = config.WEBSERVER_HOST
    port = config.WEBSERVER_PORT
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info(f"Web server listening on http://{host}:{port}")

    cron_job()


def cron_job():
    scheduler = AsyncIOScheduler()

    # TODO: more flexible configuration
    # trigger = CronTrigger(minute="*", second="*/10")
    # trigger = IntervalTrigger(hours=4)
    interval = config.AUTO_NOTIFY_INTERVAL

    trigger = IntervalTrigger(hours=interval)
    scheduler.add_job(auto_push_notification, trigger=trigger)
    scheduler.start()


async def auto_push_notification():
    try:
        twa = TWA()
        rows = twa.get_group_id_with_project()
        for row in rows:
            (project_id, group_id) = row
            project_link = twa.generate_project_detail_link(project_id)
            button = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🕹 Enter", url=project_link)]]
            )
            tasks = await twa.get_chat_tasks(group_id)
            participants = await twa.get_chat_activity_participants(group_id)

            log.info(f"group {group_id}, project {project_id}, tasks: {tasks}, participants: {participants}")

            if tasks and participants > 7:
                group_context = await get_template("group-start-pm")
                group_notify_msg = group_context.format(tasks=tasks,participants=participants)
            elif tasks:
                group_context = await get_template("group-notify-no-participants")
                group_notify_msg = group_context.format(tasks=tasks)
            else:
                continue

            # delete last notification
            pre_msg = await twa.get_previous_notify_record(group_id)
            if pre_msg:
                await tgclient.client.delete_messages(group_id, int(pre_msg))

            msg = await tgclient.send_photo(
                group_id,
                "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png",
                caption=group_notify_msg,
                reply_markup=button,
            )
            if msg:
                await twa.save_notify_record(group_id, msg.id)

    except Exception as e:
        log.error(f"auto push notification error: {e}")

async def member_check_handler(request: BaseRequest) -> Response:
    ret_data = { "ok": False }
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {payloads}")

        group_id = int(payloads.get("group_id"))
        user_id = int(payloads.get("user_id"))

        res = await tgclient.is_member(user_id, group_id)

        ret_data.update({
            "ok": True,
            "res": res,
        })

    except Exception as e:
        log.error(f"Member check error: {str(e)}")
        ret_data.update({
            "ok": False,
            "error": str(e),
        })

    return web_response.json_response(ret_data, status=200)


async def get_user_info_handler(request: BaseRequest) -> Response:
    ret_data = { "ok": False }
    try:
        user_id = int(request.query.get("user_id"))

        user = await tgclient.get_user(user_id)

        username = user.username if user.username else None

        avatar_link = await tgclient.get_avatar_link(user_id)

        if not avatar_link:
            avatar_link = ""

        firstname = user.first_name or ""
        lastname = user.last_name
        fullname = firstname + " " + lastname if lastname else firstname

        user_info = {
                "tg_user_id": user_id,
                "username": username if username else "",
                "nickname": fullname,
                "avatar": avatar_link,
        }

        ret_data.update({
            "ok": True,
            "data": user_info,
        })

    except Exception as e:
        log.error(f"Get user avatar error: {str(e)}")
        ret_data.update({
            "ok": False,
            "error": str(e)
        })

    return web_response.json_response(ret_data, status=200)


class InvalidArgumentError(Exception):
    pass


async def send_message_handler(request: BaseRequest) -> Response:
    ret_data = { "ok": False }
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {str(payloads)}")

        chat_type = payloads.get("type")

        if not chat_type:
            raise InvalidArgumentError("No type argument, please checkout the request arguments.")

        assert isinstance(chat_type, int), "type argument should be int, but got an non-int, please check it out"

        data = payloads.get("data")

        chat_id = payloads.get("chatId")

        if not chat_id:
            chat_id = data.get("owner")

        if not chat_id:
            raise InvalidArgumentError("No chat_id or owner, please checkout the request arguments.")

        assert isinstance(chat_id, str) or isinstance(chat_id, int), "chatId/data.owner not found or not correct type"

        chat_id = int(chat_id)

        uri = data.get("uri")

        if not uri:
            uri = config.TWA_LINK

        button = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🕹 Enter", url=uri)]
            ]
        )

        content: str = ""
        notify_type = data.get("notifyType")

        lottery_type = data.get("lotteryType")
        if notify_type == 1:    # create lottery task
            template = await get_template(f"lottery-create-{lottery_type}")
            content = build_lottery_create_msg(template, **data)
        elif notify_type == 2:  # user entered the draw
            template = await get_template(f"lottery-join-{lottery_type}")
            content = build_lottery_join_msg(template, **data)
        elif notify_type == 3:  # lottory draw winner announce
            template = await get_template("lottery-end")
            content = build_lottery_end_msg(template, **data)
        elif notify_type == 4:  # sending file to community admin
            filename = data.get("lotteryFileName")
            chat_id = data.get("owner")
            base_link = config.WEBSITE
            download_link = f"{base_link}/downloads/{filename}"
            content = f"Please download the winners data via {download_link}"

            await tgclient.send_message(chat_id, content)
            log.info(f"send {download_link} to {chat_id}")

            ret_data.update({"ok": True})
            return web_response.json_response(ret_data)
        elif notify_type == 5:
            content = await get_template("task-creation")
            await tgclient.send_photo(
                chat_id,
                "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png",
                caption=content,
                reply_markup=button,
            )
            ret_data.update({"ok": True})
            return web_response.json_response(ret_data)
        else:
            raise InvalidArgumentError("Not support notifyType")

        # sending message
        log.info(f"sending message {content}")
        await tgclient.send_message(
            chat_id,
            content,
            reply_markup=button,
        )

        ret_data = {"res": "ok"}

    except Exception as e:
        log.error(f"Sending occurs error: {str(e)}")
        ret_data.update({
            "ok": False,
            "error": str(e),
        })

    return web_response.json_response(ret_data, status=200)


connected_clients = set()
async def community_creation_notify(request):
    ws = web.WebSocketResponse()
    try:
        await ws.prepare(request)

        connected_clients.add(ws)
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                log.info(msg.data)
                if msg.data == "close":
                    await ws.close()
                else:
                    for wsc in connected_clients.difference({ws}):
                        if wsc.closed:
                            connected_clients.remove(wsc)
                            continue
                        await wsc.send_str(f"{msg.data}")
                    await ws.close()
            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.error(f"ws connection closed with exception {ws.exception()}")
                break
    except Exception as e:
        log.error(f"Websocket connection closed, {e}")

    return ws

async def create_invite_link_handler(request: BaseRequest) -> Response:
    ret_data = { "ok": False }
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {payloads}")

        group_id = int(payloads.get("groupId"))
        user_id = int(payloads.get("userId"))

        user = await tgclient.get_user(user_id)
        user_nick = user.first_name

        expire = datetime.fromtimestamp(EXPIRE_TS, timezone.utc)

        link = await tgclient.client.create_chat_invite_link(
            chat_id=group_id,
            name=user_nick,
            expire_date=expire,
            member_limit=99999,
        )

        invite_link = link.invite_link

        res = {
            "group_id": group_id,
            "user_id": user_id,
            "invite_link": invite_link,
        }
        ret_data.update({
            "ok": True,
            "data": res,
        })

    except PeerIdInvalid as e:
        log.error(e)
        ret_data.update({
            "code": 705,
            "error": f"bot not in group or group not exist. {e}"
        })

    except Exception as e:
        log.error(e)
        ret_data.update({
            "ok": False,
            "error": str(e),
        })

    return web_response.json_response(ret_data, status=200)

async def check_bot_privilege(request: BaseRequest) -> Response:
    ret_data = {"ok": False}
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {payloads}")

        chat_id = payloads.get("chatId")
        bot = await tgclient.client.get_me()

        member = await tgclient.client.get_chat_member(int(chat_id), bot.id)
        bot_privileges = member.privileges

        privileges = [
            "can_manage_chat",
            "can_delete_messages",
            "can_restrict_members",
            "can_change_info",
            "can_invite_users",
            "can_pin_messages",
        ]

        for privilege in privileges:
            if not bot_privileges.__getattribute__(privilege):
                ret_data.update({
                    "ok": False,
                    "error": f"bot does not have privilege: {privilege}",
                })
                return web_response.json_response(ret_data, status=200)

        ret_data.update({"ok": True})

    except PeerIdInvalid as e:
        log.error(e)
        ret_data.update({
            "code": 705,
            "error": f"Bot not in group, {e}",
        })
    except Exception as e:
        log.error(e)
        ret_data.update({
            "code": 1,
            "error": str(e),
        })

    return web_response.json_response(ret_data, status=200)

async def delete_test_handler(request: BaseRequest) -> Response:
    chat_id = -1002207973234
    await tgclient.send_photo(chat_id, "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png", caption="自毁测试 10s", delete_after=10)
    return web_response.json_response({"ok": True}, status=200)

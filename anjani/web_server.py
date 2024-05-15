import os
import json
import logging
from datetime import datetime, timezone

from pyrogram.client import Client
from pyrogram.errors import PeerIdInvalid
from pyrogram.types import User, InlineKeyboardMarkup, InlineKeyboardButton

import asyncio
import aiohttp
import aiohttp.web as web
from aiohttp import web_response
from aiohttp.web import Response

from lxml import etree

from .util.config import Config
from .util.db.mysql import AsyncMysqlClient

config = Config()

client = Client(
    "web-server",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

log = logging.getLogger("web-server")


async def start_tg_client(app) -> None:
    await client.start()


async def stop_tg_client(app) -> None:
    await client.stop()


async def web_server() -> None:
    await start_server()


async def start_server() -> None:
    app = web.Application()

    member_check_router = web.post("/is_member", member_check_handler)
    get_nickname_router = web.post("/users", get_users_handler)
    update_user_avatar_router = web.get("/update_user", get_user_avatar_handler)
    send_message_router = web.post("/sendmsg", send_message_handler)
    routers = [member_check_router, get_nickname_router, send_message_router, update_user_avatar_router]

    app.add_routes(routers)

    # start pyrogram client with web server start
    app.on_startup.append(start_tg_client)
    app.on_cleanup.append(stop_tg_client)

    runner = web.AppRunner(app)

    await runner.setup()

    host = "0.0.0.0"
    port = 8080
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info(f"Web server listening on http://{host}:{port}")


async def member_check_handler(request) -> Response:
    ret_data = { "ok": False }
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {payloads}")

        group_id = int(payloads.get("group_id"))
        user_id = int(payloads.get("user_id"))

        res = await is_member(group_id, user_id)

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


async def get_users_handler(request) -> Response:
    ret_data = { "ok": False }
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {payloads}")

        user_ids = payloads.get("user_ids")
        users = await client.get_users(user_ids)
        log.info("Geting users: %s", users)

        ret_data.update({
            "ok": True,
            "data": json.dumps(users)
        })

    except Exception as e:
        ret_data.update({
            "oK": False,
            "error": str(e),
        })

    return web_response.json_response(ret_data, status=200)


async def get_user_avatar_handler(request) -> Response:
    ret_data = { "ok": False }
    try:
        user_id = int(request.query.get("user_id"))

        user = await client.get_users(user_id)

        username = user.username if user.username else None
        avatar = ""
        if username is not None:
            tg_user_uri = f"https://t.me/{user.username}"
            avatar = await retrieve_avatar_uri(tg_user_uri)

        mysql_client = AsyncMysqlClient.init_from_env()

        firstname = user.first_name or ""
        lastname = user.last_name
        fullname = firstname + " " + lastname if lastname else firstname

        user_info = {
                "tg_user_id": user_id,
                "username": username if username else "",
                "nickname": fullname,
                "avatar": avatar,
        }

        await mysql_client.update_user_info(**user_info)

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


async def send_message_handler(request) -> Response:
    ret_data = { "ok": False }
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {str(payloads)}")

        chat_type = int(payloads.get("type"))

        assert chat_type == 88, "Not support type"

        data = payloads.get("data")

        chat_id = payloads.get("chatId")

        if chat_id is None:
            chat_id = data.get("owner")

        if chat_id is None:
            return web_response.json_response({
                "ok": False,
                "error": "No chat_id or owner, please checkout the request arguments.",
            })

        assert isinstance(chat_id, str) or isinstance(chat_id, int), "chatId/data.owner not found or not correct type"

        chat_id = int(chat_id)

        uri = data.get("uri", "")
        prize = data.get("prize", "")

        end_time_ms = data.get("endTime", "")
        end_time_ts = end_time_ms / 1000
        end_time = datetime.fromtimestamp(timestamp=end_time_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S (UTC)")

        community_name = data.get("communityName", "")

        notify_type = data.get("notifyType")
        # create lottery task
        if notify_type == 1:
            content = f"""
Attention {community_name} Community Luck Draw launched!
Prize: {prize}
End time: {end_time}
Join the excitement
"""

        # user entered the draw
        if notify_type == 2:
            nick_names = data.get("nickNames")
            # type check
            if not isinstance(nick_names, list) and not isinstance(nick_names, str):
                return web_response.json_response({
                    "ok": False,
                    "error": "nick_names should be a list or string",
                })

            if isinstance(nick_names, list):
                nick_names = ", @".join(nick_names)

            content = f"""
@{nick_names} has entered the luckydraw

🎉  Draw Time: {end_time}
🎁  Prize Details: {prize}
"""

        # lottory draw winner announce
        if notify_type == 3:
            content = f"""
🎁 The draw for the {community_name} community event has been held! Check now to see if your're a lucky winner!
"""

        # sending file to community admin
        if notify_type == 4:
            filename = data.get("lotteryFileName")
            chat_id = data.get("owner")
            filepath = f"./lottery/{filename}"
            try:
                log.info(f"sending file {filename} to {chat_id}")
                await client.send_document(chat_id, document=filepath)

                ret_data.update({"ok": True})
            except Exception as e:
                ret_data.update({"error": str(e)})

            # remove the file after sending
            # await asyncio.to_thread(os.remove, filepath)

            return web_response.json_response(ret_data)

        # sending message
        log.info(f"sending message {content}")
        await client.send_message(
            chat_id,
            content,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🕹 Enter", url=uri)]]
            ),
        )

        ret_data = {"res": "ok"}

    except Exception as e:
        log.error(f"Sending occurs error: {str(e)}")
        ret_data.update({
            "ok": False,
            "error": str(e),
        })

    return web_response.json_response(ret_data, status=200)


async def is_member(group_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(group_id, user_id)

        log.debug("Get member: %s", "".join(str(member).split()))

        if member.is_member or member.is_member is None:
            return True
        else:
            return False
    except Exception as e:
        log.error(f"Get chat member error: {str(e)}")
        return False


async def retrieve_avatar_uri(uri) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(uri) as resp:
            html_body = await resp.text()
            xpath = "/html/head/meta[@property='og:image']/@content"
            html = etree.HTML(html_body)
            avatar_uri = html.xpath(xpath)[0]
            return avatar_uri

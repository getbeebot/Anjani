from pyrogram.client import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp.web as web
from aiohttp import web_response
from aiohttp.web import Response

from .util.config import Config

import json
from datetime import datetime, timezone

import logging

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
    send_message_router = web.post("/sendmsg", send_message_handler)
    routers = [member_check_router, get_nickname_router, send_message_router]

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
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {payloads}")

        group_id = payloads.get("group_id")
        user_id = payloads.get("user_id")

        res = await is_member(group_id, user_id)

        ret_data = {"res": res}
        response = web_response.json_response(ret_data, status=200)

    except (web.HTTPBadRequest, ValueError) as e:
        return web_response.json_response({"error": str(e)}, status=400)

    return response


async def get_users_handler(request) -> Response:
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {payloads}")

        user_ids = payloads.get("user_ids")
        users = await client.get_users(user_ids)
        log.info("Geting users: %s", users)

        ret_data = {"data": json.dumps(users)}
        response = web_response.json_response(ret_data, status=200)

    except (web.HTTPBadRequest, ValueError) as e:
        return web_response.json_response({"error": str(e)}, status=400)

    return response


async def send_message_handler(request) -> Response:
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {payloads}")

        chat_id = int(payloads.get("group_id"))
        user_id = int(payloads.get("user_id"))
        uri = payloads.get("uri")
        prize = payloads.get("prize")

        user = await client.get_users(user_id)
        username = user.username

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y/%m/%d %H:%M UTC")

        content = f"""
@{username} has entered the luckydraw

🎉  Draw Time: {date_str}
🎁  Prize Details: {prize}
"""

        chat = await client.get_chat(chat_id)
        group_name = chat.title

        log.debug(f"sending message {content} to {group_name}")
        await client.send_message(
            chat_id,
            content,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Enter", url=uri)]]
            ),
        )

        ret_data = {"res": "ok"}
        response = web_response.json_response(ret_data, status=200)
    except (web.HTTPBadRequest, ValueError) as e:
        return web_response.json_response({"error": str(e)}, status=400)

    return response


async def is_member(group_id, user_id) -> bool:
    try:
        member = await client.get_chat_member(group_id, user_id)
        log.debug("get member: %s", member)
        if member.is_member is None or member.is_member:
            return True
        else:
            return False
    except:  # noqa: E722
        return False

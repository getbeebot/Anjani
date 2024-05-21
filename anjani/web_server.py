import os
import json
import logging

from pyrogram.client import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import aiohttp.web as web
from aiohttp import web_response
from aiohttp.web import Response

import aiofiles.os as aio_os

import boto3

from .util.config import Config
from .language import get_template
from .server.notification import build_lottery_create_msg, build_lottery_end_msg, build_lottery_join_msg

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
    update_user_router = web.get("/update_user", get_user_info_handler)
    send_message_router = web.post("/sendmsg", send_message_handler)
    routers = [member_check_router, get_nickname_router, send_message_router, update_user_router]

    app.add_routes(routers)

    # start pyrogram client with web server start
    app.on_startup.append(start_tg_client)
    app.on_cleanup.append(stop_tg_client)

    runner = web.AppRunner(app)

    await runner.setup()

    host = config.WEBSERVER_HOST
    port = config.WEBSERVER_PORT
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



async def get_user_info_handler(request) -> Response:
    ret_data = { "ok": False }
    try:
        user_id = int(request.query.get("user_id"))

        user = await client.get_users(user_id)

        username = user.username if user.username else None

        avatar = await download_avatar(user_id)

        avatar_link = ""

        if avatar:
            await upload_avatar(avatar)
            await aio_os.remove(avatar)
            avatar_link = f"https://{config.AWS_S3_BUCKET}.s3.ap-southeast-1.amazonaws.com/{avatar}"

        # mysql_client = AsyncMysqlClient.init_from_env()

        firstname = user.first_name or ""
        lastname = user.last_name
        fullname = firstname + " " + lastname if lastname else firstname

        user_info = {
                "tg_user_id": user_id,
                "username": username if username else "",
                "nickname": fullname,
                "avatar": avatar_link,
        }

        # await mysql_client.update_user_info(**user_info)

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


async def send_message_handler(request) -> Response:
    ret_data = { "ok": False }
    try:
        payloads = await request.json()
        log.info(f"Incoming request: {str(payloads)}")

        chat_type = payloads.get("type")

        if not chat_type:
            raise InvalidArgumentError("No type argument, please checkout the request arguments.")

        assert isinstance(chat_type, int), "type argument should be int, but got an non-int, please check it out"

        assert chat_type == 88, "Not support type"

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
            uri = os.getenv("TWA_LINK")

        content: str = ""
        notify_type = data.get("notifyType")

        if notify_type == 1:    # create lottery task
            template = await get_template("lottery-create")
            content = build_lottery_create_msg(template, **data)
        elif notify_type == 2:  # user entered the draw
            template = await get_template("lottery-join")
            content = build_lottery_join_msg(template, **data)
        elif notify_type == 3:  # lottory draw winner announce
            template = await get_template("lottery-end")
            content = build_lottery_end_msg(template, **data)
        elif notify_type == 4:  # sending file to community admin
            filename = data.get("lotteryFileName")
            chat_id = data.get("owner")
            base_link = os.getenv("WEBSITE", "https://getbeebot.com")
            download_link = f"{base_link}/downloads/{filename}"
            content = f"Please download the winners data via {download_link}"

            await client.send_message(chat_id, content)
            log.info(f"send {download_link} to {chat_id}")

            ret_data.update({"ok": True})
            return web_response.json_response(ret_data)
        else:
            raise InvalidArgumentError("Not support notifyType")

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


async def download_avatar(chat_id: int):
    try:
        photos = client.get_chat_photos(chat_id)
        photo = await photos.__anext__()

        if photo.file_id:
            avatar = f"../B{chat_id}.jpg"
            await client.download_media(photo.file_id, file_name=avatar)
            return os.path.basename(avatar)
    except Exception as e:
        log.error(f"Downloading avatar from telegram server failed: {str(e)}")

    return None


async def upload_avatar(filename):
    ACCESS_KEY = config.AWS_AK
    SECRET_KEY = config.AWS_SK
    bucket = config.AWS_S3_BUCKET
    s3 = boto3.client("s3", aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
    s3.upload_file(
        filename,
        bucket,
        filename,
        ExtraArgs={"ContentType": "image/jpeg"}
    )

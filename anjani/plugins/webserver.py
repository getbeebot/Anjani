import os
import json
import aiofiles.os as aio_os
import base64
from typing import ClassVar, Optional

import asyncio

from datetime import datetime, timezone

import aiohttp_cors
from aiohttp import web
from aiohttp import WSMsgType
from aiohttp.web import BaseRequest, Response

from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from anjani import plugin
from anjani.util.db import MysqlPoolClient
from anjani.util.project_config import BotNotificationConfig
from anjani.server.notification import (
    build_congrats_msg,
    build_congrats_records,
    build_invitation_notify,
    build_invitation_records,
    build_lottery_create_msg,
    build_lottery_join_msg,
)

import boto3

class WebServer(plugin.Plugin):
    name: ClassVar[str] = "WebServer"
    helpable: ClassVar[bool] = False

    ws_clients: set
    site: web.TCPSite
    mysql: MysqlPoolClient

    s3: any
    engage_img: str
    draw_img: str

    async def on_load(self) -> None:
        # init for aws s3
        self.s3 = boto3.client("s3", region_name="ap-southeast-1", aws_access_key_id=self.bot.config.AWS_AK, aws_secret_access_key=self.bot.config.AWS_SK)
        # init for mysql
        self.mysql = MysqlPoolClient.init_from_env()
        # init for ws clients
        self.ws_clients = set()
        self.engage_img = os.getenv("ENGAGE_IMG", "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png")
        self.draw_img = os.getenv("DRAW_IMG", "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/luckydraw.png")

    async def on_start(self, _: int) -> None:
        # init web server
        app = web.Application()

        is_member_router = web.post("/is_member", self.is_member_handler)
        update_user_router = web.get("/update_user", self.update_user_handler)
        send_msg_router = web.post("/sendmsg", self.send_msg_handler)
        privilege_check_router = web.post("/check_bot_privilege", self.privilege_check_handler)

        ws_router = web.get("/ws", self.project_creation_notify)

        # save_iq_text_router = web.post("/save_iq", self.save_iq_text_handler)
        routers = [
            is_member_router, update_user_router, send_msg_router, privilege_check_router, ws_router
            # save_iq_text_router
        ]

        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*"
            )
        })
        get_invite_link_router = app.router.add_route("POST", "/get_invite_link", self.get_invite_link_handler)
        alert_router = app.router.add_route("POST", "/alert", self.send_alert_handler)
        save_iq_rotuer = app.router.add_route("POST", "/save_iq", self.save_iq_text_handler)

        cors.add(get_invite_link_router)
        cors.add(alert_router)
        cors.add(save_iq_rotuer)

        app.add_routes(routers)

        runner = web.AppRunner(app)
        await runner.setup()
        host = self.bot.config.WEB_HOST
        port = self.bot.config.WEB_PORT
        self.site = web.TCPSite(runner, host, port)

        await self.site.start()

        self.log.info(f"Starting web server at: http://{host}:{port}")

    async def on_stop(self) -> None:
        await self.mysql.close()
        self.log.info("Shutdown websever...")
        await self.site.stop()

    async def is_member_handler(self, request: BaseRequest) -> Response:
        ret_data = {"ok": False}
        try:
            payloads = await request.json()
            self.log.info("/is_member request payloads: %s", payloads)

            group_id = int(payloads.get("group_id"))
            user_id = int(payloads.get("user_id"))

            member = await self.bot.client.get_chat_member(group_id, user_id)

            if member.is_member or member.is_member is None:
                ret_data.update({"ok": True, "res": True})
            else:
                ret_data.update({"ok": True, "res": False})
        except Exception as e:
            self.log.error("Is member check error: %s", e)
            ret_data.update({"ok": False, "res": False, "error": str(e)})

        self.log.info("/is_member check return %s", ret_data)

        return web.json_response(ret_data, status=200)

    async def update_user_handler(self, request: BaseRequest) -> Response:
        ret_data = {"ok": False}
        try:
            self.log.info("/update_user request payloads: %s", request.query)
            user_id = int(request.query.get("user_id"))

            user = await self.bot.client.get_users(user_id)
            username = user.username if user.username else None
            # avatar_link = await self.get_avatar(user_id)
            firstname = user.first_name or ""
            lastname = user.last_name
            fullname = firstname + " " + lastname if lastname else firstname

            user_info = {
                "tg_user_id": user_id,
                "username": username if username else "",
                "nickname": fullname,
                "avatar": None,
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.update_user_avatar(user_id))
            except Exception as e:
                self.log.warn("update user avatar error: %s", e)
            ret_data.update({"ok": True, "data": user_info})
        except Exception as e:
            self.log.error("update user error %s", e)
            ret_data.update({"ok": False, "error": str(e)})

        return web.json_response(ret_data, status=200)

    async def send_msg_handler(self, request: BaseRequest) -> Response:
        ret_data = { "ok": False }
        try:
            payloads = await request.json()
            self.log.info("/sendmsg request payloads: %s", payloads)

            chat_type = payloads.get("type")

            if not chat_type:
                return web.json_response({"ok": False, "error": "No type argument, please checkout the request arguments."}, status=200)

            assert isinstance(chat_type, int), "type argument should be int, but got an non-int, please check it out"

            data = payloads.get("data")

            chat_id = payloads.get("chatId")

            if not chat_id:
                chat_id = data.get("owner")

            if not chat_id:
                return web.json_response({"ok": False, "error": "No chat_id or owner, please checkout the request arguments."}, status=200)

            assert isinstance(chat_id, str) or isinstance(chat_id, int), "chatId/data.owner not found or not correct type"

            chat_id = int(chat_id)

            uri = data.get("uri") or os.getenv("TWA_LINK")

            button = InlineKeyboardMarkup([[InlineKeyboardButton("🕹 Enter", url=uri)]])

            project_id = await self.bot.mysql.get_chat_project_id(chat_id, self.bot.uid)
            project_config = await BotNotificationConfig.get_project_config(project_id)

            chat = await self.bot.client.get_chat(chat_id)
            if chat.type == ChatType.CHANNEL:
                self.log.warn("Chat type is channel, not sending notification. Channel: %s, content: %s", chat.title, payloads)
                return web.json_response({"ok": False, "error": "I'm not push notification to channel"}, status=200)

            notify_type = data.get("notifyType")

            lucky_draw_btn = InlineKeyboardButton(text="View the luckydraw", url=uri)
            withdraw_btn = InlineKeyboardButton(text="Withdraw", url=f"t.me/beecon_wallet_bot?start=true")
            ret_data.update({"ok": True})
            if notify_type == 1 and project_config.newdraw:
                await self.newdraw_notify(chat_id, data, button)
            elif notify_type == 2 and project_config.userjoin:
                await self.user_join_notify(chat_id, data, button)
            elif notify_type == 3 and project_config.draw:
                await self.draw_notify(chat_id, data, button)
            elif notify_type == 4:
                await self.draw_list_notify(data)
            elif notify_type == 5 and project_config.newtask:
                await self.newtask_notify(chat_id, button)
            elif notify_type == 6: # private congrats
                await self.congrats_notify(
                    chat_id,
                    data,
                    InlineKeyboardMarkup([
                        [lucky_draw_btn],
                        [withdraw_btn],
                    ])
                )
            elif notify_type == 7:
                await self.congrat_records_notify(
                    chat_id,
                    data,
                    InlineKeyboardMarkup([
                        [lucky_draw_btn],
                        [withdraw_btn],
                    ])
                )
            elif notify_type == 8:
                await self.invite_records_notify(
                    chat_id,
                    data,
                    InlineKeyboardMarkup([[lucky_draw_btn]])
                )
            elif notify_type == 9:
                await self.invite_success_notify(
                    chat_id,
                    data,
                    InlineKeyboardMarkup([[lucky_draw_btn]])
                )
            else:
                self.log.warn("Not send mssage for request: %s", payloads)
                ret_data.update({"ok": False, "error": "reject by setting"})
        except Exception as e:
            self.log.error(f"Sending occurs error: {str(e)}")
            ret_data.update({ "ok": False, "error": str(e) })
        return web.json_response(ret_data, status=200)

    async def get_invite_link_handler(self, request: BaseRequest) -> Response:
        ret_data = { "ok": False }
        try:
            payloads = await request.json()
            self.log.info("/get_invite_link request payloads: %s", payloads)

            group_id = int(payloads.get("groupId"))
            user_id = payloads.get("userId")

            link_label = int(datetime.now(tz=timezone.utc).timestamp())
            if user_id:
                user = await self.bot.client.get_users(int(user_id))
                link_label = user.first_name

            expire = datetime.fromtimestamp(2032995600, timezone.utc)
            link = await self.bot.client.create_chat_invite_link(
                chat_id=group_id,
                name=link_label,
                expire_date=expire,
                member_limit=99999,
            )
            invite_link = link.invite_link

            res = {
                "group_id": group_id,
                "user_id": user_id,
                "link_label": link_label,
                "invite_link": invite_link,
            }
            ret_data.update({"ok": True, "data": res})
        except Exception as e:
            self.log.error("Get invite link error: %s", str(e))
            ret_data.update({"ok": False, "error": str(e)})
        return web.json_response(ret_data, status=200)

    async def privilege_check_handler(self, request: BaseRequest) -> Response:
        ret_data = {"ok": False}
        try:
            payloads = await request.json()
            self.log.info("/check_bot_privilege request payloads: %s", payloads)

            chat_id = payloads.get("chatId")
            member = await self.bot.client.get_chat_member(int(chat_id), self.bot.uid)

            bot_privileges = member.privileges

            self.log.debug("Bot %s in chat %s: %s ", self.bot.uid, chat_id, member)

            privileges = [
                "can_manage_chat",
                "can_delete_messages",
                "can_restrict_members",
                # "can_change_info",
                "can_invite_users",
                # "can_pin_messages",
            ]

            for privilege in privileges:
                if not bot_privileges.__getattribute__(privilege):
                    ret_data.update({
                        "ok": False,
                        "error": f"bot does not have privilege: {privilege}",
                    })
                    return web.json_response(ret_data, status=200)

            ret_data.update({"ok": True})
        except Exception as e:
            self.log.error("Bot privileges check error: %s", str(e))
            ret_data.update({"ok": False, "error": str(e)})

        return web.json_response(ret_data, status=200)

    async def project_creation_notify(self, request: BaseRequest) -> Response:
        ws = web.WebSocketResponse()
        try:
            await ws.prepare(request)

            self.ws_clients.add(ws)
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    self.log.info(msg.data)
                    if msg.data == "close":
                        await ws.close()
                    else:
                        for wsc in self.ws_clients.difference({ws}):
                            if wsc.closed:
                                self.ws_clients.remove(wsc)
                                continue
                            await wsc.send_str(f"{msg.data}")
                        await ws.close()
                elif msg.type == WSMsgType.ERROR:
                    self.log.error(f"ws connection closed with exception {ws.exception()}")
                    break
        except Exception as e:
            self.log.error(f"Websocket connection closed, {e}")

    async def send_alert_handler(self, request: BaseRequest) -> Response:
        ret_data = {"ok": False}
        try:
            url = os.getenv("ALERT_API")
            user = os.getenv("ALERT_USER")
            password = os.getenv("ALERT_PASS")

            payloads = await request.json()

            auth_token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
            auth = f"Basic {auth_token}"
            headers = {
                "Authorization": auth,
                "Content-Type": "application/json",
            }

            if self.bot.uid == 6802454608:
                async def save_alert_record(name: str, description: str):
                    mysql_client = MysqlPoolClient.init_from_env()
                    await mysql_client.connect()
                    sql = "INSERT INTO alert_record(name, des) VALUES(%s, %s)"
                    values = (name, description)
                    await mysql_client.update(sql, values)
                    await mysql_client.close()
                    del mysql_client
                try:
                    msg = payloads[0]
                    name = msg.get("labels").get("alertname")
                    des = msg.get("annotations").get("description") or ""
                    loop = asyncio.get_running_loop()
                    loop.create_task(save_alert_record(name, des))
                except Exception as e:
                    self.log.error("saving alert record %s error %s", payloads, e)

            async with self.bot.http.post(url, json=payloads, headers=headers) as resp:
                self.log.info(f"Alert response: %s", resp)
                if resp.status == 200:
                    ret_data.update({"ok": True})
                else:
                    ret_data.update({"ok": False, "error": await resp.text()})
        except Exception as e:
            self.log.error(f"push alert error: {e}")
            ret_data.update({
                "ok": False,
                "error": str(e)
            })
        return web.json_response(ret_data, status=200)

    async def update_user_avatar(self, chat_id: int) -> None:
        avatar = await self.get_avatar(chat_id)
        if not avatar:
            return None
        # 1. query user id based on chat_id
        user_id = await self.mysql.get_user_id(chat_id)
        if not user_id:
            self.log.warn("update user avatar can not find user_id by telegram chat id %s", chat_id)
            return None
        # 2. update db data for user
        await self.mysql.update_user_avatar(user_id, avatar)

    async def get_avatar(self, chat_id: int) -> Optional[str]:
        avatar_link = None
        try:
            photos = self.bot.client.get_chat_photos(chat_id)
            photo = await photos.__anext__()
            if photo.file_id:
                avatar_name = f"B{chat_id}.jpg"
                avatar = f"/app/downloads/{avatar_name}"

                await self.bot.client.download_media(photo.file_id, file_name=avatar)

                s3_bucket = self.bot.config.AWS_S3_BUCKET
                self.s3.upload_file(
                    avatar,
                    s3_bucket,
                    avatar_name,
                    ExtraArgs={"ContentType": "image/jpeg"}
                )

                await aio_os.remove(avatar)

                avatar_link = f"https://{s3_bucket}.s3.ap-southeast-1.amazonaws.com/{avatar_name}"
        except Exception as e:
            self.log.warn("Get chat %s avatar link error %s", chat_id, e)

        return avatar_link

    async def newdraw_notify(self, chat_id: int, args: dict, buttons=None):
        # send newdraw create message to group, notify_type = 1
        lottery_type = args.get("lotteryType")
        template = await self.text(None, f"lottery-create-{lottery_type}", noformat=True)
        msg = build_lottery_create_msg(template, **args)
        if not buttons:
            self.log.error("No button, reject to send message to chat %s with %s", chat_id, msg)
            return None
        await self.bot.client.send_photo(chat_id, self.engage_img, caption=msg, reply_markup=buttons)
        self.log.info("Sent message to %s with %s", chat_id, msg)

    async def user_join_notify(self, chat_id: int, args: dict, buttons=None):
        # send user join message to group, notify_type = 2
        lottery_type = args.get("lotteryType")
        template = await self.text(None, f"lottery-join-{lottery_type}", noformat=True)
        msg = build_lottery_join_msg(template, **args)
        if not buttons:
            self.log.error("No button, reject to send message to chat %s with %s", chat_id, msg)
            return None
        await self.bot.client.send_photo(chat_id, self.engage_img, caption=msg, reply_markup=buttons)
        self.log.info("Sent message to %s with %s", chat_id, msg)

    async def draw_notify(self, chat_id: int, args: dict, buttons=None):
        # send message to group when draw open, notify_type = 3
        msg = await self.text(None, "lottery-end", **args)
        if not buttons:
            self.log.error("No button, reject to send message to chat %s with %s", chat_id, msg)
            return None
        await self.bot.client.send_photo(chat_id, self.draw_img, caption=msg, reply_markup=buttons)
        self.log.info("Sent message to %s with %s", chat_id, msg)

    async def draw_list_notify(self, args: dict):
        # send file to community admin, notify_type = 4
        filename = args.get("lotteryFileName")
        chat_id = args.get("owner")
        base_link = os.getenv("WEBSITE")
        download_link = f"{base_link}/downloads/{filename}"
        content = f"Please download the winners data via {download_link}"
        await self.bot.client.send_message(chat_id, content)
        self.log.info("Sent message to %s with %s", chat_id, download_link)

    async def newtask_notify(self, chat_id: int, buttons=None):
        # send message to group while task created, notify_type = 5
        msg = await self.text(None, "task-creation")
        if not buttons:
            self.log.error("No button, reject to send message to chat %s with %s", chat_id, msg)
            return None
        await self.bot.client.send_photo(chat_id=chat_id, photo=self.engage_img, caption=msg, reply_markup=buttons)
        self.log.info("Sent message to %s with %s", chat_id, msg)

    async def congrats_notify(self, chat_id: int, args: dict, buttons=None):
        # send rewards message to user, notify_type = 6
        template = await self.text(None, "congrats-draw", noformat=True)
        msg = build_congrats_msg(template, **args)
        if not buttons:
            self.log.error("No button, reject to send message to chat %s with %s", chat_id, msg)
            return None
        await self.bot.client.send_photo(chat_id=chat_id, photo=self.draw_img, caption=msg, reply_markup=buttons)
        self.log.info("Sent message to %s with %s", chat_id, msg)

    async def congrat_records_notify(self, chat_id: int, args: dict, buttons=None):
        # send reward records to user, notify_type = 7
        template = await self.text(None, "congrats-records", noformat=True)
        msg = build_congrats_records(template, **args)
        if not buttons:
            self.log.error("No button, reject to send message to chat %s with %s", chat_id, msg)
            return None
        await self.bot.client.send_message(chat_id, msg, reply_markup=buttons)
        self.log.info("Sent message to %s with %s", chat_id, msg)

    async def invite_records_notify(self, chat_id: int, args: dict, buttons=None):
        # send invite records to user, notify_type = 8
        template = await self.text(None, "invitation-records", noformat=True)
        msg = build_invitation_records(template, **args)
        if not buttons:
            self.log.error("No button, reject to send message to chat %s with %s", chat_id, msg)
            return None
        await self.bot.client.send_message(int(chat_id), msg, reply_markup=buttons)
        self.log.info("Sent message to %s with %s", chat_id, msg)

    async def invite_success_notify(self, chat_id: int, args: dict, buttons=None):
        # send message to user when others were invited, notify_type = 9
        template = await self.text(None, "invitation-notify", noformat=True)
        msg = build_invitation_notify(template, **args)

        if not buttons:
            self.log.error("No button, reject to send message to chat %s with %s", chat_id, msg)
            return None
        await self.bot.client.send_message(int(chat_id), msg, reply_markup=buttons)
        self.log.info("Sent message to %s with %s", chat_id, msg)

    async def save_iq_text_handler(self, request: BaseRequest) -> Response:
        ret_data = {"ok": False}
        try:
            payloads = await request.json()

            project_id = int(payloads.get("project_id"))
            task_id = int(payloads.get("task_id"))
            btn_text = payloads.get("btn_text")
            des = payloads.get("des")
            pics = payloads.get("pic") or "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/bnp_giveaway2.gif"

            lang = "en"
            btn_desc = json.dumps({
                "text": btn_text,
            })

            code = f"@{self.bot.user.username} ld-{project_id}-{task_id}-{lang}"

            sql = "SELECT * FROM luckydraw_share WHERE project_id = %s AND task_id = %s AND lang = %s"
            res = await self.mysql.query_one(sql, (project_id, task_id, lang))
            if res:
                sql = "UPDATE luckydraw_share SET pics=%s, btn_desc=%s, des=%s WHERE project_id=%s AND task_id=%s AND lang=%s"
                values = (pics, btn_desc, des, project_id, task_id, lang)
                await self.mysql.update(sql, values)
                return web.json_response({"ok": True, "data": code})

            sql = "INSERT INTO luckydraw_share(project_id, task_id, lang, pics, btn_desc, des) VALUES(%s, %s, %s, %s, %s, %s)"

            values = (project_id, task_id, lang, pics, btn_desc, des)

            res = await self.mysql.update(sql, values)
            if res:
                ret_data.update({
                    "ok": False,
                    "error": f"project_id {project_id} or task_id {task_id} not valid"
                })
            else:
                ret_data.update({
                "ok": True,
                "data": code,
            })

        except Exception as e:
            self.log.error("Saving inline query context error %s", e)
            ret_data.update({"error": e})

        return web.json_response(ret_data, status=200)
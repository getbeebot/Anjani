from typing import ClassVar

from datetime import datetime, timezone

import aiohttp_cors
from aiohttp import web
from aiohttp import WSMsgType
from aiohttp.web import BaseRequest, Response

from anjani import plugin, util

class WebServer(plugin.Plugin):
    name: ClassVar[str] = "WebServer"
    helpable: ClassVar[bool] = False

    ws_clients: set
    site: web.TCPSite

    async def on_load(self) -> None:
        app = web.Application()

        is_member_router = web.post("/is_member", self.is_member_handler)
        update_user_router = web.get("/update_user", self.update_user_handler)
        send_msg_router = web.post("/sendmsg", self.send_msg_handler)
        get_invite_link_router = web.post("/get_invite_link", self.get_invite_link_handler)
        privilege_check_router = web.post("/check_bot_privilege", self.privilege_check_handler)

        # TODO: add websockect
        ws_router = web.get("/ws", self.project_creation_notify)

        routers = [
            is_member_router, update_user_router, send_msg_router, get_invite_link_router, privilege_check_router, ws_router,
        ]

        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*"
            )
        })
        alert_router = app.router.add_route("POST", "/alert", self.send_alert_handler)
        cors.add(alert_router)

        app.add_routes(routers)

        runner = web.AppRunner(app)
        await runner.setup()
        host = self.bot.config.WEB_HOST
        port = self.bot.config.WEB_PORT
        self.site = web.TCPSite(runner, host, port)
        # init for ws clients
        self.ws_clients = set()

        await self.site.start()

        self.log.info(f"Starting web server at: http://{host}:{port}")

    async def on_stop(self) -> None:
        self.log.info("Shutdown web sever...")
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

        web.json_response(ret_data, status=200)

    async def update_user_handler(self, request: BaseRequest) -> Response:
        ret_data = {"ok": False}
        try:
            self.log.info("/update_user request payloads: %s", request.query)
            user_id = int(request.query.get("user_id"))

            user = await self.bot.client.get_users(user_id)
            username = user.username if user.username else None
            avatar_link = await self.get_avatar(user_id)

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
            ret_data.update({"ok": True, "data": user_info})
        except Exception as e:
            self.log.error("update user error %s", e)
            ret_data.update({"ok": False, "error": str(e)})

        web.json_response(ret_data, status=200)

    async def send_msg_handler(self, request: BaseRequest) -> Response:
        # TODO:
        pass

    async def get_invite_link_handler(self, request: BaseRequest) -> Response:
        ret_data = { "ok": False }
        try:
            payloads = await request.json()
            self.log.info("/get_invite_link request payloads: %s", payloads)

            group_id = int(payloads.get("groupId"))
            user_id = int(payloads.get("userId"))

            user = await self.bot.client.get_users(user_id)
            user_nick = user.first_name

            expire = datetime.fromtimestamp(2032995600, timezone.utc)
            link = await self.bot.client.create_chat_invite_link(
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
            ret_data.update({"ok": True, "data": res})
        except Exception as e:
            self.log.error("Get invite link error: %s", str(e))
            ret_data.update({"ok": False, "error": str(e)})
        web.json_response(ret_data, status=200)

    async def privilege_check_handler(self, request: BaseRequest) -> Response:
        ret_data = {"ok": False}
        try:
            payloads = await request.json()
            self.log.info("/check_bot_privilege request payloads: %s", payloads)



        except Exception as e:
            self.log.error("")
        pass

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
        pass

    async def get_avatar(self, user_id: int):
        pass
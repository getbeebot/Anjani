import json
from datetime import datetime, timezone

import websockets
from websockets.client import connect

import aiofiles
import aiofiles.os as aio_os
import os
from os.path import join
from typing import ClassVar, Optional

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums.parse_mode import ParseMode

from anjani import listener, plugin, command
from anjani.util.tg import build_button
from anjani.util.twa import TWA

import boto3

import re


class BeeconPlugin(plugin.Plugin):
    name: ClassVar[str] = "Beecon Plugin"
    helpable: ClassVar[bool] = False

    api_url = os.getenv("API_URL")
    aws_ak = os.getenv("AWS_AK")
    aws_sk = os.getenv("AWS_SK")
    aws_s3_bucket = os.getenv("AWS_S3_BUCKET")


    async def on_message(self, message: Message) -> None:
        payloads = "".join(str(message).split())
        self.log.debug(f"Receiving message: {payloads}")
        payloads = json.loads(payloads)
        await self.save_message(payloads)

        context = message.text

        # return if no text message
        if not context:
            return None

        api_uri = f"{self.api_url}/p/distribution/code/getInviteLink"
        from_user = message.from_user

        payloads = {}

        code = None
        if len(context) == 6:
            code = context
        else:
            pattern = re.compile("\u200b\w+\u200b")
            match = pattern.search(context)

            if match:
                target = match.group()
                code = target[1:-1]
            else:
                return None

        self.log.info(f"Invitation code: {code}")

        if code:
            payloads.update({"inviteCode": code})
            try:
                self.log.info(f"Payloads: {payloads}")
                # query for invite link based on code
                async with self.bot.http.get(api_uri, params=payloads) as resp:
                    res = await resp.json()
                    self.log.debug(res)
                    invite_link = res.get("inviteLink")
                    if invite_link:
                        reply_context = f"🎁 Join our community to get rewards\n\n{invite_link}"
                        await self.bot.client.send_message(
                            from_user.id,
                            reply_context,
                            disable_web_page_preview=False,
                        )
            except Exception as e:
                self.log.error(e)


    async def save_message(self, message) -> None:
        target_dir = "messages"
        await self.create_if_not_exist(target_dir)

        chat_id = message.get("chat").get("id", "-0")
        chat_dir_name = str(chat_id)[1:]
        chat_path = join(target_dir, chat_dir_name)
        await self.create_if_not_exist(chat_path)

        target_file = await self.get_target_file(chat_path)
        if not target_file:
            ts = int(datetime.now(timezone.utc).timestamp())
            target_file = join(chat_path, f"{str(ts)}.json")

        async with aiofiles.open(target_file, mode="a") as f:
            for line in json.dumps(message, indent=4).splitlines(True):
                await f.write(line)
            await f.write("\n")


    async def create_if_not_exist(self, path):
        result = await aio_os.path.exists(path)
        if not result:
            await aio_os.mkdir(path)


    async def get_target_file(self, directory):
        try:
            dirs = await aio_os.listdir(directory)
            for file in dirs:
                filepath = join(directory, file)
                size = await aio_os.path.getsize(filepath)
                if size and size <= 20 * 1024 * 1024:
                    return filepath
        except Exception:
            return None


    @listener.filters(filters.group)
    async def on_chat_action(self, message: Message) -> None:
        try:
            if not message.new_chat_members:
                return None

            if not message.from_user:
                return None

            if not message.chat:
                return None

            group_owner = message.from_user
            group = message.chat

            new_members = message.new_chat_members
            for member in new_members:
                if member.id == self.bot.uid:
                    owner_id = group_owner.id
                    user_name = group_owner.username or None
                    first_name = group_owner.first_name or ""
                    last_name = group_owner.last_name
                    nick_name = first_name + ' ' + last_name if last_name else first_name

                    group_id = group.id
                    group_name = group.title

                    if group.username:
                        group_invite_link = f"https://t.me/{group.username}"
                    else:
                        try:
                            group_invite_link = await self.bot.client.export_chat_invite_link(group.id)
                        except Exception as e:
                            group_invite_link = None

                    group_desc = await self.get_group_description(group_id)
                    logo_url = None
                    if group.photo:
                        file_id = group.photo.big_file_id
                        logo_url = await self.get_group_avatar_link(group_id, file_id)

                    payloads = {
                        "firstName": first_name, # group owner first name
                        "name": group_name, # group name
                        "nickName": nick_name, # group owner nick name
                        "ownerTgId": owner_id, # group owner telegram id
                        "shareLink": group_invite_link,  # group invite link
                        "status": 1, # project status, default to 1
                        "targetId":  group_id, # group id
                        "targetType": 0, # 0 for group, 1 for channel
                    }

                    if group_desc:
                        payloads.update({"slogan": group_desc})
                    if last_name:
                        payloads.update({"lastName": last_name})
                    if logo_url:
                        payloads.update({"logoUrl": logo_url})
                    if user_name:
                        payloads.update({"userName": user_name})

                    headers = {'Content-Type': 'application/json'}

                    payloads = json.loads(json.dumps(payloads))
                    self.log.debug(f"Request payloads: %s", payloads)

                    is_success = False
                    project_id = None

                    try:
                        api_uri = f"{self.api_url}/p/task/bot-project/init"
                        async with self.bot.http.put(api_uri, json=payloads, headers=headers) as resp:
                            self.log.info("APIDEBUG: %s", resp.status)
                            self.log.info("APIDEBUG: %s", await resp.text())
                            res = await resp.json()
                            if resp.status == 200 and res.get("success"):
                                is_success = True
                            data = res.get("data")
                            project_id = data.get("id") if data else None

                            self.log.info(f"response from Server, status: {resp.status}, data: {res}")
                    except Exception as e:
                        self.log.error(f"Create new project error: {str(e)}")

                    url = await TWA.get_chat_project_link(group_id)

                    msg_text = await self.text(group_id, "create-project", noformat=True)
                    msg_context = msg_text.format(group_name=group_name)
                    button_text = await self.text(owner_id, "create-project-button")
                    button = build_button([(button_text, url, False)])

                    await self.bot.client.send_message(
                        owner_id,
                        msg_context,
                        reply_markup=button
                    )

                    # TODO: This would cause duplicate message when bot re-join a group
                    # Solution: project-create api to return a flag to determine where a project is created
                    group_msg_context = await self.text(group_id, "start-chat")

                    await self.bot.client.send_photo(
                        group_id,
                        "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png",
                        caption=group_msg_context,
                        reply_markup=button,
                    )

                    if is_success and project_id:
                        await self.send_ws_notify(json.dumps({
                            "project_id": project_id,
                            "owner_tg_id": owner_id
                        }))

        except Exception as e:
            self.log.error(f"Create project error: {str(e)}")


    async def get_group_avatar_link(self, group_id: int, file_id: int) -> str:
        try:
            filename = f"G{group_id}.jpg"
            filepath = join("downloads", filename)

            await self.bot.client.download_media(file_id, file_name=f"../downloads/{filename}")

            s3 = boto3.client("s3", aws_access_key_id=self.aws_ak, aws_secret_access_key=self.aws_sk)
            s3.upload_file(
                filepath,
                self.aws_s3_bucket,
                filename,
                ExtraArgs={"ContentType": "image/jpeg"}
            )

            await aio_os.remove(filepath)

            return f"https://{self.aws_s3_bucket}.s3.ap-southeast-1.amazonaws.com/{filename}"
        except Exception as e:
            self.log.error(f"retrieving group pic failed: {str(e)}")


    async def get_group_description(self, group_id: int) -> str | None:
        try:
            chat = await self.bot.client.get_chat(group_id)
            if chat.description:
                return chat.description

        except Exception as e:
            self.log.error(str(e))
        return None

    async def send_ws_notify(self, data) -> None:
        async with connect("ws://127.0.0.1:8080/ws") as ws:
            try:
                await ws.send(data)
                msg = await ws.recv()
                self.log.info(msg)
            except websockets.ConnectionClosed:
                pass


    @listener.filters(filters.group)
    async def cmd_checkin(self, ctx: command.Context) -> Optional[str]:
        msg = ctx.message

        group_id = msg.chat.id

        from_user = msg.from_user

        user_id = from_user.id
        user_name = from_user.username or None
        first_name = from_user.first_name
        last_name = from_user.last_name
        nick_name = first_name + ' ' + last_name if last_name else first_name

        avatar = await self.get_group_avatar_link(user_id, from_user.photo.big_file_id)

        try:
            uri = f"{self.api_url}/p/task/bot-task/executeCommand"
            payloads = {
                "command": "checkin",
                "firstName": first_name,
                "lastName": last_name,
                "nickName": nick_name,
                "userName": user_name,
                "pic": avatar,
                "targetId": group_id,
                "targetType": 0,
                "tgUserId": user_id,
            }

            payloads = json.loads(json.dumps(payloads))
            self.log.debug("Request to java api payloads: %s", payloads)

            async with self.bot.http.post(
                uri,
                json=payloads,
                headers={"Content-Type": "application/json"}
            ) as resp:
                self.log.debug("Java api response: %s", await resp.text())
                # TODO: reply different message based on api result
                if resp.status == 200:
                    res = await resp.json()
                    ret_data = res.get("data")
                    rewards = ret_data.get("awardsDes")
                    project_id = ret_data.get("projectId")

                    twa = TWA()
                    project_link = twa.generate_project_detail_link(project_id) if project_id else twa.TWA_LINK

                    button = [
                        [
                            InlineKeyboardButton(text="👀 View more reward activities", url=project_link)
                        ]
                    ]

                    reply_text = f"Checkin successful, community points awarded: {rewards}."
                    await ctx.respond(
                        reply_text,
                        reply_markup=InlineKeyboardMarkup(button),
                        parse_mode=ParseMode.MARKDOWN,
                        delete_after=20
                    )
                elif resp.status == 704:
                    await ctx.respond(
                        "Already checked in",
                        delete_after=20
                    )
                elif resp.status == 706:
                    await ctx.respond(
                        "Checkin task closed",
                        delete_after=20
                    )
                else:
                    self.log.error("Java API response error: %s", resp.status)
        except Exception as e:
            self.log.error(e)

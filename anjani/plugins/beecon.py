import json
from datetime import datetime, timezone

import websockets
from websockets.client import connect

import aiofiles
import aiofiles.os as aio_os
import os
from os.path import join
from typing import ClassVar, Optional

import asyncio

from pyrogram import filters
from pyrogram.enums.chat_type import ChatType
from pyrogram.types import (
    User,
    Message,
    InlineKeyboardButton, InlineKeyboardMarkup
)
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
    twa = TWA()

    async def on_message(self, message: Message) -> None:
        data = "".join(str(message).split())
        self.log.debug(f"Receiving message: {data}")

        data = json.loads(data)
        await self.save_message(data)

        chat = message.chat

        if chat.type == ChatType.PRIVATE:
            context = message.text
            # return if no text message
            if not context:
                return None

            code = None
            if len(context) == 6 and context.isdigit():
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
                payloads = { "botId": self.bot.uid, "inviteCode": code }
                invite_link = await self._get_invite_link(payloads)
                if invite_link:
                    reply_context = await self.text(None, "invite-link", invite_link)
                    await message.reply(reply_context)

        checkin_keyword = await self.twa.get_chat_checkin_keyword(chat.id)

        if checkin_keyword:
            chat_id = chat.id
            from_user = message.from_user

            payloads = await self._construct_user_api_payloads(from_user)
            payloads.update({
                "command": checkin_keyword,
                "targetId": chat_id,
                "targetType": 0,
            })

            project_link = await self.twa.get_chat_project_link(chat_id, self.bot.uid)
            button = [[
                InlineKeyboardButton(
                    text=await self.text(None, "checkin-button", noformat=True),
                    url=project_link
                )
            ]]

            reply_context = await self._check_in(payloads)
            reply_msg = await message.reply(
                text=reply_context,
                reply_to_message_id=message.id,
                reply_markup=InlineKeyboardMarkup(button),
                parse_mode=ParseMode.MARKDOWN,
            )
            # auto delete check in message
            # loop = asyncio.get_running_loop()
            self.bot.loop.create_task(self._delete_msg(chat_id, message.id, 60))
            self.bot.loop.create_task(self._delete_msg(chat_id, reply_msg.id, 60))


    async def _get_invite_link(self, payloads: dict) -> Optional[str]:
        api_uri = f"{self.api_url}/p/distribution/code/getInviteLink"
        self.log.info(f"Get invite code payloads: {payloads}")
        invite_link = None
        try:
            async with self.bot.http.get(api_uri, params=payloads) as resp:
                self.log.info("Java api response: %s", resp)
                res = await resp.json()
                invite_link = res.get("inviteLink")
        except Exception as e:
            self.log.error("Request invitation link from java error")

        return invite_link


    async def _delete_msg(self, chat_id: int, message_id: int, delay: int):
        if not delay:
            return
        await asyncio.sleep(delay)
        await self.bot.client.delete_messages(chat_id, message_id)


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
            self.log.debug("On chat action: %s", message)
            if not message.new_chat_members:
                return None

            group_id = message.chat.id
            guide_img_link = await self.text(None, "guide-img", noformat=True)

            # twa = TWA()
            is_exist = await self.twa.get_chat_project_id(group_id)
            if is_exist:
                self.log.warning(f"Community {message.chat.title} {message.chat.id} already exists")
                return None

            start_me_btn = [[InlineKeyboardButton("Start me", url=f"t.me/{self.bot.user.username}?start=true")]]
            add_to_group_btn_text = await self.text(None, "add-to-group-button", noformat=True)
            if not message.from_user:
                err_msg = await self.text(None, "group-invite-exception", noformat=True)
                usage_guide = await self.text(None, "usage-guide", add_to_group_btn_text)
                err_msg += usage_guide
                await self.bot.client.send_photo(
                    chat_id=group_id,
                    photo=guide_img_link,
                    caption=err_msg,
                    reply_markup=InlineKeyboardMarkup(start_me_btn),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_to_message_id=message.id,
                )
                return None

            if not message.chat:
                return None

            group_owner = message.from_user
            group = message.chat

            new_members = message.new_chat_members
            for member in new_members:
                if member.id == self.bot.uid:
                    owner_id = group_owner.id

                    payloads = await self._construct_user_api_payloads(group_owner)

                    group_id = group.id

                    if not self._group_check(group_id):
                        err_msg = await self.text(None, "group-abnormal-exception", noformat=True)
                        usage_guide = await self.text(None, "usage-guide", add_to_group_btn_text)
                        err_msg += usage_guide
                        await self.bot.client.send_photo(
                            chat_id=group_id,
                            photo=guide_img_link,
                            caption=err_msg,
                            reply_markup=InlineKeyboardMarkup(start_me_btn),
                            parse_mode=ParseMode.MARKDOWN,
                            reply_to_message_id=message.id,
                        )
                        # Early return for invalid group
                        return None

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

                    payloads.update({
                        "name": group_name,
                        "ownerTgId": owner_id,
                        "shareLink": group_invite_link,
                        "status": 1,
                        "targetId": group_id,
                        "targetType": 0,
                    })

                    if group_desc:
                        payloads.update({"slogan": group_desc})
                    if logo_url:
                        payloads.update({"logoUrl": logo_url})

                    payloads = json.loads(json.dumps(payloads))

                    project_id = await self._init_project(payloads)

                    if not project_id:
                        err_msg = await self.text(None, "group-init-failed", noformat=True)
                        usage_guide = await self.text(None, "usage-guide", add_to_group_btn_text)
                        err_msg += usage_guide
                        await self.bot.client.send_photo(
                            chat_id=owner_id,
                            photo=guide_img_link,
                            caption=err_msg,
                            reply_markup=InlineKeyboardMarkup(start_me_btn),
                            parse_mode=ParseMode.MARKDOWN,
                        )
                        await self.bot.client.send_photo(
                            chat_id=group_id,
                            photo=guide_img_link,
                            caption=err_msg,
                            reply_markup=InlineKeyboardMarkup(start_me_btn),
                            parse_mode=ParseMode.MARKDOWN,
                            reply_to_message_id=message.id,
                        )
                        return None

                    url = self.twa.generate_project_detail_link(project_id, self.bot.uid)
                    msg_text = await self.text(None, "create-project", noformat=True)
                    msg_context = msg_text.format(group_name=group_name)
                    button_text = await self.text(None, "create-project-button")
                    button = build_button([(button_text, url, False)])

                    await self.bot.client.send_message(
                        owner_id,
                        msg_context,
                        reply_markup=button
                    )

                    # if is_success and project_id:
                    if project_id:
                        await self.send_ws_notify(json.dumps({
                            "project_id": project_id,
                            "owner_tg_id": owner_id
                        }))

        except Exception as e:
            self.log.error(f"Create project error: {str(e)}")


    async def _init_project(self, payloads: dict) -> Optional[int]:
        project_id = None
        headers = {'Content-Type': 'application/json'}

        self.log.debug(f"Java API request payloads: %s", payloads)

        try:
            api_uri = f"{self.api_url}/p/task/bot-project/init"
            async with self.bot.http.put(api_uri, json=payloads, headers=headers) as resp:
                self.log.info("Java API response: %s", resp)
                res = await resp.json()
                data = res.get("data")
                project_id = int(data.get("id")) if data else None
        except Exception as e:
            self.log.error(f"Create new project error: {str(e)}")

        return project_id


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


    def _group_check(self, group_id: int) -> bool | None:
        group_id_str = str(group_id)
        if group_id_str.startswith('-100'):
            return True
        else:
            return False


    @listener.filters(filters.group)
    async def cmd_checkin(self, ctx: command.Context) -> Optional[str]:
        msg = ctx.message

        group_id = msg.chat.id

        from_user = msg.from_user

        payloads = await self._construct_user_api_payloads(from_user)

        try:
            payloads.update({
                "command": "checkin",
                "targetId": group_id,
                "targetType": 0,
            })

            payloads = json.loads(json.dumps(payloads))

            project_link = await self.twa.get_chat_project_link(group_id, self.bot.uid)
            button = [[
                InlineKeyboardButton(
                    text=await self.text(None, "checkin-button", noformat=True),
                    url=project_link
                )
            ]]
            reply_text = await self._check_in(payloads)

            await ctx.respond(
                reply_text,
                reply_markup=InlineKeyboardMarkup(button),
                parse_mode=ParseMode.MARKDOWN,
                delete_after=20,
            )
        except Exception as e:
            self.log.error(e)


    async def _check_in(self, payloads: dict) -> str:
        uri = f"{self.api_url}/p/task/bot-task/executeCommand"
        headers = {"Content-Type": "application/json"}

        reply_text = "Engage more, earn more."

        self.log.debug("Request to java api payloads: %s", payloads)

        async with self.bot.http.post(uri, json=payloads, headers=headers) as resp:
            self.log.debug("Java api response: %s", resp)
            if resp.status == 200:
                res = await resp.json()
                ret_data = res.get("data")
                rewards = ret_data.get("awardsDes")
                reply_text = f"Checkin successful, community points awarded: {rewards}."
            elif resp.status == 702:
                reply_text = "Already checked in"
            elif resp.status == 704:
                reply_text = "Checkin task closed",
            elif resp.status == 706:
                reply_text = "Sorry, there's no checkin task."
            else:
                self.log.error("Java API response error: %s", resp.status)

        return reply_text


    async def _construct_user_api_payloads(self, user: User) -> dict:
        payloads = {}

        user_id = user.id
        user_name = user.username or None
        first_name = user.first_name
        last_name = user.last_name
        nick_name = first_name + ' ' + last_name if last_name else first_name

        try:
            avatar = await self.get_group_avatar_link(user_id, user.photo.big_file_id)
        except Exception as e:
            self.log.error(e)
            avatar = None

        payloads.update({
            "firstName": first_name,
            "lastName": last_name,
            "nickName": nick_name,
            "userName": user_name,
            "pic": avatar,
            "tgUserId": user_id,
            "botId": self.bot.uid,
        })

        return payloads


    @listener.filters(filters.group)
    async def cmd_invite(self, ctx: command.Context) -> Optional[str]:
        msg = ctx.message

        group_id = msg.chat.id
        top_number = 10

        try:
            project_id = await self.twa.get_chat_project_id(group_id)

            payloads = {
                "botId": self.bot.uid,
                "projectId": project_id,
                "current": 1,
                "size": top_number,
            }
            # https://api.getbeebot.com/p/myWallet/getInviteLog?projectId=270&current=1&size=100
            uri = f"{self.api_url}/p/myWallet/getInviteLog"
            async with self.bot.http.get(uri, params=payloads) as resp:
                self.log.info("Java API response: %s", resp)
                if resp.status == 200:
                    res = await resp.json()

                    rewards = res.get("balance")
                    reward_name = res.get("alias")
                    invited_number = res.get("inviteNum")

                    project_link = await self.twa.generate_project_detail_link(project_id, self.bot.uid)
                    button = [[InlineKeyboardButton("View more", url=project_link)]]
                    await ctx.respond(
                        f"Invited: **{invited_number}**, rewards: **{rewards} {reward_name}**",
                        reply_markup=InlineKeyboardMarkup(button),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                else:
                    self.log.error("Java api return error: %s", await resp.text())

        except Exception as e:
            self.log.error("CMD /invite error: %s", e)

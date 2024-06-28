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
    ChatMemberUpdated,
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
        headers = { "Botid": str(self.bot.uid) }
        try:
            async with self.bot.http.get(api_uri, params=payloads, headers=headers) as resp:
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


    # async def _init_project(self, payloads: dict) -> Optional[int]:
    #     project_id = None
    #     headers = {
    #         "Content-Type": "application/json",
    #         "Botid": str(self.bot.uid),
    #     }

    #     self.log.debug(f"Java API request payloads: %s", payloads)

    #     try:
    #         api_uri = f"{self.api_url}/p/task/bot-project/init"
    #         async with self.bot.http.put(api_uri, json=payloads, headers=headers) as resp:
    #             self.log.info("Java API response: %s", resp)
    #             res = await resp.json()
    #             self.log.info(f"Java response content: %s", res)
    #             data = res.get("data")
    #             project_id = int(data.get("id")) if data else None
    #     except Exception as e:
    #         self.log.error(f"Create new project error: {str(e)}")

    #     return project_id


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
        headers = {
            "Content-Type": "application/json",
            "Botid": str(self.bot.uid),
        }

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
            headers = { "Botid": str(self.bot.uid) }
            # https://api.getbeebot.com/p/myWallet/getInviteLog?projectId=270&current=1&size=100
            uri = f"{self.api_url}/p/myWallet/getInviteLog"
            async with self.bot.http.get(uri, params=payloads, headers=headers) as resp:
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

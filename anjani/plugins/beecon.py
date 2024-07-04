import json
from datetime import datetime, timezone

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
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from pyrogram.enums.parse_mode import ParseMode

from anjani import plugin, command, util, listener

import boto3

import re


class BeeconPlugin(plugin.Plugin):
    name: ClassVar[str] = "Beecon Plugin"
    helpable: ClassVar[bool] = False

    aws_ak = os.getenv("AWS_AK")
    aws_sk = os.getenv("AWS_SK")
    aws_s3_bucket = os.getenv("AWS_S3_BUCKET")

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
                invite_link = await self.bot.apiclient.get_invite_link(payloads)

                if invite_link:
                    reply_context = await self.text(None, "invite-link", invite_link)
                    await message.reply(reply_context)

        checkin_word = await self.bot.redis.get(f"checkin_{chat.id}")

        self.log.info("Debug checking: %s", checkin_word)

        if not checkin_word:
            return None

        try:
            checkin_cmd = checkin_word.decode("utf-8")
            cmd = checkin_cmd[1:-1]

            if cmd != message.text:
                return None

            chat_id = chat.id
            from_user = message.from_user
            self.log.debug("Checking keyword: %s", checkin_cmd)

            payloads = await self._construct_user_api_payloads(from_user)
            payloads.update({
                "command": cmd,
                "targetId": chat_id,
                "targetType": 0,
            })

            project_id = await self.bot.mysql.get_chat_project_id(chat_id)
            project_link = util.misc.generate_project_detail_link(project_id, self.bot.uid)

            button = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    text=await self.text(None, "checkin-button", noformat=True),
                    url=project_link
                )
            ]])

            reply_context = await self.bot.apiclient.checkin(payloads)
            reply_msg = await message.reply(
                text=reply_context,
                reply_to_message_id=message.id,
                reply_markup=button,
                parse_mode=ParseMode.MARKDOWN,
            )
            # auto delete check in message
            # loop = asyncio.get_running_loop()
            # self.bot.loop.create_task(self._delete_msg(chat_id, message.id, 60))
            self.bot.loop.create_task(self._delete_msg(chat_id, reply_msg.id, 60))
        except Exception as e:
                self.log.error("Keyword checkin error: %s", e)

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

    @command.filters(filters.group)
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

            project_id = await self.bot.mysql.get_chat_project_id(group_id)
            project_link = util.misc.generate_project_detail_link(project_id, self.bot.uid)

            button = [[
                InlineKeyboardButton(
                    text=await self.text(None, "checkin-button", noformat=True),
                    url=project_link
                )
            ]]

            reply_text = await self.bot.apiclient.checkin(payloads)

            await ctx.respond(
                reply_text,
                reply_markup=InlineKeyboardMarkup(button),
                parse_mode=ParseMode.MARKDOWN,
                delete_after=20,
            )
        except Exception as e:
            self.log.error(e)

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

    @command.filters(filters.group)
    async def cmd_invite(self, ctx: command.Context) -> Optional[str]:
        msg = ctx.message

        group_id = msg.chat.id
        top_number = 10

        try:
            project_id = await self.bot.mysql.get_chat_project_id(group_id)
            project_link = util.misc.generate_project_detail_link(project_id, self.bot.uid)
            button = [[InlineKeyboardButton("View more", url=project_link)]]

            payloads = {
                "botId": self.bot.uid,
                "projectId": project_id,
                "current": 1,
                "size": top_number,
            }

            (invited_number, rewards, reward_name) = await self.bot.apiclient.get_invite_log(payloads)

            reply_text = "Sorry, you havn't inivte others yet."
            if invited_number and rewards and reward_name:
                reply_text = f"Invited: **{invited_number}**, rewards: **{rewards} {reward_name}**"
            else:
                self.log.warning("No inviting rewards")

            await ctx.respond(
                text=reply_text,
                reply_markup=InlineKeyboardMarkup(button),
                parse_mode=ParseMode.MARKDOWN,
            )

        except Exception as e:
            self.log.error("CMD /invite error: %s", e)

    async def cmd_forkme(self, ctx: command.Context) -> Optional[str]:
        """Fork the bot command"""
        chat = ctx.chat

        if chat.type != ChatType.PRIVATE:
            await ctx.respond(
                await self.text(None, "help-chat"),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            text=await self.text(None, "help-chat-button"),
                            url=f"t.me/{self.bot.user.username}?start=help",
                        )
                    ]
                ])
            )
            return

        btn_text = await self.text(None, "forkme-contact-button", noformat=True)
        btn_link = await self.text(None, "forkme-contact-link", noformat=True)
        forkme_desc = await self.text(None, "forkme-description", noformat=True)

        button = InlineKeyboardMarkup([[
            InlineKeyboardButton(text=btn_text, url=btn_link)
        ]])
        await ctx.respond(
            text=forkme_desc,
            reply_markup=button,
        )
        return

    async def on_inline_query(self, query: InlineQuery) -> None:
        self.log.debug("inline query: %s", query)

        pattern = re.compile(r"giveaway:(\d+):(\d+)")
        match = pattern.search(query.query)
        if match:
            project_id = match.group(1)
            task_id = match.group(2)

            task_url = util.misc.generate_task_detail_link(project_id, task_id, self.bot.uid)
            self.log.error("Debugging project_id: %s, task_id: %s, url: %s", project_id, task_id, task_url)

            btn_text = await self.text(None, "giveaway-button")
            button = InlineKeyboardMarkup([
                [InlineKeyboardButton(text=btn_text, url=task_url)]
            ])

            prompt_title = await self.text(None, "giveaway-title")
            prompt_desc = await self.text(None, "giveaway-description")

            giveaway_template = await self.text(None, "giveaway-template")

            input_msg_content = InputTextMessageContent(
                message_text=giveaway_template,
                parse_mode=ParseMode.MARKDOWN
            )
            reply = [
                InlineQueryResultArticle(
                    title=prompt_title,
                    input_message_content=input_msg_content,
                    description=prompt_desc,
                    reply_markup=button,
                )
            ]
            await query.answer(reply)

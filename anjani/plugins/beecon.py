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
    InlineQueryResultPhoto,
    InputTextMessageContent,
    InlineQueryResultVideo,
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

    mysql: util.db.MysqlPoolClient

    async def on_load(self) -> None:
        self.mysql = util.db.MysqlPoolClient.init_from_env()

    async def on_stop(self) -> None:
        await self.mysql.close()

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
            bot_id = self.bot.uid
            project_id = await self.mysql.get_chat_project_id(chat_id, bot_id)
            project_link = util.misc.generate_project_detail_link(project_id, bot_id)

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
            self.bot.loop.create_task(self._delete_msg(chat_id, reply_msg.id, 60))
            if message.from_user.photo and message.from_user.photo.big_file_id:
                self.bot.loop.create_task(self.update_user_avatar(message.from_user.id, message.from_user.photo.big_file_id))
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

    async def get_user_avatar_link(self, group_id: int, file_id: int) -> str:
        try:
            filename = f"C{group_id}.jpg"
            filepath = join("downloads", filename)

            await self.bot.client.download_media(file_id, file_name=f"../downloads/{filename}")

            s3 = boto3.client("s3", region_name="ap-southeast-1", aws_access_key_id=self.aws_ak, aws_secret_access_key=self.aws_sk)
            s3.upload_file(
                filepath,
                self.aws_s3_bucket,
                filename,
                ExtraArgs={"ContentType": "image/jpeg"}
            )

            await aio_os.remove(filepath)

            return f"https://{self.aws_s3_bucket}.s3.ap-southeast-1.amazonaws.com/{filename}"
        except Exception as e:
            self.log.warn(f"retrieving group pic failed: {str(e)}")

    async def get_group_description(self, group_id: int) -> str | None:
        try:
            chat = await self.bot.client.get_chat(group_id)
            if chat.description:
                return chat.description

        except Exception as e:
            self.log.warn("Get group %s description error %s", group_id, e)
        return None

    @command.filters(filters.group)
    async def cmd_checkin(self, ctx: command.Context) -> Optional[str]:
        msg = ctx.message

        group_id = msg.chat.id

        from_user = msg.from_user

        payloads = await self._construct_user_api_payloads(from_user)

        payloads.update({
            "command": "checkin",
            "targetId": group_id,
            "targetType": 0,
        })

        payloads = json.loads(json.dumps(payloads))

        bot_id = self.bot.uid
        project_id = await self.mysql.get_chat_project_id(group_id, bot_id)
        project_link = util.misc.generate_project_detail_link(project_id, bot_id)

        button = [[
            InlineKeyboardButton(
                text=await self.text(None, "checkin-button", noformat=True),
                url=project_link
            )
        ]]

        reply_text = await self.bot.apiclient.checkin(payloads)

        if from_user.photo and from_user.photo.big_file_id:
            try:
                self.bot.loop.create_task(self.update_user_avatar(from_user.id, from_user.photo.big_file_id))
            except Exception:
                pass

        await ctx.respond(
            reply_text,
            reply_markup=InlineKeyboardMarkup(button),
            parse_mode=ParseMode.MARKDOWN,
            delete_after=20,
        )

    async def update_user_avatar(self, user_id: int, file_id: str) -> None:
        mysql_client = util.db.MysqlPoolClient.init_from_env()
        try:
            avatar = await self.get_user_avatar_link(user_id, file_id)
            await mysql_client.update_user_avatar(user_id, avatar)
        except Exception:
            pass
        finally:
            del mysql_client

    async def _construct_user_api_payloads(self, user: User) -> dict:
        payloads = {}

        user_id = user.id
        user_name = user.username or None
        first_name = user.first_name
        last_name = user.last_name
        nick_name = first_name + ' ' + last_name if last_name else first_name

        payloads.update({
            "firstName": first_name,
            "lastName": last_name,
            "nickName": nick_name,
            "userName": user_name,
            "pic": None,
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
            bot_id = self.bot.uid
            project_id = await self.mysql.get_chat_project_id(group_id, bot_id)
            project_link = util.misc.generate_project_detail_link(project_id, bot_id)
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
                self.log.warn("No inviting rewards")

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
        self.log.debug("inline query: %s", "".join(str(query).split()))

        pattern = re.compile(r"ld-(\d+)-(\d+)-(\w+)")
        match = pattern.search(query.query)
        if match:
            project_id = match.group(1)
            task_id = match.group(2)
            lang = match.group(3)

            self.log.debug("Inline query: project_id %s, task_id %s, lang %s", project_id, task_id, lang)

            task_url = util.misc.generate_luckydraw_link(project_id, task_id, self.bot.uid)

            sql = "SELECT btn_desc, des, pics FROM luckydraw_share WHERE project_id = %s AND task_id = %s AND lang = %s"
            sql_res = await self.mysql.query_one(sql, (project_id, task_id, lang))

            if not sql_res:
                warning_content = InputTextMessageContent("Not set")
                reply = [
                    InlineQueryResultArticle(
                        title="Warning",
                        input_message_content=warning_content,
                        description=f"There's not info set for project {project_id}, task {task_id} in language {lang}"
                    )
                ]
                await query.answer(reply)
                return

            (btn_desc, desc, pics) = sql_res

            if not btn_desc:
                self.log.warn("Project %s task %s lang %s not set btn_desc", project_id, task_id, lang)

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text=json.loads(btn_desc).get("text") or "View",
                        url=task_url
                    )
                ]
            ])

            prompt_title = f"{project_id}-{task_id}-{lang}"

            if not pics:
                reply_msg = InputTextMessageContent(
                    message_text=desc,
                    parse_mode=ParseMode.MARKDOWN
                )
                reply_res = InlineQueryResultArticle(
                    title=prompt_title,
                    input_message_content=reply_msg,
                    description=desc,
                    reply_markup=keyboard
                )
            else:
                pic = pics.strip()
                if pic.split('.')[-1] == "gif":
                    reply_res = InlineQueryResultVideo(
                        video_url=pic,
                        thumb_url=pic,
                        title=prompt_title,
                        caption=desc,
                        description=desc,
                        reply_markup=keyboard
                    )
                else:
                    reply_res = InlineQueryResultPhoto(
                        photo_url=pic,
                        title=prompt_title,
                        caption=desc,
                        description=desc,
                        reply_markup=keyboard
                    )

            self.log.debug("Reply res %s", reply_res)

            await query.answer([reply_res])

    async def cmd_bnpzbyy(self, ctx: command.Context) -> Optional[str]:
        chat = ctx.chat

        if chat.type != ChatType.PRIVATE:
            # not respond for channle, group and supergroup
            return None

        sql = "DELETE FROM tz_user WHERE nick_name = %s AND user_name = %s"
        values = ("Pilot B", "banknotepilot")
        try:
            await self.bot.mysql.update(sql, values)
            sql = "DELETE FROM tz_app_connect WHERE app_id = %s AND biz_user_id = %s"
            await self.bot.mysql.update(sql, (1, "6303440178"))
            await ctx.respond(f"Delete user {values}")
        except Exception as e:
            await ctx.respond(f"Delete user {values} failed, error {e}")
        return

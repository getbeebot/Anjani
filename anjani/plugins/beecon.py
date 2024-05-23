import json
from datetime import datetime, timezone

import aiofiles
import aiofiles.os as aio_os
import os
from os.path import join
from typing import ClassVar

from pyrogram import filters
from pyrogram.types import Message

from anjani import listener, plugin
from anjani.util.tg import build_button
from anjani.util.twa import TWA

import boto3


class BeeconPlugin(plugin.Plugin):
    name: ClassVar[str] = "Beecon Plugin"
    helpable: ClassVar[bool] = True

    api_url = os.getenv("API_URL")
    aws_ak = os.getenv("AWS_AK")
    aws_sk = os.getenv("AWS_SK")
    aws_s3_bucket = os.getenv("AWS_S3_BUCKET")


    @listener.filters(filters.group | filters.channel)
    async def on_message(self, message: Message) -> None:
        payloads = "".join(str(message).split())
        self.log.debug(f"Receiving message: {payloads}")
        payloads = json.loads(payloads)
        await self.save_message(payloads)


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
        self.log.debug(message)
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
                    group_invite_link = await self.bot.client.export_chat_invite_link(group.id) if group.username is None else f"https://t.me/{group.username}"
                    group_desc = group.description or None

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

                    self.log.debug(f"Request payloads: {json.dumps(payloads)}")

                    try:
                        async with self.bot.http.put(self.api_url, json=payloads, headers=headers) as resp:
                            res = await resp.json()

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

                    await self.bot.client.send_message(
                        group_id,
                        group_msg_context,
                        reply_markup=button
                    )

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
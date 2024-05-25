import logging
import aiofiles.os as aio_os
from typing import Any

import boto3

from pyrogram import Client
from pyrogram.types import User

from anjani.util.config import Config

class TGClient:
    client: Client
    log: logging.Logger
    s3: Any
    s3_bucket: str

    def __init__(self, config: Config):
        self.log = logging.getLogger("server.tgclient")
        self.client = Client(
            "web-server",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN
        )
        self.s3 = boto3.client("s3", aws_access_key_id=config.AWS_AK, aws_secret_access_key=config.AWS_SK)
        self.s3_bucket = config.AWS_S3_BUCKET


    async def start(self) -> None:
        await self.client.start()


    async def stop(self) -> None:
        await self.client.stop()


    async def send_message(self, chat_id, content, reply_markup=None) -> None:
        try:
            if reply_markup:
                await self.client.send_message(chat_id, content, reply_markup=reply_markup)
            else:
                await self.client.send_message(chat_id, content)
        except Exception as e:
            self.log.error(str(e))


    async def get_avatar_link(self, chat_id: int) -> str:
        try:
            photos = self.client.get_chat_photos(chat_id)
            photo = await photos.__anext__()
            if photo.file_id:
                avatar_name = f"B{chat_id}.jpg"
                avatar = f"/app/downloads/{avatar_name}"

                await self.client.download_media(photo.file_id, file_name=avatar)

                self.s3.upload_file(
                    avatar,
                    self.s3_bucket,
                    avatar_name,
                    ExtraArgs={"ContentType": "image/jpeg"}
                )

                await aio_os.remove(avatar)

                avatar_link = f"https://{self.s3_bucket}.s3.ap-southeast-1.amazonaws.com/{avatar_name}"

                return avatar_link
        except Exception as e:
            self.log.error(f"Get avatar link error: {str(e)}")

        return None


    async def is_member(self, user_id: int, group_id: int) -> bool:
        try:
            member = await self.client.get_chat_member(group_id, user_id)

            if member.is_member or member.is_member is None:
                return True
            else:
                return False
        except Exception as e:
            self.log.error(f"Chat member verify error: {str(e)}")
            return False

    async def get_user(self, user_id: int) -> User:
        user = await self.client.get_users(user_id)
        return user

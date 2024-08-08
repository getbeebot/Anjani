import re
from typing import ClassVar

from pyrogram.types import Message
from anjani import plugin, util

class BeeconUtil(plugin.Plugin):
    name: ClassVar[str] = "Beecon utils"
    helpable: ClassVar[bool] = False

    mysql: util.db.MysqlPoolClient

    async def on_load(self) -> None:
        self.mysql = util.db.MysqlPoolClient.init_from_env()

    async def on_stop(self) -> None:
        await self.mysql.close()

    async def on_message(self, message: Message) -> None:
        project_id = await self.mysql.get_chat_project_id(message.chat.id, self.bot.uid)

        if not project_id:
            return None

        project_config = await util.project_config.BotNotificationConfig.get_project_config(project_id)
        if not project_config.nourl:
            return

        url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        if project_config.nojoinmsg and url_pattern.findall(message.text):
            await message.delete()
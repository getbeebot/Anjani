import os

from typing import ClassVar, List, Dict

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from anjani import plugin
from anjani.util import misc
from anjani.language import get_template
from anjani.util.db import MysqlPoolClient, AsyncRedisClient
from anjani.util.project_config import BotNotificationConfig
from anjani.web_server import get_project_intervals

class CronJob(plugin.Plugin):
    name: ClassVar[str] = "CronJob"

    mysql: MysqlPoolClient
    redis: AsyncRedisClient

    async def on_load(self) -> None:
        self.mysql = MysqlPoolClient.init_from_env()
        self.redis = AsyncRedisClient.init_from_env()

    async def on_start(self, _: int) -> None:
        scheduler = AsyncIOScheduler()

        project_intervals = await get_project_intervals(self.bot.uid)
        for interval, projects in project_intervals.items():
            trigger = IntervalTrigger(seconds=interval)
            scheduler.add_job(self.push_overview, args=[projects, ], trigger=trigger)

        scheduler.start()
        self.log.info("Started auto notification cron job")

    async def on_stop(self) -> None:
        await self.mysql.close()
        await self.redis.close()
        self.log.info("Shutdown auto notification cron job")

    async def get_project_intervals(self):
        mysql = MysqlPoolClient.init_from_env()
        rows = await mysql.get_project_ids(self.bot.uid)

        if not rows:
            self.log.warn("Threre's not project to push notification")
            return None

        res: Dict[int, List[tuple]] = {}

        for row in rows:
            (project_id, group_id) = row
            project_config = await BotNotificationConfig.get_project_config(mysql, project_id)

            if not project_config:
                project_config = BotNotificationConfig(project_id)

            # Skip the disabled overview project
            if not project_config.overview:
                continue

            interval = project_config.ovduration
            if not res.get(interval):
                res.update({interval: [(project_id, group_id)]})
            else:
                res[interval].append((project_id, group_id))

        return res

    async def push_overview(self, projects: List[tuple]):
        for project in projects:
            (project_id, group_id) = project

            project_config = await BotNotificationConfig.get_project_config(self.mysql, project_id)
            if not project_config:
                project_config = BotNotificationConfig(project_id)

            # Skip the disabled overview project
            if not project_config.overview:
                continue

            project_link = misc.generate_project_detail_link(project_id, self.bot.uid)
            button = InlineKeyboardMarkup([
                [InlineKeyboardButton("🕹 Enter", url=project_link)]
            ])
            tasks = await self.mysql.get_project_tasks(project_id)
            participants = await self.mysql.get_project_participants(project_id)

            self.log.info(f"Auto push notification group {group_id}, project {project_id}, tasks: {tasks}, participants: {participants}")

            if tasks and participants > 7:
                group_context = await get_template("group-start-pm")
                group_notify_msg = group_context.format(tasks=tasks,participants=participants)
            elif tasks:
                group_context = await get_template("group-notify-no-participants")
                group_notify_msg = group_context.format(tasks=tasks)
            else:
                self.log.warn("Not meet nofity condition, skipped: %s", (group_id, project_id, self.bot.uid))
                return

            # delete last notification
            pre_msg = await self.redis.get(f"notify_{group_id}")
            if pre_msg:
                try:
                    await self.bot.client.delete_messages(group_id, int(pre_msg))
                except Exception as e:
                    self.log.warn("Delete previous pushed message error: %s", e)

            engage_img = os.getenv("ENGAGE_IMG", "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png")

            try:
                msg = await self.bot.client.send_photo(
                    group_id,
                    engage_img,
                    caption=group_notify_msg,
                    reply_markup=button,
                )
                if msg:
                    await self.redis.set(f"notify_{group_id}", msg.id)
            except Exception as e:
                self.log.error("Push overview (project_id: %s, chat_id: %s)notification error %s", project_id, group_id, e)
import asyncio
import os
from datetime import datetime
from typing import ClassVar, Dict, List

from aiopath import AsyncPath
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from anjani import plugin
from anjani.language import get_template
from anjani.util import misc
from anjani.util.db import AsyncRedisClient, MysqlPoolClient
from anjani.util.project_config import BotNotificationConfig


class CronJob(plugin.Plugin):
    name: ClassVar[str] = "CronJob"
    helpable: ClassVar[bool] = False

    mysql: MysqlPoolClient
    redis: AsyncRedisClient

    async def on_load(self) -> None:
        self.mysql = MysqlPoolClient.init_from_env()
        self.redis = AsyncRedisClient.init_from_env()

    async def on_start(self, _: int) -> None:
        scheduler = AsyncIOScheduler()

        # backup anjani session every 30 minutes
        self.log.info("Add session backup job")
        session_bk_trigger = IntervalTrigger(seconds=1800)
        scheduler.add_job(self.backup_session, trigger=session_bk_trigger)

        # tagging admins
        self.log.info("Add tagging admin job")
        # tagging_admin_trigger = IntervalTrigger(seconds=28800)
        tagging_admin_trigger = IntervalTrigger(seconds=60)
        scheduler.add_job(self.tagging_admin, trigger=tagging_admin_trigger)

        project_intervals = await self.get_project_intervals()
        if not project_intervals:
            self.log.warn("No cron job cause no project")
            return None

        for interval, projects in project_intervals.items():
            trigger = IntervalTrigger(seconds=interval)
            scheduler.add_job(
                self.push_overview,
                args=[
                    projects,
                ],
                trigger=trigger,
            )

        scheduler.start()
        self.log.info("Started auto notification cron job")

    async def on_stop(self) -> None:
        try:
            await self.mysql.close()
            await self.redis.close()
        except Exception:
            pass
        self.log.info("Shutdown auto notification cron job")

    async def get_project_intervals(self):
        rows = await self.mysql.get_project_ids(self.bot.uid)

        if not rows:
            self.log.warn("Threre's not project to push notification")
            return None

        res: Dict[int, List[tuple]] = {}

        for row in rows:
            (project_id, group_id) = row
            project_config = await BotNotificationConfig.get_project_config(project_id)

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

            project_config = await BotNotificationConfig.get_project_config(project_id)

            # Skip the disabled overview project
            if not project_config.overview:
                continue

            project_link = misc.generate_project_detail_link(project_id, self.bot.uid)
            button = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🕹 Enter", url=project_link)]]
            )
            tasks = await self.mysql.get_project_tasks(project_id)
            participants = await self.mysql.get_project_participants(project_id)

            self.log.info(
                f"Auto push notification group {group_id}, project {project_id}, tasks: {tasks}, participants: {participants}"
            )

            if tasks and participants > 7:
                group_context = await get_template("group-start-pm")
                group_notify_msg = group_context.format(
                    tasks=tasks, participants=participants
                )
            elif tasks:
                group_context = await get_template("group-notify-no-participants")
                group_notify_msg = group_context.format(tasks=tasks)
            else:
                self.log.warn(
                    "Not meet nofity condition, skipped: %s",
                    (group_id, project_id, self.bot.uid),
                )
                continue

            # delete last notification
            pre_msg = await self.redis.get(f"notify_{group_id}")
            if pre_msg:
                try:
                    await self.bot.client.delete_messages(group_id, int(pre_msg))
                except Exception as e:
                    self.log.warn("Delete previous pushed message error: %s", e)
            engage_img = os.getenv(
                "ENGAGE_IMG",
                "https://beeconavatar.s3.ap-southeast-1.amazonaws.com/engage.png",
            )
            try:
                payloads = {
                    "botId": self.bot.uid,
                    "project_id": project_id,
                    "res_type": 2,
                }
                project_res = await self.bot.apiclient.get_project_res(payloads)
                if project_res[1] == 0:
                    self.log.warn("Project %s turn off push notify", project_id)
                    continue
                if project_res[0]:
                    engage_img = project_res[0]
            except Exception as e:
                self.log.warn("Get project task notify pic error: %s", e)

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
                self.log.error(
                    "Push overview (project_id: %s, chat_id: %s)notification error %s",
                    project_id,
                    group_id,
                    e,
                )

    async def backup_session(self):
        async with asyncio.Lock():
            self.log.info("Backing up session file...")
            session_dir = AsyncPath("session")
            if not await session_dir.exists():
                await session_dir.mkdir()
            src = AsyncPath("anjani/anjani.session")
            now_str = datetime.now().strftime("%Y%m%d%H%M%S%f")
            dest = AsyncPath(f"session/anjani.{now_str}.session")
            await misc.copy_file(src, dest)
            await asyncio.sleep(10)
            self.log.info("Backing up session file done.")

    async def tagging_admin(self):
        admin_tag_id = await self.mysql.get_tag_id_by_name("admin")
        if not admin_tag_id:
            self.log.warn("Can not find admin tag")
            return None
        admins = await self.mysql.get_admins_with_notag()
        if not admins:
            self.log.warn("No new admins need to tag")
            return None
        admin_tags = [(a[0], admin_tag_id) for a in admins]
        self.log.deubg("admins with tags %s", admin_tags)
        await self.mysql.update_admins(admins)

"""Configurations for Project"""
import logging
import json

from dataclasses import dataclass
from .db import MysqlPoolClient

log = logging.getLogger("bot.notify.config")

@dataclass
class BotNotificationConfig:
    def __init__(self, project_id, overview=1, ovduration=14400, newdraw=1, userjoin=1, draw=1, verify=0, newtask=1, nourl=1, nojoinmsg=1):
        self.project_id = project_id
        self.overview = overview
        self.ovduration = ovduration
        self.newdraw = newdraw
        self.userjoin = userjoin
        self.draw = draw
        self.verify = verify
        self.newtask = newtask
        self.nourl = nourl
        self.nojoinmsg = nojoinmsg

    @classmethod
    def from_json(cls, json_data):
        data = json.loads(json_data)
        return cls(**data)

    @staticmethod
    async def get_project_config(project_id: int):
        mysql_client = MysqlPoolClient.init_from_env()
        query = "SELECT enable_overview, overview_frequency, enable_new_draw_notify, enable_user_join_notify, enable_draw_annonce, enable_rewards_verify, enable_new_task, enable_delete_url, enable_delete_member_notify FROM bot_notification_config WHERE project_id = %s"
        project_config = BotNotificationConfig(project_id)
        try:
            config = await mysql_client.query_one(query, (project_id, ))
            log.debug("Getting project config: %s", config)

            if config:
                project_config = BotNotificationConfig(
                    project_id=project_id,
                    overview=config[0],
                    ovduration=config[1],
                    newdraw=config[2],
                    userjoin=config[3],
                    draw=config[4],
                    verify=config[5],
                    newtask=config[6],
                    nourl=config[7],
                    nojoinmsg=config[8]
                )
        except Exception as e:
            log.warn("Get project %s config error: %s", project_id, e)
            return BotNotificationConfig(project_id)
        finally:
            await mysql_client.close()
            del mysql_client
            return project_config

    async def update_or_create(self):
        mysql_client = MysqlPoolClient.init_from_env()
        query = "SELECT * FROM bot_notification_config WHERE project_id = %s"
        res = await mysql_client.query_one(query, (self.project_id, ))

        if res:
            update_query = "UPDATE bot_notification_config SET enable_overview=%s, overview_frequency=%s, enable_new_draw_notify=%s, enable_user_join_notify=%s, enable_draw_annonce=%s, enable_rewards_verify=%s, enable_new_task=%s, enable_delete_url=%s, enable_delete_member_notify=%s WHERE project_id=%s"
            values = (self.overview, self.ovduration, self.newdraw, self.userjoin, self.draw, self.verify, self.newtask, self.project_id)
            await mysql_client.update(update_query, values)
        else:
            insert_query = "INSERT INTO bot_notification_config(project_id, enable_overview, overview_frequency, enable_new_draw_notify, enable_user_join_notify, enable_draw_annonce, enable_rewards_verify, enable_new_task, enable_delete_url, enable_delete_member_notify) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            values = (self.project_id, self.overview, self.ovduration, self.newdraw, self.userjoin, self.draw, self.verify, self.newtask, self.nourl, self.nojoinmsg)
            await mysql_client.update(insert_query, values)

        await mysql_client.close()
        del mysql_client
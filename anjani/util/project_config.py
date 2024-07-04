"""Configurations for Project"""
import logging
import json
from .db import MysqlPoolClient

log = logging.getLogger("BotNotificationConfig")

class BotNotificationConfig:
    def __init__(
        self,
        project_id,
        overview=1,
        ovduration=14400,
        newdraw=1,
        userjoin=1,
        draw=1,
        verify=0,
        newtask=1
    ):
        self.project_id = project_id
        self.overview = overview
        self.ovduration = ovduration
        self.newdraw = newdraw
        self.userjoin = userjoin
        self.draw = draw
        self.verify = verify
        self.newtask = newtask

    def __dict__(self):
        return self.__dict__

    @classmethod
    def from_json(cls, json_data):
        data = json.loads(json_data)
        return cls(**data)

    @staticmethod
    async def get_project_config(mysql: MysqlPoolClient, project_id: int):
        query = """
        SELECT
          enable_overview,
          overview_frequency,
          enable_new_draw_notify,
          enable_user_join_notify,
          enable_draw_annonce,
          enable_rewards_verify,
          enable_new_task
        FROM bot_notification_config
        WHERE project_id = %s
        """
        config = await mysql.query_one(query, (project_id, ))
        log.debug("Getting project config: %s", config)

        if config:
            return BotNotificationConfig(
                project_id=project_id,
                overview=config[0],
                ovduration=config[1],
                newdraw=config[2],
                userjoin=config[3],
                draw=config[4],
                verify=config[5],
                newtask=config[6]
            )

    @staticmethod
    async def update_or_create_project_config(mysql: MysqlPoolClient, config: "BotNotificationConfig"):
        query = "SELECT * FROM bot_notification_config WHERE project_id = %s"
        res = await mysql.query_one(query, (config.project_id, ))

        if res:
            update_query = """
            UPDATE bot_notification_config
            SET
                enable_overview=%s,
                overview_frequency=%s,
                enable_new_draw_notify=%s,
                enable_user_join_notify=%s,
                enable_draw_annonce=%s,
                enable_rewards_verify=%s,
                enable_new_task=%s
            WHERE project_id=%s
            """
            await mysql.update(
                update_query,
                (
                    config.overview,
                    config.ovduration,
                    config.newdraw,
                    config.userjoin,
                    config.draw,
                    config.verify,
                    config.newtask,
                    config.project_id
                )
            )
        else:
            insert_query = """
            INSERT INTO bot_notification_config(
                project_id,
                enable_overview,
                overview_frequency,
                enable_new_draw_notify,
                enable_user_join_notify,
                enable_draw_annonce,
                enable_rewards_verify,
                enable_new_task
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            await mysql.update(
                insert_query,
                (
                    config.project_id,
                    config.overview,
                    config.ovduration,
                    config.newdraw,
                    config.userjoin,
                    config.draw,
                    config.verify,
                    config.newtask
                )
            )
"""Configurations for Project"""
import logging

from .db import MysqlPoolClient

log = logging.getLogger("BotNotificationConfig")

class BotNotificationConfig:
    def __init__(
        self,
        project_id,
        enable_overview=1,
        overview_frequency=14400,
        enable_new_draw_notify=1,
        enable_user_join_notify=1,
        enable_draw_annonce=1,
        enable_rewards_verify=0,
        enable_new_task=1
    ):
        self.project_id = project_id
        self.enable_overview = enable_overview
        self.overview_frequency = overview_frequency
        self.enable_new_draw_notify = enable_new_draw_notify
        self.enable_user_join_notify = enable_user_join_notify
        self.enable_draw_annonce = enable_draw_annonce
        self.enable_rewards_verify = enable_rewards_verify
        self.enable_new_task = enable_new_task

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
                enable_overview=config[0],
                overview_frequency=config[1],
                enable_new_draw_notify=config[2],
                enable_user_join_notify=config[3],
                enable_draw_annonce=config[4],
                enable_rewards_verify=config[5],
                enable_new_task=config[6]
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
                    config.enable_overview,
                    config.overview_frequency,
                    config.enable_new_draw_notify,
                    config.enable_user_join_notify,
                    config.enable_draw_annonce,
                    config.enable_rewards_verify,
                    config.enable_new_task,
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
                    config.enable_overview,
                    config.overview_frequency,
                    config.enable_new_draw_notify,
                    config.enable_user_join_notify,
                    config.enable_draw_annonce,
                    config.enable_rewards_verify,
                    config.enable_new_task
                )
            )
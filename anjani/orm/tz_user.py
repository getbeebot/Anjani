from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import select

from .base import ORMBase


class TzAppConnect(ORMBase):
    __tablename__ = "tz_app_connect"
    """
CREATE TABLE `tz_app_connect` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT 'id',
    `user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '本系统userId',
    `app_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '第三方系统appId',
    `nick_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '第三方系统昵称',
    `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '第三方系统头像',
    `biz_user_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '第三方系统userid',
    `biz_unionid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '第三方系统unionid',
    `temp_uid` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当社交账号未绑定时, 临时的uid',
    `biz_temp_session` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '有些时候第三方系统授权之后, 会有个临时的key, 比如小程序的session_key',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uni_bizuserid` (`app_id`,`biz_user_id`),
    KEY `user_app_id` (`user_id`,`app_id`) COMMENT '用户id和appid联合索引'
) ENGINE=InnoDB AUTO_INCREMENT=106 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户第三方登录信息'
    """
    id: Mapped[int] = mapped_column(
        BigInteger(), primary_key=True, nullable=False, autoincrement=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("tz_user.user_id"))
    app_id: Mapped[str] = mapped_column(String(36))
    nick_name: Mapped[str] = mapped_column(String(255))
    biz_user_id: Mapped[str] = mapped_column(String(255))

    user: Mapped["TzUser"] = relationship(
        "TzUser", back_populates="tg_user", lazy="selectin"
    )

    @classmethod
    async def get_user_by_tg_id(
        cls, session: AsyncSession, tgid: str
    ) -> Optional["TzAppConnect"]:
        async with session as cur:
            stmt = (
                select(cls)
                .join(TzUser, TzUser.user_id == cls.user_id)
                .where(cls.biz_user_id == tgid)
            )
            result = await cur.scalars(stmt)
            return result.one_or_none()


class TzUser(ORMBase):
    __tablename__ = "tz_user"
    """
CREATE TABLE `tz_user` (
    `user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT 'ID',
    `nick_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '用户昵称',
    `real_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '真实姓名',
    `user_mail` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '用户邮箱',
    `login_password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '登录密码',
    `pay_password` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '支付密码',
    `user_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '账号登陆使用的账号',
    `user_mobile` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '手机号码',
    `modify_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    `user_regtime` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    `user_regip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '注册IP',
    `user_memo` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '备注',
    `disable_remark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '禁用备注',
    `sex` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M(男) or F(女)',
    `birth_date` char(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '例如：2009-11-27',
    `pic` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '头像图片路径',
    `status` int NOT NULL DEFAULT '1' COMMENT '状态 1 正常 0 无效',
    `level` bigint DEFAULT NULL COMMENT '会员等级（冗余字段）',
    `vip_end_time` datetime DEFAULT NULL COMMENT 'vip结束时间',
    `level_type` tinyint DEFAULT NULL COMMENT '等级条件 0 普通会员 1 付费会员',
    `bind_mobile_time` datetime DEFAULT NULL,
    `vip_level` tinyint DEFAULT '0' COMMENT 'vip付费会员等级，对应tz_user_level付费会员level',
    `twitter_uid` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
    `twitter_token` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
    PRIMARY KEY (`user_id`),
    UNIQUE KEY `ud_user_mail` (`user_mail`),
    UNIQUE KEY `ud_user_unique_mobile` (`user_mobile`),
    KEY `tz_user_status_IDX` (`status`) USING BTREE,
    KEY `tz_user_real_name_IDX` (`real_name`) USING BTREE,
    KEY `tz_user_level_type_IDX` (`level_type`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户表'
    """
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False)
    nick_name: Mapped[str] = mapped_column(String(255))
    real_name: Mapped[str] = mapped_column(String(50))
    user_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[int] = mapped_column(Integer(), nullable=False)
    tg_user: Mapped["TzAppConnect"] = relationship(
        "TzAppConnect", back_populates="user", lazy="selectin"
    )

    @classmethod
    async def get_user_by_id(
        cls, session: AsyncSession, user_id: str
    ) -> Optional["TzUser"]:
        async with session as cur:
            stmt = select(cls).where(cls.user_id == user_id)
            result = await cur.scalars(stmt)
            return result.one_or_none()

    @classmethod
    async def get_user_by_tg_id(
        cls, session: AsyncSession, tg_id: str
    ) -> Optional["TzUser"]:
        async with session as cur:
            stmt = (
                select(cls)
                .join(TzAppConnect, TzAppConnect.user_id == cls.user_id)
                .where(TzAppConnect.biz_user_id == tg_id)
            )
            result = await cur.scalars(stmt)
            return result.one_or_none()

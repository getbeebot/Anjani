from datetime import datetime, timezone


def build_lottery_create_msg(template: str, **args) -> str:
    community_name = args.get("communityName", "")
    prize = args.get("prize")

    end_time_ms = args.get("endTime", 0)
    end_time = format_msg_timestamp(end_time_ms)

    return template.format(community_name=community_name, prize=prize, end_time=end_time)


def build_lottery_join_msg(template: str, **args) -> str:
    tg_users = args.get("tgUsers")
    # type check
    assert isinstance(tg_users, list), "tgUsers should be a list"

    joined_users = ""
    for tg_user in tg_users:
        nick = tg_user.get("nick", "")
        tg_id = tg_user.get("tgId", "")
        joined_users += f"[{nick}](tg://user?id={tg_id}) has entered the luckydraw.\n"

    end_time_ms = args.get("endTime", 0)
    end_time = format_msg_timestamp(end_time_ms)

    prize = args.get("prize")

    return template.format(joined_users=joined_users, end_time=end_time, prize=prize)


def build_lottery_end_msg(template: str, **args) -> str:
    community_name = args.get("communityName", "")
    return template.format(community_name=community_name)


def format_msg_timestamp(ms: int) -> str:
    return datetime.fromtimestamp(timestamp=ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S (UTC)")
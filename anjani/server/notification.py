from datetime import datetime, timezone


class ArgumentTypeError(Exception):
    pass


def build_lottery_create_msg(template: str, **args) -> str:
    community_name = args.get("communityName", "")
    prize = args.get("prize")

    end_time_ms = args.get("endTime", 0)
    end_time = format_msg_timestamp(end_time_ms)

    return template.format(community_name=community_name, prize=prize, end_time=end_time)


def build_lottery_join_msg(template: str, **args) -> str:
    nick_names = args.get("nickNames")
    # type check
    if not isinstance(nick_names, list) and not isinstance(nick_names, str):
        raise ArgumentTypeError("nick_names should be a list or string")

    if isinstance(nick_names, list):
        nick_names = ", @".join(nick_names)

    end_time_ms = args.get("endTime", 0)
    end_time = format_msg_timestamp(end_time_ms)

    prize = args.get("prize")

    return template.format(nick_names=nick_names, end_time=end_time, prize=prize)


def build_lottery_end_msg(template: str, **args) -> str:
    community_name = args.get("communityName", "")
    return template.format(community_name=community_name)


def format_msg_timestamp(ms: int) -> str:
    return datetime.fromtimestamp(timestamp=ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S (UTC)")
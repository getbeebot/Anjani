from datetime import datetime, timezone


def build_lottery_create_msg(template: str, **args) -> str:
    community_name = args.get("communityName", "")
    prize = args.get("prize")

    lottery_type = args.get("lotteryType")

    if lottery_type == 0:
        end_time_ms = args.get("endTime", 0)
        end_time = format_msg_timestamp(end_time_ms)
        return template.format(community_name=community_name, prize=prize, end_time=end_time)
    elif lottery_type == 1:
        condition = args.get("miniCount")
        return template.format(community_name=community_name, prize=prize, condition=condition)
    else:
        return ""


def build_lottery_join_msg(template: str, **args) -> str:
    tg_users = args.get("tgUsers")
    # type check
    assert isinstance(tg_users, list), "tgUsers should be a list"

    joined_users = ""
    for tg_user in tg_users:
        nick = tg_user.get("nick", "")
        tg_id = tg_user.get("tgId", "")
        joined_users += f"[{nick}](tg://user?id={tg_id}) has entered the luckydraw.\n"

    prize = args.get("prize")

    lottery_type = args.get("lotteryType")
    if lottery_type == 0:
        end_time_ms = args.get("endTime", 0)
        end_time = format_msg_timestamp(end_time_ms)
        return template.format(joined_users=joined_users, prize=prize, end_time=end_time)
    elif lottery_type == 1:
        condition = args.get("miniCount")
        return template.format(joined_users=joined_users, prize=prize, condition=condition)
    else:
        return ""


def build_lottery_end_msg(template: str, **args) -> str:
    community_name = args.get("communityName", "")
    return template.format(community_name=community_name)


def format_msg_timestamp(ms: int) -> str:
    return datetime.fromtimestamp(timestamp=ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S (UTC)")

def build_congrats_msg(template: str, **args) -> str:
    prize = args.get("prize")
    source = "beecon"
    drawtime = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S (UTC)")
    return template.format(prize=prize, source=source, drawtime=drawtime)

def build_congrats_records(template: str, **args) -> str:
    source = "beecon"
    records = args.get("drawLogList")
    amount_records = [int(item.get("prizeAmount")) for item in records]
    unit_records = [item.get("symbolAlias") for item in records]
    time_records = [item.get("rewardTime") for item in records]
    records_arr = [f'{i+1}. Prize: {v[0]} {v[1]}\n   Date: {v[2]}' for i, v in enumerate(zip(amount_records, unit_records, time_records))]
    r_text = "\n".join(records_arr)

    amount = sum(amount_records)
    a_text = f"{amount} {unit_records[0]}"

    return template.format(amount=a_text, source=source, records=r_text)

def build_invitation_records(template: str, **args) -> str:
    source = "beecon"
    records = args.get("inviteList")
    id_records = [item.get("inviteeUserName") for item in records]
    time_records = [item.get("inviteTime") for item in records]
    records_arr = [f'{i+1}. ID: {v[0]}\n   Date: {v[1]}' for i, v in enumerate(zip(id_records, time_records))]

    r_text = "\n".join(records_arr)

    amount = len(records)

    return template.format(amount=amount,source=source,records=r_text)
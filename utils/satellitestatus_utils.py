# -*- coding: UTF-8 -*-
import pandas as pd
import numpy as np
import pytz
import dfply as d
from datetime import datetime, timedelta
from utils.flightcontrol_utils import tm_table, obc_resetnew
from utils.db import get_mongo
from utils.flightcontrol_utils import commands


def OBCreset_mongo_records(post_token_url,
                           post_token_user_name,
                           post_token_password, metedataservice_url, tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']

    if not tf1 or not tf2:
        now = datetime.now()
        ten_minutes_ago = now - timedelta(minutes=2880)
        tf2 = now.timestamp() * 1000
        tf1 = ten_minutes_ago.timestamp() * 1000

    else:
        tf2 = datetime.strptime(tf2, "%Y-%m-%dT%H:%M:%S.%fZ")
        tf1 = datetime.strptime(tf1, "%Y-%m-%dT%H:%M:%S.%fZ")

        tf2 = int(datetime.timestamp(tf2))
        tf1 = int(datetime.timestamp(tf1))

    # Initialize Mongo class and get MongoDBconnection
    mongo_instance = get_mongo()

    cumlulative_query = {
        '$and': [
            {'_satelliteCode': str(satelliteCode)},
            {'time_found': {'$gte': tf1,
                            '$lte': tf2}}
        ]
    }
    resetdf = mongo_instance.get_all_data('OBC_reset_records', cumlulative_query)
    switchdf = mongo_instance.get_all_data('OBC_switch_records', cumlulative_query)

    reset_list = list(resetdf)
    reset_list = pd.DataFrame(reset_list)

    switch_list = list(switchdf)
    switch_list = pd.DataFrame(switch_list)

    if not len(switch_list) and not len(reset_list):
        print("No OBC anomaly found")
        return None
    elif not len(switch_list):
        concatenated_df = reset_list
    elif not len(reset_list):
        concatenated_df = switch_list
        concatenated_df['reset_count'] = 0
    else:

        if 'time_end' in reset_list.columns:
            reset_list = reset_list.drop(columns=['time_end'])

        if 'obc_switch' in switch_list.columns:
            switch_list = switch_list.drop(columns=['obc_switch'])

        concatenated_df = pd.concat([reset_list, switch_list])
        concatenated_df['reset_count'] = concatenated_df['reset_count'].fillna(0)

    # print(concatenated_df.to_string())

    concatenated_df['cumulative_reset'] = concatenated_df.apply(
        lambda row: '0' if row['switch'] == '1' and row['reset'] == '0' else '', axis=1)

    # print(concatenated_df.to_string())

    # print(concatenated_df.to_string())
    return concatenated_df


def OBCreset_influx(post_token_url,
                    post_token_user_name,
                    post_token_password, metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    if not tf1 or not tf2:
        now_utc = datetime.now(pytz.utc)
        end_utc = now_utc - timedelta(hours=48)

        tf2 = str(now_utc.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-4] + "Z")
        tf1 = str(end_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z")
        tf2 = pd.to_datetime(tf2)
        tf1 = pd.to_datetime(tf1)

    else:
        # Convert the input timestamps to datetime objects
        tf1 = pd.to_datetime(tf1)
        tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame()

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=7)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        if satID == '1':

            filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                      current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                      current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND TMH621 <=8'

            points = _influxdb.get_all(client, tmversion, ['TMH621'], filters, limit=5000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(obc_reset='TMH621')
        elif satID == '12':

            filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                      current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                      current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND TMH102 <=8'

            points = _influxdb.get_all(client, tmversion, ['TMH102'], filters, limit=5000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(obc_reset='TMH102')
        elif satID == '13':

            filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                      current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                      current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND TMH076 <=8'

            points = _influxdb.get_all(client, tmversion, ['TMH076'], filters, limit=5000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(obc_reset='TMH076')
        else:

            filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                      current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                      current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND TMS002 <=8'

            points = _influxdb.get_all(client, tmversion, ['TMS002'], filters, limit=5000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(obc_reset='TMS002')
        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', 'satelliteCode', 'obc_reset'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)
            points_df['timestamp'] = points_df['time'].apply(lambda x: x.timestamp()) * 1000
            points_df['timestamp'] = points_df['timestamp'] // 1000
            pd.set_option('display.float_format', lambda x: '%.0f' % x)
            points_df = points_df.drop(columns=['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df


# def OBCswitch_influx_v5(post_token_url, post_token_user_name, post_token_password, metedataservice_url,
#                         influxdb_action, client_action, _influxdb, client, tf1, tf2, satID):
#     K_SWITCH_WINDOW = 30  # 配对窗口，单位：秒
#     TELE_WINDOW_MINUTES = 10
#
#     # 获取卫星信息
#     tm = tm_table(post_token_url, post_token_user_name, post_token_password, metedataservice_url, satID)
#     # print(tm)
#     satelliteCode = tm[satID]['code']
#     # print(satelliteCode)
#     tmversion = tm[satID]['tm_version']
#     # print(tmversion)
#
#     tf1_str = tf1.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + "Z" if isinstance(tf1, pd.Timestamp) else str(tf1)
#     tf2_str = tf2.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + "Z" if isinstance(tf2, pd.Timestamp) else str(tf2)
#     # print(tf1_str)
#     # print(tf2_str)
#
#
#     # 查询命令流
#     points_cmd = commands(post_token_url, post_token_user_name, post_token_password, metedataservice_url,
#                           influxdb_action, client_action, tf1_str, tf2_str, satID)
#     if points_cmd.empty:
#         return pd.DataFrame(columns=['timestamp', '_satelliteCode', 'obc_switch'])
#     points_cmd = points_cmd.sort_values(by='time').reset_index(drop=True)
#
#     print(points_cmd)
#
#     # 找到所有K0013和K0014命令
#     k13s = points_cmd[points_cmd['cmd_code'] == 'K0013']
#     k14s = points_cmd[points_cmd['cmd_code'] == 'K0014']
#     print(k14s)
#     print(k13s)
#
#     switch_records = []
#
#     def has_big_change(df, key):
#         if not df.empty and key in df.columns and len(df) > 1:
#             arr = df[key].astype(float).values
#             return abs(arr[-1] - arr[0]) > 1
#         return False
#
#     # 检查所有K0013为起点的配对
#     for idx, k13_row in k13s.iterrows():
#         t_k13 = pd.to_datetime(k13_row['time'], utc=True)
#         # 找后面K0014在配对窗口内
#         candidates = k14s.copy()
#         candidates['t_k14'] = pd.to_datetime(candidates['time'], utc=True)
#         time_diff = (candidates['t_k14'] - t_k13).dt.total_seconds()
#         valid_k14 = candidates[(time_diff >= 0) & (time_diff <= K_SWITCH_WINDOW)]
#         if valid_k14.empty:
#             continue
#         # 只选最近的一个K0014
#         k14_row = valid_k14.iloc[0]
#         t_event = pd.to_datetime(k14_row['time'], utc=True)
#
#         # 检查遥测
#         t_event_end = t_event + pd.Timedelta(minutes=TELE_WINDOW_MINUTES)
#         filters = (
#             f"where _satelliteCode = '{satelliteCode}' AND time >= '{t_event.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z'"
#             f" AND time <= '{t_event_end.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z'")
#         tmc009_df = pd.DataFrame(_influxdb.get_all(client, tmversion, ['TMC009'], filters, limit=10000))
#         tmc109_df = pd.DataFrame(_influxdb.get_all(client, tmversion, ['TMC109'], filters, limit=10000))
#
#         if has_big_change(tmc009_df, 'TMC009') or has_big_change(tmc109_df, 'TMC109'):
#             switch_records.append({
#                 '_satelliteCode': satelliteCode,
#                 'timestamp': t_k13.timestamp(),  # 事件起点时间
#                 'obc_switch': 1
#             })
#             print(switch_records)
#
#     # 检查所有K0014为起点的配对
#     for idx, k14_row in k14s.iterrows():
#         t_k14 = pd.to_datetime(k14_row['time'], utc=True)
#         candidates = k13s.copy()
#         candidates['t_k13'] = pd.to_datetime(candidates['time'], utc=True)
#         time_diff = (candidates['t_k13'] - t_k14).dt.total_seconds()
#         valid_k13 = candidates[(time_diff >= 0) & (time_diff <= K_SWITCH_WINDOW)]
#         if valid_k13.empty:
#             continue
#         # 只选最近的一个K0013
#         k13_row = valid_k13.iloc[0]
#         t_event = pd.to_datetime(k13_row['time'], utc=True)
#
#         # 检查遥测
#         t_event_end = t_event + pd.Timedelta(minutes=TELE_WINDOW_MINUTES)
#         filters = (
#             f"where _satelliteCode = '{satelliteCode}' AND time >= '{t_event.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z'"
#             f" AND time <= '{t_event_end.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z'")
#         tmc009_df = pd.DataFrame(_influxdb.get_all(client, tmversion, ['TMC009'], filters, limit=10000))
#         tmc109_df = pd.DataFrame(_influxdb.get_all(client, tmversion, ['TMC109'], filters, limit=10000))
#
#         if has_big_change(tmc009_df, 'TMC009') or has_big_change(tmc109_df, 'TMC109'):
#             switch_records.append({
#                 '_satelliteCode': satelliteCode,
#                 'timestamp': t_k14.timestamp(),  # 事件起点时间
#                 'obc_switch': 1
#             })
#             print(switch_records)
#
#     # 去重：避免同一切换被记两次（可选：用事件时间和类型做唯一标识）
#     if switch_records:
#         result_df = pd.DataFrame(switch_records).drop_duplicates(subset=['timestamp'])
#     else:
#         result_df = pd.DataFrame(columns=['timestamp', '_satelliteCode', 'obc_switch'])
#     return result_df


def OBCswitch_influx_v5(post_token_url, post_token_user_name, post_token_password, metedataservice_url,
                        influxdb_action, client_action, _influxdb, client, tf1, tf2, satID):

    # 获取卫星信息
    tm = tm_table(post_token_url, post_token_user_name, post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    tf1_str = tf1.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + "Z" if isinstance(tf1, pd.Timestamp) else str(tf1)
    tf2_str = tf2.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + "Z" if isinstance(tf2, pd.Timestamp) else str(tf2)

    # 查询命令流
    points_cmd = commands(post_token_url, post_token_user_name, post_token_password, metedataservice_url,
                          influxdb_action, client_action, tf1_str, tf2_str, satID)
    if points_cmd.empty:
        return pd.DataFrame(columns=['timestamp', '_satelliteCode', 'obc_switch'])

    # 找所有K0013命令
    k13s = points_cmd[points_cmd['cmd_code'] == 'K0013']

    switch_records = []
    for idx, row in k13s.iterrows():
        t_k13 = pd.to_datetime(row['time'], utc=True)
        switch_records.append({
            '_satelliteCode': satelliteCode,
            'timestamp': int(t_k13.timestamp()),
            'obc_switch': 1
        })

    if switch_records:
        result_df = pd.DataFrame(switch_records)
    else:
        result_df = pd.DataFrame(columns=['timestamp', '_satelliteCode', 'obc_switch'])

    return result_df


def OBCswitch_influx(post_token_url,
                     post_token_user_name,
                     post_token_password, metedataservice_url, _influxdb, client,
                     influxdb_action,
                     client_action,
                     tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    if not tf1 or not tf2:
        now_utc = datetime.now(pytz.utc)
        end_utc = now_utc - timedelta(hours=48)

        tf2 = str(now_utc.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-4] + "Z")
        tf1 = str(end_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z")
        tf2 = pd.to_datetime(tf2, format="ISO8601", utc=True)
        tf1 = pd.to_datetime(tf1, format="ISO8601", utc=True)

    else:
        # Convert the input timestamps to datetime objects
        tf1 = pd.to_datetime(tf1, format="ISO8601", utc=True)
        tf2 = pd.to_datetime(tf2, format="ISO8601", utc=True)

    if satID == '5':
        return OBCswitch_influx_v5(post_token_url, post_token_user_name, post_token_password, metedataservice_url,
                                   influxdb_action, client_action, _influxdb, client, tf1, tf2, satID)
    else:
        # Initialize an empty DataFrame to store the results
        result_df = pd.DataFrame()

        # Query data in 10-day intervals
        interval = pd.DateOffset(days=7)
        current_start = tf1
        while current_start <= tf2:
            current_end = current_start + interval

            # Ensure the end timestamp does not exceed tf2
            if current_end > tf2:
                current_end = tf2

            filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                      current_start.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z' + '\' AND time <= \'' + \
                      current_end.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z' + '\''

            if satID == '1':
                points = _influxdb.get_all(client, tmversion, ['TMH612'], filters, limit=5000000)
                points_df = pd.DataFrame(points)
                points_df = points_df >> d.rename(obc_switch='TMH612')
            elif satID == '12':
                points = _influxdb.get_all(client, tmversion, ['TMH101'], filters, limit=5000000)
                points_df = pd.DataFrame(points)
                points_df = points_df >> d.rename(obc_switch='TMH101')
            elif satID == '13':
                points = _influxdb.get_all(client, tmversion, ['TMH075'], filters, limit=5000000)
                points_df = pd.DataFrame(points)
                points_df = points_df >> d.rename(obc_switch='TMH075')
            else:
                points = _influxdb.get_all(client, tmversion, ['TMS001'], filters, limit=5000000)
                points_df = pd.DataFrame(points)
                points_df = points_df >> d.rename(obc_switch='TMS001')
            if not len(points_df):
                points_df = pd.DataFrame(columns=['time', 'satelliteCode', 'obc_switch'])
            else:
                points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)
                points_df['timestamp'] = points_df['time'].apply(lambda x: x.timestamp()) * 1000
                points_df['timestamp'] = points_df['timestamp'] // 1000
                pd.set_option('display.float_format', lambda x: '%.0f' % x)
                points_df = points_df.drop(columns=['time'])

            # Concatenate the results for the current interval to the result DataFrame
            result_df = pd.concat([result_df, points_df], ignore_index=True)

            # Move to the next interval
            current_start = current_end + pd.Timedelta(seconds=1)

        # print("result_df:\n", result_df)

        return result_df

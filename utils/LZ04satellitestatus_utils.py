# -*- coding: UTF-8 -*-
import pandas as pd
import json
import requests
import dfply as d
from utils.flightcontrol_utils import get_task_list, tm_table, lenz

#LZ04 commands
def get_LZ04commands(post_token_url,
                   post_token_user_name,
                   post_token_password, metedataservice_url, _influxdb_action, client_action, tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    # print("tm:",tm)
    # print('satelliteCode:',satelliteCode)

    # Modify the filters based on the satelliteCode
    if satelliteCode == 'LZ04':
        filters = 'where satellite_code = \'LZ04\' AND time >= \'' \
                  + tf1 + '\' AND time <= \'' + tf2 + '\''
    else:
        filters = 'where satellite_code = \'' + satelliteCode + '\' AND time >= \'' \
                  + tf1 + '\' AND time <= \'' + tf2 + '\''

    points1 = _influxdb_action.get_command(client_action, ['antenna_code', 'cmd_code', 'isdelay', 'param'],
                                           filters, limit=1000000)
    points1 = pd.DataFrame(points1)

    if lenz(points1):
        points1 = pd.DataFrame(columns=['time', 'satellite_code', 'antenna_code', 'cmd_code', 'is_delay', 'param'])
    else:
        points1['time'] = pd.to_datetime(points1['time'], format="ISO8601", utc=True)
        points1['timestamp'] = points1['time'].apply(lambda x: x.timestamp()) * 1000
        points1['timestamp'] = points1['timestamp'] // 1000
        pd.set_option('display.float_format', lambda x: '%.0f' % x)
        points1 = points1.drop(columns=['time'])

    return points1

#####################################################################LZ04 HDI payload###################################
def get_LZ04_tmz009(post_token_url,
                    post_token_user_name,
                    post_token_password,
                    metedataservice_url,
                    _influxdb,
                    client,
                    tf1,
                    tf2,
                    satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  metedataservice_url,
                  satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']   # 跟 orbit_data 一样，从 tm_table 拿 measurement

    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    result_df = pd.DataFrame()

    # 跟 orbit_data 一样：分段查，避免一次性窗口太大
    interval = pd.DateOffset(days=7)
    current_start = tf1

    while current_start <= tf2:
        current_end = current_start + interval
        if current_end > tf2:
            current_end = tf2

        filters = (
            "where _satelliteCode = '{code}' "
            "AND time >= '{t1}' AND time <= '{t2}'"
        ).format(
            code=satelliteCode,
            t1=current_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            t2=current_end.strftime('%Y-%m-%dT%H:%M:%SZ')
        )

        points = _influxdb.get_all(client, tmversion, ['TMZ009'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMZ009'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        result_df = pd.concat([result_df, points_df], ignore_index=True)

        current_start = current_end + pd.Timedelta(seconds=1)

    # 标准化数值列
    if 'TMZ009' not in result_df.columns:
        # 防御：字段名不对时直接返回空表，让上层输出 nodata
        return pd.DataFrame(columns=['time', 'TMZ009'])

    result_df['TMZ009'] = pd.to_numeric(result_df['TMZ009'], errors='coerce').fillna(0).astype(int)

    # 只保留需要的列（避免输出带一堆 tag）
    result_df = result_df[['time', 'TMZ009']].sort_values('time').reset_index(drop=True)

    return result_df


def get_LZ04_tmkp202(post_token_url,
                     post_token_user_name,
                     post_token_password,
                     metedataservice_url,
                     _influxdb,
                     client,
                     tf1,
                     tf2,
                     satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  metedataservice_url,
                  satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    result_df = pd.DataFrame()
    interval = pd.DateOffset(days=7)
    current_start = tf1

    while current_start <= tf2:
        current_end = current_start + interval
        if current_end > tf2:
            current_end = tf2

        filters = (
            "where _satelliteCode = '{code}' "
            "AND time >= '{t1}' AND time <= '{t2}'"
        ).format(
            code=satelliteCode,
            t1=current_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            t2=current_end.strftime('%Y-%m-%dT%H:%M:%SZ')
        )

        points = _influxdb.get_all(client, tmversion, ['TMKP202'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMKP202'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        result_df = pd.concat([result_df, points_df], ignore_index=True)
        current_start = current_end + pd.Timedelta(seconds=1)

    if 'TMKP202' not in result_df.columns:
        return pd.DataFrame(columns=['time', 'TMKP202'])

    result_df['TMKP202'] = pd.to_numeric(result_df['TMKP202'], errors='coerce').fillna(0).astype(int)
    result_df = result_df[['time', 'TMKP202']].sort_values('time').reset_index(drop=True)
    return result_df


def get_LZ04_hdi_switches(post_token_url,
                          post_token_user_name,
                          post_token_password,
                          metedataservice_url,
                          _influxdb,
                          client,
                          tf1,
                          tf2,
                          satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  metedataservice_url,
                  satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    result_df = pd.DataFrame()
    interval = pd.DateOffset(days=7)
    current_start = tf1

    while current_start <= tf2:
        current_end = current_start + interval
        if current_end > tf2:
            current_end = tf2

        filters = (
            "where _satelliteCode = '{code}' "
            "AND time >= '{t1}' AND time <= '{t2}'"
        ).format(
            code=satelliteCode,
            t1=current_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            t2=current_end.strftime('%Y-%m-%dT%H:%M:%SZ')
        )

        points = _influxdb.get_all(client, tmversion, ['TMH4538', 'TMKS700'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMH4538', 'TMKS700'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        result_df = pd.concat([result_df, points_df], ignore_index=True)
        current_start = current_end + pd.Timedelta(seconds=1)

    # 标准化
    if 'TMH4538' not in result_df.columns:
        result_df['TMH4538'] = pd.NA
    if 'TMKS700' not in result_df.columns:
        result_df['TMKS700'] = pd.NA

    result_df['TMH4538'] = pd.to_numeric(result_df['TMH4538'], errors='coerce')  # keep NaN
    result_df['TMKS700'] = pd.to_numeric(result_df['TMKS700'], errors='coerce')  # keep NaN

    result_df = result_df[['time', 'TMH4538', 'TMKS700']].sort_values('time').reset_index(drop=True)
    return result_df

#####################################################################LZ04 DWI payload###################################
def get_LZ04_tmz012(post_token_url,
                    post_token_user_name,
                    post_token_password,
                    metedataservice_url,
                    _influxdb,
                    client,
                    tf1,
                    tf2,
                    satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  metedataservice_url,
                  satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    result_df = pd.DataFrame()
    interval = pd.DateOffset(days=7)
    current_start = tf1

    while current_start <= tf2:
        current_end = current_start + interval
        if current_end > tf2:
            current_end = tf2

        filters = (
            "where _satelliteCode = '{code}' "
            "AND time >= '{t1}' AND time <= '{t2}'"
        ).format(
            code=satelliteCode,
            t1=current_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            t2=current_end.strftime('%Y-%m-%dT%H:%M:%SZ')
        )

        points = _influxdb.get_all(client, tmversion, ['TMZ012'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMZ012'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        result_df = pd.concat([result_df, points_df], ignore_index=True)
        current_start = current_end + pd.Timedelta(seconds=1)

    if 'TMZ012' not in result_df.columns:
        return pd.DataFrame(columns=['time', 'TMZ012'])

    result_df['TMZ012'] = pd.to_numeric(result_df['TMZ012'], errors='coerce').fillna(0).astype(int)
    result_df = result_df[['time', 'TMZ012']].sort_values('time').reset_index(drop=True)
    return result_df


def get_LZ04_dwi_switches(post_token_url,
                          post_token_user_name,
                          post_token_password,
                          metedataservice_url,
                          _influxdb,
                          client,
                          tf1,
                          tf2,
                          satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  metedataservice_url,
                  satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    result_df = pd.DataFrame()
    interval = pd.DateOffset(days=7)
    current_start = tf1

    while current_start <= tf2:
        current_end = current_start + interval
        if current_end > tf2:
            current_end = tf2

        filters = (
            "where _satelliteCode = '{code}' "
            "AND time >= '{t1}' AND time <= '{t2}'"
        ).format(
            code=satelliteCode,
            t1=current_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            t2=current_end.strftime('%Y-%m-%dT%H:%M:%SZ')
        )

        points = _influxdb.get_all(client, tmversion, ['TMH4539', 'TMKS600'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMH4539', 'TMKS600'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        result_df = pd.concat([result_df, points_df], ignore_index=True)
        current_start = current_end + pd.Timedelta(seconds=1)

    if 'TMH4539' not in result_df.columns:
        result_df['TMH4539'] = pd.NA
    if 'TMKS600' not in result_df.columns:
        result_df['TMKS600'] = pd.NA

    result_df['TMH4539'] = pd.to_numeric(result_df['TMH4539'], errors='coerce')  # keep NaN
    result_df['TMKS600'] = pd.to_numeric(result_df['TMKS600'], errors='coerce')  # keep NaN

    result_df = result_df[['time', 'TMH4539', 'TMKS600']].sort_values('time').reset_index(drop=True)
    return result_df


#####################################################################LZ04 TOPS payload##################################
def get_LZ04_tmz015(post_token_url,
                    post_token_user_name,
                    post_token_password,
                    metedataservice_url,
                    _influxdb,
                    client,
                    tf1,
                    tf2,
                    satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  metedataservice_url,
                  satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    result_df = pd.DataFrame()
    interval = pd.DateOffset(days=7)
    current_start = tf1

    while current_start <= tf2:
        current_end = current_start + interval
        if current_end > tf2:
            current_end = tf2

        filters = (
            "where _satelliteCode = '{code}' "
            "AND time >= '{t1}' AND time <= '{t2}'"
        ).format(
            code=satelliteCode,
            t1=current_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            t2=current_end.strftime('%Y-%m-%dT%H:%M:%SZ')
        )

        points = _influxdb.get_all(client, tmversion, ['TMZ015'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMZ015'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        result_df = pd.concat([result_df, points_df], ignore_index=True)
        current_start = current_end + pd.Timedelta(seconds=1)

    if 'TMZ015' not in result_df.columns:
        return pd.DataFrame(columns=['time', 'TMZ015'])

    result_df['TMZ015'] = pd.to_numeric(result_df['TMZ015'], errors='coerce').fillna(0).astype(int)
    result_df = result_df[['time', 'TMZ015']].sort_values('time').reset_index(drop=True)
    return result_df


def get_LZ04_tops_switches(post_token_url,
                           post_token_user_name,
                           post_token_password,
                           metedataservice_url,
                           _influxdb,
                           client,
                           tf1,
                           tf2,
                           satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  metedataservice_url,
                  satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    result_df = pd.DataFrame()
    interval = pd.DateOffset(days=7)
    current_start = tf1

    while current_start <= tf2:
        current_end = current_start + interval
        if current_end > tf2:
            current_end = tf2

        filters = (
            "where _satelliteCode = '{code}' "
            "AND time >= '{t1}' AND time <= '{t2}'"
        ).format(
            code=satelliteCode,
            t1=current_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            t2=current_end.strftime('%Y-%m-%dT%H:%M:%SZ')
        )

        points = _influxdb.get_all(client, tmversion, ['TMH4540', 'TMKS400'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMH4540', 'TMKS400'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        result_df = pd.concat([result_df, points_df], ignore_index=True)
        current_start = current_end + pd.Timedelta(seconds=1)

    if 'TMH4540' not in result_df.columns:
        result_df['TMH4540'] = pd.NA
    if 'TMKS400' not in result_df.columns:
        result_df['TMKS400'] = pd.NA

    # 保留 NaN
    result_df['TMH4540'] = pd.to_numeric(result_df['TMH4540'], errors='coerce')
    result_df['TMKS400'] = pd.to_numeric(result_df['TMKS400'], errors='coerce')

    result_df = result_df[['time', 'TMH4540', 'TMKS400']].sort_values('time').reset_index(drop=True)
    return result_df

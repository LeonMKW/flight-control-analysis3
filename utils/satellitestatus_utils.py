# -*- coding: UTF-8 -*-
import pandas as pd
import pytz
import dfply as d
from datetime import datetime, timedelta
from utils.flightcontrol_utils import tm_table, obc_resetnew
from utils.db import get_mongo


def OBCreset_mongo_records(metedataservice_url, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
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


def OBCreset_influx(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
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
            points_df['time'] = pd.to_datetime(points_df['time'])
            points_df['timestamp'] = points_df['time'].apply(lambda x: x.timestamp()) * 1000
            points_df['timestamp'] = points_df['timestamp'] // 1000
            pd.set_option('display.float_format', lambda x: '%.0f' % x)
            points_df = points_df.drop(columns=['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df


def OBCswitch_influx(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
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

        filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                  current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                  current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\''

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
            points_df['time'] = pd.to_datetime(points_df['time'])
            points_df['timestamp'] = points_df['time'].apply(lambda x: x.timestamp()) * 1000
            points_df['timestamp'] = points_df['timestamp'] // 1000
            pd.set_option('display.float_format', lambda x: '%.0f' % x)
            points_df = points_df.drop(columns=['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df

# -*- coding: UTF-8 -*-
import pandas as pd
import requests
import dfply as d
from utils.flightcontrol_utils import get_task_list, tm_table, lenz


def get_AScommands(post_token_url,
                   post_token_user_name,
                   post_token_password, metedataservice_url, _influxdb_action, client_action, tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    # print("tm:",tm)
    # print('satelliteCode:',satelliteCode)

    # Modify the filters based on the satelliteCode
    if satelliteCode == 'AS02' or satelliteCode == 'GS-LZA':
        filters = 'where (satellite_code = \'AS02\' OR satellite_code = \'GS-LZA\') AND time >= \'' \
                  + tf1 + '\' AND time <= \'' + tf2 + '\''
    elif satelliteCode == 'AS03' or satelliteCode == 'GS-LZB':
        filters = 'where (satellite_code = \'AS03\' OR satellite_code = \'GS-LZB\') AND time >= \'' \
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


def get_AS02_datatransmission(post_token_url,
                              post_token_user_name,
                              post_token_password, metedataservice_url, _influxdb_input, client_input, tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame(columns=['time', 'TMK2014', 'TMK2015'])

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=10)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        # Modify the filter for satellite codes if satID is 12
        if satID == '12' or satID == '15':
            filters = (
                f"where (_satelliteCode = 'AS02' OR _satelliteCode = 'GS-LZA') AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )
        elif satID == '13' or satID == '16':
            filters = (
                f"where (_satelliteCode = 'AS03' OR _satelliteCode = 'GS-LZB') AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )
        else:
            filters = (
                f"where _satelliteCode = '{satelliteCode}' AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )

        # Query data for the current interval
        points = _influxdb_input.get_all(client_input, tmversion, ['TMK2014', 'TMK2015'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMK2014', 'TMK2015'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        # Concatenate the results for the current interval to the result DataFrame
        # Check and handle concatenation
        if result_df.empty or result_df.isna().all().all():
            result_df = points_df
        else:
            non_empty_dfs = [df for df in [result_df, points_df] if not df.empty and not df.isna().all().all()]
            result_df = pd.concat(non_empty_dfs, ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df


def get_AS02_hist_data_save(post_token_url,
                            post_token_user_name,
                            post_token_password, metedataservice_url, _influxdb_input, client_input, tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame(columns=['time', 'TMS1007'])

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=10)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        # Modify the filter for satellite codes if satID is 12
        if satID == '12' or satID == '15':
            filters = (
                f"where (_satelliteCode = 'AS02' OR _satelliteCode = 'GS-LZA') AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )
        else:
            filters = (
                f"where _satelliteCode = '{satelliteCode}' AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )

        # Query data for the current interval
        points = _influxdb_input.get_all(client_input, tmversion, ['TMS1007'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMS1007'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)
            points_df['timestamp'] = points_df['time'].apply(lambda x: x.timestamp()) * 1000
            points_df['timestamp'] = points_df['timestamp'] // 1000
            pd.set_option('display.float_format', lambda x: '%.0f' % x)
            points_df = points_df.drop(columns=['time'])

        # Concatenate the results for the current interval to the result DataFrame
        # Check and handle concatenation
        if result_df.empty or result_df.isna().all().all():
            result_df = points_df
        else:
            non_empty_dfs = [df for df in [result_df, points_df] if not df.empty and not df.isna().all().all()]
            result_df = pd.concat(non_empty_dfs, ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df


def get_AS03_hist_data_save(post_token_url,
                            post_token_user_name,
                            post_token_password, metedataservice_url, _influxdb_input, client_input, tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame(columns=['time', 'TMS043'])

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=10)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        # Modify the filter for satellite codes if satID is 13 or 16
        if satID == '13' or satID == '16':
            filters = (
                f"where (_satelliteCode = 'AS03' OR _satelliteCode = 'GS-LZB') AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )
        else:
            filters = (
                f"where _satelliteCode = '{satelliteCode}' AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )

        # Query data for the current interval
        points = _influxdb_input.get_all(client_input, tmversion, ['TMS043'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMS043'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)
            points_df['timestamp'] = points_df['time'].apply(lambda x: x.timestamp()) * 1000
            points_df['timestamp'] = points_df['timestamp'] // 1000
            pd.set_option('display.float_format', lambda x: '%.0f' % x)
            points_df = points_df.drop(columns=['time'])

        # Concatenate the results for the current interval to the result DataFrame
        # Check and handle concatenation
        if result_df.empty or result_df.isna().all().all():
            result_df = points_df
        else:
            non_empty_dfs = [df for df in [result_df, points_df] if not df.empty and not df.isna().all().all()]
            result_df = pd.concat(non_empty_dfs, ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df


def get_AS03_in_sight_sensing_task_data(post_token_url,
                                        post_token_user_name,
                                        post_token_password, metedataservice_url, _influxdb_input, client_input, tf1,
                                        tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize empty DataFrames to store the results
    result_df_00F0 = pd.DataFrame(columns=['timestamp', 'TMY002', 'TMY017', 'TMY005'])
    result_df_0620 = pd.DataFrame(columns=['timestamp', 'TMH1070', 'TMH1084', 'TMH1090'])
    result_df_0094 = pd.DataFrame(columns=['timestamp', 'TMS627'])
    result_df_0684 = pd.DataFrame(columns=['timestamp', 'TMK2115', 'TMK2008', 'TMK2009'])  # Updated columns
    result_df_00D0 = pd.DataFrame(columns=['timestamp', 'TMS006'])  # New DataFrame for '00D0'

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=10)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        # Modify the filter for satellite codes if satID is 13 or 16
        if satID == '13' or satID == '16':
            filters = (
                f"where (_satelliteCode = 'AS03' OR _satelliteCode = 'GS-LZB') AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )
        else:
            filters = (
                f"where _satelliteCode = '{satelliteCode}' AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )

        # Query data for each telemetry point separately

        # Points for '00F0'
        points_00F0 = _influxdb_input.get_all(client_input, tmversion, ['TMY002', 'TMY017', 'TMY005'], filters,
                                              limit=1000000)

        # Points for '0620'
        points_0620 = _influxdb_input.get_all(client_input, tmversion, ['TMH1070', 'TMH1084', 'TMH1090'], filters,
                                              limit=1000000)

        # Points for '0094'
        points_0094 = _influxdb_input.get_all(client_input, tmversion, ['TMS627'], filters, limit=1000000)

        # Points for '0684' - updated to include TMK2008 and TMK2009
        points_0684 = _influxdb_input.get_all(client_input, tmversion, ['TMK2115', 'TMK2008', 'TMK2009'], filters,
                                              limit=1000000)

        # Points for '00D0' - new
        points_00D0 = _influxdb_input.get_all(client_input, tmversion, ['TMS006'], filters, limit=1000000)

        # Convert the results to DataFrames
        points_df_00F0 = pd.DataFrame(points_00F0)
        points_df_0620 = pd.DataFrame(points_0620)
        points_df_0094 = pd.DataFrame(points_0094)
        points_df_0684 = pd.DataFrame(points_0684)
        points_df_00D0 = pd.DataFrame(points_00D0)

        # Process the DataFrame for '00F0'
        if not points_df_00F0.empty:
            points_df_00F0['time'] = pd.to_datetime(points_df_00F0['time'], format="ISO8601", utc=True)
            points_df_00F0['timestamp'] = points_df_00F0['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_00F0['timestamp'] = points_df_00F0['timestamp'] // 1000
            points_df_00F0 = points_df_00F0.drop(columns=['time'])
            points_df_00F0['timestamp'] = points_df_00F0['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            result_df_00F0 = pd.concat([result_df_00F0, points_df_00F0], ignore_index=True)

        # Process the DataFrame for '0620'
        if not points_df_0620.empty:
            points_df_0620['time'] = pd.to_datetime(points_df_0620['time'], format="ISO8601", utc=True)
            points_df_0620['timestamp'] = points_df_0620['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_0620['timestamp'] = points_df_0620['timestamp'] // 1000
            points_df_0620 = points_df_0620.drop(columns=['time'])
            points_df_0620['timestamp'] = points_df_0620['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            # print(points_df_0620.to_string())
            result_df_0620 = pd.concat([result_df_0620, points_df_0620], ignore_index=True)

        # Process the DataFrame for '0094'
        if not points_df_0094.empty:
            points_df_0094['time'] = pd.to_datetime(points_df_0094['time'], format="ISO8601", utc=True)
            points_df_0094['timestamp'] = points_df_0094['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_0094['timestamp'] = points_df_0094['timestamp'] // 1000
            points_df_0094 = points_df_0094.drop(columns=['time'])
            points_df_0094['timestamp'] = points_df_0094['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            # print(points_df_0094.to_string())
            result_df_0094 = pd.concat([result_df_0094, points_df_0094], ignore_index=True)

        # Process the DataFrame for '0684' - including TMK2008 and TMK2009
        if not points_df_0684.empty:
            points_df_0684['time'] = pd.to_datetime(points_df_0684['time'], format="ISO8601", utc=True)
            points_df_0684['timestamp'] = points_df_0684['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_0684['timestamp'] = points_df_0684['timestamp'] // 1000
            points_df_0684 = points_df_0684.drop(columns=['time'])
            points_df_0684['timestamp'] = points_df_0684['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            # print(points_df_0094.to_string())
            result_df_0684 = pd.concat([result_df_0684, points_df_0684], ignore_index=True)

        # Process the DataFrame for '00D0' - new
        if not points_df_00D0.empty:
            points_df_00D0['time'] = pd.to_datetime(points_df_00D0['time'], format="ISO8601", utc=True)
            points_df_00D0['timestamp'] = points_df_00D0['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_00D0['timestamp'] = points_df_00D0['timestamp'] // 1000
            points_df_00D0 = points_df_00D0.drop(columns=['time'])
            points_df_00D0['timestamp'] = points_df_00D0['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            result_df_00D0 = pd.concat([result_df_00D0, points_df_00D0], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df_00F0, result_df_0620, result_df_0094, result_df_0684, result_df_00D0


def get_AS03_out_sight_sensing_task_data(post_token_url,
                                         post_token_user_name,
                                         post_token_password, metedataservice_url, _influxdb_input, client_input, tf1,
                                         tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize empty DataFrames to store the results
    result_df_00F0 = pd.DataFrame(columns=['timestamp', 'TMY002', 'TMY017', 'TMY005'])
    result_df_0620 = pd.DataFrame(columns=['timestamp', 'TMH1070', 'TMH1084', 'TMH1090'])
    result_df_0684 = pd.DataFrame(columns=['timestamp', 'TMK2115'])  # Updated columns
    result_df_00D0 = pd.DataFrame(columns=['timestamp', 'TMS006'])  # New DataFrame for '00D0'

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=10)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        # Modify the filter for satellite codes if satID is 13 or 16
        if satID == '13' or satID == '16':
            filters = (
                f"where (_satelliteCode = 'AS03' OR _satelliteCode = 'GS-LZB') AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )
        else:
            filters = (
                f"where _satelliteCode = '{satelliteCode}' AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )

        # Query data for each telemetry point separately

        # Points for '00F0'
        points_00F0 = _influxdb_input.get_all(client_input, tmversion, ['TMY002', 'TMY017', 'TMY005'], filters,
                                              limit=1000000)

        # Points for '0620'
        points_0620 = _influxdb_input.get_all(client_input, tmversion, ['TMH1070', 'TMH1084', 'TMH1090'], filters,
                                              limit=1000000)

        # Points for '0684' - updated to include TMK2008 and TMK2009
        points_0684 = _influxdb_input.get_all(client_input, tmversion, ['TMK2115'], filters,
                                              limit=1000000)

        # Points for '00D0' - new
        points_00D0 = _influxdb_input.get_all(client_input, tmversion, ['TMS006'], filters, limit=1000000)

        # Convert the results to DataFrames
        points_df_00F0 = pd.DataFrame(points_00F0)
        points_df_0620 = pd.DataFrame(points_0620)
        points_df_0684 = pd.DataFrame(points_0684)
        points_df_00D0 = pd.DataFrame(points_00D0)

        # Process the DataFrame for '00F0'
        if not points_df_00F0.empty:
            points_df_00F0['time'] = pd.to_datetime(points_df_00F0['time'], format="ISO8601", utc=True)
            points_df_00F0['timestamp'] = points_df_00F0['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_00F0['timestamp'] = points_df_00F0['timestamp'] // 1000
            points_df_00F0 = points_df_00F0.drop(columns=['time'])
            points_df_00F0['timestamp'] = points_df_00F0['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            result_df_00F0 = pd.concat([result_df_00F0, points_df_00F0], ignore_index=True)

        # Process the DataFrame for '0620'
        if not points_df_0620.empty:
            points_df_0620['time'] = pd.to_datetime(points_df_0620['time'], format="ISO8601", utc=True)
            points_df_0620['timestamp'] = points_df_0620['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_0620['timestamp'] = points_df_0620['timestamp'] // 1000
            points_df_0620 = points_df_0620.drop(columns=['time'])
            points_df_0620['timestamp'] = points_df_0620['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            # print(points_df_0620.to_string())
            result_df_0620 = pd.concat([result_df_0620, points_df_0620], ignore_index=True)

        # Process the DataFrame for '0684'
        if not points_df_0684.empty:
            points_df_0684['time'] = pd.to_datetime(points_df_0684['time'], format="ISO8601", utc=True)
            points_df_0684['timestamp'] = points_df_0684['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_0684['timestamp'] = points_df_0684['timestamp'] // 1000
            points_df_0684 = points_df_0684.drop(columns=['time'])
            points_df_0684['timestamp'] = points_df_0684['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            # print(points_df_0094.to_string())
            result_df_0684 = pd.concat([result_df_0684, points_df_0684], ignore_index=True)

        # Process the DataFrame for '00D0' - new
        if not points_df_00D0.empty:
            points_df_00D0['time'] = pd.to_datetime(points_df_00D0['time'], format="ISO8601", utc=True)
            points_df_00D0['timestamp'] = points_df_00D0['time'].apply(lambda x: x.timestamp()) * 1000
            points_df_00D0['timestamp'] = points_df_00D0['timestamp'] // 1000
            points_df_00D0 = points_df_00D0.drop(columns=['time'])
            points_df_00D0['timestamp'] = points_df_00D0['timestamp'].apply(lambda x: '{:.0f}'.format(x))
            result_df_00D0 = pd.concat([result_df_00D0, points_df_00D0], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df_00F0, result_df_0620, result_df_0684, result_df_00D0


def get_AS03_datatransmission(metedataservice_url, _influxdb_input, client_input, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame(columns=['time', 'TMK2014', 'TMK2015'])

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=10)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        # Modify the filter for satellite codes if satID is 12
        if satID == '13' or satID == '16':
            filters = (
                f"where (_satelliteCode = 'AS03' OR _satelliteCode = 'GS-LZB') AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )
        else:
            filters = (
                f"where _satelliteCode = '{satelliteCode}' AND time >= '{current_start.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"AND time <= '{current_end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            )

        # Query data for the current interval
        points = _influxdb_input.get_all(client_input, tmversion, ['TMK2014', 'TMK2015'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'TMK2014', 'TMK2015'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)

        # Concatenate the results for the current interval to the result DataFrame
        # Check and handle concatenation
        if result_df.empty or result_df.isna().all().all():
            result_df = points_df
        else:
            non_empty_dfs = [df for df in [result_df, points_df] if not df.empty and not df.isna().all().all()]
            result_df = pd.concat(non_empty_dfs, ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df

# def AS_orbit_control(metedataservice_url, _influxdb, client, tf1, tf2, satID):
#     tm = tm_table(metedataservice_url, satID)
#     satelliteCode = tm[satID]['code']
#     tmversion = tm[satID]['tm_version']
#
#     # Convert the input timestamps to datetime objects
#     tf1 = pd.to_datetime(tf1)
#     tf2 = pd.to_datetime(tf2)
#
#     # Initialize an empty DataFrame to store the results
#     result_df = pd.DataFrame()
#
#     # Query data in 10-day intervals
#     interval = pd.DateOffset(days=7)
#     current_start = tf1
#     while current_start <= tf2:
#         current_end = current_start + interval
#
#         # Ensure the end timestamp does not exceed tf2
#         if current_end > tf2:
#             current_end = tf2
#
#         filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
#                   current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
#                   current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\''
#
#         # Query data for the current interval
#         if satID == '12':
#             points = _influxdb.get_all(client, tmversion, ['TMK2012', 'TMK2013', 'TMK2044', 'TMK2045',
#                                                            'TMK2047', 'TMK2048', 'TMK2404', 'TMK2405',
#                                                            'TMK2412', 'TMK2413', 'TMK2420', 'TMK2421',
#                                                            'TMK2428', 'TMK2429', 'TMK2436', 'TMK2436',
#                                                            'TMK2444', 'TMK2445', 'TMK2452', 'TMK2453'], filters,
#                                        limit=1000000)
#             points_df = pd.DataFrame(points)
#             points_df = points_df >> d.rename(orbit_stat='TMK1050_orbit_elements_now_state')
#
#         elif satID == '14':
#             points = _influxdb.get_all(client, tmversion, ['TMK108'], filters, limit=1000000)
#             points_df = pd.DataFrame(points)
#             points_df = points_df >> d.rename(orbit_stat='TMK108')
#
#         else:
#             points = _influxdb.get_all(client, tmversion, ['TMK045'], filters, limit=1000000)
#             points_df = pd.DataFrame(points)
#             points_df = points_df >> d.rename(orbit_stat='TMK045')
#
#         if not len(points_df):
#             points_df = pd.DataFrame(columns=['time', 'satelliteCode', 'orbit_stat'])
#         else:
#             points_df['time'] = pd.to_datetime(points_df['time'], format="ISO8601", utc=True)
#
#         # Concatenate the results for the current interval to the result DataFrame
#         result_df = pd.concat([result_df, points_df], ignore_index=True)
#
#         # Move to the next interval
#         current_start = current_end + pd.Timedelta(seconds=1)
#
#     # print(result_df.to_string())
#     return result_df

# def fire_status(orbit_maneuver_url, tf1, tf2, satID):
#     orbitmaneuver_url = orbit_maneuver_url
#
#     # disable chained assignments
#     pd.options.mode.chained_assignment = None
#
#     variables = {"spacecraftIds": [str(satID)],
#                  "startMs": tf1 * 1000,
#                  "endMs": tf2 * 1000,
#                  "state": [1, 2, 3, 4, 5, 6]}
#     # print(json.dumps(variables))
#     res = requests.post(url=orbitmaneuver_url, json=variables)
#
#     orbit_maneuverdata = res.json()["data"]["list"]
#     orbit_maneuverdf = pd.DataFrame(orbit_maneuverdata)
#     print(orbit_maneuverdf.to_string())


# if __name__ == '__main__':
#     fire_status('http://orbit-service-inf.prod.yhroot.com/api/orbit/maneuver/record/query',
#                 1704583163,
#                 1705021194,
#                 2)

#     get_task_list('http://orbit-service-inf.prod.yhroot.com/graphql',
#                   '2023-11-10T05:50:00.000Z',
#                   '2023-11-11T05:50:00.000Z',
#                   '1,2,3,4,5,6,7,14')
# tm_table('http://mete-data-service.prod.yhroot.com/graphql', '1,2,3')
#  get_orbit_data_tmcode('http://mete-data-service.prod.yhroot.com/graphql', '5')
#     get_spacecraftinfo('http://mete-data-service.prod.yhroot.com/graphql', '12')

# -*- coding: UTF-8 -*-
import logging
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from utils.flightcontrol_utils import vcIdnew, get_task_list, commands, correctframe, uplock, obc_resetnew, payload_pwr, \
    file_inspect, \
    electric_propulsion, monitor_data, orbit_data, experimental_lock_data, experimental_telemetry_data, \
    hist_interval_data, gnss_interval_data
from tqdm import tqdm
from utils.db import set_value, init_val
from data.fileinspection import map_dict
from utils.core_algorithm import analyze_lock_intervals, analyze_lock_status, analyze_telemetry_intervals, \
    calculate_hist_interval, calculate_gnss_interval

from utils.ASsatellitestatus_utils import get_AScommands, get_AS02_datatransmission, get_AS02_hist_data_save
from utils.flightcontrol_utils import get_task_list

logger = logging.getLogger(__name__)

import json


def AS02_sensing_upload(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    # Retrieve the command data
    AS02_commands = get_AScommands(metedataservice_url, _influxdb, client, tf1, tf2, satID)

    # Filter for relevant commands
    TCKAF06_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF06']
    TCS801_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCS801']
    TCKBB02_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02']

    # Initialize list to store the results
    sensing_task_data = []
    processed_start1 = set()

    # Iterate over each TCKAF06 command
    for _, tckaf06_row in TCKAF06_commands.iterrows():
        tckaf06_time = tckaf06_row['timestamp']

        # Check for task cancellation
        cancel_task = TCKBB02_commands[(TCKBB02_commands['timestamp'] > tckaf06_time) &
                                       (TCKBB02_commands['timestamp'] <= tckaf06_time + 300) &
                                       (TCKBB02_commands['param'].apply(
                                           lambda x: json.loads(x)['packageForm']['params'].get('v0') == 4369))]

        if not cancel_task.empty:
            continue

        # Find TCS801 commands within 4 seconds before TCKAF06
        matching_tcs801 = TCS801_commands[(TCS801_commands['timestamp'] >= tckaf06_time - 4) &
                                          (TCS801_commands['timestamp'] < tckaf06_time)]

        if not matching_tcs801.empty:
            # Parse JSON strings into dictionaries
            tckaf06_params = json.loads(tckaf06_row['param'])
            tcs801_params = json.loads(matching_tcs801.iloc[0]['param'])

            # Extract parameters from the JSON data
            package_params = tckaf06_params['packageForm']['params']
            file_params = tcs801_params['packageForm']['params']

            start1 = package_params.get('start1')

            # Check for duplicate tasks
            if any(abs(start1 - task['TCKAF06']['start1']) < 60 for task in sensing_task_data):
                continue

            sensing_task_data.append({
                'TCKAF06': {
                    'timestamp': tckaf06_time,
                    'start1': start1,
                    'end1': package_params.get('end1'),
                    'pitch1': package_params.get('pitch1'),
                    'camera_state': package_params.get('camera_state'),
                    'scan_mode': package_params.get('scan_mode')
                },
                'TCS801': {
                    'timestamp': matching_tcs801.iloc[0]['timestamp'],
                    'file1': file_params.get('File1'),
                    'file2': file_params.get('File2'),
                    'file3': file_params.get('File3'),
                    'file4': file_params.get('File4'),
                    'file5': file_params.get('File5'),
                    'file6': file_params.get('File6'),
                    'file7': file_params.get('File7'),
                    'file8': file_params.get('File8')
                }
            })
            processed_start1.add(start1)

    result = json.dumps(sensing_task_data, ensure_ascii=False)
    return result


def AS02_payload_data_transmission(metedataservice_url, _influxdb_input, client_input, influxdb_action, host_action,
                                   tf1, tf2, satID):
    # Retrieve the command data
    AS02_payloaddatatransmission = get_AS02_datatransmission(metedataservice_url, _influxdb_input, client_input, tf1,
                                                             tf2, satID)

    # Remove duplicate rows with the same TMK2014 and TMK2015 values, keeping only the first occurrence
    AS02_payloaddatatransmission = AS02_payloaddatatransmission.drop_duplicates(subset=['TMK2014', 'TMK2015'])

    # Initialize list to store the results
    payload_transmission_data = []

    # Iterate over each TMK2014 and TMK2015 pair
    for _, payload_row in AS02_payloaddatatransmission.iterrows():
        TMK2014 = payload_row['TMK2014']
        TMK2015 = payload_row['TMK2015']

        if TMK2014 != 0 and TMK2015 != 0:
            duration = TMK2015 - TMK2014

            # Calculate the start time for querying commands (48 hours before TMK2014)
            start_time = int(TMK2014 - 48 * 3600)
            end_time = int(TMK2014)

            # Convert start_time and end_time to datetime strings
            start_time_str = pd.to_datetime(start_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')
            end_time_str = pd.to_datetime(end_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')

            # Retrieve the command data for the specific time range
            AS02_commands = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=start_time_str,
                                           tf2=end_time_str, satID=satID)

            # Filter for relevant commands
            TCKAF03_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF03']
            TCS804_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCS804']
            TCKBB02_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02']

            # Find TCKAF03 commands with start equal to TMK2014
            matching_tckaf03 = TCKAF03_commands[
                (TCKAF03_commands['param'].apply(
                    lambda x: json.loads(x)['packageForm']['params'].get('start') == TMK2014))
            ]

            if not matching_tckaf03.empty:
                tckaf03_row = matching_tckaf03.iloc[0]
                tckaf03_time = tckaf03_row['timestamp']
                tckaf03_params = json.loads(tckaf03_row['param'])

                # Check for TCKBB02 commands between TCKAF03's timestamp and TMK2014
                matching_tckbb02 = TCKBB02_commands[
                    (TCKBB02_commands['timestamp'] > tckaf03_time) &
                    (TCKBB02_commands['timestamp'] <= TMK2014) &
                    (TCKBB02_commands['param'].apply(
                        lambda x: json.loads(x)['packageForm']['params'].get('v0') == 17476))
                    ]

                # If TCKBB02 with v0 == 17476 is found, ignore this task group
                if not matching_tckbb02.empty:
                    continue

                # Find TCS804 commands within 60 seconds after the TCKAF03 time
                matching_tcs804 = TCS804_commands[
                    (TCS804_commands['timestamp'] > tckaf03_time) &
                    (TCS804_commands['timestamp'] <= tckaf03_time + 60)
                    ]

                if matching_tcs804.empty:
                    continue

                tcs804_list = []
                for _, tcs804_row in matching_tcs804.iterrows():
                    tcs804_params = json.loads(tcs804_row['param'])

                    # Extract File1 and File2
                    file_params = tcs804_params['packageForm']['params']
                    file1 = file_params.get('File1')
                    file2 = file_params.get('File2')

                    tcs804_list.append({
                        'timestamp': tcs804_row['timestamp'],
                        'File1': file1,
                        'File2': file2
                    })

                payload_transmission_data.append({
                    'TMK2014': TMK2014,
                    'TMK2015': TMK2015,
                    'duration': duration,
                    'TCKAF03': {
                        'timestamp': tckaf03_time,
                        'params': tckaf03_params['packageForm']['params']
                    },
                    'TCS804': tcs804_list
                })

    result = json.dumps(payload_transmission_data, ensure_ascii=False)
    return result


def AS02_platform_data_transmission(metedataservice_url, _influxdb_input, client_input, influxdb_action, host_action,
                                    tf1, tf2, satID):
    # Retrieve the platform data transmission data
    AS02_payloaddatatransmission = get_AS02_datatransmission(metedataservice_url, _influxdb_input, client_input, tf1,
                                                             tf2, satID)

    # Remove duplicate rows with the same TMK2014 and TMK2015 values, keeping only the first occurrence
    AS02_payloaddatatransmission = AS02_payloaddatatransmission.drop_duplicates(subset=['TMK2014', 'TMK2015'])

    # Initialize list to store the results
    platform_transmission_data = []

    # Iterate over each TMK2014 and TMK2015 pair
    for _, payload_row in AS02_payloaddatatransmission.iterrows():
        TMK2014 = payload_row['TMK2014']
        TMK2015 = payload_row['TMK2015']

        if TMK2014 != 0 and TMK2015 != 0:
            duration = TMK2015 - TMK2014

            # Calculate the start time for querying commands (48 hours before TMK2014)
            start_time = int(TMK2014 - 48 * 3600)
            end_time = int(TMK2014)

            # Convert start_time and end_time to datetime strings
            start_time_str = pd.to_datetime(start_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')
            end_time_str = pd.to_datetime(end_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')

            # Retrieve the command data for the specific time range
            AS02_commands = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=start_time_str,
                                           tf2=end_time_str, satID=satID)

            # Filter for relevant commands
            TCKAF03_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF03']
            TCS813_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCS813']
            TCKBB02_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02']

            # Find TCKAF03 commands with start equal to TMK2014
            matching_tckaf03 = TCKAF03_commands[
                (TCKAF03_commands['param'].apply(
                    lambda x: json.loads(x)['packageForm']['params'].get('start') == TMK2014))
            ]

            if not matching_tckaf03.empty:
                tckaf03_row = matching_tckaf03.iloc[0]
                tckaf03_time = tckaf03_row['timestamp']
                tckaf03_params = json.loads(tckaf03_row['param'])

                # Check for TCKBB02 commands between TCKAF03's timestamp and TMK2014
                matching_tckbb02 = TCKBB02_commands[
                    (TCKBB02_commands['timestamp'] > tckaf03_time) &
                    (TCKBB02_commands['timestamp'] <= TMK2014) &
                    (TCKBB02_commands['param'].apply(
                        lambda x: json.loads(x)['packageForm']['params'].get('v0') == 17476))
                    ]

                # If TCKBB02 with v0 == 17476 is found, ignore this task group
                if not matching_tckbb02.empty:
                    continue

                # Find TCS813 commands within 60 seconds after the TCKAF03 time
                matching_tcs813 = TCS813_commands[
                    (TCS813_commands['timestamp'] > tckaf03_time) &
                    (TCS813_commands['timestamp'] <= tckaf03_time + 60)
                    ]

                if matching_tcs813.empty:
                    continue

                tcs813_list = []
                for _, tcs813_row in matching_tcs813.iterrows():
                    tcs813_params = json.loads(tcs813_row['param'])

                    # Extract FileNum
                    file_params = tcs813_params['packageForm']['params']
                    file_num = file_params.get('FIleNum')

                    tcs813_list.append({
                        'timestamp': tcs813_row['timestamp'],
                        'FileNum': file_num
                    })

                platform_transmission_data.append({
                    'TMK2014': TMK2014,
                    'TMK2015': TMK2015,
                    'duration': duration,
                    'TCKAF03': {
                        'timestamp': tckaf03_time,
                        'params': tckaf03_params['packageForm']['params']
                    },
                    'TCS813': tcs813_list
                })

    result = json.dumps(platform_transmission_data, ensure_ascii=False)
    return result


# def AS02_hist_file_save(metedataservice_url, _influxdb_input, client_input, influxdb_action, host_action, tf1, tf2,
#                         satID):
#     # Retrieve the command data
#     AS02hist_file_save_command = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=tf1, tf2=tf2,
#                                                 satID=satID)
#
#     # Retrieve the telemetry data
#     AS02hist_file_save_telemetry = get_AS02_hist_data_save(metedataservice_url, _influxdb_input, client_input, tf1, tf2,
#                                                            satID)
#
#     # Filter for relevant commands
#     TCS811_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCS811']
#     TCS812_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCS812']
#     TCH209_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCH209']
#
#     # Initialize list to store the results
#     hist_file_save_data = []
#
#     # Iterate over each TCS811 command
#     for _, tcs811_row in TCS811_commands.iterrows():
#         tcs811_time = tcs811_row['timestamp']
#         tcs811_params = json.loads(tcs811_row['param'])
#         tcs811_file = tcs811_params['packageForm']['params']['FIle']
#
#         # Find the corresponding TCH209 commands within 10 minutes after TCS811
#         matching_tch209 = TCH209_commands[
#             (TCH209_commands['timestamp'] > tcs811_time) &
#             (TCH209_commands['timestamp'] <= tcs811_time + 600)
#             ]
#
#         tch209_filenames = []
#         for _, tch209_row in matching_tch209.iterrows():
#             tch209_params = json.loads(tch209_row['param'])
#             tch209_filenames.append(tch209_params['packageForm']['params']['filename'])
#
#         # Check for the corresponding TCS812 command
#         matching_tcs812 = TCS812_commands[
#             (TCS812_commands['timestamp'] > tcs811_time)
#         ]
#         # print(matching_tcs812.to_string())
#
#         if matching_tcs812.empty:
#             return {'error': 'file_saving_stop_not_found(TCS812)'}
#
#         tcs812_row = matching_tcs812.iloc[0]
#         tcs812_time = tcs812_row['timestamp']
#         tcs812_params = json.loads(tcs812_row['param'])
#         tcs812_delay_seconds = tcs812_params['delayForm']['seconds']
#         print(tcs812_delay_seconds)
#         tcs812_dt = datetime.strptime(tcs812_delay_seconds, "%Y-%m-%dT%H:%M:%S.%fZ") #转北京时间
#         tcs812_timestamp = int(tcs812_dt.timestamp())
#         tcs812_ts = int(tcs812_timestamp)
#         print(tcs812_ts)
#
#         # Find the first record in TMS1007 after TCS811
#         matching_tms1007_start = AS02hist_file_save_telemetry[
#             (AS02hist_file_save_telemetry['timestamp'] > tcs811_time)
#         ]
#         print(AS02hist_file_save_telemetry['timestamp'])
#
#         if matching_tms1007_start.empty:
#             continue
#
#         tms1007_start_time = matching_tms1007_start.iloc[0]['timestamp']
#
#         # Find the first record in TMS1007 after TCS812's delay seconds
#         matching_tms1007_end = AS02hist_file_save_telemetry[
#             (AS02hist_file_save_telemetry['timestamp'] > tcs812_ts)
#         ]
#
#         # print(matching_tms1007_end)
#
#         if matching_tms1007_end.empty:
#             continue
#
#         tms1007_end_time = matching_tms1007_end.iloc[0]['timestamp']
#
#         # Calculate the absolute difference
#         file_size = abs(tms1007_end_time - tms1007_start_time)
#
#         hist_file_save_data.append({
#             'hist_data_saving_time': tcs811_time,
#             'save_to_number': tcs811_file,
#             'files_saved': tch209_filenames,
#             'file_size': file_size
#         })
#
#     result = json.dumps(hist_file_save_data, ensure_ascii=False)
#     return result

def AS02_hist_file_save(metedataservice_url, _influxdb_input, client_input, influxdb_action, host_action, tf1, tf2,
                        satID):
    # Retrieve the command data
    AS02hist_file_save_command = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=tf1, tf2=tf2,
                                                satID=satID)

    # Retrieve the telemetry data
    AS02hist_file_save_telemetry = get_AS02_hist_data_save(metedataservice_url, _influxdb_input, client_input, tf1, tf2,
                                                           satID)
    # print(AS02hist_file_save_telemetry.to_string())

    # Filter for relevant commands
    TCS811_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCS811']
    TCS812_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCS812']
    TCH209_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCH209']

    # Initialize list to store the results
    hist_file_save_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')

    # Iterate over each TCS811 command
    for _, tcs811_row in TCS811_commands.iterrows():
        tcs811_time = tcs811_row['timestamp']
        tcs811_params = json.loads(tcs811_row['param'])
        tcs811_file = tcs811_params['packageForm']['params']['FIle']

        # Find the corresponding TCH209 commands within 10 minutes after TCS811
        matching_tch209 = TCH209_commands[
            (TCH209_commands['timestamp'] > tcs811_time) &
            (TCH209_commands['timestamp'] <= tcs811_time + 600)
            ]

        tch209_filenames = []
        for _, tch209_row in matching_tch209.iterrows():
            tch209_params = json.loads(tch209_row['param'])
            tch209_filenames.append(tch209_params['packageForm']['params']['filename'])

        # Check for the corresponding TCS812 command
        matching_tcs812 = TCS812_commands[
            (TCS812_commands['timestamp'] > tcs811_time)
        ]

        if matching_tcs812.empty:
            return {'error': 'file_saving_stop_not_found(TCS812)'}

        tcs812_row = matching_tcs812.iloc[0]
        tcs812_time = tcs812_row['timestamp']
        tcs812_params = json.loads(tcs812_row['param'])
        tcs812_delay_seconds = tcs812_params['delayForm']['seconds']

        # Parse the delay time and convert it to a timestamp
        tcs812_dt = datetime.strptime(tcs812_delay_seconds, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
        tcs812_timestamp = int(tcs812_dt.timestamp())
        # print(tcs812_timestamp)

        # Find the first record in TMS1007 after TCS811
        matching_tms1007_start = AS02hist_file_save_telemetry[
            (AS02hist_file_save_telemetry['timestamp'] > tcs811_time)
        ]

        if matching_tms1007_start.empty:
            continue

        tms1007_start_time = matching_tms1007_start.iloc[0]['timestamp']
        tms1007_start_value = matching_tms1007_start.iloc[0][
            'TMS1007']

        # Find the first record in TMS1007 after TCS812's delay seconds
        matching_tms1007_end = AS02hist_file_save_telemetry[
            (AS02hist_file_save_telemetry['timestamp'] > tcs812_timestamp)
        ]
        # print(matching_tms1007_end)

        if matching_tms1007_end.empty:
            continue

        tms1007_end_time = matching_tms1007_end.iloc[0]['timestamp']
        tms1007_end_value = matching_tms1007_end.iloc[0][
            'TMS1007']

        # Calculate the absolute difference of values
        file_size = abs(tms1007_end_value - tms1007_start_value)

        hist_file_save_data.append({
            'hist_data_saving_time': tcs811_time,
            'save_to_number': tcs811_file,
            'files_saved': tch209_filenames,
            'file_size': file_size
        })

    result = json.dumps(hist_file_save_data, ensure_ascii=False)
    return result


def silicon_battery_task(metedataservice_url, influxdb_action, host_action, tf1, tf2, satID):
    # Retrieve the command data
    AS_commands = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=tf1, tf2=tf2, satID=satID)

    # Filter for TCN090 commands
    TCN090_commands = AS_commands[AS_commands['cmd_code'] == 'TCN090']

    # Initialize list to store the results
    silicon_battery_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')

    # Iterate over each TCN090 command
    for _, tcn090_row in TCN090_commands.iterrows():
        tcn090_time = tcn090_row['timestamp']
        tcn090_params = json.loads(tcn090_row['param'])
        tcn090_delay_seconds = tcn090_params['delayForm']['seconds']

        # Parse the delay time and convert it to a timestamp
        tcn090_dt = datetime.strptime(tcn090_delay_seconds, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
        tcn090_timestamp = int(tcn090_dt.timestamp())

        silicon_battery_data.append({
            'command_sent_time': tcn090_time,
            'command_execution_time': tcn090_timestamp
        })

    result = json.dumps(silicon_battery_data, ensure_ascii=False)
    return result


def delete_platform_data_task(metedataservice_url, influxdb_action, host_action, tf1, tf2, satID):
    # Retrieve the command data
    AS_commands = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=tf1, tf2=tf2, satID=satID)

    # Filter for TCS815 commands
    TCS815_commands = AS_commands[AS_commands['cmd_code'] == 'TCS815']

    # Initialize list to store the results
    delete_payload_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')

    # Iterate over each TCS815 command
    for _, tcs815_row in TCS815_commands.iterrows():
        tcs815_time = tcs815_row['timestamp']
        tcs815_params = json.loads(tcs815_row['param'])
        tcs815_delay_seconds = tcs815_params['delayForm']['seconds']

        # Parse the delay time and convert it to a timestamp
        tcs815_dt = datetime.strptime(tcs815_delay_seconds, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
        tcs815_timestamp = int(tcs815_dt.timestamp())

        delete_payload_data.append({
            'command_time': tcs815_time,
            'delay_time': tcs815_timestamp,
            'params': tcs815_params['packageForm']['params']
        })

    result = json.dumps(delete_payload_data, ensure_ascii=False)
    return result


def delete_payload_data_task(metedataservice_url, influxdb_action, host_action, tf1, tf2, satID):
    # Retrieve the command data
    AS_commands = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=tf1, tf2=tf2, satID=satID)

    # Filter for TCS815 commands
    TCS815_commands = AS_commands[AS_commands['cmd_code'] == 'TCS808']

    # Initialize list to store the results
    delete_payload_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')

    # Iterate over each TCS815 command
    for _, tcs815_row in TCS815_commands.iterrows():
        tcs815_time = tcs815_row['timestamp']
        tcs815_params = json.loads(tcs815_row['param'])
        tcs815_delay_seconds = tcs815_params['delayForm']['seconds']

        # Parse the delay time and convert it to a timestamp
        tcs815_dt = datetime.strptime(tcs815_delay_seconds, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
        tcs815_timestamp = int(tcs815_dt.timestamp())

        delete_payload_data.append({
            'command_time': tcs815_time,
            'delay_time': tcs815_timestamp,
            'params': tcs815_params['packageForm']['params']
        })

    result = json.dumps(delete_payload_data, ensure_ascii=False)
    return result

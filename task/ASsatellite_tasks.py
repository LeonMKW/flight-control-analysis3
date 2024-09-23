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

from utils.ASsatellitestatus_utils import get_AScommands, get_AS02_datatransmission, get_AS02_hist_data_save, \
    get_AS03_in_sight_sensing_task_data, get_AS03_out_sight_sensing_task_data, get_AS03_hist_data_save
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


def delete_platform_folder_task(metedataservice_url, influxdb_action, host_action, tf1, tf2, satID):
    # Retrieve the command data
    AS_commands = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=tf1, tf2=tf2, satID=satID)

    # Filter for TCS815 commands
    TCS815_commands = AS_commands[AS_commands['cmd_code'] == 'TCH208']

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
    # print(result)
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


def AS03_sensing_upload(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    # Retrieve the command data
    AS03_commands = get_AScommands(metedataservice_url, _influxdb, client, tf1, tf2, satID)

    # Filter for relevant commands
    TCKAF15_commands = AS03_commands[AS03_commands['cmd_code'] == 'TCKAF15']
    TCKBB02_commands = AS03_commands[AS03_commands['cmd_code'] == 'TCKBB02']

    # Initialize list to store the results
    sensing_task_data = []

    # Iterate over each TCKAF15 command
    for _, tckaf15_row in TCKAF15_commands.iterrows():
        tckaf15_time = tckaf15_row['timestamp']
        tckaf15_params = json.loads(tckaf15_row['param'])['packageForm']['params']

        task_start = tckaf15_params['start']
        task_end = tckaf15_params['end']
        duration = task_end - task_start
        side = tckaf15_params['side']
        lat = tckaf15_params['latka']
        lon = tckaf15_params['lonka']
        alt = tckaf15_params['altka']

        # Check for task cancellation
        cancel_task = TCKBB02_commands[
            (TCKBB02_commands['timestamp'] > tckaf15_time) &
            (TCKBB02_commands['timestamp'] <= tckaf15_time + 300) &
            (TCKBB02_commands['param'].apply(
                lambda x: json.loads(x)['packageForm']['params'].get('v0') == 26214))
            ]

        if not cancel_task.empty:
            continue

        # Check for duplicate tasks
        if any(abs(task_start - task['TCKAF15']['start']) < 60 for task in sensing_task_data):
            continue

        sensing_task_data.append({
            'TCKAF15': {
                'timestamp': tckaf15_time,
                'start': task_start,
                'end': task_end,
                'duration': duration,
                'side': side,
                'lat': lat,
                'lon': lon,
                'alt': alt
            }
        })

    result = json.dumps(sensing_task_data, ensure_ascii=False)
    return result


def AS03_in_sight_sensing_task(orbit_service, metedataservice_url, _influxdb, client, tf1, tf2, satID):
    # Retrieve the telemetry data
    result_df_00F0, result_df_0620, result_df_0094, result_df_0684 = get_AS03_in_sight_sensing_task_data(
        metedataservice_url, _influxdb, client, tf1, tf2, satID)
    result_df_00F0['timestamp'] = result_df_00F0['timestamp'].astype(float)
    result_df_0620['timestamp'] = result_df_0620['timestamp'].astype(float)
    result_df_0094['timestamp'] = result_df_0094['timestamp'].astype(float)
    result_df_0684['timestamp'] = result_df_0684['timestamp'].astype(float)

    task_list = get_task_list(orbit_service, tf1, tf2, satID)

    result = {'InfaredSensing': {}}

    for i, task in task_list.iterrows():
        task_start = pd.to_datetime(task['starting'])
        task_end = pd.to_datetime(task['ending'])

        # Get data within task start and end times
        df_00F0_task = result_df_00F0[(result_df_00F0['timestamp'] >= task_start.timestamp()) &
                                      (result_df_00F0['timestamp'] <= task_end.timestamp())]

        df_0620_task = result_df_0620[(result_df_0620['timestamp'] >= task_start.timestamp()) &
                                      (result_df_0620['timestamp'] <= task_end.timestamp())]
        df_0094_task = result_df_0094[(result_df_0094['timestamp'] >= task_start.timestamp()) &
                                      (result_df_0094['timestamp'] <= task_end.timestamp())]
        df_0684_task = result_df_0684[(result_df_0684['timestamp'] >= task_start.timestamp()) &
                                      (result_df_0684['timestamp'] <= task_end.timestamp())]

        # Process probeon (1.2)
        probeon_groups = (df_00F0_task['TMY002'] != df_00F0_task['TMY002'].shift()).cumsum()
        consecutive_probeon_groups = df_00F0_task.groupby(probeon_groups).filter(
            lambda x: (x['TMY002'] == 15).all() and len(x) >= 2)

        probeon_data = {}
        for j, (group, group_df) in enumerate(consecutive_probeon_groups.groupby(probeon_groups), start=1):
            if (group_df['TMY002'] == 15).all():
                starttimestamp = group_df['timestamp'].iloc[0]
                endtimestamp = group_df['timestamp'].iloc[-1]
                duration = endtimestamp - starttimestamp
                probeon_data[str(j)] = {
                    'starttimestamp': starttimestamp,
                    'endtimestamp': endtimestamp,
                    'duration': duration
                }

        # Process cameraon and shooting (1.3, 1.4, 1.5)
        cameraon = df_0620_task[df_0620_task['TMH1084'] == 1]
        shooting = df_00F0_task[df_00F0_task['TMY005'] == 2]

        cameraon_data = {
            'starttimestamp': cameraon['timestamp'].iloc[0] if not cameraon.empty else None,
            'endtimestamp': cameraon['timestamp'].iloc[-1] if not cameraon.empty else None,
            'duration': (cameraon['timestamp'].iloc[-1] - cameraon['timestamp'].iloc[0]) if not cameraon.empty else None
        }

        shooting_data = {
            'starttimestamp': shooting['timestamp'].iloc[0] if not shooting.empty else None,
            'endtimestamp': shooting['timestamp'].iloc[-1] if not shooting.empty else None,
            'duration': (shooting['timestamp'].iloc[-1] - shooting['timestamp'].iloc[0]) if not shooting.empty else None
        }

        # Process temperatures (1.3, 1.4, 1.5)
        if not cameraon.empty:
            cameraon_tmy017 = df_00F0_task[(df_00F0_task['timestamp'] >= cameraon['timestamp'].iloc[0]) &
                                           (df_00F0_task['timestamp'] <= cameraon['timestamp'].iloc[-1])]
            cameraon_tms627 = df_0094_task[(df_0094_task['timestamp'] >= cameraon['timestamp'].iloc[0]) &
                                           (df_0094_task['timestamp'] <= cameraon['timestamp'].iloc[-1])]
        else:
            cameraon_tmy017 = pd.DataFrame()
            cameraon_tms627 = pd.DataFrame()

        if not shooting.empty:
            shooting_tms627 = df_0094_task[(df_0094_task['timestamp'] >= shooting['timestamp'].iloc[0]) &
                                           (df_0094_task['timestamp'] <= shooting['timestamp'].iloc[-1])]
        else:
            shooting_tms627 = pd.DataFrame()

        cameraon_tmy017_data = {
            'time': cameraon_tmy017['timestamp'].tolist() if not cameraon_tmy017.empty else [],
            'value': cameraon_tmy017['TMY017'].tolist() if not cameraon_tmy017.empty else []
        }

        cameraon_tms627_data = {
            'time': cameraon_tms627['timestamp'].tolist() if not cameraon_tms627.empty else [],
            'value': cameraon_tms627['TMS627'].tolist() if not cameraon_tms627.empty else []
        }

        shooting_tms627_data = {
            'time': shooting_tms627['timestamp'].tolist() if not shooting_tms627.empty else [],
            'value': shooting_tms627['TMS627'].tolist() if not shooting_tms627.empty else []
        }

        # Initialize status fields
        sensing_status = "0"
        ram_status = "0"
        infra_B_can_bus_status = "0"
        side_swipe_angle = None

        # Check for status conditions
        if df_0620_task['TMH1084'].sum() > 10:
            sensing_status = "1"
            # Get the interval of the first and last timestamp where TMH1084 == 1
            interval_start = df_0620_task[df_0620_task['TMH1084'] == 1]['timestamp'].iloc[0]
            interval_end = df_0620_task[df_0620_task['TMH1084'] == 1]['timestamp'].iloc[-1]

            interval_df_0620 = df_0620_task[(df_0620_task['timestamp'] >= interval_start) &
                                            (df_0620_task['timestamp'] <= interval_end)]

            if interval_df_0620['TMH1070'].sum() > 10:
                ram_status = "1"
                infra_B_can_bus_status = "0"
            if interval_df_0620['TMH1090'].sum() <= 10:
                infra_B_can_bus_status = "1"
                ram_status = "0"

            # Get the first value of TMK2115 that is not 0 during the task period
            side_swipe_angle_values = df_0684_task[df_0684_task['TMK2115'] != 0]['TMK2115']
            if not side_swipe_angle_values.empty:
                side_swipe_angle = side_swipe_angle_values.iloc[0]

        # Assemble task data
        if sensing_status == "1":  # Only add the task data if sensing_status is "1"
            task_data = {
                'probeon(探测器上电时间)': probeon_data,
                'cameraon(相机上下电时间)': cameraon_data,
                'shooting(成像时间)': shooting_data,
                'cameraonTMY017(相机上电焦面测点)': cameraon_tmy017_data,
                'cameraonTMS627(相机上电制冷机测点)': cameraon_tms627_data,
                'shootingTMS627(成像期间电制冷机测点)': shooting_tms627_data,
                'sensing_status': sensing_status,  # 0无成像 1成像
                'ram_status': ram_status,  # 0好1坏
                'infra_B_can_bus_status': infra_B_can_bus_status,  # 0好1坏
                'side-swipe-angle': side_swipe_angle
            }

            result['InfaredSensing'][str(i + 1)] = task_data

    return json.dumps(result, indent=4, ensure_ascii=False)


def AS03_out_sight_sensing_task(orbit_service, metedataservice_url, _influxdb, client, influxdb_action, host_action,
                                tf1, tf2, satID):
    # Step 1: Get the uploaded sensing data tasks
    AS03_sensing_upload_data = AS03_sensing_upload(metedataservice_url, influxdb_action, host_action, tf1, tf2, satID)
    AS03_sensing_upload_data = json.loads(AS03_sensing_upload_data)  # Parse JSON data

    # Step 2: Adjust satIDs based on satID
    if satID == '13':
        satIDs = '13,16'  # Include both '13' and '16'
    else:
        satIDs = satID

    # Call get_task_list with the adjusted satIDs
    task_list = get_task_list(orbit_service, tf1, tf2, satIDs)
    # Ensure 'task_list' is a DataFrame
    if not isinstance(task_list, pd.DataFrame):
        raise ValueError("Expected task_list to be a DataFrame, but got something else.")

    # Step 3: Retrieve the telemetry data
    result_df_00F0, result_df_0620, result_df_0684 = get_AS03_out_sight_sensing_task_data(
        metedataservice_url, _influxdb, client, tf1, tf2, satID)

    # Ensure result_df_0620 is a DataFrame
    if not isinstance(result_df_0620, pd.DataFrame):
        raise ValueError("Expected result_df_0620 to be a DataFrame, but got something else.")

    result_df_0620['timestamp'] = result_df_0620['timestamp'].astype(float)

    result = {'InfaredSensing': {}}

    # Step 4: Identify out-of-sight tasks
    out_sight_tasks = []
    for task in AS03_sensing_upload_data:
        task_start = task['TCKAF15']['start']  # Start time in seconds since epoch
        task_end = task['TCKAF15']['end']
        duration = task['TCKAF15']['duration']
        side = task['TCKAF15']['side']
        lat = task['TCKAF15']['lat']
        lon = task['TCKAF15']['lon']
        alt = task['TCKAF15']['alt']
        # Check if task_start is within any task in task_list
        in_sight = False
        for _, row in task_list.iterrows():
            list_task_start = pd.to_datetime(row['starting'], utc=True).timestamp()
            list_task_end = pd.to_datetime(row['ending'], utc=True).timestamp()
            if list_task_start <= task_start <= list_task_end:
                in_sight = True
                break
        if not in_sight:
            # This is an out-of-sight task
            out_sight_tasks.append(task)

    # Step 5: Process each out-of-sight task
    for i, task in enumerate(out_sight_tasks, start=1):
        task_info = task['TCKAF15']
        task_start = task_info['start']
        task_end = task_info['end']
        duration = task_info['duration']
        side = task_info['side']
        lat = task_info['lat']
        lon = task_info['lon']
        alt = task_info['alt']

        # Search TMH1084 in ±1800 seconds of task_start
        window_start = task_start - 1800
        window_end = task_start + 1800

        # Filter result_df_0620 within this window
        df_window = result_df_0620[
            (result_df_0620['timestamp'] >= window_start) &
            (result_df_0620['timestamp'] <= window_end)
            ]

        # Find intervals where TMH1084 == 1
        sensing_tasks = df_window[df_window['TMH1084'] == 1]

        if sensing_tasks.empty:
            # No sensing activity for this task, set fields to 'nodata'
            task_data = {
                'upload_task': {
                    'start': task_start,
                    'end': task_end,
                    'duration': duration,
                    'side': side,
                    'lat': lat,
                    'lon': lon,
                    'alt': alt
                },
                'cameraon': {
                    'starttimestamp': 'nodata',
                    'endtimestamp': 'nodata',
                    'duration': 'nodata'
                },
                'ram_status': 'nodata',
                'infra_B_can_bus_status': 'nodata',
            }
            # Use a unique key for each task
            result['InfaredSensing'][f'Task_{i}'] = task_data
            continue  # Skip to the next task

        # Proceed if sensing_tasks is not empty
        # Calculate the time difference between consecutive rows
        sensing_tasks = sensing_tasks.copy()  # Avoid SettingWithCopyWarning
        sensing_tasks['time_diff'] = sensing_tasks['timestamp'].diff().fillna(0)

        # Group consecutive intervals where the time difference is less than 200 seconds
        sensing_tasks['group'] = (sensing_tasks['time_diff'] > 200).cumsum()

        # Step 6: Process each group
        for group_id, group_df in sensing_tasks.groupby('group'):
            group_task_start = group_df['timestamp'].iloc[0]
            group_task_end = group_df['timestamp'].iloc[-1]

            # Calculate ram_status and infra_B_can_bus_status
            if group_df['TMH1070'].sum() > 1:
                ram_status = "1"
                infra_B_can_bus_status = "0"
            elif group_df['TMH1090'].sum() == 0:
                infra_B_can_bus_status = "1"
                ram_status = "0"
            else:
                ram_status = "0"
                infra_B_can_bus_status = "0"

            # Process cameraon data
            cameraon_data = {
                'starttimestamp': group_task_start,
                'endtimestamp': group_task_end,
                'duration': group_task_end - group_task_start
            }

            # Assemble task data with additional task information
            task_data = {
                'upload_task': {
                    'start': task_start,
                    'end': task_end,
                    'duration': duration,
                    'side': side,
                    'lat': lat,
                    'lon': lon,
                    'alt': alt
                },
                'cameraon': cameraon_data,
                'ram_status': ram_status,  # 0: good, 1: bad
                'infra_B_can_bus_status': infra_B_can_bus_status,  # 0: good, 1: bad
            }

            # Use a unique key for each task and group
            result['InfaredSensing'][f'Task_{i}_Group_{group_id}'] = task_data

    return json.dumps(result, indent=4, ensure_ascii=False)


def AS03_payload_data_transmission(metedataservice_url, _influxdb_input, client_input, influxdb_action, host_action,
                                   tf1, tf2, satID):
    # Retrieve the command data
    AS03_payloaddatatransmission = get_AS02_datatransmission(metedataservice_url, _influxdb_input, client_input, tf1,
                                                             tf2, satID)

    # Remove duplicate rows with the same TMK2014 and TMK2015 values, keeping only the first occurrence
    AS03_payloaddatatransmission = AS03_payloaddatatransmission.drop_duplicates(subset=['TMK2014', 'TMK2015'])

    # Initialize list to store the results
    payload_transmission_data = []

    # Iterate over each TMK2014 and TMK2015 pair
    for _, payload_row in AS03_payloaddatatransmission.iterrows():
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

                # Filter TCS804 commands based on DataSource
                matching_tcs804_payload = matching_tcs804[
                    (matching_tcs804['param'].apply(
                        lambda x: json.loads(x)['packageForm']['params'].get('DataSource') == 1))
                ]

                if matching_tcs804_payload.empty:
                    continue

                tcs804_list = []
                for _, tcs804_row in matching_tcs804_payload.iterrows():
                    tcs804_params = json.loads(tcs804_row['param'])

                    # Extract File1 and File2
                    file_params = tcs804_params['packageForm']['params']
                    file1 = file_params.get('FileStart')
                    file2 = file_params.get('FileEnd')

                    tcs804_list.append({
                        'timestamp': tcs804_row['timestamp'],
                        'FileStart': file1,
                        'FileEnd': file2
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


def AS03_platform_data_transmission(metedataservice_url, _influxdb_input, client_input, influxdb_action, host_action,
                                    tf1, tf2, satID):
    # Retrieve the command data
    AS03_payloaddatatransmission = get_AS02_datatransmission(metedataservice_url, _influxdb_input, client_input, tf1,
                                                             tf2, satID)

    # Remove duplicate rows with the same TMK2014 and TMK2015 values, keeping only the first occurrence
    AS03_payloaddatatransmission = AS03_payloaddatatransmission.drop_duplicates(subset=['TMK2014', 'TMK2015'])

    # Initialize list to store the results
    payload_transmission_data = []

    # Iterate over each TMK2014 and TMK2015 pair
    for _, payload_row in AS03_payloaddatatransmission.iterrows():
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

                # Filter TCS804 commands based on DataSource
                matching_tcs804_payload = matching_tcs804[
                    (matching_tcs804['param'].apply(
                        lambda x: json.loads(x)['packageForm']['params'].get('DataSource') == 0))
                ]

                if matching_tcs804_payload.empty:
                    continue

                tcs804_list = []
                for _, tcs804_row in matching_tcs804_payload.iterrows():
                    tcs804_params = json.loads(tcs804_row['param'])

                    # Extract File1 and File2
                    file_params = tcs804_params['packageForm']['params']
                    file1 = file_params.get('FileStart')
                    file2 = file_params.get('FileEnd')

                    tcs804_list.append({
                        'timestamp': tcs804_row['timestamp'],
                        'FileStart': file1,
                        'FileEnd': file2
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


def AS03_hist_file_save(metedataservice_url, _influxdb_input, client_input, influxdb_action, host_action, tf1, tf2,
                        satID):
    # Retrieve the command data
    AS03hist_file_save_command = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=tf1, tf2=tf2,
                                                satID=satID)

    # Retrieve the telemetry data
    AS03hist_file_save_telemetry = get_AS03_hist_data_save(metedataservice_url, _influxdb_input, client_input, tf1, tf2,
                                                           satID)

    # Filter for relevant commands
    TCS813_commands = AS03hist_file_save_command[AS03hist_file_save_command['cmd_code'] == 'TCS813']
    TCS803_commands = AS03hist_file_save_command[AS03hist_file_save_command['cmd_code'] == 'TCS803']
    TCH209_commands = AS03hist_file_save_command[AS03hist_file_save_command['cmd_code'] == 'TCH209']

    # Initialize list to store the results
    hist_file_save_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')

    # Iterate over each TCS813 command
    for _, tcs813_row in TCS813_commands.iterrows():
        tcs813_time = tcs813_row['timestamp']
        tcs813_params = json.loads(tcs813_row['param'])

        # Check "Payload" == 0
        if tcs813_params['packageForm']['params'].get('Payload') != 0:
            continue

        # Find the nearest TCS803 command after TCS813
        matching_tcs803 = TCS803_commands[
            (TCS803_commands['timestamp'] > tcs813_time)
        ]

        if matching_tcs803.empty:
            return {'error': 'file_saving_stop_not_found(TCS803)'}

        tcs803_row = matching_tcs803.iloc[0]
        tcs803_time = tcs803_row['timestamp']
        tcs803_params = json.loads(tcs803_row['param'])
        tcs803_delay_seconds = tcs803_params['delayForm']['seconds']

        # Parse the delay time and convert it to a timestamp
        tcs803_dt = datetime.strptime(tcs803_delay_seconds, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
        tcs803_timestamp = int(tcs803_dt.timestamp())

        # Find the corresponding TCH209 commands between TCS813 and TCS803
        matching_tch209 = TCH209_commands[
            (TCH209_commands['timestamp'] > tcs813_time) &
            (TCH209_commands['timestamp'] <= tcs803_time)
            ]

        tch209_filenames = []
        for _, tch209_row in matching_tch209.iterrows():
            tch209_params = json.loads(tch209_row['param'])
            tch209_filenames.append(tch209_params['packageForm']['params']['filename'])

        # Find the first record in TMS043 after TCS813
        matching_tms043_start = AS03hist_file_save_telemetry[
            (AS03hist_file_save_telemetry['timestamp'] > tcs813_time)
        ]

        if matching_tms043_start.empty:
            continue

        tms043_start_time = matching_tms043_start.iloc[0]['timestamp']
        tms043_start_value = matching_tms043_start.iloc[0]['TMS043']

        # Find the first record in TMS043 after TCS803's delay seconds
        matching_tms043_end = AS03hist_file_save_telemetry[
            (AS03hist_file_save_telemetry['timestamp'] > tcs803_timestamp)
        ]

        if matching_tms043_end.empty:
            continue

        tms043_end_time = matching_tms043_end.iloc[0]['timestamp']
        tms043_end_value = matching_tms043_end.iloc[0]['TMS043']

        # Calculate the absolute difference of values
        file_size = abs(tms043_end_value - tms043_start_value)

        hist_file_save_data.append({
            'hist_data_saving_time': tcs813_time,
            'save_to_number': tcs813_params['packageForm']['params'].get('FIle', 0),
            'files_saved': tch209_filenames,
            'file_size': file_size
        })

    result = json.dumps(hist_file_save_data, ensure_ascii=False)
    return result


def AS03_delete_data_task(metedataservice_url, influxdb_action, host_action, tf1, tf2, satID):
    # Retrieve the command data
    AS_commands = get_AScommands(metedataservice_url, influxdb_action, host_action, tf1=tf1, tf2=tf2, satID=satID)

    # Filter for TCS809 commands
    TCS809_commands = AS_commands[AS_commands['cmd_code'] == 'TCS809']

    # Initialize list to store the results
    delete_payload_data = []

    # Define the timezone
    tz_utc = pytz.utc

    # Iterate over each TCS809 command
    for _, tcs809_row in TCS809_commands.iterrows():
        tcs809_time = tcs809_row['timestamp']
        tcs809_params = json.loads(tcs809_row['param'])
        tcs809_delay_seconds = tcs809_params['delayForm']['seconds']

        # Parse the delay time and convert it to a timestamp
        tcs809_dt = datetime.strptime(tcs809_delay_seconds, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
        tcs809_timestamp = int(tcs809_dt.timestamp())

        # Determine the delete_data_type
        delete_data_type = "0" if tcs809_params['packageForm']['params']['DataSource'] == "00" else "1"

        delete_payload_data.append({
            'command_time': tcs809_time,
            'delay_time': tcs809_timestamp,
            'params': tcs809_params['packageForm']['params'],
            'delete_data_type': delete_data_type
        })

    # Remove records with the same FileEnd and FileStart, keeping the one with the smaller command_time
    unique_payload_data = []
    seen_params = {}
    for data in delete_payload_data:
        key = (data['params']['FileEnd'], data['params']['FileStart'])
        if key not in seen_params or seen_params[key]['command_time'] > data['command_time']:
            seen_params[key] = data

    unique_payload_data = list(seen_params.values())

    result = json.dumps(unique_payload_data, ensure_ascii=False)
    return result

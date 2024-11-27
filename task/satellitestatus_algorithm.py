# -*- coding: UTF-8 -*-
import pytz
import dfply as d
from datetime import datetime, timedelta
from utils.flightcontrol_utils import tm_table, obc_resetnew
from utils.db import get_mongo
import logging
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from utils.flightcontrol_utils import vcIdnew, get_task_list, commands, correctframe, uplock, obc_resetnew, payload_pwr, \
    file_inspect, \
    electric_propulsion, monitor_data, orbit_data, experimental_lock_data, experimental_telemetry_data, \
    hist_interval_data, gnss_interval_data
from tqdm import tqdm
from utils.db import set_value, init_val
from data.fileinspection import map_dict
from utils.core_algorithm import analyze_lock_intervals, analyze_lock_status, analyze_telemetry_intervals, \
    calculate_hist_interval, calculate_gnss_interval
from utils.satellitestatus_utils import OBCreset_influx, OBCswitch_influx, OBCreset_mongo_records
from utils.db import get_mongo
from utils.flightcontrol_utils import tm_table
from utils.notification_content import OBC_cumulative_reset_content
import requests


def write_reset_count(post_token_url,
                      post_token_user_name,
                      post_token_password, metedataservice_url, influxdb, client, tf1, tf2, satID):
    resettime_data = OBCreset_influx(post_token_url,
                                     post_token_user_name,
                                     post_token_password, metedataservice_url, influxdb, client, tf1, tf2, satID)
    # print(resettime_data.to_string())
    resettime_data['reset_detect'] = (resettime_data['obc_reset'] != resettime_data['obc_reset'].shift()).astype(int)
    # Force the first row of 'obc_switch' and 'obc_reset' columns to be 0
    resettime_data.loc[0, ['reset_detect']] = 0

    # obc reset

    # Get rows where 'obc_reset' is not equal to 0
    non_zero_reset = resettime_data[(resettime_data['reset_detect'] != 0)]
    # print(non_zero_reset.to_string())

    non_zero_record = []

    eventid = None
    time_found = None
    satellite_code = None
    for index, row in non_zero_reset.iterrows():
        if row['obc_reset'] != 0:
            eventid = row['_satelliteCode'] + str(int(row['timestamp']))
            time_found = row['timestamp']
            satellite_code = row['_satelliteCode']
        elif row['obc_reset'] == 0 and eventid is not None:
            time_end = row['timestamp']
            # Skip writing if time_end is 0
            if time_end != 0 and time_end is not None:
                reset_count = 1
                non_zero_record.append({
                    '_satelliteCode': satellite_code,
                    'eventid': eventid,
                    'time_found': time_found,
                    'time_end': time_end,
                    'reset_count': reset_count,
                    'switch_count': 0,
                    'switch': '0',
                    'reset': '1',
                })
            eventid = None

    # Update reset_count based on non_zero_reset
    for record in non_zero_record:
        reset_value = non_zero_reset.loc[non_zero_reset['timestamp'] == record['time_found'], 'obc_reset'].values
        if len(reset_value) > 0:
            record['reset_count'] = reset_value[0]

    mongo_instance = get_mongo()

    # Insert or update documents in the collection
    for doc in non_zero_record:
        eventid = doc['eventid']
        existing_doc = mongo_instance.read_OBCrecord_data(eventid, 'OBC_reset_records')
        if existing_doc:
            # Update the existing document
            mongo_instance.update_flight_operation_satellite_data(doc, 'OBC_reset_records', eventid)
            print("OBC reset updated", eventid)
        else:
            # Insert a new document
            mongo_instance.write_flight_operation_data(doc, 'OBC_reset_records')
            print("new OBC reset detected", eventid)
            # print(doc)

    return print("executing OBC reset algorithm:", satID)


# def write_switch_count(metedataservice_url, influxdb, client, tf1, tf2, satID):
#     resettime_data = OBCswitch_influx(metedataservice_url, influxdb, client, tf1, tf2, satID)
#
#     # Check if 'obc_switch' column exists
#     if 'obc_switch' not in resettime_data.columns:
#         print("No 'obc_switch' detected")
#         return
#
#     # Add new columns 'switch_detect'
#     resettime_data['switch_detect'] = (resettime_data['obc_switch'] != resettime_data['obc_switch'].shift()).astype(int)
#     resettime_data.loc[0, ['switch_detect']] = 0
#
#     # obc switch
#
#     # Get rows where 'obc_switch' is not equal to 0
#     non_zero_switch = resettime_data.dropna(subset=['obc_switch']).loc[resettime_data['switch_detect'] != 0]
#
#     non_zero_switch_records = []
#
#     for index, row in non_zero_switch.iterrows():
#         # Only proceed if 'switch_detect' is equal to 1
#         if row['switch_detect'] == 1:
#             eventid = row['_satelliteCode'] + str(int(row['timestamp']))
#             time_found = row['timestamp']
#             non_zero_switch_records.append({
#                 '_satelliteCode': row['_satelliteCode'],
#                 'eventid': eventid,
#                 'time_found': time_found,
#                 'obc_switch': row['obc_switch'],
#                 'switch_count': 1,
#                 'switch': '1',
#                 'reset': '0'
#             })
#
#     # print(non_zero_switch.to_string())
#     # print(non_zero_switch_records)
#     mongo_instance = get_mongo()
#
#     # Insert or update documents in the collection
#     for doc in non_zero_switch_records:
#         eventid = doc['eventid']
#         existing_doc = mongo_instance.read_OBCrecord_data(eventid, 'OBC_switch_records')
#         if existing_doc:
#             # Update the existing document
#             mongo_instance.update_flight_operation_satellite_data(doc, 'OBC_switch_records', eventid)
#             print("OBC switch updated", eventid)
#         else:
#             # Insert a new document
#             mongo_instance.write_flight_operation_data(doc, 'OBC_switch_records')
#             print("new OBC switch detected", eventid)
#
#     return print("executing OBC switch algorithm：", satID)


def write_switch_count(post_token_url,
                       post_token_user_name,
                       post_token_password,
                       metedataservice_url, influxdb, client, tf1, tf2, satID):
    resettime_data = OBCswitch_influx(post_token_url,
                                      post_token_user_name,
                                      post_token_password, metedataservice_url, influxdb, client, tf1, tf2, satID)

    # Check if 'obc_switch' column exists
    if 'obc_switch' not in resettime_data.columns:
        print("No 'obc_switch' detected")
        return

    # Add new columns 'switch_detect'
    resettime_data['switch_detect'] = (resettime_data['obc_switch'] != resettime_data['obc_switch'].shift()).astype(int)
    resettime_data.loc[0, ['switch_detect']] = 0

    # Get rows where 'obc_switch' is not equal to 0
    non_zero_switch = resettime_data.dropna(subset=['obc_switch']).loc[resettime_data['switch_detect'] != 0]

    if len(non_zero_switch) >= 2:
        non_zero_switch = non_zero_switch.reset_index(drop=True)

        i = 1
        while i < len(non_zero_switch):
            current_timestamp = non_zero_switch.loc[i, 'timestamp']
            previous_timestamp = non_zero_switch.loc[i - 1, 'timestamp']

            if (current_timestamp - previous_timestamp) < 8:
                non_zero_switch = non_zero_switch.drop([i, i - 1])
                non_zero_switch = non_zero_switch.reset_index(drop=True)
                i = max(i - 1, 1)
            else:
                i += 1

        if len(non_zero_switch) == 0:
            print('outlier in switch')
            return

    non_zero_switch_records = []

    for index, row in non_zero_switch.iterrows():
        # Only proceed if 'switch_detect' is equal to 1
        if row['switch_detect'] == 1:
            eventid = row['_satelliteCode'] + str(int(row['timestamp']))
            time_found = row['timestamp']
            non_zero_switch_records.append({
                '_satelliteCode': row['_satelliteCode'],
                'eventid': eventid,
                'time_found': time_found,
                'obc_switch': row['obc_switch'],
                'switch_count': 1,
                'switch': '1',
                'reset': '0'
            })

    mongo_instance = get_mongo()

    # Insert or update documents in the collection
    for doc in non_zero_switch_records:
        eventid = doc['eventid']
        existing_doc = mongo_instance.read_OBCrecord_data(eventid, 'OBC_switch_records')
        if existing_doc:
            # Update the existing document
            mongo_instance.update_flight_operation_satellite_data(doc, 'OBC_switch_records', eventid)
            print("OBC switch updated", eventid)
        else:
            # Insert a new document
            mongo_instance.write_flight_operation_data(doc, 'OBC_switch_records')
            print("new OBC switch detected", eventid)

    print("executing OBC switch algorithm:", satID)


def check_repeating_records(post_token_url,
                            post_token_user_name,
                            post_token_password, metedataservice_url, tf1, tf2, satID):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']

    if not tf1 or not tf2:
        now = datetime.now()
        ten_minutes_ago = now - timedelta(minutes=2880)
        tf2 = int(now.timestamp())
        tf1 = int(ten_minutes_ago.timestamp())
    else:
        tf2 = datetime.strptime(tf2, "%Y-%m-%dT%H:%M:%S.%fZ")
        tf1 = datetime.strptime(tf1, "%Y-%m-%dT%H:%M:%S.%fZ")

        tf2 = int(datetime.timestamp(tf2))
        tf1 = int(datetime.timestamp(tf1))

    # Initialize Mongo class and get MongoDBconnection
    mongo_instance = get_mongo()

    check_query = {
        '$and': [
            {'_satelliteCode': str(satelliteCode)},
            {'time_found': {'$gte': tf1,
                            '$lte': tf2}}
        ]
    }
    to_be_cleared = mongo_instance.get_all_data('OBC_reset_records', check_query)

    to_be_cleared = list(to_be_cleared)

    # Sort records by time_found
    sorted_records = sorted(to_be_cleared, key=lambda x: x['time_found'])

    # List to store non-overlapping records
    non_overlapping_records = []

    # Initialize variable to store the end time of the last processed record
    last_end_time = float('-inf')

    # Iterate through records
    for record in sorted_records:
        time_found = record['time_found']
        time_end = record['time_end']

        # Check for overlap with the previous record
        if time_found <= last_end_time:
            # Overlapping records found, skip this record
            continue

        # Add this record to non-overlapping records
        non_overlapping_records.append(record)

        # Update the last end time
        last_end_time = time_end

    # print(non_overlapping_records)

    # Remove records from the collection
    for record in to_be_cleared:
        if record not in non_overlapping_records:
            mongo_instance.delete_nearest_data('OBC_reset_records', {'eventid': record['eventid']})
            mongo_instance.delete_nearest_data('cumulative_reset_count', {'eventid': record['eventid']})
    return non_overlapping_records


def calculate_cumulative_reset(post_token_url,
                               post_token_user_name,
                               post_token_password, metedataservice_url, tf1, tf2, satID, note_url):
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satID)
    satelliteCode = tm[satID]['code']

    # Convert time strings to timestamps
    if not tf1 or not tf2:
        now = datetime.now()
        ten_minutes_ago = now - timedelta(minutes=2880)
        tf2 = int(now.timestamp())
        tf1 = int(ten_minutes_ago.timestamp())
    # else:
    #     tf2 = int(datetime.strptime(tf2, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
    #     tf1 = int(datetime.strptime(tf1, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())

    # Initialize Mongo class and get MongoDB connection
    mongo_instance = get_mongo()

    # Retrieve reset records within the specified time interval and for the given satelliteCode
    check_query = {
        '$and': [
            {'_satelliteCode': str(satelliteCode)},
            {'time_found': {'$gte': tf1, '$lte': tf2}}
        ]
    }
    # print(check_query)
    reset_records = mongo_instance.get_all_data('OBC_reset_records', check_query)
    # print(type(reset_records))
    # print(list(reset_records))
    # reset_records = list(reset_records)
    # print(len(reset_records))
    if reset_records:
        # Iterate over reset records
        for reset_record in reset_records:
            # Check if the eventid already exists in cumulative_reset_count
            existing_doc = mongo_instance.read_OBCrecord_data(reset_record['eventid'], 'cumulative_reset_count')
            # print(type(existing_doc))
            # print(existing_doc)
            # print(list(existing_doc))

            if not existing_doc:
                # Find the nearest switch record
                switch_query = {
                    '_satelliteCode': str(satelliteCode),
                    'time_found': {'$lt': reset_record['time_found']}
                }
                nearest_switch = mongo_instance.get_nearest_data('OBC_switch_records', switch_query)
                # nearest_switch = list(nearest_switch_cursor)  # Assuming there's only one nearest switch
                # print(nearest_switch)

                # Find reset records between nearest switch and current reset record
                reset_query = {
                    '_satelliteCode': str(satelliteCode),
                    'time_found': {'$gte': nearest_switch['time_found'], '$lt': reset_record['time_found']}
                }
                reset_records_between = mongo_instance.get_all_data('OBC_reset_records', reset_query)
                # print(list(reset_records_between))

                # Calculate cumulative reset count
                cumulative_count = sum(reset['reset_count'] for reset in reset_records_between) + reset_record[
                    'reset_count']

                # Store eventid, cumulative_count, and all other fields in the new collection
                cumulative_reset_doc = {
                    'eventid': reset_record['eventid'],
                    'cumulative_count': cumulative_count,
                    **reset_record  # Include all fields from reset_record
                }
                # print(cumulative_reset_doc['_satelliteCode'])
                # print(cumulative_reset_doc['cumulative_count'])
                mongo_instance.write_flight_operation_data(cumulative_reset_doc, 'cumulative_reset_count')
                content = OBC_cumulative_reset_content(cumulative_reset_doc)
                # print(content)
                response = requests.post(note_url, json=json.loads(content))
                # print(response.text)

                # Check response status
                if response.status_code == 200:
                    print("OBC_status posted successfully.")
                    # print(response.text)
                else:
                    print(f"Failed to post content. Status code: {response.status_code}")
                    print(response.text)

    else:
        print('No document found')

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
from utils.core_algorithm import get_nearest_document


def write_reset_count(metedataservice_url, influxdb, client, tf1, tf2, satID):
    resettime_data = OBCreset_influx(metedataservice_url, influxdb, client, tf1, tf2, satID)
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
                    'reset': '1'
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
        else:
            # Insert a new document
            mongo_instance.write_flight_operation_data(doc, 'OBC_reset_records')

    return print("executing OBC reset algorithm")


def write_switch_count(metedataservice_url, influxdb, client, tf1, tf2, satID):
    resettime_data = OBCswitch_influx(metedataservice_url, influxdb, client, tf1, tf2, satID)
    # print(resettime_data.to_string())
    # Add new columns 'switch_detect'
    resettime_data['switch_detect'] = (resettime_data['obc_switch'] != resettime_data['obc_switch'].shift()).astype(int)
    resettime_data.loc[0, ['switch_detect']] = 0

    # obc switch

    # Get rows where 'obc_switch' is not equal to 0
    non_zero_switch = resettime_data.dropna(subset=['obc_switch']).loc[resettime_data['obc_switch'] != 0]

    non_zero_switch_records = []

    for index, row in non_zero_switch.iterrows():
        # Only proceed if 'obc_switch' is not equal to 0
        if row['switch_detect'] != 0:
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

    # print(non_zero_switch.to_string())
    # print(non_zero_switch_records)
    mongo_instance = get_mongo()

    # Insert or update documents in the collection
    for doc in non_zero_switch_records:
        eventid = doc['eventid']
        existing_doc = mongo_instance.read_OBCrecord_data(eventid, 'OBC_switch_records')
        if existing_doc:
            # Update the existing document
            mongo_instance.update_flight_operation_satellite_data(doc, 'OBC_switch_records', eventid)
        else:
            # Insert a new document
            mongo_instance.write_flight_operation_data(doc, 'OBC_switch_records')

    return print("executing OBC switch algorithm")


def check_repeating_records(metedataservice_url, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
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

    # print(tf1)
    # print(tf2)
    # print(satelliteCode)

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
            # mongo_instance.delete_nearest_data('OBC_cumulative_reset', {'eventid': record['eventid']})
    return non_overlapping_records


def write_cumulative_data(metedataservice_url, tf1, tf2, satID):
    # TODO: now calculate cumulative reset after each switch found, group by _satelliteCode
    concatenated_df = OBCreset_mongo_records(metedataservice_url, tf1, tf2, satID)

    if concatenated_df is None:
        print("No new OBC anomal written")
        return

    concatenated_df = concatenated_df.sort_values(by='time_found', ascending=True)
    mongo_instance = get_mongo()
    # Iterate over the rows of the concatenated DataFrame
    for index, row in concatenated_df.iterrows():
        # Check if the eventid already exists in the MongoDB collection
        existing_doc = mongo_instance.read_OBCrecord_data(row['eventid'], 'OBC_cumulative_reset')

        # Construct the document to be inserted or updated
        doc = {
            '_satelliteCode': row['_satelliteCode'],
            'eventid': row['eventid'],
            'time_found': row['time_found'],
            'reset_count': row['reset_count'],
            'switch_count': row['switch_count'],
            'reset': row['reset'],
            'switch': row['switch'],
            'cumulative_count': row['cumulative_reset']
        }

        # If there is an existing document, update it
        if existing_doc:
            mongo_instance.update_flight_operation_satellite_data(doc, 'OBC_cumulative_reset', row['eventid'])
        else:
            # If there isn't an existing document, insert a new one
            mongo_instance.write_flight_operation_data(doc, 'OBC_cumulative_reset')

        return print("new OBC anomal written")

# def update_cumulative_reset(metedataservice_url, tf1, tf2, satID):
#     tm = tm_table(metedataservice_url, satID)
#     satelliteCode = tm[satID]['code']
#
#     if not tf1 or not tf2:
#         now = datetime.now()
#         ten_minutes_ago = now - timedelta(minutes=2880)
#         tf2 = now.timestamp() * 1000
#         tf1 = ten_minutes_ago.timestamp() * 1000
#     else:
#         tf2 = datetime.strptime(tf2, "%Y-%m-%dT%H:%M:%S.%fZ")
#         tf1 = datetime.strptime(tf1, "%Y-%m-%dT%H:%M:%S.%fZ")
#
#         tf2 = int(datetime.timestamp(tf2))
#         tf1 = int(datetime.timestamp(tf1))
#
#     # print(tf1)
#     # print(tf2)
#     # print(satelliteCode)
#
#     # Initialize Mongo class and get MongoDB connection
#     mongo_instance = get_mongo()
#     nearest_doc = get_nearest_document(mongo_instance, satelliteCode, time_found=)
#
#     # Query MongoDB to retrieve OBC_cumulative_reset records within the specified time range and satelliteCode
#     # cumlulative_query = {
#     #     '$and': [
#     #         {'_satelliteCode': str(satelliteCode)},
#     #         {'time_found': {'$gte': tf1, '$lte': tf2}},
#     #         {'cumulative_count': ''}
#     #     ]
#     # }
#     # documents = mongo_instance.get_all_data('OBC_cumulative_reset', cumlulative_query)
#
#     # lt = list(documents)
#     # concatenated_df = pd.DataFrame(lt)
#     # print(lt)
#     # print(concatenated_df.to_string())
#
#     # # Iterate over each document
#     # for doc in documents:
#     #     # Fetch the nearest document with a non-empty 'cumulative_count'
#     #     nearest_doc = get_nearest_document(mongo_instance, satelliteCode, doc['time_found'])
#     #
#     #     # Keep fetching nearest documents until a non-empty 'cumulative_count' is found
#     #     while nearest_doc and nearest_doc['cumulative_count'] == '':
#     #         nearest_doc = get_nearest_document(mongo_instance, satelliteCode, nearest_doc['time_found'])
#     #
#     #     # If a nearest document with a non-empty 'cumulative_count' is found, update the current document
#     #     if nearest_doc:
#     #         doc['cumulative_count'] = str(int(nearest_doc['cumulative_count']) + doc['reset_count'])
#     #         mongo_instance.update_flight_operation_satellite_data(doc, 'OBC_cumulative_reset', doc['_id'])
#     #     else:
#     #         # If there is no nearest document with a non-empty 'cumulative_count', the 'cumulative_count' remains empty
#     #         pass
#
#     print("OBC reset update complete")

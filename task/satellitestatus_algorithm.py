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
        else:
            # Insert a new document
            mongo_instance.write_flight_operation_data(doc, 'OBC_reset_records')

    return print("executing OBC reset algorithm")


def write_switch_count(metedataservice_url, influxdb, client, tf1, tf2, satID):
    resettime_data = OBCswitch_influx(metedataservice_url, influxdb, client, tf1, tf2, satID)

    # Check if 'obc_switch' column exists
    if 'obc_switch' not in resettime_data.columns:
        print("No 'obc_switch' detected")
        return

    # Add new columns 'switch_detect'
    resettime_data['switch_detect'] = (resettime_data['obc_switch'] != resettime_data['obc_switch'].shift()).astype(int)
    resettime_data.loc[0, ['switch_detect']] = 0

    # obc switch

    # Get rows where 'obc_switch' is not equal to 0
    non_zero_switch = resettime_data.dropna(subset=['obc_switch']).loc[resettime_data['switch_detect'] != 0]

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


# def update_cumulative_reset(metedataservice_url, tf1, tf2, satID):
#     tm = tm_table(metedataservice_url, satID)
#     satelliteCode = tm[satID]['code']
#
#     if not tf1 or not tf2:
#         now = datetime.now()
#         ten_minutes_ago = now - timedelta(minutes=2880)
#         tf2 = int(now.timestamp())
#         tf1 = int(ten_minutes_ago.timestamp())
#     else:
#         tf2 = datetime.strptime(tf2, "%Y-%m-%dT%H:%M:%S.%fZ")
#         tf1 = datetime.strptime(tf1, "%Y-%m-%dT%H:%M:%S.%fZ")
#
#         tf2 = int(datetime.timestamp(tf2))
#         tf1 = int(datetime.timestamp(tf1))
#
#     # Initialize Mongo class and get MongoDBconnection
#     mongo_instance = get_mongo()
#
#     check_query = {
#         '$and': [
#             {'_satelliteCode': str(satelliteCode)},
#             {'time_found': {'$gte': tf1,
#                             '$lte': tf2}},
#             {'cumulative_count': {'$eq': 0}}
#         ]
#     }
#     documents = mongo_instance.get_all_data('OBC_reset_records', check_query)
#
#     to_be_updated = list(documents)
#
#     # to_be_updated = pd.DataFrame(to_be_updated)
#
#     # print(to_be_updated)
#     # print(to_be_updated.dtypes)
#
#     for doc in to_be_updated:
#         # Find the nearest switch record
#         switch_query = {
#             '_satelliteCode': str(satelliteCode),
#             'time_found': {'$lt': doc['time_found']}
#         }
#         nearest_switch_cursor = mongo_instance.get_nearest_data('OBC_switch_records', switch_query)
#
#         # Extract the nearest switch document from the cursor
#         nearest_switch = list(nearest_switch_cursor)
#         nearest_switch_doc = nearest_switch[0]  # Assuming there's only one nearest switch
#         # print(nearest_switch_doc)
#
#         # Find reset records between nearest switch and current document's time_found
#         reset_query = {
#             '_satelliteCode': str(satelliteCode),
#             'time_found': {'$gte': nearest_switch_doc['time_found'], '$lt': doc['time_found']}
#         }
#         reset_records = mongo_instance.get_all_data('OBC_reset_records', reset_query)
#
#         # print(list(reset_records))
#         if len(list(reset_records)) == 0:
#             # If no reset records found, update the to_be_updated document with its reset_count
#             filter_query = {'eventid': doc['eventid']}
#             update_query = {'cumulative_count': doc['reset_count']}
#             # print(doc['reset_count'])
#             # print(update_query)
#             mongo_instance.update_cumulative_data('OBC_reset_records', filter_query, update_query)
#             print('restarting from switch')
#         else:
#             non_zero_reset_records = [reset_record for reset_record in reset_records if
#                                       reset_record['cumulative_count'] != 0]
#
#             print(non_zero_reset_records)
#             print('adding')
#
#             # Initialize cumulative count sum
#             cumulative_count_sum = doc['reset_count']
#
#             # Find all previous cumulative counts
#             previous_cumulative_counts = [reset_record['cumulative_count'] for reset_record in non_zero_reset_records]
#
#             # Add all previous cumulative counts to cumulative_count_sum
#             cumulative_count_sum += sum(previous_cumulative_counts)
#             print(cumulative_count_sum)
#
#             # Update cumulative 0 document with the sum of cumulative counts and its reset_count
#             filter_query = {'eventid': doc['eventid']}
#             update_query = {'cumulative_count': cumulative_count_sum}
#             mongo_instance.update_cumulative_data('OBC_reset_records', filter_query, update_query)
#             print('Cumulative count updated based on non-zero reset records')


# def calculate_cumulative_reset(metedataservice_url, tf1, tf2, satID):
#     tm = tm_table(metedataservice_url, satID)
#     satelliteCode = tm[satID]['code']
#
#     if not tf1 or not tf2:
#         now = datetime.now()
#         ten_minutes_ago = now - timedelta(minutes=2880)
#         tf2 = int(now.timestamp())
#         tf1 = int(ten_minutes_ago.timestamp())
#     else:
#         tf2 = datetime.strptime(tf2, "%Y-%m-%dT%H:%M:%S.%fZ")
#         tf1 = datetime.strptime(tf1, "%Y-%m-%dT%H:%M:%S.%fZ")
#
#         tf2 = int(datetime.timestamp(tf2))
#         tf1 = int(datetime.timestamp(tf1))
#
#     # Initialize Mongo class and get MongoDBconnection
#     mongo_instance = get_mongo()
#
#     check_query = {
#         '$and': [
#             {'_satelliteCode': str(satelliteCode)},
#             {'time_found': {'$gte': tf1,
#                             '$lte': tf2}}
#         ]
#     }
#     documents = mongo_instance.get_all_data('OBC_reset_records', check_query)
#
#     to_be_updated = list(documents)
#
#     # to_be_updated = pd.DataFrame(to_be_updated)
#
#     # print(to_be_updated)
#     # print(to_be_updated.dtypes)
#
#     for doc in to_be_updated:
#         # Find the nearest switch record
#         switch_query = {
#             '_satelliteCode': str(satelliteCode),
#             'time_found': {'$lt': doc['time_found']}
#         }
#         nearest_switch_cursor = mongo_instance.get_nearest_data('OBC_switch_records', switch_query)
#
#         # Extract the nearest switch document from the cursor
#         nearest_switch = list(nearest_switch_cursor)
#         nearest_switch_doc = nearest_switch[0]  # Assuming there's only one nearest switch
#         # print(nearest_switch_doc)
#
#         # Find reset records between nearest switch and current document's time_found
#         reset_query = {
#             '_satelliteCode': str(satelliteCode),
#             'time_found': {'$gte': nearest_switch_doc['time_found'], '$lt': doc['time_found']}
#         }
#         reset_records = mongo_instance.get_all_data('OBC_reset_records', reset_query)
#
#         # print(list(reset_records))
#         if len(list(reset_records)) == 0:
#             # If no reset records found, update the to_be_updated document with its reset_count
#             filter_query = {'eventid': doc['eventid']}
#             update_query = {'cumulative_count': doc['reset_count']}
#             # print(doc['reset_count'])
#             # print(update_query)
#             mongo_instance.update_cumulative_data('OBC_reset_records', filter_query, update_query)
#             print('restarting from switch')
#         else:
#             non_zero_reset_records = [reset_record for reset_record in reset_records if
#                                       reset_record['cumulative_count'] != 0]
#
#             print(non_zero_reset_records)
#             print('adding')
#
#             # Initialize cumulative count sum
#             cumulative_count_sum = doc['reset_count']
#
#             # Find all previous cumulative counts
#             previous_cumulative_counts = [reset_record['cumulative_count'] for reset_record in non_zero_reset_records]
#
#             # Add all previous cumulative counts to cumulative_count_sum
#             cumulative_count_sum += sum(previous_cumulative_counts)
#             print(cumulative_count_sum)
#
#             # Update cumulative 0 document with the sum of cumulative counts and its reset_count
#             filter_query = {'eventid': doc['eventid']}
#             update_query = {'cumulative_count': cumulative_count_sum}
#             mongo_instance.update_cumulative_data('OBC_reset_records', filter_query, update_query)
#             print('Cumulative count updated based on non-zero reset records')


def calculate_cumulative_reset(metedataservice_url, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']

    # Convert time strings to timestamps
    if not tf1 or not tf2:
        now = datetime.now()
        ten_minutes_ago = now - timedelta(minutes=2880)
        tf2 = int(now.timestamp())
        tf1 = int(ten_minutes_ago.timestamp())
    else:
        tf2 = int(datetime.strptime(tf2, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
        tf1 = int(datetime.strptime(tf1, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())

    # Initialize Mongo class and get MongoDB connection
    mongo_instance = get_mongo()

    # Retrieve reset records within the specified time interval and for the given satelliteCode
    check_query = {
        '$and': [
            {'_satelliteCode': str(satelliteCode)},
            {'time_found': {'$gte': tf1, '$lte': tf2}}
        ]
    }
    reset_records = mongo_instance.get_all_data('OBC_reset_records', check_query)
    # print(list(reset_records))

    if reset_records is not None:

        # Iterate over reset records
        for reset_record in reset_records:
            # Check if the eventid already exists in cumulative_reset_count
            # Check if the eventid already exists in cumulative_reset_count
            existing_doc = mongo_instance.read_OBCrecord_data(reset_record['eventid'], 'cumulative_reset_count')
            print(list(existing_doc))

            if not existing_doc:
                # Find the nearest switch record
                switch_query = {
                    '_satelliteCode': str(satelliteCode),
                    'time_found': {'$lt': reset_record['time_found']}
                }
                nearest_switch_cursor = mongo_instance.get_nearest_data('OBC_switch_records', switch_query)
                nearest_switch = list(nearest_switch_cursor)[0]  # Assuming there's only one nearest switch

                # Find reset records between nearest switch and current reset record
                reset_query = {
                    '_satelliteCode': str(satelliteCode),
                    'time_found': {'$gte': nearest_switch['time_found'], '$lt': reset_record['time_found']}
                }
                reset_records_between = mongo_instance.get_all_data('OBC_reset_records', reset_query)

                # Calculate cumulative reset count
                cumulative_count = sum(reset['reset_count'] for reset in reset_records_between) + reset_record[
                    'reset_count']

                # Store eventid, cumulative_count, and all other fields in the new collection
                cumulative_reset_doc = {
                    'eventid': reset_record['eventid'],
                    'cumulative_count': cumulative_count,
                    **reset_record  # Include all fields from reset_record
                }
                mongo_instance.write_flight_operation_data(cumulative_reset_doc, 'cumulative_reset_count')

    else:
        print('No document found')

# def write_cumulative_data(metedataservice_url, tf1, tf2, satID):
#     # # TODO: now calculate cumulative reset after each switch found, group by _satelliteCode
# concatenated_df = OBCreset_mongo_records(metedataservice_url, tf1, tf2, satID)
#
# if concatenated_df is None:
#     print("No new OBC anomal written")
#     return
#
# concatenated_df = concatenated_df.sort_values(by='time_found', ascending=True)
# mongo_instance = get_mongo()
# # Iterate over the rows of the concatenated DataFrame
# for index, row in concatenated_df.iterrows():
#     # Check if the eventid already exists in the MongoDB collection
#     existing_doc = mongo_instance.read_OBCrecord_data(row['eventid'], 'OBC_cumulative_reset')
#
#     # Construct the document to be inserted or updated
#     doc = {
#         '_satelliteCode': row['_satelliteCode'],
#         'eventid': row['eventid'],
#         'time_found': row['time_found'],
#         'reset_count': row['reset_count'],
#         'switch_count': row['switch_count'],
#         'reset': row['reset'],
#         'switch': row['switch'],
#         'cumulative_count': row['cumulative_reset']
#     }
#
#     # If there is an existing document, update it
#     if existing_doc:
#         mongo_instance.update_flight_operation_satellite_data(doc, 'OBC_cumulative_reset', row['eventid'])
#     else:
#         # If there isn't an existing document, insert a new one
#         mongo_instance.write_flight_operation_data(doc, 'OBC_cumulative_reset')
#
#     return print("new OBC anomal written")

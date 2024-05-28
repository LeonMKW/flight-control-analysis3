import logging
import pprint
import json
import pandas as pd
import pytz
from datetime import datetime, timedelta
from utils.flightcontrol_utils import get_task_list
from task.flightcontrol_algorithms import downlink_statics, general_anomal, satcom, uplink_statics_new, \
    spiderling_file_inspection, \
    orbit_control, orbit_statistics
from utils.db import get_mongo
from dateutil import parser
from utils.od_utils import get_altitude
import time


def sat_alert(satellitecode, mongo_instance, ts1, ts2):
    alertdf = mongo_instance.read_alert_data(ts1, ts2, satellitecode)

    alert_list = list(alertdf)

    # Check if alert_list is empty
    if len(alert_list) == 0:
        # Return empty DataFrames with the required structure
        subsystem_df = pd.DataFrame(columns=['subsystem', 'count'])
        event_level_df = pd.DataFrame(columns=['subsystem', 'FATAL', 'CRITICAL', 'WARNING', 'INFO'])
        return subsystem_df, event_level_df

    # alerts = pd.DataFrame(alert_list)
    params_data = [item['params'] for item in alert_list]
    df = pd.json_normalize(params_data)

    # Drop unnecessary columns
    df = df.drop(
        columns=['eventDesc', 'eventCode', 'eventLogId', 'eventTirrgerType', 'eventObjectType', 'eventObjectId',
                 'eventTime', 'eventRemark', 'eventTimeStr', 'param.ext'])

    # Flatten param.itemDatas and create a new DataFrame
    flattened_data = []
    for index, row in df.iterrows():
        for item in row['param.itemDatas']:
            item['eventName'] = row['eventName']
            item['eventLevel'] = row['eventLevel']
            flattened_data.append(item)

    new_df = pd.DataFrame(flattened_data)

    # Frequency count of 'subsystem' column
    subsystem_df = new_df['subsystem'].value_counts().reset_index()
    subsystem_df.columns = ['subsystem', 'count']

    # Group by 'subsystem' and 'eventLevel' and count occurrences
    event_level_grouped = new_df.groupby(['subsystem', 'eventLevel']).size().reset_index(name='count')

    # Pivot the DataFrame to have subsystems as rows and event levels as columns
    event_level_df = event_level_grouped.pivot(index='subsystem', columns='eventLevel', values='count').fillna(
        0).reset_index()

    # Ensure all event levels are present
    for level in ['FATAL', 'CRITICAL', 'WARNING', 'INFO']:
        if level not in event_level_df.columns:
            event_level_df[level] = 0

    # Ensure count columns are integers
    event_level_df = event_level_df.astype({level: 'int' for level in ['FATAL', 'CRITICAL', 'WARNING', 'INFO']})
    # print(event_level_df)
    return subsystem_df, event_level_df


def obp(cur, satellitecode):
    # orbit status
    query_orbit_precision = f"""
    SELECT *
    FROM orbit_precision_summary
    WHERE spacecraft = '{satellitecode}'
    ORDER BY timestamp DESC
    LIMIT 1;
    """

    cur.execute(query_orbit_precision)
    op = cur.fetchone()
    obp_df = pd.DataFrame([op])
    # Drop unnecessary columns
    obp_df = obp_df[['mse']]
    return obp_df


def obh(mete_data_service, influxdb_orbdata, client_orbdata, satID):
    altitude = get_altitude(mete_data_service, influxdb_orbdata, client_orbdata, satID)
    altitude['alt'] = round(altitude['alt'] / 1000, 3)
    altitude = altitude[['alt']]

    return altitude


def get_tracking_quality(mongo_instance, collection, mission_ids):
    tracking_list = mongo_instance.read_tracking_quality_data(collection, mission_ids=mission_ids)
    return tracking_list


def get_all_quality_data(uplock_quality_list, telemetry_quality_list):
    merged_data = []
    for uplock in uplock_quality_list:
        for telemetry in telemetry_quality_list:
            if (uplock['mission_id'] == telemetry['mission_id'] and
                    uplock['starting'] == telemetry['starting'] and
                    uplock['ending'] == telemetry['ending']):
                merged_data.append({
                    'mission_id': uplock['mission_id'],
                    'starting': uplock['starting'],
                    'ending': uplock['ending'],
                    'telemetry': telemetry['group_info'],
                    'uplink': uplock['group_info']
                })
    print(merged_data)
    return merged_data

    # # Check if alert_list is empty
    # if len(tracking_list) == 0:
    #     # Return empty DataFrames with the required structure
    #     tracking_list = pd.DataFrame(columns=['subsystem', 'FATAL', 'CRITICAL', 'WARNING', 'INFO'])
    #     return subsystem_df, event_level_df
    #
    # # alerts = pd.DataFrame(alert_list)
    # params_data = [item['params'] for item in alert_list]
    # df = pd.json_normalize(params_data)
    #
    # # Drop unnecessary columns
    # df = df.drop(
    #     columns=['eventDesc', 'eventCode', 'eventLogId', 'eventTirrgerType', 'eventObjectType', 'eventObjectId',
    #              'eventTime', 'eventRemark', 'eventTimeStr', 'param.ext'])
    #
    # # Flatten param.itemDatas and create a new DataFrame
    # flattened_data = []
    # for index, row in df.iterrows():
    #     for item in row['param.itemDatas']:
    #         item['eventName'] = row['eventName']
    #         item['eventLevel'] = row['eventLevel']
    #         flattened_data.append(item)
    #
    # new_df = pd.DataFrame(flattened_data)
    #
    # # Frequency count of 'subsystem' column
    # subsystem_df = new_df['subsystem'].value_counts().reset_index()
    # subsystem_df.columns = ['subsystem', 'count']
    #
    # # Group by 'subsystem' and 'eventLevel' and count occurrences
    # event_level_grouped = new_df.groupby(['subsystem', 'eventLevel']).size().reset_index(name='count')
    #
    # # Pivot the DataFrame to have subsystems as rows and event levels as columns
    # event_level_df = event_level_grouped.pivot(index='subsystem', columns='eventLevel', values='count').fillna(
    #     0).reset_index()
    #
    # # Ensure all event levels are present
    # for level in ['FATAL', 'CRITICAL', 'WARNING', 'INFO']:
    #     if level not in event_level_df.columns:
    #         event_level_df[level] = 0
    #
    # # Ensure count columns are integers
    # event_level_df = event_level_df.astype({level: 'int' for level in ['FATAL', 'CRITICAL', 'WARNING', 'INFO']})
    # # print(event_level_df)
    # return subsystem_df, event_level_df

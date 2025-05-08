import logging
import pprint
import json
import pandas as pd
from requests import post
import pytz
from datetime import datetime, timedelta
from utils.flightcontrol_utils import get_task_list
from task.flightcontrol_algorithms import downlink_statics, general_anomal, satcom, uplink_statics_new, \
    spiderling_file_inspection, \
    orbit_control, orbit_statistics
from utils.db import get_mongo
from dateutil import parser
from utils.od_utils import get_altitude, get_phase, get_phase_new, get_all_altitude
import requests
import arrow
from utils.authentication import get_header_token


def sat_alert(satellitecode, mongo_instance, ts1, ts2):
    alertdf = mongo_instance.read_alert_data(ts1, ts2, satellitecode)
    alert_list = list(alertdf)

    # Check if alert_list is empty
    if len(alert_list) == 0:
        # Return empty DataFrames with the required structure
        subsystem_df = pd.DataFrame(columns=['subsystem', 'count'])
        event_level_df = pd.DataFrame(columns=['subsystem', 'FATAL', 'CRITICAL', 'WARNING', 'INFO'])
        return subsystem_df, event_level_df

    params_data = [item['params'] for item in alert_list]
    df = pd.json_normalize(params_data)

    # Drop unnecessary columns if they exist (use errors='ignore')
    df = df.drop(
        columns=['eventDesc', 'eventCode', 'eventLogId', 'eventTirrgerType', 'eventObjectType', 'eventObjectId',
                 'eventTime', 'eventRemark', 'eventTimeStr', 'param.ext'],
        errors='ignore'
    )

    # Flatten param.itemDatas and create a new DataFrame
    flattened_data = []
    for index, row in df.iterrows():
        itemDatas = row.get('param.itemDatas', [])
        if itemDatas:
            item = itemDatas[0]  # Only take the first itemData
            # Extract subsystem directly from item, default to "unknown"
            subsystem = item.get('subsystem', 'unknown')
            if subsystem is None:
                subsystem = 'unknown'
            item['subsystem'] = subsystem

            # Extract event-related fields from row
            item['eventName'] = row.get('eventName', 'unknown')
            item['eventLevel'] = row.get('eventLevel', 'unknown')

            flattened_data.append(item)

    new_df = pd.DataFrame(flattened_data)

    # Handle missing isEnd by setting to "unknown"
    if 'isEnd' not in new_df.columns:
        new_df['isEnd'] = "unknown"
    else:
        new_df['isEnd'] = new_df['isEnd'].fillna("unknown")

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

    return subsystem_df, event_level_df


# def obp(cur, satellitecode):
#     # orbit status
#     query_orbit_precision = f"""
#     SELECT *
#     FROM orbit_precision_summary
#     WHERE spacecraft = '{satellitecode}'
#     ORDER BY timestamp DESC
#     LIMIT 1;
#     """
#
#     cur.execute(query_orbit_precision)
#     op = cur.fetchone()
#     obp_df = pd.DataFrame([op])
#     # Drop unnecessary columns
#     obp_df = obp_df[['mse']]
#     return obp_df

def get_obh(post_token_url,
            post_token_user_name,
            post_token_password, mete_data_service, influxdb_orbdata, client_orbdata, satID, start, end):
    satI = satID.split(",")  # Split the comma-separated satellite IDs into a list
    all_altitudes = []

    for sat in satI:
        altitude_df = get_all_altitude(post_token_url,
                                       post_token_user_name,
                                       post_token_password, mete_data_service, influxdb_orbdata, client_orbdata, sat,
                                       start, end)
        altitude_df['alt'] = round(altitude_df['alt'] / 1000, 3)
        altitude_df['_satelliteCode'] = altitude_df['_satelliteCode']
        all_altitudes.append(altitude_df[['alt', '_satelliteCode']])

    # Combine all altitude dataframes into one
    combined_df = pd.concat(all_altitudes, ignore_index=True)
    result = combined_df.to_dict(orient='records')  # Convert DataFrame to a list of dictionaries

    return json.dumps(result)


def obh(post_token_url,
        post_token_user_name,
        post_token_password, mete_data_service, influxdb_orbdata, client_orbdata, satID, start, end):
    # Assumes start and end are defined here or passed to this function
    altitude = get_altitude(post_token_url,
                            post_token_user_name,
                            post_token_password, mete_data_service, influxdb_orbdata, client_orbdata, satID, start, end)
    # print(altitude)
    altitude['alt'] = round(altitude['alt'] / 1000, 3)
    altitude = altitude[['alt']]

    return altitude


def o2pphase(post_token_url,
             post_token_user_name,
             post_token_password, mete_data_service, influxdb_orbdata, client_orbdata, satID):
    phase = get_phase(post_token_url,
                      post_token_user_name,
                      post_token_password, mete_data_service, influxdb_orbdata, client_orbdata, satID)
    phase['phase'] = round(phase['phase'], 3)
    phase = phase[['phase']]
    return phase


def o2pphase_new(influxdb_orbdata, client_orbdata):
    phase = get_phase_new(influxdb_orbdata, client_orbdata)
    phase['phase_diff'] = round(phase['phase_diff'], 3)
    return phase


def get_tracking_quality(mongo_instance, collection, mission_ids):
    tracking_list = mongo_instance.read_tracking_quality_data(collection, mission_ids=mission_ids)
    return tracking_list


def process_quality_lists(uplock_quality_list, telemetry_quality_list):
    for uplock in uplock_quality_list:
        if uplock['total_group_number'] == 0:
            uplock['group_info'] = {
                '1': {
                    'duration': 0,
                    'lock_status': 0,
                    'start': uplock['starting'],
                    'end': uplock['ending']
                }
            }

    for telemetry in telemetry_quality_list:
        if telemetry['total_group_number'] == 0:
            telemetry['group_info'] = {
                '0': {
                    'start': 0,
                    'end': 0
                }
            }


def get_all_quality_data(uplock_quality_list, telemetry_quality_list):
    process_quality_lists(uplock_quality_list, telemetry_quality_list)

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
    return merged_data


def get_daily_reset_stats(mongo_instance, collection, satcode, tf1, tf2):
    daily_reset_stats = mongo_instance.get_doc_by_satid_tf(collection, satcode, tf1, tf2)
    return daily_reset_stats


def get_fire_records(post_token_url,
                     post_token_user_name,
                     post_token_password, orbit_maneuver_url, start, end, date, satID):
    satIDs = satID.split(",")

    token = get_header_token(post_token_url,
                             post_token_user_name,
                             post_token_password)

    headers = {
        'x-web-token': token
    }

    if not start or not end:
        date = datetime.strptime(date, "%Y-%m-%d")
        cst = pytz.timezone("Asia/Shanghai")
        startDate_cst = cst.localize(date)
        utc = pytz.timezone("UTC")
        startDate = startDate_cst.astimezone(utc)
        endDate = startDate + timedelta(days=1)
    else:
        startDate = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S.%fZ")
        startDate = startDate.replace(tzinfo=pytz.UTC)
        endDate = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S.%fZ")
        endDate = endDate.replace(tzinfo=pytz.UTC)
        # endDate += timedelta(days=+2)  # Add 2 days to the end date
        date = f"{start} to {end}"

    # Format the dates as ISO 8601 strings
    timefilter1 = startDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
    timefilter2 = endDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
    ts1 = parser.isoparse(timefilter1)
    ts1 = int(ts1.timestamp() * 1000)

    ts2 = parser.isoparse(timefilter2)
    ts2 = int(ts2.timestamp() * 1000)

    # Define the payload with dynamic values
    orbit_maneuver_body = {
        "spacecraftId": satIDs,
        "state": [1, 2, 3, 4, 5, 6],
        "startMs": ts1,
        "endMs": ts2,
        "pageSize": 1000,
        "page": 1,
        "order": 4
    }

    # Send the POST request
    orbitcal_response = post(url=orbit_maneuver_url, json=orbit_maneuver_body, headers=headers, timeout=300)

    # Return the response from the request
    return orbitcal_response


def get_gateway_task(post_token_url,
                     post_token_user_name,
                     post_token_password, app_url, start, end, date, satID):
    satIDs = satID.split(",")

    if not start or not end:
        date = datetime.strptime(date, "%Y-%m-%d")
        cst = pytz.timezone("Asia/Shanghai")
        startDate_cst = cst.localize(date)
        utc = pytz.timezone("UTC")
        startDate = startDate_cst.astimezone(utc)
        endDate = startDate + timedelta(days=1)
    else:
        startDate = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S.%fZ")
        startDate = startDate.replace(tzinfo=pytz.UTC)
        endDate = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S.%fZ")
        endDate = endDate.replace(tzinfo=pytz.UTC)
        date = f"{start} to {end}"

        # Make datetime.utcnow() offset-aware by adding timezone information
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)

        # Check if endDate is greater than current time
        if endDate > now_utc:
            endDate = now_utc

    # Format the dates as ISO 8601 strings
    timefilter1 = startDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
    timefilter2 = endDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
    ts1 = parser.isoparse(timefilter1)
    ts1 = int(ts1.timestamp() * 1000)

    ts2 = parser.isoparse(timefilter2)
    ts2 = int(ts2.timestamp() * 1000)

    token = get_header_token(post_token_url,
                             post_token_user_name,
                             post_token_password)

    headers = {
        'x-web-token': token
    }

    payload = {
        "startAt": ts1,
        "endAt": ts2,
        "spacecraftIds": satIDs,
        "antennaIDs": [],
        "taskType": ["COMMUNICATION"]
    }

    response = post(app_url, headers=headers, json=payload)

    return response


def get_flight_controller(post_token_url,
                          post_token_user_name,
                          post_token_password, orbit_service, satelliteIDs, startAt, endAt):
    url = orbit_service + '/v2/api/openapi-transform/get-task-on-duty-list'

    token = get_header_token(post_token_url,
                             post_token_user_name,
                             post_token_password)

    # Define the headers with the required token
    headers = {
        'x-web-token': token
    }

    query = """
    query($satelliteIDs:[String!],$startAt:Date!,$endAt:Date!){
        getTaskOnDutyList(satelliteIDs:$satelliteIDs,startAt:$startAt,endAt:$endAt,
            groupIDs:[],caretakerIDs:[]){
            records{
              caretaker{
                name
              }
              startAt
              endAt
              satellite{
                code
              }
            }
          }
        }
    """
    variables = {"startAt": startAt, "endAt": endAt, "satelliteIDs": satelliteIDs}
    res = requests.post(url=url, json={"query": query, "variables": variables}, headers=headers)
    # print(variables)
    result = res.json()["data"]["getTaskOnDutyList"]["records"]

    caretakers = []
    for record in result:
        # Optionally, you can check if the record's start and end times overlap with your input times
        record_start = arrow.get(record["startAt"])
        record_end = arrow.get(record["endAt"])
        input_start = arrow.get(startAt)
        input_end = arrow.get(endAt)

        # Check if the record overlaps with the input time range
        if record_end > input_start and record_start < input_end:
            caretakers.append(record["caretaker"]["name"])

    # Remove duplicates if needed
    caretakers = list(set(caretakers))
    return caretakers

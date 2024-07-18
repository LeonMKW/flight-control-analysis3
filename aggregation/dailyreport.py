import logging
import pprint
import json
import pandas as pd
import pytz
from datetime import datetime, timedelta
from task.flightcontrol_algorithms import downlink_statics, general_anomal, satcom, uplink_statics_new, \
    spiderling_file_inspection, orbit_control, orbit_statistics, comtask_up
from utils.db import get_mongo
from dateutil import parser
from utils.dailyreport_utils import o2pphase, sat_alert, obh, get_tracking_quality, get_all_quality_data, \
    o2pphase_new
from utils.flightcontrol_utils import tm_table
from utils.db import OSS2
import os
import base64
from utils.notification_content import spiderling_daily_report_content
import requests

def daily_report_spiderling(orbitservice_url,
                            mete_data_service,
                            influxdb_input,
                            client_input,
                            influxdb_action,
                            client_action,
                            influxdb_chronograf,
                            client_chronograf,
                            satID,
                            date,
                            start,
                            end,
                            mariadb,
                            influxdb_orbdata,
                            client_orbdata
                            ):
    satIDs = satID.split(",")  # Convert comma-separated string to a list of satellite IDs

    all_tt_dfs = []
    all_stcodes = []  # List to store stcode for each satellite
    total_comtask_sent = 0  # Variable to sum up total commands sent

    # Initialize Mongo class and get MongoDBconnection
    mongo_instance = get_mongo()

    db = mariadb
    conn = db.get_connection()
    cur = conn.cursor(dictionary=True)

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
    ts1 = ts1.timestamp() * 1000

    ts2 = parser.isoparse(timefilter2)
    ts2 = ts2.timestamp() * 1000

    phasediff = o2pphase_new(influxdb_orbdata, client_orbdata)
    phasediff_json = phasediff.to_json(orient='records')  # Convert DataFrame to JSON

    for satID in satIDs:

        # mission details and flight control section

        down = downlink_statics(orbitservice_url, mete_data_service, influxdb_input, client_input, timefilter1,
                                timefilter2,
                                satID)

        up = uplink_statics_new(orbitservice_url, mete_data_service, influxdb_input, client_input, influxdb_action,
                                client_action,
                                timefilter1, timefilter2, satID)

        payload = satcom(orbitservice_url, mete_data_service, influxdb_input, client_input, influxdb_action,
                         client_action,
                         timefilter1, timefilter2, satID)

        file_inspect_result = spiderling_file_inspection(orbitservice_url, mete_data_service, influxdb_input,
                                                         client_input,
                                                         influxdb_action,
                                                         client_action,
                                                         timefilter1, timefilter2, satID)

        anomal = general_anomal(orbitservice_url, mete_data_service, influxdb_input, client_input,
                                timefilter1,
                                timefilter2, satID)

        com_command = comtask_up(mete_data_service=mete_data_service,
                                 _influxdb_input=influxdb_input,
                                 _influxdb_action=influxdb_action,
                                 client_action=client_action,
                                 tf1=timefilter1,
                                 tf2=timefilter2,
                                 satID=satID)

        # Assuming `com_command` returns a list of commands
        total_comtask_sent += len(com_command)

        orbit_control_result = orbit_control(orbit_service=orbitservice_url,
                                             mete_data_service=mete_data_service,
                                             _influxdb_chonograf=influxdb_chronograf,
                                             client_chronograf=client_chronograf,
                                             _influxdb=influxdb_input,
                                             client=client_input,
                                             tf1=timefilter1,
                                             tf2=timefilter2,
                                             satID=satID)

        orbit_status_result = orbit_statistics(orbitservice_url, mete_data_service, influxdb_input, client_input,
                                               timefilter1,
                                               timefilter2, satID)

        downjson = json.loads(down)
        downjsontt = downjson['task_list']
        downdf = pd.DataFrame(downjsontt)

        upjson = json.loads(up)
        upjsontt = upjson['task_list']
        updf = pd.DataFrame(upjsontt)

        payloadjson = json.loads(payload)
        payloadjsontt = payloadjson['task_list_all']
        payloaddf = pd.DataFrame(payloadjsontt)

        file_inspect_resultjson = json.loads(file_inspect_result)
        file_inspect_resultjsontt = file_inspect_resultjson['task_list_all']
        file_inspect_resultdf = pd.DataFrame(file_inspect_resultjsontt)

        anomal_resultjson = json.loads(anomal)
        anomal_resultjsontt = anomal_resultjson['task_list_all']
        anomal_resultdf = pd.DataFrame(anomal_resultjsontt)

        common_columns = ['remark', 'starting', 'ending',
                          'satellite_code', 'satellite_id',
                          'station_name', 'device', 'antID',
                          'approach_angle', 'max_elvation', 'departure_angle',
                          'company_name', 'rally', 'mission_id']

        # Merge dataframes and keep only one copy of common rows
        merged_df1 = pd.merge(downdf, updf, on=common_columns, how='outer')
        merged_df2 = pd.merge(merged_df1, payloaddf, on=common_columns, how='outer')
        merged_df3 = pd.merge(merged_df2, file_inspect_resultdf, on=common_columns, how='outer')
        merged_df4 = pd.merge(merged_df3, anomal_resultdf, on=common_columns, how='outer')

        orbit_control_result['starting'] = orbit_control_result['starting'].apply(lambda x: x.timestamp()) * 1000
        pd.set_option('display.float_format', lambda x: '%.6f' % x)
        orbit_control_result['ending'] = orbit_control_result['ending'].apply(lambda x: x.timestamp()) * 1000
        pd.set_option('display.float_format', lambda x: '%.6f' % x)

        # 其中datetime_df_utc是datetime64[ns, UTC]

        merged_df5 = pd.merge(merged_df4, orbit_control_result, on=common_columns, how='outer')

        orbit_status_result['starting'] = orbit_status_result['starting'].apply(lambda x: x.timestamp()) * 1000
        pd.set_option('display.float_format', lambda x: '%.6f' % x)
        orbit_status_result['ending'] = orbit_status_result['ending'].apply(lambda x: x.timestamp()) * 1000
        pd.set_option('display.float_format', lambda x: '%.6f' % x)

        merged_df6 = pd.merge(merged_df5, orbit_status_result, on=common_columns, how='outer')
        merged_df6['tdownlink'] = pd.to_numeric(merged_df6['tdownlink'], errors='coerce').round().astype(
            pd.Int64Dtype())
        merged_df6['duration'] = pd.to_numeric(merged_df6['duration'], errors='coerce').round().astype(pd.Int64Dtype())

        columns_to_drop = ['device', 'fileinspectsum', 'satellite_id', 'antID', 'approach_angle',
                           'max_elvation',
                           'departure_angle', 'rally', 'tdownlink', 'rdownlink', 'ratio', 'auto_lock', 'lock_interval',
                           'diff', 'orbit_status', 'missing', 'duration', 'timegap', 'ending', ]
        for col in columns_to_drop:
            del merged_df6[col]

        column_order = ['remark',
                        'mission_id',
                        'starting',
                        'satellite_code',
                        'station_name',
                        'up',
                        'increase',
                        'com_status',
                        'fileinspect',
                        'anomal',
                        'fire_status',
                        'company_name']

        tt = merged_df6[column_order]

        tt['starting'] = pd.to_datetime(tt['starting'], unit='ms')
        # Localize the datetime column to Asia/Shanghai timezone
        tt['starting'] = tt['starting'].dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai')
        tt['starting'] = tt['starting'].dt.strftime('%Y-%m-%d %H:%M:%S %Z%z')

        all_tt_dfs.append(tt)

        # print(tt.to_string())

        satellitecode = tt['satellite_code'][0]

        # satellite alert status
        subsystemdf, leveldf = sat_alert(satellitecode, mongo_instance, ts1, ts2)

        # orbit height
        obh_df = obh(mete_data_service, influxdb_orbdata, client_orbdata, satID)
        # print(obh_df)
        phase_df = o2pphase(mete_data_service, influxdb_orbdata, client_orbdata, satID)

        ttjson = tt.to_json(orient='records')
        subsystemjson = subsystemdf.to_json(orient='records')
        leveljson = leveldf.to_json(orient='records')
        phasejson = phase_df.to_json(orient='records')
        obhjson = obh_df.to_json(orient='records')

        # Convert JSON strings to dictionaries
        flightcontrol_data = json.loads(ttjson)
        # print(flightcontrol_data)
        subsystem_data = json.loads(subsystemjson)
        level_data = json.loads(leveljson)
        phasedata = json.loads(phasejson)[0] if phasejson else {}
        orbit_h_data = json.loads(obhjson)[0] if obhjson else {}

        # Create nested structure for subsystems and levels
        subsystem_dict = {item['subsystem']: {'count': item['count']} for item in subsystem_data}
        level_dict = {item['subsystem']: {key: item.get(key, 0) for key in ['FATAL', 'CRITICAL', 'WARNING', 'INFO']} for
                      item in level_data}

        # Calculate total_anomal_sum and updiff
        total_anomal_sum = sum(1 for item in flightcontrol_data if item['anomal'])
        updiff = sum(1 for item in flightcontrol_data if abs(item['up'] - item['increase']) >= 1)

        # Combine the JSON objects into the desired structure
        stcode = {
            "satID": satellitecode,
            "flightcontrol": flightcontrol_data,
            "subsystem": subsystem_dict,
            "level": level_dict,
            "orbit": {
                "p": phasedata,
                "h": orbit_h_data
            },
            "total_anomal_sum": total_anomal_sum,
            "updiff": updiff
        }

        all_stcodes.append(stcode)

    # Wrapping all info by overall satellites
    final_tt_df = pd.concat(all_tt_dfs, ignore_index=True)
    # print(final_tt_df.to_string())

    # Additional required fields
    total_mission = int(len(final_tt_df))
    normal_mission = int(len(final_tt_df[final_tt_df['anomal'] == '']))
    auto_anomal_mission = int(len(final_tt_df[(final_tt_df['anomal'] != '') & (final_tt_df['anomal'] != '跟踪失败')]))
    auto_fail_mission = int(len(final_tt_df[final_tt_df['anomal'] == '跟踪失败']))
    total_command_sent = int(final_tt_df['up'].sum())
    payload_work = int(len(final_tt_df[final_tt_df['com_status'] != '']))
    com_only = int(len(final_tt_df[final_tt_df['com_status'] == '通信']))
    v_freq = int(len(final_tt_df[final_tt_df['com_status'] == '通信+v数传']))
    platform_file_inspect = int(len(final_tt_df[final_tt_df['fileinspect'] != '']))
    platform_firing = int(len(final_tt_df[final_tt_df['fire_status'] != '']))

    # Close cursor and connection
    cur.close()
    conn.close()

    # Final JSON for JS
    result = {
        'satellites': all_stcodes,  # Include the stcodes for all satellites
        'total_mission': total_mission,
        'normal_mission': normal_mission,
        'auto_anomal_mission': auto_anomal_mission,
        'auto_fail_mission': auto_fail_mission,
        'total_command_sent': total_command_sent,
        'payload_work': payload_work,
        'com_only': com_only,
        'v_freq': v_freq,
        'platform_file_inspect': platform_file_inspect,
        'platform_firing': platform_firing,
        'total_comtask_sent': total_comtask_sent,
        'phase_diff': json.loads(phasediff_json)  # Add phasediff JSON
    }

    result = json.dumps(result, ensure_ascii=False)
    return result


def tracking_quality(orbitservice_url,
                     mete_data_service,
                     influxdb_input,
                     client_input,
                     satID,
                     date,
                     start,
                     end,
                     mariadb):
    satIDs = satID.split(",")  # Convert comma-separated string to a list of satellite IDs

    all_track_qualities = []

    # Initialize Mongo class and get MongoDB connection
    mongo_instance = get_mongo()

    db = mariadb
    conn = db.get_connection()
    cur = conn.cursor(dictionary=True)

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
    ts1 = ts1.timestamp() * 1000

    ts2 = parser.isoparse(timefilter2)
    ts2 = ts2.timestamp() * 1000

    for satID in satIDs:
        down = downlink_statics(orbitservice_url, mete_data_service, influxdb_input, client_input, timefilter1,
                                timefilter2,
                                satID)

        downjson = json.loads(down)
        downjsontt = downjson['task_list']
        downdf = pd.DataFrame(downjsontt)
        mission_id = downdf['mission_id']
        mission_ids = mission_id.tolist()

        # adding tracking quality data

        uplock_quality = get_tracking_quality(mongo_instance, 'experimental_uplock', mission_ids)
        telemetry_quality = get_tracking_quality(mongo_instance, 'experimental_telemetry', mission_ids)
        track_quality = get_all_quality_data(uplock_quality, telemetry_quality)
        for mission_id in mission_ids:
            tq_for_mission = next((tq for tq in track_quality if tq.get('mission_id') == mission_id), None)
            all_track_qualities.append(tq_for_mission)

    # Transform the list of tracking quality dictionaries into a dictionary
    mission_dict = {f"mission_{tq['mission_id']}": tq for tq in all_track_qualities if tq is not None}
    # Convert keys and remove 'mission_'
    mission_quality = {}
    for key, value in mission_dict.items():
        mission_id = key.split('_')[1]
        mission_quality[mission_id] = value

    mission_quality_json = {"mission_quality": mission_quality}

    for mission_id, mission_data in mission_quality_json["mission_quality"].items():
        if "uplink" in mission_data:
            mission_data["uplink"] = {key: value for key, value in mission_data["uplink"].items() if
                                      value["lock_status"] != 0}

    # Convert to JSON
    mission_quality_json = json.dumps(mission_quality_json, indent=4)

    return mission_quality_json


def daily_reset_stats(metedataservice_url,
                      satID,
                      date,
                      start,
                      end
                      ):
    global max_reset
    satIDs = satID.split(",")  # Convert comma-separated string to a list of satellite IDs

    # Filter only allowed satellite IDs
    allowed_satIDs = {"2", "3", "4", "5", "6"}
    filtered_satIDs = [satID for satID in satIDs if satID in allowed_satIDs]

    if not filtered_satIDs:
        return json.dumps([])  # Return an empty JSON array if no valid satID is provided

    sat_codes = tm_table(metedataservice_url, filtered_satIDs)
    sat_codes_set = {value['code'] for key, value in sat_codes.items()}

    results = []

    # Initialize Mongo class and get MongoDBconnection
    mongo_instance = get_mongo()

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
    ts1 = ts1.timestamp()

    ts2 = parser.isoparse(timefilter2)
    ts2 = ts2.timestamp()

    for sat_code in sat_codes_set:
        daily_cumulative_reset = mongo_instance.get_doc_by_satid_tf('cumulative_reset_count', sat_code, ts1, ts2)
        daily_cumulative_reset = list(daily_cumulative_reset)

        if len(daily_cumulative_reset) == 0:
            previous_cumulative_data = mongo_instance.get_largest_end_time_doc('cumulative_reset_count', sat_code)
            previous_cumulative_counts = [item['cumulative_count'] for item in previous_cumulative_data]
            previous_cumulative_reset = max(previous_cumulative_counts) if previous_cumulative_counts else 0
            today_cumulative_reset = 0

        else:
            min_time_end = min(daily_cumulative_reset, key=lambda x: x['time_end'])['time_end']
            previous_cumulative_data = mongo_instance.get_doc_closest_but_not_greater('cumulative_reset_count',
                                                                                      sat_code, min_time_end)
            previous_cumulative_counts = [item['cumulative_count'] for item in previous_cumulative_data]
            previous_cumulative_reset = max(previous_cumulative_counts) if previous_cumulative_counts else 0
            today_cumulative_reset = len(daily_cumulative_reset)

        max_reset = 8
        results.append({
            'sat_code': sat_code,
            'previous_cumulative_reset': previous_cumulative_reset,
            'today_cumulative_reset': today_cumulative_reset,
            'max_reset': max_reset
        })

    return json.dumps(results)


def get_all_alerts(mete_data_service, satIDs, date, start, end):
    satIDs = satIDs.split(",")  # Convert comma-separated string to a list of satellite IDs

    # Filter only allowed satellite IDs
    allowed_satIDs = {"2", "3", "4", "5", "6", "7", "12", "13", "14"}
    filtered_satIDs = [satID for satID in satIDs if satID in allowed_satIDs]

    sat_codes = tm_table(mete_data_service, filtered_satIDs)
    sat_codes_set = {value['code'] for key, value in sat_codes.items()}

    mongo_instance = get_mongo()

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
    ts1 = ts1.timestamp() * 1000

    ts2 = parser.isoparse(timefilter2)
    ts2 = ts2.timestamp() * 1000

    combined_alerts = []

    for sat_code in sat_codes_set:
        alertdf = mongo_instance.read_alert_data(ts1, ts2, sat_code)

        alert_list = list(alertdf)

        # Check if alert_list is empty
        if len(alert_list) == 0:
            continue

        # Extract params data
        params_data = [item['params'] for item in alert_list]
        df = pd.json_normalize(params_data)

        # Drop unnecessary columns
        df = df.drop(
            columns=['eventCode', 'eventLogId', 'eventTirrgerType', 'eventObjectType', 'eventObjectId',
                     'eventTimeStr', 'eventDesc'])

        # Flatten param.itemDatas and create a new DataFrame
        flattened_data = []
        for index, row in df.iterrows():
            for item in row['param.itemDatas']:
                item['eventName'] = row['eventName']
                item['eventLevel'] = row['eventLevel']
                item['eventRemark'] = row['eventRemark']
                item['param.ext'] = row['param.ext']
                item['eventTime'] = row['eventTime']
                item['satCode'] = sat_code  # Add sat_code to the item
                flattened_data.append(item)

        new_df = pd.DataFrame(flattened_data)

        combined_alerts.append(new_df)

    if combined_alerts:
        final_df = pd.concat(combined_alerts, ignore_index=True)
    else:
        final_df = pd.DataFrame()

    # Convert final DataFrame to JSON format
    alertinfo_json = final_df.to_json(orient='records', force_ascii=False)

    return alertinfo_json


def upload_report_to_alibabacloud(ossendpoint, ossaccess, osssecret, osspath, localpath):
    oss_instance = OSS2(_endpoint=ossendpoint, _access=ossaccess, _secret=osssecret)
    oss_instance.upload_file(key=osspath, filename=localpath)


def publish_report_task(image_data, file_name, OSS2cli, push_note_url):
    # Decode the image data
    image_data = image_data.split(',')[1]
    image_data = base64.b64decode(image_data)

    # Save the image locally
    file_path = os.path.join('data', file_name)
    with open(file_path, 'wb') as f:
        f.write(image_data)

    localpath = f"data/{file_name}"
    osspath = f"flight-control-analysis/dailyreport/{file_name}"

    try:
        # Upload to Alibaba Cloud OSS
        upload_report_to_alibabacloud(ossendpoint=OSS2cli.endpoint, ossaccess=OSS2cli.access,
                                      osssecret=OSS2cli.secret, osspath=osspath, localpath=localpath)

        # Get the image URL from OSS
        imgurl = OSS2cli.make_url(image_name=osspath)

        # Create the content for the push notification
        content = spiderling_daily_report_content(imgurl=imgurl)

        # Post the notification to DingTalk
        response = requests.post(push_note_url, json=json.loads(content), timeout=300)

        # Ensure the local file is deleted after the post request
        os.remove(localpath)

        return response
    except Exception as e:
        # Log the error if needed
        print(f"An error occurred: {e}")

        # Ensure the local file is deleted in case of an error
        if os.path.exists(localpath):
            os.remove(localpath)

        # Optionally, you can re-raise the exception or handle it differently
        raise

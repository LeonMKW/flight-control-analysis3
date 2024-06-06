import logging
import pprint
import json
import pandas as pd
import pytz
from datetime import datetime, timedelta
from task.flightcontrol_algorithms import downlink_statics, general_anomal, satcom, uplink_statics_new, \
    spiderling_file_inspection, \
    orbit_control, orbit_statistics
from utils.db import get_mongo
from dateutil import parser
from utils.dailyreport_utils import o2pphase, sat_alert, obh, get_tracking_quality, get_all_quality_data, \
    get_daily_reset_stats
from utils.flightcontrol_utils import tm_table


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

    # print(ts1)
    # print(ts2)

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

        # print(tt.to_string())
        # print(tt.dtypes)

        # tt = tt.rename(columns={'remark': '计划',
        #                         'mission_id': '任务代号',
        #                         'starting': '开始时间',
        #                         'satellite_code': '卫星代号',
        #                         'station_name': '测站名称',
        #                         'up': '发令计数',
        #                         'increase': '星上正确指令计数增加',
        #                         'com_status': '通信情况',
        #                         'fileinspect': '文件巡检',
        #                         'anomal': '复位切机',
        #                         'fire_status': '轨控'
        #                         })
        all_tt_dfs.append(tt)

        # print(tt.to_string())

        satellitecode = tt['satellite_code'][0]

        # satellite alert status
        subsystemdf, leveldf = sat_alert(satellitecode, mongo_instance, ts1, ts2)
        # print(subsystemdf.to_string())
        # print(leveldf.to_string())

        # orbit status
        # obp_df = obp(cur, satellitecode)
        # print(obp_df.to_string())

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

        # Combine the JSON objects into the desired structure
        stcode = {
            "satID": satellitecode,
            "flightcontrol": flightcontrol_data,
            "subsystem": subsystem_dict,
            "level": level_dict,
            "orbit": {
                "p": phasedata,
                "h": orbit_h_data
            }
        }

        all_stcodes.append(stcode)

        # Wrapping all info by overall satellites
    final_tt_df = pd.concat(all_tt_dfs, ignore_index=True)

    # Close cursor and connection
    cur.close()
    conn.close()

    # TTC service providers
    provider_count = final_tt_df['company_name'].value_counts()
    provider_count = provider_count.reset_index()
    provider_count.columns = ['provider', 'count']
    total = provider_count['count'].sum()
    total_row = pd.DataFrame({'provider': ['Total'], 'count': [total]})
    provider_count = pd.concat([provider_count, total_row], ignore_index=True)

    # Final JSON for JS
    result = {
        'satellites': all_stcodes  # Include the stcodes for all satellites
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
    allowed_satIDs = {"2", "3", "4", "5", "6", "7"}
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

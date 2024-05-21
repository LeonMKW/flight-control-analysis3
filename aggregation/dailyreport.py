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
                            end
                            ):
    satIDs = satID.split(",")  # Convert comma-separated string to a list of satellite IDs

    all_tt_dfs = []

    for satID in satIDs:
        # Check if start or end is None
        if not start or not end:
            date = datetime.strptime(date, "%Y-%m-%d")
            cst = pytz.timezone("Asia/Shanghai")
            startDate_cst = cst.localize(date)
            # print(startDate)
            utc = pytz.timezone("UTC")
            startDate = startDate_cst.astimezone(utc)
            endDate = startDate + timedelta(days=1)
            # print(startDate_utc)
            # print(endDate)
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
        timefilter1 = startDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        timefilter2 = endDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"

        # print(date)
        # print(timefilter1)
        # print(timefilter2)

        # tt = get_task_list(orbitservice_url, timefilter1, timefilter2, satID)

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
        # dtype = orbit_control_result.dtypes['starting']
        # print(dtype)

        # print(orbit_control_result['starting'])
        # orbit_control_result['starting'] = pd.to_datetime(orbit_control_result.starting).tz_localize(None)
        # orbit_control_result['ending'] = orbit_control_result['ending'].dt.timestamp()
        # orbit_control_result['start'] = orbit_control_result['starting'].datetime.fromisoformat()

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

        # print(downdf.to_string())
        # print(updf.to_string())
        # print(payloaddf.to_string())
        # print(file_inspect_resultdf.to_string())
        # print(anomal_resultdf.to_string())
        # print(orbit_control_result.to_string())
        # print(orbit_status_result.to_string())

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

        columns_to_drop = ['ending', 'device', 'fileinspectsum', 'satellite_id', 'antID', 'approach_angle',
                           'max_elvation',
                           'departure_angle', 'rally', 'missing']
        for col in columns_to_drop:
            del merged_df6[col]

        column_order = ['remark',
                        'starting',
                        'satellite_code',
                        'station_name',
                        'duration',
                        'timegap',
                        'tdownlink',
                        'rdownlink',
                        'ratio',
                        'up',
                        'increase',
                        'diff',
                        'unlock_stat',
                        'auto_lock',
                        'lock_interval',
                        'com_status',
                        'fileinspect',
                        'anomal',
                        'fire_status',
                        'orbit_status',
                        'company_name']

        tt = merged_df6[column_order]

        tt = tt.rename(columns={'remark': '计划',
                                'starting': '开始时间',
                                'satellite_code': '卫星代号',
                                'station_name': '测站名称',
                                'duration': '过境时长',
                                'timegap': '入境时差',
                                'tdownlink': '理论遥测帧数',
                                'rdownlink': '收到遥测帧数',
                                'ratio': '送达率',
                                'up': '发令计数',
                                'increase': '星上正确指令计数增加',
                                'diff': '相差',
                                'unlock_stat': '遥控失锁帧数',
                                'auto_lock': '遥控锁定帧数',
                                'lock_interval': '遥控锁定时差',
                                'com_status': '通信情况',
                                'fileinspect': '文件巡检',
                                'anomal': '复位切机',
                                'fire_status': '轨控',
                                'orbit_status': '轨道状态'
                                })
        print(tt.to_string())
        # print(orbit_status_result.to_string())
        # provider_count = orbit_status_result['company_name'].value_counts()
        # provider_count = provider_count.reset_index()
        # provider_count.columns = ['provider', 'count']
        # total = provider_count['count'].sum()
        # total_row = pd.DataFrame({'provider': ['Total'], 'count': [total]})
        # provider_count = pd.concat([provider_count, total_row], ignore_index=True)
        #
        # print(provider_count)

        # result = {
        #     'task_list': json.loads(tt.to_json(orient='records')),
        #     # 'company_name_counts': company_name_counts,
        #     # 'rally_counts': rally_counts,
        #     # 'failed': failed_timegap_count,
        #     # 'total_tasks': task_list_length,
        #     # 'station_name_counts': station_name_counts
        # }
        #
        # result = json.dumps(result, ensure_ascii=False)
        return tt

# if __name__ == '__main__':
#     daily_report('http://orbit-service-inf.prod.yhroot.com/graphql',
#                  'http://mete-data-service.prod.yhroot.com/graphql',
#                  '2023-11-10',
#                  '2023-11-09T05:50:00',
#                  '2023-11-11T06:20:00',
#                  '2')
# tm_table('http://mete-data-service.prod.yhroot.com/graphql', '1,2,3')
#  get_orbit_data_tmcode('http://mete-data-service.prod.yhroot.com/graphql', '5')
#     get_spacecraftinfo('http://mete-data-service.prod.yhroot.com/graphql', '12')


# def daily_report_spiderling(orbitservice_url,
#                             mete_data_service,
#                             influxdb_input,
#                             client_input,
#                             influxdb_action,
#                             client_action,
#                             influxdb_chronograf,
#                             client_chronograf,
#                             satID,
#                             date,
#                             start,
#                             end
#                             ):
#     # Check if start or end is None
#     if not start or not end:
#         date = datetime.strptime(date, "%Y-%m-%d")
#         cst = pytz.timezone("Asia/Shanghai")
#         startDate_cst = cst.localize(date)
#         # print(startDate)
#         utc = pytz.timezone("UTC")
#         startDate = startDate_cst.astimezone(utc)
#         endDate = startDate + timedelta(days=1)
#         # print(startDate_utc)
#         # print(endDate)
#     else:
#         startDate = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S.%fZ")
#         startDate = startDate.replace(tzinfo=pytz.UTC)
#         endDate = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S.%fZ")
#         endDate = endDate.replace(tzinfo=pytz.UTC)
#         date = f"{start} to {end}"
#
#         # Make datetime.utcnow() offset-aware by adding timezone information
#         now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
#
#         # Check if endDate is greater than current time
#         if endDate > now_utc:
#             endDate = now_utc
#
#     # Format the dates as ISO 8601 strings
#     timefilter1 = startDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
#     timefilter2 = endDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
#
#     # print(date)
#     # print(timefilter1)
#     # print(timefilter2)
#
#     # tt = get_task_list(orbitservice_url, timefilter1, timefilter2, satID)
#
#     down = downlink_statics(orbitservice_url, mete_data_service, influxdb_input, client_input, timefilter1, timefilter2,
#                             satID)
#
#     up = uplink_statics_new(orbitservice_url, mete_data_service, influxdb_input, client_input, influxdb_action,
#                             client_action,
#                             timefilter1, timefilter2, satID)
#
#     payload = satcom(orbitservice_url, mete_data_service, influxdb_input, client_input, influxdb_action,
#                      client_action,
#                      timefilter1, timefilter2, satID)
#
#     file_inspect_result = spiderling_file_inspection(orbitservice_url, mete_data_service, influxdb_input, client_input,
#                                           influxdb_action,
#                                           client_action,
#                                           timefilter1, timefilter2, satID)
#
#     anomal = general_anomal(orbitservice_url, mete_data_service, influxdb_input, client_input,
#                             timefilter1,
#                             timefilter2, satID)
#
#     orbit_control_result = orbit_control(orbit_service=orbitservice_url,
#                                          mete_data_service=mete_data_service,
#                                          _influxdb_chonograf=influxdb_chronograf,
#                                          client_chronograf=client_chronograf,
#                                          _influxdb=influxdb_input,
#                                          client=client_input,
#                                          tf1=timefilter1,
#                                          tf2=timefilter2,
#                                          satID=satID)
#     # dtype = orbit_control_result.dtypes['starting']
#     # print(dtype)
#
#     # print(orbit_control_result['starting'])
#     # orbit_control_result['starting'] = pd.to_datetime(orbit_control_result.starting).tz_localize(None)
#     # orbit_control_result['ending'] = orbit_control_result['ending'].dt.timestamp()
#     # orbit_control_result['start'] = orbit_control_result['starting'].datetime.fromisoformat()
#
#     orbit_status_result = orbit_statistics(orbitservice_url, mete_data_service, influxdb_input, client_input,
#                                            timefilter1,
#                                            timefilter2, satID)
#
#     downjson = json.loads(down)
#     downjsontt = downjson['task_list']
#     downdf = pd.DataFrame(downjsontt)
#
#     upjson = json.loads(up)
#     upjsontt = upjson['task_list']
#     updf = pd.DataFrame(upjsontt)
#
#     payloadjson = json.loads(payload)
#     payloadjsontt = payloadjson['task_list_all']
#     payloaddf = pd.DataFrame(payloadjsontt)
#
#     file_inspect_resultjson = json.loads(file_inspect_result)
#     file_inspect_resultjsontt = file_inspect_resultjson['task_list_all']
#     file_inspect_resultdf = pd.DataFrame(file_inspect_resultjsontt)
#
#     anomal_resultjson = json.loads(anomal)
#     anomal_resultjsontt = anomal_resultjson['task_list_all']
#     anomal_resultdf = pd.DataFrame(anomal_resultjsontt)
#
#     # print(downdf.to_string())
#     # print(updf.to_string())
#     # print(payloaddf.to_string())
#     # print(file_inspect_resultdf.to_string())
#     # print(anomal_resultdf.to_string())
#     # print(orbit_control_result.to_string())
#     # print(orbit_status_result.to_string())
#
#     common_columns = ['remark', 'starting', 'ending',
#                       'satellite_code', 'satellite_id',
#                       'station_name', 'device', 'antID',
#                       'approach_angle', 'max_elvation', 'departure_angle',
#                       'company_name', 'rally', 'mission_id']
#
#     # Merge dataframes and keep only one copy of common rows
#     merged_df1 = pd.merge(downdf, updf, on=common_columns, how='outer')
#     merged_df2 = pd.merge(merged_df1, payloaddf, on=common_columns, how='outer')
#     merged_df3 = pd.merge(merged_df2, file_inspect_resultdf, on=common_columns, how='outer')
#     merged_df4 = pd.merge(merged_df3, anomal_resultdf, on=common_columns, how='outer')
#
#     orbit_control_result['starting'] = orbit_control_result['starting'].apply(lambda x: x.timestamp()) * 1000
#     pd.set_option('display.float_format', lambda x: '%.6f' % x)
#     orbit_control_result['ending'] = orbit_control_result['ending'].apply(lambda x: x.timestamp()) * 1000
#     pd.set_option('display.float_format', lambda x: '%.6f' % x)
#
#     # 其中datetime_df_utc是datetime64[ns, UTC]
#
#     merged_df5 = pd.merge(merged_df4, orbit_control_result, on=common_columns, how='outer')
#
#     orbit_status_result['starting'] = orbit_status_result['starting'].apply(lambda x: x.timestamp()) * 1000
#     pd.set_option('display.float_format', lambda x: '%.6f' % x)
#     orbit_status_result['ending'] = orbit_status_result['ending'].apply(lambda x: x.timestamp()) * 1000
#     pd.set_option('display.float_format', lambda x: '%.6f' % x)
#
#     merged_df6 = pd.merge(merged_df5, orbit_status_result, on=common_columns, how='outer')
#     merged_df6['tdownlink'] = pd.to_numeric(merged_df6['tdownlink'], errors='coerce').round().astype(pd.Int64Dtype())
#     merged_df6['duration'] = pd.to_numeric(merged_df6['duration'], errors='coerce').round().astype(pd.Int64Dtype())
#
#     columns_to_drop = ['ending', 'device', 'fileinspectsum', 'satellite_id', 'antID', 'approach_angle', 'max_elvation',
#                        'departure_angle', 'company_name', 'rally', 'missing']
#     for col in columns_to_drop:
#         del merged_df6[col]
#
#     column_order = ['remark',
#                     'starting',
#                     'satellite_code',
#                     'station_name',
#                     'duration',
#                     'timegap',
#                     'tdownlink',
#                     'rdownlink',
#                     'ratio',
#                     'up',
#                     'increase',
#                     'diff',
#                     'unlock_stat',
#                     'auto_lock',
#                     'lock_interval',
#                     'com_status',
#                     'fileinspect',
#                     'anomal',
#                     'fire_status',
#                     'orbit_status']
#
#     tt = merged_df6[column_order]
#
#     tt = tt.rename(columns={'remark': '计划',
#                             'starting': '开始时间',
#                             'satellite_code': '卫星代号',
#                             'station_name': '测站名称',
#                             'duration': '过境时长',
#                             'timegap': '入境时差',
#                             'tdownlink': '理论遥测帧数',
#                             'rdownlink': '收到遥测帧数',
#                             'ratio': '送达率',
#                             'up': '发令计数',
#                             'increase': '星上正确指令计数增加',
#                             'diff': '相差',
#                             'unlock_stat': '遥控失锁帧数',
#                             'auto_lock': '遥控锁定帧数',
#                             'lock_interval': '遥控锁定时差',
#                             'com_status': '通信情况',
#                             'fileinspect': '文件巡检',
#                             'anomal': '复位切机',
#                             'fire_status': '轨控',
#                             'orbit_status': '轨道状态'
#                             })
#     # print(tt.to_string())
#
#     result = {
#         'task_list': json.loads(tt.to_json(orient='records')),
#         # 'company_name_counts': company_name_counts,
#         # 'rally_counts': rally_counts,
#         # 'failed': failed_timegap_count,
#         # 'total_tasks': task_list_length,
#         # 'station_name_counts': station_name_counts
#     }
#
#     result = json.dumps(result, ensure_ascii=False)
#     return result

# daily_report_AS()

# if __name__ == '__main__':
#     daily_report('http://orbit-service-inf.prod.yhroot.com/graphql',
#                  'http://mete-data-service.prod.yhroot.com/graphql',
#                  '2023-11-10',
#                  '2023-11-09T05:50:00',
#                  '2023-11-11T06:20:00',
#                  '2')
# tm_table('http://mete-data-service.prod.yhroot.com/graphql', '1,2,3')
#  get_orbit_data_tmcode('http://mete-data-service.prod.yhroot.com/graphql', '5')
#     get_spacecraftinfo('http://mete-data-service.prod.yhroot.com/graphql', '12')

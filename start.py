# -*- coding: UTF-8 -*-
import os
import sys
from datetime import datetime
from dateutil import parser
from flask import Flask, Response, request
from utils.factory import create_app
import logging
import json
from bson import ObjectId
from flask_cors import CORS
from utils import db
from task.algorithms import downlink_statics, target_detect, satcom, uplink_statics_new, file_inspection, \
    general_anomal, experimental_uplock, experimental_telemetry
from task.dailyreport import daily_report_spiderling
from utils.utils import experimental_telemetry_data
import pandas as pd


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)


PYTHON_ENV = os.environ.get('PYTHON_ENV')
if PYTHON_ENV is None:
    print("Config input error:", PYTHON_ENV)
    sys.exit()
app = create_app(config_name=PYTHON_ENV.upper())
app.app_context().push()
logger = logging.getLogger(__name__)

# 加载influx
influxdb_input = db.Influxdb(app.config['INFLUXDB_USER'], app.config['INFLUXDB_PASSWD'],
                             app.config['INFLUXDB_DB_INPUT'])

influxdb_action = db.Influxdb(app.config['INFLUXDB_USER'], app.config['INFLUXDB_PASSWD'],
                              app.config['INFLUXDB_DB_ACTION'])

influxdb_chronograf = db.Influxdb(app.config['INFLUXDB_USER'], app.config['INFLUXDB_PASSWD'],
                                  app.config['INFLUXDB_DB_CHRONOGRAF'])

client_input = influxdb_input.connect(app.config['INFLUXDB_HOST'],
                                      app.config['INFLUXDB_PORT'])

client_action = influxdb_action.connect(app.config['INFLUXDB_HOST'],
                                        app.config['INFLUXDB_PORT'])

client_chronograf = influxdb_chronograf.connect(app.config['INFLUXDB_HOST'],
                                                app.config['INFLUXDB_PORT'])

orbit_service = app.config['ORBIT_SERVICE']
mete_data_service = app.config['METE_DATA']
# orbit_propagation = app.config['ORBIT_PROPAGATION']
# orbit_maneuver = app.config['ORBIT_MANEUVER']

app = Flask(__name__)
CORS(app)

db.init_val()


@app.route("/")
def hello_world():
    return 'hello world'


@app.route('/status', methods=['POST'])
def progress_bar():
    response = db.progress
    return response
    # return Response(response=response,
    #                 status=200,
    #                 mimetype='application/json')


# downlink
@app.route('/downlink-stats', methods=['POST'])
def down():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = downlink_statics(orbit_service, mete_data_service, influxdb_input, client_input, data['start'],
                                data['end'], data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# uplink
@app.route('/uplink-stats', methods=['POST'])
def up():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = uplink_statics_new(orbit_service, mete_data_service, influxdb_input, client_input, influxdb_action,
                                  client_action, data['start'],
                                  data['end'],
                                  data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# target_detect
@app.route('/targetdetect-stats', methods=['POST'])
def reset():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = target_detect(orbit_service, mete_data_service, influxdb_input, client_input, data['start'], data['end'],
                             data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# sat_com
@app.route('/com-stats', methods=['POST'])
def satellite_com():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = satcom(orbit_service, mete_data_service, influxdb_input, client_input, influxdb_action, client_action,
                      data['start'], data['end'],
                      data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# file_inspection
@app.route('/fileinspection-stats', methods=['POST'])
def file_inspect():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = file_inspection(orbit_service, mete_data_service, influxdb_input, client_input, influxdb_action,
                               client_action, data['start'], data['end'],
                               data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# spiderling_daily_report
@app.route('/spiderlingdailyreport', methods=['POST'])
def spiderling_report_spawn():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = daily_report_spiderling(orbit_service,
                                       mete_data_service,
                                       influxdb_input,
                                       client_input,
                                       influxdb_action,
                                       client_action,
                                       influxdb_chronograf,
                                       client_chronograf,
                                       satID=data['satID'],
                                       date=data['date'],
                                       start=data['start'],
                                       end=data['end']
                                       )
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# reset statistics
@app.route('/reset-stats', methods=['POST'])
def reset_stats():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = general_anomal(orbit_service, mete_data_service, influxdb_input, client_input,
                              data['start'], data['end'],
                              data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# @app.route('/download', methods=["GET"])
# def download():
#     file_path = os.path.join(os.getcwd(), "build", f'forecast_and_plan v{exe_version}.rar')
#     return send_file(path_or_file=file_path, as_attachment=True)

# data = {
#     'timestamp': [1710410279, 1710410281, 1710410283, 1710410285, 1710410287, 1710410289, 1710410290, 1710410292,
#                   1710410294, 1710410298, 1710410299, 1710410300, 1710410302, 1710410303, 1710410305, 1710410307],
#     'lockstatus': [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]}
# df = pd.DataFrame(data)


if __name__ == "__main__":
    # results_dict = experimental_telemetry('http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                    'http://mete-data-service.prod.yhroot.com/graphql',
    #                                    influxdb_input, client_input,
    #                                    "2024-03-27T03:51:07.000Z",
    #                                    "2024-03-27T04:05:05.000Z", '12')

    # results_dict = experimental_telemetry('http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                       'http://mete-data-service.prod.yhroot.com/graphql',
    #                                       influxdb_input, client_input,
    #                                       "2024-03-23T01:00:38.000Z",
    #                                       "2024-03-23T01:29:38.000Z", '5')
    #

    # results_dict = experimental_uplock('http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                    'http://mete-data-service.prod.yhroot.com/graphql',
    #                                    influxdb_input, client_input,
    #                                    "2024-03-22T04:39:30.000Z",
    #                                    "2024-03-22T07:11:51.000Z", '12')
    # print(results_dict)
    # results_dict = experimental_uplock('http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                    'http://mete-data-service.prod.yhroot.com/graphql',
    #                                    influxdb_input, client_input,
    #                                    "2024-03-18T06:54:45.000Z",
    #                                    "2024-03-18T07:17:35.000Z", '2')
    # results_dict = experimental_uplock('http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                    'http://mete-data-service.prod.yhroot.com/graphql',
    #                                    influxdb_input, client_input,
    #                                    "2024-03-10T12:50:00.000Z",
    #                                    "2024-03-10T13:10:00.000Z", "1")
    # print(results_dict)

    # results_dict = experimental_telemetry_data(
    #                                            'http://mete-data-service.prod.yhroot.com/graphql',
    #                                            influxdb_input, client_input,
    #                                            "2024-03-26T03:01:00.000Z",
    #                                            "2024-03-26T03:31:00.000Z", '3')
    # print(results_dict.to_string())

    # vcId(mete_data_service, influxdb_input, client_input, "2024-02-03T00:08:13.000Z", "2024-02-03T00:48:13.000Z",
    #      '7')
    port = int(os.environ.get("PORT", 7877))
    app.run(host='0.0.0.0', port=port, debug=True)

# downlink_statics(influxdb_input, client_input, '2023-09-20T09:00:00.000Z', '2023-09-21T10:00:00.000Z', '2')
# downlink_statics(influxdb_input, client_input, '2023-09-21T06:00:00.000Z', '2023-09-21T09:00:00.000Z', '2')
# 一次fail
# downlink_statics(influxdb_input, client_input, '2023-09-01T16:00:00.000Z', '2023-09-22T09:00:00.000Z', '2,3')
# downlink_statics(orbit_service, mete_data_service, influxdb_input, client_input, '2023-09-20T16:00:00.000Z', '2023-09-22T09:00:00.000Z', '2')
# 格式fail
# downlink_statics(influxdb_input, client_input, '2023-09-07T16:00:00.000Z', '2023-11-05T16:00:00.000Z', '7')
# commands(influxdb_action, client_action, '2023-10-07T16:00:00.000Z', '2023-10-11T16:00:00.000Z', '5')
# correctframe(influxdb_input, client_input, '2022-10-07T10:00:00.000Z', '2023-10-08T11:00:00.000Z', '6')
# obc_resetnew(mete_data_service, influxdb_input, client_input, '2023-10-15T01:21:26.000Z', '2023-10-20T03:21:26.000Z','3')
# uplink_statics_new(influxdb_input, client_input, influxdb_action, client_action, '2023-10-01T16:00:00.000Z',
#                    '2023-11-05T16:00:00.000Z', '7')
# reset_detect(orbit_service, mete_data_service, influxdb_input, client_input, '2023-11-07T01:21:26.000Z', '2023-11-08T02:09:26.000Z', '14')
# reset_detect(orbit_service, mete_data_service, influxdb_input, client_input, '2023-09-30T01:21:26.000Z', '2023-10-01T03:21:26.000Z', '4')
# payload_pwr(mete_data_service, influxdb_input, client_input, '2023-10-15T16:00:00.000Z', '2023-10-15T16:00:00.000Z', '1')
# satcom(orbit_service, mete_data_service,influxdb_input, client_input, influxdb_action, client_action, '2023-10-28T01:21:26.000Z', '2023-10-31T03:21:26.000Z', '14')
# file_inspection(orbit_service, mete_data_service, influxdb_input, client_input, influxdb_action, client_action, '2023-10-29T10:00:00.000Z', '2023-10-31T23:00:00.000Z', '3')
# vcIdnew(mete_data_service, influxdb_input, client_input, "2023-07-22T16:00:00.000Z", "2023-07-23T04:00:00.000Z", '14')
# daily_report_spiderling(orbitservice_url='http://orbit-service-inf.prod.yhroot.com/graphql',
#                         mete_data_service='http://mete-data-service.prod.yhroot.com/graphql',
#                         influxdb_input=influxdb_input,
#                         client_input=client_input,
#                         influxdb_action=influxdb_action,
#                         client_action=client_action,
#                         influxdb_chronograf=influxdb_chronograf,
#                         client_chronograf=client_chronograf,
#                         satID='6',
#                         date='2024-01-30',
#                         start='',
#                         end='')
# electric_propulsion('http://mete-data-service.prod.yhroot.com/graphql',
#                     influxdb_input,
#                     client_input,
#                     '2024-01-10T16:00:00.000Z',
#                     '2024-01-17T16:00:00.000Z',
#                     '3')
# monitor_data('http://mete-data-service.prod.yhroot.com/graphql',
#              influxdb_chronograf,
#              client_chronograf,
#              '2024-01-10T16:00:00.000Z',
#              '2024-01-17T16:00:00.000Z',
#              '3')
# orbit_control('http://orbit-service-inf.prod.yhroot.com/graphql',
#               'http://mete-data-service.prod.yhroot.com/graphql',
#               influxdb_chronograf, client_chronograf,
#               influxdb_input, client_input,
#               '2024-01-10T16:00:00.000Z',
#               '2024-01-17T16:00:00.000Z',
#               '3')
# orbit_statistics('http://orbit-service-inf.prod.yhroot.com/graphql',
#                  'http://mete-data-service.prod.yhroot.com/graphql',
#                  influxdb_input, client_input,
#                  '2023-12-16T16:00:00.000Z',
#                  '2023-12-17T16:00:00.000Z',
#                  '14')
# uplock('http://mete-data-service.prod.yhroot.com/graphql',
#        influxdb_input,
#        client_input,
#        '2023-12-16T16:00:00.000Z',
#        '2023-12-17T16:00:00.000Z',
#        '6')

# def analyze_telemetry_intervals(df):
#     df = df.sort_values(by='timestamp')
#
#     # Group by 'timestamp' and calculate difference
#     df['timestamp_diff'] = df['timestamp'].diff()
#
#     # Fill NaN values in the difference column with 0
#     df['timestamp_diff'] = df['timestamp_diff'].fillna(0)
#
#     # Reset group counter when 'timestamp' difference exceeds 3
#     df['group'] = (df['timestamp_diff'] > 3).cumsum()
#
#     # Group by the calculated 'group'
#     grouped = df.groupby('group')
#
#     # Count total number of groups
#     total_group_number = grouped.ngroups
#
#     # Count number of groups where there is telemetry data
#     num_groups = len(grouped)
#
#     # Find the longest group
#     longest_group_length = grouped.size().max()
#     longest_group_number = grouped.size().idxmax()
#
#     # Find the first and last timestamp of the longest group
#     first_timestamp = df[df['group'] == longest_group_number]['timestamp'].iloc[0]
#     last_timestamp = df[df['group'] == longest_group_number]['timestamp'].iloc[-1]
#
#     # print(total_group_number)
#     # print(num_groups)
#     # print(longest_group_length)
#
#     return {
#         "total_group_number": total_group_number,
#         "num_groups": num_groups,
#         "longest_group_length": longest_group_length,
#         "longest_group_number": longest_group_number,
#         "first_timestamp": first_timestamp,
#         "last_timestamp": last_timestamp
#     }
#
#
# df = pd.DataFrame({
#     'timestamp': [1708957314449.000000, 1708957314450.000000, 1708957314451.000000,
#                   1708957314452.000000, 1708957314457.000000, 1708957314458.000000],
#     'aoc_flag': [0, 0, 0, 0, 0, 0],
#     'vcId': [21, 21, 42, 21, 21, 21]
# })
# print(df)
#
# if __name__ == "__main__":
#     print(df.to_string())
#
#     df = analyze_telemetry_intervals(df)
#     print(df)

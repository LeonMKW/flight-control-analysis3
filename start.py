# -*- coding: UTF-8 -*-
import os
import sys
import time
from flask import Flask, Response, request
from utils.factory import create_app
import logging
import json
from bson import ObjectId
from flask_cors import CORS
from utils import db
from task.algorithms import downlink_statics, target_detect, satcom, uplink_statics_new, file_inspection, \
    general_anomal, orbit_control
from task.dailyreport import daily_report_spiderling
from utils.utils import electric_propulsion, monitor_data, uplock
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
orbit_maneuver = app.config['ORBIT_MANEUVER']

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


if __name__ == "__main__":
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

# import pandas as pd
#
#
# def analyze_lock_status(df, satID):
#     if satID == 1:
#         # Check if 'XAlock' or 'XBlock' equals 1
#         df['lock_status'] = (df['XALock'] == 1) | (df['XBlock'] == 1)
#     else:
#         # Check if 'XAlock' or 'XBlock' equals 2
#         df['lock_status'] = (df['XALock'] == 2) | (df['XBlock'] == 2)
#
#     # Convert boolean values to 1 and 0
#     df['lock_status'] = df['lock_status'].astype(int)
#
#     # Calculate 'lock_interval'
#     first_lock_time = round(df[df['lock_status'] == 1]['timestamp'].iloc[0] / 1000)
#     first_non_lock_time = round(df[df['lock_status'] == 0]['timestamp'].iloc[0] / 1000)
#     lock_interval = first_lock_time - first_non_lock_time
#
#     # Check if the first 6 lock_status are all 0 for 'autolock'
#     if all(df['lock_status'][:6] == 0):
#         autolock = '前判未锁'
#     else:
#         autolock = '前判锁定'
#
#     # Analyze 'lock_status' column for 'lock_stat'
#     max_consecutive_zeros = 0
#     current_consecutive_zeros = 0
#
#     for status in df['lock_status']:
#         if status == 0:
#             current_consecutive_zeros += 1
#             max_consecutive_zeros = max(max_consecutive_zeros, current_consecutive_zeros)
#         else:
#             current_consecutive_zeros = 0
#
#     if max_consecutive_zeros >= 5:
#         lock_stat = '上行失锁'
#     elif 1 < max_consecutive_zeros < 5:
#         lock_stat = '上行闪锁'
#     else:
#         lock_stat = '全程锁定'
#
#     return autolock, lock_stat, lock_interval
#
#
# import pandas as pd
# import numpy as np
#
# df = pd.DataFrame({
#     'timestamp': [1708957314449.000000, 1708957314449.000000, 1708957316449.000000,
#                   1708957316449.000000, 1708957318449.000000, 1708957318449.000000],
#     'XBlock': [np.nan, 0.00000, np.nan, 0.00000, np.nan, 2.00000],
#     'XALock': [0.00000, np.nan, 0.00000, np.nan, 0.00000, np.nan]
# })
# print(df)
# df = df.groupby('timestamp').last().reset_index()
#
#     # df['lock_status'] = ((df['XBlock'] == 2) | (df['XALock'] == 2)).astype(int)
# #
# #
# if __name__ == "__main__":
#     print(df.to_string())
#
#     satID = 3  # Or whatever value it should be
#     autolock, lock_stat, lock_interval = analyze_lock_status(df, satID)
#     print(df)
#     print("Autolock:", autolock)
#     print("Lock status:", lock_stat)
#     print("Lock interval:", lock_interval)

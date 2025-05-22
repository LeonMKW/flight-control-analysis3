# -*- coding: UTF-8 -*-
import os
import sys
import requests
from flask import Flask, Response, request, jsonify, render_template
from utils.factory import create_app
import logging
import json
from bson import ObjectId
from flask_cors import CORS
from utils import db
from task.flightcontrol_algorithms import downlink_statics, downlink_statics_experiment, target_detect, satcom, \
    uplink_statics_new, \
    spiderling_file_inspection, spiderling_file_inspect_experiment, uplink_statics_experiment, \
    general_anomal, experimental_uplock, experimental_telemetry, hist_interval, gnss_interval
from aggregation.dailyreport import daily_report_spiderling, tracking_quality, daily_reset_stats, get_all_alerts, \
    publish_report_task, upload_to_oss2_only_report_task, ask_dify
from task.flightcontrol_automation_tasks import flight_operation_data_auto_task
from task.satellitestatus_automation_tasks import satellite_status_data_auto_task

# from task.od_automation_tasks import orbit_precision_analysis_auto_task
# collision_avoidance_precision_analysis_auto_task
from utils.dailyreport_utils import get_fire_records, get_gateway_task, get_obh, get_flight_controller
from task.ASsatellite_tasks import AS02_sensing_upload, AS02_payload_data_transmission, \
    AS02_platform_data_transmission, AS02_hist_file_save, silicon_battery_task, delete_platform_data_task, \
    delete_payload_data_task, AS03_sensing_upload, AS03_in_sight_sensing_task, AS03_payload_data_transmission, \
    AS03_platform_data_transmission, AS03_hist_file_save, AS03_delete_data_task, delete_platform_folder_task, \
    AS03_out_sight_sensing_task
import warnings
from task.od_algorithm import get_Post_Satellite_Report_Info, get_satellite_report_files, \
    propagating_2nd_predictive_ephemeris

from task.AS_satellitestatus_automation_task import AS02_auto_task_with_duplicate_check, \
    AS03_auto_task_with_duplicate_check

from task.space_enviroment_info import space_environment_info_with_summary_from_odpa

warnings.filterwarnings('ignore')


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

client_input = influxdb_input.connect(app.config['INFLUXDB_HOST'],
                                      app.config['INFLUXDB_PORT'])

influxdb_action = db.Influxdb(app.config['INFLUXDB_USER'], app.config['INFLUXDB_PASSWD'],
                              app.config['INFLUXDB_DB_ACTION'])

client_action = influxdb_action.connect(app.config['INFLUXDB_HOST'],
                                        app.config['INFLUXDB_PORT'])

influxdb_chronograf = db.Influxdb(app.config['INFLUXDB_USER'], app.config['INFLUXDB_PASSWD'],
                                  app.config['INFLUXDB_DB_CHRONOGRAF'])

client_chronograf = influxdb_chronograf.connect(app.config['INFLUXDB_HOST'],
                                                app.config['INFLUXDB_PORT'])

influxdb_orbdata = db.Influxdb(app.config['INFLUXDB_USER'], app.config['INFLUXDB_PASSWD'],
                               app.config['INFLUXDB_DB_ORBITDATA'])

client_orbdata = influxdb_orbdata.connect(app.config['INFLUXDB_HOST'],
                                          app.config['INFLUXDB_PORT'])

orbit_service = app.config['ORBIT_SERVICE']
mete_data_service = app.config['METE_DATA']
# orbit_propagation = app.config['ORBIT_PROPAGATION']
# orbit_maneuver = app.config['ORBIT_MANEUVER']

# 加载mongodb
mongo = db.Mongo(app.config['MONGO_HOSTS'],
                 app.config['MONGO_AUTH_SOURCE'],
                 app.config['MONGO_INITDB_ROOT_USERNAME'],
                 app.config['MONGO_INITDB_ROOT_PASSWORD'])

# 加载通知服务
note_url = app.config['NOTIFICATION_URL']

# 加载轨道外推计算接口
orbit_prop_url = app.config['ORBIT_PROPAGATION']

# 加载轨控活动查询
orbit_maneuver_url = app.config['ORBIT_MANEUVER']

# 加载mariadb
mariadbsetup = db.Mariadb(app.config['MARIADB_HOST'],
                          app.config['MARIADB_PORT'],
                          app.config['MARIADB_ODDBNAME'],
                          app.config['MARIADB_USER'],
                          app.config['MARIADB_PASSWORD'])

# 连OSS
OSS2 = db.OSS2(app.config['OSS2_ENDPOINT'],
               app.config['OSS2_ACCESS'],
               app.config['OSS2_SECRET'],
               app.config['OSS2_BUCKET'])

# 查信关站任务
gateway_url = app.config['APPLICATION_TASK']
# gateway_auth = app.config['APPLICATION_AUTHORIZATION']

# 航天器信息上报列表查询
post_satellite_report_search = app.config['POST_SATELLITE_REPORT_SEARCH']

# 航天器上报轨道外推下载链接
get_satellite_file_download = app.config['GET_SATELLITE_FILE_DOWNLOAD']

# 获取HTTP POST返还结果的AUTH TOKEN
post_token_url = app.config['POST_TOKEN_URL']
post_token_user_name = app.config['POST_TOKEN_USERNAME']

# 连ODPA
odpa3_url = app.config['ODPA3_URL']

post_token_password = app.config['POST_TOKEN_PASSWORD']

# 连deepseek-r1
dsr1_url = app.config['DSR1_URL']
dsr1_token = app.config['DSR1_TOKEN']

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

    response = downlink_statics(post_token_url,
                                post_token_user_name,
                                post_token_password,
                                orbit_service, mete_data_service, influxdb_input, client_input, data['start'],
                                data['end'], data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


@app.route('/downlink-stats-experiment', methods=['POST'])
def down_exp():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = downlink_statics_experiment(post_token_url,
                                           post_token_user_name,
                                           post_token_password, orbit_service, mete_data_service, influxdb_input,
                                           client_input,
                                           data['start'],
                                           data['end'], data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# downgap
@app.route('/downgap-experiment', methods=['POST'])
def downgap():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = experimental_telemetry(post_token_url,
                                      post_token_user_name,
                                      post_token_password, orbit_service, mete_data_service, influxdb_input,
                                      client_input, data['start'],
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

    response = uplink_statics_new(post_token_url,
                                  post_token_user_name,
                                  post_token_password, orbit_service, mete_data_service, influxdb_input, client_input,
                                  influxdb_action,
                                  client_action, data['start'],
                                  data['end'],
                                  data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# upgap
@app.route('/upgap-experiment', methods=['POST'])
def upgap():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = experimental_uplock(post_token_url,
                                   post_token_user_name,
                                   post_token_password, orbit_service, mete_data_service, influxdb_input, client_input,
                                   data['start'],
                                   data['end'], data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


@app.route('/uplink-stats-experiment', methods=['POST'])
def up_exp():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = uplink_statics_experiment(post_token_url,
                                         post_token_user_name,
                                         post_token_password, orbit_service, mete_data_service, influxdb_input,
                                         client_input,
                                         influxdb_action,
                                         client_action, data['start'],
                                         data['end'],
                                         data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# hist_interval
@app.route('/hist-interval-experiment', methods=['POST'])
def hist_int():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = hist_interval(post_token_url,
                             post_token_user_name,
                             post_token_password, orbit_service, mete_data_service, influxdb_input, client_input,
                             data['start'],
                             data['end'], data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# gnss_interval
@app.route('/gnss-interval-experiment', methods=['POST'])
def gnss_int():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = gnss_interval(post_token_url,
                             post_token_user_name,
                             post_token_password, orbit_service, mete_data_service, influxdb_input, client_input,
                             data['start'],
                             data['end'], data['satID'])
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

    response = target_detect(post_token_url,
                             post_token_user_name,
                             post_token_password, orbit_service, mete_data_service, influxdb_input, client_input,
                             data['start'], data['end'],
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

    response = satcom(post_token_url,
                      post_token_user_name,
                      post_token_password, orbit_service, mete_data_service, influxdb_input, client_input,
                      influxdb_action, client_action,
                      data['start'], data['end'],
                      data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# file_inspection
@app.route('/spiderlingfileinspection-stats', methods=['POST'])
def file_inspect():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = spiderling_file_inspection(post_token_url,
                                          post_token_user_name,
                                          post_token_password, orbit_service, mete_data_service, influxdb_input,
                                          client_input,
                                          influxdb_action,
                                          client_action, data['start'], data['end'],
                                          data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# file_inspection_experiment
@app.route('/spiderlingfileinspection-stats-experiment', methods=['POST'])
def file_inspect_experiment():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = spiderling_file_inspect_experiment(post_token_url,
                                                  post_token_user_name,
                                                  post_token_password, orbit_service, mete_data_service, influxdb_input,
                                                  client_input,
                                                  influxdb_action,
                                                  client_action, data['start'], data['end'],
                                                  data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# # spiderling_daily_report
@app.route('/spiderlingdailyreport', methods=['POST'])
def spiderling_report_spawn():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    try:
        response = daily_report_spiderling(post_token_url,
                                           post_token_user_name,
                                           post_token_password,
                                           orbit_service,
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
                                           end=data['end'],
                                           mariadb=mariadbsetup,
                                           influxdb_orbdata=influxdb_orbdata,
                                           client_orbdata=client_orbdata
                                           )
        return Response(response=response,
                        status=200,
                        mimetype='application/json')

    except ValueError as e:
        return Response(response=json.dumps({"Error": str(e)}),
                        status=400,
                        mimetype='application/json')


# reset statistics
@app.route('/reset-stats', methods=['POST'])
def reset_stats():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = general_anomal(post_token_url,
                              post_token_user_name,
                              post_token_password,
                              orbit_service, mete_data_service, influxdb_input, client_input,
                              data['start'], data['end'],
                              data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# write to flight-operation-middle-data //自动计算系列
@app.route('/flight-operation-middle-data', methods=['POST'])
def write_to_mongo_fod():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = flight_operation_data_auto_task(post_token_url,
                                               post_token_user_name,
                                               post_token_password,
                                               orbit_service,
                                               mete_data_service,
                                               influxdb_input,
                                               client_input,
                                               influxdb_action,
                                               client_action,
                                               satIDs=data['satIDs'],
                                               date=data['date'],
                                               start=data['start'],
                                               end=data['end']
                                               )
    return jsonify(response), 200


# write to flight-operation-middle-data //自动计算系列
@app.route('/satellite-status-auto-mission', methods=['POST'])
def satellite_OBC_status_calculate():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = satellite_status_data_auto_task(post_token_url,
                                               post_token_user_name,
                                               post_token_password,
                                               mete_data_service,
                                               influxdb_input,
                                               client_input,
                                               satIDs=data['satIDs'],
                                               date=data['date'],
                                               start=data['start'],
                                               end=data['end'],
                                               note_url=note_url
                                               )
    return jsonify(response), 200


# # excute odpa task //自动计算系列
# @app.route('/odpa', methods=['POST'])
# def odpa():
#     data = request.json
#     if data is None or data == {}:
#         return Response(response=json.dumps({"Error": "Please provide connection information"}),
#                         status=400,
#                         mimetype='application/json')
#
#     response = orbit_precision_analysis_auto_task(
#         post_token_url,
#         post_token_user_name,
#         post_token_password,
#         metedataservice_url=mete_data_service,
#         orbitserviceurl=orbit_service,
#         _influxdb=influxdb_input, client=client_input,
#         mariadb=mariadbsetup,
#         note_url=note_url,
#         orbit_prop_url=orbit_prop_url,
#         OSS2=OSS2,
#         satID_list=data['satIDs']
#     )
#     return jsonify(response), 200


# # excute collision avoidance PA//自动计算系列
# @app.route('/capa', methods=['POST'])
# def capa():
#     data = request.json
#     if data is None or data == {}:
#         return Response(response=json.dumps({"Error": "Please provide connection information"}),
#                         status=400,
#                         mimetype='application/json')
#
#     response = collision_avoidance_precision_analysis_auto_task(metedataservice_url=mete_data_service,
#                                                                 orbitserviceurl=orbit_service,
#                                                                 _influxdb=influxdb_input, client=client_input,
#                                                                 mariadb=mariadbsetup,
#                                                                 note_url=note_url,
#                                                                 orbit_prop_url=orbit_prop_url,
#                                                                 OSS2=OSS2,
#                                                                 satID_list=data['satIDs']
#                                                                 )
#     return jsonify(response), 200


# spiderling track_quality
@app.route('/trackquality', methods=['POST'])
def gettrackquality():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = tracking_quality(post_token_url,
                                post_token_user_name,
                                post_token_password,
                                orbitservice_url=orbit_service,
                                mete_data_service=mete_data_service,
                                influxdb_input=influxdb_input,
                                client_input=client_input,
                                satID=data['satID'],
                                date=data['date'],
                                start=data['start'],
                                end=data['end'],
                                mariadb=mariadbsetup
                                )
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# spiderling daily reset count
@app.route('/cumulative-reset', methods=['POST'])
def getcumreset():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = daily_reset_stats(post_token_url,
                                 post_token_user_name,
                                 post_token_password,
                                 metedataservice_url=mete_data_service,
                                 satID=data['satID'],
                                 date=data['date'],
                                 start=data['start'],
                                 end=data['end']
                                 )
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# fire_records
@app.route('/fire-records', methods=['POST'])
def getfire():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = get_fire_records(post_token_url,
                                post_token_user_name,
                                post_token_password,
                                orbit_maneuver_url=orbit_maneuver_url,
                                start=data['start'],
                                end=data['end'],
                                date=data['date'],
                                satID=data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# gs_gateway_task
@app.route('/gateway-task', methods=['POST'])
def getgatewaytaskrecord():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = get_gateway_task(post_token_url,
                                post_token_user_name,
                                post_token_password,
                                app_url=gateway_url,
                                start=data['start'],
                                end=data['end'],
                                date=data['date'],
                                satID=data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# fire_records
@app.route('/get-all-alerts', methods=['POST'])
def getallalerts():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = get_all_alerts(post_token_url,
                              post_token_user_name,
                              post_token_password,
                              mete_data_service=mete_data_service,
                              satIDs=data['satID'],
                              date=data['date'],
                              start=data['start'],
                              end=data['end']
                              )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


@app.route('/upload-to-oss2-only', methods=['POST'])
def upload_image_to_oss_only():
    data = request.json
    if not data or 'image' not in data or 'fileName' not in data:
        return Response(response=json.dumps({"message": "Invalid input"}),
                        status=400,
                        mimetype='application/json')

    try:
        upload_to_oss2_only_report_task(
            image_data=data['image'],
            file_name=data['fileName'],
            OSS2cli=OSS2
        )
        return Response(response=json.dumps({"message": "success"}),
                        status=200,
                        mimetype='application/json')
    except Exception as e:
        print(f"Upload error: {e}")
        return Response(response=json.dumps({"message": "error", "detail": str(e)}),
                        status=500,
                        mimetype='application/json')


@app.route('/publish-spiderlingdailyreport', methods=['POST'])
def upload_image_and_publish_to_dingtalk():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = publish_report_task(image_data=data['image'],
                                   file_name=data['fileName'],
                                   OSS2cli=OSS2,
                                   push_note_url=note_url
                                   )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02 remote sensing task upload
@app.route('/AS02-upload-sensing-task', methods=['POST'])
def getallAS02uploadsensingtask():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS02_sensing_upload(post_token_url,
                                   post_token_user_name,
                                   post_token_password,
                                   mete_data_service,
                                   influxdb_action,
                                   client_action,
                                   satID=data['satID'],
                                   tf1=data['tf1'],
                                   tf2=data['tf2']
                                   )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02 payload data transmission
@app.route('/AS02-payload-data-transmission', methods=['POST'])
def getallAS02payloaddatatransmission():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS02_payload_data_transmission(post_token_url,
                                              post_token_user_name,
                                              post_token_password,
                                              mete_data_service,
                                              _influxdb_input=influxdb_input,
                                              client_input=client_input,
                                              influxdb_action=influxdb_action,
                                              host_action=client_action,
                                              satID=data['satID'],
                                              tf1=data['tf1'],
                                              tf2=data['tf2']
                                              )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02 platform data transmission
@app.route('/AS02-platform-data-transmission', methods=['POST'])
def getallAS02platformdatatransmission():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS02_platform_data_transmission(
        post_token_url,
        post_token_user_name,
        post_token_password,
        mete_data_service,
        _influxdb_input=influxdb_input,
        client_input=client_input,
        influxdb_action=influxdb_action,
        host_action=client_action,
        satID=data['satID'],
        tf1=data['tf1'],
        tf2=data['tf2']
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02 hist_data_save
@app.route('/AS02-histdatasave', methods=['POST'])
def getAS02histdatasave():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS02_hist_file_save(post_token_url,
                                   post_token_user_name,
                                   post_token_password,
                                   mete_data_service,
                                   _influxdb_input=influxdb_input,
                                   client_input=client_input,
                                   influxdb_action=influxdb_action,
                                   host_action=client_action,
                                   satID=data['satID'],
                                   tf1=data['tf1'],
                                   tf2=data['tf2']
                                   )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02 silicon-battery-experiment
@app.route('/AS02-silicon-battery', methods=['POST'])
def getAS02siliconbattery():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = silicon_battery_task(post_token_url,
                                    post_token_user_name,
                                    post_token_password,
                                    mete_data_service,
                                    influxdb_action=influxdb_action,
                                    host_action=client_action,
                                    satID=data['satID'],
                                    tf1=data['tf1'],
                                    tf2=data['tf2']
                                    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02-delete-platform-task
@app.route('/AS02-delete-platform-task', methods=['POST'])
def get_delete_platform_data_task():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = delete_platform_data_task(post_token_url,
                                         post_token_user_name,
                                         post_token_password,
                                         mete_data_service,
                                         influxdb_action=influxdb_action,
                                         host_action=client_action,
                                         satID=data['satID'],
                                         tf1=data['tf1'],
                                         tf2=data['tf2']
                                         )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02-delete-platformfolder-task
@app.route('/AS02-delete-platformfolder-task', methods=['POST'])
def get_delete_platform_folder_data_task():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = delete_platform_folder_task(post_token_url,
                                           post_token_user_name,
                                           post_token_password,
                                           mete_data_service,
                                           influxdb_action=influxdb_action,
                                           host_action=client_action,
                                           satID=data['satID'],
                                           tf1=data['tf1'],
                                           tf2=data['tf2']
                                           )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02-delete-payload-task
@app.route('/AS02-delete-payload-task', methods=['POST'])
def get_delete_payload_data_task():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = delete_payload_data_task(post_token_url,
                                        post_token_user_name,
                                        post_token_password,
                                        mete_data_service,
                                        influxdb_action=influxdb_action,
                                        host_action=client_action,
                                        satID=data['satID'],
                                        tf1=data['tf1'],
                                        tf2=data['tf2']
                                        )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS03 remote sensing task upload
@app.route('/AS03-upload-sensing-task', methods=['POST'])
def getAS03uploadsensingtask():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS03_sensing_upload(post_token_url,
                                   post_token_user_name,
                                   post_token_password,
                                   mete_data_service,
                                   influxdb_action,
                                   client_action,
                                   satID=data['satID'],
                                   tf1=data['tf1'],
                                   tf2=data['tf2']
                                   )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


@app.route('/obh', methods=['POST'])
def all_obh():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = get_obh(
        post_token_url,
        post_token_user_name,
        post_token_password,
        mete_data_service=mete_data_service,
        influxdb_orbdata=influxdb_orbdata,
        client_orbdata=client_orbdata,
        satID=data['satID'],  # Accept multiple satellite IDs
        start=data['start'],
        end=data['end']
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# try
@app.route('/try', methods=['POST'])
def od_temp():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = propagating_2nd_predictive_ephemeris(
        post_token_url,
        post_token_user_name,
        post_token_password,
        mete_data_service=mete_data_service,
        post_satellite_report_search_url=post_satellite_report_search,
        get_satellite_file_download_url=get_satellite_file_download,
        satelliteId=data['satelliteId'],
        reportTypes=data['reportTypes'],
        beginTime=data['beginTime'],
        endTime=data['endTime'],
        states=data['states'],
        _influxdb=influxdb_input,
        client=client_input,
        orbit_prop_url=orbit_prop_url,
        propagation_hours=data['propagation_hours'],
        mariadb=mariadbsetup
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS03 remote infrared sensing
@app.route('/AS03-insight-sensing-task', methods=['POST'])
def AS03insightsensingtask():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS03_in_sight_sensing_task(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service=orbit_service,
        metedataservice_url=mete_data_service,
        _influxdb=influxdb_input,
        client=client_input,
        satID=data['satID'],
        tf1=data['tf1'],
        tf2=data['tf2']
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS03 remote infrared sensing outsight
@app.route('/AS03-outsight-sensing-task', methods=['POST'])
def AS03outsightsensingtask():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS03_out_sight_sensing_task(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service=orbit_service,
        metedataservice_url=mete_data_service,
        _influxdb=influxdb_input,
        client=client_input,
        influxdb_action=influxdb_action,
        host_action=client_action,
        satID=data['satID'],
        tf1=data['tf1'],
        tf2=data['tf2']
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS03 payload data transmission
@app.route('/AS03-payload-data-transmission', methods=['POST'])
def getallAS03payloaddatatransmission():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS03_payload_data_transmission(
        post_token_url,
        post_token_user_name,
        post_token_password,
        mete_data_service,
        _influxdb_input=influxdb_input,
        client_input=client_input,
        influxdb_action=influxdb_action,
        host_action=client_action,
        satID=data['satID'],
        tf1=data['tf1'],
        tf2=data['tf2']
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS03 payload data transmission
@app.route('/AS03-platform-data-transmission', methods=['POST'])
def getallAS03platformdatatransmission():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS03_platform_data_transmission(
        post_token_url,
        post_token_user_name,
        post_token_password,
        mete_data_service,
        _influxdb_input=influxdb_input,
        client_input=client_input,
        influxdb_action=influxdb_action,
        host_action=client_action,
        satID=data['satID'],
        tf1=data['tf1'],
        tf2=data['tf2']
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS03 hist_data_save
@app.route('/AS03-histdatasave', methods=['POST'])
def getAS03histdatasave():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS03_hist_file_save(
        post_token_url,
        post_token_user_name,
        post_token_password,
        mete_data_service,
        _influxdb_input=influxdb_input,
        client_input=client_input,
        influxdb_action=influxdb_action,
        host_action=client_action,
        satID=data['satID'],
        tf1=data['tf1'],
        tf2=data['tf2']
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS03-delete-data-task
@app.route('/AS03-delete-data-task', methods=['POST'])
def get_AS03_delete_all_data_task():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS03_delete_data_task(
        post_token_url,
        post_token_user_name,
        post_token_password,
        mete_data_service,
        influxdb_action=influxdb_action,
        host_action=client_action,
        satID=data['satID'],
        tf1=data['tf1'],
        tf2=data['tf2']
    )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02 automatedtask
@app.route('/AS02-auto-task-with-duplicate-check', methods=['POST'])
def AS02_auto_task_with_duplicate_check_route():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS02_auto_task_with_duplicate_check(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url=mete_data_service,
        influxdb_input=influxdb_input,
        client_input=client_input,
        influxdb_action=influxdb_action,
        host_action=client_action,
        satIDs=data['satID'],
        date=data.get('date'),
        start=data.get('start'),
        end=data.get('end')
    )

    return Response(response=json.dumps(response),
                    status=200,
                    mimetype='application/json')


# AS03 automatedtask
@app.route('/AS03-auto-task-with-duplicate-check', methods=['POST'])
def AS03_auto_task_with_duplicate_check_route():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS03_auto_task_with_duplicate_check(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service=orbit_service,
        metedataservice_url=mete_data_service,
        influxdb_input=influxdb_input,
        client_input=client_input,
        influxdb_action=influxdb_action,
        host_action=client_action,
        satIDs=data['satID'],
        date=data.get('date'),
        start=data.get('start'),
        end=data.get('end')
    )

    return Response(response=json.dumps(response),
                    status=200,
                    mimetype='application/json')


# flight controller on duty
@app.route('/get-flight-controller', methods=['POST'])
def getflightcontroller():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = get_flight_controller(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service=orbit_service,
        satelliteIDs=data['satelliteIDs'],
        startAt=data['startAt'],
        endAt=data['endAt']
    )

    return Response(response=json.dumps(response),
                    status=200,
                    mimetype='application/json')


# flight controller on duty
@app.route('/space-environment-info-with-summary-from-odpa', methods=['POST'])
def spaceenvironmentinfowithsummaryfromodpa():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = space_environment_info_with_summary_from_odpa(
        odpa3_url=odpa3_url,
        tf1=data['start'],
        tf2=data['end']
    )

    return Response(response=json.dumps(response),
                    status=200,
                    mimetype='application/json')


# dailyreport_ai_summary
@app.route("/dailyreport-ai-summary", methods=["POST"])
def daily_report_ai_summary():
    data = request.get_json(force=True, silent=True) or {}

    # ---- 1. 基础校验 ----
    if "query" not in data or not data["query"].strip():
        return Response(
            json.dumps({"error": "query is required"}),
            status=400,
            mimetype="application/json",
        )

    query = data["query"].strip()

    # ---- 2. 组织 inputs ----
    #    DeepSeek-R1 的 payload 里 "inputs" 可以为空字典，也可以包含你希望注入的变量。
    inputs = {}
    if "satelliteIDs" in data:
        inputs["satelliteIDs"] = data["satelliteIDs"]

    # 如果你还有别的可选字段，也可以追加进去
    # if "some_other_key" in data:
    #     inputs["some_other_key"] = data["some_other_key"]

    # ---- 3. 调用 ask_dify ----
    try:
        answer = ask_dify(
            url=dsr1_url,  # 形如 http://172.16.8.191/v1/chat-messages
            api_key=dsr1_token,  # Bearer Token
            query=query,
            inputs=inputs or {},  # 保证至少是 {}
            user=data.get("user", "abc-123"),  # user 可省略
            streaming=False  # 如需流式改 True
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype="application/json",
        )

    # ---- 4. 返回结果 ----
    return Response(
        json.dumps({"answer": answer}),
        status=200,
        mimetype="application/json",
    )


@app.route('/index', methods=['GET'])
def index():
    print(f"-------------------service staring on {request.remote_addr}------------------")
    return render_template('index.html')


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7877))
    app.run(host='0.0.0.0', port=port, debug=True)
    # daily_report_spiderling(orbitservice_url='http://orbit-service-inf.prod.yhroot.com/graphql',
    #                         mete_data_service='http://mete-data-service.prod.yhroot.com/graphql',
    #                         influxdb_input=influxdb_input,
    #                         client_input=client_input,
    #                         influxdb_action=influxdb_action,
    #                         client_action=client_action,
    #                         influxdb_chronograf=influxdb_chronograf,
    #                         client_chronograf=client_chronograf,
    #                         satID='6,7',
    #                         date='2024-01-30',
    #                         start='',
    #                         end='')
    # satellite_properties('http://mete-data-service.prod.yhroot.com/graphql', satIDs='2')
    # od_tmcode('http://mete-data-service.prod.yhroot.com/graphql', satIDs='2')
    # gnss_get_last('http://mete-data-service.prod.yhroot.com/graphql',
    #               influxdb_input, client_input, satIDs='2')
    # ephemeris_acquire(metedataservice_url='http://mete-data-service.prod.yhroot.com/graphql',
    #     orbitserviceurl='http://orbit-service-inf.prod.yhroot.com/graphql',
    #               startAt="2024-03-25T15:06:59.000Z",
    #               endAt="2024-03-26T05:38:23.000Z",
    #               satIDs="4")
    # orbit_precision_calculation_step1(metedataservice_url='http://mete-data-service.prod.yhroot.com/graphql',
    #                                   orbitserviceurl='http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                   _influxdb=influxdb_input, client=client_input, satIDs="4")

    # orbit_precision_analysis_auto_task(metedataservice_url='http://mete-data-service.prod.yhroot.com/graphql',
    #                                    orbitserviceurl='http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                    orbit_prop_url=orbit_prop_url,
    #                                    _influxdb=influxdb_input, client=client_input, satID_list="6",
    #                                    mariadb=mariadbsetup,
    #                                    note_url=note_url,
    #                                    OSS2=OSS2)

    # satellite_status_data_auto_task('http://mete-data-service.prod.yhroot.com/graphql', influxdb_input, client_input,
    #                                 satIDs='13',
    #                                 date='2024-04-25', start='', end='')
    # OBCreset_influx('http://mete-data-service.prod.yhroot.com/graphql', influxdb_input, client_input, satID='3',
    #                 tf1='', tf2='')
    # write_reset_count('http://mete-data-service.prod.yhroot.com/graphql', influxdb_input, client_input, satID='4',
    #                   tf1='2024-05-06T00:00:00.000Z', tf2='2024-05-06T06:40:00.000Z')
    # write_switch_count('http://mete-data-service.prod.yhroot.com/graphql', influxdb_input, client_input, satID='4',
    #                   tf1='2024-05-06T00:00:00.000Z', tf2='2024-05-06T06:40:00.000Z')
    # check_repeating_records('http://mete-data-service.prod.yhroot.com/graphql', satID='4',
    #                   tf1='2024-05-06T00:00:00.000Z', tf2='2024-05-06T06:40:00.000Z')
    # OBCreset_mongo_records('http://mete-data-service.prod.yhroot.com/graphql', satID='4',
    #                        tf1='2024-04-24T12:05:16.000Z',
    #                        tf2='2024-04-24T23:07:23.000Z')
    # write_cumulative_data('http://mete-data-service.prod.yhroot.com/graphql', satID='4',
    #                       tf1='2024-04-24T10:00:16.000Z', tf2='2024-04-24T23:07:23.000Z')

    # calculate_cumulative_reset('http://mete-data-service.prod.yhroot.com/graphql', satID='4',
    #                            tf1='', tf2='',
    #                            note_url=note_url)
    # OBCswitch_data('http://mete-data-service.prod.yhroot.com/graphql', satID='3', tf1='', tf2='')
    # hist_interval('http://orbit-service-inf.prod.yhroot.com/graphql',
    #               'http://mete-data-service.prod.yhroot.com/graphql',
    #               influxdb_input, client_input,
    #               "2024-03-25T15:06:59.000Z",
    #               "2024-03-27T15:38:23.000Z",
    #               '6')
    # gnss_interval('http://orbit-service-inf.prod.yhroot.com/graphql',
    #               'http://mete-data-service.prod.yhroot.com/graphql',
    #               influxdb_input, client_input,
    #               "2024-03-28T00:06:59.000Z",
    #               "2024-03-28T03:38:23.000Z",
    #               '12')

    # results_dict = experimental_uplock('http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                    'http://mete-data-service.prod.yhroot.com/graphql',
    #                                    influxdb_input, client_input,
    #                                    "2024-03-22T04:39:30.000Z",
    #                                    "2024-03-22T07:11:51.000Z", '12')

    # results_dict = experimental_telemetry('http://orbit-service-inf.prod.yhroot.com/graphql',
    #                                       'http://mete-data-service.prod.yhroot.com/graphql',
    #                                       influxdb_input, client_input,
    #                                       "2024-03-22T04:39:30.000Z",
    #                                       "2024-03-22T07:11:51.000Z", '12')
    #
    # json.dumps(results_dict)

    # vcId(mete_data_service, influxdb_input, client_input, "2024-02-03T00:08:13.000Z", "2024-02-03T00:48:13.000Z",
    #      '7')

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
    # non_zero_switch = pd.DataFrame({
    #     '_satelliteCode': ['GS-2BP01', 'GS-2BP01', 'GS-2BP01', 'GS-2BP01'],
    #     'timestamp': [1703779096, 1703785330, 1703864766, 1703864816],
    #     'obc_switch': [0, 1],
    #     'obc_reset': [0, 0],
    #     'switch_detect': [1, 1],
    #     'reset_detect': [0, 0]
    # })
    # non_zero_record = pd.DataFrame({
    #     'eventid': ['GS-2BP011703779096', 'GS-2BP011703864766'],
    #     'time_found': [1703779096, 1703864766],
    #     'time_end': [1703785330, 1703864816],
    #     'reset_count': [1, 1]
    # })
    #
    # resettime_data = pd.DataFrame({
    #     '_satelliteCode': ['GS-2BP01', 'GS-2BP01', 'GS-2BP01', 'GS-2BP01', 'GS-2BP01'],
    #     'timestamp': [17061690219, 1706169020, 1706169025, 1706169026, 1706169027],
    #     'obc_switch': [1, 0, 0, 0, 0]
    # })
    #
    # resettime_data = pd.DataFrame({
    #     '_satelliteCode': ['GS-2BP01', 'GS-2BP01', 'GS-2BP01', 'GS-2BP01', 'GS-2BP01'],
    #     'timestamp': [17061690219, 1706169020, 1706169025, 1706169026, 1706169027],
    #     'obc_switch': [1, 0, 0, 0, 0],
    #     'switch_detect': [0, 1, 0, 0, 0]
    # })
    #
    # non_zero_switch = pd.DataFrame({
    #     '_satelliteCode': ['GS-2BP01'],
    #     'timestamp': [1706169020],
    #     'obc_switch': [0],
    #     'switch_detect': [1]
    # })
    #
    # concatenated_df = pd.DataFrame({
    #     '_id': ['6628a3c5ba2467df7e27cb29', '6628a3c5ba2467df7e27cb2a', '6628a3c5ba2467df7e27cb2b',
    #             '6628a3c5ba2467df7e27cb2c', '6628a3c5ba2467df7e27cb2d', '6628a3c5ba2467df7e27cb2e',
    #             '6628a3c5ba2467df7e27cb2f'],
    #     '_satelliteCode': ['AP02', 'AP02', 'AP02', 'AP02', 'AP02', 'AP02', 'AP02'],
    #     'eventid': ['GS-2AP021706168969', 'GS-2AP021706766499', 'GS-2AP021708223478',
    #                 'GS-2AP021708850805', 'GS-2AP021709686237',
    #                 'GS-2AP021706778233', 'GS-2AP021706778299'],
    #     'time_found': [1706168969, 1706766499, 1708223478, 1708850805, 1709686237, 1706778233, 1706778299],
    #     'reset_count': [1, 2, 1, 1, 1,0,0],
    #     'switch_count': [0, 0, 0, 0, 0,1,1],
    #     'reset': ['1', '1', '1', '1', '1', '0', '0'],
    #     'switch': ['0', '0', '0', '0', '0', '1', '1'],
    #     'cumulative_reset': ['0','0','0','0','0','0','0']
    # })
    # concatenated_df = pd.DataFrame({
    #     '_id': ['6628a3c5ba2467df7e27cb29', '6628a3c5ba2467df7e27cb2a', '6628a3c5ba2467df7e27cb2b',
    #             '6628a3c5ba2467df7e27cb2c', '6628a3c5ba2467df7e27cb2d'],
    #     '_satelliteCode': ['AP02', 'AP02', 'AP02', 'AP02', 'AP02'],
    #     'eventid': ['GS-2AP021706168969', 'GS-2AP021706766499', 'GS-2AP021708223478',
    #                 'GS-2AP021708850805', 'GS-2AP021709686237'],
    #     'time_found': [1706168969, 1706766499, 1708223478, 1708850805, 1709686237],
    #     'reset_count': [1, 2, 1, 1, 1],
    #     'switch_count': [0, 0, 0, 0, 0],
    #     'reset': ['1', '1', '1', '1', '1'],
    #     'switch': ['0', '0', '0', '0', '0'],
    #     'cumulative_reset': ['','','','','']
    # })

    # df = pd.DataFrame({
    #     'theoretical_x': [1279973.62608240009, 1106017.49535070010, 929334.75234759995],
    #     'theoretical_y': [5345947.77563359961, 5608584.46683130041, 5847791.48911049962],
    #     'theoretical_z': [-4080415.79589120019, -3764272.40594930016, -3431255.79982369998],
    #     'timestamp': [1715563538, 1715563598, 1715563658],
    #     'x': [1279970.12500000000, 1106013.87500000000, 929330.68750000000],
    #     'y': [5345957.00000000000, 5608592.00000000000, 5847798.00000000000],
    #     'z': [-4080393.00000000000, -3764249.00000000000, -3431231.75000000000],
    #     'x_diff': [3.50108240009, 3.62035070010, 4.06484759995],
    #     'y_diff': [-9.22436640039, -7.53316869959, -6.51088950038],
    #     'z_diff': [-22.79589120019, -23.40594930016, -23.40594930016],
    #     'theoretical_distance2': [6845968.38808263652, 6844650.55118188728, 6843525.75401437003],
    #     'actual_distance2': [6845961.34967109747, 6844643.26668362692, 6843518.70734209940],
    #     'error': [7.03841153905, 7.28449826036, 7.04667227063]
    # })

    # df = pd.DataFrame({
    #     'a': [6.892519e+06,  6.893181e+06],
    #     'e': ['AP02','AP02'],
    #     'i': [1.715074e+09,63.531165],
    #     'dw': [0.00689,123],
    #     'xw': [63.531853,456],
    #     'M': [153.703414,789],
    #     'CD': [344.437449,458],
    #     'epochTimeUTC': ['2024-03-26T02:05:17.000Z', '2024-03-25T15:40:16.000Z']
    #
    # })

    # df1 = pd.DataFrame({
    #     'theoretical_x': [6338734, 6339343, 6339941, 6362019],
    #     'theoretical_y': [2008452, 2011836, 2015210, 2206383],
    #     'theoretical_z': [1611161, 1604545, 1597928, 1210978],
    #     'error': [17.77391304190, 17.77391304190, 16.75567443387, 16.75567443387],
    #     'timestamp': [1715239589, 1715239590, 1715239591, 1715239649],
    # })
    #
    # TCS811_commands = pd.DataFrame({
    #     'satellite_code': ['LZA'],
    #     'antenna_code': ['1807'],
    #     'cmd_code': ['TCH209'],
    #     'isdelay': ['None'],
    #     'param': ['{"commandId":"clxb82aft2zp40y7kcnc03no0","delayForm":{"atsId":1,"cmdNumber":89,"seconds":"2024-06-12T10:01:00.000Z","isDelay":true},"packageForm":{"cmdCode":"TCH209","params":{"Index":0,"wFrequency":10000,"foldername":"202405","filename":"20240511.dat"}},"satelliteCode":"GS-LZA","satelliteId":"15","tcTmVersion":"ASvast01","frameSeqCount":64,"transferSequenceNumber":0,"frameType":"tc","test":false,"antennaId":"34","antennaCode":"TLG-1807","type":1,"retry":0,"checkUplinkLock":false,"sendInterval":2000}'],
    #     'timestamp': [1718159939]
    #
    # })
    #
    # targetdf = pd.DataFrame({
    #     'theoretical_x': ['-1712943.63087889994', '-1371636.22557260003'],
    #     'theoretical_y': ['-2596766.44749019993', '-2874099.16606240021'],
    #     'theoretical_z': ['6169234.26303370018', '6135249.92168310005'],
    #     'x': ['-1712951.87500000000', '-1371645.00000000000'],
    #     'y': ['-2596782.00000000000', '-2874115.00000000000'],
    #     'z': ['6169225.50000000000', '6135242.50000000000'],
    #     'timestamp': ['1720590030', '1720590090'],
    #     'x_diff': ['8.24412110006', '8.77442739997'],
    #     'y_diff': ['15.55250980007', '15.83393759979'],
    #     'z_diff': ['8.76303370018', '7.42168310005'],
    #     'theoretical_distance2': ['6909183.97913736384', '6912533.80123208649'],
    #     'actual_distance2': ['6909184.04382458609', '6912535.53864688985'],
    #     'error': ['17.60244567648', '18.10260081070']
    #
    # })

    # df1 = pd.DataFrame({
    #     '计划': ['状态监视', '下传GNSS'],
    #     '开始时间': ['2008452', '2206383'],
    #     '卫星代号': ['GS-2BP02', 'GS-2BP02'],
    #     '测站名称': ['喀纳斯-SX-7301-华路', '七台河-SX-7501-驭星'],
    #     '发令计数': ['11', '2'],
    #     '接受': ['11', '2'],
    #     '通信情况': ['', 'V数传'],
    #     '文件巡检': ['', '正常'],
    #     '复位切机': ['境外复位', ''],
    #     '轨控': ['', '1456777'],
    #     'company_name': ['华路', '驭星']
    # })
    #
    # df2 = pd.DataFrame({
    #     'subsystem': ['姿轨控驱动app', '功率驱动'],
    #     'count': ['7', '4'],
    # })
    #
    # df3 = pd.DataFrame({
    #     'eventLevel': ['CRITICAL', 'WARNING','INFO'],
    #     'count': ['3', '1','6'],
    # })
    # df4 = pd.DataFrame({
    #     'mse': ['12.2']
    # })
    #
    # df5 = pd.DataFrame({
    #     'alt': ['543']
    # })

    # print(df)
    #
    # if __name__ == "__main__":
    #     print(df.to_string())
    #
    # df = analyze_telemetry_intervals(df)
    # print(df)
    # df = pd.DataFrame({
    #     'time': ['0'],
    #     'phase': [0],
    #     '_satelliteCode': [satellitecode]
    # })

    # targetdf = pd.DataFrame({
    #     'timestamp': ['1715920162', '1715920164', '1715920167', '1715920169', '1715920176', '1715920179', '1715920184',
    #                   '1715920172'],
    #     'TMY002': ['0.0', '15.0', '15.0', '0.0', '0.0', '15.0', '15.0', '15.0'],
    #     'TMY017': ['15.55250980007', '16.83393759979', '17.83393759979', '15.83393666979', '15.833545979', '15.833923459979', '15.8339543979', '15.83979'],
    #     'TMY005': ['8.76303370018', '7.4235', '7.42140005', '7.1005', '7.425', '4.42168310005', '5.42168310005', '6.42168310005'],
    #     '_satelliteCode': ['AS03', 'AS03', 'AS03', 'AS03', 'AS03', 'AS03', 'AS03', 'AS03']
    # })

    # result_df = pd.DataFrame({
    #     'timestamp': ['1720838048', '1720838088', '1720876033', '1720876041'],
    #     'TMS043': ['4221', '4221', '7259', '7259'],
    #     '_satelliteCode': ['AS03', 'AS03', 'AS03', 'AS03']
    # })

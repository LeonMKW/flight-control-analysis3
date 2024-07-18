# -*- coding: UTF-8 -*-
import os
import sys
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
    publish_report_task
from task.flightcontrol_automation_tasks import flight_operation_data_auto_task
from task.satellitestatus_automation_tasks import satellite_status_data_auto_task

from task.od_automation_tasks import orbit_precision_analysis_auto_task
from utils.dailyreport_utils import get_fire_records, get_gateway_task
from task.ASsatellite_tasks import AS02_sensing_upload, AS02_payload_data_transmission, AS02_platform_data_transmission
import warnings

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
               app.config['OSS2_SECRET'])

# 查信关站任务
gateway_url = app.config['APPLICATION_TASK']
gateway_auth = app.config['APPLICATION_AUTHORIZATION']

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


@app.route('/downlink-stats-experiment', methods=['POST'])
def down_exp():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = downlink_statics_experiment(orbit_service, mete_data_service, influxdb_input, client_input,
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

    response = experimental_telemetry(orbit_service, mete_data_service, influxdb_input, client_input, data['start'],
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


# upgap
@app.route('/upgap-experiment', methods=['POST'])
def upgap():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = experimental_uplock(orbit_service, mete_data_service, influxdb_input, client_input, data['start'],
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

    response = uplink_statics_experiment(orbit_service, mete_data_service, influxdb_input, client_input,
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

    response = hist_interval(orbit_service, mete_data_service, influxdb_input, client_input, data['start'],
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

    response = gnss_interval(orbit_service, mete_data_service, influxdb_input, client_input, data['start'],
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
@app.route('/spiderlingfileinspection-stats', methods=['POST'])
def file_inspect():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = spiderling_file_inspection(orbit_service, mete_data_service, influxdb_input, client_input,
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

    response = spiderling_file_inspect_experiment(orbit_service, mete_data_service, influxdb_input, client_input,
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

    response = general_anomal(orbit_service, mete_data_service, influxdb_input, client_input,
                              data['start'], data['end'],
                              data['satID'])
    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# write to flight-operation-middle-data
@app.route('/flight-operation-middle-data', methods=['POST'])
def write_to_mongo_fod():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = flight_operation_data_auto_task(orbit_service,
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


# write to flight-operation-middle-data
@app.route('/satellite-status-auto-mission', methods=['POST'])
def satellite_OBC_status_calculate():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = satellite_status_data_auto_task(mete_data_service,
                                               influxdb_input,
                                               client_input,
                                               satIDs=data['satIDs'],
                                               date=data['date'],
                                               start=data['start'],
                                               end=data['end'],
                                               note_url=note_url
                                               )
    return jsonify(response), 200


# excute odpa task
@app.route('/odpa', methods=['POST'])
def odpa():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = orbit_precision_analysis_auto_task(metedataservice_url=mete_data_service,
                                                  orbitserviceurl=orbit_service,
                                                  _influxdb=influxdb_input, client=client_input,
                                                  mariadb=mariadbsetup,
                                                  note_url=note_url,
                                                  orbit_prop_url=orbit_prop_url,
                                                  OSS2=OSS2,
                                                  satID_list=data['satIDs']
                                                  )
    return jsonify(response), 200


# spiderling track_quality
@app.route('/trackquality', methods=['POST'])
def gettrackquality():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = tracking_quality(orbitservice_url=orbit_service,
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

    response = daily_reset_stats(metedataservice_url=mete_data_service,
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

    response = get_fire_records(orbit_maneuver_url=orbit_maneuver_url,
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

    response = get_gateway_task(app_url=gateway_url,
                                app_auth=gateway_auth,
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

    response = get_all_alerts(mete_data_service=mete_data_service,
                              satIDs=data['satID'],
                              date=data['date'],
                              start=data['start'],
                              end=data['end']
                              )

    return Response(response=response,
                    status=200,
                    mimetype='application/json')


# AS02 remote sensing task
@app.route('/AS02-upload-sensing-task', methods=['POST'])
def getallAS02uploadsensingtask():
    data = request.json
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')

    response = AS02_sensing_upload(
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

    response = AS02_payload_data_transmission(
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


@app.route('/publish-spiderlingdailyreport', methods=['POST'])
def upload_image():
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
    # df2 = pd.DataFrame({
    #     'x': ['6338737', '6362010', '6358572', '6362017'],
    #     'y': ['2008459', '2206380', '2394364', '2206382'],
    #     'z': ['1611162', '1210965', '805338', '1210970'],
    #     'timestamp': ['1715239589', '1715239645', '1715239709', '1715239649'],
    # })
    #
    # targetdf = pd.DataFrame({
    #     'theoretical_x': ['6338734', '6362019'],
    #     'theoretical_y': ['2008452', '2206383'],
    #     'theoretical_z': ['1611161', '1210978'],
    #     'x': ['6338737', '6362017'],
    #     'y': ['2008459', '2206382'],
    #     'z': ['1611162', '1210970'],
    #     'timestamp': ['1715239589', '1715239649'],
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

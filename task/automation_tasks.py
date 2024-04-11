import json
from flask import jsonify
from bson import ObjectId
import pytz
from datetime import datetime, timedelta
from task.algorithms import downlink_statics_experiment, experimental_telemetry, uplink_statics_experiment, \
    experimental_uplock, \
    hist_interval, gnss_interval, satcom, file_inspection, orbit_control
from utils import db


def flight_operation_data_auto_task(orbitservice_url,
                                    mete_data_service,
                                    influxdb_input,
                                    client_input,
                                    influxdb_action,
                                    client_action,
                                    satID,
                                    date,
                                    start,
                                    end,
                                    ):
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
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        if endDate > now_utc:
            endDate = now_utc

    timefilter1 = startDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
    timefilter2 = endDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"

    # Get data for 'down', 'up', 'downgap', and 'upgap'
    down = downlink_statics_experiment(orbitservice_url, mete_data_service, influxdb_input, client_input,
                                       timefilter1,
                                       timefilter2,
                                       satID)
    down = json.loads(down)

    up = uplink_statics_experiment(orbitservice_url, mete_data_service, influxdb_input, client_input,
                                   influxdb_action,
                                   client_action,
                                   timefilter1,
                                   timefilter2,
                                   satID)
    up = json.loads(up)

    downgap = experimental_telemetry(orbitservice_url, mete_data_service, influxdb_input, client_input,
                                     timefilter1,
                                     timefilter2,
                                     satID)
    downgap = json.loads(downgap)

    upgap = experimental_uplock(orbitservice_url, mete_data_service, influxdb_input, client_input,
                                timefilter1,
                                timefilter2,
                                satID)
    upgap = json.loads(upgap)

    hist_time = hist_interval(orbitservice_url, mete_data_service, influxdb_input, client_input,
                              timefilter1,
                              timefilter2,
                              satID)

    hist_time = json.loads(hist_time)

    gnss_time = gnss_interval(orbitservice_url, mete_data_service, influxdb_input, client_input,
                              timefilter1,
                              timefilter2,
                              satID)

    gnss_time = json.loads(gnss_time)

    # Initialize Mongo class and get MongoDB connection
    mongo_instance = db.get_mongo()

    # Initialize a list to store outputs
    outputs = []

    # Write 'down' data to MongoDB
    for mission in down["task_list"]:
        mission_id = mission["mission"]["mission_id"]
        result = mongo_instance.read_data(mission_id, 'downlink_statics_experiment')
        if not result:
            response = mongo_instance.write_flight_operation_data(mission["mission"], 'downlink_statics_experiment')

        else:
            response = mongo_instance.update_flight_operation_data(mission["mission"], 'downlink_statics_experiment',
                                                                   mission_id)

        outputs.append(response)

    # Write 'up' data to MongoDB
    for mission in up["task_list"]:
        mission_id = mission["mission"]["mission_id"]
        result = mongo_instance.read_data(mission_id, 'uplink_statics_experiment')
        if not result:
            response = mongo_instance.write_flight_operation_data(mission["mission"], 'uplink_statics_experiment')

        else:
            response = mongo_instance.update_flight_operation_data(mission["mission"], 'uplink_statics_experiment',
                                                                   mission_id)
        outputs.append(response)

    # Write 'downgap' data to MongoDB
    for mission in downgap["task_list"]:
        mission_id = mission["mission"]["mission_id"]
        result = mongo_instance.read_data(mission_id, 'experimental_telemetry')
        if not result:
            response = mongo_instance.write_flight_operation_data(mission["mission"], 'experimental_telemetry')
        else:
            response = mongo_instance.update_flight_operation_data(mission["mission"], 'experimental_telemetry',
                                                                   mission_id)
        outputs.append(response)

    # Write 'upgap' data to MongoDB
    for mission in upgap["task_list"]:
        mission_id = mission["mission"]["mission_id"]
        result = mongo_instance.read_data(mission_id, 'experimental_uplock')
        if not result:
            response = mongo_instance.write_flight_operation_data(mission["mission"], 'experimental_uplock')
        else:
            response = mongo_instance.update_flight_operation_data(mission["mission"], 'experimental_uplock',
                                                                   mission_id)
        outputs.append(response)

    # Write 'hist_time' data to MongoDB
    for mission in hist_time["task_list"]:
        mission_id = mission["mission"]["mission_id"]
        result = mongo_instance.read_data(mission_id, 'hist_interval')
        if not result:
            response = mongo_instance.write_flight_operation_data(mission["mission"], 'hist_interval')
        else:
            response = mongo_instance.update_flight_operation_data(mission["mission"], 'hist_interval',
                                                                   mission_id)
        outputs.append(response)

    # Write 'gnss_time' data to MongoDB
    for mission in gnss_time["task_list"]:
        mission_id = mission["mission"]["mission_id"]
        result = mongo_instance.read_data(mission_id, 'gnss_interval')
        if not result:
            response = mongo_instance.write_flight_operation_data(mission["mission"], 'gnss_interval')
        else:
            response = mongo_instance.update_flight_operation_data(mission["mission"], 'gnss_interval',
                                                                   mission_id)
        outputs.append(response)

    return outputs

import json
from flask import jsonify
from bson import ObjectId
import pytz
from datetime import datetime, timedelta
from task.ASsatellite_tasks import AS02_sensing_upload, AS02_payload_data_transmission, \
    AS02_platform_data_transmission, \
    AS02_hist_file_save, \
    silicon_battery_task, delete_platform_data_task, delete_payload_data_task, \
    AS03_sensing_upload, AS03_in_sight_sensing_task, AS03_payload_data_transmission, \
    AS03_platform_data_transmission, AS03_hist_file_save, AS03_delete_data_task, delete_platform_folder_task
from utils.flightcontrol_utils import get_task_list
from utils.db import get_mongo


def AS02_auto_task_with_duplicate_check(metedataservice_url,
                                        influxdb_input,
                                        client_input,
                                        influxdb_action, host_action, satIDs, date=None, start=None,
                                        end=None):
    if not start and not end and not date:
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        endDate = now_utc
        startDate = endDate - timedelta(hours=48)
    elif not start or not end:
        if not date:
            raise ValueError("Either both 'start' and 'end' or 'date' must be provided.")
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

    satID_mapping = {
        '13': '13_16',
        '16': '13_16',
        '12': '12_15',
        '15': '12_15'
    }

    satIDs = satIDs.split(",")

    outputs = []

    mongo_instance = get_mongo()

    for satID in satIDs:
        unified_satID = satID_mapping.get(satID, satID)

        # AS02_sensing_upload part
        response = AS02_sensing_upload(metedataservice_url, influxdb_action, host_action, timefilter1, timefilter2,
                                       satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF06' in record:
                composite_key = {
                    'command_time': record['TCKAF06']['timestamp'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['TCKAF06']['timestamp']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS02-upload-sensing-task')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS02-upload-sensing-task')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS02_payload_data_transmission part
        response = AS02_payload_data_transmission(metedataservice_url,
                                                  _influxdb_input=influxdb_input,
                                                  client_input=client_input,
                                                  influxdb_action=influxdb_action,
                                                  host_action=host_action,
                                                  tf1=timefilter1,
                                                  tf2=timefilter2,
                                                  satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF03' in record:
                composite_key = {
                    'command_time': record['TCKAF03']['timestamp'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['TCKAF03']['timestamp']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS02-payload-data-transmission')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS02-payload-data-transmission')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS02_platform_data_transmission part
        response = AS02_platform_data_transmission(metedataservice_url,
                                                   _influxdb_input=influxdb_input,
                                                   client_input=client_input,
                                                   influxdb_action=influxdb_action,
                                                   host_action=host_action,
                                                   tf1=timefilter1,
                                                   tf2=timefilter2,
                                                   satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF03' in record:
                composite_key = {
                    'command_time': record['TCKAF03']['timestamp'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['TCKAF03']['timestamp']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS02-platform-data-transmission')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS02-platform-data-transmission')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS02-histdatasave
        response = AS02_hist_file_save(metedataservice_url,
                                       _influxdb_input=influxdb_input,
                                       client_input=client_input,
                                       influxdb_action=influxdb_action,
                                       host_action=host_action,
                                       tf1=timefilter1,
                                       tf2=timefilter2,
                                       satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'hist_data_saving_time' in record:
                composite_key = {
                    'command_time': record['hist_data_saving_time'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['hist_data_saving_time']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS02-histdatasave')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS02-histdatasave')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS02-silicon-battery
        response = silicon_battery_task(metedataservice_url,
                                        influxdb_action=influxdb_action,
                                        host_action=host_action,
                                        tf1=timefilter1,
                                        tf2=timefilter2,
                                        satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_sent_time' in record:
                composite_key = {
                    'command_time': record['command_sent_time'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['command_sent_time']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS02-silicon-battery')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS02-silicon-battery')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS02-delete-platform-task
        response = delete_platform_data_task(metedataservice_url,
                                             influxdb_action=influxdb_action,
                                             host_action=host_action,
                                             tf1=timefilter1,
                                             tf2=timefilter2,
                                             satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_time' in record:
                composite_key = {
                    'command_time': record['command_time'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['command_time']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS02-delete-platform-task')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS02-delete-platform-task')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS02-delete-platform-FOLDER-task
        response = delete_platform_folder_task(metedataservice_url,
                                               influxdb_action=influxdb_action,
                                               host_action=host_action,
                                               tf1=timefilter1,
                                               tf2=timefilter2,
                                               satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_time' in record:
                composite_key = {
                    'command_time': record['command_time'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['command_time']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS02-delete-platformfolder-task')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS02-delete-platformfolder-task')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS02-delete-payload-task
        response = delete_payload_data_task(metedataservice_url,
                                            influxdb_action=influxdb_action,
                                            host_action=host_action,
                                            tf1=timefilter1,
                                            tf2=timefilter2,
                                            satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_time' in record:
                composite_key = {
                    'command_time': record['command_time'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['command_time']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS02-delete-payload-task')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS02-delete-payload-task')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

    return outputs


def AS03_auto_task_with_duplicate_check(orbit_service, metedataservice_url, influxdb_input, client_input,
                                        influxdb_action, host_action, satIDs, date=None, start=None, end=None):
    if not start and not end and not date:
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        endDate = now_utc
        startDate = endDate - timedelta(hours=48)
    elif not start or not end:
        if not date:
            raise ValueError("Either both 'start' and 'end' or 'date' must be provided.")
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

    satID_mapping = {
        '13': '13_16',
        '16': '13_16',
        '12': '12_15',
        '15': '12_15'
    }

    satIDs = satIDs.split(",")

    outputs = []

    mongo_instance = get_mongo()

    for satID in satIDs:
        unified_satID = satID_mapping.get(satID, satID)

        # AS03-upload-sensing-task part
        response = AS03_sensing_upload(metedataservice_url, influxdb_action, host_action, timefilter1, timefilter2,
                                       satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF15' in record:
                composite_key = {
                    'command_time': record['TCKAF15']['timestamp'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['TCKAF15']['timestamp']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS03-upload-sensing-task')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS03-upload-sensing-task')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS03-insight-sensing-task part
        response = AS03_in_sight_sensing_task(orbit_service=orbit_service, metedataservice_url=metedataservice_url,
                                              _influxdb=influxdb_input, client=client_input,
                                              tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for key, value in payload_data.get("InfaredSensing", {}).items():
            probeon_data = value.get("probeon(探测器上电时间)")
            if probeon_data:
                first_probeon_key = next(iter(probeon_data.keys()))
                starttimestamp = probeon_data[first_probeon_key].get("starttimestamp")
                if starttimestamp:
                    composite_key = {
                        'command_time': starttimestamp,
                        'satID': unified_satID
                    }

                    # Add the composite key to the record
                    value['command_time'] = starttimestamp
                    value['satID'] = unified_satID

                    existing_record = mongo_instance.read_AS_data(composite_key, 'AS03-insight-sensing-task')
                    if not existing_record:
                        result = mongo_instance.write_AS_data(value, 'AS03-insight-sensing-task')
                        response = {'inserted_id': str(result.inserted_id)}
                    else:
                        response = {
                            'matched_count': 1,
                            'modified_count': 0
                        }

                    outputs.append(response)

        # AS03-payload-data-transmission
        response = AS03_payload_data_transmission(metedataservice_url=metedataservice_url,
                                                  _influxdb_input=influxdb_input,
                                                  client_input=client_input,
                                                  influxdb_action=influxdb_action,
                                                  host_action=host_action,
                                                  tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF03' in record:
                composite_key = {
                    'command_time': record['TCKAF03']['timestamp'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['TCKAF03']['timestamp']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS03-payload-data-transmission')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS03-payload-data-transmission')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS03-platform-data-transmission
        response = AS03_platform_data_transmission(metedataservice_url=metedataservice_url,
                                                   _influxdb_input=influxdb_input,
                                                   client_input=client_input,
                                                   influxdb_action=influxdb_action,
                                                   host_action=host_action,
                                                   tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF03' in record:
                composite_key = {
                    'command_time': record['TCKAF03']['timestamp'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['TCKAF03']['timestamp']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS03-platform-data-transmission')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS03-platform-data-transmission')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS03-histdatasave
        response = AS03_hist_file_save(metedataservice_url=metedataservice_url,
                                       _influxdb_input=influxdb_input,
                                       client_input=client_input,
                                       influxdb_action=influxdb_action,
                                       host_action=host_action,
                                       tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'hist_data_saving_time' in record:
                composite_key = {
                    'command_time': record['hist_data_saving_time'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['hist_data_saving_time']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS03-histdatasave')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS03-histdatasave')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

        # AS03-delete-data-task
        response = AS03_delete_data_task(metedataservice_url=metedataservice_url,
                                         influxdb_action=influxdb_action,
                                         host_action=host_action,
                                         tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_time' in record:
                composite_key = {
                    'command_time': record['command_time'],
                    'satID': unified_satID
                }

                # Add the composite key to the record
                record['command_time'] = record['command_time']
                record['satID'] = unified_satID

                existing_record = mongo_instance.read_AS_data(composite_key, 'AS03-delete-data-task')
                if not existing_record:
                    result = mongo_instance.write_AS_data(record, 'AS03-delete-data-task')
                    response = {'inserted_id': str(result.inserted_id)}
                else:
                    response = {
                        'matched_count': 1,
                        'modified_count': 0
                    }

                outputs.append(response)

    return outputs

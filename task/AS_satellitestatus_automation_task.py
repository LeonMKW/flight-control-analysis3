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
    AS03_platform_data_transmission, AS03_hist_file_save, AS03_delete_data_task, delete_platform_folder_task, \
    AS03_out_sight_sensing_task
from utils.flightcontrol_utils import get_task_list
from utils.db import get_mongo
import hashlib


def AS02_auto_task_with_duplicate_check(post_token_url,
                                        post_token_user_name,
                                        post_token_password, metedataservice_url,
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
        response = AS02_sensing_upload(post_token_url,
                                       post_token_user_name,
                                       post_token_password, metedataservice_url, influxdb_action, host_action,
                                       timefilter1, timefilter2,
                                       satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF06' in record:
                command_time = record['TCKAF06']['timestamp']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS02-upload-sensing-task')
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS02_payload_data_transmission part
        response = AS02_payload_data_transmission(post_token_url,
                                                  post_token_user_name,
                                                  post_token_password, metedataservice_url,
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
                command_time = record['TCKAF03']['timestamp']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS02-payload-data-transmission')
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS02_platform_data_transmission part
        response = AS02_platform_data_transmission(post_token_url,
                                                   post_token_user_name,
                                                   post_token_password, metedataservice_url,
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
                command_time = record['TCKAF03']['timestamp']
                start_value = (record.get('TCKAF03', {}).get('params', {}) or {}).get('start')  # 可能是 None

                # 推荐 1：start 优先做唯一键（同一个“计划开始”视为同一任务）
                # 如果你更保守，可用“start + timestamp”一起做键
                key_sat = unified_satID
                key_start = str(start_value) if start_value is not None else "NA"
                key_ctime = str(int(command_time)) if isinstance(command_time, (int, float)) else "NA"

                # 方案 A（更合并）：唯一键 = sat + start
                composite_key_str = f"{key_sat}|{key_start}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID
                record['scheduled_start'] = start_value  # 强烈建议额外落库，查询更方便

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS02-payload-data-transmission')
                outputs.append({
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                })

                outputs.append(response)

        # AS02-histdatasave
        response = AS02_hist_file_save(post_token_url,
                                       post_token_user_name,
                                       post_token_password, metedataservice_url,
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
                command_time = record['hist_data_saving_time']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS02-histdatasave')
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS02-silicon-battery
        response = silicon_battery_task(post_token_url,
                                        post_token_user_name,
                                        post_token_password, metedataservice_url,
                                        influxdb_action=influxdb_action,
                                        host_action=host_action,
                                        tf1=timefilter1,
                                        tf2=timefilter2,
                                        satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_sent_time' in record:
                command_time = record['command_sent_time']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS02-silicon-battery')
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS02-delete-platform-task
        response = delete_platform_data_task(post_token_url,
                                             post_token_user_name,
                                             post_token_password, metedataservice_url,
                                             influxdb_action=influxdb_action,
                                             host_action=host_action,
                                             tf1=timefilter1,
                                             tf2=timefilter2,
                                             satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_time' in record:
                command_time = record['command_time']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS02-delete-platform-task')
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS02-delete-platform-FOLDER-task
        response = delete_platform_folder_task(post_token_url,
                                               post_token_user_name,
                                               post_token_password, metedataservice_url,
                                               influxdb_action=influxdb_action,
                                               host_action=host_action,
                                               tf1=timefilter1,
                                               tf2=timefilter2,
                                               satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_time' in record:
                command_time = record['command_time']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS02-delete-platformfolder-task')
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS02-delete-payload-task
        response = delete_payload_data_task(post_token_url,
                                            post_token_user_name,
                                            post_token_password, metedataservice_url,
                                            influxdb_action=influxdb_action,
                                            host_action=host_action,
                                            tf1=timefilter1,
                                            tf2=timefilter2,
                                            satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_time' in record:
                command_time = record['command_time']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS02-delete-payload-task')
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

    return outputs


def AS03_auto_task_with_duplicate_check(post_token_url,
                                        post_token_user_name,
                                        post_token_password, orbit_service, metedataservice_url, influxdb_input,
                                        client_input,
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
        response = AS03_sensing_upload(post_token_url,
                                       post_token_user_name,
                                       post_token_password, metedataservice_url, influxdb_action, host_action,
                                       timefilter1, timefilter2,
                                       satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF15' in record:
                command_time = record['TCKAF15']['timestamp']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS03-upload-sensing-task')

                # Prepare the response
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }
                outputs.append(response)

        # AS03-insight-sensing-task part
        response = AS03_in_sight_sensing_task(post_token_url,
                                              post_token_user_name,
                                              post_token_password, orbit_service=orbit_service,
                                              metedataservice_url=metedataservice_url,
                                              _influxdb=influxdb_input, client=client_input,
                                              tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for key, value in payload_data.get("InfaredSensing", {}).items():
            probeon_data = value.get("probeon(探测器上电时间)")
            if probeon_data:
                first_probeon_key = next(iter(probeon_data.keys()))
                starttimestamp = probeon_data[first_probeon_key].get("starttimestamp")
                if starttimestamp:
                    # Create a unique _id from the composite key
                    composite_key_str = f"{starttimestamp}_{unified_satID}"
                    unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                    # Add the _id and composite key to the record
                    value['_id'] = unique_id
                    value['command_time'] = starttimestamp
                    value['satID'] = unified_satID

                    # Replace or insert the record using _id
                    result = mongo_instance.replace_AS_data({'_id': unique_id}, value, 'AS03-insight-sensing-task')

                    # Prepare the response
                    response = {
                        'matched_count': result.matched_count,
                        'modified_count': result.modified_count,
                        'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                        '_id': unique_id
                    }

                    outputs.append(response)

        # AS03-outsight-sensing-task part
        response = AS03_out_sight_sensing_task(post_token_url,
                                               post_token_user_name,
                                               post_token_password,
                                               orbit_service=orbit_service,
                                               metedataservice_url=metedataservice_url,
                                               _influxdb=influxdb_input,
                                               client=client_input,
                                               influxdb_action=influxdb_action,
                                               host_action=host_action,
                                               tf1=timefilter1,
                                               tf2=timefilter2,
                                               satID=satID
                                               )
        payload_data = json.loads(response)

        for task_key, task_value in payload_data.get("InfaredSensing", {}).items():
            upload_task = task_value.get("upload_task")

            if upload_task and upload_task.get('start'):
                key_timestamp = upload_task['start']

                # Create a unique _id from the composite key
                composite_key_str = f"{key_timestamp}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                task_value['_id'] = unique_id
                task_value['start'] = key_timestamp
                task_value['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, task_value, 'AS03-outsight-sensing-task')

                # Prepare the response
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }
                outputs.append(response)

        # AS03-payload-data-transmission
        response = AS03_payload_data_transmission(post_token_url,
                                                  post_token_user_name,
                                                  post_token_password, metedataservice_url=metedataservice_url,
                                                  _influxdb_input=influxdb_input,
                                                  client_input=client_input,
                                                  influxdb_action=influxdb_action,
                                                  host_action=host_action,
                                                  tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF03' in record:
                command_time = record['TCKAF03']['timestamp']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS03-payload-data-transmission')

                # Prepare the response
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS03-platform-data-transmission
        response = AS03_platform_data_transmission(post_token_url,
                                                   post_token_user_name,
                                                   post_token_password, metedataservice_url=metedataservice_url,
                                                   _influxdb_input=influxdb_input,
                                                   client_input=client_input,
                                                   influxdb_action=influxdb_action,
                                                   host_action=host_action,
                                                   tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'TCKAF03' in record:
                command_time = record['TCKAF03']['timestamp']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS03-platform-data-transmission')

                # Prepare the response
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS03-histdatasave
        response = AS03_hist_file_save(post_token_url,
                                       post_token_user_name,
                                       post_token_password, metedataservice_url=metedataservice_url,
                                       _influxdb_input=influxdb_input,
                                       client_input=client_input,
                                       influxdb_action=influxdb_action,
                                       host_action=host_action,
                                       tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'hist_data_saving_time' in record:
                command_time = record['hist_data_saving_time']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS03-histdatasave')

                # Prepare the response
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

        # AS03-delete-data-task
        response = AS03_delete_data_task(post_token_url,
                                         post_token_user_name,
                                         post_token_password, metedataservice_url=metedataservice_url,
                                         influxdb_action=influxdb_action,
                                         host_action=host_action,
                                         tf1=timefilter1, tf2=timefilter2, satID=satID)
        payload_data = json.loads(response)

        for record in payload_data:
            if 'command_time' in record:
                command_time = record['command_time']

                # Create a unique _id from the composite key
                composite_key_str = f"{command_time}_{unified_satID}"
                unique_id = hashlib.md5(composite_key_str.encode('utf-8')).hexdigest()

                # Add the _id and composite key to the record
                record['_id'] = unique_id
                record['command_time'] = command_time
                record['satID'] = unified_satID

                # Replace or insert the record using _id
                result = mongo_instance.replace_AS_data({'_id': unique_id}, record, 'AS03-delete-data-task')

                # Prepare the response
                response = {
                    'matched_count': result.matched_count,
                    'modified_count': result.modified_count,
                    'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                    '_id': unique_id
                }

                outputs.append(response)

    return outputs

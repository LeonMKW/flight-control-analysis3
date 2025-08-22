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

        # 取 payload & platform 结果
        payload_json = AS02_payload_data_transmission(post_token_url,
                                                      post_token_user_name,
                                                      post_token_password, metedataservice_url,
                                                      _influxdb_input=influxdb_input,
                                                      client_input=client_input,
                                                      influxdb_action=influxdb_action,
                                                      host_action=host_action,
                                                      tf1=timefilter1,
                                                      tf2=timefilter2,
                                                      satID=satID)
        payload_list = json.loads(payload_json)

        platform_json = AS02_platform_data_transmission(post_token_url,
                                                        post_token_user_name,
                                                        post_token_password, metedataservice_url,
                                                        _influxdb_input=influxdb_input,
                                                        client_input=client_input,
                                                        influxdb_action=influxdb_action,
                                                        host_action=host_action,
                                                        tf1=timefilter1,
                                                        tf2=timefilter2,
                                                        satID=satID)
        platform_list = json.loads(platform_json)

        # ---- 工具：取 scheduled_start、判定是否占位 ----
        def _extract_start_and_placeholder_from_payload(rec):
            start_val = (rec.get('TCKAF03', {}).get('params', {}) or {}).get('start')
            tcs = rec.get('TCS804', []) or []
            is_placeholder = (len(tcs) == 1 and
                              (tcs[0].get('File1') == 0 and tcs[0].get('File2') == 0))
            return start_val, is_placeholder

        def _extract_start_and_placeholder_from_platform(rec):
            start_val = (rec.get('TCKAF03', {}).get('params', {}) or {}).get('start')
            tcs = rec.get('TCS813', []) or []
            is_placeholder = (len(tcs) == 1 and (tcs[0].get('FileNum') == 0))
            return start_val, is_placeholder

        # mission_uid 生成（跨集合统一，便于关联合并）
        def _mission_uid(unified_satID, start_val):
            return hashlib.md5(f"{unified_satID}|{start_val}".encode("utf-8")).hexdigest()

        # 各集合 _id 命名空间（避免肉眼混淆）
        def _payload_id(unified_satID, start_val):
            return hashlib.md5(f"payload|{unified_satID}|{start_val}".encode("utf-8")).hexdigest()

        def _platform_id(unified_satID, start_val):
            return hashlib.md5(f"platform|{unified_satID}|{start_val}".encode("utf-8")).hexdigest()

        # 先按 mission（start）归并
        payload_by_start = {}
        for rec in payload_list:
            if 'TCKAF03' not in rec:
                continue
            start_val, is_ph = _extract_start_and_placeholder_from_payload(rec)
            payload_by_start[start_val] = {'rec': rec, 'is_placeholder': is_ph}

        platform_by_start = {}
        for rec in platform_list:
            if 'TCKAF03' not in rec:
                continue
            start_val, is_ph = _extract_start_and_placeholder_from_platform(rec)
            platform_by_start[start_val] = {'rec': rec, 'is_placeholder': is_ph}

        # 合并所有 mission 键
        all_starts = set(payload_by_start.keys()) | set(platform_by_start.keys())

        for start_val in all_starts:
            p = payload_by_start.get(start_val)
            q = platform_by_start.get(start_val)

            # 判定是否需要“压制占位写入”（另一侧已有真实数据）
            suppress_payload_placeholder = bool(p and p['is_placeholder'] and q and not q['is_placeholder'])
            suppress_platform_placeholder = bool(q and q['is_placeholder'] and p and not p['is_placeholder'])

            # ---- 写 payload 集合 ----
            if p and (not suppress_payload_placeholder):
                rec = p['rec']
                command_time = rec['TCKAF03']['timestamp']
                mission_uid = _mission_uid(unified_satID, start_val)
                unique_id = _payload_id(unified_satID, start_val)

                rec['_id'] = unique_id
                rec['mission_uid'] = mission_uid
                rec['task_type'] = 'payload'
                rec['scheduled_start'] = start_val
                rec['command_time'] = command_time
                rec['satID'] = unified_satID
                rec['is_placeholder'] = p['is_placeholder']  # 可选：落库标识

                wr = mongo_instance.replace_AS_data({'_id': unique_id}, rec, 'AS02-payload-data-transmission')
                outputs.append({'matched_count': wr.matched_count, 'modified_count': wr.modified_count,
                                'upserted_id': str(wr.upserted_id) if wr.upserted_id else None, '_id': unique_id})

            # ---- 写 platform 集合 ----
            if q and (not suppress_platform_placeholder):
                rec = q['rec']
                command_time = rec['TCKAF03']['timestamp']
                mission_uid = _mission_uid(unified_satID, start_val)
                unique_id = _platform_id(unified_satID, start_val)

                rec['_id'] = unique_id
                rec['mission_uid'] = mission_uid
                rec['task_type'] = 'platform'
                rec['scheduled_start'] = start_val
                rec['command_time'] = command_time
                rec['satID'] = unified_satID
                rec['is_placeholder'] = q['is_placeholder']  # 可选：落库标识

                wr = mongo_instance.replace_AS_data({'_id': unique_id}, rec, 'AS02-platform-data-transmission')
                outputs.append({'matched_count': wr.matched_count, 'modified_count': wr.modified_count,
                                'upserted_id': str(wr.upserted_id) if wr.upserted_id else None, '_id': unique_id})

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

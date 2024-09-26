# -*- coding: UTF-8 -*-

import pymongo
from influxdb import InfluxDBClient
import logging
from bson import ObjectId
import logging
import mariadb
import sys
import oss2
import pandas as pd
import json


class Influxdb(object):
    """
    influxdb数据库操作
    """

    def __init__(self, _user, _pwd, _dbname):
        self._user = _user
        self._pwd = _pwd
        self._dbname = _dbname

    def connect(self, _host, _port):
        client = InfluxDBClient(_host, _port, self._user, self._pwd, self._dbname)
        return client

    def get_all(self, _client, measurement, fields, filters=None, limit=1000000):
        query_str = 'select _satelliteCode,' + ','.join([x for x in fields]) \
                    + ' from \"' + measurement + '\" ' + filters \
                    + ' limit ' + str(limit)
        # print(query_str)
        result = _client.query(query_str)
        if len(result) == 0:
            return {}
        points = list(result.get_points())
        return points

    def get_distinct_alt(self, _client, start_time, end_time, satellitecode, limit=1):
        # Query to get data within the time range
        query_str = f'SELECT "alt", "_satelliteCode" FROM "alt" WHERE "_satelliteCode" = \'{satellitecode}\' AND time >= \'{start_time}\' AND time <= \'{end_time}\' ORDER BY time DESC LIMIT {limit}'
        result = _client.query(query_str)

        points = list(result.get_points())

        # If no data found within the range, get the closest available data before the start time
        if len(points) == 0:
            nearest_query = f'SELECT "alt", "_satelliteCode" FROM "alt" WHERE "_satelliteCode" = \'{satellitecode}\' AND time < \'{start_time}\' ORDER BY time DESC LIMIT 1'
            result = _client.query(nearest_query)
            points = list(result.get_points())

        return points

    def get_distinct_phase(self, _client, filters=None, limit=1000000):
        query_str = 'select \"phase\", _satelliteCode from \"phase\" ' + filters \
                    + 'ORDER BY time DESC' + ' limit ' + str(limit)
        result = _client.query(query_str)
        if len(result) == 0:
            return {}
        # print(query_str)
        points = list(result.get_points())
        return points

    def get_distinct_phase_diff(self, _client, filters=None, limit=1):
        query_str = 'select \"phase_diff\", _satelliteCode from \"phase_diff\" ' + filters \
                    + 'ORDER BY time DESC' + ' limit ' + str(limit)
        result = _client.query(query_str)
        if len(result) == 0:
            return {}
        # print(query_str)
        points = list(result.get_points())
        return points

    def get_all_monitors(self, _client, measurement, fields, filters=None, limit=100000):
        query_str = 'select satelliteCode,' + ','.join([x for x in fields]) \
                    + ' from \"' + measurement + '\" ' + filters \
                    + ' limit ' + str(limit)
        result = _client.query(query_str)
        if len(result) == 0:
            return {}
        points = list(result.get_points())
        return points

    def get_command(self, _client, fields, filters=None, limit=1000000):
        query_str = 'select satellite_code,' + ','.join([x for x in fields]) \
                    + ' FROM tcSendRecord ' + filters \
                    + ' limit ' + str(limit)
        # print(query_str)
        result = _client.query(query_str)
        if len(result) == 0:
            return {}
        points = list(result.get_points())
        return points


def check_str_is_cn(str_all):
    """检查字符串中是否有中文字符"""
    for s in str_all:
        if '\u4e00' <= s <= '\u9fa5':
            return True
    return False


def init_val():
    global progress
    progress = {'progress': 0, 'total': 0}


def pbar():
    global progress
    progress = {}
    return progress


def set_value(key, value):
    # global progress
    progress[key] = value


# mongo = None


def get_mongo():
    return mongo


class Mongo(object):

    def __init__(self, hosts, _mongo_auth_source, _mongo_initdb_root_usename, _mongo_initdb_root_password):
        self._MONGO_HOSTS = hosts
        self._MONGO_AUTH_SOURCE = _mongo_auth_source
        self._MONGO_INITDB_ROOT_USERNAME = _mongo_initdb_root_usename
        self._MONGO_INITDB_ROOT_PASSWORD = _mongo_initdb_root_password
        self.client = pymongo.MongoClient(
            host=self._MONGO_HOSTS,
            serverSelectionTimeoutMS=3000,  # 3 second timeout
            authSource=str(self._MONGO_AUTH_SOURCE),
            username=str(self._MONGO_INITDB_ROOT_USERNAME),
            password=str(self._MONGO_INITDB_ROOT_PASSWORD)
        )
        global mongo
        mongo = self

    def get_connection(self):
        return self.client

    # READ
    def read_data(self, mission_id, collection):
        result = self.client['flight-control-middle-data'][str(collection)].find_one({'mission_id': mission_id})
        return result

    def read_AS_data(self, query, collection):
        result = self.client['flight-control-middle-data'][str(collection)].find_one(query)
        return result

    def read_OBCrecord_data(self, eventid, collection):
        result = self.client['flight-control-middle-data'][str(collection)].find_one({'eventid': eventid})
        return result

    def get_lastone_data(self, collection, query):
        result = self.client['flight-control-middle-data'][str(collection)].find_one(query, sort=[('time_found',
                                                                                                   pymongo.DESCENDING)])
        return result

    def get_all_data(self, collection, query):
        result = self.client['flight-control-middle-data'][str(collection)].find(query)
        return result

    def get_nearest_data(self, collection, query):
        result = self.client['flight-control-middle-data'][str(collection)].find_one(query, sort=[('time_found',
                                                                                                   pymongo.DESCENDING)])
        return result

    def get_cum_reset_data(self, collection):
        result = self.client['flight-control-middle-data'][str(collection)].find_one(sort=[('time_found',
                                                                                            pymongo.DESCENDING)])
        return result

    def read_alert_data(self, tf1, tf2, satelliteCode):
        pipeline = [
            {
                "$sort": {
                    "createTime": -1
                }
            },
            {
                "$lookup": {
                    "from": "notice_config",
                    "localField": "noticeCode",
                    "foreignField": "noticeCode",
                    "as": "noticeConfig"
                }
            },
            {
                "$match": {
                    "createTime": {
                        "$gte": int(tf1),
                        "$lte": int(tf2)
                    },
                    "systemId": "61",
                    "params.eventObjectName": str(satelliteCode),
                    "noticeConfig.channelType": "dingtalk_robot",
                    "params.eventCode": {"$regex": "TCTM"}
                }
            },
            {
                "$project": {
                    "params": 1
                }
            }
        ]

        # Execute the aggregation pipeline
        result = self.client["ttnonc-notice"]["notice_record"].aggregate(pipeline)

        return result

    def read_alert_data_end_status(self, eventLogId):
        pipeline = [
            {
                "$sort": {
                    "createTime": -1
                }
            },
            {
                "$match": {
                    "startEventLogId": eventLogId,
                }
            },
            {
                "$project": {
                    "startEventLogId": 1,
                    "isEnd": 1
                }
            }
        ]

        # Execute the aggregation pipeline
        result = self.client["ttnonc-event"]["event_status"].aggregate(pipeline)

        return list(result)

    def read_tracking_quality_data(self, collection_name, mission_ids):
        collection = self.client['flight-control-middle-data'][str(collection_name)]

        # Ensure mission_ids is a list of strings or integers
        if not isinstance(mission_ids, list):
            logging.error("mission_ids must be a list of strings or integers.")
            raise ValueError("mission_ids must be a list of strings or integers.")

        query = {"mission_id": {"$in": mission_ids}}
        documents = collection.find(query)

        # Convert to list and return
        doc = list(documents)
        # logging.info(f"Found {len(doc)} documents for mission_ids: {mission_ids}")
        return doc

    def get_doc_by_satid_tf(self, collection, satcode, ts1, ts2):
        query = {
            "_satelliteCode": satcode,
            "time_end": {
                "$gte": ts1,
                "$lte": ts2
            }
        }
        response = self.client['flight-control-middle-data'][collection].find(query)
        return response

    def get_largest_end_time_doc(self, collection, satcode):
        query = {
            "_satelliteCode": satcode
        }
        response = self.client['flight-control-middle-data'][collection].find(query).sort("time_end", -1).limit(1)
        return response

    def get_doc_closest_but_not_greater(self, collection, satcode, target_ts):
        query = {
            "_satelliteCode": satcode,
            "time_end": {
                "$lt": target_ts
            }
        }
        response = self.client['flight-control-middle-data'][collection].find(query).sort("time_end", -1).limit(1)
        return response

    # CREATE
    def write_flight_operation_data(self, content, collection):
        # logging.info(print('writing flight_operation to Mongo...'))

        response = self.client['flight-control-middle-data'][str(collection)].insert_one(content)
        output = {'type': 'Insert',
                  'Document_ID': str(ObjectId(response.inserted_id))}
        return output

    # WRITE
    def write_AS_data(self, data, collection):
        result = self.client['flight-control-middle-data'][str(collection)].insert_one(data)
        return result

    # UPDATE
    def update_AS_data(self, data, collection, composite_key):
        result = self.client['flight-control-middle-data'][str(collection)].update_one(composite_key, {"$set": data}, upsert=True)
        return result

    def replace_AS_data(self, filter_dict, data, collection):
        collection = self.client['flight-control-middle-data'][str(collection)]
        result = collection.replace_one(filter_dict, data, upsert=True)
        return result

    # UPDATE
    def update_flight_operation_data(self, content, collection, mission_id):
        # logging.info('updating flight_operation to Mongo...')
        filter_query = {'mission_id': mission_id}
        response = self.client['flight-control-middle-data'][str(collection)].update_one(filter_query,
                                                                                         {'$set': content})
        output = {'type': 'Update',
                  'Document_ID': str(ObjectId(response.upserted_id))}

        return output

    def update_flight_operation_satellite_data(self, content, collection, eventid):
        # logging.info('updating flight_operation to Mongo...')
        filter_query = {'eventid': eventid}
        response = self.client['flight-control-middle-data'][str(collection)].update_one(filter_query,
                                                                                         {'$set': content})
        output = {'type': 'Update',
                  'Document_ID': str(ObjectId(response.upserted_id))}

        return output

    # def update_cumulative_data(self, collection, query, content):
    #     # logging.info('updating flight_operation to Mongo...')
    #     response = self.client['flight-control-middle-data'][str(collection)].update_one(query, content)
    #     output = {'type': 'Update',
    #               'Document_ID': str(ObjectId(response.upserted_id))}
    #
    #     return output

    def update_cumulative_data(self, collection, query, content):
        # Use the $set operator to update specific fields
        update_query = {'$set': content}
        response = self.client['flight-control-middle-data'][str(collection)].update_one(query, update_query)
        output = {'type': 'Update', 'Document_ID': str(ObjectId(response.upserted_id))}
        return output

    # DETELE
    def delete_nearest_data(self, collection, query):
        result = self.client['flight-control-middle-data'][str(collection)].delete_one(query)
        return result


# MARIADB CLASS OBJECT
class Mariadb(object):
    def __init__(self, _host, _port, _dbname, _username, _password):
        self.host = _host
        self.port = _port
        self.database = _dbname
        self.user = _username
        self.password = _password

    def get_connection(self):
        try:
            conn = mariadb.connect(host=self.host, port=self.port, database=self.database, user=self.user,
                                   password=self.password)
            # cur = conn.cursor()
        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            sys.exit(1)

        return conn

    # def cur(self):
    #     cur = self.cursor()
    #     return cur


class OSS2:
    def __init__(self, _endpoint, _access, _secret):
        self.endpoint = _endpoint
        self.access = _access
        self.secret = _secret

    def get_oss_client(self):
        """
        Establish a connection to the Aliyun OSS server.
        Returns an OSS client object.
        """
        auth = oss2.Auth(self.access, self.secret)
        client = oss2.Bucket(auth, self.endpoint, 'odprecision')  # Replace 'bucket_name' with your actual bucket name
        return client

    def upload_file(self, key, filename):
        """上传一个本地文件到OSS的普通文件。

        :param str key: 上传到OSS的文件名
        :param str filename: 本地文件名，需要有可读权限

        :param headers: 用户指定的HTTP头部。可以指定Content-Type、Content-MD5、x-oss-meta-开头的头部等
        :type headers: 可以是dict，建议是oss2.CaseInsensitiveDict

        :param progress_callback: 用户指定的进度回调函数。参考 :ref:`progress_callback`

        :return: :class:`PutObjectResult <oss2.models.PutObjectResult>`
        """

        client = self.get_oss_client()
        client.put_object_from_file(key, filename)

        logging.info(f"{filename} successfully uploaded as object {key} to bucket odprecision")

    def make_url(self, image_name):
        client = self.get_oss_client()
        imgurl = client.sign_url('GET', image_name, 2592000000)
        # print(imgurl)
        return imgurl

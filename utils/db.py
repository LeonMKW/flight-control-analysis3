# -*- coding: UTF-8 -*-

import pymongo
from influxdb import InfluxDBClient
import logging
from bson import ObjectId


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
        result = _client.query(query_str)
        if len(result) == 0:
            return {}
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

    # CREATE
    def write_flight_operation_data(self,content, collection):
        logging.info(print('writing flight_operation to Mongo...'))

        response = self.client['flight-control-middle-data'][str(collection)].insert_one(content)
        output = {'type': 'Insert',
                  'Document_ID': str(ObjectId(response.inserted_id))}
        return output

    # UPDATE
    def update_flight_operation_data(self, content, collection, mission_id):
        logging.info('updating flight_operation to Mongo...')
        filter_query = {'mission_id': mission_id}
        response = self.client['flight-control-middle-data'][str(collection)].update_one(filter_query,
                                                                                         {'$set': content})
        output = {'type': 'Update',
                  'Document_ID': str(ObjectId(response.upserted_id))}

        return output



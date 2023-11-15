# -*- coding: UTF-8 -*-
import json
from flask import current_app
from influxdb import InfluxDBClient


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

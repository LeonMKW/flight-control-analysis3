# -*- coding: UTF-8 -*-
from __future__ import absolute_import

import logging
import os
import sys

from utils.db import Influxdb
from utils.factory import create_app
import task
# from utils import Influxdb

PYTHON_ENV = os.environ.get('PYTHON_ENV')
if PYTHON_ENV is None:
    print("Config input error:", PYTHON_ENV)
    sys.exit()
app = create_app(config_name=PYTHON_ENV.upper())
app.app_context().push()
logger = logging.getLogger(__name__)

# 加载influx
influxdb_input = Influxdb(app.config['INFLUXDB_USER'], app.config['INFLUXDB_PASSWD'],
                          app.config['INFLUXDB_DB_INPUT'])
client_input = influxdb_input.connect(app.config['INFLUXDB_HOST'],
                                      app.config['INFLUXDB_PORT'])

orbit_service = app.config['ORBIT_SERVICE']
mete_data_service = app.config['METE_DATA']


# if __name__ == "__main__":
#     # start_api()
#     influx_get('2023-09-01T16:00:00.000Z', '2023-09-02T10:00:00.000Z', '5', 'TMS001', client_input)
# # telephone_call_post('http://172.16.10.51:6002/api/orbit/alert/emergency')

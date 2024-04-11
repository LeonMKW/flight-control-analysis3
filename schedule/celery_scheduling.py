# -*- coding: UTF-8 -*-
import logging
from datetime import datetime
import json

import requests
from celery import Celery
from flask import current_app
from app.task.telephone import telephone_call_post
from app.task.task import traversal, write_alerts_to_influxdb, output_alerts_to_Dingtalk, check_key_interval, \
    rolling_mongo

celery_app = Celery(__name__)
logger = logging.getLogger(__name__)
# -*- coding: UTF-8 -*-
import pandas as pd
import requests
import dfply as d
import datetime
from utils.flightcontrol_utils import tm_table
from utils.db import get_mongo


def reset_data(metedataservice_url, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']

    if not tf1 or not tf2:
        now = datetime.datetime.now()
        ten_minutes_ago = now - datetime.timedelta(minutes=10000)
        tf2 = now.timestamp() * 1000
        tf1 = ten_minutes_ago.timestamp() * 1000

    # Initialize Mongo class and get MongoDBconnection
    mongo_instance = get_mongo()

    resetdf = mongo_instance.read_notice_data(tf1, tf2, satelliteCode)
    result_list = list(resetdf)
    df = pd.DataFrame(result_list)
    print(result_list)

    print(df.to_string())

    return result_list

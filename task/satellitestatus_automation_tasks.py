import json
from flask import jsonify
from bson import ObjectId
import pytz
from datetime import datetime, timedelta
from task.satellitestatus_algorithm import write_reset_count, write_switch_count, check_repeating_records, \
    calculate_cumulative_reset
from utils.flightcontrol_utils import get_task_list
from utils.db import get_mongo


def satellite_status_data_auto_task(
                                    mete_data_service,
                                    influxdb_input,
                                    client_input,
                                    satIDs,
                                    date,
                                    start,
                                    end,
                                    note_url
                                    ):
    if not start and not end and not date:
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        endDate = now_utc
        startDate = endDate - timedelta(hours=48)
    elif not start or not end:
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
    tf1timestamp = startDate.timestamp()
    tf2timestamp = endDate.timestamp()

    satIDs = satIDs.split(",")  # Convert comma-separated string to a list of satellite IDs

    outputs = []  # Initialize a list to store outputs

    # Iterate over each satellite ID
    for satID in satIDs:
        write_switch_count(mete_data_service, influxdb_input, client_input, timefilter1, timefilter2, satID)

        write_reset_count(mete_data_service, influxdb_input, client_input, timefilter1, timefilter2, satID)

        check_repeating_records(mete_data_service, timefilter1, timefilter2, satID)

        calculate_cumulative_reset(mete_data_service, tf1timestamp, tf2timestamp, satID, note_url)

    return outputs

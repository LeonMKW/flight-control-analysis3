import logging
import pprint
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from utils.utils import get_task_list
from task.algorithms import downlink_statics, reset_detect, satcom, uplink_statics_new, file_inspection


def daily_report(orbitservice_url,
                 mete_data_service,
                 influxdb_input,
                 client_input,
                 influxdb_action,
                 client_action,
                 date,
                 start,
                 end,
                 satID):
    startDate = datetime.strptime(date, "%Y-%m-%d")

    # Check if start or end is NA
    if pd.isna(start) or pd.isna(end):
        endDate = startDate + timedelta(days=1)
    else:
        startDate = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
        endDate = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S")
        date = f"{start} to {end}"

    # Check if endDate is greater than current time
    if endDate > datetime.utcnow():
        endDate = datetime.utcnow()

    # Format the dates as ISO 8601 strings
    timefilter1 = startDate.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    timefilter2 = endDate.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    print(date)
    print(timefilter1)
    print(timefilter2)

    tt = get_task_list(orbitservice_url, timefilter1, timefilter2, satID)

    down = downlink_statics(orbitservice_url, mete_data_service, influxdb_input, client_input, timefilter1, timefilter2,
                            satID)

    up = uplink_statics_new(orbitservice_url, mete_data_service, influxdb_input, client_input, influxdb_action,
                            client_action,
                            timefilter1, timefilter2, satID)

    payload = satcom(orbitservice_url, mete_data_service, influxdb_input, client_input, influxdb_action,
                     client_action,
                     timefilter1, timefilter2, satID)

    file_inspect_result = file_inspection(orbitservice_url, mete_data_service, influxdb_input, client_input,
                                          influxdb_action,
                                          client_action,
                                          timefilter1, timefilter2, satID)

    downjson = json.loads(down)
    downjsontt = downjson['task_list']
    downdf = pd.DataFrame(downjsontt)

    upjson = json.loads(up)
    upjsontt = upjson['task_list']
    updf = pd.DataFrame(upjsontt)

    payloadjson = json.loads(payload)
    payloadjsontt = payloadjson['task_list_all']
    payloaddf = pd.DataFrame(payloadjsontt)

    file_inspect_resultjson = json.loads(file_inspect_result)
    file_inspect_resultjsontt = file_inspect_resultjson['task_list_all']
    file_inspect_resultdf = pd.DataFrame(file_inspect_resultjsontt)

    print(downdf.to_string())
    print(updf.to_string())
    print(payloaddf.to_string())
    print(file_inspect_resultdf.to_string())

    return tt

# if __name__ == '__main__':
#     daily_report('http://orbit-service-inf.prod.yhroot.com/graphql',
#                  'http://mete-data-service.prod.yhroot.com/graphql',
#                  '2023-11-10',
#                  '2023-11-09T05:50:00',
#                  '2023-11-11T06:20:00',
#                  '2')
# tm_table('http://mete-data-service.prod.yhroot.com/graphql', '1,2,3')
#  get_orbit_data_tmcode('http://mete-data-service.prod.yhroot.com/graphql', '5')
#     get_spacecraftinfo('http://mete-data-service.prod.yhroot.com/graphql', '12')

# -*- coding: UTF-8 -*-
import pandas as pd
import requests
import dfply as d
import json


def lenz(df):
    return len(df) == 0


def get_task_list(orbitservice_url, startAt, endAt, satIDs):
    orbitserviceurl = orbitservice_url

    # disable chained assignments
    pd.options.mode.chained_assignment = None

    query1 = """
    query(
        $startAt: Date
        $endAt: Date
        $satIDs: [String!]) {
        getAllTask(
        satIDs: $satIDs
        startAt: $startAt
        endAt: $endAt
        statuses: [accepted, completed]
        tcTypes: [TTC, GATEWAY]
        ) {
        satellite {
          code
          id
        }
        antenna { 
          name
          code
          id
        }
        company { 
          name
        }
        startAt:beginAt
        endAt
        threePoints
        status
      }
    }
    """
    satIDs = satIDs.split(",")
    variables = {"startAt": startAt, "endAt": endAt, "satIDs": satIDs}
    res = requests.post(url=orbitserviceurl, json={"query": query1, "variables": variables})
    all_tasks = res.json()["data"]["getAllTask"]
    all_tasks = pd.DataFrame(all_tasks)
    # print(all_tasks.to_string())
    all_tasks = pd.concat([all_tasks.drop(['satellite'], axis=1), all_tasks['satellite'].apply(pd.Series)], axis=1) >> \
                d.rename(satellite_code='code', satellite_id='id')
    # print(all_tasks.to_string())
    all_tasks = pd.concat([all_tasks.drop(['antenna'], axis=1), all_tasks['antenna'].apply(pd.Series)], axis=1)
    # print(all_tasks.to_string())
    all_tasks = pd.concat([all_tasks.drop(['threePoints'], axis=1), all_tasks['threePoints'].apply(pd.Series)], axis=1)
    all_tasks = all_tasks >> d.rename(antID='id',
                                      device='code',
                                      starting='startAt',
                                      ending='endAt',
                                      station_name='name')
    all_tasks = pd.concat([all_tasks.drop(['company'], axis=1), all_tasks['company'].apply(pd.Series)], axis=1)
    all_tasks = all_tasks.rename(
        columns={'name': 'company_name',
                 0: 'approach_angle',
                 1: 'max_elvation',
                 2: 'departure_angle'}) >> d.drop('status')
    all_tasks = all_tasks[all_tasks.company_name != "银河航天"]
    all_tasks.reset_index(inplace=True, drop=True)

    # print(all_tasks.to_string())

    all_tasks['ending'] = pd.to_datetime(all_tasks['ending'])
    all_tasks['starting'] = pd.to_datetime(all_tasks['starting'])

    # 接力轨次判定
    rally: list = [None] * len(all_tasks)

    if len(all_tasks) < 2:
        rally = ["normal"]

    else:
        for i in range(1, len(all_tasks)):
            overlap = (all_tasks['starting'][i] - all_tasks['ending'][i - 1]).total_seconds()

            if overlap < 0:
                rally[i] = "rallylast"
                rally[i - 1] = "rallynext"
            else:
                rally[i] = "normal"

    all_tasks['rally'] = rally
    all_tasks['rally'].fillna("normal", inplace=True)

    # print(all_tasks.to_string())
    # print(type(all_tasks['starting']))
    return all_tasks


def tm_table(metedataservice_url, satIDs):
    metedataserviceurl = metedataservice_url

    query2 = """
    query{
        getAllSpacecraft{
        id
        code
        label: name
        tctmVersion
        }
    }
    """

    res = requests.post(url=metedataserviceurl, json={"query": query2})
    all_info = res.json()["data"]["getAllSpacecraft"]
    sat_ID_code = {}
    for i in range(0, len(all_info)):
        if all_info[i]['id'] in satIDs:
            sat_ID_code[all_info[i]['id']] = {"code": all_info[i]['code'],
                                              "tm_version": 'tm_all_' + all_info[i]["tctmVersion"]}
    for key in sat_ID_code:
        if key == '1':
            sat_ID_code[key]['tm_version'] = 'tm_all'
            break
    # print(sat_ID_code)

    return sat_ID_code


# def vcId(metedataservice_url, _influxdb, client, tf1, tf2, satID):
#     tm = tm_table(metedataservice_url, satID)
#     satelliteCode = tm[satID]['code']
#     tmversion = tm[satID]['tm_version']
#
#     if tmversion != 'tm_all':
#         tmversion = tmversion + '_grd'
#
#     filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' \
#               + tf1 + '\' AND time <= \'' + tf2 + '\' AND _aoc_flag = 0'
#
#     points1 = _influxdb.get_all(client, tmversion, ['_aoc_flag'], filters, limit=1000000)
#     points1 = pd.DataFrame(points1)
#     if lenz(points1):
#         points1 = pd.DataFrame(columns=['time', 'satelliteCode', '_aoc_flag'])
#     else:
#         points1['time'] = pd.to_datetime(points1['time'])
#     # print(points1)
#
#     return points1


def vcIdnew(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    if tmversion != 'tm_all':
        tmversion = tmversion + '_grd'

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame(columns=['time', '_satelliteCode', '_aoc_flag', '_source'])

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=10)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                  current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                  current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND _aoc_flag = 0'

        # Query data for the current interval
        points = _influxdb.get_all(client, tmversion, ['_aoc_flag', '_source'], filters, limit=1000000)
        points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', '_satelliteCode', '_aoc_flag', '_source'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df


def commands(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']

    filters = 'where satellite_code = \'' + satelliteCode + '\' AND time >= \'' \
              + tf1 + '\' AND time <= \'' + tf2 + '\''

    points1 = _influxdb.get_command(client, ['antenna_code', 'cmd_code'], filters, limit=1000000)
    points1 = pd.DataFrame(points1)
    if lenz(points1):
        points1 = pd.DataFrame(columns=['time', 'satellite_code', 'antenna_code', 'cmd_code'])
    else:
        points1['time'] = pd.to_datetime(points1['time'])
    # print(points1.to_string())

    return points1


# 发令前判应答机锁定状态
def Xlock(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame()

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=7)
    current_start = tf1

    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                  current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                  current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\''

        # Query data for the current interval
        if satID == '1':
            points = _influxdb.get_all(client, tmversion, ['TMC016', 'TMC066'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(x_a='TMC016',
                                              x_b='TMC066')

        else:
            points = _influxdb.get_all(client, tmversion, ['TMC001', 'TMC101'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(x_a='TMC001',
                                              x_b='TMC101')

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', 'satelliteCode', 'correct_command'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    # print(result_df)

    return result_df


# 星上收到正确帧计数
def correctframe(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame()

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=7)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                  current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                  current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\''

        # Query data for the current interval
        if satID == '14':
            points = _influxdb.get_all(client, tmversion, ['TMH3005'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(correct_command='TMH3005')

        else:
            points = _influxdb.get_all(client, tmversion, ['TMH302'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(correct_command='TMH302')

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', 'satelliteCode', 'correct_command'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    # print(result_df)

    return result_df


# optimized obc reset
def obc_resetnew(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame()

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=7)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                  current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                  current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\''

        if satID == '1':
            points = _influxdb.get_all(client, tmversion, ['TMH612', 'TMH621'], filters, limit=5000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(obc_switch='TMH612', obc_reset='TMH621')
        else:
            points = _influxdb.get_all(client, tmversion, ['TMS001', 'TMS002'], filters, limit=5000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(obc_switch='TMS001', obc_reset='TMS002')

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', 'satelliteCode', 'obc_switch', 'obc_reset'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    # print(result_df)

    return result_df


def payload_pwr(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    tmversion = tm[satID]['tm_version']

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame()

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=7)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                  current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                  current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\''

        # Query data for the current interval
        if satID == '1':
            points = _influxdb.get_all(client, tmversion, ['TMP248', 'TMP268'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(payload_signal1='TMP248',
                                              payload_signal2='TMP268')

        elif satID == '2':
            points = _influxdb.get_all(client, tmversion, ['TMP261', 'TMP277', 'TMP301'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(payload_signal1='TMP261',
                                              payload_signal2='TMP277',
                                              payload_signal3='TMP301')

        elif satID == '7':
            points = _influxdb.get_all(client, tmversion, ['TMP239', 'TMP237', 'TMP273'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(payload_signal1='TMP239',
                                              payload_signal2='TMP237',
                                              payload_signal3='TMP273')

        elif satID == '14':
            points = _influxdb.get_all(client, tmversion, ['TMS505', 'TMS506'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(payload_signal1='TMS505',
                                              payload_signal2='TMS506')

        else:
            points = _influxdb.get_all(client, tmversion, ['TMP203', 'TMP201', 'TMP241'], filters, limit=1000000)
            points_df = pd.DataFrame(points)
            points_df = points_df >> d.rename(payload_signal1='TMP203',
                                              payload_signal2='TMP201',
                                              payload_signal3='TMP241')

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time', 'satelliteCode', 'payload_signal1'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    # print(result_df.to_string())
    return result_df


# obc file inspection
def file_inspect(metedataservice_url, _influxdb, client, tf1, tf2, satID):
    tm = tm_table(metedataservice_url, satID)
    satelliteCode = tm[satID]['code']
    if satID == '1':
        tmversion = 'tm_all'
    else:
        tmversion = tm[satID]['tm_version'] + '_grd'

    # Convert the input timestamps to datetime objects
    tf1 = pd.to_datetime(tf1)
    tf2 = pd.to_datetime(tf2)

    # Initialize an empty DataFrame to store the results
    result_df = pd.DataFrame()

    # Query data in 10-day intervals
    interval = pd.DateOffset(days=7)
    current_start = tf1
    while current_start <= tf2:
        current_end = current_start + interval

        # Ensure the end timestamp does not exceed tf2
        if current_end > tf2:
            current_end = tf2

        filters = 'where _satelliteCode = \'' + satelliteCode + '\' AND time >= \'' + \
                  current_start.strftime('%Y-%m-%dT%H:%M:%SZ') + '\' AND time <= \'' + \
                  current_end.strftime('%Y-%m-%dT%H:%M:%SZ') + '\''

        # Query data for the current interval
        if satID == '1' or satID == '2':
            points = _influxdb.get_all(client, tmversion, ['TMH1301', 'TMH1302', 'TMH1303', 'TMH1304', 'TMH1305',
                                                           'TMH1306', 'TMH1307', 'TMH1308', 'TMH1309', 'TMH1310',
                                                           'TMH1311', 'TMH1312', 'TMH1313', 'TMH1314', 'TMH1315',
                                                           'TMH1316', 'TMH1317', 'TMH1318', 'TMH1319', 'TMH1320',
                                                           'TMH1321', 'TMH1322', 'TMH1323', 'TMH1324', 'TMH1325',
                                                           'TMH1326', 'TMH1327', 'TMH1328', 'TMH1329', 'TMH1330',
                                                           'TMH1331', 'TMH1332', 'TMH1333', 'TMH1334', 'TMH1335',
                                                           'TMH1336', 'TMH1337', 'TMH1338', 'TMH1339', 'TMH1340',
                                                           'TMH1341', 'TMH1342', 'TMH1343', 'TMH1344', 'TMH1345',
                                                           'TMH1346', 'TMH1347', 'TMH1348', 'TMH1349', 'TMH1350',
                                                           'TMH1351', 'TMH1352', 'TMH1353', 'TMH1354', 'TMH1355',
                                                           'TMH1356', 'TMH1357', 'TMH1358', 'TMH1359', 'TMH1360',
                                                           'TMH1361', 'TMH1362', 'TMH1363', 'TMH1364', 'TMH1365',
                                                           'TMH1366', 'TMH1367', 'TMH1368', 'TMH1369', 'TMH1370',
                                                           'TMH1371', 'TMH1372', 'TMH1373', 'TMH1374', 'TMH1375',
                                                           'TMH1376', 'TMH1377', 'TMH1378', 'TMH1379', 'TMH1380',
                                                           'TMH1381', 'TMH1382', 'TMH1383', 'TMH1384', 'TMH1385',
                                                           'TMH1386', 'TMH1387', 'TMH1388', 'TMH1389', 'TMH1390',
                                                           'TMH1391', 'TMH1392', 'TMH1393', 'TMH1394', 'TMH1395',
                                                           'TMH1396', 'TMH1397', 'TMH1398', 'TMH1399', 'TMH1400',
                                                           'TMH1401', 'TMH1402', 'TMH1403', 'TMH1404', 'TMH1405',
                                                           'TMH1406', 'TMH1407', 'TMH1408', 'TMH1409', 'TMH1410',
                                                           'TMH1411', 'TMH1412', 'TMH1413', 'TMH1414', 'TMH1415',
                                                           'TMH1416', 'TMH1417', 'TMH1418', 'TMH1419', 'TMH1420',
                                                           'TMH1421', 'TMH1422', 'TMH1423', 'TMH1424', 'TMH1425',
                                                           'TMH1426', 'TMH1427', 'TMH1428', 'TMH1429', 'TMH1430',
                                                           'TMH1431', 'TMH1432', 'TMH1433', 'TMH1434', 'TMH1435',
                                                           'TMH1436', 'TMH1437', 'TMH1438', 'TMH1439', 'TMH1440',
                                                           'TMH1441', 'TMH1442', 'TMH1443', 'TMH1444', 'TMH1445',
                                                           'TMH1446', 'TMH1447', 'TMH1448', 'TMH1449', 'TMH1450'],
                                       filters, limit=1000000)
            points_df = pd.DataFrame(points)

        elif satID == '7':
            points = _influxdb.get_all(client, tmversion, ['TMH1301', 'TMH1302', 'TMH1303', 'TMH1304', 'TMH1305',
                                                           'TMH1306', 'TMH1307', 'TMH1308', 'TMH1309', 'TMH1310',
                                                           'TMH1311', 'TMH1312', 'TMH1313', 'TMH1314', 'TMH1315',
                                                           'TMH1316', 'TMH1317', 'TMH1318', 'TMH1319', 'TMH1320',
                                                           'TMH1321', 'TMH1322', 'TMH1323', 'TMH1324', 'TMH1325',
                                                           'TMH1326', 'TMH1327', 'TMH1328', 'TMH1329', 'TMH1330',
                                                           'TMH1331', 'TMH1332', 'TMH1333', 'TMH1334', 'TMH1335',
                                                           'TMH1336', 'TMH1337', 'TMH1338', 'TMH1339', 'TMH1340',
                                                           'TMH1341', 'TMH1342', 'TMH1343', 'TMH1344', 'TMH1345',
                                                           'TMH1346', 'TMH1347', 'TMH1348', 'TMH1349', 'TMH1350',
                                                           'TMH1351', 'TMH1352', 'TMH1353', 'TMH1354', 'TMH1355',
                                                           'TMH1356', 'TMH1357', 'TMH1358', 'TMH1359', 'TMH1360',
                                                           'TMH1361', 'TMH1362', 'TMH1363', 'TMH1364', 'TMH1365',
                                                           'TMH1366', 'TMH1367', 'TMH1368', 'TMH1369', 'TMH1370',
                                                           'TMH1371', 'TMH1372', 'TMH1373', 'TMH1374', 'TMH1375',
                                                           'TMH1376', 'TMH1377', 'TMH1378', 'TMH1379', 'TMH1380',
                                                           'TMH1381', 'TMH1382', 'TMH1383', 'TMH1384', 'TMH1385',
                                                           'TMH1386', 'TMH1387', 'TMH1388', 'TMH1389', 'TMH1390',
                                                           'TMH1391', 'TMH1392', 'TMH1393', 'TMH1394', 'TMH1395',
                                                           'TMH1396', 'TMH1397', 'TMH1398', 'TMH1399', 'TMH1400',
                                                           'TMH1401', 'TMH1402', 'TMH1403', 'TMH1404', 'TMH1405',
                                                           'TMH1406', 'TMH1407', 'TMH1408', 'TMH1409', 'TMH1410',
                                                           'TMH1411', 'TMH1412', 'TMH1413', 'TMH1414', 'TMH1415',
                                                           'TMH1416', 'TMH1417', 'TMH1418', 'TMH1419', 'TMH1420',
                                                           'TMH1421', 'TMH1422', 'TMH1423', 'TMH1424', 'TMH1425',
                                                           'TMH1426', 'TMH1427', 'TMH1428', 'TMH1429', 'TMH1430',
                                                           'TMH1431', 'TMH1432', 'TMH1433', 'TMH1434', 'TMH1435',
                                                           'TMH1436', 'TMH1437', 'TMH1438', 'TMH1439', 'TMH1440',
                                                           'TMH1441', 'TMH1442', 'TMH1443', 'TMH1444', 'TMH1445',
                                                           'TMH1446', 'TMH1447', 'TMH1448', 'TMH1449', 'TMH1450',
                                                           'TMH1451', 'TMH1452', 'TMH1453', 'TMH1454', 'TMH1455',
                                                           'TMH1456', 'TMH1457', 'TMH1458', 'TMH1459', 'TMH1460',
                                                           'TMH1461', 'TMH1462', 'TMH1463', 'TMH1464', 'TMH1465',
                                                           'TMH1466', 'TMH1467', 'TMH1468', 'TMH1469', 'TMH1470',
                                                           'TMH1471', 'TMH1472', 'TMH1473', 'TMH1474', 'TMH1475',
                                                           'TMH1476', 'TMH1477', 'TMH1478', 'TMH1479', 'TMH1480',
                                                           'TMH1481', 'TMH1482', 'TMH1483', 'TMH1484', 'TMH1485',
                                                           'TMH1486', 'TMH1487', 'TMH1488', 'TMH1489', 'TMH1490',
                                                           'TMH1491', 'TMH1492', 'TMH1493', 'TMH1494', 'TMH1495',
                                                           'TMH1496', 'TMH1497', 'TMH1498', 'TMH1499', 'TMH1500',
                                                           'TMH1501', 'TMH1502', 'TMH1503', 'TMH1504', 'TMH1505',
                                                           'TMH1506', 'TMH1507', 'TMH1508', 'TMH1509', 'TMH1510',
                                                           'TMH1511', 'TMH1512', 'TMH1513', 'TMH1514', 'TMH1515',
                                                           'TMH1516', 'TMH1517', 'TMH1518', 'TMH1519', 'TMH1520',
                                                           'TMH1521', 'TMH1522', 'TMH1523', 'TMH1524', 'TMH1525',
                                                           'TMH1526', 'TMH1527', 'TMH1528', 'TMH1529', 'TMH1530',
                                                           'TMH1531', 'TMH1532', 'TMH1533', 'TMH1534', 'TMH1535',
                                                           'TMH1536', 'TMH1537', 'TMH1538', 'TMH1539', 'TMH1540',
                                                           'TMH1541', 'TMH1542', 'TMH1543', 'TMH1544', 'TMH1545',
                                                           'TMH1546', 'TMH1547', 'TMH1548', 'TMH1549', 'TMH1550',
                                                           'TMH1551', 'TMH1552', 'TMH1553', 'TMH1554', 'TMH1555',
                                                           'TMH1556', 'TMH1557', 'TMH1558', 'TMH1559', 'TMH1560',
                                                           'TMH1561', 'TMH1562', 'TMH1563', 'TMH1564', 'TMH1565',
                                                           'TMH1566', 'TMH1567', 'TMH1568', 'TMH1569', 'TMH1570',
                                                           'TMH1571', 'TMH1572', 'TMH1573', 'TMH1574', 'TMH1575',
                                                           'TMH1576', 'TMH1577', 'TMH1578', 'TMH1579', 'TMH1580',
                                                           'TMH1581', 'TMH1582', 'TMH1583', 'TMH1584', 'TMH1585',
                                                           'TMH1586', 'TMH1587', 'TMH1588', 'TMH1589', 'TMH1590',
                                                           'TMH1591', 'TMH1592', 'TMH1593', 'TMH1594', 'TMH1595',
                                                           'TMH1596', 'TMH1597', 'TMH1598', 'TMH1599', 'TMH1600',
                                                           'TMH1601', 'TMH1602', 'TMH1603', 'TMH1604', 'TMH1605',
                                                           'TMH1606', 'TMH1607', 'TMH1608', 'TMH1609', 'TMH1610',
                                                           'TMH1611', 'TMH1612', 'TMH1613', 'TMH1614', 'TMH1615',
                                                           'TMH1616', 'TMH1617', 'TMH1618', 'TMH1619', 'TMH1620',
                                                           'TMH1621', 'TMH1622', 'TMH1623', 'TMH1624', 'TMH1625',
                                                           'TMH1626', 'TMH1627', 'TMH1628', 'TMH1629', 'TMH1630',
                                                           'TMH1631', 'TMH1632', 'TMH1633', 'TMH1634', 'TMH1635',
                                                           'TMH1636', 'TMH1637', 'TMH1638', 'TMH1639', 'TMH1640',
                                                           'TMH1641', 'TMH1642', 'TMH1643', 'TMH1644', 'TMH1645',
                                                           'TMH1646', 'TMH1647', 'TMH1648', 'TMH1649', 'TMH1650',
                                                           'TMH1651', 'TMH1652', 'TMH1653', 'TMH1654', 'TMH1655',
                                                           'TMH1656', 'TMH1657', 'TMH1658', 'TMH1659', 'TMH1660',
                                                           'TMH1661', 'TMH1662', 'TMH1663', 'TMH1664', 'TMH1665',
                                                           'TMH1666', 'TMH1667', 'TMH1668', 'TMH1669', 'TMH1670',
                                                           'TMH1671', 'TMH1672', 'TMH1673', 'TMH1674', 'TMH1675',
                                                           'TMH1676', 'TMH1677', 'TMH1678', 'TMH1679', 'TMH1680',
                                                           'TMH1681', 'TMH1682'],
                                       filters, limit=1000000)
            points_df = pd.DataFrame(points)

        elif satID == '14':
            points = _influxdb.get_all(client, tmversion, [
                'TMH6101', 'TMH6102', 'TMH6103', 'TMH6104', 'TMH6105', 'TMH6106', 'TMH6107', 'TMH6108', 'TMH6109',
                'TMH6110', 'TMH6111', 'TMH6112', 'TMH6113', 'TMH6114', 'TMH6115', 'TMH6116', 'TMH6117', 'TMH6118',
                'TMH6119', 'TMH6120', 'TMH6121', 'TMH6122', 'TMH6123', 'TMH6124', 'TMH6125', 'TMH6126', 'TMH6127',
                'TMH6128', 'TMH6129', 'TMH6130', 'TMH6131', 'TMH6132', 'TMH6133', 'TMH6134', 'TMH6135', 'TMH6136',
                'TMH6137', 'TMH6138', 'TMH6139',
                'TMH6140', 'TMH6141', 'TMH6142', 'TMH6143', 'TMH6144', 'TMH6145', 'TMH6146', 'TMH6147', 'TMH6148',
                'TMH6149', 'TMH6150', 'TMH6151', 'TMH6152', 'TMH6153', 'TMH6154', 'TMH6155', 'TMH6156', 'TMH6157',
                'TMH6158', 'TMH6159', 'TMH6160', 'TMH6161', 'TMH6162', 'TMH6163', 'TMH6164', 'TMH6165', 'TMH6166',
                'TMH6167', 'TMH6168', 'TMH6169', 'TMH6170', 'TMH6171', 'TMH6172', 'TMH6173', 'TMH6174', 'TMH6175',
                'TMH6176', 'TMH6177', 'TMH6178',
                'TMH6179', 'TMH6180', 'TMH6181', 'TMH6182', 'TMH6183', 'TMH6184', 'TMH6185', 'TMH6186', 'TMH6187',
                'TMH6188', 'TMH6189', 'TMH6190', 'TMH6191', 'TMH6192', 'TMH6193', 'TMH6194', 'TMH6195', 'TMH6196',
                'TMH6197', 'TMH6198', 'TMH6199', 'TMH6200', 'TMH6201', 'TMH6202', 'TMH6203', 'TMH6204', 'TMH6205',
                'TMH6206', 'TMH6207', 'TMH6208', 'TMH6209', 'TMH6210', 'TMH6211', 'TMH6212', 'TMH6213', 'TMH6214',
                'TMH6215', 'TMH6216', 'TMH6217',
                'TMH6218', 'TMH6219', 'TMH6220', 'TMH6221', 'TMH6222', 'TMH6223', 'TMH6224', 'TMH6225', 'TMH6226',
                'TMH6227', 'TMH6228', 'TMH6229', 'TMH6230', 'TMH6231', 'TMH6232', 'TMH6233', 'TMH6234', 'TMH6235',
                'TMH6236', 'TMH6237', 'TMH6238', 'TMH6239', 'TMH6240', 'TMH6241', 'TMH6242', 'TMH6243', 'TMH6244',
                'TMH6245', 'TMH6246', 'TMH6247', 'TMH6248', 'TMH6249', 'TMH6250', 'TMH6251', 'TMH6252', 'TMH6253',
                'TMH6254', 'TMH6255', 'TMH6256',
                'TMH6257', 'TMH6258', 'TMH6259', 'TMH6260', 'TMH6261', 'TMH6262', 'TMH6263', 'TMH6264', 'TMH6265',
                'TMH6266', 'TMH6267', 'TMH6268', 'TMH6269', 'TMH6270', 'TMH6271', 'TMH6272', 'TMH6273', 'TMH6274',
                'TMH6275', 'TMH6276', 'TMH6277', 'TMH6278', 'TMH6279', 'TMH6280', 'TMH6281', 'TMH6282', 'TMH6283',
                'TMH6284', 'TMH6285', 'TMH6286', 'TMH6287', 'TMH6288', 'TMH6289', 'TMH6290', 'TMH6291', 'TMH6292',
                'TMH6293', 'TMH6294', 'TMH6295',
                'TMH6296', 'TMH6297', 'TMH6298', 'TMH6299', 'TMH6300', 'TMH6301', 'TMH6302', 'TMH6303', 'TMH6304',
                'TMH6305', 'TMH6306', 'TMH6307', 'TMH6308', 'TMH6309', 'TMH6310', 'TMH6311', 'TMH6312', 'TMH6313',
                'TMH6314', 'TMH6315', 'TMH6316', 'TMH6317', 'TMH6318', 'TMH6319', 'TMH6320', 'TMH6321', 'TMH6322',
                'TMH6323', 'TMH6324', 'TMH6325', 'TMH6326', 'TMH6327', 'TMH6328', 'TMH6329', 'TMH6330', 'TMH6331',
                'TMH6332', 'TMH6333', 'TMH6334',
                'TMH6335', 'TMH6336', 'TMH6337', 'TMH6338', 'TMH6339', 'TMH6340', 'TMH6341', 'TMH6342', 'TMH6343',
                'TMH6344', 'TMH6345', 'TMH6346', 'TMH6347', 'TMH6348', 'TMH6349', 'TMH6350', 'TMH6351', 'TMH6352',
                'TMH6353', 'TMH6354', 'TMH6355', 'TMH6356', 'TMH6357', 'TMH6358', 'TMH6359', 'TMH6360', 'TMH6361',
                'TMH6362', 'TMH6363', 'TMH6364', 'TMH6365', 'TMH6366', 'TMH6367', 'TMH6368', 'TMH6369', 'TMH6370',
                'TMH6371', 'TMH6372', 'TMH6373',
                'TMH6374', 'TMH6375', 'TMH6376', 'TMH6377', 'TMH6378', 'TMH6379', 'TMH6380', 'TMH6381', 'TMH6382',
                'TMH6383', 'TMH6384', 'TMH6385', 'TMH6386', 'TMH6387', 'TMH6388', 'TMH6389', 'TMH6390', 'TMH6391',
                'TMH6392', 'TMH6393', 'TMH6394', 'TMH6395', 'TMH6396', 'TMH6397', 'TMH6398', 'TMH6399', 'TMH6400',
                'TMH6401', 'TMH6402', 'TMH6403', 'TMH6404', 'TMH6405', 'TMH6406', 'TMH6407', 'TMH6408', 'TMH6409',
                'TMH6410', 'TMH6411', 'TMH6412',
                'TMH6413', 'TMH6414', 'TMH6415', 'TMH6416', 'TMH6417', 'TMH6418', 'TMH6419', 'TMH6420', 'TMH6421',
                'TMH6422', 'TMH6423', 'TMH6424', 'TMH6425', 'TMH6426', 'TMH6427', 'TMH6428', 'TMH6429', 'TMH6430',
                'TMH6431', 'TMH6432', 'TMH6433', 'TMH6434', 'TMH6435', 'TMH6436', 'TMH6437', 'TMH6438', 'TMH6439',
                'TMH6440', 'TMH6441', 'TMH6442', 'TMH6443', 'TMH6444', 'TMH6445', 'TMH6446', 'TMH6447', 'TMH6448',
                'TMH6449', 'TMH6450', 'TMH6451',
                'TMH6452', 'TMH6453', 'TMH6454', 'TMH6455', 'TMH6456', 'TMH6457', 'TMH6458', 'TMH6459', 'TMH6460',
                'TMH6461', 'TMH6462', 'TMH6463', 'TMH6464', 'TMH6465', 'TMH6466', 'TMH6467', 'TMH6468', 'TMH6469',
                'TMH6470', 'TMH6471', 'TMH6472', 'TMH6473', 'TMH6474', 'TMH6475', 'TMH6476', 'TMH6477', 'TMH6478',
                'TMH6479', 'TMH6480', 'TMH6481', 'TMH6482', 'TMH6483', 'TMH6484', 'TMH6485', 'TMH6486', 'TMH6487',
                'TMH6488', 'TMH6489', 'TMH6490',
                'TMH6491', 'TMH6492', 'TMH6493', 'TMH6494', 'TMH6495', 'TMH6496', 'TMH6497', 'TMH6498', 'TMH6499',
                'TMH6500'
                                                           ],
                                       filters, limit=1000000)
            points_df = pd.DataFrame(points)

        else:
            points = _influxdb.get_all(client, tmversion, ['TMH1301', 'TMH1302', 'TMH1303', 'TMH1304', 'TMH1305',
                                                           'TMH1306', 'TMH1307', 'TMH1308', 'TMH1309', 'TMH1310',
                                                           'TMH1311', 'TMH1312', 'TMH1313', 'TMH1314', 'TMH1315',
                                                           'TMH1316', 'TMH1317', 'TMH1318', 'TMH1319', 'TMH1320',
                                                           'TMH1321', 'TMH1322', 'TMH1323', 'TMH1324', 'TMH1325',
                                                           'TMH1326', 'TMH1327', 'TMH1328', 'TMH1329', 'TMH1330',
                                                           'TMH1331', 'TMH1332', 'TMH1333', 'TMH1334', 'TMH1335',
                                                           'TMH1336', 'TMH1337', 'TMH1338', 'TMH1339', 'TMH1340',
                                                           'TMH1341', 'TMH1342', 'TMH1343', 'TMH1344', 'TMH1345',
                                                           'TMH1346', 'TMH1347', 'TMH1348', 'TMH1349', 'TMH1350',
                                                           'TMH1351', 'TMH1352', 'TMH1353', 'TMH1354', 'TMH1355',
                                                           'TMH1356', 'TMH1357', 'TMH1358', 'TMH1359', 'TMH1360',
                                                           'TMH1361', 'TMH1362', 'TMH1363', 'TMH1364', 'TMH1365',
                                                           'TMH1366', 'TMH1367', 'TMH1368', 'TMH1369', 'TMH1370',
                                                           'TMH1371', 'TMH1372', 'TMH1373', 'TMH1374', 'TMH1375',
                                                           'TMH1376', 'TMH1377', 'TMH1378', 'TMH1379', 'TMH1380',
                                                           'TMH1381', 'TMH1382', 'TMH1383', 'TMH1384', 'TMH1385',
                                                           'TMH1386', 'TMH1387', 'TMH1388', 'TMH1389', 'TMH1390',
                                                           'TMH1391', 'TMH1392', 'TMH1393', 'TMH1394', 'TMH1395',
                                                           'TMH1396', 'TMH1397', 'TMH1398', 'TMH1399', 'TMH1400',
                                                           'TMH1401', 'TMH1402', 'TMH1403', 'TMH1404', 'TMH1405',
                                                           'TMH1406', 'TMH1407', 'TMH1408', 'TMH1409', 'TMH1410',
                                                           'TMH1411', 'TMH1412', 'TMH1413', 'TMH1414', 'TMH1415',
                                                           'TMH1416', 'TMH1417', 'TMH1418', 'TMH1419', 'TMH1420',
                                                           'TMH1421', 'TMH1422', 'TMH1423', 'TMH1424', 'TMH1425',
                                                           'TMH1426', 'TMH1427', 'TMH1428', 'TMH1429', 'TMH1430',
                                                           'TMH1431', 'TMH1432', 'TMH1433', 'TMH1434', 'TMH1435',
                                                           'TMH1436', 'TMH1437', 'TMH1438', 'TMH1439', 'TMH1440',
                                                           'TMH1441', 'TMH1442', 'TMH1443', 'TMH1444', 'TMH1445',
                                                           'TMH1446', 'TMH1447', 'TMH1448', 'TMH1449', 'TMH1450',
                                                           'TMH1451', 'TMH1452', 'TMH1453', 'TMH1454', 'TMH1455',
                                                           'TMH1456', 'TMH1457', 'TMH1458', 'TMH1459', 'TMH1460',
                                                           'TMH1461', 'TMH1462', 'TMH1463', 'TMH1464', 'TMH1465',
                                                           'TMH1466', 'TMH1467', 'TMH1468', 'TMH1469', 'TMH1470',
                                                           'TMH1471', 'TMH1472', 'TMH1473', 'TMH1474', 'TMH1475',
                                                           'TMH1476', 'TMH1477', 'TMH1478', 'TMH1479', 'TMH1480',
                                                           'TMH1481', 'TMH1482'],
                                       filters, limit=1000000)
            points_df = pd.DataFrame(points)

        if not len(points_df):
            points_df = pd.DataFrame(columns=['time'])
        else:
            points_df['time'] = pd.to_datetime(points_df['time'])

        # Concatenate the results for the current interval to the result DataFrame
        result_df = pd.concat([result_df, points_df], ignore_index=True)

        # Move to the next interval
        current_start = current_end + pd.Timedelta(seconds=1)

    return result_df

# if __name__ == '__main__':
#     get_task_list('http://orbit-service-inf.prod.yhroot.com/graphql',
#                   '2023-11-10T05:50:00.000Z',
#                   '2023-11-11T05:50:00.000Z',
#                   '1,2,3,4,5,6,7,14')
# tm_table('http://mete-data-service.prod.yhroot.com/graphql', '1,2,3')
#  get_orbit_data_tmcode('http://mete-data-service.prod.yhroot.com/graphql', '5')
#     get_spacecraftinfo('http://mete-data-service.prod.yhroot.com/graphql', '12')

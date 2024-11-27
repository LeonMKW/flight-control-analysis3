# -*- coding: UTF-8 -*-
from datetime import datetime, timedelta
from json.decoder import JSONDecodeError
import pandas as pd
import requests
import dfply as d
from utils.flightcontrol_utils import tm_table
import pytz
from utils.authentication import get_header_token


def satellite_properties(post_token_url,
                         post_token_user_name,
                         post_token_password, metedataservice_url, satIDs):
    metedataserviceurl = metedataservice_url + '/v2/api/openapi-transform/get-all-spacecraft'
    token = get_header_token(post_token_url,
                             post_token_user_name,
                             post_token_password)

    # Define the headers with the required token
    headers = {
        'x-web-token': token
    }

    query2 = """
    query{
        getAllSpacecraft{
        id
        code
        label: name
        tctmVersion
        weight
        surfaceArea
        thrust
        }
    }
    """

    res = requests.post(url=metedataserviceurl, json={"query": query2}, headers=headers, timeout=300)

    all_info = res.json()["data"]["getAllSpacecraft"]
    satellite_od_dict = {sat["id"]: sat for sat in all_info if sat["id"] in satIDs}
    satellite_info = satellite_od_dict.get(satIDs)

    if satellite_info:
        return satellite_info
    else:
        print("ID not found in the dictionary.")
        return None


def od_tmcode(post_token_url,
              post_token_user_name,
              post_token_password, metedataservice_url, satIDs):
    metedataserviceurl = metedataservice_url + '/v2/api/openapi-transform/get-spacecraft-info-by-id'

    token = get_header_token(post_token_url,
                             post_token_user_name,
                             post_token_password)

    # Define the headers with the required token
    headers = {
        'x-web-token': token
    }

    gnss_info = """
    query($id: String!) {
    getSpacecraftInfoByID(id: $id) {
        determinationConfigs {
        apID
        gpsTimeField
        xField
        yField
        zField
        validStatement
        }
      }
    }
    """
    variables = {"id": str(satIDs)}
    res = requests.post(url=metedataserviceurl, json={"query": gnss_info, "variables": variables}, headers=headers,
                        timeout=300)
    # print(res.json())
    # Extract relevant data from the response
    data = res.json().get("data", {})
    get_spacecraft_info = data.get("getSpacecraftInfoByID", {})
    determination_configs = get_spacecraft_info.get("determinationConfigs", [])
    # print(determination_configs)
    # Convert the result to a DataFrame
    satgnssconfig_df = pd.json_normalize(determination_configs, sep='_')  # Assuming you have pandas installed

    if satIDs == 1:
        satgnssconfig_df = satgnssconfig_df.tail(1)
    else:
        satgnssconfig_df = satgnssconfig_df.head(1)

    satgnssconfig_df = satgnssconfig_df.reset_index(drop=True)

    # print(satgnssconfig_df.to_string())

    return satgnssconfig_df


def gnss_get_last(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, _influxdb, client, satIDs):
    satellite_od_dict = satellite_properties(post_token_url,
                                             post_token_user_name,
                                             post_token_password, metedataservice_url, satIDs)
    satellitecode = satellite_od_dict['code']
    tm = tm_table(post_token_url,
                  post_token_user_name,
                  post_token_password, metedataservice_url, satIDs)
    tmversion = tm[satIDs]['tm_version']
    satgnssconfig_df = od_tmcode(post_token_url,
                                 post_token_user_name,
                                 post_token_password, metedataservice_url, satIDs)
    tm_timestamp = satgnssconfig_df.at[0, 'gpsTimeField']
    tm_valid = satgnssconfig_df.at[0, 'validStatement']

    filters = 'where _satelliteCode = \'' + satellitecode + '\' AND ' + \
              tm_valid + ' AND time <= now() AND time >= now() - 24h ORDER BY time ASC'

    # Query data for the current interval
    points = _influxdb.get_all(client, tmversion, [tm_timestamp], filters, limit=1)
    points_df = pd.DataFrame(points)
    # print(points_df.to_string())

    gnsstime_last = int(points_df[tm_timestamp].iloc[0])
    # print(gnsstime_last)

    return gnsstime_last


def ephemeris_acquire(post_token_url,
                      post_token_user_name,
                      post_token_password, orbitserviceurl, metedataservice_url, startAt, endAt, satIDs):
    orbitserviceurl = orbitserviceurl + '/v2/api/openapi-transform/get-orbital-elements-list-graphql'

    token = get_header_token(post_token_url,
                             post_token_user_name,
                             post_token_password)

    # Define the headers with the required token
    headers = {
        'x-web-token': token
    }

    satellite_od_dict = satellite_properties(post_token_url,
                                             post_token_user_name,
                                             post_token_password, metedataservice_url, satIDs)
    satellitecode = satellite_od_dict['code']
    query1 = """query(
        $lyTimeStart: Date
        $lyTimeEnd: Date
        $satID: String) {
        getOrbitalElementsList(
          page: 1, 
          limit: 10, 
          satID: $satID,
          lyTimeStart: $lyTimeStart,
          lyTimeEnd: $lyTimeEnd
        ) {
        total
          records{
            a
            e
            i
            dw
            xw
            M
            CD
            remark
            gnssCount
            residual
            createdAt
            type
            epochTimeUTC
            id
            thrust
            isValid
            updatedAt
            spacecraft{
              code
            }
          }
        }
    }
    """
    variables = {"lyTimeStart": startAt, "lyTimeEnd": endAt, "satID": satIDs}
    # print(variables)
    # print(startAt)
    # print(endAt)
    res = requests.post(url=orbitserviceurl, json={"query": query1, "variables": variables}, headers=headers,
                        timeout=300)
    # print(res.json())
    all_ephemeris = res.json()["data"]["getOrbitalElementsList"]['records']
    # print(all_ephemeris)
    orbit_data = pd.DataFrame(all_ephemeris)
    orbit_data['spacecraft'] = orbit_data['spacecraft'].apply(lambda x: x['code'])

    # print(orbit_data.to_string())

    sixelements = orbit_data[(orbit_data['gnssCount'] > 50) & (orbit_data['spacecraft'] == satellitecode)]
    # print(sixelements.to_string())

    return sixelements


def orbitcal_body(satellite_od_dict, ephemeris, hours=24):
    # Use ephemeris["timestamp"][0] directly for beginTime
    begin_time = int(ephemeris["timestamp"][0] * 1000)

    # Calculate endTime by adding hours (converted to milliseconds) directly to beginTime
    end_time = int(begin_time + hours * 3600 * 1000)  # Convert hours to milliseconds

    return {
        "thrusterForce": 0,
        "firePeriods": [],
        "calcStepInSeconds": 1,
        "radiationFlow": 73,
        "beginTime": begin_time,  # 13-digit Unix timestamp in milliseconds
        "endTime": end_time,  # 13-digit Unix timestamp in milliseconds
        "satelliteMass": satellite_od_dict["weight"],
        "satelliteArea": satellite_od_dict["surfaceArea"],
        'orbitElements': {
            "CD": ephemeris["CD"][0],
            "epochTimeUTC": ephemeris["epochTimeUTC"][0],
            "a": ephemeris["a"][0],
            "e": ephemeris["e"][0],
            "i": ephemeris["i"][0],
            "dw": ephemeris["dw"][0],
            "xw": ephemeris["xw"][0],
            "M": ephemeris["M"][0]
        }
    }


# will be used for collision avoidance update PA
def get_gnss_data(satellite_od_dict, satgnssconfig_df, tmversion, _influxdb, client, tf1, tf2):
    # print(tf1)
    # print(tf2)
    satellitecode = satellite_od_dict['code']

    if satellitecode == "GS-1a":
        tm_x = 'TMK2703_gps_rx'
        tm_y = 'TMK2704_gps_ry'
        tm_z = 'TMK2705_gps_rz'
        tm_time = 'TMK2702_gps_time'
        tm_valid = 'TMK2701_gps_state=1'
    else:
        tm_x = satgnssconfig_df.at[0, 'xField']
        tm_y = satgnssconfig_df.at[0, 'yField']
        tm_z = satgnssconfig_df.at[0, 'zField']
        tm_time = satgnssconfig_df.at[0, 'gpsTimeField']
        tm_valid = satgnssconfig_df.at[0, 'validStatement']

    # # Initialize an empty DataFrame to store the results
    # points_df = pd.DataFrame()

    filters = 'where _satelliteCode = \'' + satellitecode + '\' AND time >= \'' + \
              tf1 + '\' AND time <= \'' + tf2 + '\' AND ' + tm_valid

    # Query data for the current interval
    points = _influxdb.get_all(client, tmversion, [tm_time, tm_x, tm_y, tm_z], filters, limit=86400)
    points_df = pd.DataFrame(points)

    if not len(points_df):
        points_df = pd.DataFrame(columns=['time', '_satelliteCode', 'x', 'y', 'z'])
    else:
        # colnames = ['time', '_satelliteCode', 'timestamp', 'x', 'y', 'z']
        points_df.columns = ['time', '_satelliteCode', 'timestamp', 'x', 'y', 'z']

    # print(result_df.to_string())

    return points_df


def get_all_altitude(post_token_url,
                     post_token_user_name,
                     post_token_password, metedataservice_url, influxdb_orbdata, client_orbdata, satID, start, end):
    satellite_od_dict = satellite_properties(post_token_url,
                                             post_token_user_name,
                                             post_token_password, metedataservice_url, satID)
    satellitecode = satellite_od_dict['code']
    tf1 = pd.to_datetime(start).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    tf2 = pd.to_datetime(end).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    # Use the modified function to get data or nearest data
    points = influxdb_orbdata.get_distinct_alt(client_orbdata, tf1, tf2, satellitecode)

    points_df = pd.DataFrame(points)
    if len(points_df) == 0:
        return pd.DataFrame()  # or handle it as needed

    return points_df


def get_altitude(post_token_url,
                 post_token_user_name,
                 post_token_password, metedataservice_url, influxdb_orbdata, client_orbdata, satID, start, end):
    satellite_od_dict = satellite_properties(post_token_url,
                                             post_token_user_name,
                                             post_token_password, metedataservice_url, satID)
    satellitecode = satellite_od_dict['code']

    # Ensure the input timestamps are in the correct format
    tf1 = pd.to_datetime(start).strftime('%Y-%m-%dT%H:%M:%SZ')
    tf2 = pd.to_datetime(end).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Query data for the current interval
    points = influxdb_orbdata.get_distinct_alt(client_orbdata, tf1, tf2, satellitecode)
    points_df = pd.DataFrame(points)

    # Print the DataFrame to check it
    # print(points_df.to_string())

    return points_df


def get_phase(post_token_url,
              post_token_user_name,
              post_token_password, metedataservice_url, influxdb_orbdata, client_orbdata, satID):
    satellite_od_dict = satellite_properties(post_token_url,
                                             post_token_user_name,
                                             post_token_password, metedataservice_url, satID)
    satellitecode = satellite_od_dict['code']

    filters = 'WHERE _satelliteCode = \'' + satellitecode + '\' '

    # Query data for the current interval
    points = influxdb_orbdata.get_distinct_phase(client_orbdata, filters=filters, limit=1)
    points_df = pd.DataFrame(points)
    # 检查points_df是否为空
    if points_df.empty:
        points_df = pd.DataFrame({
            'time': ['0'],
            'phase': [0],
            '_satelliteCode': [satellitecode]
        })
        return points_df
    else:
        return points_df


def get_phase_new(influxdb_orbdata, client_orbdata):
    filter1 = 'WHERE _satelliteCode = \'GS-2 & GS-2AP01\' '
    filter2 = 'WHERE _satelliteCode = \'GS-2AP01 & GS-2AP02\' '
    filter3 = 'WHERE _satelliteCode = \'GS-2AP02 & GS-2BP01\' '
    filter4 = 'WHERE _satelliteCode = \'GS-2BP01 & GS-2AP03\' '

    # Query data for the current interval
    points1 = influxdb_orbdata.get_distinct_phase_diff(client_orbdata, filters=filter1, limit=1)
    points2 = influxdb_orbdata.get_distinct_phase_diff(client_orbdata, filters=filter2, limit=1)
    points3 = influxdb_orbdata.get_distinct_phase_diff(client_orbdata, filters=filter3, limit=1)
    points4 = influxdb_orbdata.get_distinct_phase_diff(client_orbdata, filters=filter4, limit=1)

    # Convert each result to DataFrame
    points_df1 = pd.DataFrame(points1)
    points_df2 = pd.DataFrame(points2)
    points_df3 = pd.DataFrame(points3)
    points_df4 = pd.DataFrame(points4)

    # Concatenate all DataFrames into one
    points_df = pd.concat([points_df1, points_df2, points_df3, points_df4], ignore_index=True)

    # 检查points_df是否为空
    if points_df.empty:
        points_df = pd.DataFrame({
            'time': ['0'],
            'phase_diff': [0],
            '_satelliteCode': ['0']
        })

    return points_df

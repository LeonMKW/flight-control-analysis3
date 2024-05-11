# -*- coding: UTF-8 -*-
from datetime import datetime, timedelta
from json.decoder import JSONDecodeError
import pandas as pd
import requests
import dfply as d
from utils.flightcontrol_utils import tm_table
import pytz


def satellite_properties(metedataservice_url, satIDs):
    metedataserviceurl = metedataservice_url

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

    res = requests.post(url=metedataserviceurl, json={"query": query2})
    all_info = res.json()["data"]["getAllSpacecraft"]

    satellite_od_dict = {sat["id"]: sat for sat in all_info if sat["id"] in satIDs}

    if satIDs[0] in satellite_od_dict:
        satellite_od_dict = satellite_od_dict[satIDs[0]]
        # print(satellite_od_dict)
        return satellite_od_dict
    else:
        print("ID not found in the dictionary.")
        return None


def od_tmcode(metedataservice_url, satIDs):
    metedataserviceurl = metedataservice_url

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
    res = requests.post(url=metedataserviceurl, json={"query": gnss_info, "variables": variables})

    # Extract relevant data from the response
    data = res.json().get("data", {})
    get_spacecraft_info = data.get("getSpacecraftInfoByID", {})
    determination_configs = get_spacecraft_info.get("determinationConfigs", [])

    # Convert the result to a DataFrame
    satgnssconfig_df = pd.json_normalize(determination_configs, sep='_')  # Assuming you have pandas installed

    if satIDs == 1:
        satgnssconfig_df = satgnssconfig_df.head(1)
    else:
        satgnssconfig_df = satgnssconfig_df.tail(1)

    satgnssconfig_df = satgnssconfig_df.reset_index(drop=True)

    # print(satgnssconfig_df.to_string())

    return satgnssconfig_df


def gnss_get_last(metedataservice_url, _influxdb, client, satIDs):
    satellite_od_dict = satellite_properties(metedataservice_url, satIDs)
    satellitecode = satellite_od_dict['code']
    tm = tm_table(metedataservice_url, satIDs)
    tmversion = tm[satIDs]['tm_version']
    satgnssconfig_df = od_tmcode(metedataservice_url, satIDs)

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


def ephemeris_acquire(orbitserviceurl, metedataservice_url, startAt, endAt, satIDs):
    satellite_od_dict = satellite_properties(metedataservice_url, satIDs)
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
    # print(startAt)
    # print(endAt)
    res = requests.post(url=orbitserviceurl, json={"query": query1, "variables": variables})
    all_ephemeris = res.json()["data"]["getOrbitalElementsList"]['records']
    # print(all_ephemeris)
    orbit_data = pd.DataFrame(all_ephemeris)
    orbit_data['spacecraft'] = orbit_data['spacecraft'].apply(lambda x: x['code'])

    # print(orbit_data.to_string())

    sixelements = orbit_data[(orbit_data['gnssCount'] > 50) & (orbit_data['spacecraft'] == satellitecode)]
    # print(sixelements.to_string())

    return sixelements


def orbitcal_body(satellite_od_dict, ephemeris):
    # ephemeris["epochTimeUTC"] = pd.to_datetime(ephemeris["epochTimeUTC"])  # Convert to datetime
    dt_object = datetime.utcfromtimestamp(ephemeris["timestamp"][0])
    dt_object += timedelta(hours=2)
    # Convert datetime object to string
    new_date_string = dt_object.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]+'Z'

    return {
        "thrust": 0,
        "thrusterWorking": 0,
        "periods": [],
        "step": 1,
        "radiationFlow": 73,
        "startAt": ephemeris["epochTimeUTC"][0],
        "endAt": new_date_string,
        "satelliteWeight": satellite_od_dict["weight"],
        "satelliteArea": satellite_od_dict["surfaceArea"],
        "CD": ephemeris["CD"][0],
        "epochTimeUTC": ephemeris["epochTimeUTC"][0],
        "a": ephemeris["a"][0],
        "e": ephemeris["e"][0],
        "i": ephemeris["i"][0],
        "dw": ephemeris["dw"][0],
        "xw": ephemeris["xw"][0],
        "M": ephemeris["M"][0]
    }

    # Now 'gnssdata' contains the GNSS data


def get_gnss_data(satellite_od_dict, satgnssconfig_df, tmversion, _influxdb, client, tf1, tf2):
    # print(tf1)
    # print(tf2)
    satellitecode = satellite_od_dict['code']
    tm_time = satgnssconfig_df.at[0, 'gpsTimeField']
    tm_x = satgnssconfig_df.at[0, 'xField']
    tm_y = satgnssconfig_df.at[0, 'yField']
    tm_z = satgnssconfig_df.at[0, 'zField']
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

import pandas as pd
from utils.od_utils import satellite_properties, od_tmcode, gnss_get_last, ephemeris_acquire, orbitcal_body, \
    get_gnss_data
from utils.flightcontrol_utils import tm_table
import json
import requests
import pytz
from datetime import datetime, timedelta


def orbit_precision_calculation_step1(metedataservice_url, orbitserviceurl, _influxdb, client, satIDs):
    now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
    endDate = now_utc
    startDate = endDate - timedelta(hours=48)

    tf1 = startDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
    tf2 = endDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
    gnsstime_last = gnss_get_last(metedataservice_url, _influxdb, client, satIDs)
    # print(gnsstime_last)
    sixelements = ephemeris_acquire(orbitserviceurl, metedataservice_url, tf1, tf2, satIDs)
    # print(sixelements.to_string())

    sixelements['epochTime'] = pd.to_datetime(sixelements['epochTimeUTC'], format='%Y-%m-%dT%H:%M:%S.%fZ')
    sixelements['timestamp'] = sixelements['epochTime'].apply(lambda x: x.timestamp()) * 1000
    sixelements['timestamp'] = sixelements['timestamp'] // 1000
    # pd.set_option('display.float_format', lambda x: '%.0f' % x)
    # print(sixelements.to_string())
    # print(sixelements.dtypes)

    # gnss_timelast_datetime = pd.to_datetime(gnsstime_last, unit='s', utc=True)
    ephemeris = sixelements[sixelements['timestamp'] <= gnsstime_last]
    ephemeris = ephemeris.sort_values(by='epochTimeUTC', ascending=False).head(1).reset_index(drop=True)

    # print(ephemeris.to_string())
    ephemeris_dict = ephemeris.to_dict()
    # print(ephemeris_dict)

    if len(ephemeris) == 1:
        print("Ephemeris successfully obtained")
        return ephemeris_dict

    else:
        print("No available ephemeris")


def orbit_precision_calculation_step2_1(satellite_od_dict, ephemeris_dict, _influxdb, client, satIDs,
                                        orbit_prop_url, satgnssconfig_df, tmversion):
    # print(ephemeris_dict)
    ephemeris = pd.DataFrame.from_dict(ephemeris_dict)
    # print(ephemeris.to_string())
    orbitbody = orbitcal_body(satellite_od_dict, ephemeris_dict)
    # orbitbody = json.dumps(orbitbody)

    # starting propagating process
    print(satellite_od_dict['code'] + " orbit propagation starting on ephemeris..." + ephemeris_dict['epochTimeUTC'][0])

    orbit_v2 = orbit_prop_url
    orbitcal_response = requests.post(url=orbit_v2, json=orbitbody)

    if orbitcal_response.status_code >= 400 or orbitcal_response.status_code == 204:
        print(f"orbit_propagation_failed for satellite: {satellite_od_dict['code']}")

    content = json.loads(orbitcal_response.text)
    orbit_cal = content['data']
    orbit_caldf = pd.DataFrame(orbit_cal)
    orbit_caldf = orbit_caldf[['epochTimeUTC',
                               'ecefx',
                               'ecefy',
                               'ecefz']].rename(columns={'ecefx': 'theoretical_x',
                                                         'ecefy': 'theoretical_y',
                                                         'ecefz': 'theoretical_z'})

    orbit_caldf['epochTime'] = pd.to_datetime(orbit_caldf['epochTimeUTC'], format='%Y-%m-%dT%H:%M:%S.%fZ', utc=True)
    orbit_caldf['timestamp'] = orbit_caldf['epochTime'].apply(lambda x: x.timestamp())
    orbit_caldf['timestamp'] = orbit_caldf['timestamp'].astype('int')
    orbit_caldf.drop(['epochTimeUTC', 'epochTime'], axis=1, inplace=True)
    # print(orbit_caldf.to_string())

    dt_object = datetime.utcfromtimestamp(ephemeris_dict["timestamp"][0])
    dt_object += timedelta(hours=24)
    # Convert datetime object to string
    new_date_string = dt_object.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

    result = get_gnss_data(satellite_od_dict, satgnssconfig_df, tmversion, _influxdb, client,
                           ephemeris_dict["epochTimeUTC"][0], new_date_string)
    result.drop(['time', '_satelliteCode'], axis=1, inplace=True)
    pd.set_option('display.float_format', lambda x: '%.11f' % x)
    # print(result.to_string())

    if satIDs == 1:
        result['timestamp'] = result['timestamp'] - 27

    ephemeris_id_value = ephemeris_dict['id'][0]

    merged_df = (pd.merge(orbit_caldf, result, on='timestamp', suffixes=('_theoretical', '_observed'))
                 .pipe(lambda x: x.assign(x_diff=pd.to_numeric(x['theoretical_x']) - pd.to_numeric(x['x'])))
                 .pipe(lambda x: x.assign(y_diff=pd.to_numeric(x['theoretical_y']) - pd.to_numeric(x['y'])))
                 .pipe(lambda x: x.assign(z_diff=pd.to_numeric(x['theoretical_z']) - pd.to_numeric(x['z'])))
                 )

    # print(merged_df.to_string())
    merged_df = (merged_df
                 .assign(theoretical_distance2=lambda x: (x['theoretical_x'].astype(float) ** 2 +
                                                          x['theoretical_y'].astype(float) ** 2 +
                                                          x['theoretical_z'].astype(float) ** 2) ** 0.5)
                 .assign(actual_distance2=lambda x: (x['x'].astype(float) ** 2 +
                                                     x['y'].astype(float) ** 2 +
                                                     x['z'].astype(float) ** 2) ** 0.5)
                 .assign(error=lambda x: abs(x['theoretical_distance2'] - x['actual_distance2']))
                 .assign(ephemeris_id=ephemeris_id_value)
                 )

    # Calculate mean error
    avg2 = merged_df['error'].mean()

    # Calculate error for the first hour
    avg2_init = abs(
        merged_df.at[0, 'theoretical_distance2'] - merged_df.at[0, 'actual_distance2'])

    # Calculate maximum error
    avg2_max = abs(merged_df['theoretical_distance2'] - merged_df['actual_distance2']).max()

    # Create a summary DataFrame
    # ephemeris_id_df = pd.DataFrame({'ephemeris_id': [ephemeris_id_value]})
    orbit_precision_summary = pd.concat([ephemeris,
                                         pd.DataFrame({'mse': [avg2],  # 均方差/轨道精度
                                                       'hour_error': [avg2_init],  # 星历误差/外推1小时均方差
                                                       'max_error': [avg2_max]})], axis=1)  # 外推24小时最大误差

    # print(orbit_precision_evaluate.to_string())
    # print(merged_df.to_string())

    return merged_df, orbit_precision_summary


def check_dict_value_types(input_dict):
    types_dict = {}
    for key, value in input_dict.items():
        types_dict[key] = type(value).__name__
    return types_dict

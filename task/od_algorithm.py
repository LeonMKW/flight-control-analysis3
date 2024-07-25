import pandas as pd
from utils.od_utils import satellite_properties, od_tmcode, gnss_get_last, ephemeris_acquire, orbitcal_body, \
    get_gnss_data, orbitcal_body
from utils.flightcontrol_utils import tm_table
import uuid
import json
import requests
import pytz
from datetime import datetime, timedelta
import logging
import math
import zipfile
import io
import re
from datetime import datetime


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
        logging.info("Ephemeris successfully obtained")
        return ephemeris_dict

    else:
        logging.info("No available ephemeris")


def orbit_precision_calculation_step2_1(satellite_od_dict, ephemeris_dict, _influxdb, client, satIDs,
                                        orbit_prop_url, satgnssconfig_df, tmversion, hours=24):
    # print(ephemeris_dict)
    ephemeris = pd.DataFrame.from_dict(ephemeris_dict)
    # print(ephemeris.to_string())
    orbitbody = orbitcal_body(satellite_od_dict, ephemeris_dict, hours=hours)
    # orbitbody = json.dumps(orbitbody)

    # starting propagating process
    logging.info(
        satellite_od_dict['code'] + " orbit propagation starting on ephemeris..." + ephemeris_dict['epochTimeUTC'][0])

    orbit_v2 = orbit_prop_url
    orbitcal_response = requests.post(url=orbit_v2, json=orbitbody, timeout=300)

    if orbitcal_response.status_code >= 400 or orbitcal_response.status_code == 204:
        logging.info(f"orbit_propagation_failed for satellite: {satellite_od_dict['code']}")

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
    dt_object += timedelta(hours=hours)
    # Convert datetime object to string
    new_date_string = dt_object.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

    result = get_gnss_data(satellite_od_dict, satgnssconfig_df, tmversion, _influxdb, client,
                           ephemeris_dict["epochTimeUTC"][0], new_date_string)
    result.drop(['time', '_satelliteCode'], axis=1, inplace=True)
    pd.set_option('display.float_format', lambda x: '%.11f' % x)
    # print(result.to_string())
    # print(satIDs)
    if satIDs == '1':
        result['timestamp'] = result['timestamp'] - 27

    # print(result.to_string())
    ephemeris_id_value = ephemeris_dict['id'][0]

    merged_df = (pd.merge(orbit_caldf, result, on='timestamp', suffixes=('_theoretical', '_observed'))
                 .pipe(lambda x: x.assign(x_diff=pd.to_numeric(x['theoretical_x']) - pd.to_numeric(x['x'])))
                 .pipe(lambda x: x.assign(y_diff=pd.to_numeric(x['theoretical_y']) - pd.to_numeric(x['y'])))
                 .pipe(lambda x: x.assign(z_diff=pd.to_numeric(x['theoretical_z']) - pd.to_numeric(x['z'])))
                 )

    # print(merged_df.to_string())
    merged_df = (merged_df
                 .assign(theoretical_distance2=lambda x: x[['theoretical_x',
                                                            'theoretical_y',
                                                            'theoretical_z']].astype(float).pow(2).sum(axis=1).apply(
        math.sqrt))
                 .assign(
        actual_distance2=lambda x: x[['x', 'y', 'z']].astype(float).pow(2).sum(axis=1).apply(math.sqrt))
                 .assign(error=lambda x: ((x['theoretical_x'] - x['x']).astype(float) ** 2 +
                                          (x['theoretical_y'] - x['y']).astype(float) ** 2 +
                                          (x['theoretical_z'] - x['theoretical_z']).astype(float) ** 2).apply(
        math.sqrt))
                 .assign(ephemeris_id=ephemeris_id_value)
                 )
    # print(merged_df.to_string())

    # Calculate mean error
    avg2 = merged_df['error'].mean()

    # Calculate the initial average difference
    avg2_init = math.sqrt((merged_df.at[0, 'theoretical_x'] - merged_df.at[0, 'x']) ** 2 +
                          (merged_df.at[0, 'theoretical_y'] - merged_df.at[0, 'y']) ** 2 +
                          (merged_df.at[0, 'theoretical_z'] - merged_df.at[0, 'z']) ** 2)

    # Calculate the maximum error
    avg2_max = merged_df['error'].max()

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


# used for od comparision
def get_Post_Satellite_Report_Info(post_satellite_report_search_url, satelliteId, reportTypes, beginTime, endTime,
                                   states):
    # Construct the JSON body
    payload = {
        "satelliteId": satelliteId,
        "reportTypes": reportTypes,
        "beginTime": beginTime,
        "endTime": endTime,
        "states": states
    }

    # Make the HTTP POST request
    response = requests.post(post_satellite_report_search_url, json=payload)

    # Check if the request was successful
    if response.status_code == 200:
        # print(response.json())
        return response.json()
    else:
        response.raise_for_status()


def extract_file_ids(report_info):
    file_ids = []
    if report_info['code'] == 0:
        for report in report_info['data']['satelliteReportInfoList']:
            file_ids.append(report['fileId'])
    return file_ids


def parse_xml_content(xml_content):
    xml_data = {}
    epo_date = re.search(r'<EpoDate>(.*?)</EpoDate>', xml_content).group(1)
    epo_time = re.search(r'<EpoTime>(.*?)</EpoTime>', xml_content).group(1)
    beijing_time_str = f"{epo_date} {epo_time}"
    beijing_time = datetime.strptime(beijing_time_str, "%Y-%m-%d %H:%M:%S.%f")
    utc_timestamp = int(beijing_time.timestamp() * 1000)

    xml_data['epochutctimestamp'] = utc_timestamp
    xml_data['a'] = re.search(r'<Axis>(.*?)</Axis>', xml_content).group(1)
    xml_data['e'] = re.search(r'<Eccentricity>(.*?)</Eccentricity>', xml_content).group(1)
    xml_data['i'] = re.search(r'<Inclination>(.*?)</Inclination>', xml_content).group(1)
    xml_data['dw'] = re.search(r'<RAAN>(.*?)</RAAN>', xml_content).group(1)
    xml_data['xw'] = re.search(r'<ArgOfPer>(.*?)</ArgOfPer>', xml_content).group(1)
    xml_data['M'] = re.search(r'<MeanAn>(.*?)</MeanAn>', xml_content).group(1)
    xml_data['CD'] = re.search(r'<CDSM>(.*?)</CDSM>', xml_content).group(1)
    return xml_data


def parse_txt_content(txt_content):
    data_start = txt_content.index("DATA_START") + len("DATA_START")
    data_stop = txt_content.index("DATA_STOP")
    data_lines = txt_content[data_start:data_stop].strip().split('\n')

    data_entries = []
    for line in data_lines:
        columns = line.split()
        beijing_time = datetime.strptime(columns[0], "%Y-%m-%dT%H:%M:%S.%f0")
        utc_timestamp = int(beijing_time.timestamp() * 1000)

        data_entry = {
            'utctimestamp': utc_timestamp,
            'x': columns[1],
            'y': columns[2],
            'z': columns[3],
            'vx': columns[4],
            'vy': columns[5],
            'vz': columns[6]
        }
        data_entries.append(data_entry)

    return data_entries


def download_and_extract_zip(get_satellite_file_download_url, file_id):
    url = f"{get_satellite_file_download_url}?fileId={file_id}"
    response = requests.get(url)
    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            files_data = {}
            for file_name in zip_ref.namelist():
                with zip_ref.open(file_name) as file:
                    content = file.read().decode('utf-8')
                    if file_name.endswith('.xml'):
                        files_data['xml'] = parse_xml_content(content)
                    elif file_name.endswith('.txt'):
                        files_data['txt'] = parse_txt_content(content)
            return files_data
    else:
        response.raise_for_status()


def get_satellite_report_files(post_satellite_report_search_url, get_satellite_file_download_url, satelliteId,
                               reportTypes, beginTime, endTime, states):
    report_info = get_Post_Satellite_Report_Info(post_satellite_report_search_url, satelliteId, reportTypes, beginTime,
                                                 endTime, states)
    file_ids = extract_file_ids(report_info)
    all_files_data = []

    for file_id in file_ids:
        files_data = download_and_extract_zip(get_satellite_file_download_url, file_id)
        all_files_data.append(files_data)

    # print(all_files_data)

    return json.dumps(all_files_data, indent=4)


# def timestamp2iso8601(timestamp):
#     # 将毫秒转换为秒
#     timestamp_s = timestamp / 1000
#     # 创建一个表示1970年1月1日的UTC时间的datetime对象
#     epoch = datetime.utcfromtimestamp(0)
#     # 将时间戳的秒数加到epoch上
#     dt_object = epoch + timedelta(seconds=timestamp_s)
#     # 格式化为ISO 8601格式的字符串
#     iso8601tz = dt_object.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
#     return iso8601tz


def convert_json_format(json_data):
    # 创建一个新的字典来存储转换后的数据
    new_format_data = {}

    # 遍历原始JSON数据的键和值
    for key, value in json_data.items():
        # 检查值是否是列表，并且列表中只有一个元素
        if isinstance(value, list) and len(value) == 1:
            # 如果是，将列表中的元素转换为字典，键为0
            new_format_data[key] = {0: value[0]}
        elif isinstance(value, str) or isinstance(value, (int, float)):
            # 如果值是字符串、整数或浮点数，直接转换为字典，键为0
            new_format_data[key] = {0: value}
        else:
            # 如果是其他类型，可能需要特殊处理，这里直接跳过
            continue

    # 使用传入的 id 字段，如果不存在则添加默认的 id 字段
    if 'id' not in new_format_data:
        new_format_data['id'] = {0: json_data.get('id', str(uuid.uuid4()))}

    return new_format_data


def calculate_average_error_per_chunk(merged_df, chunk_size=1450):
    # Ensure the DataFrame columns are in the correct numeric format
    merged_df['error'] = pd.to_numeric(merged_df['error'])

    # Calculate the number of chunks
    num_chunks = len(merged_df) // chunk_size
    if len(merged_df) % chunk_size != 0:
        num_chunks += 1

    average_errors = []

    for i in range(num_chunks):
        # Get the start and end indices for the current chunk
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size

        # Slice the DataFrame to get the current chunk
        chunk_df = merged_df.iloc[start_idx:end_idx]

        # Calculate the average error for the current chunk
        average_error = chunk_df['error'].mean()

        # Append the average error to the results list
        average_errors.append(average_error)

    return average_errors


def propagating_2nd_predictive_ephemeris(mete_data_service, post_satellite_report_search_url,
                                         get_satellite_file_download_url, satelliteId,
                                         reportTypes, beginTime, endTime, states, _influxdb, client, orbit_prop_url,
                                         propagation_hours):
    reporting_orbit_data = get_satellite_report_files(post_satellite_report_search_url,
                                                      get_satellite_file_download_url,
                                                      satelliteId, reportTypes,
                                                      beginTime, endTime, states)
    reporting_orbit_data = json.loads(reporting_orbit_data)

    for report in reporting_orbit_data:
        ephemeris_dict = report["xml"]
        ephemeris_dict["timestamp"] = [ephemeris_dict["epochutctimestamp"] / 1000]
        ephemeris_dict["epochTimeUTC"] = [
            datetime.utcfromtimestamp(ephemeris_dict["epochutctimestamp"] / 1000).strftime('%Y-%m-%dT%H:%M:%S.%f')[
            :-3] + 'Z']
        ephemeris_dict = convert_json_format(ephemeris_dict)
        satellite_od_dict = satellite_properties(metedataservice_url=mete_data_service, satIDs=satelliteId)
        satgnssconfig_df = od_tmcode(metedataservice_url=mete_data_service, satIDs=satelliteId)
        tm = tm_table(metedataservice_url=mete_data_service, satIDs=satelliteId)
        tmversion = tm[satelliteId]['tm_version']

        merged_df, orbit_precision_summary = orbit_precision_calculation_step2_1(satellite_od_dict,
                                                                                 ephemeris_dict,
                                                                                 _influxdb=_influxdb, client=client,
                                                                                 satIDs=satelliteId,
                                                                                 orbit_prop_url=orbit_prop_url,
                                                                                 satgnssconfig_df=satgnssconfig_df,
                                                                                 tmversion=tmversion,
                                                                                 hours=propagation_hours)

        # Calculate average error per chunk
        average_errors = calculate_average_error_per_chunk(merged_df, chunk_size=725)

        # Convert the DataFrames and average errors to JSON format
        merged_df_json = merged_df.to_json(orient='records')
        orbit_precision_summary_json = orbit_precision_summary.to_json(orient='records')
        average_errors_json = json.dumps(average_errors)

        # Append the JSON data to the report
        report["merged_df"] = json.loads(merged_df_json)
        report["orbit_precision_summary"] = json.loads(orbit_precision_summary_json)
        print(orbit_precision_summary_json)
        report["average_errors"] = json.loads(average_errors_json)
        print(average_errors_json)

    # Combine all reports into a single JSON object
    combined_json = json.dumps(reporting_orbit_data, indent=4)

    return combined_json

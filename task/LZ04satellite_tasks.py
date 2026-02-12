import json
import pandas as pd
import pytz
import logging
from utils.flightcontrol_utils import get_task_list,commands
from utils.LZ04satellitestatus_utils import get_LZ04_tmkp202, get_LZ04_tmz009, get_LZ04_hdi_switches, \
get_LZ04_tmz012, get_LZ04_dwi_switches,get_LZ04_tmz015,get_LZ04_tops_switches,get_LZ04_fields_df


LZ04_PAYLOAD_CONFIG = {
    "HDI": {
        "name": "HDI",
        "app_code": "TMH4538",
        "aocs_code": "TMKS700",
        "record_code": "TMZ009",
        "memory_code": "TMZ011",
    },
    "DWI": {
        "name": "DWI",
        "app_code": "TMH4539",
        "aocs_code": "TMKS600",
        "record_code": "TMZ012",
        "memory_code": "TMZ014",
    },
    "TOPS": {
        "name": "TOPS",
        "app_code": "TMH4540",
        "aocs_code": "TMKS400",
        "record_code": "TMZ015",
        "memory_code": "TMZ017",
    }
}


def _first_non_zero_non_nan(series):
    if series is None:
        return None
    s = pd.to_numeric(pd.Series(series), errors='coerce').dropna()
    for v in s.tolist():
        vi = int(v)
        if vi != 0:
            return vi
    return None


def _last_non_nan(series):
    if series is None:
        return None
    s = pd.to_numeric(pd.Series(series), errors='coerce').dropna()
    if s.empty:
        return None
    return int(s.iloc[-1])


def LZ04_hdi_task(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  orbit_service,
                  metedataservice_url,
                  _influxdb,
                  client,
                  tf1,
                  tf2,
                  satID):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    task_list = get_task_list(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service,
        tf1,
        tf2,
        satID
    )

    if not isinstance(task_list, pd.DataFrame) or task_list.empty:
        return json.dumps({"HDI": {}, "Error": "No task_list"}, ensure_ascii=False)

    # TMZ009
    tmz009_df = get_LZ04_tmz009(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if tmz009_df is None or tmz009_df.empty:
        tmz009_df = pd.DataFrame(columns=['time', 'TMZ009'])
    else:
        tmz009_df['time'] = pd.to_datetime(tmz009_df['time'], utc=True, errors='coerce')
        tmz009_df = tmz009_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        if 'TMZ009' not in tmz009_df.columns:
            tmz009_df['TMZ009'] = pd.NA
        tmz009_df['TMZ009'] = pd.to_numeric(tmz009_df['TMZ009'], errors='coerce')

    # TMZ011
    tmz011_df = get_LZ04_fields_df(
        post_token_url, post_token_user_name, post_token_password,
        metedataservice_url, _influxdb, client,
        tf1, tf2, satID,
        fields=['TMZ011']
    )
    if tmz011_df is None or tmz011_df.empty:
        tmz011_df = pd.DataFrame(columns=['time', 'TMZ011'])
    else:
        tmz011_df['time'] = pd.to_datetime(tmz011_df['time'], utc=True, errors='coerce')
        tmz011_df = tmz011_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        if 'TMZ011' not in tmz011_df.columns:
            tmz011_df['TMZ011'] = pd.NA
        tmz011_df['TMZ011'] = pd.to_numeric(tmz011_df['TMZ011'], errors='coerce')

    # switches (TMH4538 / TMKS700)  —— 注意：这里要保留 NaN，不能 fill 0
    sw_df = get_LZ04_hdi_switches(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if sw_df is None or sw_df.empty:
        sw_df = pd.DataFrame(columns=['time', 'TMH4538', 'TMKS700'])
    else:
        sw_df['time'] = pd.to_datetime(sw_df['time'], utc=True, errors='coerce')
        sw_df = sw_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    # TMKP202 orbit no
    tmkp202_df = get_LZ04_tmkp202(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if tmkp202_df is None or tmkp202_df.empty:
        tmkp202_df = pd.DataFrame(columns=['time', 'TMKP202'])
    else:
        tmkp202_df['time'] = pd.to_datetime(tmkp202_df['time'], utc=True, errors='coerce')
        tmkp202_df = tmkp202_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    result = {"HDI": {}}

    prev_tmz011_last = None
    prev_orbit_no = None

    for idx in range(len(task_list)):
        mission_id = task_list['mission_id'].iat[idx]
        start_dt = pd.to_datetime(task_list['starting'].iat[idx], utc=True)
        end_dt   = pd.to_datetime(task_list['ending'].iat[idx], utc=True)

        # 1) switches: 任务窗内分别取第一条“非NaN”
        sw_win = sw_df[(sw_df['time'] >= start_dt) & (sw_df['time'] <= end_dt)]

        app_series  = sw_win['TMH4538'].dropna() if 'TMH4538' in sw_win.columns else pd.Series(dtype=float)
        aocs_series = sw_win['TMKS700'].dropna() if 'TMKS700' in sw_win.columns else pd.Series(dtype=float)

        app_on  = int(app_series.iloc[0])  if not app_series.empty  else None
        aocs_on = int(aocs_series.iloc[0]) if not aocs_series.empty else None

        switches_on = (app_on == 1 and aocs_on == 1)

        # 2) TMZ009 => HDI record_no
        if not switches_on:
            hdi_status = "off"
            hdi_no = 0
            last_tmz009 = "skip"
        else:
            df_tmz = tmz009_df[(tmz009_df['time'] >= start_dt) & (tmz009_df['time'] <= end_dt)]
            if df_tmz.empty:
                hdi_status = "nodata"
                hdi_no = None
                last_tmz009 = "nodata"
            else:
                vals = pd.to_numeric(df_tmz['TMZ009'], errors='coerce').dropna().tolist()
                if not vals:
                    hdi_status = "nodata"
                    hdi_no = None
                    last_tmz009 = "nodata"
                else:
                    last_tmz009 = int(vals[-1])
                    if all(int(v) == 0 for v in vals):
                        hdi_status = "off"
                        hdi_no = 0
                    else:
                        hdi_status = "on"
                        hdi_no = last_tmz009

        # 2.1) TMZ011 memory values in window
        df_mem = tmz011_df[(tmz011_df['time'] >= start_dt) & (tmz011_df['time'] <= end_dt)]
        if df_mem.empty:
            tmz011_first_non_zero = None
            tmz011_last_non_nan = None
        else:
            mem_vals = df_mem['TMZ011'] if 'TMZ011' in df_mem.columns else pd.Series(dtype=float)
            tmz011_first_non_zero = _first_non_zero_non_nan(mem_vals)
            tmz011_last_non_nan = _last_non_nan(mem_vals)

        # 3) TMKP202 orbit no（取任务窗内最后一个值）
        df_orb = tmkp202_df[(tmkp202_df['time'] >= start_dt) & (tmkp202_df['time'] <= end_dt)]
        if df_orb.empty:
            orbit_no = None
        else:
            orbit_no = int(df_orb['TMKP202'].iloc[-1])

        # 4) delta vs previous (current first_non_zero_nan - previous last_non_nan)
        if idx == 0 or prev_tmz011_last is None or tmz011_first_non_zero is None:
            delta_vs_prev = "nodata"
            delta_tmz011 = "nodata"
        else:
            delta_vs_prev = "ok"
            delta_tmz011 = tmz011_first_non_zero - prev_tmz011_last

        if idx == 0 or prev_orbit_no is None or orbit_no is None:
            delta_orbit = "nodata"
        else:
            delta_orbit = orbit_no - prev_orbit_no

        delta_block = {
            "delta_vs_prev": delta_vs_prev,
            "delta_TMKP202": delta_orbit,
            "delta_TMZ011": delta_tmz011
        }

        # 更新 prev（只在当前值非 None 时更新）
        if tmz011_last_non_nan is not None:
            prev_tmz011_last = tmz011_last_non_nan
        if orbit_no is not None:
            prev_orbit_no = orbit_no

        task_payload = {
            "mission_id": mission_id,
            "satellite_code": task_list['satellite_code'].iat[idx] if 'satellite_code' in task_list.columns else "",
            "station_name": task_list['station_name'].iat[idx] if 'station_name' in task_list.columns else "",
            "device": task_list['device'].iat[idx] if 'device' in task_list.columns else "",
            "company_name": task_list['company_name'].iat[idx] if 'company_name' in task_list.columns else "",
            "remark": task_list['remark'].iat[idx] if 'remark' in task_list.columns else "",
            "starting": int(start_dt.timestamp() * 1000),
            "ending": int(end_dt.timestamp() * 1000),

            "switches": {
                "TMH4538_app": app_on if app_on is not None else "nodata",
                "TMKS700_aocs": aocs_on if aocs_on is not None else "nodata",
                "both_on": int(switches_on)
            },

            "TMKP202_orbit_no": orbit_no if orbit_no is not None else "nodata",

            "HDI": {
                "status": hdi_status,
                "record_no": hdi_no if hdi_no is not None else "nodata",
                "last_tmz009": last_tmz009,
                "first_tmz011_non_zero_nan": tmz011_first_non_zero if tmz011_first_non_zero is not None else "nodata",
                "last_tmz011_non_nan": tmz011_last_non_nan if tmz011_last_non_nan is not None else "nodata"
            },

            "orbit_and_hdi_delta_vs_prev": delta_block
        }

        result["HDI"][f"Task_{idx+1}"] = task_payload

    return json.dumps(result, ensure_ascii=False, indent=4)


def LZ04_dwi_task(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  orbit_service,
                  metedataservice_url,
                  _influxdb,
                  client,
                  tf1,
                  tf2,
                  satID):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    task_list = get_task_list(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service,
        tf1,
        tf2,
        satID
    )

    if not isinstance(task_list, pd.DataFrame) or task_list.empty:
        return json.dumps({"DWI": {}, "Error": "No task_list"}, ensure_ascii=False)

    # TMZ012
    tmz012_df = get_LZ04_tmz012(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if tmz012_df is None or tmz012_df.empty:
        tmz012_df = pd.DataFrame(columns=['time', 'TMZ012'])
    else:
        tmz012_df['time'] = pd.to_datetime(tmz012_df['time'], utc=True, errors='coerce')
        tmz012_df = tmz012_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        if 'TMZ012' not in tmz012_df.columns:
            tmz012_df['TMZ012'] = pd.NA
        tmz012_df['TMZ012'] = pd.to_numeric(tmz012_df['TMZ012'], errors='coerce')

    # TMZ014
    tmz014_df = get_LZ04_fields_df(
        post_token_url, post_token_user_name, post_token_password,
        metedataservice_url, _influxdb, client,
        tf1, tf2, satID,
        fields=['TMZ014']
    )
    if tmz014_df is None or tmz014_df.empty:
        tmz014_df = pd.DataFrame(columns=['time', 'TMZ014'])
    else:
        tmz014_df['time'] = pd.to_datetime(tmz014_df['time'], utc=True, errors='coerce')
        tmz014_df = tmz014_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        if 'TMZ014' not in tmz014_df.columns:
            tmz014_df['TMZ014'] = pd.NA
        tmz014_df['TMZ014'] = pd.to_numeric(tmz014_df['TMZ014'], errors='coerce')

    # switches (TMH4539 / TMKS600) —— 保留 NaN，不能 fill 0
    sw_df = get_LZ04_dwi_switches(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if sw_df is None or sw_df.empty:
        sw_df = pd.DataFrame(columns=['time', 'TMH4539', 'TMKS600'])
    else:
        sw_df['time'] = pd.to_datetime(sw_df['time'], utc=True, errors='coerce')
        sw_df = sw_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    # TMKP202 orbit no（复用同一个函数）
    tmkp202_df = get_LZ04_tmkp202(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if tmkp202_df is None or tmkp202_df.empty:
        tmkp202_df = pd.DataFrame(columns=['time', 'TMKP202'])
    else:
        tmkp202_df['time'] = pd.to_datetime(tmkp202_df['time'], utc=True, errors='coerce')
        tmkp202_df = tmkp202_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    result = {"DWI": {}}

    prev_tmz014_last = None
    prev_orbit_no = None

    for idx in range(len(task_list)):
        mission_id = task_list['mission_id'].iat[idx]
        start_dt = pd.to_datetime(task_list['starting'].iat[idx], utc=True)
        end_dt   = pd.to_datetime(task_list['ending'].iat[idx], utc=True)

        # 1) switches: 任务窗内分别取第一条“非NaN”
        sw_win = sw_df[(sw_df['time'] >= start_dt) & (sw_df['time'] <= end_dt)]

        app_series  = sw_win['TMH4539'].dropna() if 'TMH4539' in sw_win.columns else pd.Series(dtype=float)
        aocs_series = sw_win['TMKS600'].dropna() if 'TMKS600' in sw_win.columns else pd.Series(dtype=float)

        app_on  = int(app_series.iloc[0])  if not app_series.empty  else None
        aocs_on = int(aocs_series.iloc[0]) if not aocs_series.empty else None

        switches_on = (app_on == 1 and aocs_on == 1)

        # 2) TMZ012 => DWI record_no
        if not switches_on:
            dwi_status = "off"
            dwi_no = 0
            last_tmz012 = "skip"
        else:
            df_tmz = tmz012_df[(tmz012_df['time'] >= start_dt) & (tmz012_df['time'] <= end_dt)]
            if df_tmz.empty:
                dwi_status = "nodata"
                dwi_no = None
                last_tmz012 = "nodata"
            else:
                vals = pd.to_numeric(df_tmz['TMZ012'], errors='coerce').dropna().tolist()
                if not vals:
                    dwi_status = "nodata"
                    dwi_no = None
                    last_tmz012 = "nodata"
                else:
                    last_tmz012 = int(vals[-1])
                    if all(int(v) == 0 for v in vals):
                        dwi_status = "off"
                        dwi_no = 0
                    else:
                        dwi_status = "on"
                        dwi_no = last_tmz012

        # 2.1) TMZ014 memory values in window
        df_mem = tmz014_df[(tmz014_df['time'] >= start_dt) & (tmz014_df['time'] <= end_dt)]
        if df_mem.empty:
            tmz014_first_non_zero = None
            tmz014_last_non_nan = None
        else:
            mem_vals = df_mem['TMZ014'] if 'TMZ014' in df_mem.columns else pd.Series(dtype=float)
            tmz014_first_non_zero = _first_non_zero_non_nan(mem_vals)
            tmz014_last_non_nan = _last_non_nan(mem_vals)

        # 3) TMKP202 orbit no（取任务窗内最后一个值）
        df_orb = tmkp202_df[(tmkp202_df['time'] >= start_dt) & (tmkp202_df['time'] <= end_dt)]
        if df_orb.empty:
            orbit_no = None
        else:
            orbit_no = int(df_orb['TMKP202'].iloc[-1])

        # 4) delta vs previous (current first_non_zero_nan - previous last_non_nan)
        if idx == 0 or prev_tmz014_last is None or tmz014_first_non_zero is None:
            delta_vs_prev = "nodata"
            delta_tmz014 = "nodata"
        else:
            delta_vs_prev = "ok"
            delta_tmz014 = tmz014_first_non_zero - prev_tmz014_last

        if idx == 0 or prev_orbit_no is None or orbit_no is None:
            delta_orbit = "nodata"
        else:
            delta_orbit = orbit_no - prev_orbit_no

        delta_block = {
            "delta_vs_prev": delta_vs_prev,
            "delta_TMKP202": delta_orbit,
            "delta_TMZ014": delta_tmz014
        }

        # 更新 prev（只在当前值非 None 时更新）
        if tmz014_last_non_nan is not None:
            prev_tmz014_last = tmz014_last_non_nan
        if orbit_no is not None:
            prev_orbit_no = orbit_no

        task_payload = {
            "mission_id": mission_id,
            "satellite_code": task_list['satellite_code'].iat[idx] if 'satellite_code' in task_list.columns else "",
            "station_name": task_list['station_name'].iat[idx] if 'station_name' in task_list.columns else "",
            "device": task_list['device'].iat[idx] if 'device' in task_list.columns else "",
            "company_name": task_list['company_name'].iat[idx] if 'company_name' in task_list.columns else "",
            "remark": task_list['remark'].iat[idx] if 'remark' in task_list.columns else "",
            "starting": int(start_dt.timestamp() * 1000),
            "ending": int(end_dt.timestamp() * 1000),

            "switches": {
                "TMH4539_app": app_on if app_on is not None else "nodata",
                "TMKS600_aocs": aocs_on if aocs_on is not None else "nodata",
                "both_on": int(switches_on)
            },

            "TMKP202_orbit_no": orbit_no if orbit_no is not None else "nodata",

            "DWI": {
                "status": dwi_status,
                "record_no": dwi_no if dwi_no is not None else "nodata",
                "last_tmz012": last_tmz012,
                "first_tmz014_non_zero_nan": tmz014_first_non_zero if tmz014_first_non_zero is not None else "nodata",
                "last_tmz014_non_nan": tmz014_last_non_nan if tmz014_last_non_nan is not None else "nodata"
            },

            "orbit_and_dwi_delta_vs_prev": delta_block
        }

        result["DWI"][f"Task_{idx+1}"] = task_payload

    return json.dumps(result, ensure_ascii=False, indent=4)


def LZ04_tops_task(post_token_url,
                   post_token_user_name,
                   post_token_password,
                   orbit_service,
                   metedataservice_url,
                   _influxdb,
                   client,
                   tf1,
                   tf2,
                   satID):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    task_list = get_task_list(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service,
        tf1,
        tf2,
        satID
    )

    if not isinstance(task_list, pd.DataFrame) or task_list.empty:
        return json.dumps({"TOPS": {}, "Error": "No task_list"}, ensure_ascii=False)

    # switches
    sw_df = get_LZ04_tops_switches(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if sw_df is None or sw_df.empty:
        sw_df = pd.DataFrame(columns=['time', 'TMH4540', 'TMKS400'])
    else:
        sw_df['time'] = pd.to_datetime(sw_df['time'], utc=True, errors='coerce')
        sw_df = sw_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    # record TMZ015
    tmz015_df = get_LZ04_tmz015(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if tmz015_df is None or tmz015_df.empty:
        tmz015_df = pd.DataFrame(columns=['time', 'TMZ015'])
    else:
        tmz015_df['time'] = pd.to_datetime(tmz015_df['time'], utc=True, errors='coerce')
        tmz015_df = tmz015_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        if 'TMZ015' not in tmz015_df.columns:
            tmz015_df['TMZ015'] = pd.NA
        tmz015_df['TMZ015'] = pd.to_numeric(tmz015_df['TMZ015'], errors='coerce')

    # TMZ017
    tmz017_df = get_LZ04_fields_df(
        post_token_url, post_token_user_name, post_token_password,
        metedataservice_url, _influxdb, client,
        tf1, tf2, satID,
        fields=['TMZ017']
    )
    if tmz017_df is None or tmz017_df.empty:
        tmz017_df = pd.DataFrame(columns=['time', 'TMZ017'])
    else:
        tmz017_df['time'] = pd.to_datetime(tmz017_df['time'], utc=True, errors='coerce')
        tmz017_df = tmz017_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        if 'TMZ017' not in tmz017_df.columns:
            tmz017_df['TMZ017'] = pd.NA
        tmz017_df['TMZ017'] = pd.to_numeric(tmz017_df['TMZ017'], errors='coerce')

    # orbit TMKP202（复用你已有的）
    tmkp202_df = get_LZ04_tmkp202(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if tmkp202_df is None or tmkp202_df.empty:
        tmkp202_df = pd.DataFrame(columns=['time', 'TMKP202'])
    else:
        tmkp202_df['time'] = pd.to_datetime(tmkp202_df['time'], utc=True, errors='coerce')
        tmkp202_df = tmkp202_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    result = {"TOPS": {}}

    prev_tmz017_last = None
    prev_orbit_no = None

    for idx in range(len(task_list)):
        mission_id = task_list['mission_id'].iat[idx]
        start_dt = pd.to_datetime(task_list['starting'].iat[idx], utc=True)
        end_dt   = pd.to_datetime(task_list['ending'].iat[idx], utc=True)

        # 1) switches: first non-NaN in window
        sw_win = sw_df[(sw_df['time'] >= start_dt) & (sw_df['time'] <= end_dt)]

        app_series  = sw_win['TMH4540'].dropna() if 'TMH4540' in sw_win.columns else pd.Series(dtype=float)
        aocs_series = sw_win['TMKS400'].dropna() if 'TMKS400' in sw_win.columns else pd.Series(dtype=float)

        app_on  = int(app_series.iloc[0])  if not app_series.empty  else None
        aocs_on = int(aocs_series.iloc[0]) if not aocs_series.empty else None

        switches_on = (app_on == 1 and aocs_on == 1)

        # 2) TMZ015 record
        if not switches_on:
            tops_status = "off"
            rec_no = 0
            last_tmz015 = "skip"
        else:
            df_rec = tmz015_df[(tmz015_df['time'] >= start_dt) & (tmz015_df['time'] <= end_dt)]
            if df_rec.empty:
                tops_status = "nodata"
                rec_no = None
                last_tmz015 = "nodata"
            else:
                vals = pd.to_numeric(df_rec['TMZ015'], errors='coerce').dropna().tolist()
                if not vals:
                    tops_status = "nodata"
                    rec_no = None
                    last_tmz015 = "nodata"
                else:
                    last_tmz015 = int(vals[-1])
                    if all(int(v) == 0 for v in vals):
                        tops_status = "off"
                        rec_no = 0
                    else:
                        tops_status = "on"
                        rec_no = last_tmz015

        # 2.1) TMZ017 memory values in window
        df_mem = tmz017_df[(tmz017_df['time'] >= start_dt) & (tmz017_df['time'] <= end_dt)]
        if df_mem.empty:
            tmz017_first_non_zero = None
            tmz017_last_non_nan = None
        else:
            mem_vals = df_mem['TMZ017'] if 'TMZ017' in df_mem.columns else pd.Series(dtype=float)
            tmz017_first_non_zero = _first_non_zero_non_nan(mem_vals)
            tmz017_last_non_nan = _last_non_nan(mem_vals)

        # 3) orbit no
        df_orb = tmkp202_df[(tmkp202_df['time'] >= start_dt) & (tmkp202_df['time'] <= end_dt)]
        orbit_no = int(df_orb['TMKP202'].iloc[-1]) if not df_orb.empty else None

        # 4) delta vs prev (current first_non_zero_nan - previous last_non_nan)
        if idx == 0 or prev_tmz017_last is None or tmz017_first_non_zero is None:
            delta_vs_prev = "nodata"
            delta_tmz017 = "nodata"
        else:
            delta_vs_prev = "ok"
            delta_tmz017 = tmz017_first_non_zero - prev_tmz017_last

        if idx == 0 or prev_orbit_no is None or orbit_no is None:
            delta_orbit = "nodata"
        else:
            delta_orbit = orbit_no - prev_orbit_no

        delta_block = {
            "delta_vs_prev": delta_vs_prev,
            "delta_TMKP202": delta_orbit,
            "delta_TMZ017": delta_tmz017
        }

        if tmz017_last_non_nan is not None:
            prev_tmz017_last = tmz017_last_non_nan
        if orbit_no is not None:
            prev_orbit_no = orbit_no

        task_payload = {
            "mission_id": mission_id,
            "satellite_code": task_list['satellite_code'].iat[idx] if 'satellite_code' in task_list.columns else "",
            "station_name": task_list['station_name'].iat[idx] if 'station_name' in task_list.columns else "",
            "device": task_list['device'].iat[idx] if 'device' in task_list.columns else "",
            "company_name": task_list['company_name'].iat[idx] if 'company_name' in task_list.columns else "",
            "remark": task_list['remark'].iat[idx] if 'remark' in task_list.columns else "",
            "starting": int(start_dt.timestamp() * 1000),
            "ending": int(end_dt.timestamp() * 1000),

            "switches": {
                "TMH4540_app": app_on if app_on is not None else "nodata",
                "TMKS400_aocs": aocs_on if aocs_on is not None else "nodata",
                "both_on": int(switches_on)
            },

            "TMKP202_orbit_no": orbit_no if orbit_no is not None else "nodata",

            "TOPS": {
                "status": tops_status,
                "record_no": rec_no if rec_no is not None else "nodata",
                "last_tmz015": last_tmz015,
                "first_tmz017_non_zero_nan": tmz017_first_non_zero if tmz017_first_non_zero is not None else "nodata",
                "last_tmz017_non_nan": tmz017_last_non_nan if tmz017_last_non_nan is not None else "nodata"
            },

            "orbit_and_tops_delta_vs_prev": delta_block
        }

        result["TOPS"][f"Task_{idx+1}"] = task_payload

    return json.dumps(result, ensure_ascii=False, indent=4)


def LZ04_payload_task(post_token_url,
                      post_token_user_name,
                      post_token_password,
                      orbit_service,
                      metedataservice_url,
                      _influxdb,
                      client,
                      influxdb_action,
                      client_action,
                      satID,
                      tf1,
                      tf2,
                      mode="HDI"):
    """
    mode: HDI / DWI / TOPS

    新增逻辑：
    - 引入 memory_code（HDI:TMZ011 / DWI:TMZ014 / TOPS:TMZ017）
    - 状态扩展：on / off / nodata / idle
    - 异常检测：memory==0 且 record存在非0（按你描述，这是 anomal）
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    mode = (mode or "HDI").upper().strip()
    if mode not in LZ04_PAYLOAD_CONFIG:
        return json.dumps({"Error": f"Invalid mode: {mode}. Use HDI/DWI/TOPS"}, ensure_ascii=False)

    cfg = LZ04_PAYLOAD_CONFIG[mode]
    app_code = cfg["app_code"]
    aocs_code = cfg["aocs_code"]
    record_code = cfg["record_code"]
    memory_code = cfg["memory_code"]

    task_list = get_task_list(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service,
        tf1,
        tf2,
        satID
    )
    if not isinstance(task_list, pd.DataFrame) or task_list.empty:
        return json.dumps(
            {"mode": mode, "satID": satID, "tf1": tf1, "tf2": tf2, "tasks": [], "summary": {"total_tasks": 0}},
            ensure_ascii=False
        )

    cmd_df = commands(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=influxdb_action,  # 注意：你函数参数里现在还没有 influxdb_action/client_action，需要补上
        client=client_action,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )

    # 1) switches（保留 NaN）
    sw_df = get_LZ04_fields_df(
        post_token_url, post_token_user_name, post_token_password,
        metedataservice_url, _influxdb, client,
        tf1, tf2, satID,
        fields=[app_code, aocs_code]
    )

    # 2) record + memory（这里允许 NaN -> 0，便于判断“全0”）
    rm_df = get_LZ04_fields_df(
        post_token_url, post_token_user_name, post_token_password,
        metedataservice_url, _influxdb, client,
        tf1, tf2, satID,
        fields=[record_code, memory_code]
    )
    if record_code not in rm_df.columns:
        rm_df[record_code] = 0
    if memory_code not in rm_df.columns:
        rm_df[memory_code] = pd.NA

    rm_df[record_code] = pd.to_numeric(rm_df[record_code], errors='coerce').fillna(0).astype(int)
    # memory：保留 NaN 以便“first non-NaN”判定；但也提供一个 fill0 的版本给统计
    rm_df[memory_code] = pd.to_numeric(rm_df[memory_code], errors='coerce')  # keep NaN

    # 3) orbit：TMKP202（复用你已有的）
    tmkp202_df = get_LZ04_tmkp202(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if tmkp202_df is None or tmkp202_df.empty:
        tmkp202_df = pd.DataFrame(columns=['time', 'TMKP202'])
    else:
        tmkp202_df['time'] = pd.to_datetime(tmkp202_df['time'], utc=True, errors='coerce')
        tmkp202_df = tmkp202_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        if 'TMKP202' not in tmkp202_df.columns:
            tmkp202_df['TMKP202'] = pd.NA
        tmkp202_df['TMKP202'] = pd.to_numeric(tmkp202_df['TMKP202'], errors='coerce')

    tasks_out = []
    prev_memory_last = None
    prev_orbit = None

    # summary counters
    on_cnt = off_cnt = nodata_cnt = idle_cnt = 0
    anomaly_cnt = 0

    for i in range(len(task_list)):
        row = task_list.iloc[i]
        mission_id = row.get('mission_id')

        start_dt = pd.to_datetime(row.get('starting'), utc=True)
        end_dt = pd.to_datetime(row.get('ending'), utc=True)

        # switches: first non-NaN
        sw_win = sw_df[(sw_df['time'] >= start_dt) & (sw_df['time'] <= end_dt)]
        app_series = sw_win[app_code].dropna() if app_code in sw_win.columns else pd.Series(dtype=float)
        aocs_series = sw_win[aocs_code].dropna() if aocs_code in sw_win.columns else pd.Series(dtype=float)

        app_val = int(app_series.iloc[0]) if not app_series.empty else None
        aocs_val = int(aocs_series.iloc[0]) if not aocs_series.empty else None
        switches_on = (app_val == 1 and aocs_val == 1)

        # record + memory in window
        rm_win = rm_df[(rm_df['time'] >= start_dt) & (rm_df['time'] <= end_dt)]

        record_vals = rm_win[record_code].tolist() if (not rm_win.empty and record_code in rm_win.columns) else []
        record_all_zero = (len(record_vals) == 0) or all(v == 0 for v in record_vals)

        # memory first non-zero non-NaN + last non-NaN
        if rm_win.empty or memory_code not in rm_win.columns:
            memory_first_non_zero = None
            memory_last_non_nan = None
        else:
            mem_series = rm_win[memory_code]
            memory_first_non_zero = _first_non_zero_non_nan(mem_series)
            memory_last_non_nan = _last_non_nan(mem_series)

        anomaly = False
        anomaly_reason = ""

        # status logic (with new memory consideration)
        if not switches_on:
            status = "off"
            record_val = 0
            last_record = "skip"
        else:
            if rm_win.empty:
                # switches on but no record/memory telemetry
                status = "nodata"
                record_val = None
                last_record = "nodata"
            else:
                if not record_all_zero:
                    # proceed as before: record is active
                    last_record = int(record_vals[-1]) if record_vals else 0
                    record_val = last_record

                    status = "on"
                else:
                    # record all zero in task duration
                    # => acceptable "payload not executing" scenario (idle)
                    last_record = 0
                    record_val = 0

                    # memory_last_non_nan could be None (no telemetry), treat as nodata
                    if memory_last_non_nan is None:
                        status = "nodata"
                    else:
                        status = "idle"  # switches on, but no active recording (acceptable)

        # orbit last in window
        df_orb_win = tmkp202_df[(tmkp202_df['time'] >= start_dt) & (tmkp202_df['time'] <= end_dt)]
        orbit_val = None
        if not df_orb_win.empty:
            last_orb = df_orb_win['TMKP202'].dropna()
            if not last_orb.empty:
                orbit_val = int(last_orb.iloc[-1])

        # delta vs prev (current first_non_zero_nan - previous last_non_nan)
        if i == 0 or prev_memory_last is None or memory_first_non_zero is None:
            delta_record = "nodata"
            delta_ok = False
        else:
            delta_record = memory_first_non_zero - prev_memory_last
            delta_ok = True

        if i == 0 or prev_orbit is None or orbit_val is None:
            delta_orbit = "nodata"
        else:
            delta_orbit = orbit_val - prev_orbit

        delta = {"ok": delta_ok, "delta_orbit": delta_orbit, "delta_record": delta_record}

        if memory_last_non_nan is not None:
            prev_memory_last = memory_last_non_nan
        if orbit_val is not None:
            prev_orbit = orbit_val

        # summary
        if status == "on":
            on_cnt += 1
        elif status == "off":
            off_cnt += 1
        elif status == "idle":
            idle_cnt += 1
        else:
            nodata_cnt += 1

        if anomaly:
            anomaly_cnt += 1

        # ---- erase memory storage detection (TCZ020) ----
        cmd_win = cmd_df[(cmd_df['time'] >= start_dt) & (cmd_df['time'] <= end_dt)]
        erase_hits = cmd_win[cmd_win['cmd_code'] == 'TCZ020']

        cerase_memory_storage = 1 if not erase_hits.empty else 0

        if cerase_memory_storage == 1:
            execution_times = [
                t.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
                for t in erase_hits['time'].dropna().sort_values().tolist()
            ]
        else:
            execution_times = []

        tasks_out.append({
            "mission_id": mission_id,
            "window": {
                "start_ms": int(start_dt.timestamp() * 1000),
                "end_ms": int(end_dt.timestamp() * 1000),
            },
            "meta": {
                "satellite_code": row.get('satellite_code', ""),
                "station_name": row.get('station_name', ""),
                "device": row.get('device', ""),
                "company_name": row.get('company_name', ""),
                "remark": row.get('remark', ""),
            },
            "switches": {
                "app": {"code": app_code, "value": app_val if app_val is not None else "nodata"},
                "aocs": {"code": aocs_code, "value": aocs_val if aocs_val is not None else "nodata"},
                "both_on": bool(switches_on)
            },
            "record": {
                "name": cfg["name"],
                "code": record_code,
                "status": status,               # on/off/idle/nodata
                "value": record_val if record_val is not None else "nodata",
                "last_value": last_record
            },
            "memory": {
                "code": memory_code,
                "first_non_zero_nan": memory_first_non_zero if memory_first_non_zero is not None else "nodata",
                "last_non_nan": memory_last_non_nan if memory_last_non_nan is not None else "nodata"
            },
            "orbit": {
                "code": "TMKP202",
                "value": orbit_val if orbit_val is not None else "nodata"
            },
            "delta_vs_prev": delta,
            "anomaly": {
                "flag": bool(anomaly),
                "reason": anomaly_reason if anomaly else ""
            },
            "cerase_memory_storage": {
                "cmd_code": "TCZ020",
                "value": cerase_memory_storage,  # 0 / 1
                "execution_times": execution_times  # [] or [ISO8601...]
            }
        })

    summary = {
        "total_tasks": len(tasks_out),
        "on": on_cnt,
        "off": off_cnt,
        "idle": idle_cnt,
        "nodata": nodata_cnt,
        "anomaly": anomaly_cnt
    }

    return json.dumps({
        "mode": mode,
        "satID": satID,
        "tf1": tf1,
        "tf2": tf2,
        "tasks": tasks_out,
        "summary": summary
    }, ensure_ascii=False, indent=4)


def _classify_tmz021_values(values):
    """
    values: iterable of ints
    return dict with buckets
    """
    buckets = {"HDI": [], "DWI": [], "TOPS": [], "PLATFORM": [], "OUT_OF_RANGE": []}

    for v in sorted(set(values)):
        if 1 <= v <= 160:
            buckets["HDI"].append(v)
        elif 161 <= v <= 320:
            buckets["DWI"].append(v)
        elif 321 <= v <= 480:
            buckets["TOPS"].append(v)
        elif 481 <= v <= 511:
            buckets["PLATFORM"].append(v)
        else:
            buckets["OUT_OF_RANGE"].append(v)

    return buckets


def LZ04_data_transmission_task(post_token_url,
                               post_token_user_name,
                               post_token_password,
                               orbit_service,
                               metedataservice_url,
                               _influxdb,
                               client,
                               satID,
                               tf1,
                               tf2):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    task_list = get_task_list(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service,
        tf1,
        tf2,
        satID
    )

    if not isinstance(task_list, pd.DataFrame) or task_list.empty:
        return json.dumps({
            "type": "DATA_TRANSMISSION",
            "satID": satID,
            "tf1": tf1,
            "tf2": tf2,
            "tasks": [],
            "summary": {"total_tasks": 0}
        }, ensure_ascii=False)

    # 拉取 TMZ086 + TMZ021（一次性）
    tm_df = get_LZ04_fields_df(
        post_token_url, post_token_user_name, post_token_password,
        metedataservice_url, _influxdb, client,
        tf1, tf2, satID,
        fields=["TMZ086", "TMZ021"]
    )

    # 处理类型
    if "TMZ086" not in tm_df.columns:
        tm_df["TMZ086"] = pd.NA
    if "TMZ021" not in tm_df.columns:
        tm_df["TMZ021"] = pd.NA

    tm_df["TMZ086"] = pd.to_numeric(tm_df["TMZ086"], errors="coerce")  # float
    tm_df["TMZ021"] = pd.to_numeric(tm_df["TMZ021"], errors="coerce")  # may be float/int

    tasks_out = []

    power_on_cnt = 0
    power_off_cnt = 0

    for i in range(len(task_list)):
        row = task_list.iloc[i]
        mission_id = row.get("mission_id")

        start_dt = pd.to_datetime(row.get("starting"), utc=True)
        end_dt = pd.to_datetime(row.get("ending"), utc=True)

        win = tm_df[(tm_df["time"] >= start_dt) & (tm_df["time"] <= end_dt)]

        # ---- Rule 1: terminal power ----
        # on if any TMZ086 in [0.4, 1]
        tmz086_series = win["TMZ086"].dropna() if not win.empty else pd.Series(dtype=float)
        in_range = tmz086_series[(tmz086_series >= 0.4) & (tmz086_series <= 1.0)]
        terminal_power = "on" if len(in_range) > 0 else "off"
        terminal_power_hit_count = int(len(in_range))

        if terminal_power == "on":
            power_on_cnt += 1
        else:
            power_off_cnt += 1

        # ---- Rule 2: TMZ021 unique non-zero ----
        tmz021_series = win["TMZ021"].dropna() if not win.empty else pd.Series(dtype=float)

        # 取非0，转 int（避免 1.0 这种）
        tmz021_nonzero = []
        for x in tmz021_series.tolist():
            try:
                xi = int(round(float(x)))
            except Exception:
                continue
            if xi != 0:
                tmz021_nonzero.append(xi)

        unique_values = sorted(set(tmz021_nonzero))
        buckets = _classify_tmz021_values(unique_values)

        tasks_out.append({
            "mission_id": mission_id,
            "window": {
                "start_ms": int(start_dt.timestamp() * 1000),
                "end_ms": int(end_dt.timestamp() * 1000)
            },
            "meta": {
                "satellite_code": row.get("satellite_code", ""),
                "station_name": row.get("station_name", ""),
                "device": row.get("device", ""),
                "company_name": row.get("company_name", ""),
                "remark": row.get("remark", ""),
            },

            "terminal_power": {
                "telemetry": "TMZ086",
                "status": terminal_power,  # on/off
                "hit_count_0p4_to_1": terminal_power_hit_count
            },

            "tmz021": {
                "telemetry": "TMZ021",
                "unique_nonzero_values": unique_values,
                "classified": buckets,
                "counts": {k: len(v) for k, v in buckets.items()}
            }
        })

    summary = {
        "total_tasks": len(tasks_out),
        "terminal_power_on": power_on_cnt,
        "terminal_power_off": power_off_cnt
    }

    return json.dumps({
        "type": "DATA_TRANSMISSION",
        "satID": satID,
        "tf1": tf1,
        "tf2": tf2,
        "tasks": tasks_out,
        "summary": summary
    }, ensure_ascii=False, indent=4)

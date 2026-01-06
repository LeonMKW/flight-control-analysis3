import json
import pandas as pd
import pytz
import logging
from utils.flightcontrol_utils import get_task_list
from utils.LZ04satellitestatus_utils import get_LZ04_tmkp202, get_LZ04_tmz009, get_LZ04_hdi_switches, \
get_LZ04_tmz012, get_LZ04_dwi_switches,get_LZ04_tmz015,get_LZ04_tops_switches


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

    prev_hdi_no = None
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
                vals = df_tmz['TMZ009'].tolist()
                last_tmz009 = int(vals[-1])
                if all(v == 0 for v in vals):
                    hdi_status = "off"
                    hdi_no = 0
                else:
                    hdi_status = "on"
                    hdi_no = last_tmz009

        # 3) TMKP202 orbit no（取任务窗内最后一个值）
        df_orb = tmkp202_df[(tmkp202_df['time'] >= start_dt) & (tmkp202_df['time'] <= end_dt)]
        if df_orb.empty:
            orbit_no = None
        else:
            orbit_no = int(df_orb['TMKP202'].iloc[-1])

        # 4) delta vs previous
        if idx == 0 or prev_hdi_no is None or prev_orbit_no is None or hdi_no is None or orbit_no is None:
            delta_block = {
                "delta_vs_prev": "nodata",
                "delta_TMKP202": "nodata",
                "delta_TMZ009": "nodata"
            }
        else:
            delta_block = {
                "delta_vs_prev": "ok",
                "delta_TMKP202": orbit_no - prev_orbit_no,
                "delta_TMZ009":  hdi_no - prev_hdi_no
            }

        # 更新 prev（只在当前值非 None 时更新）
        if hdi_no is not None:
            prev_hdi_no = hdi_no
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
                "last_tmz009": last_tmz009
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

    prev_dwi_no = None
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
                vals = df_tmz['TMZ012'].tolist()
                last_tmz012 = int(vals[-1])
                if all(v == 0 for v in vals):
                    dwi_status = "off"
                    dwi_no = 0
                else:
                    dwi_status = "on"
                    dwi_no = last_tmz012

        # 3) TMKP202 orbit no（取任务窗内最后一个值）
        df_orb = tmkp202_df[(tmkp202_df['time'] >= start_dt) & (tmkp202_df['time'] <= end_dt)]
        if df_orb.empty:
            orbit_no = None
        else:
            orbit_no = int(df_orb['TMKP202'].iloc[-1])

        # 4) delta vs previous
        if idx == 0 or prev_dwi_no is None or prev_orbit_no is None or dwi_no is None or orbit_no is None:
            delta_block = {
                "delta_vs_prev": "nodata",
                "delta_TMKP202": "nodata",
                "delta_TMZ012": "nodata"
            }
        else:
            delta_block = {
                "delta_vs_prev": "ok",
                "delta_TMKP202": orbit_no - prev_orbit_no,
                "delta_TMZ012":  dwi_no - prev_dwi_no
            }

        # 更新 prev（只在当前值非 None 时更新）
        if dwi_no is not None:
            prev_dwi_no = dwi_no
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
                "last_tmz012": last_tmz012
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

    prev_rec_no = None
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
                vals = df_rec['TMZ015'].tolist()
                last_tmz015 = int(vals[-1])
                if all(v == 0 for v in vals):
                    tops_status = "off"
                    rec_no = 0
                else:
                    tops_status = "on"
                    rec_no = last_tmz015

        # 3) orbit no
        df_orb = tmkp202_df[(tmkp202_df['time'] >= start_dt) & (tmkp202_df['time'] <= end_dt)]
        orbit_no = int(df_orb['TMKP202'].iloc[-1]) if not df_orb.empty else None

        # 4) delta vs prev
        if idx == 0 or prev_rec_no is None or prev_orbit_no is None or rec_no is None or orbit_no is None:
            delta_block = {
                "delta_vs_prev": "nodata",
                "delta_TMKP202": "nodata",
                "delta_TMZ015": "nodata"
            }
        else:
            delta_block = {
                "delta_vs_prev": "ok",
                "delta_TMKP202": orbit_no - prev_orbit_no,
                "delta_TMZ015":  rec_no - prev_rec_no
            }

        if rec_no is not None:
            prev_rec_no = rec_no
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
                "last_tmz015": last_tmz015
            },

            "orbit_and_tops_delta_vs_prev": delta_block
        }

        result["TOPS"][f"Task_{idx+1}"] = task_payload

    return json.dumps(result, ensure_ascii=False, indent=4)


from task.od_algorithm import orbit_precision_calculation_step1, \
    orbit_precision_calculation_step2_1, check_dict_value_types
from utils.od_utils import satellite_properties, od_tmcode
from utils.flightcontrol_utils import tm_table
from datetime import datetime, timedelta
import pytz


def orbit_precision_analysis_auto_task(metedataservice_url,
                                       orbitserviceurl,
                                       _influxdb, client,
                                       orbit_prop_url,
                                       mariadb,
                                       satIDs):
    tm = tm_table(metedataservice_url, satIDs)
    tmversion = tm[satIDs]['tm_version']
    satellite_od_dict = satellite_properties(metedataservice_url, satIDs)
    # print(satellite_od_dict)
    satgnssconfig_df = od_tmcode(metedataservice_url, satIDs)
    satgnssconfig_df = od_tmcode(metedataservice_url, satIDs)
    # print(satgnssconfig_df)

    db = mariadb
    conn = db.get_connection()
    cur = conn.cursor()

    # step1

    ephemeris_dict = orbit_precision_calculation_step1(metedataservice_url, orbitserviceurl, _influxdb, client, satIDs)

    ephemeris_id = ephemeris_dict['id'][0]

    # step 2, if row ephemeris_id > 0, already exists, go to next satID, else calculate merged_df,
    # orbit_precision_evaluate and continue to step 3
    try:
        cur.execute("SELECT COUNT(*) FROM orbit_precision_summary WHERE id = ?", (ephemeris_id,))
        row = cur.fetchone()
        count = row[0]
        if count > 0:
            print(f"Ephemeris ID {ephemeris_id} exists in 'orbit_precision_summary' table.")
        else:
            print(
                f"{ephemeris_id} starting evaluation...")

            merged_df, orbit_precision_summary = orbit_precision_calculation_step2_1(satellite_od_dict,
                                                                                     ephemeris_dict,
                                                                                     _influxdb, client,
                                                                                     satIDs,
                                                                                     orbit_prop_url,
                                                                                     satgnssconfig_df,
                                                                                     tmversion)
            # print(orbit_precision_summary.to_string())
            # print(merged_df.dtypes)
            merged_df['ephemeris_id'] = merged_df['ephemeris_id'].astype('int')
            # print(merged_df.to_string())
            # print(merged_df.dtypes)

            utc = pytz.timezone('UTC')
            beijing = pytz.timezone('Asia/Shanghai')
            timestamp_utc = datetime.strptime(orbit_precision_summary['epochTimeUTC'][0], '%Y-%m-%dT%H:%M:%S.%fZ')
            # Localize UTC time
            utc_dt = utc.localize(timestamp_utc)

            # Convert to Beijing time
            beijing_dt = utc_dt.astimezone(beijing)

            # Format the datetime object as a string
            orbit_precision_summary['beijing_time'] = beijing_dt.strftime('%Y-%m-%d %H:%M:%S')
            orbit_precision_summary['id'] = int(orbit_precision_summary['id'])
            orbit_precision_summary['timestamp'] = int(orbit_precision_summary['timestamp'])
            orbit_precision_summary['thrust'] = float(orbit_precision_summary['thrust'])

            # print(merged_df.to_string())
            orbit_precision_summary = orbit_precision_summary.to_dict(orient='records')[0]
            # orbit_precision_summary = {key: str(value) for key, value in orbit_precision_summary.items()}
            orbit_precision_summary.pop('createdAt', None)
            orbit_precision_summary.pop('updatedAt', None)
            orbit_precision_summary.pop('epochTime', None)
            # print(orbit_precision_summary)
            # value_types = check_dict_value_types(orbit_precision_summary)
            #
            #
            # # Print the result
            # for key, value_type in value_types.items():
            #     print(f"Key: {key}, Value Type: {value_type}")

            # step 3_1 push notification



            # step 3_2 mariadb operation
            try:
                # Write summary to orbit_precision_summary table
                cur.execute(
                    "INSERT INTO orbit_precision_summary "
                    "(a,e,i,dw,xw,M,CD,remark,gnssCount,residual,type,epochTimeUTC,id,"
                    "thrust,isValid,spacecraft,timestamp,mse,hour_error,max_error,beijing_time"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (orbit_precision_summary['a'],
                     orbit_precision_summary['e'],
                     orbit_precision_summary['i'],
                     orbit_precision_summary['dw'],
                     orbit_precision_summary['xw'],
                     orbit_precision_summary['M'],
                     orbit_precision_summary['CD'],
                     orbit_precision_summary['remark'],
                     orbit_precision_summary['gnssCount'],
                     orbit_precision_summary['residual'],
                     orbit_precision_summary['type'],
                     orbit_precision_summary['epochTimeUTC'],
                     orbit_precision_summary['id'],
                     orbit_precision_summary['thrust'],
                     orbit_precision_summary['isValid'],
                     orbit_precision_summary['spacecraft'],
                     orbit_precision_summary['timestamp'],
                     orbit_precision_summary['mse'],
                     orbit_precision_summary['hour_error'],
                     orbit_precision_summary['max_error'],
                     orbit_precision_summary['beijing_time']
                     ))

                # Write all points to orbit_precision_data table
                # print(merged_df.to_string())
                # print(merged_df.dtypes)
                for index, row in merged_df.iterrows():
                    query = "INSERT INTO orbit_precision_data " \
                            "(theoretical_x,theoretical_y,theoretical_z,timestamp,x,y,z,x_diff,y_diff,z_diff," \
                            "theoretical_distance2,actual_distance2,error,ephemeris_id" \
                            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"

                    ephemeris_id_int = int(row['ephemeris_id'])

                    cur.execute(query, (row['theoretical_x'], row['theoretical_y'], row['theoretical_z'],
                                        row['timestamp'], row['x'], row['y'], row['z'],
                                        row['x_diff'], row['y_diff'], row['z_diff'],
                                        row['theoretical_distance2'], row['actual_distance2'], row['error'],
                                        ephemeris_id_int))

                # Commit the changes to the database
                conn.commit()

            except BaseException as e:
                print(f"Error: {e}")

    except BaseException as e:
        print(f"Error: {e}")

    try:
        # detele all data earlier than 7 days
        delete_query = "DELETE FROM orbit_precision_data WHERE FROM_UNIXTIME(timestamp) < (NOW() - INTERVAL 7 DAY)"
        cur.execute(delete_query)

        # Commit the changes to the database
        conn.commit()

    except BaseException as e:
        print(f"Error: {e}")

    # Close cursor and connection
    cur.close()
    conn.close()

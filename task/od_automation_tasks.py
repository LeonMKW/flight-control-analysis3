from task.od_algorithm import orbit_precision_calculation_step1, \
    orbit_precision_calculation_step2_1
from utils.od_utils import satellite_properties, od_tmcode
from utils.flightcontrol_utils import tm_table


def orbit_precision_analysis_auto_task(metedataservice_url,
                                       orbitserviceurl,
                                       _influxdb, client,
                                       orbit_prop_url,
                                       mariadb,
                                       satIDs):
    satellite_od_dict = satellite_properties(metedataservice_url, satIDs)
    tm = tm_table(metedataservice_url, satIDs)
    tmversion = tm[satIDs]['tm_version']
    satellite_od_dict = satellite_properties(metedataservice_url, satIDs)
    # print(satellite_od_dict)
    satgnssconfig_df = od_tmcode(metedataservice_url, satIDs)
    # print(satgnssconfig_df)

    # db = mariadb
    # conn = db.get_connection()
    # cur = conn.cursor()
    ephemeris_dict = orbit_precision_calculation_step1(metedataservice_url, orbitserviceurl, _influxdb, client, satIDs)

    ephemeris_id = ephemeris_dict['id'][0]

    merged_df = orbit_precision_calculation_step2_1(satellite_od_dict,
                                        ephemeris_dict,
                                        _influxdb, client,
                                        satIDs,
                                        orbit_prop_url,
                                        satgnssconfig_df,
                                        tmversion)

    # orbit_precision_calculation_step2_2(merged_df)

    # Execute the query to check if ephemeris_id exists in the 'id' field of the 'orbit_precision_evaluate' table
    # try:
    #     cur.execute("SELECT COUNT(*) FROM orbit_precision_evaluate WHERE id = ?", (ephemeris_id,))
    #     row = cur.fetchone()
    #     count = row[0]
    #     if count > 0:
    #         print(f"Ephemeris ID {ephemeris_id} exists in the 'id' field of the 'orbit_precision_evaluate' table.")
    #     else:
    #         print(
    #             f"{ephemeris_id} starting evaluation...")
    #
    #         orbit_precision_calculation_step2_1(satellite_od_dict,
    #                                           ephemeris_dict,
    #                                           _influxdb, client,
    #                                           satIDs,
    #                                           orbit_prop_url,
    #                                           satgnssconfig_df,
    #                                           tmversion,)
    #
    #
    #
    # except mariadb.Error as e:
    #     print(f"Error executing SQL query: {e}")
    #
    # # Close cursor and connection
    # cur.close()
    # conn.close()

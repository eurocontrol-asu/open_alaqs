import pandas as pd
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv("./caepport_movements_full.csv", delimiter=";")
rwy_time = pd.to_datetime(df.runway_time, infer_datetime_format=True)
blc_time = pd.to_datetime(df.block_time, infer_datetime_format=True)
df["taxiing_time_sec"] = round(abs((rwy_time - blc_time).dt.total_seconds()),1)
# df['rwy_time'] = [d.time() for d in rwy_time]
# df['blk_time'] = [d.time() for d in blc_time]
df["taxiing_time_sec"] = (rwy_time - blc_time).dt.total_seconds().astype(int)

# Index(['runway_time', 'block_time', 'aircraft_registration', 'aircraft',
#        'gate', 'departure_arrival', 'runway', 'engine_name', 'prof_id',
#        'track_id', 'taxi_route', 'tow_ratio', 'apu_code', 'taxi_engine_count',
#        'set_time_of_main_engine_start_after_block_off_in_s',
#        'set_time_of_main_engine_start_before_takeoff_in_s',
#        'set_time_of_main_engine_off_after_runway_exit_in_s',
#        'engine_thrust_level_for_taxiing', 'taxi_fuel_ratio',
#        'number_of_stop_and_gos', 'domestic', 'taxiing_time_sec'],
#       dtype='object')

subset = ['aircraft', 'gate', 'departure_arrival', 'runway', 'engine_name', 'prof_id','taxi_route','taxiing_time_sec']
subset2 = ['aircraft', 'gate', 'departure_arrival', 'runway', 'engine_name', 'prof_id','taxi_route']
# df.groupby(['aircraft', 'gate', 'departure_arrival', 'runway', 'engine_name', 'prof_id','taxi_route','taxiing_time_sec'])

hourly_df_list = []
for h, hh in df.groupby(rwy_time.dt.hour):
       # ddf = hh[subset].copy()
       # xdata = ddf.astype(str).drop_duplicates(subset=None)#.reset_index()

       groups = hh.astype(str).groupby(subset2)  # .groups

       hourly_data = pd.DataFrame(index=hh.index, columns=df.keys())
       hourly_data = hourly_data.assign(annual_operations=np.nan)
       # Take the other values from the original dataframe (mostly nan values)
       # cnt = 0
       indices=[]
       for gp in groups:
              for it in subset:
                     hourly_data.loc[gp[1].index.values[0], it] = gp[1][it].iloc[0]
              hourly_data.loc[gp[1].index.values[0], "annual_operations"] = gp[1].shape[0]
              hourly_data.loc[gp[1].index.values[0], "taxiing_time_sec"] = int(df.loc[gp[1].index, "taxiing_time_sec"].sum()/gp[1].shape[0])
              indices.append(gp[1].index[0])

       for it in df.keys():
              if not (it in subset or it == "annual_operations" or it == "taxiing_time_sec"):
                     hourly_data.loc[indices, it] = df.loc[indices, it]

       clean_hourly_df = hourly_data.dropna(how='all').copy()
       clean_hourly_df['runway_time'] = pd.to_datetime(clean_hourly_df.runway_time).apply(lambda dt: dt.replace(month=1, day=1))
       clean_hourly_df['block_time'] = clean_hourly_df['runway_time'] + pd.to_timedelta(clean_hourly_df['taxiing_time_sec'], unit='s')
              # cnt+=+1
              # break
       hourly_df_list.append(clean_hourly_df)

hdf = pd.concat(hourly_df_list)
hdf = hdf.drop(['rwy_time', 'blk_time','taxiing_time_sec'], 1)
# hdf.drop('blk_time', 1)
# hdf.drop('taxiing_time_sec', 1)


# rep_df = df[df.duplicated(subset=subset, keep='first')==True]

ddf = df[subset]
groups = ddf.astype(str).groupby(subset)#.groups
data = pd.DataFrame(index=df.index, columns=df.columns)
data["annual_operations"] = None
cnt = 0
for gp in groups:
       for it in subset:
              data.loc[cnt, it] = gp[1][it].iloc[0]
       data.loc[cnt, "annual_operations"] = gp[1].shape[0]
       cnt+=+1
       break

ops = [gp[1].shape[0] for gp in groups]

# essential_data = ddf.astype(str).drop_duplicates(subset=subset).reset_index()
essential_data.loc[:, "annual_operations"] = [gp[1].shape[0] for gp in groups]

# essential_data = df.sort('C').drop_duplicates(subset=['aircraft', 'gate', 'departure_arrival', 'runway', 'engine_name', 'prof_id','taxi_route','taxiing_time_sec'], take_last=True)


# import matplotlib.pyplot as plt
# fig, ax = plt.subplots()
# ax.plot(nearestRunwayPoint.x, nearestRunwayPoint.y, "or", markersize=7)
# ax.plot(cRunwayPoint.GetX(), cRunwayPoint.GetY(), "b")
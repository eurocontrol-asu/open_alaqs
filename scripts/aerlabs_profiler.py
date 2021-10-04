from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

if __name__ == "__main__":

    d = {}
    t = {}

    for x in (Path(__file__).parents[1] / 'data').glob('*_profiled.csv'):

        data = pd.read_csv(x)

        # Get the total processing time
        total_time = data["timestamp"].sum()

        for stage, stage_data in data.groupby('stage'):
            if stage == 'process()':
                plt.figure(num=1)
                plt.title(stage)
                plt.plot(stage_data['count'], stage_data['timestamp'],
                         label=f'{x.stem} ({total_time :.0f}s)')
                plt.xlabel('count (for-loop)')
                plt.ylabel('processing time (per loop) [s]')
                plt.legend()
                plt.grid()

                plt.figure(num=2)
                plt.title(stage)
                plt.plot(stage_data['count'], stage_data['timestamp'].cumsum(),
                         label=f'{x.stem} ({total_time :.0f}s)')
                plt.xlabel('count (for-loop)')
                plt.ylabel('cumulative processing time [s]')
                plt.legend()
                plt.grid()

        # Get the total times for each stage
        v = data.groupby('stage')['timestamp'].sum()
        v['count'] = data['count'].max()

        t[x.stem] = v
        d[x.stem] = data

    t = pd.DataFrame(t).sort_index(axis=1).sort_values('count', axis=1)

    plt.figure()
    plt.title('all stages')

    b = None
    labels = t.columns + ' (n=' + t.loc['count'].astype(int).astype(str) + ')'
    stages = ('beginJob()', 'process()', 'endJob()')
    for stage in stages:
        it = t.loc[stage]
        plt.bar(labels, it, bottom=b, label=stage)
        if b is None:
            b = it
        else:
            b += it
    plt.xlabel('case')
    plt.ylabel('cumulative processing time [s]')
    plt.legend()
    plt.grid()

    # Add total times
    t.loc['totals'] = t.loc[list(stages)].sum()

    print(t.loc[['totals', 'count']].T)

    plt.show()

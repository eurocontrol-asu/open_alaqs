from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

if __name__ == "__main__":

    # Get the current folder
    current_folder = Path(__file__).parent

    # Set the cases
    case = {
            "name": "Get Emissions Lookup",
            "folder": "getemissions_lookup"
        }

    print(case['name'])

    # Clear the figures
    plt.figure(num=1).clf()
    plt.figure(num=2).clf()
    plt.figure(num=3).clf()

    # Set variables
    d = {}
    t = {}

    # Get the folder
    results_folder = (current_folder.parent / 'data' / case["folder"])

    # Get the files
    results_files = results_folder.glob('*_profiled.csv')

    # Get the data
    for x in results_files:
        data = pd.read_csv(x)

        # Get the total processing time
        total_time = data["timestamp"].sum()

        for stage, stage_data in data.groupby('stage'):
            if stage == 'process()':
                f1 = plt.figure(num=1)
                plt.title(stage)
                plt.plot(stage_data['count'], stage_data['timestamp'],
                         label=f'{x.stem} ({total_time :.0f}s)')
                plt.xlabel('count (for-loop)')
                plt.ylabel('processing time (per loop) [s]')
                plt.legend()
                plt.grid()

                f2 = plt.figure(num=2)
                plt.title(stage)
                plt.plot(stage_data['count'],
                         stage_data['timestamp'].cumsum(),
                         label=f'{x.stem} ({total_time :.0f}s)')
                plt.xlabel('count (for-loop)')
                plt.ylabel('cumulative processing time [s]')
                plt.legend()
                plt.grid()

                if '_original_' in x.stem:

                    f3 = plt.figure(num=3)
                    x_label = 'with dispersion enabled' if '_dispersion_' in x.stem else 'with dispersion disabled'
                    plt.plot(stage_data['count'],
                             stage_data['timestamp'].cumsum(),
                             label=x_label)

                if '_original_p' in x.stem:
                    f4 = plt.figure(num=4)
                    plt.plot(stage_data['count'],
                             stage_data['timestamp'].cumsum(),
                             label='original')
                if '_dataframe_' in x.stem:
                    f4 = plt.figure(num=4)
                    plt.plot(stage_data['count'],
                             stage_data['timestamp'].cumsum(),
                             label='iteration 1')
                if '_period_p' in x.stem:
                    f4 = plt.figure(num=4)
                    plt.plot(stage_data['count'],
                             stage_data['timestamp'].cumsum(),
                             label='iteration 2')

                if '_original_d' in x.stem:
                    f5 = plt.figure(num=5)
                    plt.plot(stage_data['count'],
                             stage_data['timestamp'].cumsum(),
                             label='original')
                if '_period_d' in x.stem:
                    f5 = plt.figure(num=5)
                    plt.plot(stage_data['count'],
                             stage_data['timestamp'].cumsum(),
                             label='iteration 2')

        # Get the total times for each stage
        v = data.groupby('stage')['timestamp'].sum()
        v['count'] = data['count'].max()

        t[x.stem] = v
        d[x.stem] = data

    t = pd.DataFrame(t).sort_index(axis=1).sort_values('count', axis=1)

    # f3 = plt.figure(num=3)
    # plt.title('all stages')
    #
    # b = None
    # labels = t.columns + ' (n=' + t.loc['count'].astype(int).astype(
    #     str) + ')'
    # stages = ('beginJob()', 'process()', 'endJob()')
    # for stage in stages:
    #     it = t.loc[stage]
    #     plt.bar(labels, it, bottom=b, label=stage)
    #     if b is None:
    #         b = it
    #     else:
    #         b += it
    # plt.xlabel('case')
    # plt.ylabel('cumulative processing time [s]')
    # plt.legend()
    # plt.grid()
    #
    # # Add total times
    # t.loc['totals'] = t.loc[list(stages)].sum()
    #
    # print(t.loc[['totals', 'count']].T)

    """
    Plot the problem
    """
    f3 = plt.figure(num=3)
    plt.title('EmissionCalculation.process() execution time')
    plt.xlabel('iteration (for-loop)')
    plt.ylabel('cumulative processing time [s]')
    plt.grid()
    plt.legend()

    """
    Plot the improvement without dispersion
    """
    f4 = plt.figure(num=4)
    plt.title('EmissionCalculation.process() execution time with dispersion disabled')
    plt.xlabel('iteration (for-loop)')
    plt.ylabel('cumulative processing time [s]')
    plt.grid()
    plt.legend()

    """
    Plot the improvement with dispersion
    """
    f5 = plt.figure(num=5)
    plt.title('EmissionCalculation.process() execution time with dispersion enabled')
    plt.xlabel('iteration (for-loop)')
    plt.ylabel('cumulative processing time [s]')
    plt.grid()
    plt.legend()

    """
    Show time improvement over iterations
    """

    o1t = t[t.columns[t.columns.str.contains('_original_p')][0]]
    o2t = t[t.columns[t.columns.str.contains('_original_d')][0]]
    i1t = t[t.columns[t.columns.str.contains('_dataframe')][0]]
    i21t = t[t.columns[t.columns.str.contains('_period_p')][0]]
    i22t = t[t.columns[t.columns.str.contains('_period_d')][0]]

    d1 = pd.Series([
        o1t['process()'],
        i1t['process()'],
        i21t['process()'],
    ], index=[
        'original',
        'iteration 1',
        'iteration 2',
    ])
    d2 = pd.Series([
        o2t['process()'],
        0,
        i22t['process()'],
    ], index=[
        'original',
        'iteration 1',
        'iteration 2',
    ])

    dd1 = 100 * (d1['original'] - d1) / d1['original']
    dd2 = 100 * (d2['original'] - d2) / d2['original']

    print(d1)
    for _i in range(d1.shape[0] - 1):
        i = 1 + _i
        print(f'iteration {i}: improvement of', dd1[f'iteration {i}'], '%')
    print(d2)
    for _i in range(d2.shape[0] - 1):
        i = 1 + _i
        print(f'iteration {i}: improvement of', dd2[f'iteration {i}'], '%')

    f1.savefig(current_folder / f"figures/plot_{case['folder']}_1.png")
    f2.savefig(current_folder / f"figures/plot_{case['folder']}_2.png")
    f3.savefig(current_folder / f"figures/plot_{case['folder']}_3.png")
    f4.savefig(current_folder / f"figures/plot_{case['folder']}_4.png")
    f5.savefig(current_folder / f"figures/plot_{case['folder']}_5.png")

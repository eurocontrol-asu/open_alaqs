from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

if __name__ == "__main__":

    # Get the current folder
    current_folder = Path(__file__).parent

    # Set the cases
    case = {
            "name": "Movement Emission Calculation",
            "folder": "movement_emission_calculation"
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
                    x_label = 'original'
                    plt.plot(stage_data['count'],
                             stage_data['timestamp'].cumsum(),
                             label=x_label)

                elif '_beginJob_' not in x.stem:

                    f3 = plt.figure(num=3)
                    x_label = 'iteration 1 (b9cc4cc7)'
                    plt.plot(stage_data['count'],
                             stage_data['timestamp'].cumsum(),
                             label=x_label)

        # Get the total times for each stage
        v = data.groupby('stage')['timestamp'].sum()
        v['count'] = data['count'].max()

        t[x.stem] = v
        d[x.stem] = data

    t = pd.DataFrame(t).sort_index(axis=1).sort_values('count', axis=1)

    """
    Plot the problem
    """
    f3 = plt.figure(num=3)
    plt.title('MovementSourceModule.process() execution time')
    plt.xlabel('iteration (for-loop)')
    plt.ylabel('cumulative processing time [s]')
    plt.grid()
    plt.legend()

    """
    Show time improvement over iterations
    """

    ot = t[t.columns[t.columns.str.contains('_original_')][0]]
    it = t[t.columns[~(t.columns.str.contains('_original_') | t.columns.str.contains('_beginJob_'))][0]]

    d = pd.Series([
        ot['process()'],
        it['process()'],
    ], index=[
        'original',
        'iteration 1',
    ])

    dd = 100 * (d['original'] - d) / d['original']

    print(d)
    for _i in range(d.shape[0] - 1):
        i = 1 + _i
        print(f'iteration {i}: improvement of', dd[f'iteration {i}'], '%')

    f1.savefig(current_folder / f"figures/plot_{case['folder']}_1.png")
    f2.savefig(current_folder / f"figures/plot_{case['folder']}_2.png")
    f3.savefig(current_folder / f"figures/plot_{case['folder']}_3.png")

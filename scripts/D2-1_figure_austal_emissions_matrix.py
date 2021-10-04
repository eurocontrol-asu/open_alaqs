from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

if __name__ == "__main__":

    # Get the current folder
    current_folder = Path(__file__).parent

    # Set the cases
    case = {
        "name": "AUSTAL Emissions Matrx",
        "folder": "austal_emissions_matrix"
    }

    print(case['name'])

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

        # Get the total times for each stage
        v = data.groupby('stage')['timestamp'].sum()
        v['count'] = data['count'].max()

        t[x.stem] = v
        d[x.stem] = data

    t = pd.DataFrame(t).sort_index(axis=1).sort_values('count', axis=1)

    f3 = plt.figure(num=3)
    plt.title('all stages')

    b = None
    labels = t.columns + ' (n=' + t.loc['count'].astype(int).astype(
        str) + ')'
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

    """
    Plot the problem
    """
    f4 = plt.figure(num=4)
    plt.title('AUSTAL2000OutputModule.process() execution time')

    # Get the data
    data = [
        t.loc['process()', '20210712-153951_original_profiled'],
        t.loc['process()', '20210712-175835_df_sum_profiled'],
        t.loc['process()', '20210712-181101_df_hashvalue_profiled'],
        # t.loc['process()', '20210712-190236_transformationmatrix_profiled']
    ]

    # Set the labels
    labels = [
        'original',
        'iteration 1',
        'iteration 2',
        # 'iteration 3'
    ]

    plt.xticks(range(len(data)), labels)
    plt.bar(range(len(data)), data)
    plt.ylabel('execution time [s]')

    """
    Show time improvement over iterations
    """

    d = pd.Series(data, index=labels)

    dd = 100 * (d['original'] - d) / d['original']

    for _i in range(len(data) - 1):
        i = 1 + _i
        print(f'iteration {i}: improvement of', dd[f'iteration {i}'], '%')

    """
    Show totals
    """
    print(t.loc[['totals', 'count']].T)

    f1.savefig(current_folder / f"figures/plot_austal_emissions_matrix_1.png")
    f2.savefig(current_folder / f"figures/plot_austal_emissions_matrix_2.png")
    f3.savefig(current_folder / f"figures/plot_austal_emissions_matrix_3.png")
    f4.savefig(current_folder / f"figures/plot_austal_emissions_matrix_4.png")

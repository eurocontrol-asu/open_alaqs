from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

if __name__ == "__main__":

    # Get the current folder
    current_folder = Path(__file__).parent

    # Set the cases
    case = {
        "name": "AUSTAL Endjob",
        "folder": "austal_endjob"
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
    plt.title('AUSTAL2000OutputModule.endJob() execution time')

    # Get the original columns
    original_columns = t.columns[t.columns.str.contains("_original_")]

    # Get the original data
    original_t = t[original_columns].T

    # Plot the endJob execution times
    plt.plot(original_t['count'], original_t['endJob()'],
             marker='o', linestyle=':')

    plt.xlabel('number of hours in selected time range')
    plt.ylabel('execution time [s]')
    plt.xlim(left=0)
    # plt.ylim(bottom=0)
    plt.grid()

    """
    Plot the iterations
    """
    f5 = plt.figure(num=5)
    plt.title('AUSTAL2000OutputModule.endJob() execution time')

    # Get the relevant columns
    original_columns = t.columns[t.columns.str.contains("_original_")]
    iteration_1_columns = t.columns[t.columns.str.contains("_results_p")]
    iteration_2_columns = t.columns[t.columns.str.contains("_results_2_p")]

    # Get the relevant data
    original_t = t[original_columns].T
    iteration_1_t = t[iteration_1_columns].T
    iteration_2_t = t[iteration_2_columns].T

    # Plot the endJob execution times
    plt.plot(original_t['count'], original_t['endJob()'],
             marker='o', linestyle=':', label='original')
    plt.plot(iteration_1_t['count'], iteration_1_t['endJob()'],
             marker='o', linestyle=':', label='iteration 1 (849cb97a)')
    plt.plot(iteration_2_t['count'], iteration_2_t['endJob()'],
             marker='o', linestyle=':', label='iteration 2 (a4c01d09)')

    plt.xlabel('number of hours in selected time range')
    plt.ylabel('execution time [s]')
    plt.xlim(left=0)
    # plt.ylim(bottom=0)
    plt.grid()
    plt.legend()

    """
    Show time improvement over iterations
    """
    ot = original_t.set_index('count')
    i1t = iteration_1_t.set_index('count')
    i2t = iteration_2_t.set_index('count')

    di1t = 100 * (ot - i1t) / ot
    di2t = 100 * (ot - i2t) / ot

    print('iteration 1: improvement of',
          di1t.loc[4340, 'endJob()'], '% at 6 months and',
          di1t.loc[8756, 'endJob()'], '% at 12 months')
    print('iteration 2: improvement of',
          di2t.loc[4340, 'endJob()'], '% at 6 months and',
          di2t.loc[8756, 'endJob()'], '% at 12 months')

    """
    Show totals
    """
    print(t.loc[['totals', 'count']].T)

    f1.savefig(current_folder / f"figures/plot_austal_endjob_1.png")
    f2.savefig(current_folder / f"figures/plot_austal_endjob_2.png")
    f3.savefig(current_folder / f"figures/plot_austal_endjob_3.png")
    f4.savefig(current_folder / f"figures/plot_austal_endjob_4.png")
    f5.savefig(current_folder / f"figures/plot_austal_endjob_5.png")

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

if __name__ == "__main__":

    # Get the current folder
    current_folder = Path(__file__).parent

    # Set the cases
    case = {
        "name": "AUSTAL Total Emissions Sum",
        "folder": "austal_total_emissions_sum"
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
    Plot the iterations
    """

    # Get the relevant columns
    original_columns = t.columns[t.columns.str.contains("_original_")]
    iteration_1_columns = t.columns[t.columns.str.contains("_dataframe_")]

    # Get the relevant data
    original_t = t[original_columns].T
    iteration_1_t = t[iteration_1_columns].T

    # Create a figure
    f4 = plt.figure(num=4)
    plt.title('AUSTAL2000OutputModule.process() execution time')

    # Plot the process execution times
    plt.plot(original_t['count'], original_t['process()'],
             marker='o', linestyle=':', label='original')
    plt.plot(iteration_1_t['count'], iteration_1_t['process()'],
             marker='o', linestyle=':', label='iteration (dd9a3a58)')

    plt.xlabel('number of hours in selected time range')
    plt.ylabel('execution time [s]')
    plt.xlim(left=0)
    plt.ylim(bottom=0)
    plt.grid()
    plt.legend()

    """
    Show time improvement over iterations
    """
    ot = original_t.set_index('count')
    i1t = iteration_1_t.set_index('count')

    di1t = 100 * (ot - i1t) / ot

    print('For all sources with time range of 1 day:')
    print('\toriginal:', ot.loc[20, 'process()'], 'seconds')
    print('\titeration 1:', i1t.loc[20, 'process()'], 'seconds')
    print('improvement of', di1t.loc[20, 'process()'], '%')
    print('For point sources only with time range of 6 months:')
    print('\toriginal:', ot.loc[4340, 'process()'], 'seconds')
    print('\titeration 1:', i1t.loc[4340, 'process()'], 'seconds')
    print('iteration 2: improvement of', di1t.loc[4340, 'process()'], '%')

    """
    Show totals
    """
    print(t.loc[['totals', 'count']].T)

    f1.savefig(current_folder / f"figures/plot_austal_total_emissions_sum_1.png")
    f2.savefig(current_folder / f"figures/plot_austal_total_emissions_sum_2.png")
    f3.savefig(current_folder / f"figures/plot_austal_total_emissions_sum_3.png")
    f4.savefig(current_folder / f"figures/plot_austal_total_emissions_sum_4.png")
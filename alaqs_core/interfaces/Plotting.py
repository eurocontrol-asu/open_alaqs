import matplotlib
import matplotlib.pyplot as plt

matplotlib.use('Qt5Agg')


def plotTrajectoryXZ(movements_list=None, isCartesian=True):
    if movements_list is None:
        movements_list = []
    withDashText = False
    if movements_list:
        import matplotlib as mpl
        #from mpl_toolkits.mplot3d import Axes3D
        #import numpy as np
        # import matplotlib.pyplot as plt
        # mpl.rcParams['legend.fontsize'] = 10

        matplotlib.rcParams['legend.fontsize'] = 10

        fig = plt.figure()
        #ax = fig.gca(projection='3d')
        ax = fig.gca()
        x = []
        y = []
        z = []

        movements = []
        for mov in movements_list:
            if not mov.getTrajectory(isCartesian) is None:
                #if mov.getTrajectory(isCartesian).getPoints(mode="")[1].getX()< 1000.:
                movements.append(mov)
        movements = sorted(movements, key=lambda x: x.getTrajectory(isCartesian).getPoints(mode="")[-1].getX())

        for mov in movements:
            x_,y_,z_ = [],[],[]
            if not mov.getTrajectory(isCartesian) is None:
                for point in mov.getTrajectory(isCartesian).getPoints(mode=""):
                    (x__,y__,z__) = point.getCoordinates()
                    x_.append(x__)
                    y_.append(y__)
                    z_.append(z__)
                #x.append(x_)
                #y.append(y_)
                #z.append(z_)
                if withDashText:
                    ax.plot(x_, z_, label=mov.getAircraft().getType(), color="blue")
                else:
                    ax.plot(x_, z_, label=mov.getAircraft().getType())
                if withDashText:
                    ax.text(x_[-1], z_[-1], str(mov.getAircraft().getType()), withdash=True,
                       dashdirection=1,
                       dashlength=20,
                       rotation=90,
                       dashrotation=90,
                       dashpush=10,
                       fontsize=12
                       )

        ax.set_xlim(ax.get_xlim()[0], 1.2*ax.get_xlim()[1])
        ax.set_ylim(ax.get_ylim()[0], 1.1*ax.get_ylim()[1])
        #ax.set_xlim(ax.get_xlim()[0], 2500.)
        #ax.set_ylim(ax.get_ylim()[0], 100.)
        if not withDashText:
            ax.legend()
        if not isCartesian:
            plt.xlabel("x-coordinate (SRID: 3857)")
        else:
            plt.xlabel("Distance from threshold [m]")
        plt.ylabel("Height [m]")
        plt.show()
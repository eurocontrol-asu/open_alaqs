from datetime import datetime

from PyQt5.QtWidgets import QProgressDialog


class ProgressBarStage:
    def __init__(self, parent: QProgressDialog, start: int, end: int,
                 minimum: int = 0, maximum: int = 100, value: int = None):

        # Set the progress bar and associated range
        self._parent = parent
        self._start = start
        self._end = end

        # Set the stage range and current value
        self._min = minimum
        self._max = maximum
        self._value = minimum if value is None else value

        # Start the timer
        self._start_time = datetime.now()
        self._end_time = None

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        if self._min <= val <= self._max:
            self._value = val
        else:
            raise ValueError(
                f'value must be between {self._min} and {self._max} (incl.)')

        # Determine the progress as a percentage
        perc = 1 - (self._max - val) / (self._max - self._min)

        # Determine the progress
        p = self._start + perc * (self._end - self._start)

        self._parent.setValue(int(round(p)))

    def nextValue(self, step: int = 1):
        try:
            return self.setValue(self.value() + step)
        except ValueError:
            pass

    @classmethod
    def firstStage(cls, parent: QProgressDialog, end: int = None,
                   duration: int = None, *args, **kwargs):
        if end is not None and duration is not None:
            raise ValueError('only end or duration should be specified')
        if duration is not None:
            end = parent.minimum() + duration
        return cls(parent, parent.minimum(), end, *args, **kwargs)

    def nextStage(self, end: int = None, duration: int = None, *args, **kwargs):
        self.finish()
        if end is not None and duration is not None:
            raise ValueError('only end or duration should be specified')
        if duration is not None:
            if duration <= 0:
                raise ValueError('duration should be larger than zero')
            end = self._end + duration
        if end > self._parent.maximum():
            raise ValueError('the stage end should not be larger than the '
                             'maximum value of the progress bar')
        return ProgressBarStage(self._parent, self._end, end, *args, **kwargs)

    def finalStage(self, *args, **kwargs):
        self.finish()
        return ProgressBarStage(self._parent, self._end, self._parent.maximum(),
                                *args, **kwargs)

    def finish(self):
        self.setValue(self._max)
        self._end_time = datetime.now()

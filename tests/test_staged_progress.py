import pytest

PyQt5 = pytest.importorskip("PyQt5")

from open_alaqs.alaqs_core.tools.ProgressBarStage import ProgressBarStage  # noqa: E402


class FakeProgressBar:
    def __init__(self, minimum: int, maximum: int):
        self._min = minimum
        self._max = maximum
        self._value = None

    def value(self) -> int:
        return self._value

    def minimum(self) -> int:
        return self._min

    def maximum(self) -> int:
        return self._max

    def setValue(self, val: int):
        self._value = val


def test_stages():
    # Create a progress object running from 0 to 100 units
    staged_progress = FakeProgressBar(0, 100)

    # Create the stages
    stage_1 = ProgressBarStage(staged_progress, 0, 20)
    stage_2 = ProgressBarStage(staged_progress, 20, 40)
    stage_3 = ProgressBarStage(staged_progress, 40, 100)

    assert int(stage_1._start) == 0
    assert int(stage_1._end) == 20

    stage_1.setValue(50)

    assert staged_progress.value() == 10

    stage_2.setValue(50)

    assert staged_progress.value() == 30

    stage_3.setValue(80)

    assert staged_progress.value() == 88


def test_first_stage():
    # Create a progress object running from 0 to 100 units
    staged_progress = FakeProgressBar(0, 100)

    # Create the stages
    stage_1 = ProgressBarStage.firstStage(staged_progress, 20)
    stage_2 = ProgressBarStage(staged_progress, 20, 40)
    stage_3 = ProgressBarStage(staged_progress, 40, 100)

    assert int(stage_1._start) == 0
    assert int(stage_1._end) == 20

    stage_1.setValue(50)

    assert staged_progress.value() == 10

    stage_2.setValue(50)

    assert staged_progress.value() == 30

    stage_3.setValue(80)

    assert staged_progress.value() == 88


def test_next_value():
    # Create a progress object running from 0 to 100 units
    staged_progress = FakeProgressBar(0, 100)

    # Create the stages
    stage = ProgressBarStage.firstStage(staged_progress, staged_progress.maximum())

    assert int(stage._start) == 0
    assert int(stage._end) == 100

    stage.setValue(50)

    assert staged_progress.value() == 50

    stage.nextValue()

    assert staged_progress.value() == 51


def test_next_stage():
    # Create a progress object running from 0 to 100 units
    staged_progress = FakeProgressBar(0, 100)

    # Create the stages
    stage_1 = ProgressBarStage(staged_progress, 0, 20)
    stage_2 = stage_1.nextStage(40)
    stage_3 = stage_2.nextStage(100)

    assert int(stage_1._start) == 0
    assert int(stage_1._end) == 20

    stage_1.setValue(50)

    assert staged_progress.value() == 10

    stage_2.setValue(50)

    assert staged_progress.value() == 30

    stage_3.setValue(80)

    assert staged_progress.value() == 88


def test_stage_duration():
    # Create a progress object running from 0 to 100 units
    staged_progress = FakeProgressBar(0, 100)

    # Create the stages
    stage_1 = ProgressBarStage(staged_progress, 0, 20)
    stage_2 = stage_1.nextStage(duration=40)
    stage_3 = stage_2.nextStage(100)

    assert int(stage_1._start) == 0
    assert int(stage_1._end) == 20

    stage_1.setValue(50)

    assert staged_progress.value() == 10

    stage_2.setValue(50)

    assert staged_progress.value() == 40

    stage_3.setValue(80)

    assert staged_progress.value() == 92


def test_final_stage():
    # Create a progress object running from 0 to 100 units
    staged_progress = FakeProgressBar(0, 100)

    # Create the stages
    stage_1 = ProgressBarStage(staged_progress, 0, 20)
    stage_2 = stage_1.nextStage(40)
    stage_3 = stage_2.finalStage()

    assert int(stage_1._start) == 0
    assert int(stage_1._end) == 20

    stage_1.setValue(50)

    assert staged_progress.value() == 10

    stage_2.setValue(50)

    assert staged_progress.value() == 30

    stage_3.setValue(80)

    assert staged_progress.value() == 88


def test_next_stage_min_max():
    # Create a progress object running from 0 to 100 units
    staged_progress = FakeProgressBar(0, 100)

    # Create the stages
    stage_1 = ProgressBarStage(staged_progress, 0, 20)
    stage_2 = stage_1.nextStage(40, minimum=50)
    stage_3 = stage_2.nextStage(100, maximum=1000)

    assert int(stage_1._start) == 0
    assert int(stage_1._end) == 20

    stage_1.setValue(50)

    assert staged_progress.value() == 10

    stage_2.setValue(50)

    assert staged_progress.value() == 20

    stage_3.setValue(80)

    assert staged_progress.value() == 45

import numpy as np

from volscan.lateral import infill_prior


def test_infill_scores_ground_between_two_arms_above_open_ground():
    m = np.zeros((40, 40), bool)
    m[:, 10:13] = True          # west arm
    m[:, 27:30] = True          # east arm
    valid = np.ones_like(m)
    p = infill_prior(m, valid, step_m=25.0, radius_m=400.0, power=1.0)
    between, outside = p[20, 20], p[20, 36]
    assert between > outside > 0
    assert p[m].max() == 0                        # never on the flow itself


def test_infill_is_zero_far_from_the_flow_and_on_invalid_cells():
    m = np.zeros((60, 60), bool)
    m[28:32, 28:32] = True
    valid = np.ones_like(m)
    valid[0:5, :] = False
    p = infill_prior(m, valid, step_m=25.0, radius_m=200.0)
    assert p[2, 2] == 0 and p[45, 5] == 0
    assert p[30, 34] > 0

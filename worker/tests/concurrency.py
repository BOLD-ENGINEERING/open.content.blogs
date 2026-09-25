import os


def assert_wall_time_budget(wall: float, median: float) -> None:
    cpu_count = os.cpu_count()
    enforce_bound = cpu_count is not None and cpu_count >= 4
    print(
        f"S10 timing: cpu_count={cpu_count}, wall={wall:.6f}s, "
        f"median={median:.6f}s, enforce_2x_bound={enforce_bound}"
    )
    if enforce_bound:
        assert wall < 2 * median

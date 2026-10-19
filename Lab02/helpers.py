import numpy as np


def manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    
    return abs(x1 - x2) + abs(y1 - y2)
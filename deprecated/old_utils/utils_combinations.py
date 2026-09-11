# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison

"""

# %% Packages
""" Third party and local imports """

from itertools import permutations
from itertools import combinations
from itertools import combinations_with_replacement

from math import factorial

# %% Functions
""" Define functions """


# %% Variables
""" Set local variables """


# %% Main
""" Test permutations """

if __name__ == "__main__":
    print("order matters")
    list_perm = list(
        permutations(
            [
                1,
                2,
                3,
                4,
            ],
            r=2,
        )
    )

    for tuple in list_perm:
        print(tuple)

    print("order doesn't matter")
    list_comb = list(
        combinations(
            [
                1,
                2,
                3,
                4,
            ],
            r=2,
        )
    )

    for tuple in list_comb:
        print(tuple)

    print("allow element to itself")

    list_comb_r = list(
        combinations_with_replacement(
            [
                1,
                2,
                3,
                4,
            ],
            r=2,
        )
    )

    print(f"len of w/ replacement list {len(list_comb_r)}")
    print(f"len of w/o replacement list {len(list_comb)}")

# %% Work
""" Specific questions """

list_items = range(1, 23)
n = len(list_items)
r = 2  # choose

list_comb = list(
    combinations(
        list_items,
        r=r,
    )
)

C = len(list_comb)
print(f"list total combinations {C} from {n} choose {r}")
C = factorial(n) / (factorial(r) * factorial(n - r))
print(f"list total combinations {C} from {n} choose {r}")

r = 3
C = factorial(n) / (factorial(r) * factorial(n - r))
print(f"list total combinations {C} from {n} choose {r}")

n = 6
r = 2
C = factorial(n) / (factorial(r) * factorial(n - r))
print(f"list total combinations {C} from {n} choose {r}")

r = 3
C = factorial(n) / (factorial(r) * factorial(n - r))
print(f"list total combinations {C} from {n} choose {r}")

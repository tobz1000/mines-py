#!/usr/bin/env python3.4

# Test speed of different db solutions for storing/fetching game state info.

import numpy
from functools import reduce
from profilehooks import profile
import inspect
import types
import random
import operator

MINE = -1
UNKNOWN = -2
TO_CLEAR = -3

class NoDbNdarray:
	def create_grid(self, dims):
		self.game_grid = numpy.ndarray(dims, dtype=int)
		self.game_grid.fill(UNKNOWN)

	def set_cells(self, coords_list, state):
		for coords in coords_list:
			self.game_grid[coords] = state

	def get_state_cells(self, state):
		return tuple(c.tolist() for c in
			numpy.transpose((self.game_grid == state).nonzero()))

	def get_cell_state(self, coords):
		return self.game_grid[coords]

def test(Db, dims, mines):
	db = Db()

	# Get unique random positions from grid as 1d array
	mine_positions = random.sample(range(reduce(operator.mul, dims, 1)), mines)

	# Convert to list of coords in grid-shaped array
	mine_positions = numpy.transpose(numpy.unravel_index(mine_positions, dims))

	db.create_grid(dims)
	db.set_cells(mine_positions, MINE)
	db.get_state_cells(MINE)

test(NoDbNdarray, [10000,10000], 200)
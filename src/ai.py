#!/usr/bin/env python3.4
import json
import requests
import random
import math
import numpy
import functools
import itertools
import time
from profilehooks import profile

SERVER_ADDR = "http://localhost:1066"

# Ghetto enums for cell value; non-neg values are surround count for cleared
# cells
MINE = -1
UNKNOWN = -2
TO_CLEAR = -3

# A grouping of cells with a potential number of mines within them.
# TODO: possibly get rid of min_mines/max_mines; may not be necessary if not
# splitting overlapping (non-subset) zones. In this case just throw an error if
# trying to create a MineZone without a definite/fixed number of mines.
class MineZone:
	def __init__(self, cells=frozenset(), min_mines=0, max_mines=0):
		if(min_mines > max_mines):
			raise MineZoneErr(
				cells,
				min_mines,
				max_mines,
				"Constructed MineZone with greater min_mines than max_mines."
			)

		self.cells = cells
		self.min_mines = max(min_mines, 0)
		self.max_mines = min(max_mines, len(self.cells))
		self.fixed = self.min_mines == self.max_mines
		self.can_clear = self.fixed and self.min_mines == 0
		self.can_flag = self.fixed and self.min_mines == len(self.cells)

	def __str__(self):
		return "MineZone (min {} max {}): {}".format(self.min_mines,
				self.max_mines, tuple(self.cells))

	def __len__(self):
		return len(self.cells)

	# maMines/min_mines not considered for equality
	def __eq__(self, other):
		return self.cells == other.cells

	def __gt__(self, other):
		return self.cells > other.cells

	def __ge__(self, other):
		return self.cells >= other.cells

	def __or__(self, other):
		if(len(self.cells & other.cells) == 0):
			return MineZone(
				self.cells | other.cells,
				self.min_mines + other.min_mines,
				self.max_mines + other.max_mines,
			)

		if(self == other):
			return self & other

		# If self is a superset, the new MineZone will be identical; with the
		# exception that other may inform us of a higher minimum mine count
		if(self > other):
			return MineZone(
				self.cells,
				max(self.min_mines, other.min_mines),
				self.max_mines
			)

		if(self < other):
			return other | self

		# If neither is a subset of the other, calculate possible mine count
		# range for union
		min_mines = max(self.min_mines, other.min_mines)
		# TODO: this is wrong. Consider:
		# ... 1  2 ...
		# [ ][ ][ ][ ]
		# The union should have a fixed number of mines - 2. However the below
		# formula gives a maximum of 1 (less than the minimum...)
		max_mines = self.max_mines + other.max_mines - len(self.cells &
				other.cells)

		return MineZone(self.cells | other.cells, min_mines, max_mines)

	def __and__(self, other):
		if(len(self.cells & other.cells) == 0):
			return MineZone()

		if(self == other):
			return MineZone(
				self.cells,
				max(self.min_mines, other.min_mines),
				min(self.max_mines, other.max_mines)
			)

		# If self is a subset, the new MineZone will be identical; with the
		# exception that other may inform us of a lower maximum mine count
		if(self < other):
			return MineZone(
				self.cells,
				self.min_mines,
				min(self.max_mines, other.max_mines)
			)

		if(self > other):
			return other & self

		# if neither is a subset of the other, calculate possible mine count
		# range for intersection
		# TODO: I think this is wrong - compare with comment on __or__ logic
		min_mines = max(
			0,
			self.min_mines - len(self.cells - other.cells),
			other.min_mines - len(other.cells - self.cells)
		)
		max_mines = min(self.max_mines, other.max_mines)

		return MineZone(self.cells & other.cells, min_mines, max_mines)

	def __sub__(self, other):
		if(self <= other):
			return MineZone()

		if(self > other):
			try:
				return MineZone(
					self.cells - other.cells,
					self.min_mines - other.max_mines,
					self.max_mines - other.min_mines
				)
			except MineZoneErr as e:
				print("Error while subtracting:\n{}\nminus:\n{}".format(
					self, other
				))
				raise

		return self - (self & other)

class MineZoneErr(Exception):
	def __init__(self, cells, min_mines, max_mines, msg=None):
		self.cells = cells
		self.min_mines = min_mines
		self.max_mines = max_mines

		if msg:
			print(msg)
		print("cells={}; min_mines={}; max_mines={}".format(cells, min_mines,
				max_mines))

class GameEnd(Exception):
	def __init__(self, game, msg=None):
		end_time = time.time()

		print()

		if msg:
			print(msg)

		turns_id = "{:x}".format(abs(game.turns_hash_sum))[:5]

		print("{}".format("Win!!11" if game.win else "Lose :((("))
		print("Turns id: {}".format(turns_id))
		print("Time elapsed: {:.5}s (+{:.5}s waiting)".format(
			end_time - game.start_time - game.wait_time,
			game.wait_time)
		)
		print("="*50)

class Game:
	id = None
	dims = None
	mines = None
	game_grid = None
	password = "pass"
	game_over = False
	win = False
	turns_hash_sum = 0
	start_time = None
	wait_time = None
	surr_coords_lookup = None

	def __init__(self, dims=None, mines=None, reload_id=None):
		self.wait_time = float(0)

		if(dims and mines):
			resp = self.action({
				"action": "newGame",
				"dims": dims,
				"mines": mines
			})
		elif(reload_id):
			resp = self.action({
				"action": "loadGame",
				"id": reload_id
			})
		else:
			raise Exception("Insufficient game parameters")

		self.dims = resp["dims"]
		self.mines = resp["mines"]
		self.id = resp["id"]

		self.game_grid = numpy.ndarray(self.dims, dtype=int)
		self.game_grid.fill(UNKNOWN)
		self.surr_coords_lookup = {}

		print("New game: {} (original {}) dims: {} mines: {}".format(
			self.id,
			reload_id or self.id,
			self.dims,
			self.mines
		))

	def action(self, params):
		if self.id:
			params["id"] = self.id

		if self.password:
			params["pass"] = self.password

		wait_start = time.time()

		# TODO: error handling, both from "error" JSON and other server
		# response/no server response
		resp = json.loads(requests.post(SERVER_ADDR + "/action",
				data=json.dumps(params)).text)

		self.wait_time += time.time() - wait_start

		err = resp.get("error")

		if err:
			raise Exception('Server error response: "{}"; info: {}'.format(err,
					json.dumps(resp.get("info"))))

		self.game_over = resp["gameOver"]
		self.win = resp["win"]

		self.cells_rem = resp["cellsRem"]

		for cell in resp["newCellData"]:
			self.game_grid[tuple(cell["coords"])] = {
				'empty':	cell["surrounding"],
				'cleared':	cell["surrounding"],
				'mine':		MINE,
				'unknown':	UNKNOWN
			}[cell["state"]]

		return resp

	def clear_cells(self):
		coords_list = tuple(tuple(c.tolist()) for c in
			numpy.transpose((self.game_grid == TO_CLEAR).nonzero())
		)

		print(" {}".format(len(coords_list)), end='', flush=True)

		self.turns_hash_sum += hash(coords_list)

		resp = self.action({
			"action": "clearCells",
			"coords": coords_list
		})

		print("->{}".format(len(resp["newCellData"])), end='', flush=True)

		if self.game_over:
			raise GameEnd(self)

	# Iterator for co-ordinate tuples of all cells in contact with a given cell.
	def get_surrounding(self, coords):
		if not coords in self.surr_coords_lookup:
			self.surr_coords_lookup[coords] = []

			for shift in itertools.product(*([-1, 0, 1],) * len(coords)):
				surr_coords = tuple(sum(c) for c in zip(shift, coords))

				# Check all coords are positive
				if any(c < 0 for c in surr_coords):
					continue

				# Check all coords are within grid size
				if any(c >= d for c, d in zip(surr_coords, self.dims)):
					continue

				self.surr_coords_lookup[coords].append(surr_coords)

		return self.surr_coords_lookup[coords]

	def first_turn(self, coords=None):
		self.start_time = time.time()
		if coords == None:
			coords = tuple(
				math.floor(random.random() * dim) for dim in self.dims
			)

		if coords == 0:
			coords = (0,) * len(self.dims)

		print("Clearing...", end='', flush=True)
		self.game_grid[coords] = TO_CLEAR
		self.clear_cells()

	# If a pass of a state results in a change, go back to the previous stage.
	# A turn is ready to submit when the final stage passes without a change,
	# and there is at least one cell set to TO_CLEAR.
	#@profile
	def turn(self, strategy_name):
		mine_zones = None

		# 1. Create a MineZone for each cell with mines around
		def create_zones():
			nonlocal mine_zones
			mine_zones = []

			def create_zone(coords):
				zone_cells = frozenset([
					surr for surr in self.get_surrounding(coords) if
							self.game_grid[surr] == UNKNOWN
				])

				known_mines = sum(1 for surr in self.get_surrounding(coords)
						if self.game_grid[surr] == MINE)

				zone_mines = self.game_grid[coords] - known_mines

				if len(zone_cells) == 0:
					return

				mine_zones.append(MineZone(
					zone_cells,
					zone_mines,
					zone_mines
				))

			for coords in numpy.transpose((self.game_grid > 0).nonzero()):
				create_zone(tuple(coords))

			return False

		# 2. Check for zones to clear/flag
		def mark_clear_flag():
			changed = False
			for zone in mine_zones:
				if zone.can_flag:
					for coords in zone.cells:
						self.game_grid[coords] = MINE
						changed = True
				if zone.can_clear:
					for coords in zone.cells:
						self.game_grid[coords] = TO_CLEAR
						changed = True
			return changed

		# 3. Substract from zones which fully cover another zone
		def subtract_subsets():
			nonlocal mine_zones
			changed = False
			for i, j in itertools.combinations(range(len(mine_zones)), 2):
				if len(mine_zones[i]) == 0 or len(mine_zones[j]) == 0:
					continue

				if mine_zones[i] == mine_zones[j]:
					changed = True
					mine_zones[i] &= mine_zones[j]
					mine_zones[j] = MineZone()

				elif mine_zones[i] < mine_zones[j]:
					changed = True
					mine_zones[j] -= mine_zones[i]

				elif mine_zones[i] > mine_zones[j]:
					changed = True
					mine_zones[i] -= mine_zones[j]

			return changed

		# TODO:
		# If the combination of two zones has fixed mine count, add it to
		# mine_zones.
		def combine_overlaps():
			pass

		# 4. Split each overlapping zone
		# TODO: This stage hasn't seemed to achieved any additional clearings so
		# far. Possibly should be removed.
		def split_overlaps():
			nonlocal mine_zones
			changed = False

			for i, j in itertools.combinations(range(len(mine_zones)), 2):
				# if not mine_zones[i].fixed or not mine_zones[j].fixed:
				# 	continue

				if len(mine_zones[i] & mine_zones[j]) == 0:
					continue

				if (
					mine_zones[i] < mine_zones[j] or
					mine_zones[i] == mine_zones[j] or
					mine_zones[i] > mine_zones[j]
				):
					continue

				split_zones = [
					mine_zones[j] - mine_zones[i],
					mine_zones[i] -  mine_zones[j],
					mine_zones[i] & mine_zones[j]
				]

				# print("removing:\n{}\n{};".format(mine_zones[i], mine_zones[j]))
				# print("adding:\n{}".format('\n'.join(map(str, split_zones))))

				changed = True
				mine_zones[i] = MineZone()
				mine_zones[j] = MineZone()
				mine_zones += split_zones

		# 5. Exhaustive test of all possible mine positions in overlapping zones
		# TODO: find elegant way to go back to first stage after a change here,
		# instead of back to previous stage.
		def exhaustive_zone_test():
			nonlocal mine_zones
			for i, j in itertools.combinations(range(len(mine_zones)), 2):
				if not mine_zones[i].fixed or not mine_zones[j].fixed:
					continue

				test_cells = mine_zones[i].cells | mine_zones[j].cells
				valid_mine_patterns = []

				# Try every combination of cells as mines
				for n in range(1, len(test_cells) + 1):
					for test_mines in itertools.combinations(test_cells, n):
						test_mines = frozenset(test_mines)
						pattern_valid = True
						# Check whether no. of mines is correct for both zones
						for zone in (mine_zones[i], mine_zones[j]):
							if len(test_mines & zone.cells) != zone.min_mines:
								pattern_valid = False
								break

						if pattern_valid:
							valid_mine_patterns.append(test_mines)

				# print("valid patterns: {}".format(valid_mine_patterns))
				for cell in test_cells:
					if all(cell not in pattern for pattern in
							valid_mine_patterns):
						self.game_grid[cell] = TO_CLEAR
					elif all(cell in pattern for pattern in
							valid_mine_patterns):
						self.game_grid[cell] = MINE

			return False

		strategy = {
			"strat0" : [
				create_zones,
				mark_clear_flag,
				exhaustive_zone_test
			],
			"strat1" : [
				create_zones,
				mark_clear_flag,
				subtract_subsets,
				exhaustive_zone_test
			],
		}[strategy_name]

		# Recursive function to allow more flexible control flows. The provided
		# list of stages are performed in order, with the previous stage being
		# revisited if something changes. A stage can be a single function or
		# a nested list of stages.
		def perform_stages(stage):
			if callable(stage):
				return stage()

			i = 0
			changed = False
			while i < len(stage):
				increment = 1
				if perform_stages(stage[i]):
					changed = True
					# Go back to previous set on change, if possible
					if i > 0:
						increment = -1
				i += increment
			return changed

		perform_stages(strategy)

		if (self.game_grid == TO_CLEAR).any():
			self.clear_cells()
		else:
			raise GameEnd(self, "Out of ideas!")

def play_game(game, strategy_name):
	try:
		game.first_turn(0)
		while True:
			game.turn(strategy_name)
	except GameEnd as e:
		pass
	return game.id

def play_all_strategies(dims, mines):
	# game = Game(dims, mines)
	game = Game(dims, mines)
	play_game(game, "strat0")
	game_repeat = Game(reload_id=game.id)
	play_game(game_repeat, "strat1")

if __name__ == '__main__':
	play_all_strategies([160, 160], 1500)

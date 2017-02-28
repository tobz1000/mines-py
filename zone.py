#!/usr/bin/env python3

class Zone:
	def __init__(self, size, count):
		assert size >= 0
		assert count >= 0
		assert count <= size

		self.size = size
		self.count = count

	def sub_zones(self, size):
		return (Zone(size, c) for c in range(0, min(self.size, size) + 1))

	def __repr__(self):
		return "Z({},{})".format(self.size, self.count)

def set_counts(a, b, shared_size):
	assert a.size >= shared_size
	assert b.size >= shared_size

	for s in a.sub_zones(shared_size):
		try:
			a_diff_b = Zone(a.size - s.size, a.count - s.count)
			b_diff_a = Zone(b.size - s.size, b.count - s.count)
		except AssertionError:
			continue

		yield (a_diff_b, s, b_diff_a)

def print_intersect_diffs(a, b, shared_size):
	sc = list(set_counts(a, b, shared_size))

	if len(sc) == 0:
		return
	print("{}, {}, shared={}:".format(a, b, shared_size))

	for a_d, s, b_d in sc:
		print("  {}, {}, {}".format(a_d.count, s.count, b_d.count))

	print("            {}".format(intersect_diff_count(a, b, shared_size)))

def intersect_diff_count(a, b, shared_size):
	min_shared_mines = max(
		0,
		a.count - (a.size - shared_size),
		b.count - (b.size - shared_size)
	)

	max_shared_mines = shared_size - max(
		0,
		shared_size - a.count,
		shared_size - b.count
	)

	return max_shared_mines - min_shared_mines

for s in range(6):
	for a_size in range(s, s + 3):
		for a_count in range(a_size + 1):
			for b_size in range(s, s + 3):
				for b_count in range(b_size + 1):
					print_intersect_diffs(
						Zone(a_size, a_count),
						Zone(b_size, b_count),
						s
					)

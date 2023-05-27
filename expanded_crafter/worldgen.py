import functools

import numpy as np
import matplotlib.pyplot as plt
import opensimplex

from . import constants
from . import objects


def generate_world(world, player):
    simplex = opensimplex.OpenSimplex(seed=world.random.randint(0, 2**31 - 1))
    tunnels = np.zeros(world.area, bool)
    poles = np.zeros(world.area, bool)
    world_x, world_y = world.area

    north_pole = world.random.uniform(world_y / 8, world_y / 4)
    south_pole = world.random.uniform((6.0 * world_y) / 8, world_y)
    for y in range(poles.shape[1]):
        poles[y, : int(north_pole)] = True
        poles[y, int(south_pole) :] = True
        north_pole = max(north_pole + world.random.normal(0), 1)
        south_pole = min(south_pole + world.random.normal(0), world_y - 1)

    starts = np.zeros((world.area[0], world.area[1]))
    water = np.zeros((world.area[0], world.area[1]))
    mountain = np.zeros((world.area[0], world.area[1]))
    water_threshold = np.zeros((world.area[0], world.area[1]))
    for x in range(world.area[0]):
        for y in range(world.area[1]):
            start_x_y, mtn_x_y, water_x_y, water_threshold_x_y = _set_material(
                world,
                (x, y),
                player,
                tunnels,
                poles,
                simplex,
            )
            starts[x, y] = start_x_y
            mountain[x, y] = mtn_x_y
            water[x, y] = water_x_y
            water_threshold[x, y] = water_threshold_x_y
    for x in range(world.area[0]):
        for y in range(world.area[1]):
            _set_object(world, (x, y), player, tunnels)


def _set_material(world, pos, player, tunnels, poles, simplex):
    x, y = pos
    simplex = functools.partial(_simplex, simplex)
    uniform = world.random.uniform

    # create surface that has high value very close to spawn
    dist_from_player = np.sqrt((x - player.pos[0]) ** 2 + (y - player.pos[1]) ** 2)
    start = 4 - dist_from_player + (2 * simplex(x, y, 8, 3))
    start = 1 / (1 + np.exp(-start))  # (0, 1)

    # where do these numbers come from
    water = simplex(x, y, 3, {15: 1, 5: 0.15}, False) + 0.1
    water -= 2 * start  # decrease water odds close to spawn?
    mountain = simplex(x, y, 0, {15: 1, 5: 0.3})
    mountain -= 4 * start + 0.3 * water

    water_coeff = world.random.uniform(0.5, 1.5)
    water_pos = abs(y - player.pos[1]) / world.area[1]
    water_threshold = 0.3 * (1.0 + water_coeff * water_pos)
    shore_threshold = 0.05 * (1.0 + water_coeff * water_pos)

    # makes region right by spawn grass
    if start > 0.5:
        world[x, y] = "grass"
    elif mountain > 0.15:
        if simplex(x, y, 6, 7) > 0.15 and mountain > 0.3:  # cave
            world[x, y] = "path"
        elif simplex(2 * x, y / 5, 7, 3) > 0.4:  # horizonal tunnle
            world[x, y] = "path"
            tunnels[x, y] = True
        elif simplex(x / 5, 2 * y, 7, 3) > 0.4:  # vertical tunnle
            world[x, y] = "path"
            tunnels[x, y] = True
        elif simplex(x, y, 1, 8) > 0 and uniform() > 0.85:
            world[x, y] = "coal"
        elif simplex(x, y, 2, 6) > 0.4 and uniform() > 0.75:
            world[x, y] = "iron"
        elif simplex(x, y, 3, 5) > 0.3 and uniform() > 0.75:
            world[x, y] = "gold"
        elif simplex(x, y, 4, 5) > 0.22 and uniform() > 0.7:
            world[x, y] = "emerald"
        elif mountain > 0.18 and uniform() > 0.994:
            world[x, y] = "diamond"
        elif mountain > 0.3 and simplex(x, y, 6, 5) > 0.35:
            world[x, y] = "lava"
        else:
            world[x, y] = "stone"

    elif (
        water_threshold - shore_threshold < water <= water_threshold + shore_threshold
        and simplex(x, y, 4, 9) > -0.2
    ):
        if poles[x, y] and y < world.area[1] // 2:
            world[x, y] = "ice"
        elif poles[x, y] and y > world.area[1] // 2:
            world[x, y] = "mud"
        else:
            world[x, y] = "sand"
    elif water_threshold < water:
        world[x, y] = "water"
    else:  # normal terrain
        if poles[x, y] and y < world.area[1] // 2:
            if simplex(x, y, 5, 7) > 0 and uniform() > 0.9:
                world[x, y] = "pinetree"
            else:
                world[x, y] = "snow"
        elif poles[x, y] and y > world.area[1] // 2:
            if simplex(x, y, 7, 5) > 0.6 and uniform() > 0.85:
                world[x, y] = "pyramid"
            elif simplex(x, y, 5, 7) > 0 and uniform() > 0.9:
                world[x, y] = "cactus"
            else:
                world[x, y] = "sand"
        else:
            if simplex(x, y, 5, 7) > 0 and uniform() > 0.8:
                world[x, y] = "tree"
            elif simplex(x, y, 6, 2) > 0.2 and uniform() > 0.7:
                world[x, y] = "flower"
            else:
                world[x, y] = "grass"

    return start, mountain, water, water_threshold


def _set_object(world, pos, player, tunnels):
    x, y = pos
    uniform = world.random.uniform
    dist = np.sqrt((x - player.pos[0]) ** 2 + (y - player.pos[1]) ** 2)
    material, _ = world[x, y]
    if material not in constants.walkable:
        pass
    elif dist > 3 and material == "grass" and uniform() > 0.985:
        world.add(objects.Cow(world, (x, y)))
    elif dist > 3 and material == "grass" and uniform() > 0.99:
        world.add(objects.Pig(world, (x, y)))
    elif dist > 3 and material == "snow" and uniform() > 0.99:
        world.add(objects.Penguin(world, (x, y)))
    elif dist > 10 and uniform() > 0.993:
        world.add(objects.Zombie(world, (x, y), player))
    elif dist > 10 and material == "snow" and uniform() > 0.997:
        world.add(objects.Moose(world, (x, y), player))
    elif dist > 10 and material == "grass" and uniform() > 0.998:
        world.add(objects.BrownBear(world, (x, y), player))
    elif dist > 10 and material == "snow" and uniform() > 0.9985:
        world.add(objects.PolarBear(world, (x, y), player))
    elif material == "path" and tunnels[x, y] and uniform() > 0.95:
        world.add(objects.Skeleton(world, (x, y), player))


def _simplex(simplex, x, y, z, sizes, normalize=True):
    if not isinstance(sizes, dict):
        sizes = {sizes: 1}
    value = 0
    for size, weight in sizes.items():
        if hasattr(simplex, "noise3d"):
            noise = simplex.noise3d(x / size, y / size, z)
        else:
            noise = simplex.noise3(x / size, y / size, z)
        value += weight * noise
    if normalize:
        value /= sum(sizes.values())
    return value

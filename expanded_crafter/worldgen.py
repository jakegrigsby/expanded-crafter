import functools

import numpy as np
import matplotlib.pyplot as plt
import opensimplex

from . import constants
from . import objects


def generate_world(world, player):
    simplex = opensimplex.OpenSimplex(seed=world.random.randint(0, 2**31 - 1))
    tunnels = np.zeros(world.area, bool)
    starts = np.zeros((world.area[0], world.area[1]))
    water = np.zeros((world.area[0], world.area[1]))
    mountain = np.zeros((world.area[0], world.area[1]))
    desert = np.zeros((world.area[0], world.area[1]))
    snow = np.zeros((world.area[0], world.area[1]))
    for x in range(world.area[0]):
        for y in range(world.area[1]):
            start_x_y, mtn_x_y, water_x_y, desert_x_y, snow_x_y = _set_material(
                world, (x, y), player, tunnels, simplex
            )
            starts[x, y] = start_x_y
            mountain[x, y] = mtn_x_y
            water[x, y] = water_x_y
            desert[x, y] = desert_x_y
            snow[x, y] = snow_x_y
    for x in range(world.area[0]):
        for y in range(world.area[1]):
            _set_object(world, (x, y), player, tunnels)

    plt.imshow(desert)
    plt.show()


def _set_material(world, pos, player, tunnels, simplex):
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

    # needs tuning
    desert = simplex(x, y, 2, {50: 1, 20: 0.5, 5: 0.15})
    desert -= 2 * start
    snow = simplex(x, y, 4, {50: 1, 20: 0.5, 5: 0.15})
    snow -= 2 * start

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
        elif mountain > 0.18 and uniform() > 0.994:
            world[x, y] = "diamond"
        elif mountain > 0.3 and simplex(x, y, 6, 5) > 0.35:
            world[x, y] = "lava"
        else:
            world[x, y] = "stone"
    elif 0.25 < water <= 0.35 and simplex(x, y, 4, 9) > -0.2:
        world[x, y] = "sand"
    elif 0.3 < water:
        world[x, y] = "water"
    elif 0.2 < desert:
        world[x, y] = "sand"
    elif 0.2 < snow:
        world[x, y] = "snow"
    else:  # grassland
        if simplex(x, y, 5, 7) > 0 and uniform() > 0.8:
            world[x, y] = "tree"
        else:
            world[x, y] = "grass"

    return start, mountain, water, desert, snow


def _set_object(world, pos, player, tunnels):
    x, y = pos
    uniform = world.random.uniform
    dist = np.sqrt((x - player.pos[0]) ** 2 + (y - player.pos[1]) ** 2)
    material, _ = world[x, y]
    if material not in constants.walkable:
        pass
    elif dist > 3 and material == "grass" and uniform() > 0.985:
        world.add(objects.Cow(world, (x, y)))
    elif dist > 10 and uniform() > 0.993:
        world.add(objects.Zombie(world, (x, y), player))
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

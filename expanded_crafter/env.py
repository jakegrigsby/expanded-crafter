import collections

import numpy as np

from . import constants
from . import engine
from . import objects
from . import worldgen


# Gym is an optional dependency.
try:
    import gym

    DiscreteSpace = gym.spaces.Discrete
    BoxSpace = gym.spaces.Box
    DictSpace = gym.spaces.Dict
    BaseClass = gym.Env
except ImportError:
    DiscreteSpace = collections.namedtuple("DiscreteSpace", "n")
    BoxSpace = collections.namedtuple("BoxSpace", "low, high, shape, dtype")
    DictSpace = collections.namedtuple("DictSpace", "spaces")
    BaseClass = object


class Env(BaseClass):
    def __init__(
        self,
        area=(256, 256),
        view=(9, 9),
        size=(64, 64),
        reward=True,
        length=10000,
        seed=None,
    ):
        view = np.array(view if hasattr(view, "__len__") else (view, view))
        size = np.array(size if hasattr(size, "__len__") else (size, size))
        seed = np.random.randint(0, 2**31 - 1) if seed is None else seed
        self._area = area
        self._view = view
        self._size = size
        self._reward = reward
        self._length = length
        self._seed = seed
        self._episode = 0
        self._world = engine.World(area, constants.materials, (12, 12))
        self._textures = engine.Textures(constants.root / "assets")
        item_rows = int(np.ceil(len(constants.items) / view[0]))
        self._local_view = engine.LocalView(
            self._world, self._textures, [view[0], view[1] - item_rows]
        )
        self._item_view = engine.ItemView(self._textures, [view[0], item_rows])
        self._sem_view = engine.SemanticView(
            self._world,
            [
                objects.Player,
                objects.Cow,
                objects.Zombie,
                objects.Skeleton,
                objects.Arrow,
                objects.Plant,
                objects.Corn,
                objects.Berry,
                objects.Pig,
                objects.Sheep,
                objects.Camel,
                objects.Moose,
                objects.Penguin,
                objects.BrownBear,
                objects.PolarBear,
                objects.Raider,
                objects.Fence,
                objects.Fire,
            ],
        )
        self._step = None
        self._player = None
        self._last_health = None
        self._unlocked = None
        # Some libraries expect these attributes to be set.
        self.reward_range = None
        self.metadata = None

    @property
    def observation_space(self):
        return BoxSpace(0, 255, tuple(self._size) + (3,), np.uint8)

    @property
    def action_space(self):
        return DiscreteSpace(len(constants.actions))

    @property
    def action_names(self):
        return constants.actions

    def reset(self):
        center = (self._world.area[0] // 2, self._world.area[1] // 2)
        self._episode += 1
        self._step = 0
        self._world.reset(seed=hash((self._seed, self._episode)) % (2**31 - 1))
        self._update_time()
        self._player = objects.Player(self._world, center)
        self._last_health = self._player.health
        self._world.add(self._player)
        self._unlocked = set()
        worldgen.generate_world(self._world, self._player)
        return self._obs()

    def step(self, action):
        self._step += 1
        self._update_time()
        self._player.action = constants.actions[action]
        for obj in self._world.objects:
            if self._player.distance(obj) < 2 * max(self._view):
                obj.update()
        if self._step % 10 == 0:
            for chunk, objs in self._world.chunks.items():
                # xmin, xmax, ymin, ymax = chunk
                # center = (xmax - xmin) // 2, (ymax - ymin) // 2
                # if self._player.distance(center) < 4 * max(self._view):
                self._balance_chunk(chunk, objs)
        obs = self._obs()
        reward = (self._player.health - self._last_health) / 10
        self._last_health = self._player.health
        unlocked = {
            name
            for name, count in self._player.achievements.items()
            if count > 0 and name not in self._unlocked
        }
        if unlocked:
            self._unlocked |= unlocked
            reward += 1.0
        dead = self._player.health <= 0
        over = self._length and self._step >= self._length
        done = dead or over
        info = {
            "inventory": self._player.inventory.copy(),
            "achievements": self._player.achievements.copy(),
            "discount": 1 - float(dead),
            "semantic": self._sem_view(),
            "player_pos": self._player.pos,
            "reward": reward,
        }
        if not self._reward:
            reward = 0.0
        return obs, reward, done, info

    def render(self, size=None):
        size = size or self._size
        unit = size // self._view
        canvas = np.zeros(tuple(size) + (3,), np.uint8)
        local_view = self._local_view(self._player, unit)
        item_view = self._item_view(self._player.inventory, unit)
        view = np.concatenate([local_view, item_view], 1)
        border = (size - (size // self._view) * self._view) // 2
        (x, y), (w, h) = border, view.shape[:2]
        canvas[x : x + w, y : y + h] = view
        return canvas.transpose((1, 0, 2))

    def _obs(self):
        return self.render()

    def _update_time(self):
        """
        changed from crafter default to 1) start at morning 2) have longer days with more sunlight
        """
        progress = (self._step / 400) + 0.15
        daylight = 1 - np.abs(np.cos(np.pi * progress)) ** 4
        self._world.daylight = daylight

    def _balance_chunk(self, chunk, objs):
        light = self._world.daylight
        self._balance_object(
            chunk=chunk,
            objs=objs,
            cls=objects.Zombie,
            material=("grass", "snow", "sand"),
            span_dist=6,
            despan_dist=0,
            spawn_prob=0.2,
            despawn_prob=0.4,
            ctor=lambda pos: objects.Zombie(self._world, pos, self._player),
            target_fn=lambda num, space: (
                1.0 * (light < 0.3) and (space > 30),
                3.0 * (light < 0.3) and (space > 30),
            ),
        )
        self._balance_object(
            chunk,
            objs,
            objects.Skeleton,
            "path",
            7,
            7,
            0.1,
            0.1,
            lambda pos: objects.Skeleton(self._world, pos, self._player),
            lambda num, space: (0 if space < 6 else 1, 2),
        )
        self._balance_object(
            chunk,
            objs,
            objects.Cow,
            "grass",
            5,
            5,
            0.01,
            0.1,
            lambda pos: objects.Cow(self._world, pos),
            lambda num, space: (0 if space < 30 else 1, 1.5 + light),
        )
        self._balance_object(
            chunk,
            objs,
            objects.Pig,
            "grass",
            5,
            5,
            0.01,
            0.1,
            lambda pos: objects.Pig(self._world, pos),
            lambda num, space: (0 if space < 30 else 1, 1.5 + light),
        )
        self._balance_object(
            chunk,
            objs,
            objects.Sheep,
            "grass",
            5,
            5,
            0.01,
            0.1,
            lambda pos: objects.Sheep(self._world, pos),
            lambda num, space: (0 if space < 30 else 1, 1.5 + light),
        )
        self._balance_object(
            chunk,
            objs,
            objects.Camel,
            "sand",
            5,
            5,
            0.01,
            0.1,
            lambda pos: objects.Camel(self._world, pos),
            lambda num, space: (0 if space < 30 else 1, 1.5 + light),
        )
        self._balance_object(
            chunk,
            objs,
            objects.Moose,
            "snow",
            8,
            8,
            0.01,
            0.1,
            lambda pos: objects.Moose(self._world, pos, self._player),
            lambda num, space: (0 if space < 30 else 1, 2.0),
        )
        self._balance_object(
            chunk,
            objs,
            objects.Penguin,
            "snow",
            4,
            4,
            0.01,
            0.1,
            lambda pos: objects.Penguin(self._world, pos),
            lambda num, space: (0 if space < 30 else 1, 2.0 + light),
        )
        self._balance_object(
            chunk,
            objs,
            objects.BrownBear,
            "grass",
            10,
            10,
            0.005,
            0.08,
            lambda pos: objects.BrownBear(self._world, pos, self._player),
            lambda num, space: (0 if space < 30 else 0, 1),
        )
        self._balance_object(
            chunk,
            objs,
            objects.PolarBear,
            "snow",
            10,
            10,
            0.004,
            0.08,
            lambda pos: objects.PolarBear(self._world, pos, self._player),
            lambda num, space: (0 if space < 30 else 0, 1),
        )
        self._balance_object(
            chunk,
            objs,
            objects.Raider,
            ("grass", "snow", "sand"),
            20,
            20,
            0.002,
            0.06,
            lambda pos: objects.Raider(self._world, pos, self._player),
            lambda num, space: (0 if space < 30 else 0, 1),
        )

    def _balance_object(
        self,
        chunk,
        objs,
        cls,
        material,
        span_dist,
        despan_dist,
        spawn_prob,
        despawn_prob,
        ctor,
        target_fn,
    ):
        xmin, xmax, ymin, ymax = chunk
        random = self._world.random
        creatures = [obj for obj in objs if isinstance(obj, cls)]

        if not isinstance(material, tuple):
            material = (material,)

        mask = None
        for material_i in material:
            mask_i = self._world.mask(*chunk, material_i)
            mask = mask_i if mask is None else mask | mask_i

        # range of object counts based on how much space they have to spawn
        target_min, target_max = target_fn(len(creatures), mask.sum())
        if len(creatures) < int(target_min) and random.uniform() < spawn_prob:
            # spawn new object
            xs = np.tile(np.arange(xmin, xmax)[:, None], [1, ymax - ymin])
            ys = np.tile(np.arange(ymin, ymax)[None, :], [xmax - xmin, 1])
            xs, ys = xs[mask], ys[mask]
            i = random.randint(0, len(xs))
            pos = np.array((xs[i], ys[i]))
            empty = self._world[pos][1] is None
            away = self._player.distance(pos) >= span_dist
            if empty and away:
                self._world.add(ctor(pos))
        elif len(creatures) > int(target_max) and random.uniform() < despawn_prob:
            # despawn object
            obj = random.choice(creatures)
            away = self._player.distance(obj.pos) >= despan_dist
            if away:
                self._world.remove(obj)

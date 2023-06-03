import collections
import functools
import pathlib

import imageio
import numpy as np
from PIL import Image, ImageEnhance


class AttrDict(dict):

    __getattr__ = dict.__getitem__


class staticproperty:
    def __init__(self, function):
        self.function = function

    def __get__(self, instance, owner=None):
        return self.function()


class World:
    def __init__(self, area, materials, chunk_size):
        self.area = area
        self._chunk_size = chunk_size
        self._mat_names = {i: x for i, x in enumerate([None] + materials)}
        self._mat_ids = {x: i for i, x in enumerate([None] + materials)}
        self.reset()

    def reset(self, seed=None):
        self.random = np.random.RandomState(seed)
        self.daylight = 0.0
        self._chunks = collections.defaultdict(set)
        self._objects = [None]
        self._mat_map = np.zeros(self.area, np.uint8)
        self._obj_map = np.zeros(self.area, np.uint32)

    @property
    def objects(self):
        # Return a new list so the objects cannot change while being iterated over.
        return [obj for obj in self._objects if obj]

    @property
    def chunks(self):
        return self._chunks.copy()

    def add(self, obj):
        assert hasattr(obj, "pos")
        obj.pos = np.array(obj.pos)
        assert self._obj_map[tuple(obj.pos)] == 0
        index = len(self._objects)
        self._objects.append(obj)
        self._obj_map[tuple(obj.pos)] = index
        self._chunks[self.chunk_key(obj.pos)].add(obj)

    def remove(self, obj):
        if obj.removed:
            return
        self._objects[self._obj_map[tuple(obj.pos)]] = None
        self._obj_map[tuple(obj.pos)] = 0
        self._chunks[self.chunk_key(obj.pos)].remove(obj)
        obj.removed = True

    def move(self, obj, pos):
        if obj.removed:
            return
        pos = np.array(pos)
        assert self._obj_map[tuple(pos)] == 0
        index = self._obj_map[tuple(obj.pos)]
        self._obj_map[tuple(pos)] = index
        self._obj_map[tuple(obj.pos)] = 0
        old_chunk = self.chunk_key(obj.pos)
        new_chunk = self.chunk_key(pos)
        if old_chunk != new_chunk:
            self._chunks[old_chunk].remove(obj)
            self._chunks[new_chunk].add(obj)
        obj.pos = pos

    def __setitem__(self, pos, material):
        if material not in self._mat_ids:
            id_ = len(self._mat_ids)
            self._mat_ids[material] = id_
        self._mat_map[tuple(pos)] = self._mat_ids[material]

    def __getitem__(self, pos):
        if not _inside((0, 0), pos, self.area):
            return None, None
        material = self._mat_names[self._mat_map[tuple(pos)]]
        obj = self._objects[self._obj_map[tuple(pos)]]
        return material, obj

    def nearby(self, pos, distance):
        (x, y), d = pos, distance
        ids = set(
            self._mat_map[x - d : x + d + 1, y - d : y + d + 1].flatten().tolist()
        )
        materials = tuple(self._mat_names[x] for x in ids)
        indices = self._obj_map[x - d : x + d + 1, y - d : y + d + 1].flatten().tolist()
        objs = {self._objects[i] for i in indices if i > 0}
        return materials, objs

    def mask(self, xmin, xmax, ymin, ymax, material):
        region = self._mat_map[xmin:xmax, ymin:ymax]
        return region == self._mat_ids[material]

    def count(self, material):
        return (self._mat_map == self._mat_ids[material]).sum()

    def chunk_key(self, pos):
        (x, y), (csx, csy) = pos, self._chunk_size
        xmin, ymin = (x // csx) * csx, (y // csy) * csy
        xmax = min(xmin + csx, self.area[0])
        ymax = min(ymin + csy, self.area[1])
        return (xmin, xmax, ymin, ymax)


class Textures:
    def __init__(self, directory):
        self._originals = {}
        self._textures = {}
        for filename in pathlib.Path(directory).glob("*.png"):
            image = imageio.imread(filename.read_bytes())
            image = image.transpose((1, 0) + tuple(range(2, len(image.shape))))
            self._originals[filename.stem] = image
            self._textures[(filename.stem, image.shape[:2])] = image

    def get(self, name, size):
        if name is None:
            name = "unknown"
        size = int(size[0]), int(size[1])
        key = name, size
        if key not in self._textures:
            image = self._originals[name]
            image = Image.fromarray(image)
            image = image.resize(size[::-1], resample=Image.NEAREST)
            image = np.array(image)
            self._textures[key] = image
        return self._textures[key]


class GlobalView:

    pass


class UncoverView:

    pass


class LocalView:
    def __init__(self, world, textures, grid):
        self._world = world
        self._textures = textures
        self._grid = np.array(grid)
        self._offset = self._grid // 2
        self._area = np.array(self._world.area)
        self._center = None

    def __call__(self, player, unit):
        self._unit = np.array(unit)
        self._center = np.array(player.pos)
        canvas = np.zeros(tuple(self._grid * unit) + (3,), np.uint8) + 127
        for x in range(self._grid[0]):
            for y in range(self._grid[1]):
                pos = self._center + np.array([x, y]) - self._offset
                if not _inside((0, 0), pos, self._area):
                    continue
                texture = self._textures.get(self._world[pos][0], unit)
                _draw(canvas, np.array([x, y]) * unit, texture)

        fire_pos = []
        for obj in self._world.objects:
            pos = obj.pos - self._center + self._offset
            if not _inside((0, 0), pos, self._grid):
                continue
            texture = self._textures.get(obj.texture, unit)
            _draw_alpha(canvas, pos * unit, texture)
            if "fire" in obj.texture:
                fire_pos.append(pos * unit)
        canvas = self._light(canvas, self._world.daylight, fire_pos=fire_pos)
        if player.sleeping:
            canvas = self._sleep(canvas)
        # if player.health < 1:
        #   canvas = self._tint(canvas, (128, 0, 0), 0.6)
        return canvas

    def _sleep(self, canvas):
        canvas = np.array(
            ImageEnhance.Color(Image.fromarray(canvas.astype(np.uint8))).enhance(0.0)
        )
        canvas = self._tint(canvas, (0, 0, 16), 0.5)
        return canvas

    def _light(self, canvas, daylight, fire_pos):
        if daylight > 0.9:
            return canvas

        darkness = np.ones_like(canvas).astype(np.float32)
        for fire in fire_pos:
            fire_loc = ((np.array(fire) / np.array(canvas.shape[:-1])) - 0.5) * 2.0
            fire_loc = fire_loc[0], fire_loc[1]
            darkness -= 1.0 - self._vignette(canvas.shape, stddev=0.5, center=fire_loc)

        dark = self._tint(canvas, color=(38, 37, 54), amount=min(1.0 - daylight, 0.9))
        fire = self._tint(
            canvas, color=(217, 179, 76), amount=min(1.0 - daylight, 0.9) / 3
        )
        dark_canvas = dark * darkness + fire * (1.0 - darkness)

        final = (1.0 - daylight) * (dark_canvas) + daylight * canvas
        return final

    def _tint(self, canvas, color, amount):
        color = np.array(color)
        return (1 - amount) * canvas + amount * color

    @functools.lru_cache(10)
    def _vignette(self, shape, stddev, center):
        x, y = center
        xs, ys = np.meshgrid(np.linspace(-1, 1, shape[0]), np.linspace(-1, 1, shape[1]))
        vig = 1 - np.exp(-0.5 * ((xs - x) ** 2 + (ys - y) ** 2) / (stddev**2)).T
        return vig[..., np.newaxis].astype(np.float32)


class ItemView:
    def __init__(self, textures, grid):
        self._textures = textures
        self._grid = np.array(grid)

    def __call__(self, inventory, unit):
        unit = np.array(unit)
        canvas = np.zeros(tuple(self._grid * unit) + (3,), np.uint8)
        for index, (item, amount) in enumerate(inventory.items()):
            if amount < 1:
                continue
            self._item(canvas, index, item, unit)
            self._amount(canvas, index, amount, unit)
        return canvas

    def _item(self, canvas, index, item, unit):
        pos = index % self._grid[0], index // self._grid[0]
        pos = (pos * unit + 0.1 * unit).astype(np.int32)
        texture = self._textures.get(item, 0.8 * unit)
        _draw_alpha(canvas, pos, texture)

    def _amount(self, canvas, index, amount, unit):
        pos = index % self._grid[0], index // self._grid[0]
        pos = (pos * unit + 0.4 * unit).astype(np.int32)
        text = str(amount) if amount in list(range(10)) else "unknown"
        texture = self._textures.get(text, 0.6 * unit)
        _draw_alpha(canvas, pos, texture)


class SemanticView:
    def __init__(self, world, obj_types):
        self._world = world
        self._mat_ids = world._mat_ids.copy()
        self._obj_ids = {c: len(self._mat_ids) + i for i, c in enumerate(obj_types)}

    def __call__(self):
        canvas = self._world._mat_map.copy()
        for obj in self._world.objects:
            canvas[tuple(obj.pos)] = self._obj_ids[type(obj)]
        return canvas


def _inside(lhs, mid, rhs):
    return (lhs[0] <= mid[0] < rhs[0]) and (lhs[1] <= mid[1] < rhs[1])


def _draw(canvas, pos, texture):
    (x, y), (w, h) = pos, texture.shape[:2]
    if texture.shape[-1] == 4:
        texture = texture[..., :3]
    canvas[x : x + w, y : y + h] = texture


def _draw_alpha(canvas, pos, texture):
    (x, y), (w, h) = pos, texture.shape[:2]
    if texture.shape[-1] == 4:
        alpha = texture[..., 3:].astype(np.float32) / 255
        texture = texture[..., :3].astype(np.float32) / 255
        current = canvas[x : x + w, y : y + h].astype(np.float32) / 255
        blended = alpha * texture + (1 - alpha) * current
        texture = (255 * blended).astype(np.uint8)
    canvas[x : x + w, y : y + h] = texture

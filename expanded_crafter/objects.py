import numpy as np

from . import constants
from . import engine


class Object:
    def __init__(self, world, pos):
        self.world = world
        self.pos = np.array(pos)
        self.random = world.random
        self.inventory = {"health": 0}
        self.removed = False

    @property
    def texture(self):
        raise "unknown"

    @property
    def walkable(self):
        return constants.walkable

    @property
    def health(self):
        return self.inventory["health"]

    @health.setter
    def health(self, value):
        self.inventory["health"] = max(0, value)

    @property
    def all_dirs(self):
        return ((-1, 0), (+1, 0), (0, -1), (0, +1))

    def move(self, direction):
        direction = np.array(direction)
        target = self.pos + direction
        if self.is_free(target):
            self.world.move(self, target)
            return True
        return False

    def is_free(self, target, materials=None):
        materials = self.walkable if materials is None else materials
        material, obj = self.world[target]
        return obj is None and material in materials

    def distance(self, target):
        if hasattr(target, "pos"):
            target = target.pos
        return np.abs(target - self.pos).sum()

    def toward(self, target, long_axis=True):
        if hasattr(target, "pos"):
            target = target.pos
        offset = target - self.pos
        dists = np.abs(offset)
        if dists[0] > dists[1] if long_axis else dists[0] <= dists[1]:
            return np.array((np.sign(offset[0]), 0))
        else:
            return np.array((0, np.sign(offset[1])))

    def take_damage(self, damage: int):
        self.health -= damage

    def random_dir(self):
        return self.all_dirs[self.random.randint(0, 4)]


class Player(Object):
    def __init__(self, world, pos):
        super().__init__(world, pos)
        self.facing = (0, 1)
        self.inventory = {
            name: info["initial"] for name, info in constants.items.items()
        }
        self.achievements = {name: 0 for name in constants.achievements}
        self.action = "noop"
        self.sleeping = False
        self._last_health = self.health
        self._on_material = "grass"
        self._hunger = 0
        self._thirst = 0
        self._fatigue = 0
        self._recover = 0
        self._armor = None

    @property
    def texture(self):
        if self._on_material in ["water", "deepwater"]:
            return {
                (-1, 0): "ship-left",
                (+1, 0): "ship-right",
                (0, -1): "ship-up",
                (0, +1): "ship-down",
            }[tuple(self.facing)]
        elif self.sleeping:
            return "player-sleep"
        else:
            armorstr = f"{self._armor}armor" if self._armor is not None else ""
            return {
                (-1, 0): f"player{armorstr}-left",
                (+1, 0): f"player{armorstr}-right",
                (0, -1): f"player{armorstr}-up",
                (0, +1): f"player{armorstr}-down",
            }[tuple(self.facing)]

    def take_damage(self, damage: int):
        if self._armor == "iron":
            damage = max(int(damage * 0.5), 1)
        elif self._armor == "diamond":
            damage = max(int(damage * 0.1), 1)
        elif self._armor == "magic":
            damage = min(int(damage * 0.1), 1)
        self.health -= damage

    @property
    def walkable(self):
        options = constants.walkable + ["lava"]
        if self.inventory["ship"]:
            options += ["water", "deepwater"]
        return options

    def update(self):
        target = (self.pos[0] + self.facing[0], self.pos[1] + self.facing[1])
        material, obj = self.world[target]
        action = self.action
        if self.sleeping:
            if self.inventory["energy"] < constants.items["energy"]["max"]:
                action = "sleep"
            else:
                self.sleeping = False
                self.achievements["wake_up"] += 1
        if action == "noop":
            pass
        elif action.startswith("move_"):
            self._move(action[len("move_") :])
        elif action == "do" and obj:
            self._do_object(obj)
        elif action == "do":
            self._do_material(target, material)
        elif action == "sleep":
            if self.inventory["energy"] < constants.items["energy"]["max"]:
                self.sleeping = True
        elif action.startswith("place_"):
            self._place(action[len("place_") :], target, material)
        elif action.startswith("make_"):
            self._make(action[len("make_") :])
        self._update_life_stats()
        self._degen_or_regen_health()
        for name, amount in self.inventory.items():
            maxmium = constants.items[name]["max"]
            self.inventory[name] = max(0, min(amount, maxmium))
        # This needs to happen after the inventory states are clamped
        # because it involves the health water inventory count.
        self._wake_up_when_hurt()
        self._on_material, _ = self.world[self.pos]

    def _update_life_stats(self):
        self._hunger += 0.25 if self.sleeping else 0.5
        if self._hunger > 25:
            self._hunger = 0
            self.inventory["food"] -= 1
        self._thirst += 0.25 if self.sleeping else 0.5
        if self._thirst > 20:
            self._thirst = 0
            self.inventory["drink"] -= 1
        if self.sleeping:
            self._fatigue = min(self._fatigue - 1, 0)
        else:
            self._fatigue += 0.5
        if self._fatigue < -10:
            self._fatigue = 0
            self.inventory["energy"] += 1
        if self._fatigue > 30:
            self._fatigue = 0
            self.inventory["energy"] -= 1

    def _degen_or_regen_health(self):
        necessities = (
            self.inventory["food"] > 0,
            self.inventory["drink"] > 0,
            self.inventory["energy"] > 0 or self.sleeping,
        )
        if all(necessities):
            self._recover += 2 if self.sleeping else 1
        else:
            self._recover -= 0.5 if self.sleeping else 1
        if self._recover > 25:
            self._recover = 0
            self.health += 1
        if self._recover < -15:
            self._recover = 0
            self.health -= 1

    def _wake_up_when_hurt(self):
        if self.health < self._last_health:
            self.sleeping = False
        self._last_health = self.health

    def _move(self, direction):
        directions = dict(left=(-1, 0), right=(+1, 0), up=(0, -1), down=(0, +1))
        self.facing = directions[direction]
        self.move(self.facing)
        if self.world[self.pos][0] == "lava":
            self.health = 0

    def _do_object(self, obj):
        damage = max(
            [
                1,
                self.inventory["wood_sword"] and 2,
                self.inventory["stone_sword"] and 3,
                self.inventory["iron_sword"] and 5,
            ]
        )
        if isinstance(obj, Plant):
            if obj.ripe:
                obj.grown = 0
                self.inventory["food"] += 4
                self.achievements["eat_plant"] += 1
        if isinstance(obj, Fence):
            self.world.remove(obj)
            self.inventory["fence"] += 1
            self.achievements["collect_fence"] += 1
        if isinstance(obj, Zombie):
            obj.take_damage(damage=damage)
            if obj.health <= 0:
                self.achievements["defeat_zombie"] += 1
        if isinstance(obj, Skeleton):
            obj.take_damage(damage=damage)
            if obj.health <= 0:
                self.achievements["defeat_skeleton"] += 1
        if isinstance(obj, FriendlyMob):
            obj.take_damage(damage=damage)
            if obj.health <= 0:
                self.inventory["food"] += obj.food_value
                self.achievements[f"eat_{obj.texture}"] += 1
                self._hunger = 0
        if isinstance(obj, NeutralMob):
            obj.take_damage(damage=damage)
            obj.angry = True
            if obj.health <= 0:
                self.inventory["food"] += obj.food_value
                self.achievements[f"eat_{obj.texture}"] += 1
                self._hunger = 0
        if isinstance(obj, Raider):
            obj.take_damage(damage=damage)
            if obj.health <= 0:
                self.achievements[f"defeat_raider"] += 1

    def _do_material(self, target, material):
        if material == "water":
            self._thirst = 0
        info = constants.collect.get(material)
        if not info:
            return
        for name, amount in info["require"].items():
            if self.inventory[name] < amount:
                return
        self.world[target] = info["leaves"]
        if self.random.uniform() <= info.get("probability", 1):
            for name, amount in info["receive"].items():
                self.inventory[name] += amount
                self.achievements[f"collect_{name}"] += 1
        takes = info.get("takes", None)
        if takes is not None:
            for name, amount in takes.items():
                self.inventory[name] -= amount

    def _place(self, name, target, material):
        if self.world[target][1]:
            return
        info = constants.place[name]
        if material not in info["where"]:
            return
        if any(self.inventory[k] < v for k, v in info["uses"].items()):
            return
        for item, amount in info["uses"].items():
            self.inventory[item] -= amount
        if info["type"] == "material":
            self.world[target] = name
        elif info["type"] == "object":
            cls = {
                "fence": Fence,
                "plant": Plant,
            }[name]
            self.world.add(cls(self.world, target))
        self.achievements[f"place_{name}"] += 1

    def _make(self, name):
        nearby, _ = self.world.nearby(self.pos, 1)
        info = constants.make[name]
        if not all(util in nearby for util in info["nearby"]):
            return
        if any(self.inventory[k] < v for k, v in info["uses"].items()):
            return
        for item, amount in info["uses"].items():
            self.inventory[item] -= amount

        if "armor" in name:
            self._armor = name.replace("_armor", "")
        else:
            self.inventory[name] += info["gives"]

        self.achievements[f"make_{name}"] += 1


class FriendlyMob(Object):
    def __init__(
        self,
        world,
        pos,
        texture: str,
        health: int,
        sense_of_a_straight_line: float,
        antsy: float,
        food_value: int,
    ):
        super().__init__(world, pos)
        self.health = health
        self.sosa = sense_of_a_straight_line
        self.antsy = antsy
        self.food_value = food_value
        self._texture = texture
        self._last_dir = None

    @property
    def texture(self):
        return self._texture

    def update(self):
        if self.health <= 0:
            self.world.remove(self)
        if self.random.uniform() < self.antsy:
            if self._last_dir is None:
                direction = self.random_dir()
            else:
                direction = (
                    self._last_dir
                    if self.random.uniform() < self.sosa
                    else self.random_dir()
                )
            self.move(direction)
            self._last_dir = direction


class Cow(FriendlyMob):
    def __init__(self, world, pos):
        super().__init__(
            world,
            pos,
            texture="cow",
            health=3,
            sense_of_a_straight_line=0.0,
            antsy=0.5,
            food_value=6,
        )


class Penguin(FriendlyMob):
    def __init__(self, world, pos):
        super().__init__(
            world,
            pos,
            texture="penguin",
            health=2,
            sense_of_a_straight_line=0.0,
            antsy=0.8,
            food_value=2,
        )


class Pig(FriendlyMob):
    def __init__(self, world, pos):
        super().__init__(
            world,
            pos,
            texture="pig",
            health=5,
            sense_of_a_straight_line=0.75,
            antsy=0.4,
            food_value=4,
        )


class Camel(FriendlyMob):
    def __init__(self, world, pos):
        super().__init__(
            world,
            pos,
            texture="camel",
            health=4,
            sense_of_a_straight_line=0.95,
            antsy=0.5,
            food_value=3,
        )


class NeutralMob(Object):
    def __init__(
        self,
        world,
        pos,
        player,
        texture: str,
        sense_of_straight_line: float,
        antsy: float,
        health: int,
        damage: int,
        cooldown: int,
        pursuit_distance: int,
        pursuit_long_axis: float,
        food_value: int,
    ):
        super().__init__(world, pos)
        self.player = player
        self._texture = texture
        self.sosa = sense_of_straight_line
        self.antsy = antsy
        self.health = health
        self.damage = damage
        self.cooldown = cooldown
        self._cur_cooldown = 0
        self.pursuit_distance = pursuit_distance
        self.pursuit_long_axis = pursuit_long_axis
        self.food_value = food_value
        self._last_dir = None
        self.angry = False

    @property
    def texture(self):
        return self._texture

    def update(self):
        if self.health <= 0:
            self.world.remove(self)
        dist = self.distance(self.player)
        if self.angry and dist < self.pursuit_distance:
            # attack
            self.move(
                self.toward(self.player, self.random.uniform() < self.pursuit_long_axis)
            )
            if dist <= 1:
                if self._cur_cooldown:
                    self._cur_cooldown -= 1
                else:
                    damage = 2 * self.damage if self.player.sleeping else self.damage
                    self.player.take_damage(damage)
                    self._cur_cooldown = self.cooldown
        elif self.angry and dist > self.pursuit_distance:
            # territory defended
            self.angry = False
        elif self.random.uniform() < self.antsy:
            # move somewhat predictably
            if self._last_dir is None:
                direction = self.random_dir()
            else:
                direction = (
                    self._last_dir
                    if self.random.uniform() < self.sosa
                    else self.random_dir()
                )
            self.move(direction)
            self._last_dir = direction


class Moose(NeutralMob):
    def __init__(self, world, pos, player):
        super().__init__(
            world,
            pos,
            player,
            texture="moose",
            sense_of_straight_line=0.8,
            antsy=0.2,
            health=8,
            damage=2,
            cooldown=3,
            pursuit_distance=15,
            pursuit_long_axis=0.7,
            food_value=8,
        )


class BrownBear(NeutralMob):
    def __init__(self, world, pos, player):
        super().__init__(
            world,
            pos,
            player,
            texture="brown_bear",
            sense_of_straight_line=0.7,
            antsy=0.1,
            health=10,
            damage=5,
            cooldown=4,
            pursuit_distance=25,
            pursuit_long_axis=0.8,
            food_value=9,
        )


class PolarBear(NeutralMob):
    def __init__(self, world, pos, player):
        super().__init__(
            world,
            pos,
            player,
            texture="polar_bear",
            sense_of_straight_line=0.65,
            antsy=0.12,
            health=11,
            damage=6,
            cooldown=3,
            pursuit_distance=20,
            pursuit_long_axis=0.8,
            food_value=9,
        )


class Raider(Object):
    def __init__(self, world, pos, player):
        super().__init__(world, pos)
        self.player = player
        self.health = 4
        # start with cooldown so player has time to deal damage before being robbed
        self.cooldown = 4
        self.satisfied = 0

    @property
    def texture(self):
        return "raider"

    def update(self):
        if self.health <= 0 or self.satisfied == 1:
            self.world.remove(self)
        dist = self.distance(self.player)

        if self.satisfied:
            if self.random.uniform() < 0.5:
                self.move(self.random_dir())
            self.satisfied -= 1
        elif dist <= 20 and self.random.uniform() < 0.9:
            self.move(self.toward(self.player, self.random.uniform() < 0.5))
        else:
            self.move(self.random_dir())

        if dist <= 1 and not self.satisfied:
            if self.cooldown:
                self.cooldown -= 1
            else:
                # steal resources
                inv = self.player.inventory
                if inv["coin"]:
                    inv["coin"] = 0
                    self.satisfied = 200
                elif inv["diamond"]:
                    inv["diamond"] = 0
                    self.satisfied = 200
                elif inv["gold"]:
                    inv["gold"] = 0
                    self.satisfied = 200
                elif inv["emerald"]:
                    inv["emerald"] = 0
                    self.satisfied = 200
                elif inv["wood"]:
                    inv["wood"] = 0
                    self.satisfied = 200
                else:
                    # don't call the bluff
                    self.player.take_damage(50)
                self.cooldown = 4


class Zombie(Object):
    def __init__(self, world, pos, player):
        super().__init__(world, pos)
        self.player = player
        self.health = 5
        self.cooldown = 0

    @property
    def texture(self):
        return "zombie"

    def update(self):
        if self.health <= 0:
            self.world.remove(self)
        dist = self.distance(self.player)
        if dist <= 8 and self.random.uniform() < 0.65:
            self.move(self.toward(self.player, self.random.uniform() < 0.8))
        else:
            self.move(self.random_dir())
        dist = self.distance(self.player)
        if dist <= 1:
            if self.cooldown:
                self.cooldown -= 1
            else:
                if self.player.sleeping:
                    damage = 7
                else:
                    damage = 2
                self.player.take_damage(damage)
                self.cooldown = 5


class Skeleton(Object):
    def __init__(self, world, pos, player):
        super().__init__(world, pos)
        self.player = player
        self.health = 3
        self.reload = 0

    @property
    def texture(self):
        return "skeleton"

    def update(self):
        if self.health <= 0:
            self.world.remove(self)
        self.reload = max(0, self.reload - 1)
        dist = self.distance(self.player.pos)
        if dist <= 3:
            moved = self.move(-self.toward(self.player, self.random.uniform() < 0.6))
            if moved:
                return
        if dist <= 5 and self.random.uniform() < 0.5:
            self._shoot(self.toward(self.player))
        elif dist <= 8 and self.random.uniform() < 0.3:
            self.move(self.toward(self.player, self.random.uniform() < 0.6))
        elif self.random.uniform() < 0.2:
            self.move(self.random_dir())

    def _shoot(self, direction):
        if self.reload > 0:
            return
        if direction[0] == 0 and direction[1] == 0:
            return
        pos = self.pos + direction
        if self.is_free(pos, Arrow.walkable):
            self.world.add(Arrow(self.world, pos, direction))
            self.reload = 4


class Arrow(Object):
    def __init__(self, world, pos, facing):
        super().__init__(world, pos)
        self.facing = facing

    @property
    def texture(self):
        return {
            (-1, 0): "arrow-left",
            (+1, 0): "arrow-right",
            (0, -1): "arrow-up",
            (0, +1): "arrow-down",
        }[tuple(self.facing)]

    @engine.staticproperty
    def walkable():
        return constants.walkable + ["water", "lava"]

    def update(self):
        target = self.pos + self.facing
        material, obj = self.world[target]
        if obj:
            obj.take_damage(damage=2)
            self.world.remove(self)
        elif material not in self.walkable:
            self.world.remove(self)
            if material in ["table", "furnace"]:
                self.world[target] = "path"
        else:
            self.move(self.facing)


class Plant(Object):
    def __init__(self, world, pos):
        super().__init__(world, pos)
        self.health = 1
        self.grown = 0

    @property
    def texture(self):
        if self.ripe:
            return "plant-ripe"
        else:
            return "plant"

    @property
    def ripe(self):
        return self.grown > 300

    def update(self):
        self.grown += 1
        objs = [self.world[self.pos + dir_][1] for dir_ in self.all_dirs]
        if any(
            isinstance(obj, (Zombie, Skeleton, FriendlyMob, NeutralMob)) for obj in objs
        ):
            self.take_damage(damage=1)
        if self.health <= 0:
            self.world.remove(self)


class Fence(Object):
    def __init__(self, world, pos):
        super().__init__(world, pos)

    @property
    def texture(self):
        return "fence"

    def update(self):
        pass

import argparse

import imageio
import numpy as np
import matplotlib.pyplot as plt

import expanded_crafter as crafter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--amount", type=int, default=1)
    parser.add_argument("--area", nargs=2, type=int, default=(256, 256))
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--filename", type=str, default="terrain.png")
    args = parser.parse_args()

    env = crafter.Env(args.area, args.area, args.size, seed=args.seed)
    images = []
    for index in range(args.amount):
        images.append(env.reset())
        coal = env._world.count("coal")
        iron = env._world.count("iron")
        gold = env._world.count("gold")
        emerald = env._world.count("emerald")
        diamonds = env._world.count("diamond")
        pyramids = env._world.count("pyramid")

        print(
            f"Map: {index:>2}, diamonds: {diamonds:>2}, iron: {iron:>2}, gold: {gold:>2}, emerald: {emerald:>2}, coal: {coal:>2}, pyramid: {pyramids:>2}"
        )

    max_worlds_per_col = 4
    rows = max(len(images) // max_worlds_per_col, 1)
    strips = []
    for row in range(rows):
        strip = []
        for col in range(min(max_worlds_per_col, len(images))):
            try:
                strip.append(images[row * max_worlds_per_col + col])
            except IndexError:
                strip.append(np.zeros_like(strip[-1]))
        strips.append(np.concatenate(strip, 1))
    grid = np.concatenate(strips, 0)

    imageio.imsave(args.filename, grid)
    print("Saved", args.filename)
    fig = plt.subplots(figsize=(25, 10))
    plt.imshow(grid)
    plt.show()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-


import os
from collections import deque


import numpy as np
from rlpack.algos import SAC
from rlpack.common import ContinuousActionMemory
from rlpack.environment import MujocoWrapper
from tensorboardX import SummaryWriter
from tqdm import tqdm
import argparse

parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('--env_name',  type=str, default="Reacher-v2")
args = parser.parse_args()


class Config(object):
    """Config."""

    def __init__(self):
        """All papameters here."""
        self.rnd = 1
        self.save_path = f"./log/sac/exp_{args.env_name}"

        # 环境
        self.n_env = 1
        self.dim_observation = None
        self.dim_action = None

        # 训练长度
        self.trajectory_length = None
        self.update_step = 5000   # for each env
        self.warm_start_length = 10000
        self.memory_size = int(1e6)

        # 周期参数
        self.log_freq = 1

        # 算法参数
        self.batch_size = 64
        self.discount = 0.99


def process_env(env):
    config = Config()
    config.dim_observation = env.dim_observation
    config.dim_action = env.dim_action
    config.trajectory_length = env.horizon_length if env.horizon_length > 0 else 500
    return config


def safemean(x):
    return np.nan if len(x) == 0 else np.mean(x)


def learn(env, agent, config):
    memory = ContinuousActionMemory(capacity=config.memory_size, n_env=config.n_env, dim_obs=config.dim_observation, dim_act=config.dim_action)
    epinfobuf = deque(maxlen=20)
    summary_writer = SummaryWriter(os.path.join(config.save_path, "summary"))

    # 热启动，随机收集数据。
    obs = env.reset()
    print("obs shape:", obs.shape)
    print(f"observation: max={np.max(obs)} min={np.min(obs)}")
    for i in tqdm(range(config.warm_start_length)):
        actions = env.sample_action()
        next_obs, rewards, dones, infos = env.step(actions)

        memory.store_sards(obs, actions, rewards, dones, next_obs)
        obs = next_obs

    print("Finish warm start.")
    print("Start training.")
    for i in tqdm(range(config.update_step)):
        epinfos = []
        for _ in range(config.trajectory_length):
            actions = agent.get_action(obs)
            next_obs, rewards, dones, infos = env.step(actions)

            for info in infos:
                maybeepinfo = info.get('episode')
                if maybeepinfo:
                    epinfos.append(maybeepinfo)

            memory.store_sards(obs, actions, rewards, dones, next_obs)
            obs = next_obs

        update_ratio = i / config.update_step
        for _ in range(config.trajectory_length):
            data_batch = memory.sample_transition(100)
            agent.update(data_batch, update_ratio)

        epinfobuf.extend(epinfos)
        summary_writer.add_scalar("eprewmean", safemean([epinfo["r"] for epinfo in epinfobuf]), global_step=i)
        summary_writer.add_scalar("eplenmean", safemean([epinfo['l'] for epinfo in epinfobuf]), global_step=i)

        if i > 0 and i % config.log_freq == 0:
            rewmean = safemean([epinfo["r"] for epinfo in epinfobuf])
            lenmean = safemean([epinfo['l'] for epinfo in epinfobuf])
            tqdm.write(f"iter: {i} eprewmean: {rewmean}  eplenmean: {lenmean}  rew: {epinfobuf[-1]['r']}  len: {epinfobuf[-1]['l']}")


if __name__ == "__main__":
    config = Config()
    env = MujocoWrapper(f"{args.env_name}", config.n_env)
    config = process_env(env)
    agent = SAC(rnd=1,
                dim_obs=config.dim_observation,
                dim_act=config.dim_action,
                discount=0.99,
                save_path=config.save_path,
                save_model_freq=100,
                log_freq=1000,
                policy_lr=1e-3,
                value_lr=1e-3,
                alpha=0.2,
                action_high=1.0,
                action_low=-1.0,
                moving_udpate_target_ratio=0.995
                )

    learn(env, agent, config)

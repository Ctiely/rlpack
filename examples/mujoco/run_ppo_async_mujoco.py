# -*- coding: utf-8 -*-


import os
from collections import deque


import numpy as np
from rlpack.algos import ContinuousPPO
from rlpack.common import AsyncContinuousActionMemory
from rlpack.environment import AsyncMujocoWrapper
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
        self.save_path = f"./log/ppo/exp_async_{args.env_name}"

        # 环境
        self.n_env = 2
        self.dim_observation = None
        self.dim_action = None   # gym中不同环境的action数目不同。

        # 训练长度
        self.trajectory_length = 2048
        self.update_step = 5000   # for each env
        self.warm_start_length = 2000
        self.memory_size = 2149

        # 周期参数
        self.training_epoch = 10
        self.save_model_freq = 50
        self.log_freq = 1

        # 算法参数
        # self.batch_size = 64
        # self.discount = 0.99
        # self.gae = 0.95
        # self.policy_lr_schedule = lambda x: 3e-4
        # self.value_lr_schedule = lambda x: 3e-4

        # self.clip_schedule = lambda x: (1 - x) * 0.1
        # self.vf_coef = 1.0
        # self.entropy_coef = 0.01
        # self.max_grad_norm = 40


def process_env(env):
    config = Config()
    config.dim_observation = env.dim_observation
    config.dim_action = env.dim_action
    return config


def safemean(x):
    return np.nan if len(x) == 0 else np.mean(x)


def learn(env, agent, config):
    memory = AsyncContinuousActionMemory(maxsize=config.memory_size, dim_obs=config.dim_observation, dim_act=config.dim_action)
    memory.register(env)
    epinfobuf = deque(maxlen=20)
    summary_writer = SummaryWriter(os.path.join(config.save_path, "summary"))

    # 热启动，随机收集数据。
    obs = env.reset()
    print("obs shape:", obs.shape)
    memory.store_s(obs)
    print(f"observation: max={np.max(obs)} min={np.min(obs)}")
    for i in tqdm(range(config.warm_start_length)):
        actions = env.sample_action(obs.shape[0])
        memory.store_a(actions)
        next_obs, rewards, dones, infos = env.step(actions)

        memory.store_rds(rewards, dones, next_obs)
        obs = next_obs

    print("Finish warm start.")
    print("Start training.")
    for i in tqdm(range(config.update_step)):
        epinfos = []
        for _ in range(config.trajectory_length):
            actions = agent.get_action(obs)
            memory.store_a(actions)
            next_obs, rewards, dones, infos = env.step(actions)

            for info in infos:
                maybeepinfo = info.get('episode')
                if maybeepinfo:
                    epinfos.append(maybeepinfo)

            memory.store_rds(rewards, dones, next_obs)
            obs = next_obs

        """
        Update the model.
        """
        update_ratio = i / config.update_step
        data_batch = memory.get_last_n_samples(config.trajectory_length)
        agent.update(data_batch, update_ratio)

        """
        Print trianing info.
        """
        epinfobuf.extend(epinfos)
        summary_writer.add_scalar("eprewmean", safemean([epinfo["r"] for epinfo in epinfobuf]), global_step=i)
        summary_writer.add_scalar("eplenmean", safemean([epinfo['l'] for epinfo in epinfobuf]), global_step=i)

        if i > 0 and i % config.log_freq == 0:
            rewmean = safemean([epinfo["r"] for epinfo in epinfobuf])
            lenmean = safemean([epinfo['l'] for epinfo in epinfobuf])
            tqdm.write(f"iter: {i} eprewmean: {rewmean}  eplenmean: {lenmean}  rew: {epinfobuf[-1]['r']}  len: {epinfobuf[-1]['l']}")


if __name__ == "__main__":
    config = Config()
    env = AsyncMujocoWrapper(f"{args.env_name}", config.n_env, config.n_env, 50013)
    config = process_env(env)
    agent = ContinuousPPO(rnd=1,
                          n_env=config.n_env,
                          dim_obs=config.dim_observation,
                          dim_act=config.dim_action,
                          discount=0.99,
                          gae=0.95,
                          save_path=f"./log/ppo/exp_async_{args.env_name}",
                          save_model_freq=50,
                          vf_coef=1.0,
                          entropy_coef=0.01,
                          max_grad_norm=40,
                          policy_lr_schedule=lambda x: 3e-4,
                          value_lr_schedule=lambda x: 3e-4,
                          trajectory_length=2048,
                          batch_size=64,
                          training_epoch=10)
    learn(env, agent, config)
